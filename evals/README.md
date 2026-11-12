# Evals

How the router is tested. The design is in `docs/agent-overload/04-eval-design.md`.

```
worlds/         catalogue of 40 kinds of work, name lists, the generator, the two generated worlds,
                and the extra work used by the heavy-use roster (heavy.py, *.heavy.json)
cases/          the case builder, the validator, the cases, the 20-case review sampler,
                and the stress set (stress.py, dev.stress.jsonl)
run.py          runs one version over the cases at one or more roster sizes
run_case.py     runs one case through the real orchestrator, in its own process
materialize.py  writes a world in the form each version stores agents
grade.py        the grading rules and the summaries
rescore.py      re-grades one saved run with the current rules
report.py       builds every results table, and regraded.csv, from the saved runs
charts.py       draws the charts used in the Markdown report from the saved runs
offline.py      lookup quality, plain search against the lookup, the ask settings
references.py   four simple strategies scored by the same grader
results/        one file per run, runs.csv as recorded, regraded.csv under the current rules
recorded/       saved model responses (local, not in git)
CHECKSUMS       sha256 of the frozen worlds and cases
```

None of these call a model:

```
python -m evals.worlds.generate && python -m evals.cases.build      # rebuild the test set
python -m evals.cases.validate
shasum -a 256 -c evals/CHECKSUMS
python -m evals.references dev
python -m evals.report dev
python -m evals.report --categories heldout
python -m evals.offline lookup
```

Running a version needs `OPENROUTER_API_KEY`:

```
python -m evals.run --world dev --version v0 --sizes 20,160,640 --repeats 3
python -m evals.run --world dev --version v2 --sizes 160 --heavy --tag heavy
python -m evals.run --world dev --set stress --version v2 --sizes 160 --tag stress
```

Versions: `v0` the original, `v1` the rewritten prompt alone, `v2` records and lookup (the default),
`v2d` v2 with only a title and one line of description kept per agent, `v2b` v2 with each candidate saying how it was found, `v3` required to ask, `v4` code rule, `v5` a second model call.
