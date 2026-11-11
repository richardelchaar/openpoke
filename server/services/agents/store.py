"""One work record per agent, in SQLite.

A record says who an agent has dealt with, on which threads, what it searched for, and in
one line what its work is about. The lookup searches these records to find candidates for
a message, and the agent reads its own record as memory.
"""

from __future__ import annotations

import re
import secrets
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple

from ...config import get_data_dir
from ...logging_config import logger

SCHEMA = """
CREATE TABLE IF NOT EXISTS agents (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    summary     TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'active',     -- active | discarded
    throwaway   INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL,
    last_used   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS agent_people (
    agent_id TEXT NOT NULL, email TEXT NOT NULL, name TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (agent_id, email)
);
CREATE TABLE IF NOT EXISTS agent_threads (
    agent_id TEXT NOT NULL, thread_id TEXT NOT NULL, subject TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (agent_id, thread_id)
);
CREATE TABLE IF NOT EXISTS agent_notes (                 -- past search queries and reminders
    agent_id TEXT NOT NULL, kind TEXT NOT NULL, text TEXT NOT NULL,
    PRIMARY KEY (agent_id, kind, text)
);
CREATE TABLE IF NOT EXISTS contacts (
    email TEXT PRIMARY KEY, name TEXT NOT NULL
);
CREATE VIRTUAL TABLE IF NOT EXISTS agent_search USING fts5(
    agent_id UNINDEXED, title, summary, subjects, people, notes,
    tokenize = 'porter unicode61'
);
"""

# How many of each kind of fact a record keeps. A long-lived agent can't grow without limit.
MAX_PEOPLE, MAX_THREADS, MAX_NOTES = 25, 25, 25

