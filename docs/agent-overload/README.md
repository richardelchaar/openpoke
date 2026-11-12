# Agent overload

My work on agent overload in OpenPoke: what the problem is, what I changed, and how I tested it.

Based on `shlokkhemani/openpoke` at commit `5b5f635`.

**Start with the report:** [report.html](report.html) is the full write-up with charts (download it and open it in a browser), and [08-report.md](08-report.md) is the same text in Markdown.

---

## The problem in one sentence

The orchestrator has to pick the right agent from a list of bare names that only grows, with no record of what each agent did and no sign of the people who don't have an agent yet, under a prompt that tells it never to ask.

## What I did

1. **Built a test set first,** with a known right answer for every message, and froze it.
2. **Measured the original.** Its largest error is acting when it should ask. A longer roster did not make it less accurate on the model I used; it made it more expensive.
3. **Laid out seven configurations,** from the original to the most involved, each behind a switch in the same code, and ran every one on the same cases.
4. **Chose the simplest one that did best:** each agent keeps a work record, a lookup in code finds about ten candidates for each message, and the orchestrator is shown those in place of every name.
5. **Ran it once on a held-out world.**

## Results

One model for everything (`anthropic/claude-haiku-5.5`). 448 test cases on the world I built on and 158 on a held-out world; 406 and 143 of them are scored.

**Every configuration, right outcome, on the world I built on**

| | 20 agents | 160 agents | 640 agents | 160 agents, crowded |
|---|---|---|---|---|
| 0. Original | 81% | 78% | 77% | 83% |
| 1. Prompt rewritten, nothing else | 81% | 81% | 81% | 83% |
| 2. Lookup over a description of each agent | 87% | 86% | 85% | 89% |
| **3. Lookup over a work record of each agent** | **96%** | **97%** | **95%** | **95%** |
| 4. …and required to ask when unsure | 94% | 94% | 91% | 91% |
| 5. …and code decides when to ask | 91% | 90% | 91% | 85% |
| 6. …and a second model call decides | 94% | 93% | 93% | 94% |

The crowded roster keeps 160 agents and gives each person in a case six more pieces of work and ten namesakes. That column is graded with two allowances described in the report; under the normal rules configuration 0 scores 68% there and configuration 3 scores 85%.

**The chosen configuration on the held-out world, run once**

| | 20 agents | 160 agents | 640 agents |
|---|---|---|---|
| Original, right | 78% | 78% | 74% |
| **Configuration 3, right** | **90%** | **92%** | **92%** |
| Original, asks when it should | 47% | 42% | 33% |
| Configuration 3, asks when it should | 92% | 97% | 97% |
| Original, tokens per message | 11,400 | 17,700 | 39,700 |
| Configuration 3, tokens per message | 10,300 | 10,500 | 10,700 |

**What stands out**

- **The original's largest error is not asking.** With the work record and lookup it asks when it should 92 to 97% of the time.
- **A rewritten prompt alone does nothing overall.**
- **A one-line description per agent gets part of the way.** The work record and the contacts get the rest, in three places: people with no agent yet, a go-between copied on someone else's work, and fewer duplicates.
- **Forcing the question adds needless questions and no correct ones.**
- **The gain is on unclear messages.** On clear ones the chosen configuration is slightly worse, because it sometimes asks when it didn't need to.

**Where it falls short**

- On the held-out world it asks needlessly on 7% of clear messages, against a bar of 5% that I set beforehand. Three of eight bars were missed. A second iteration aimed at this did not reduce it.
- On 40 messier messages it gets 70% right, against 62% for the original. A short form of a name ("Wes" for Wesley) finds nothing.
- The test set is generated, and I chose its categories. Everything ran on one model.
- The test supplies the user's contacts and a clean summary for every agent. In the app these are thinner.

---

## What is in this folder

| File | What's in it |
|---|---|
| [report.html](report.html), [08-report.md](08-report.md) | The write-up: the test set, the original's results, the seven configurations, results, limits, what I'd do next |
| [01-codebase.md](01-codebase.md) | How OpenPoke works, the causes of overload in the code, other gaps I found |
| [02-solutions.md](02-solutions.md) | The options for each cause, what I chose and why, the decision log |
| [03-technical-design.md](03-technical-design.md) | What is built, part by part |
| [04-eval-design.md](04-eval-design.md) | The test worlds, the cases, how answers are checked |
| [05-plan.md](05-plan.md) | The plan as written before the runs, the pass bars, and what changed |
| [06-tasks.md](06-tasks.md) | The checklist |
| [07-journal.md](07-journal.md) | One entry per experiment: what I expected, what happened, what I decided |

In the code and the journal the configurations are named `v0` (0), `v1` (1), `v2d` (2), `v2` (3), `v3` (4), `v4` (5) and `v5` (6).

## Running it

```
python -m pytest tests -q                 # 39 tests, no model calls
python -m evals.cases.validate            # every case against its world
python -m evals.report dev                # the results tables, from the saved runs
python -m evals.run --world dev --version v2 --sizes 20,160,640     # needs OPENROUTER_API_KEY
```
