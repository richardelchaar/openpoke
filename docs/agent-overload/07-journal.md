# 07 · Journal

One entry per experiment, in the order they were run. The experiments are listed in [05-plan.md](05-plan.md). Every number comes from a file in `evals/results/`; to see a run under the current grading rules, use `python -m evals.rescore <file>`.

All runs use `anthropic/claude-haiku-5.5` for every role, on the dev world.

---

## Setup · Nov 10

**Making it run.** The original's models are hardcoded to `anthropic/claude-sonnet-4`. A live call returned "no provider serves this model anymore", so nothing worked until the models came from config. The first request then failed with a 402: the client sends no output cap, so the provider reserved the model's full 65,536-token output against the account balance. Capping output at 4,096 fixed it.

**Cost.** Each message makes at least two model calls, and each carries a system prompt of about 4,400 tokens. Marking the system prompt and the first message as cacheable cut the cost per message by 40 to 55% with no change in behaviour. All runs below have caching on.

**The test set.** Two generated worlds, 448 dev cases and 158 held-out cases, 22 categories. Frozen and tagged `cases-frozen` before any changed version was run.

---

## E1 · Size sweep

| | |
|---|---|
| Question | At what roster size does the original start to fail? |
| Expected | Accuracy falls as the roster grows. |
| Setup | V0, about 64 cases, 2 repeats, 8 sizes. Run before the cases were frozen, on an earlier draw. `20261110-194312-dev-v0-sweep` |

| Agents | 10 | 20 | 40 | 80 | 160 | 320 | 640 | 1,280 |
|---|---|---|---|---|---|---|---|---|
| Right | 73% | 73% | 78% | 80% | 75% | 77% | 77% | 79% |
| Tokens per message | 11,900 | 12,200 | 12,800 | 14,600 | 19,000 | 26,300 | 40,700 | 69,500 |

**Result.** I was wrong. Accuracy is flat from 10 agents to 1,280. Cost is not: six times the tokens at the top.

**Why.** Finding a named person in a list is close to a text search for a current model. The hard part is the two or three agents that could fit, and those are in the roster at every size. My filler agents also can't add confusion, by design: none shares a name with anyone in a case, so that a case's right answer is the same at every size.

**Decision.** Sizes 20, 160 and 640. The write-up leads with ambiguity and cost, not list length.

---

## E1b · Crowded test (added because of E1)

| | |
|---|---|
| Question | E1 held the number of same-name people fixed. Does a roster with more people sharing a first name do worse? |
| Expected | Yes, noticeably. |
| Setup | V0, 160 agents, 168 cases whose right answer can't change with more namesakes, 3 repeats, with 0 and 10 extra people per first name. `…-v0-crowd0`, `…-v0-crowd10` |

| | 0 extra | 10 extra |
|---|---|---|
| Right | 95% | 93% |
| Route | 95% | 92% |
| Needless questions (of 414 runs) | 3 | 13 |

**Result.** A small effect: about 3 points on routing, and more needless questions.

**Decision.** Keep it as a cheap extra run for every version.

---

## E2 · Baseline

| | |
|---|---|
| Question | How bad is the original, and which errors dominate? |
| Expected | Reusing an agent for unrelated work would be the largest error. |
| Setup | V0, all 448 cases, sizes 20 / 160 / 640, 3 repeats. `20261110-202454-dev-v0-baseline` |

| | 20 | 160 | 640 |
|---|---|---|---|
| Right | 81% | 78% | 77% |
| Asks when it should | 45% | 35% | 35% |
| Asks when it shouldn't | 1% | 1% | 1% |
| Duplicates | 1.5% | 3.2% | 3.9% |
| Tokens per message | 11,700 | 18,200 | 40,100 |

**Result.** Wrong again about the largest error. It is not asking: about 200 of 1,218 runs at each size.

What else the run showed:

- **When it should ask and doesn't, it usually acts on every option.** At 20 agents, 119 of 176 missed questions sent the work to both agents or both people.
- **Size changes which mistake it makes.** With few agents it reuses too readily; with many it creates too readily. Duplicates rise from 1.5% to 3.9%.
- **One category does break with size.** "Ask the adjuster where Anton's claim stands" reaches the client's agent 92% of the time at 20 agents and 39% at 640.
- **A contact with no agent is invisible to it:** 0 of 270. It only sees agent names.
- **Run-to-run variation is small.** The overall rate moved 1.2 points across the three repeats, and 90% of cases gave the same result all three times.

