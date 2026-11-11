"""Runs one version over a set of cases at one or more roster sizes.

    python -m evals.run --world dev --version v0 --sizes 25,200,800 --repeats 3
    python -m evals.run --world dev --version v0 --sizes 10,20,40 --sample 60 --tag sweep

Each case runs in its own process (see run_case.py). Where a case expected a question and
got one, the scripted answers are sent as a second turn. Results go to evals/results/ as one
file per run, with a row added to runs.csv.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import gzip
import json
import random
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from .cases.build import load_cases
from .grade import grade, print_summary, summarize
from .run_case import VERSIONS
from .worlds.generate import load

EVAL_DIR = Path(__file__).resolve().parent
RESULTS_DIR = EVAL_DIR / "results"
MARK = "@@TRACE@@"


async def run_job(job: dict, limit: asyncio.Semaphore) -> dict:
    async with limit:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "evals.run_case",
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
            cwd=str(EVAL_DIR.parent),
        )
        try:
            out, _ = await asyncio.wait_for(proc.communicate(json.dumps(job).encode()), timeout=300)
        except asyncio.TimeoutError:
            proc.kill()
            out = b""
        text = out.decode(errors="replace")
        if MARK in text:
            return json.loads(text.split(MARK, 1)[1])
        return {**job, "turns": [], "crash": "the case process produced no result"}


async def run_all(jobs: List[dict], concurrency: int, label: str) -> List[dict]:
    """Runs every job. Repeats of one case at one size run one after another, so the
    later ones read the prompt from the provider's cache instead of paying for it again."""
    limit = asyncio.Semaphore(concurrency)
    chains: Dict[tuple, List[dict]] = {}
    for job in jobs:
        chains.setdefault((job["case_id"], job["size"], job.get("answer_kind")), []).append(job)
    done: List[dict] = []
    started = time.monotonic()

    async def run_chain(chain: List[dict]) -> None:
        for job in chain:
            done.append(await run_job(job, limit))
            if len(done) % 100 == 0 or len(done) == len(jobs):
                print(f"  {label}: {len(done)}/{len(jobs)}  ({time.monotonic() - started:.0f}s)", flush=True)

    await asyncio.gather(*(run_chain(chain) for chain in chains.values()))
    return done


def pick_cases(cases: List[dict], args: argparse.Namespace) -> List[dict]:
    if args.categories:
        wanted = set(args.categories.split(","))
        cases = [c for c in cases if c["category"] in wanted]
    if args.sample:
        # The same share of every category, chosen by a fixed seed.
        rng = random.Random(7)
        by_cat: Dict[str, List[dict]] = {}
        for c in cases:
            by_cat.setdefault(c["category"], []).append(c)
        share = args.sample / len(cases)
        cases = [c for group in by_cat.values() for c in rng.sample(group, max(1, round(len(group) * share)))]
    return cases


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--world", default="dev")
    parser.add_argument("--version", required=True, choices=sorted(VERSIONS))
    parser.add_argument("--sizes", required=True, help="roster sizes, comma separated")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--sample", type=int, help="run about this many cases, spread over the categories")
    parser.add_argument("--categories", help="only these categories, comma separated")
    parser.add_argument("--concurrency", type=int, default=16)
    parser.add_argument("--crowd", type=int, default=0,
                        help="add this many extra people for each first name in a case")
    parser.add_argument("--tag", default="")
    parser.add_argument("--replay-only", action="store_true", help="use saved model responses, call nothing")
    args = parser.parse_args()

    world = load(args.world)
    cases = pick_cases(load_cases(args.world), args)
    by_id = {c["id"]: c for c in cases}
    sizes = [int(s) for s in args.sizes.split(",")]
    base = {"world": args.world, "version": args.version, "replay_only": args.replay_only, "crowd": args.crowd}

    jobs = [{**base, "case_id": c["id"], "size": size, "repeat": r}
            for c in cases for size in sizes for r in range(args.repeats)]
    print(f"{args.version} on {args.world}: {len(cases)} cases x {len(sizes)} sizes x {args.repeats} repeats = {len(jobs)} runs")
    traces = asyncio.run(run_all(jobs, args.concurrency, "first turn"))
    broke = [t for t in traces if t.get("crash") or any(turn.get("error") for turn in t["turns"])]
    if len(broke) > len(traces) * 0.02:
        sample = broke[0].get("crash") or next(turn["error"] for turn in broke[0]["turns"] if turn.get("error"))
        sys.exit(f"{len(broke)} of {len(traces)} runs failed, so nothing was saved. First failure: {sample[:300]}")
    rows = [grade(t, by_id[t["case_id"]], world) for t in traces]

    # Where a question was needed and asked, send each scripted answer as a second turn.
    follow = [{**base, "case_id": r["case_id"], "size": r["size"], "repeat": r["repeat"], "answer_kind": a["kind"]}
              for r in rows if r["expected"] == "ask" and r["asked"] for a in by_id[r["case_id"]]["answers"]]
    if follow:
        answered = asyncio.run(run_all(follow, args.concurrency, "after the answer"))
        traces += answered
        rows += [grade(t, by_id[t["case_id"]], world) for t in answered]

    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                            cwd=EVAL_DIR.parent).stdout.strip()
    run_id = f"{datetime.now():%Y%m%d-%H%M%S}-{args.world}-{args.version}" + (f"-{args.tag}" if args.tag else "")
    summary = summarize(rows)
    RESULTS_DIR.mkdir(exist_ok=True)
    with gzip.open(RESULTS_DIR / f"{run_id}.jsonl.gz", "wt") as handle:
        handle.write(json.dumps({"run_id": run_id, "commit": commit, "args": vars(args),
                                 "switches": VERSIONS[args.version], "summary": summary}) + "\n")
        for trace, row in zip(traces, rows):
            handle.write(json.dumps({"grade": row, "trace": trace}) + "\n")

    runs_csv = RESULTS_DIR / "runs.csv"
    is_new = not runs_csv.exists()
    with runs_csv.open("a", newline="") as handle:
        writer = csv.writer(handle)
        if is_new:
            writer.writerow(["run_id", "commit", "world", "version", "size", "cases", "repeats", "right",
                             "wrong_person", "asked_when_needed", "asked_when_not_needed", "right_after_answer",
                             "tokens_per_case", "cost_per_case"])
        for size, s in summary.items():
            writer.writerow([run_id, commit, args.world, args.version, size, len(cases), args.repeats] + [
                "" if s[k] is None else round(s[k], 4) for k in
                ["right", "wrong_person", "asked_when_needed", "asked_when_not_needed", "right_after_answer",
                 "tokens_per_case", "cost_per_case"]])

    print_summary(summary)
    total = sum(c["cost"] or 0 for t in traces for turn in t["turns"] for c in turn["calls"] if not c["cached"])
    print(f"\nspent on this run: ${total:.2f}   results: evals/results/{run_id}.jsonl.gz")


if __name__ == "__main__":
    main()
