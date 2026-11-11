"""Analyses that need no model call: they re-run the app's own lookup and decision code
over the cases.

    python -m evals.offline lookup      how often the right agent is among the candidates
    python -m evals.offline tradeoff    what each ask setting costs in needless questions

`tradeoff` reads the judge's saved labels from the latest v5 run, so that run has to exist.
"""

from __future__ import annotations

import glob
import gzip
import json
import sys
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional

from .cases.build import load_cases
from .grade import DESIGN_CHOICE
from .run_case import roster_for
from .worlds.generate import load

SIZES = [20, 160, 640]
RESULTS = Path(__file__).resolve().parent / "results"


def store_for(world: dict, case: dict, size: int, crowd: int = 0):
    """The work records for one case's roster, built by the app's own record-keeping code."""
    from server.services.agents.store import AgentStore
    from . import materialize
    import server.services.agents.store as store_module

    store = AgentStore(Path(tempfile.mkdtemp(prefix="openpoke-offline-")) / "agents.db")
    store_module._store = store   # materialize writes to the app's shared store
    materialize.write_records(world["works"], world["people"], roster_for(world, case, size, crowd))
    return store


def recent_for(case: dict) -> List[str]:
    ids: List[str] = []
    for entry in reversed(case["recent_chat"]):
        if entry["tag"] == "handoff" and entry["agent"] not in ids:
            ids.append(entry["agent"])
    return ids[:3]


def last_shown_for(case: dict) -> str:
    for entry in reversed(case["recent_chat"]):
        if entry["tag"] in ("poke_reply", "agent_message"):
            return entry["text"]
    return ""


def wanted(case: dict) -> Optional[List[str]]:
    """The agents the lookup has to surface for the case to be answerable. None if the
    case doesn't depend on finding an existing agent."""
    exp = case["expected"]
    if exp["outcome"] == "route":
        return exp["agents"]
    if exp["outcome"] == "ask":
        return [o for o in exp["options_must_include"] if not o.startswith("contact:")]
    return None


def pct(hits: int, total: int) -> str:
    return f"{100 * hits / total:5.1f}%" if total else "    -"


# -- lookup quality ------------------------------------------------------------------

def lookup_quality(world_name: str = "dev") -> None:
    from server.routing.lookup import lookup

    world, cases = load(world_name), load_cases(world_name)
    limits = [3, 5, 10, 20]
    found = {limit: defaultdict(lambda: [0, 0]) for limit in limits}        # (size) -> [hits, total]
    by_category = defaultdict(lambda: defaultdict(lambda: [0, 0]))            # at the default limit
    contacts = defaultdict(lambda: [0, 0])
    for size in SIZES:
        for case in cases:
            need = wanted(case)
            if need is None:
                continue
            store = store_for(world, case, size)
            recent = recent_for(case)
            for limit in limits:
                result = lookup(case["message"], store, recent, limit=limit, last_shown=last_shown_for(case))
                got = {c.agent_id for c in result.candidates}
                hit = all(a in got for a in need)
                found[limit][size][0] += hit
                found[limit][size][1] += 1
                if limit == 10:
                    by_category[case["category"]][size][0] += hit
                    by_category[case["category"]][size][1] += 1
                    for option in case["expected"].get("options_must_include", []):
                        if option.startswith("contact:"):
                            email = world["people"][option.split(":")[1]]["email"]
                            contacts[size][0] += any(p.email == email for p in result.people)
                            contacts[size][1] += 1
    print(f"{world_name}: how often every agent the case needs is among the candidates\n")
    print(f"{'candidates allowed':24}" + "".join(f"{s:>9}" for s in SIZES))
    for limit in limits:
        print(f"{limit:<24}" + "".join(f"{pct(*found[limit][s]):>9}" for s in SIZES))
    print(f"\nby category, with 10 candidates allowed\n{'':34}" + "".join(f"{s:>9}" for s in SIZES))
    for category, sizes in by_category.items():
        print(f"{category:34}" + "".join(f"{pct(*sizes[s]):>9}" for s in SIZES))
    print(f"{'contact with no agent is found':34}" + "".join(f"{pct(*contacts[s]):>9}" for s in SIZES))


# -- the trade-off -------------------------------------------------------------------

def asked(steps: List[dict]) -> bool:
    return any(step["do"] == "ask" for step in steps)


def score(points: Dict[str, List[bool]], cases_by_id: Dict[str, dict], label: str) -> None:
    should = [a for cid, asks in points.items() if cases_by_id[cid]["expected"]["outcome"] == "ask" for a in asks]
    should_not = [a for cid, asks in points.items() if cases_by_id[cid]["expected"]["outcome"] != "ask" for a in asks]
    print(f"{label:22} asks when it should {pct(sum(should), len(should))}   "
          f"asks when it shouldn't {pct(sum(should_not), len(should_not))}")


def tradeoff(world_name: str = "dev") -> None:
    from server.routing.decide import code_rule, count_labels
    from server.routing.lookup import LookupResult, MatchedPerson, lookup
    from server.routing.pipeline import Routing

    world = load(world_name)
    cases = [c for c in load_cases(world_name) if c["category"] not in DESIGN_CHOICE]
    by_id = {c["id"]: c for c in cases}
    size = 160

    print("code rule (v4): the decision at each margin, from the lookup's scores\n")
    routings = {}
    for case in cases:
        store = store_for(world, case, size)
        routings[case["id"]] = Routing(lookup(case["message"], store, recent_for(case),
                                              last_shown=last_shown_for(case)), [])
    for margin in [0.0, 0.1, 0.25, 0.5, 0.75, 1.0]:
        points = {cid: [asked(code_rule(routing, margin))] for cid, routing in routings.items()}
        score(points, by_id, f"margin {margin}")

    runs = sorted(glob.glob(str(RESULTS / f"*-{world_name}-v5-main.jsonl.gz")))
    if not runs:
        print("\nno v5 run found, so the judge's settings can't be compared yet")
        return
    print(f"\njudge (v5): the decision at each setting, from the labels saved in {Path(runs[-1]).name}\n")
    with gzip.open(runs[-1], "rt") as handle:
        handle.readline()
        traces = [json.loads(line)["trace"] for line in handle]
    for setting in ["loose", "balanced", "strict"]:
        points: Dict[str, List[bool]] = defaultdict(list)
        for trace in traces:
            if trace.get("answer_kind") or not trace["turns"] or trace["case_id"] not in by_id:
                continue
            saved = trace["turns"][0].get("routing") or {}
            report = (saved.get("decision") or {}).get("report")
            if not report:
                continue
            people = [MatchedPerson(p["name"], p["email"], p["agents"], p["full_name"]) for p in saved["people"]]
            routing = Routing(LookupResult([], people), [])
            points[trace["case_id"]].append(asked(count_labels(report, routing, setting)))
        score(points, by_id, setting)


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "lookup"
    world_name = sys.argv[2] if len(sys.argv) > 2 else "dev"
    {"lookup": lookup_quality, "tradeoff": tradeoff}[what](world_name)
