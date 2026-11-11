# 05 · Plan: experiments and changes

What I'll run, in what order, what I expect, and what would change my mind. Results go in [07-journal.md](07-journal.md).

---

## 1. The versions

All versions live in the same code behind config switches, and all run on the same model.

| Version | Lookup | Who decides | Prompt |
|---|---|---|---|
| **V0** Original | None: every name in the prompt | Orchestrator | Original |
| **V1** Prompt only | None | Orchestrator | Rewritten |
| **V2** Records and lookup | Work records | Orchestrator picks from the candidates | Rewritten |
| **V3** Told to ask | Work records | Orchestrator, with a rule to ask when unsure | Rewritten |
| **V4** Code rule | Work records | Code asks when candidates for the same person are too close to call | Rewritten |
| **V5** Judge + code | Work records | A small model labels each candidate; code counts | Rewritten |

V2 adds several things together: the lookup, agent IDs, the separate create tool, the hand-off record, throwaway agents and the duplicate check. So V1 against V2 compares the prompt alone with the prompt plus records. It doesn't separate those pieces.

From V2 up, every version gets the same candidates from the same lookup. Only the decider changes.

At the end, the default is set to the winner. The others stay in the code, switched off, so any result can be re-run.

---

## 2. The experiments

| # | Experiment | Question | What I expect | What would change my mind |
|---|---|---|---|---|
| E1 | **Size sweep.** V0 at doubling roster sizes on ~60 cases | At what size does the original start to fail? | Accuracy falls as the roster grows | If it doesn't fall, overload on this model is about ambiguity, not size, and the report leads with that |
| E2 | **Baseline.** V0 at the chosen sizes, all dev cases | How bad is it, and which errors dominate? | Wrong reuse is the largest error, because the prompt favours existing agents | The error breakdown sets which fixes matter most |
| E3 | **Prompt and records.** V1 and V2 | How far does the prompt alone get, and what do the records add on top? | The prompt helps a little; the records remove the effect of size | If V1 alone matches V2, the records aren't earning their place |
| E4 | **The decider.** V3, V4, V5, judged on the cases about asking | Which way of deciding to ask works? | V3 rarely asks; V4 asks on the obvious cases; V5 also catches the ones that differ in meaning | If V4 ties with V5, V5's extra call is dropped |
| E5 | **Trade-off.** V4 and V5 across their ask settings, scored from saved results | What does each extra question buy? | A curve; V5's sits closer to the corner | Picks the default setting |
| E6 | **Lookup quality.** How often the right agent is among the candidates, by category | Is keyword search enough? | High everywhere except "different wording" | If that category is poor, add embeddings and re-run |
| E7 | **Held-out.** V0 and the winner on the second world, once, at the same roster sizes | Does it hold on a world I never tuned on? | Close to the dev result | Whatever it shows is what I report |

**How E4 is judged.** V5's judge call does more than decide when to ask: it also says whether a message is chat or work, and splits a two-part message. V4 leaves both to the orchestrator. So the choice between them is made on the cases about asking: the ones where it should ask (categories 13 to 15) and the ones where it should not (4 and 5). The overall score is reported too. If V4 wins, chat-or-work stays with the orchestrator's prompt.

**The duplicate check** is on from V2 up. Its traces show how often it fired and how often it was right, so it needs no run of its own.

**Before E7,** the winner is run once more on the dev world with the settings locked. E7 is compared with that run.

**The ask settings in E5.** Each of the two versions has one dial for how readily it asks:

| Version | Dial | Values |
|---|---|---|
| V4 | The margin: how close two candidates' keyword scores must be to count as a tie | A few values from small (rarely asks) to large (asks often) |
| V5 | What stops a route to the one exact match when another candidate is plausible | loose (nothing), balanced (only when the task would send), strict (always) |

Each value gives one point: wrong routes on one axis, unnecessary questions on the other.

V4's margin is chosen before its run in E4. That only needs the lookup's scores, which exist as soon as the lookup does.

E1 to E4 and E7 call the model. E5 and E6 are code over saved results, so they cost nothing to run.

