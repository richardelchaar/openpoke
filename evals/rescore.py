"""Re-grades a saved run with the current rules and prints the summary. Calls no model.

    python -m evals.rescore evals/results/<run>.jsonl.gz
"""

from __future__ import annotations

import gzip
import json
import sys

from .cases.build import load_cases
from .grade import grade, print_summary, summarize
from .worlds.generate import load


def rescore(path: str) -> dict:
    with gzip.open(path, "rt") as handle:
        head = json.loads(handle.readline())
        traces = [json.loads(line)["trace"] for line in handle]
    world_name = head["args"]["world"]
    world, cases = load(world_name), {c["id"]: c for c in load_cases(world_name)}
    rows = [grade(t, cases[t["case_id"]], world) for t in traces if t["case_id"] in cases]
    return summarize(rows)


if __name__ == "__main__":
    for path in sys.argv[1:]:
        print(path)
        print_summary(rescore(path))
