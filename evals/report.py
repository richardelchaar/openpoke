"""Builds the results tables from the saved runs, re-graded with the current rules.

    python -m evals.report            prints the tables as Markdown
    python -m evals.report --json     prints the numbers behind them
    python -m evals.report --categories [world]   the original against the chosen version, by category
    python -m evals.report --csv      writes results/regraded.csv: every run under the current rules

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
    "v2d": "Lookup over a description only",
    "v2b": "Records and lookup, second iteration",
    "v3": "Required to ask", "v4": "Code rule", "v5": "Second model call",
}
CATEGORY_NAMES = {
    "clear_followup": "Clear follow-up", "pronoun_followup": "Pronoun follow-up", "after_gap": "Follow-up after a gap",
    "two_works_topic_named": "Same person, two pieces of work, topic named",
    "same_first_name_topic_settles": "Same first name, topic settles it", "different_wording": "Different wording",
    "shared_contact": "Shared contact", "email_alert_followup": "Follow-up on an email alert", "correction": "Correction",
    "known_first_name_new_person": "Known first name, different person", "brand_new_person": "Brand-new person",
    "same_person_vague": "Same person, vague", "same_first_name_vague": "Same first name, nothing settles it",
    "agent_or_contact": "A person with an agent, or a contact", "chat": "Chat", "two_tasks": "Two tasks in one message",
    "topic_switch": "Topic switch", "inbox_scanner": "Inbox-scanner trap", "messy_text": "Messy text",
    "after_a_question": "After a question",
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


def by_category(world: str, version: str = "v2") -> str:
    """The original against one version, category by category, pooled over the three sizes."""
    data = collect(world)
    sizes = ["20", "160", "640"]
    lines = [f"**By category, {world} world, pooled over 20 / 160 / 640 agents**", "",
             f"| Category | Original | {VERSIONS[version]} | Change |", "|---|---|---|---|"]
    rows = []
    for key, name in CATEGORY_NAMES.items():
        a = sum(data["v0"][s]["categories"][key] for s in sizes) / 3
        b = sum(data[version][s]["categories"][key] for s in sizes) / 3
        rows.append((b - a, f"| {name} | {pct(a)} | {pct(b)} | {100 * (b - a):+.0f} |"))
    lines += [row for _, row in sorted(rows, reverse=True)]
    for label, v in (("Original", "v0"), (VERSIONS[version], version)):
        without = " / ".join(pct(data[v][s]["right_without_contacts"]) for s in sizes)
        lines.append(f"\n{label}, right outcome without the contact category: {without}")
    return "\n".join(lines)


def regraded_csv(path: Path) -> None:
    """One row per version, world and roster, under the current grading rules."""
    import csv

    keys = ["right", "asked_when_needed", "asked_when_not_needed", "right_after_answer", "wrong_person",
            "tokens_per_case", "cost_per_case", "seconds_per_case"]
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["world", "version", "roster", "cases"] + keys + ["duplicates", "wrong_person_after_answer", "answered"])
        for world in ("dev", "heldout"):
            for version, columns in collect(world).items():
                for roster, s in columns.items():
                    writer.writerow([world, version, roster, s["n"]]
                                    + ["" if s[k] is None else round(s[k], 4) for k in keys]
                                    + [s["errors"].get("duplicate", 0), s["wrong_person_after_answer"], s["answered"]])


if __name__ == "__main__":
    world = next((a for a in sys.argv[1:] if not a.startswith("--")), "dev")
    if "--csv" in sys.argv:
        regraded_csv(RESULTS / "regraded.csv")
        print(f"wrote {RESULTS / 'regraded.csv'}")
    elif "--categories" in sys.argv:
        print(by_category(world))
    elif "--json" in sys.argv:
        print(json.dumps(collect(world), indent=1))
    else:
        print(markdown(world))
