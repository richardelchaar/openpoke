"""Decides, before the orchestrator runs, whether a message should be routed, should
create something new, or needs a question first.

Two deciders share one output. Both leave the result on the Routing: which agents the
orchestrator may hand off to this turn, whether it may create one, and a note saying what
was decided. The hand-off tool refuses anything else, so a question can't be skipped.

  code_rule   no model call. Works from the lookup's keyword scores.
  judge       one model call labels every candidate, then code counts the labels.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from ..config import get_settings
from ..logging_config import logger
from ..openrouter_client import request_chat_completion
from ..services.conversation import get_conversation_log
from .lookup import Candidate, MatchedPerson
from .pipeline import Routing, render_candidates, render_contacts


async def decide(text: str, routing: Routing) -> None:
    settings = get_settings()
    if settings.routing_decider == "code_rule":
        steps = code_rule(routing, settings.routing_ask_margin)
        routing.decision = {"decider": "code_rule", "margin": settings.routing_ask_margin, "steps": steps}
    else:
        report = await judge(text, routing)
        if report is None:   # the judge failed twice: let the orchestrator pick from the candidates
            routing.decision = {"decider": "judge", "fallback": True}
            return
        steps = count_labels(report, routing, settings.routing_ask)
        routing.decision = {"decider": "judge", "ask": settings.routing_ask, "report": report, "steps": steps}
    apply(steps, routing)


# -- shared: turning steps into what the orchestrator may do -------------------------

def apply(steps: List[dict], routing: Routing) -> None:
    """Each step is one of: route, ask, create, none, open (no decision, orchestrator picks)."""
    if not steps or all(s["do"] == "open" for s in steps):
        return
    approved: List[str] = []
    may_create = False
    lines: List[str] = []
    for step in steps:
        if step["do"] == "route":
            approved += step["agents"]
            may_create = may_create or bool(step.get("or_create"))
            titles = ", ".join(f"{a} ({_title(routing, a)})" for a in step["agents"])
            lines.append(f"- {step['about']}: hand off to {titles}."
                         + (" If it is clearly new work, create an agent for it." if step.get("or_create") else ""))
        elif step["do"] == "ask":
            options = "; ".join(step["options"])
            lines.append(f"- {step['about']}: ASK the user which they mean. Do not call any agent for this. "
                         f"Name these options: {options}; and offer \"something new\".")
        elif step["do"] == "create":
            may_create = True
            who = f" for {step['person']}" if step.get("person") else ""
            kind = " Use throwaway=true: it is a one-off lookup." if step.get("throwaway") else ""
            lines.append(f"- {step['about']}: this is new work. Create an agent{who}.{kind}")
        elif step["do"] == "none":
            lines.append(f"- {step['about']}: no agent is needed. Reply yourself.")
        else:
            approved += step.get("agents", [])
            may_create = True
            lines.append(f"- {step['about']}: nothing was decided. Choose from the candidates or create an agent.")
    routing.approved = list(dict.fromkeys(approved))
    routing.may_create = may_create
    routing.note = "\n".join(lines)


def _title(routing: Routing, agent_id: str) -> str:
    candidate = routing.lookup.get(agent_id)
    return candidate.title if candidate else agent_id


def _option(routing: Routing, agent_id: str) -> str:
    c = routing.lookup.get(agent_id)
    if not c:
        return agent_id
    who = c.people[0]["name"] if c.people else ""
    return f"{who}: {c.summary or c.title}".strip(": ")


# -- the code rule -------------------------------------------------------------------

def code_rule(routing: Routing, margin: float) -> List[dict]:
    """Ask when a name in the message could mean more than one thing and the message's
    words don't favour one.

    People are grouped by the name the user wrote. A full name is one person; a first name
    is everyone who has it. Within a group the options are those people's agents, plus any
    of them who has no agent yet. If the best option's keyword score doesn't beat the next
    by `margin` (as a share of the best), the words haven't settled it, so ask.
    """
    groups: Dict[str, List[MatchedPerson]] = {}
    for person in routing.lookup.people:
        groups.setdefault(person.email if person.full_name else person.said, []).append(person)
    if not groups:
        return [{"do": "open", "about": "the message", "agents": [c.agent_id for c in routing.lookup.candidates]}]

    recent = [c.agent_id for c in routing.lookup.candidates if "recent" in c.why]
    steps: List[dict] = []
    for people in groups.values():
        about = people[0].name if len(people) == 1 else f"\"{people[0].said}\""
        agents = [c for c in routing.lookup.candidates if any(c.agent_id in p.agents for p in people)]
        without = [p for p in people if not p.agents]
        if not agents and len(without) == 1:
            steps.append({"do": "create", "about": about, "person": f"{without[0].name} <{without[0].email}>"})
        elif len(agents) == 1 and not without:
            steps.append({"do": "route", "about": about, "agents": [agents[0].agent_id], "or_create": True})
        elif agents:
            ranked = sorted(agents, key=lambda c: -c.score)
            top = ranked[0].score
            second = ranked[1].score if len(ranked) > 1 else 0.0
            if top > 0 and (top - second) / top >= margin:
                steps.append({"do": "route", "about": about, "agents": [ranked[0].agent_id], "or_create": True})
            else:
                options = [_option(routing, c.agent_id) for c in ranked[:4]] + [f"{p.name} (no work with them yet)" for p in without]
                steps.append({"do": "ask", "about": about, "options": options,
                              "option_agents": [c.agent_id for c in ranked[:4]]})
        else:
            options = [f"{p.name} (no work with them yet)" for p in without]
            steps.append({"do": "ask", "about": about, "options": options, "option_agents": []})
    # Whatever was said just before stays reachable, for "send it" in the same breath.
    for step in steps:
        if step["do"] == "route":
            step["agents"] += [a for a in recent if a not in step["agents"]][:0]
    return steps


# -- the judge -----------------------------------------------------------------------

JUDGE_PROMPT = """You sort an incoming message for an email assistant. The assistant keeps one agent per piece of work: one thread or task with one person. You are given the recent chat, the user's new message, the candidate agents that might be meant, and people in the user's contacts whose names match.

