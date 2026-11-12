"""Emails wait here until the user has seen them and approved them.

Execution agents can draft, reply and forward, but nothing they write is sent at once.
Each of those calls records a held email and returns its approval id. An email leaves
only through `send`, and only after `approve`, which needs two things: the user's own
turn, and the email's exact text already shown to the user. Each approval sends once.

Before this, reply and forward sent immediately, and only a line in a prompt asked the
model to check with the user first.
"""

from __future__ import annotations

import json
import re
import secrets
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from ..config import get_data_dir

SCHEMA = """
CREATE TABLE IF NOT EXISTS held_emails (
    id           TEXT PRIMARY KEY,
    kind         TEXT NOT NULL,            -- draft | reply | forward
    recipient    TEXT NOT NULL,
    subject      TEXT NOT NULL DEFAULT '',
    body         TEXT NOT NULL DEFAULT '',
    gmail_args   TEXT NOT NULL,            -- what is sent to Gmail once approved
    draft_id     TEXT,                     -- for a draft: Gmail's id for it
    created_at   TEXT NOT NULL,
    approved_at  TEXT,
    sent_at      TEXT
);
CREATE INDEX IF NOT EXISTS held_emails_draft ON held_emails (draft_id);
"""


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _normal(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


class ApprovalError(Exception):
    """An email that may not be approved or sent, with the reason."""


class ApprovalStore:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path, check_same_thread=False, timeout=30)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._db.executescript(SCHEMA)
            self._db.commit()

    def hold(self, kind: str, *, recipient: str, gmail_args: Dict[str, Any], subject: str = "",
             body: str = "", draft_id: Optional[str] = None) -> dict:
        """Record an email that is not to be sent until it is approved."""
        held_id = f"ap_{secrets.token_hex(4)}"
        with self._lock:
            self._db.execute(
                "INSERT INTO held_emails (id, kind, recipient, subject, body, gmail_args, draft_id, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (held_id, kind, recipient.strip(), subject or "", body or "",
                 json.dumps(gmail_args, sort_keys=True), draft_id, _now()))
            self._db.commit()
        return self.get(held_id)

    def get(self, held_id: str) -> Optional[dict]:
        with self._lock:
            row = self._db.execute("SELECT * FROM held_emails WHERE id = ?", (held_id,)).fetchone()
        if row is None:
            return None
        held = dict(row)
        held["gmail_args"] = json.loads(held["gmail_args"])
        return held

    def for_draft(self, draft_id: str) -> Optional[dict]:
        with self._lock:
            row = self._db.execute(
                "SELECT id FROM held_emails WHERE draft_id = ? ORDER BY created_at DESC LIMIT 1", (draft_id,)).fetchone()
        return self.get(row[0]) if row else None

    def awaiting_approval(self) -> bool:
        with self._lock:
            row = self._db.execute(
                "SELECT 1 FROM held_emails WHERE approved_at IS NULL AND sent_at IS NULL LIMIT 1").fetchone()
        return row is not None

    def approve(self, held_id: str, *, from_user: bool, shown: Iterable[str]) -> dict:
        """Approve one held email. `shown` is everything the user has been shown so far."""
        held = self.get(held_id)
        if held is None:
            raise ApprovalError(f"There is no held email with the id {held_id}.")
        if not from_user:
            raise ApprovalError("Only the user can approve sending. This turn was not started by the user.")
        if held["sent_at"]:
            raise ApprovalError("That email has already been sent. Sending it again needs a new approval.")
        if not self._was_shown(held, shown):
            raise ApprovalError("The user has not been shown this email's exact text yet. "
                                "Show it with send_draft and wait for their answer.")
        with self._lock:
            self._db.execute("UPDATE held_emails SET approved_at = ? WHERE id = ?", (_now(), held_id))
            self._db.commit()
        return self.get(held_id)

    def take_for_sending(self, held_id: str) -> dict:
        """Mark an approved email as sent and return it. Each approval sends once."""
        with self._lock:
            row = self._db.execute(
                "UPDATE held_emails SET sent_at = ? WHERE id = ? AND approved_at IS NOT NULL AND sent_at IS NULL "
                "RETURNING id", (_now(), held_id)).fetchone()
            self._db.commit()
        if row is None:
            held = self.get(held_id)
            if held is None:
                raise ApprovalError(f"There is no held email with the id {held_id}.")
            if held["sent_at"]:
                raise ApprovalError("That email has already been sent.")
            raise ApprovalError("The user has not approved this email. It stays unsent.")
        return self.get(held_id)

    def put_back(self, held_id: str) -> None:
        """Undo `take_for_sending` when Gmail refused the send, so it can be retried."""
        with self._lock:
            self._db.execute("UPDATE held_emails SET sent_at = NULL WHERE id = ?", (held_id,))
            self._db.commit()

    @staticmethod
    def _was_shown(held: dict, shown: Iterable[str]) -> bool:
        """Was the email's exact text shown to the user? For a forward, the recipient and
        any note added to it; otherwise the recipient and the whole body. Whitespace
        differences are ignored."""
        needed = [held["recipient"].lower()]
        body = held["gmail_args"].get("additional_text") if held["kind"] == "forward" else held["body"]
        if body:
            needed.append(_normal(body).lower())
        return any(all(part in _normal(text).lower() for part in needed) for text in shown)


_store: Optional[ApprovalStore] = None
_store_lock = threading.Lock()


def get_approval_store() -> ApprovalStore:
    global _store
    with _store_lock:
        if _store is None:
            _store = ApprovalStore(get_data_dir() / "approvals.db")
        return _store
