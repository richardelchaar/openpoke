"""Grades what the orchestrator did against the case's expected outcome.

Grading is by rule. A turn is reduced to four facts: which existing agents got work, which
new agents were created, whether it asked a question, and the text of its reply. The rules
are the same for every version.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Dict, Iterable, List, Optional

# Categories where the expected outcome is this project's design choice, not a mistake by
# any reasonable standard. The original app is told to reuse an agent that has useful
# context, so reusing a person's agent for new work, or a search agent for another search,
# is it doing as designed. These are reported as behaviour and left out of the "right" rate.
DESIGN_CHOICE = {"same_person_new_topic", "one_off_lookup"}

ERRORS = ["wrong_person", "wrong_agent", "duplicate", "wrong_reuse", "missed_ask", "unnecessary_ask",
          "bad_question", "extra_agents", "unnecessary_agent", "failed"]


def _asked(turn: dict) -> bool:
    """A question, and nothing handed off."""
    return not turn["existing"] and not turn["created"] and "?" in (turn.get("reply") or "")


def _is_for(created: dict, person: dict) -> bool:
    """Was this new agent made for this person? Versions with records say so; the original
    only has the name and instructions it wrote."""
    if created.get("person_email") and person.get("email"):
        return created["person_email"].lower() == person["email"].lower()
    text = f"{created.get('name', '')} {created.get('instructions', '')} {created.get('person_name', '')}".lower()
    return person["first"].lower() in text and person["last"].lower() in text


def grade_turn(expected: dict, turn: dict, case: dict, world: dict) -> dict:
    works, people = world["works"], world["people"]
    got, created, asked = set(turn["existing"]), turn["created"], _asked(turn)
    reply = (turn.get("reply") or "").lower()
    outcome = expected["outcome"]

    def owner(aid: str) -> Optional[str]:
        return works[aid]["person"]

    error: Optional[str] = None
    if turn.get("error") or turn.get("crash"):
        error = "failed"

    elif outcome == "route":
        want = set(expected["agents"])
        if case.get("category") == "correction":
            # "No, the other Colin": telling the agent that was wrongly used to stop is
            # part of a good correction, so contacting it again is not held against it.
            got -= {e["agent"] for e in case["recent_chat"] if e["tag"] == "handoff"} - want
        if got == want and not created:
            pass
        elif not got and not created:
            error = "unnecessary_ask" if asked else "failed"
        elif created and not got:
            error = "duplicate"
        elif {owner(a) for a in got if owner(a)} - {owner(a) for a in want}:
            error = "wrong_person"
        elif want <= got:
            error = "extra_agents"
        else:
            error = "wrong_agent"

    elif outcome == "create":
        person = expected["person"]
        if got:
            same = all(owner(a) and people[owner(a)]["first"] == person["first"]
                       and people[owner(a)]["last"] == person["last"] for a in got)
            error = "wrong_reuse" if same else "wrong_person"
        elif created:
            if not any(_is_for(c, person) for c in created):
                error = "failed"
        else:
            error = "unnecessary_ask" if asked else "failed"

    elif outcome == "ask":
        if got or created:
            error = "missed_ask"
        elif not asked:
            error = "failed"
        elif not turn.get("heavy"):
            # With heavy use a person has up to eight pieces of work, and a good question
            # may not list them all. There, asking and sending nothing is enough.
            terms = case["option_terms"]
            if not all(any(t in reply for t in terms[o]) for o in expected["options_must_include"]):
                error = "bad_question"

    elif outcome == "none":
        if got or created:
            error = "unnecessary_agent"

    elif outcome == "throwaway":   # a one-off lookup: something new that won't stay, never an existing agent
        if got:
            error = "wrong_reuse"
        elif not created:
            error = "unnecessary_ask" if asked else "failed"

    elif outcome == "ask_or_act":  # after a vague answer: ask once more, or act on one of the options
        if created or not (asked or (got and got <= set(expected["agents"]))):
            error = "failed"

    result = {"right": error is None, "error": error, "asked": asked}
    if error == "missed_ask":
        # How it guessed: everything it could have meant, one of them, or something else.
        options = {o for o in expected["options_must_include"] if o in works}
        result["guess"] = "all_options" if got == options else "one_option" if got and got <= options else "other"
    return result


def grade(trace: dict, case: dict, world: dict) -> dict:
    """One row per run of a case. A second turn, if there was one, is graded as `after`."""
    row = {
        "case_id": case["id"], "category": case["category"], "group": case["group"], "risk": case["risk"],
        "expected": case["expected"]["outcome"], "version": trace["version"], "size": trace["size"],
        "repeat": trace["repeat"], "answer_kind": trace.get("answer_kind"), "heavy": bool(trace.get("heavy")),
    }
    if not trace["turns"]:
        row.update({"right": False, "error": "failed", "asked": False, "crash": trace.get("crash")})
        return row
    for turn in trace["turns"]:
        turn["heavy"] = bool(trace.get("heavy"))
    row.update(grade_turn(case["expected"], trace["turns"][0], case, world))
    if len(trace["turns"]) > 1:
        answer = next(a for a in case["answers"] if a["kind"] == trace["answer_kind"])
        after = grade_turn(answer["expected"], trace["turns"][1], case, world)
        if not after["right"] and _new_agent_for_the_chosen_person(answer, trace["turns"][1], case, world):
            after = {"right": True, "error": None, "asked": False}
        row["after"] = after
    calls = [c for turn in trace["turns"][:1] for c in turn["calls"]]
    row.update({
        "model_calls": len(calls),
        "prompt_tokens": sum(c["prompt_tokens"] for c in calls),
        "completion_tokens": sum(c["completion_tokens"] for c in calls),
        "cost": sum(c["cost"] or 0 for c in calls),
        "seconds": sum(c["seconds"] for c in calls),
    })
    return row


WHICH_PERSON = {"same_first_name_vague", "agent_or_contact"}


def _new_agent_for_the_chosen_person(answer: dict, turn: dict, case: dict, world: dict) -> bool:
    """Where the question was which person was meant, and the user has now said, the
    request may go to that person's existing agent or to a new agent for them. Which of
    the two is the design choice this project leaves unscored, so both count."""
    if case.get("base_category", case["category"]) not in WHICH_PERSON or answer["expected"]["outcome"] != "route":
        return False
    if turn["existing"] or not turn["created"]:
        return False
    owner = world["people"][world["works"][answer["expected"]["agents"][0]]["person"]]
    return all(_is_for(c, owner) for c in turn["created"])


# -- summaries ---------------------------------------------------------------------

def rate(rows: Iterable[dict], key=lambda r: r["right"]) -> Optional[float]:
    rows = list(rows)
    return sum(1 for r in rows if key(r)) / len(rows) if rows else None


def summarize(rows: List[dict]) -> Dict[str, dict]:
    """Per roster size: overall and per group, each error type, questions, cost."""
    # With ten more people sharing the first name, "no, the other Gustavo" no longer points
    # at one person, so a correction has no single right answer under heavy use.
    rows = [r for r in rows if not (r.get("heavy") and r["category"] == "correction")]
    everything = [r for r in rows if not r.get("answer_kind")]
    first = [r for r in everything if r["category"] not in DESIGN_CHOICE]
    design = [r for r in everything if r["category"] in DESIGN_CHOICE]
    after = [r for r in rows if r.get("answer_kind") and "after" in r]
    out: Dict[str, dict] = {}
    for size in sorted({r["size"] for r in first}):
        at = [r for r in first if r["size"] == size]
        by_group = defaultdict(list)
        by_category = defaultdict(list)
        for r in at:
            by_group[r["group"]].append(r)
            by_category[r["category"]].append(r)
        should_ask = [r for r in at if r["expected"] == "ask"]
        should_not = [r for r in at if r["expected"] != "ask"]
        answered = [r for r in after if r["size"] == size]
        out[str(size)] = {
            "n": len(at),
            "right": rate(at),
            "groups": {g: rate(rs) for g, rs in by_group.items()},
            "categories": {c: rate(rs) for c, rs in by_category.items()},
            "errors": dict(Counter(r["error"] for r in at if r["error"])),
            "asked_when_needed": rate(should_ask, lambda r: r["asked"]),
            "asked_when_not_needed": rate(should_not, lambda r: r["asked"]),
            "right_after_answer": rate(answered, lambda r: r["after"]["right"]),
            "wrong_person": rate(at, lambda r: r["error"] == "wrong_person"),
            "design_choice": {c: {"n": len(rs), "separate_agent": rate(rs),
                                  "reused_existing": rate(rs, lambda r: r["error"] == "wrong_reuse")}
                              for c in sorted(DESIGN_CHOICE)
                              for rs in [[r for r in design if r["size"] == size and r["category"] == c]] if rs},
            "tokens_per_case": sum(r["prompt_tokens"] + r["completion_tokens"] for r in at) / len(at),
            "cost_per_case": sum(r["cost"] for r in at) / len(at),
            "calls_per_case": sum(r["model_calls"] for r in at) / len(at),
        }
    return out


def print_summary(summary: Dict[str, dict]) -> None:
    def pct(x: Optional[float]) -> str:
        return "   -" if x is None else f"{100 * x:4.0f}%"

    sizes = list(summary)
    print(f"\n{'':28}" + "".join(f"{s:>8}" for s in sizes))
    print(f"{'cases':28}" + "".join(f"{summary[s]['n']:>8}" for s in sizes))
    print(f"{'right':28}" + "".join(f"{pct(summary[s]['right']):>8}" for s in sizes))
    for group in ["route", "create", "ask", "no_lasting_agent", "robustness"]:
        print(f"{'  ' + group:28}" + "".join(f"{pct(summary[s]['groups'].get(group)):>8}" for s in sizes))
    for label, key in [("asked when needed", "asked_when_needed"), ("asked when not needed", "asked_when_not_needed"),
                       ("right after the answer", "right_after_answer"), ("wrong person", "wrong_person")]:
        print(f"{label:28}" + "".join(f"{pct(summary[s][key]):>8}" for s in sizes))
    for cat in sorted(DESIGN_CHOICE):
        if any(cat in summary[s]["design_choice"] for s in sizes):
            print(f"{'reuses for ' + cat[:17]:28}" + "".join(
                f"{pct(summary[s]['design_choice'].get(cat, {}).get('reused_existing')):>8}" for s in sizes))
    for error in ERRORS:
        counts = [summary[s]["errors"].get(error, 0) for s in sizes]
        if any(counts):
            print(f"{'  ' + error:28}" + "".join(f"{c:>8}" for c in counts))
    print(f"{'tokens per case':28}" + "".join(f"{summary[s]['tokens_per_case']:>8.0f}" for s in sizes))
    print(f"{'cost per case ($)':28}" + "".join(f"{summary[s]['cost_per_case']:>8.4f}" for s in sizes))
