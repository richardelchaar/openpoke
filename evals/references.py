"""Scores four simple strategies with the same grader, so the real numbers have a floor
and a ceiling. Calls no model.

    python -m evals.references dev

  always right     does what each case expects: proves the grader can give 100%
  most recent      hands every message to the newest agent in the roster
  always create    makes a new agent for every message
  always ask       asks a question every time, naming every option perfectly
"""

from __future__ import annotations

import sys
from typing import Callable, Dict, List

from .cases.build import load_cases
from .grade import DESIGN_CHOICE, grade_turn, rate
from .run_case import roster_for
from .worlds.generate import load

SIZE = 160


def always_right(case: dict, world: dict, roster: List[str]) -> dict:
    exp = case["expected"]
    if exp["outcome"] == "route":
        return {"existing": exp["agents"], "created": [], "reply": "On it."}
    if exp["outcome"] == "create":
        p = exp["person"]
        return {"existing": [], "created": [{"name": f"{p['first']} {p['last']}", "instructions": ""}], "reply": "On it."}
    if exp["outcome"] == "ask":
        terms = " or ".join(case["option_terms"][o][0] for o in exp["options_must_include"])
        return {"existing": [], "created": [], "reply": f"Which one: {terms}?"}
    if exp["outcome"] == "throwaway":
        return {"existing": [], "created": [{"name": "lookup", "instructions": "", "throwaway": True}], "reply": "On it."}
    return {"existing": [], "created": [], "reply": "Sure."}


def most_recent(case: dict, world: dict, roster: List[str]) -> dict:
    return {"existing": [roster[-1]], "created": [], "reply": "On it."}


def always_create(case: dict, world: dict, roster: List[str]) -> dict:
    return {"existing": [], "created": [{"name": "New task", "instructions": case["message"]}], "reply": "On it."}


def always_ask(case: dict, world: dict, roster: List[str]) -> dict:
    terms = " or ".join(t for options in case.get("option_terms", {}).values() for t in options[:1])
    return {"existing": [], "created": [], "reply": f"Which do you mean: {terms or 'this'}?"}


STRATEGIES: Dict[str, Callable] = {
    "always right": always_right, "most recent": most_recent,
    "always create": always_create, "always ask": always_ask,
}


def main() -> None:
    world_name = sys.argv[1] if len(sys.argv) > 1 else "dev"
    world = load(world_name)
    cases = [c for c in load_cases(world_name) if c["category"] not in DESIGN_CHOICE]
    print(f"{world_name}, {len(cases)} cases, {SIZE} agents\n")
    print(f"{'':16}{'right':>8}{'route':>8}{'create':>8}{'ask':>8}{'chat':>8}{'robust':>8}")
    for name, strategy in STRATEGIES.items():
        rows = []
        for case in cases:
            turn = strategy(case, world, roster_for(world, case, SIZE))
            rows.append({"group": case["group"], **grade_turn(case["expected"], turn, case, world)})
        by_group = lambda g: rate([r for r in rows if r["group"] == g])  # noqa: E731
        cells = [rate(rows)] + [by_group(g) for g in ("route", "create", "ask", "no_lasting_agent", "robustness")]
        print(f"{name:16}" + "".join(f"{100 * c:7.0f}%" for c in cells))


if __name__ == "__main__":
    main()
