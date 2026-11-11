"""Finds the agents that might be meant by a message. No model call.

Four sources, combined:
  recent   the agents in the last few hand-offs, which is what makes "reply to her" work
  people   agents that have dealt with anyone the message names
  topic    agents whose record shares words with the message (keyword search)
  chat     when the message names nobody, the people named in the last thing the user was
           shown, which is what makes "reply to that" work after an email alert

The result is a short list of candidates, each with why it is there, and the people the
message's names matched, including contacts who have no agent yet.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ..services.agents import AgentStore

RECENT_HANDOFFS = 3     # how many past hand-offs count as recent
TOPIC_MATCHES = 5       # how many agents the keyword search may add
MAX_CANDIDATES = 10

_WORD = re.compile(r"[a-z0-9']+")
STOP_WORDS = set("""a about all also am an and any are as ask at back be been but by can check could did do does
    email for from get got had has have he her him his how i if in is it its just know let me my need new no not
    of on one or our out please reply say see send she so tell that the their them then there they this to up us
    was we were what when where which who will with would yes yet you your""".split())


@dataclass
class Candidate:
    agent_id: str
    title: str
    summary: str
    people: List[dict]
    subjects: List[str]
    why: List[str] = field(default_factory=list)   # recent | person | first_name | chat | topic
    score: float = 0.0                              # keyword score against the message


@dataclass
class MatchedPerson:
    name: str
    email: str
    agents: List[str]
    full_name: bool        # the message gave more than a first name
    said: str = ""         # the word in the message that matched, e.g. "omar"


@dataclass
class LookupResult:
    candidates: List[Candidate]
    people: List[MatchedPerson]

    def get(self, agent_id: str) -> Optional[Candidate]:
        return next((c for c in self.candidates if c.agent_id == agent_id), None)


def words(text: str) -> List[str]:
    return _WORD.findall(text.lower())


def match_people(message: str, store: AgentStore) -> List[MatchedPerson]:
    """Everyone the user knows whose name appears in the message.

    A person named in full shuts out people who only share the first name: "email Omar
    Kaur" is about one Omar.
    """
    tokens = set(words(message))
    matched: List[MatchedPerson] = []
    for person in store.known_people():
        parts = [p for p in words(person["name"]) if len(p) > 1]
        if not parts:
            continue
        hits = [p for p in parts if p in tokens]
        if person["email"] in message.lower():
            matched.append(MatchedPerson(person["name"], person["email"], person["agents"], True, person["email"]))
        elif hits:
            matched.append(MatchedPerson(person["name"], person["email"], person["agents"], len(hits) >= 2, hits[0]))
    if any(p.full_name for p in matched):
        matched = [p for p in matched if p.full_name]
    return matched


def lookup(message: str, store: AgentStore, recent: List[str], limit: int = MAX_CANDIDATES,
           last_shown: str = "") -> LookupResult:
    people = match_people(message, store)
    from_chat: List[MatchedPerson] = []
    if not people and last_shown:
        from_chat = match_people(last_shown, store)
    name_words = {w for p in people for w in words(p.name)}
    topic_text = " ".join(w for w in words(message) if w not in STOP_WORDS and w not in name_words and len(w) > 2)
    scores: Dict[str, float] = dict(store.search(topic_text))

    why: Dict[str, List[str]] = {}

    def add(agent_id: str, reason: str) -> None:
        reasons = why.setdefault(agent_id, [])
        if reason not in reasons:
            reasons.append(reason)

    for agent_id in recent[:RECENT_HANDOFFS]:
        record = store.get(agent_id)
        if record and record["status"] == "active" and not record["throwaway"]:
            add(agent_id, "recent")
    for person in people:
        for agent_id in person.agents:
            add(agent_id, "person" if person.full_name else "first_name")
    for person in from_chat:
        for agent_id in person.agents:
            add(agent_id, "chat")
    for agent_id in list(scores)[:TOPIC_MATCHES]:
        add(agent_id, "topic")

    def rank(agent_id: str) -> tuple:
        reasons = why[agent_id]
        named = "person" in reasons or "first_name" in reasons or "chat" in reasons
        return (0 if "recent" in reasons else 1, 0 if named else 1, -scores.get(agent_id, 0.0))

    candidates: List[Candidate] = []
    for agent_id in sorted(why, key=rank)[:limit]:
        record = store.get(agent_id)
        if not record:
            continue
        candidates.append(Candidate(
            agent_id=agent_id,
            title=record["title"],
            summary=record["summary"],
            people=record["people"],
            subjects=[t["subject"] for t in record["threads"] if t["subject"]],
            why=why[agent_id],
            score=round(scores.get(agent_id, 0.0), 3),
        ))
    return LookupResult(candidates, people)
