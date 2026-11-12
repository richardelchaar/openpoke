# Results

One file per run. The first line is the run's settings and summary; each line after is one
case's trace and grade.

- `runs.csv` has one row per run and roster size **as graded when the run was made**. Several
  grading rules changed afterwards, so its figures differ from the report's.
- `regraded.csv` has every run under the current rules. It is what the report uses, and
  `python -m evals.report --csv` rebuilds it.

The grade and summary stored in a file are as the grader stood when the run was made.
To see a run under the current rules, re-grade it. This calls no model:

```
python -m evals.rescore evals/results/<run>.jsonl.gz
```

Notes on individual runs:

- `…-v0-sweep`: the original at eight roster sizes on about 64 cases, used to choose the
  three sizes. It was run before the cases were frozen, on an earlier draw of them, so it
  can't be re-graded against the current cases. Its stored summary is what's cited.
- `…-v0-baseline`: stored with the first scoring, which counted two design-choice
  categories as errors. Re-grading gives the figures used in `docs/agent-overload/05-plan.md`.
