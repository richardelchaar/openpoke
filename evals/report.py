"""Builds the results tables from the saved runs, re-graded with the current rules.

    python -m evals.report            prints the tables as Markdown
    python -m evals.report --json     prints the numbers behind them

Calls no model. Every figure in the write-up comes from here.
"""

from __future__ import annotations

import glob
import gzip
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

from .cases.build import load_cases
from .grade import grade, summarize
from .worlds.generate import load
from .worlds.heavy import load_heavy

RESULTS = Path(__file__).resolve().parent / "results"
VERSIONS = {
    "v0": "Original", "v1": "Prompt only", "v2": "Records and lookup",
    "v3": "Told to ask", "v4": "Code rule", "v5": "Judge",
}


def latest(world: str, version: str, tag: str) -> Optional[str]:
    runs = sorted(glob.glob(str(RESULTS / f"*-{world}-{version}-{tag}.jsonl.gz")))
    return runs[-1] if runs else None


def regrade(path: str) -> Dict[str, dict]:
    with gzip.open(path, "rt") as handle:
        head = json.loads(handle.readline())
        traces = [json.loads(line)["trace"] for line in handle]
    args = head["args"]
    world = load(args["world"])
    if args.get("heavy"):
        world = load_heavy(world)
    case_set = f"{args['world']}.{args['set']}" if args.get("set") else args["world"]
    cases = {c["id"]: c for c in load_cases(case_set)}
    return summarize([grade(t, cases[t["case_id"]], world) for t in traces])


def collect(world: str = "dev") -> Dict[str, dict]:
    """version -> column -> summary. Columns: 20, 160, 640, heavy, stress."""
    out: Dict[str, dict] = {}
    for version in VERSIONS:
        columns: Dict[str, dict] = {}
        main = latest(world, version, "baseline" if version == "v0" and world == "dev" else "main")
        if main:
            columns.update(regrade(main))
        for tag in ("heavy", "stress"):
            run = latest(world, version, tag)
            if run:
                columns[tag] = regrade(run)["160"]
        if columns:
            out[version] = columns
    return out


def pct(x: Optional[float], digits: int = 0) -> str:
    return "-" if x is None else f"{100 * x:.{digits}f}%"


def table(data: Dict[str, dict], title: str, key, columns: List[str], heads: List[str]) -> str:
    lines = [f"**{title}**", "", "| | " + " | ".join(heads) + " |", "|---|" + "---|" * len(heads)]
    for version, name in VERSIONS.items():
        if version in data:
            cells = [key(data[version][c]) if c in data[version] else "-" for c in columns]
            lines.append(f"| {name} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def markdown(world: str = "dev") -> str:
    data = collect(world)
    sizes = ["20", "160", "640", "heavy"]
    heads = ["20 agents", "160 agents", "640 agents", "160 agents, heavy use"]
    dup = lambda s: pct(s["errors"].get("duplicate", 0) / s["n"], 1)  # noqa: E731
    parts = [
        table(data, "Right outcome", lambda s: pct(s["right"]), sizes, heads),
        table(data, "Asks when it should", lambda s: pct(s["asked_when_needed"]), sizes, heads),
        table(data, "Asks when it shouldn't", lambda s: pct(s["asked_when_not_needed"]), sizes, heads),
        table(data, "Right after the user answers", lambda s: pct(s["right_after_answer"]), sizes, heads),
        table(data, "Reaches the wrong person", lambda s: pct(s["wrong_person"], 1), sizes, heads),
        table(data, "Creates a duplicate", dup, sizes, heads),
        table(data, "Tokens per message", lambda s: f"{s['tokens_per_case']:,.0f}", sizes, heads),
        table(data, "Cost per message", lambda s: f"${s['cost_per_case']:.4f}", sizes, heads),
        table(data, "Stress set, 40 messier messages, right", lambda s: pct(s["right"]), ["stress"], ["160 agents"]),
    ]
    return "\n\n".join(parts)


if __name__ == "__main__":
    world = next((a for a in sys.argv[1:] if not a.startswith("--")), "dev")
    if "--json" in sys.argv:
        print(json.dumps(collect(world), indent=1))
    else:
        print(markdown(world))
