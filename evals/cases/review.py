"""Picks 20 cases at random for a person to read: 10 that should ask, 10 from the rest.

    python -m evals.cases.review dev > review.md

The seed is fixed, so the same 20 come out each time.
"""

from __future__ import annotations

import random
import sys

from ..worlds.generate import load
from .build import load_cases


def describe(case: dict, works: dict, people: dict) -> str:
    exp = case["expected"]
    lines = [f"### {case['id']}", ""]
    for entry in case["recent_chat"]:
        if entry["tag"] != "handoff":
            lines.append(f"- _{entry['tag']}_: {entry['text']}")
    lines += [f"- **message: {case['message']}**", ""]
    lines.append("Agents that exist for this person or name:")
    for aid in case["required"]:
        w = works[aid]
        who = people[w["person"]] if w["person"] else None
        lines.append(f"- `{w['name']}`: {w['summary']}" + (f" ({who['first']} {who['last']})" if who else ""))
    if not case["required"]:
        lines.append("- none")
    lines.append("")
    if exp["outcome"] == "route":
        lines.append("**Expected:** hand off to " + ", ".join(f"`{works[a]['name']}`" for a in exp["agents"]))
    elif exp["outcome"] == "create":
        lines.append(f"**Expected:** create a new agent for {exp['person']['first']} {exp['person']['last']}")
    elif exp["outcome"] == "ask":
        options = [f"`{works[o]['name']}`" if o in works else
                   f"{people[o.split(':')[1]]['first']} {people[o.split(':')[1]]['last']} (a contact with no agent)"
                   for o in exp["options_must_include"]]
        lines.append("**Expected:** ask which, offering " + " and ".join(options))
    elif exp["outcome"] == "none":
        lines.append("**Expected:** answer directly, no agent")
    else:
        lines.append("**Expected:** a one-off lookup, not an existing agent")
    lines += ["", "Verdict: ", ""]
    return "\n".join(lines)


def main() -> None:
    world_name = sys.argv[1] if len(sys.argv) > 1 else "dev"
    world, cases = load(world_name), load_cases(world_name)
    rng = random.Random(20)
    asks = rng.sample([c for c in cases if c["expected"]["outcome"] == "ask"], 10)
    rest = rng.sample([c for c in cases if c["expected"]["outcome"] != "ask"], 10)
    print(f"# 20 cases to review ({world_name} world)\n")
    print("For each: is the expected outcome what a sensible assistant should do? Write ok, or what's wrong.\n")
    for case in asks + rest:
        print(describe(case, world["works"], world["people"]))


if __name__ == "__main__":
    main()
