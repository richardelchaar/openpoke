# Agent overload

My work on agent overload in OpenPoke: what the problem is, what I changed, and how I tested it.

Based on `shlokkhemani/openpoke` at commit `5b5f635`.

**Status:** planning complete; implementation not started. Results will appear here first.

---

## The problem in one sentence

The orchestrator has to pick the right agent from a list of bare names that only grows, with no record of what each agent did, under a prompt that tells it never to ask.

## The approach in four lines

1. **Measure the original first,** on test cases fixed before any change.
2. **Replace the list of names with a work record per agent,** and look up a handful of candidates for each message.
3. **Decide in code whether to route, create or ask,** and only allow a hand-off to agents that decision approved.
4. **Compare each way of deciding on the same cases,** then confirm on a second world I never tuned on.

## Results

*To come.*

---

## Reading order

| File | What's in it |
|---|---|
| [01-codebase.md](01-codebase.md) | How OpenPoke works today, the causes of overload in the code, other gaps I found |
| [02-solutions.md](02-solutions.md) | The options for each cause, what I chose and why, the decision log |
| [03-technical-design.md](03-technical-design.md) | What I picked for each part and why: storage, lookup, the model call, the decision rules, safety |
| [04-eval-design.md](04-eval-design.md) | The test worlds, the cases, how answers are checked, what's traced |
| [05-plan.md](05-plan.md) | The versions, the experiments, what I expect from each |
| [06-tasks.md](06-tasks.md) | The ordered checklist |
| [07-journal.md](07-journal.md) | One entry per experiment *(starts with the first run)* |
| 08-report.md | The final write-up *(written last)* |

If you have five minutes, read this page and the report.
