"""Turns a world into the files the app reads, and reads back what the orchestrator did.

Each version stores agents its own way, so each gets the world in its own format. The
right answers don't change; only how they are written down for the app does.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List

# Versions that write a hand-off entry into the conversation log. In real use they would
# have written one for each earlier hand-off, so the chat before a case includes them.
RECORDS_HANDOFFS = {"v2", "v2b", "v3", "v4", "v5"}
# Versions where each agent has a work record and the orchestrator sees candidates.
USES_RECORDS = RECORDS_HANDOFFS


def write_world(world: dict, roster: List[str], case: dict, version: str, data_dir: Path) -> None:
    from server.services.conversation import get_conversation_log
    from server.services.execution import get_agent_roster

    works, people = world["works"], world["people"]

    if version in USES_RECORDS:
        write_records(works, people, roster)
    else:
        agent_roster = get_agent_roster()
        agent_roster.load()
        for aid in roster:
            agent_roster._agents.append(works[aid]["name"])
        agent_roster.save()

    log = get_conversation_log()
    for entry in case["recent_chat"]:
        tag, text = entry["tag"], entry["text"]
        if tag == "user_message":
            log.record_user_message(text)
        elif tag == "poke_reply":
            log.record_reply(text)
        elif tag == "agent_message":
            log.record_agent_message(text)
        elif tag == "handoff" and version in RECORDS_HANDOFFS:
            log.record_handoff(entry["agent"], works[entry["agent"]]["name"], text)


def write_records(works: dict, people: dict, roster: List[str]) -> None:
    """Build each agent's work record the way the app would have: from the person named
    when the agent was created, and from the tool calls the agent went on to make. The
    calls go through the app's own record-keeping code, so its rules are what get tested."""
    from server.services.agents import get_agent_store, record_tool_call

    store = get_agent_store()
    in_roster = {works[aid][key] for aid in roster for key in ("person", "third")} - {None}
    with store.batch():
        for pid, p in people.items():
            # The user's contacts: everyone on an agent in the roster, and everyone in the core.
            if pid in in_roster or p["core"]:
                store.add_contact(p["email"], f"{p['first']} {p['last']}")
        for aid in roster:
            work = works[aid]
            store.create(work["name"], summary=work["summary"], agent_id=aid, created_at=work["started"])
            if work["person"]:
                p = people[work["person"]]
                store.add_person(aid, p["email"], f"{p['first']} {p['last']}")
            for turn in work["history"]:
                for call in turn["calls"]:
                    record_tool_call(store, aid, call["tool"], call["args"])


def read_turn(version: str, tool_calls: List[dict], names: Dict[str, str]) -> dict:
    """What the orchestrator did in one turn, in terms every version shares.

    existing: ids of agents that already existed and were handed work
    created:  new agents, each with the name and instructions it was given
    """
    existing: List[str] = []
    created: List[dict] = []
    if version in USES_RECORDS:
        for call in tool_calls:
            args, payload = call["arguments"], call["payload"] or {}
            if payload.get("status") != "submitted":
                continue   # refused: not an approved agent, or the duplicate check stepped in
            if call["name"] == "send_message_to_agent":
                existing.append(str(args.get("agent_id", "")))
            elif call["name"] == "create_agent":
                created.append({"name": str(args.get("title", "")), "instructions": str(args.get("instructions", "")),
                                "person_name": payload.get("person_name", ""), "person_email": payload.get("person_email", ""),
                                "throwaway": bool(payload.get("throwaway"))})
        return {"existing": sorted(set(existing)), "created": created}
    for call in tool_calls:
        if call["name"] != "send_message_to_agent":
            continue
        args = call["arguments"]
        name = str(args.get("agent_name", ""))
        if name in names:
            existing.append(names[name])
        else:
            created.append({"name": name, "instructions": str(args.get("instructions", "")), "throwaway": False})
    return {"existing": sorted(set(existing)), "created": created}