**A mistake of mine, corrected.** I had scored "new work for a person who already has an agent" as an error when the original reuses that person's agent. The original's prompt asks for exactly that, so I was scoring my own design preference. That category and one-off lookups are now reported as behaviour and left out of the rates. The original reuses in 54% / 38% / 26% of those cases.

**Decision.** Pass bars written into the plan. Later versions run once per size, and a gap under 2 points is a tie.

---

## E3 · Prompt alone (V1), and prompt plus records (V2)

| | |
|---|---|
| Question | How far does a rewritten prompt get, and what do the records add? |
| Expected | The prompt helps a little. The records remove the effect of size. |
| Setup | All 448 cases, 3 sizes, 1 run each. `20261110-211320-dev-v1-main`, `20261110-214819-dev-v2-main` |

| | V0 | V1 prompt only | V2 records + lookup |
|---|---|---|---|
| Right (20 / 160 / 640) | 81 / 78 / 77% | 81 / 81 / 81% | 96 / 97 / 95% |
| Asks when it should | 45 / 35 / 35% | 67 / 67 / 64% | 100 / 100 / 100% |
| Asks when it shouldn't | 1% | 3 to 5% | 3 to 4% |
| Duplicates | 1.5 to 3.9% | 6 to 7% | about 1% |
| Tokens per message at 640 | 40,100 | 35,000 | 11,100 |

**Result.** The prompt alone does nothing overall. It asks more, and it creates far more duplicates, because "new work gets a new agent" with only names to go on makes it start fresh too often.

The records do the work. Once the orchestrator sees a handful of candidates, each with who it has dealt with and what it is about, plus the contacts the names matched, it asks every time it should, without being forced to.

**Decision.** Keep the records and the lookup.

---

## E6 · Lookup quality (run before E4, since it needs no model)

| | |
|---|---|
| Question | Is the right agent among the candidates? |
| Expected | High everywhere except different wording. |
| Setup | The app's lookup code over every case at 3 sizes. `python -m evals.offline lookup` |

**Result.** 100% in every category but one, at every size, and the same with 3, 5, 10 or 20 candidates allowed. Different wording was not the weak spot, because every such case names the person and the name match finds the agent.

The one failure was **0 of 12** on follow-ups to an email alert. "Reply to that" names nobody and follows no hand-off, so nothing in the message pointed anywhere.

**Decision.** Added a fourth source: when a message names nobody, the people named in the last thing the user was shown. 12 of 12 after the change. The candidate limit stays at 10; nothing here argues for another value.

**Plain search against the full lookup** (`python -m evals.offline search`, 640 agents). Keyword search over the records with nothing else finds the agents a case needs 88% of the time. The full lookup finds them 100%. Everything plain search misses is a message that names nobody: pronoun follow-ups, follow-ups to an email alert, and follow-ups after a question, each 0% against 100%. It also can't see a contact who has no agent. So search is most of it, and the recent hand-offs, the last message shown and the contacts are what close the gap.

**Not covered.** No case combines different wording with no name, which is where keyword search would miss. That remains untested, and it is the case for adding embeddings later.

---

## E4 · Who decides when to ask (V3, V4, V5), first round

| | |
|---|---|
| Question | Which way of deciding to ask works? |
| Expected | V3 rarely asks. V4 asks on the obvious cases. V5 also catches the ones that differ in meaning. |
| Setup | All 448 cases, 3 sizes, 1 run each. `…-dev-v3-main`, `…-dev-v4-main`, `…-dev-v5-main` |

| | V2 picks freely | V3 told to ask | V4 code rule | V5 judge |
|---|---|---|---|---|
| Right (20 / 160 / 640) | 96 / 97 / 95% | 94 / 94 / 91% | 91 / 90 / 91% | 94 / 93 / 93% |
| Asks when it should | 100% | 100% | 96% | 100% |
| Asks when it shouldn't | 3 to 4% | 6 to 12% | 11 to 12% | 7 to 9% |
| Right after the answer | 87 / 85 / 82% | 89 / 88 / 88% | 79 / 77 / 77% | 90 / 90 / 92% |

**Result.** My expectation was wrong in the direction that matters. With candidates in front of it, the orchestrator already asks when it should. Each stronger way of making it ask added needless questions and no correct ones.

- **V3** asks about new people and about things the topic already settles.
- **V4** can't see meaning. "Tell Caleb we want the new seats live on Monday" shares no word with his subscription record, so it asks. After the user answers "something new" it gets the next step right only 26% of the time.
- **V5** asked "which one?" when there was a single option, and treated candidates that only shared a topic with the message as alternatives.

