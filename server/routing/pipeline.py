"""What happens to a message before the orchestrator sees it.

Looks up the candidate agents, lets the configured decider say what is allowed this turn,
and renders both for the orchestrator's prompt. The result is also the trace of the turn.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, field
from html import escape
from typing import Any, Dict, List, Optional

from ..config import get_settings
from ..services.agents import get_agent_store
from ..services.conversation import get_conversation_log
from .lookup import RECENT_HANDOFFS, LookupResult, lookup


@dataclass
class Routing:
    lookup: LookupResult
    approved: List[str]                    # agents the orchestrator may hand off to this turn
    may_create: bool = True
    note: str = ""                         # the decision, in words, for the orchestrator
    decision: Dict[str, Any] = field(default_factory=dict)

    def trace(self) -> Dict[str, Any]:
        return {
            "candidates": [{"agent_id": c.agent_id, "title": c.title, "why": c.why, "score": c.score}
                           for c in self.lookup.candidates],
            "people": [{"name": p.name, "email": p.email, "agents": p.agents, "full_name": p.full_name}
                       for p in self.lookup.people],
            "approved": self.approved,
            "may_create": self.may_create,
            "decision": self.decision,
        }


_current: ContextVar[Optional[Routing]] = ContextVar("routing", default=None)


def current_routing() -> Optional[Routing]:
    return _current.get()


def set_routing(routing: Optional[Routing]) -> None:
    _current.set(routing)


async def route_message(text: str, from_user: bool = True) -> Optional[Routing]:
    """Run the lookup and the decider for one message. None when the lookup is switched off."""
    settings = get_settings()
    if settings.routing_lookup != "records":
        return None
    store = get_agent_store()
    log = get_conversation_log()
    result = lookup(text, store, log.recent_handoffs(RECENT_HANDOFFS), last_shown=log.last_shown())
    routing = Routing(result, [c.agent_id for c in result.candidates])
    # Only a user's message is put to the decider. An agent's report is not a request.
    if from_user and settings.routing_decider in ("code_rule", "judge"):
        from .decide import decide
        await decide(text, routing)
    return routing


# Why a candidate is in the list, as the orchestrator and the judge are told it.
FOUND_BY = {
    "recent": "used in the last few messages",
    "person": "the person named in the message",
    "first_name": "a first name in the message",
    "chat": "the person in the last message shown to the user",
    "topic": "topic words only",
}


def render_candidates(routing: Routing) -> str:
    if not routing.lookup.candidates:
        return "<candidate_agents>\nNone\n</candidate_agents>"
    blocks: List[str] = []
    for c in routing.lookup.candidates:
        found = ", ".join(FOUND_BY[w] for w in c.why)
        lines = [f'<agent id="{escape(c.agent_id, quote=True)}" title="{escape(c.title, quote=True)}" found_by="{found}">']
        if c.people:
            lines.append("people: " + ", ".join(escape(f"{p['name']} <{p['email']}>".strip()) for p in c.people[:4]))
        if c.subjects:
            lines.append("threads: " + ", ".join(f'"{escape(s)}"' for s in c.subjects[:3]))
        if c.summary:
            lines.append("about: " + escape(c.summary))
        lines.append("</agent>")
        blocks.append("\n".join(lines))
    return "<candidate_agents>\n" + "\n".join(blocks) + "\n</candidate_agents>"


def render_contacts(routing: Routing) -> str:
    if not routing.lookup.people:
        return ""
    lines = []
    for p in routing.lookup.people:
        has = f"agents: {', '.join(p.agents)}" if p.agents else "no agent yet"
        lines.append(f"- {escape(p.name)} <{escape(p.email)}> ({has})")
    return "<matched_contacts>\n" + "\n".join(lines) + "\n</matched_contacts>"