_WORD = re.compile(r"[a-z0-9']+")


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class AgentStore:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path, check_same_thread=False, timeout=30)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._batching = False
        self._dirty: set[str] = set()   # agents whose search row needs rewriting
        with self._lock:
            self._db.executescript(SCHEMA)
            self._db.commit()

    # -- writing ---------------------------------------------------------------------
    @contextmanager
    def batch(self) -> Iterator[None]:
        """Group many writes into one commit."""
        with self._lock:
            self._batching = True
            try:
                yield
            finally:
                self._batching = False
                for agent_id in self._dirty:
                    self._index(agent_id)
                self._dirty.clear()
                self._db.commit()

    def _write(self, sql: str, params: tuple = ()) -> None:
        with self._lock:
            self._db.execute(sql, params)
            if not self._batching:
                self._db.commit()

    def create(self, title: str, *, summary: str = "", throwaway: bool = False,
               agent_id: Optional[str] = None, created_at: Optional[str] = None) -> str:
        agent_id = agent_id or f"ag_{secrets.token_hex(4)}"
        when = created_at or _now()
        self._write("INSERT INTO agents (id, title, summary, throwaway, created_at, last_used) VALUES (?, ?, ?, ?, ?, ?)",
                    (agent_id, title.strip(), summary.strip(), int(throwaway), when, when))
        self.reindex(agent_id)
        return agent_id

    def add_person(self, agent_id: str, email: str, name: str = "") -> None:
        email = email.strip().lower()
        if not email or self._count("agent_people", agent_id) >= MAX_PEOPLE:
            return
        name = name.strip() or self.contact_name(email)
        self._write("INSERT INTO agent_people (agent_id, email, name) VALUES (?, ?, ?) "
                    "ON CONFLICT (agent_id, email) DO UPDATE SET name = CASE WHEN excluded.name != '' THEN excluded.name ELSE name END",
                    (agent_id, email, name))
        self.reindex(agent_id)

    def add_thread(self, agent_id: str, thread_id: str, subject: str = "") -> None:
        if not thread_id or self._count("agent_threads", agent_id) >= MAX_THREADS:
            return
        self._write("INSERT INTO agent_threads (agent_id, thread_id, subject) VALUES (?, ?, ?) "
                    "ON CONFLICT (agent_id, thread_id) DO UPDATE SET subject = CASE WHEN excluded.subject != '' THEN excluded.subject ELSE subject END",
                    (agent_id, thread_id, subject.strip()))
        self.reindex(agent_id)

    def add_note(self, agent_id: str, kind: str, text: str) -> None:
        text = text.strip()
        if not text or self._count("agent_notes", agent_id) >= MAX_NOTES:
            return
        self._write("INSERT OR IGNORE INTO agent_notes (agent_id, kind, text) VALUES (?, ?, ?)", (agent_id, kind, text[:300]))
        self.reindex(agent_id)

    def set_summary(self, agent_id: str, summary: str) -> None:
        self._write("UPDATE agents SET summary = ? WHERE id = ?", (summary.strip(), agent_id))
        self.reindex(agent_id)

    def touch(self, agent_id: str) -> None:
        self._write("UPDATE agents SET last_used = ? WHERE id = ?", (_now(), agent_id))

    def discard(self, agent_id: str) -> None:
        """A throwaway agent that has finished. It never comes back in a lookup."""
        self._write("UPDATE agents SET status = 'discarded' WHERE id = ?", (agent_id,))
        self._write("DELETE FROM agent_search WHERE agent_id = ?", (agent_id,))

    def add_contact(self, email: str, name: str) -> None:
        if email and name:
            self._write("INSERT OR REPLACE INTO contacts (email, name) VALUES (?, ?)", (email.strip().lower(), name.strip()))

    def clear(self) -> None:
        with self.batch():
            for table in ("agents", "agent_people", "agent_threads", "agent_notes", "agent_search"):
                self._db.execute(f"DELETE FROM {table}")

    def reindex(self, agent_id: str) -> None:
        """Rewrite the agent's row in the search index from its record."""
        with self._lock:
            if self._batching:
                self._dirty.add(agent_id)
                return
            self._index(agent_id)
            self._db.commit()

    def _index(self, agent_id: str) -> None:
        record = self.get(agent_id)
        with self._lock:
            self._db.execute("DELETE FROM agent_search WHERE agent_id = ?", (agent_id,))
            if record and record["status"] == "active" and not record["throwaway"]:
                self._db.execute(
                    "INSERT INTO agent_search (agent_id, title, summary, subjects, people, notes) VALUES (?, ?, ?, ?, ?, ?)",
                    (agent_id, record["title"], record["summary"],
                     " . ".join(t["subject"] for t in record["threads"]),
                     " . ".join(f"{p['name']} {p['email']}" for p in record["people"]),
                     " . ".join(n["text"] for n in record["notes"])))

    # -- reading ---------------------------------------------------------------------
    def _count(self, table: str, agent_id: str) -> int:
        with self._lock:
            return self._db.execute(f"SELECT COUNT(*) FROM {table} WHERE agent_id = ?", (agent_id,)).fetchone()[0]

    def get(self, agent_id: str) -> Optional[dict]:
        with self._lock:
            row = self._db.execute("SELECT * FROM agents WHERE id = ?", (agent_id,)).fetchone()
            if row is None:
                return None
            record = dict(row)
            record["people"] = [dict(r) for r in self._db.execute(
                "SELECT email, name FROM agent_people WHERE agent_id = ? ORDER BY rowid", (agent_id,))]
            record["threads"] = [dict(r) for r in self._db.execute(
                "SELECT thread_id, subject FROM agent_threads WHERE agent_id = ? ORDER BY rowid", (agent_id,))]
            record["notes"] = [dict(r) for r in self._db.execute(
                "SELECT kind, text FROM agent_notes WHERE agent_id = ? ORDER BY rowid", (agent_id,))]
            return record

    def exists(self, agent_id: str) -> bool:
        with self._lock:
            return self._db.execute("SELECT 1 FROM agents WHERE id = ? AND status = 'active'", (agent_id,)).fetchone() is not None

    def count(self) -> int:
        with self._lock:
            return self._db.execute("SELECT COUNT(*) FROM agents WHERE status = 'active' AND throwaway = 0").fetchone()[0]

    def contact_name(self, email: str) -> str:
        with self._lock:
            row = self._db.execute("SELECT name FROM contacts WHERE email = ?", (email.strip().lower(),)).fetchone()
            return row[0] if row else ""

    def known_people(self) -> List[dict]:
        """Everyone the user knows: contacts, and the people on agents' records.
        Each comes with the agents that have dealt with them."""
        with self._lock:
            people: Dict[str, dict] = {}
            for row in self._db.execute("SELECT email, name FROM contacts"):
                people[row["email"]] = {"email": row["email"], "name": row["name"], "agents": []}
            rows = self._db.execute(
                "SELECT p.email, p.name, p.agent_id FROM agent_people p JOIN agents a ON a.id = p.agent_id "
                "WHERE a.status = 'active' AND a.throwaway = 0")
            for row in rows:
                person = people.setdefault(row["email"], {"email": row["email"], "name": row["name"], "agents": []})
                person["name"] = person["name"] or row["name"]
                person["agents"].append(row["agent_id"])
            return list(people.values())

    def search(self, text: str) -> List[Tuple[str, float]]:
        """Agents whose record shares words with the text, best first. A higher score is a
        better match (BM25: rare words count more, word endings are ignored)."""
        terms = sorted(set(_WORD.findall(text.lower())))
        if not terms:
            return []
        query = " OR ".join(f'"{t}"' for t in terms)
        with self._lock:
            try:
                rows = self._db.execute(
                    "SELECT agent_id, bm25(agent_search) AS rank FROM agent_search WHERE agent_search MATCH ? ORDER BY rank",
                    (query,)).fetchall()
            except sqlite3.OperationalError as exc:
                logger.warning(f"Agent search failed: {exc}")
                return []
        return [(row["agent_id"], -row["rank"]) for row in rows]


_store: Optional[AgentStore] = None
_store_lock = threading.Lock()


def get_agent_store() -> AgentStore:
    global _store
    with _store_lock:
        if _store is None:
            _store = AgentStore(get_data_dir() / "agents.db")
        return _store