What V5 does better is the turn after the answer.

**Two grading rules corrected after reading the failures, for every version:**

- On "no, the other Colin" the app routes to the right Colin and tells the wrongly used agent to stop. That was being marked as reaching the wrong person.
- After a question about which person, a new agent for the chosen person counts as well as their existing one.

**Decision.** Three changes for a second round, all from reading failures: each candidate now says how it was found; a question needs at least two options; and the judge's guidance covers three situations it got wrong.

---

## E5 · The ask settings

| | |
|---|---|
| Question | What does asking more readily buy? |
| Expected | A curve, with V5's closer to the corner. |
| Setup | Decisions recomputed from the lookup's scores (V4) and the judge's saved labels (V5), 160 agents. `python -m evals.offline tradeoff` |

| V4 margin | 0 | 0.1 | 0.25 | 0.5 | 0.75 | 1.0 |
|---|---|---|---|---|---|---|
| Asks when it should | 95% | 95% | 95% | 95% | 95% | 95% |
| Asks when it shouldn't | 8% | 9% | 9% | 9% | 12% | 14% |

| V5 setting | loose | balanced | strict |
|---|---|---|---|
| Asks when it should | 98% | 98% | 98% |
| Asks when it shouldn't | 5.8% | 6.8% | 6.8% |

**Result.** There is no curve. Neither dial buys a correct question; both only add needless ones. The setting I built to ask more readily before a send moves the result by one point.

**Decision.** The risk setting isn't earning its place. Unless the second round changes this, it goes.

---

## Crowded test for every version

160 agents, 10 extra people per first name, 138 scored cases, one run.

| | V0 | V1 | V2 | V3 | V4 | V5 |
|---|---|---|---|---|---|---|
| Right | 93% | 91% | 92% | 91% | 91% | 89% |
| Needless questions | 13 of 414 | 7 | 9 | 12 | 10 | 14 |

**Result.** No version does better than the original here. With eleven people called Felix, every version sometimes asks "which Felix?" even when the topic settles it.

**Decision.** Reported as a limit. The changes don't make name crowding worse, and don't fix it.

---

*Next: the second round of V2 to V5, then the held-out world.*

---

## Stress set · written after the main results

| | |
|---|---|
| Question | The main cases always spell a name the way the contacts do. What happens when a message doesn't? |
| Expected | Every version does worse, and the lookup does worst on names it can't match. |
| Setup | 40 messages in 7 kinds, 160 agents, one run per version. `…-dev-v*-stress`. Not used to tune anything. |

| Right, of the cases in each kind | V0 | V1 | V2 | V3 | V4 | V5 |
|---|---|---|---|---|---|---|
| Short form of a first name ("ask Wes…") | 4/6 | 3/6 | 1/6 | 3/6 | 3/6 | 1/6 |
| Misspelt surname ("Colin Pachceo") | 6/6 | 6/6 | 6/6 | 5/6 | 5/6 | 5/6 |
| Surname alone ("ask Oduya…") | 3/6 | 2/6 | 6/6 | 6/6 | 6/6 | 6/6 |
| Lowercase with a typo in the first name | 5/6 | 5/6 | 3/6 | 3/6 | 4/6 | 4/6 |
| No name, topic and detail | 1/5 | 1/5 | 5/5 | 5/5 | 5/5 | 5/5 |
| No name, topic in other words | 1/5 | 1/5 | 5/5 | 5/5 | 5/5 | 5/5 |
| Two people named, one is the recipient | 5/6 | 4/6 | 2/6 | 0/6 | 4/6 | 4/6 |
| **All 40** | **25** | **22** | **28** | **27** | **32** | **30** |

**Result.** As expected, every version is well below its main-set score: 63% for the original and 68 to 80% for the others. With 40 cases, the gaps between the changed versions are within noise.

- **The lookup wins where there is no name to match:** a surname alone and no name at all, 16 of 16 against the original's 5 of 16. The original mostly creates a duplicate there.
- **The lookup loses on a short form of a first name:** "Wes" is not "Wesley", names are matched as whole words, so the right agent is never a candidate. The original reads the whole list and can make the leap.
- **Two people in one message** confuses the versions with a lookup: both people's agents are candidates, and the message is treated as two tasks or as a question.
- **The original reaches the wrong person 6 times in 40.** No version with the lookup does.

**Decision.** Reported as a limit. The two clear fixes are matching short forms and near-spellings of a name, and telling a recipient from someone merely mentioned. Neither is built.
