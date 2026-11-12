"""Checks every case against its world.

    python -m evals.cases.validate dev heldout

A case is only useful if its stated answer is the right one whatever the roster size.
So this checks, against the whole world including all the filler:
  - every agent a case names exists, and the expected ones are in its roster;
  - no word in the message is also a filler person's name;
  - a case that should route points at exactly the people its category says it should;
  - a case that should ask really has two things to choose between;
  - a case that should create really has nothing to reuse;
  - a request that names a topic doesn't share words with the wrong piece of work.
It also reports how varied each category is. Exits non-zero if anything fails.
"""

from __future__ import annotations

import sys
from collections import Counter, defaultdict
from typing import Dict, List

from ..worlds.generate import load
from .build import STOP, load_cases, words

FIRST_ONLY_ONE = {"after_gap", "two_works_topic_named", "different_wording"}


def validate(world: str) -> List[str]:
    w = load(world)
    # The crowd shares first names with the core on purpose and is only added by the
    # crowded run, which filters it per case. It is left out of these checks.
    people = {pid: p for pid, p in w["people"].items() if not p.get("crowd")}
    works = {aid: x for aid, x in w["works"].items() if x["tag"] != "crowd"}
    cases = load_cases(world)
    problems: List[str] = []

    works_of: Dict[str, List[str]] = defaultdict(list)
    for aid, work in works.items():
        if work["person"]:
            works_of[work["person"]].append(aid)
    by_first: Dict[str, List[str]] = defaultdict(list)
    for pid, p in people.items():
        by_first[p["first"].lower()].append(pid)
    filler_names = {n.lower() for p in people.values() if not p["core"] for n in (p["first"], p["last"])}
    all_names = {n.lower() for p in people.values() for n in (p["first"], p["last"])}

    def bad(case: dict, why: str) -> None:
        problems.append(f"{case['id']}: {why}  | {case['message']}")

    seen_ids = set()
    for case in cases:
        if case["id"] in seen_ids:
            bad(case, "duplicate id")
        seen_ids.add(case["id"])
        exp, cat = case["expected"], case.get("base_category", case["category"])
        tokens = words(case["message"])

        for aid in case["required"] + exp.get("agents", []):
            if aid not in works:
                bad(case, f"unknown agent {aid}")
        for aid in exp.get("agents", []) + [o for o in exp.get("options_must_include", []) if o.startswith("a_")]:
            if aid not in case["required"]:
                bad(case, f"expected agent {aid} is not in the case's roster")

        clash = filler_names & set(tokens)
        for entry in case["recent_chat"]:
            if entry["tag"] == "user_message":
                clash |= filler_names & set(words(entry["text"]))
        if clash:
            bad(case, f"words that are also filler names: {sorted(clash)}")

        named = [pid for t in set(tokens) for pid in by_first.get(t, [])]
        with_agents = [pid for pid in named if works_of[pid]]
        fully_named = [pid for pid in named if people[pid]["last"].lower() in tokens]

        if exp["outcome"] == "route" and cat not in {"pronoun_followup", "email_alert_followup", "after_a_question",
                                                     "correction", "shared_contact", "two_tasks"}:
            target = works[exp["agents"][0]]["person"]
            if fully_named and fully_named != [target]:
                bad(case, "full name in the message is not the expected person")
            if not fully_named:
                if cat in FIRST_ONLY_ONE and with_agents != [target]:
                    bad(case, f"first name should point at one person with agents, found {len(with_agents)}")
                if cat == "same_first_name_topic_settles" and len(with_agents) != 2:
                    bad(case, f"expected two people with this first name, found {len(with_agents)}")

        if cat in {"two_works_topic_named", "same_first_name_topic_settles", "clear_followup"}:
            right = works[exp["agents"][0]]
            content = {t for t in tokens if t not in STOP and t not in all_names and len(t) > 3}
            for other in case["required"]:
                if other in exp["agents"]:
                    continue
                o = works[other]
                theirs = set(words(f"{o['label']} {o['detail']} {o['subject']}"))
                ours = set(words(f"{right['label']} {right['detail']} {right['subject']} {right['summary']}"))
                leak = (content & theirs) - ours
                if leak:
                    bad(case, f"shares {sorted(leak)} with the wrong work ({o['label']})")

        if cat == "same_person_vague":
            opts = exp["options_must_include"]
            if sorted(works_of[works[opts[0]]["person"]]) != sorted(opts):
                bad(case, "the person's work is not exactly the two options")
        if cat == "same_first_name_vague" and len(with_agents) != 2:
            bad(case, f"expected two people with agents, found {len(with_agents)}")
        if cat == "agent_or_contact":
            if len(with_agents) != 1 or len(named) != 2:
                bad(case, f"expected one person with an agent and one contact, found {len(with_agents)} of {len(named)}")

        if exp["outcome"] == "create":
            person = exp["person"]
            match = [pid for pid in by_first.get(person["first"].lower(), []) if people[pid]["last"] == person["last"]]
            if cat == "brand_new_person" and (person["first"].lower() in by_first or person["last"].lower() in all_names):
                bad(case, "the new person's name already exists in the world")
            if cat == "known_first_name_new_person" and (not match or works_of[match[0]]):
                bad(case, "the contact should exist and have no agent")
            if cat == "same_person_new_topic":
                families = {works[a]["family"] for a in works_of[match[0]]}
                from ..worlds.catalogue import BY_KEY
                if BY_KEY[case["new_kind"]].family in families:
                    bad(case, "the new topic is one the person already has")

        if exp["outcome"] == "ask":
            for option, terms in case["option_terms"].items():
                if not terms:
                    bad(case, f"no words to recognise option {option} in a question")
            if not {a["kind"] for a in case["answers"]} >= {"picks", "vague"}:
                bad(case, "missing a scripted answer")

    # How varied is each category?
    print(f"\n{world}: {len(cases)} cases")
    print(f"  {'category':34} {'n':>4} {'messages':>9} {'kinds':>6} {'people':>7}")
    stats = defaultdict(lambda: {"n": 0, "messages": set(), "kinds": set(), "people": set()})
    for case in cases:
        s = stats[case["category"]]
        s["n"] += 1
        s["messages"].add(case["message"])
        for aid in case["expected"].get("agents", []) + case["expected"].get("options_must_include", []):
            if aid in works:
                s["kinds"].add(works[aid]["kind"])
                s["people"].add(works[aid]["person"])
    for cat, s in stats.items():
        print(f"  {cat:34} {s['n']:>4} {len(s['messages']):>9} {len(s['kinds']):>6} {len(s['people']):>7}")
    risks = Counter(c["risk"] for c in cases)
    print(f"  risk: {dict(risks)}")
    return problems


def main() -> None:
    failed = False
    for world in sys.argv[1:] or ["dev", "heldout"]:
        problems = validate(world)
        for line in problems:
            print("  PROBLEM", line)
        print(f"  {len(problems)} problems")
        failed = failed or bool(problems)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
