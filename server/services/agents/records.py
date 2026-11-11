"""Keeps an agent's work record current from the tool calls it makes.

Facts are copied from the arguments of the call, so an address or thread ID on a record is
the exact one the agent used. Only what the agent acted on is recorded: drafts, sends,
replies, forwards and reminders. A search records the query and nothing from its results,
so an agent that read the whole inbox does not end up matching every name in it.
"""

from __future__ import annotations

from typing import Any, Dict

from .store import AgentStore


def record_tool_call(store: AgentStore, agent_id: str, tool: str, args: Dict[str, Any]) -> None:
    def text(key: str) -> str:
        value = args.get(key)
        return value.strip() if isinstance(value, str) else ""

    if tool == "gmail_create_draft":
        store.add_person(agent_id, text("recipient_email"))
        for extra in list(args.get("cc") or []) + list(args.get("bcc") or []):
            if isinstance(extra, str):
                store.add_person(agent_id, extra)
        # A draft has no thread yet unless it replies on one; the subject is kept either way.
        store.add_thread(agent_id, text("thread_id") or f"subject:{text('subject').lower()}", text("subject"))
    elif tool == "gmail_reply_to_thread":
        store.add_person(agent_id, text("recipient_email"))
        store.add_thread(agent_id, text("thread_id"))
    elif tool == "gmail_forward_email":
        store.add_person(agent_id, text("recipient_email"))
    elif tool in ("createTrigger", "updateTrigger"):
        store.add_note(agent_id, "reminder", text("payload"))
    elif tool == "task_email_search":
        store.add_note(agent_id, "query", text("search_query"))
    elif tool == "gmail_search_people":
        store.add_note(agent_id, "query", text("query"))
    store.touch(agent_id)
