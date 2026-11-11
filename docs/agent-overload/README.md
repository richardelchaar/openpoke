# Agent overload

My work on agent overload in OpenPoke: what the problem is, what I changed, and how I tested it.

Based on `shlokkhemani/openpoke` at commit `5b5f635`.

---

## The problem in one sentence

The orchestrator has to pick the right agent from a list of bare names that only grows, with no record of what each agent did and no sign of the people who don't have an agent yet, under a prompt that tells it never to ask.

## What I changed

1. **Each agent has a work record:** who it has dealt with, on which threads, what it searched for. The record is filled in from the agent's own tool calls.
2. **A lookup finds about ten candidates for each message,** in code: the agents used recently, the agents that have dealt with anyone the message names, and the agents whose record matches the topic. It also returns the contacts the names matched, including people with no agent.
3. **The orchestrator sees those candidates in place of every name,** hands off by agent id, and creates a new agent with a separate tool.

I also built two ways of forcing the decision to ask, in code and with a second model call, and measured them. Neither beat letting the orchestrator decide from the candidates, so both are switched off.

## Results

One model for everything (`anthropic/claude-haiku-5.5`). 448 test cases on the dev world, 158 on a held-out world run once at the end.

**Right outcome, held-out world**

| | 20 agents | 160 agents | 640 agents |
|---|---|---|---|
| Original | 78% | 78% | 74% |
| **Records and lookup** | **90%** | **92%** | **92%** |

**The same on the dev world, with every version**

| | 20 agents | 160 agents | 640 agents | 160 agents, heavy use |
|---|---|---|---|---|
| Original | 81% | 78% | 77% | 83% |
| Prompt rewritten, nothing else | 81% | 81% | 81% | 83% |
| **Records and lookup** | **96%** | **97%** | **95%** | **95%** |
| …and required to ask when unsure | 94% | 94% | 91% | 91% |
| …and code decides when to ask | 91% | 90% | 91% | 85% |
| …and a second model call decides | 94% | 93% | 93% | 94% |

"Heavy use" keeps the roster at 160 agents and gives each person in a case six more pieces of work and ten namesakes.

**What stands out**

- **The original's largest error is not asking.** It asks when it should 35 to 45% of the time. With the records and lookup it asks 92 to 100% of the time.
- **A longer list does not make the original less accurate** on this model. It makes it cost more: 40,100 tokens a message at 640 agents, against 11,100 with the lookup.
- **A rewritten prompt alone does nothing overall.** It asks more and creates far more duplicates.
- **Forcing the question adds needless questions and no correct ones.**
- **With the lookup, no run reached the wrong person.**

**Where it falls short**

- On the held-out world it asks needlessly 7% of the time, against a bar of 5% that I set beforehand. Three of eight bars were missed.
- On 40 messier messages it gets 70% right, against 62% for the original. A short form of a name ("Wes" for Wesley) finds nothing.
- The test set is generated, and I chose its categories. The 92% is what the design does when names resolve cleanly.

---

## Reading order

| File | What's in it |
|---|---|
| [08-report.md](08-report.md) | The write-up: findings, results, limits, what I'd do next |
| [01-codebase.md](01-codebase.md) | How OpenPoke works, the causes of overload in the code, other gaps I found |
| [02-solutions.md](02-solutions.md) | The options for each cause, what I chose and why, the decision log |
| [03-technical-design.md](03-technical-design.md) | What is built, part by part |
| [04-eval-design.md](04-eval-design.md) | The test worlds, the cases, how answers are checked |
| [05-plan.md](05-plan.md) | The plan as written before the runs, the pass bars, and what changed |
| [06-tasks.md](06-tasks.md) | The checklist |
| [07-journal.md](07-journal.md) | One entry per experiment: what I expected, what happened, what I decided |

If you have five minutes, read this page and the report.

## Running it

```
python -m pytest tests -q                 # 38 tests, no model calls
python -m evals.cases.validate            # every case against its world
python -m evals.report                    # the results tables, from the saved runs
python -m evals.run --world dev --version v2 --sizes 20,160,640     # needs OPENROUTER_API_KEY
```
