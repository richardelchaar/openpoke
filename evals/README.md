# Evals

How the router is tested. The design is in `docs/agent-overload/04-eval-design.md`.

```
worlds/      catalogue of 40 kinds of work, name lists, the generator, the two generated worlds
cases/       the case builder, the validator, the cases, the 20-case review sampler
run.py       runs one version over the cases at one or more roster sizes
run_case.py  runs one case through the real orchestrator, in its own process
materialize.py  writes a world in the form each version stores agents
grade.py     the grading rules and the summary tables
rescore.py   re-grades a saved run with the current rules, calling no model
results/     one file per run, plus runs.csv
recorded/    saved model responses (local, not in git)
CHECKSUMS    sha256 of the worlds and cases
```

Rebuild and check the test set (no model calls):

```
python -m evals.worlds.generate
python -m evals.cases.build
python -m evals.cases.validate
shasum -a 256 -c evals/CHECKSUMS
```

Run a version (needs `OPENROUTER_API_KEY`):

```
python -m evals.run --world dev --version v0 --sizes 20,160,640 --repeats 3
```