You do not choose an agent. You judge each candidate on its own, for each task in the message.

First, the message as a whole:
- "chat": thanks, small talk, or a general question. No agent is needed.
- "work": something to do with the user's email or the people in it.

Then list the tasks. Most messages have one. "Ask Bo for the invoice and tell Di I'm late" has two.

For each task, give every candidate agent one label:
- "exact": the task continues this agent's piece of work. The person and the topic both fit, or the chat makes clear this is the one (the draft just shown, the email just mentioned, "reply to that").
- "plausible": it could be this agent's work, but the message does not say enough to be sure, and something else could equally be meant.
- "same_person_other_work": the right person, but the task is clearly about something else than this agent's work.
- "unrelated": a different person or nothing to do with it.

And give each matched contact who has no agent yet one label: "exact" if the task clearly means that person (for instance their full name is given), "plausible" if they could be the one meant, "unrelated" otherwise.

How to judge:
- A person and a topic are named: the agent holding that topic for that person is "exact". That person's other agents are "same_person_other_work".
- A person is named, with more than one agent, and nothing says which piece of work ("follow up with Bo", "nudge Bo"): each of their agents is "plausible".
- A first name fits more than one person and nothing says which: each of them is "plausible". This includes a contact with no agent.
- A full name is given: people who only share the first name are "unrelated".
- A new topic for a person who already has an agent for something else: their agents are "same_person_other_work". It is new work.
- Use the chat. "it", "that", "them" point at the most recent hand-off. "No, the other Bo" means the Bo who was NOT just used: that one is "exact" and the one just used is "unrelated".
- If the user has just answered a question about which one, their answer settles it.
- Different words can mean the same work ("the fender-bender" for an auto claim). Judge by meaning.
- Do not label something "plausible" only because it shares a name. If the topic rules it out, say so.