**What changed as the work went.** This section is the plan as written before the runs. What happened is in [07-journal.md](07-journal.md). The differences:

| Planned | What happened |
|---|---|
| Sizes chosen where the original starts to fail | It doesn't fail with size. Sizes are 20, 160 and 640, and a fourth roster was added: 160 agents with heavy use, where each person in a case has six more pieces of work and ten namesakes. |
| V4's margin chosen before its run | Run at 0.25. Swept afterwards from 0 to 1: no value adds a correct question. |
| The duplicate check measured from its traces | Not done. The duplicate rate is reported for every version instead. |
| A final dev run of the winner before E7 | Not needed: the winner's settings were never changed after its dev run. |
| An agent-memory check on about 20 agents | Not built. Agent memory is listed as a gap in the report. |
| | Added: a crowded test (ten namesakes), a stress set of 40 messier messages, and a comparison of plain keyword search with the full lookup. |
| | Five grading rules were changed after reading failures, for every version. Each is in the journal, and the report lists them with their effect. |
| | A second iteration of V2 (each candidate says how it was found), run on the dev world. A tie. |

---

## 3. Pass bars

I write the bars into this file **after E2 and before any fixed version is run**, because sensible targets depend on the baseline. Each bar is a number for one rate at one roster size. A missed bar is reported as missed.

Written on Nov 10 after the baseline (run `20261110-202454-dev-v0-baseline`), before any fixed version was run. The original's figures are for 20 / 160 / 640 agents, as graded on that day; two later grading changes moved them slightly (the report has the current figures). A bar has to hold at every size.

| Rate | The original | Bar for the fix |
|---|---|---|
| Right outcome, overall | 80% / 76% / 77% | 88% or more |
| Asked when it should | 45% / 35% / 35% | 80% or more |
| Asked when it shouldn't | 1% / 1% / 1% | 5% or less |
| Right after the answer | 82% / 77% / 78% | 85% or more |
| Wrong person | 2.6% / 1.6% / 0.7% | 1% or less |
| Duplicates | 1.2% / 3.0% / 3.9% | 1% or less |
| Right outcome at 640 agents against 20 | the same | Within 3 points |
| Tokens per message | 11,700 / 18,200 / 40,200 | 15,000 or less at every size |

**Two categories are left out of these rates.** New work for a person who already has an agent, and one-off lookups. The original is told to reuse an agent that has useful context, so when it puts a person's new work into their existing agent it is doing as designed. I prefer one agent per piece of work, but that is my design choice and not the original's mistake. So these two are reported as behaviour (how often each version reuses an existing agent: the original does so in 54% / 38% / 26% of new-work cases) and not counted as right or wrong.

The original was run three times. Its overall rate moved by 1.2 points between repeats, and 90% of cases gave the same result all three times. So each fixed version is run once per size, and a difference of under 2 points overall is treated as a tie.

---

## 4. Rules for keeping a change

A component stays only if, on the dev world:
1. it improves the rate it was built for;
2. it doesn't make the wrong-person rate worse; and
3. its cost in time and tokens is stated.

When two options do equally well, the simpler one wins.

Settings are locked before E7. Nothing changes after the held-out run.

---

## 5. Where the changes are

| Area | Files |
|---|---|
| Config: models, data directory, routing switches | `server/config.py` |
| Work records and contacts | `server/services/agents/` (new) |
| Lookup, the pipeline, the two deciders | `server/routing/` (new) |
| Orchestrator: prompt, tools, running the lookup | `server/agents/interaction_agent/` (`agent.py`, `tools.py`, `runtime.py`, `system_prompt_v2.md` and the `agent_tools_*.md` sections) |
| Execution agents: record updates, the record in the prompt | `server/agents/execution_agent/` (`runtime.py`, `agent.py`, `system_prompt.md`) |
| Model client: output cap, caching, retries, forced tool call | `server/openrouter_client/client.py` |
| Hand-off entries in the conversation log | `server/services/conversation/log.py` |
| Eval | `evals/` (new) |
| Tests | `tests/` (new) |
| Checks on every push | `.github/workflows/checks.yml` (new) |