For each task also say:
- "sends": true if doing it would send, reply or forward something to someone; false if it only reads or looks something up.
- "one_off": true if it is a quick lookup that belongs to no ongoing piece of work.
- "person": the full name of the person the task is with, if the message makes that clear, otherwise "".
"""

REPORT_TOOL = {
    "type": "function",
    "function": {
        "name": "report",
        "description": "Report the judgment of the message.",
        "parameters": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": ["chat", "work"]},
                "tasks": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "what": {"type": "string", "description": "The task in a few words."},
                            "sends": {"type": "boolean"},
                            "one_off": {"type": "boolean"},
                            "person": {"type": "string"},
                            "agents": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "agent_id": {"type": "string"},
                                        "label": {"type": "string", "enum": ["exact", "plausible", "same_person_other_work", "unrelated"]},
                                    },
                                    "required": ["agent_id", "label"],
                                },
                            },
                            "contacts": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "email": {"type": "string"},
                                        "label": {"type": "string", "enum": ["exact", "plausible", "unrelated"]},
                                    },
                                    "required": ["email", "label"],
                                },
                            },
                        },
                        "required": ["what", "sends", "one_off", "person", "agents", "contacts"],
                    },
                },
            },
            "required": ["kind", "tasks"],
        },
    },
}

CHAT_ENTRIES_FOR_JUDGE = 8


async def judge(text: str, routing: Routing) -> Optional[dict]:
    """One model call. Returns the report, or None if the output was unusable twice."""
    settings = get_settings()
    recent = list(get_conversation_log().iter_entries())[-CHAT_ENTRIES_FOR_JUDGE:]
    chat = "\n".join(f"<{tag}>{payload}</{tag}>" for tag, _, payload in recent) or "None"
    content = "\n\n".join(part for part in [
        f"<recent_chat>\n{chat}\n</recent_chat>",
        render_candidates(routing),
        render_contacts(routing),
        f"<new_user_message>\n{text.strip()}\n</new_user_message>",
    ] if part)
    known = {c.agent_id for c in routing.lookup.candidates}
    for attempt in range(2):
        try:
            response = await request_chat_completion(
                model=settings.judge_model,
                messages=[{"role": "user", "content": content}],
                system=JUDGE_PROMPT,
                api_key=settings.openrouter_api_key,
                tools=[REPORT_TOOL],
                tool_choice={"type": "function", "function": {"name": "report"}},
                temperature=0.0,
                max_tokens=1500,
            )
            call = response["choices"][0]["message"]["tool_calls"][0]
            report = json.loads(call["function"]["arguments"])
            if report.get("kind") not in ("chat", "work") or not isinstance(report.get("tasks"), list):
                raise ValueError("report is missing kind or tasks")
            for task in report["tasks"]:
                task["agents"] = [a for a in task.get("agents", []) if a.get("agent_id") in known]
                task.setdefault("contacts", [])
            return report
        except Exception as exc:
            logger.warning(f"Judge output unusable (attempt {attempt + 1}): {exc}")
    return None


def count_labels(report: dict, routing: Routing, ask: str) -> List[dict]:
    """The decision, from the judge's labels.

    One exact match and nothing in the way: route. More than one exact, or anything
    plausible in the way: ask. A contact with no agent who is clearly meant, or nothing
    that fits: create. `ask` sets what counts as in the way when there is one exact match
    and something else is plausible: strict always, balanced when the task would send,
    loose never.
    """
    if report["kind"] == "chat" or not report["tasks"]:
        return [{"do": "none", "about": "the message"}]
    without_agent = {p.email: p for p in routing.lookup.people if not p.agents}
    steps: List[dict] = []
    for task in report["tasks"]:
        about = task.get("what") or "the task"
        exact = [a["agent_id"] for a in task["agents"] if a["label"] == "exact"]
        plausible = [a["agent_id"] for a in task["agents"] if a["label"] == "plausible"]
        contacts_exact = [without_agent[c["email"]] for c in task["contacts"]
                          if c["label"] == "exact" and c["email"] in without_agent]
        contacts_plausible = [without_agent[c["email"]] for c in task["contacts"]
                              if c["label"] == "plausible" and c["email"] in without_agent]
        doubt = bool(plausible or contacts_plausible)
        in_the_way = doubt and (ask == "strict" or (ask == "balanced" and task.get("sends", True)))

        if len(exact) == 1 and not contacts_exact and not in_the_way:
            steps.append({"do": "route", "about": about, "agents": exact})
        elif len(exact) + len(contacts_exact) >= 2 or (doubt and (in_the_way or not exact)):
            agents = exact + plausible
            options = [_option(routing, a) for a in agents] + \
                      [f"{p.name} (no work with them yet)" for p in contacts_exact + contacts_plausible]
            steps.append({"do": "ask", "about": about, "options": options, "option_agents": agents})
        elif contacts_exact:
            p = contacts_exact[0]
            steps.append({"do": "create", "about": about, "person": f"{p.name} <{p.email}>"})
        else:
            steps.append({"do": "create", "about": about, "person": task.get("person", ""),
                          "throwaway": bool(task.get("one_off"))})
    return steps
