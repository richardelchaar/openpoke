# 07 · Journal

One entry per experiment, in the order they were run. The experiments are listed in [05-plan.md](05-plan.md). Every number comes from a file in `evals/results/`; to see a run under the current grading rules, use `python -m evals.rescore <file>`.

All runs use `anthropic/claude-haiku-5.5` for every role. All are on the dev world except E7.

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
| Needless questions (of 414 runs each) | 3 | 13 |

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

- **When it should ask and doesn't, it usually picks one option.** At 20 agents, of 176 missed questions, 131 went to one of the options and 40 to every option. (An earlier version of this entry had those the wrong way round: the grader was counting a hand-off to the only agent, where the other option was a contact, as "every option".)
- **Size changes which mistake it makes.** With few agents it reuses too readily; with many it creates too readily. Duplicates rise from 1.5% to 3.9%.
- **One category does break with size.** "Ask the adjuster where Anton's claim stands" reaches the client's agent 92% of the time at 20 agents and 39% at 640.
- **A contact with no agent is invisible to it:** right in 0 of 270. It only sees agent names. In 196 it used the agent of the person who has one, in 47 it made a new agent, and in 27 it asked without mentioning the contact.
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

**Decision.** I made three changes from reading these failures: each candidate says how it was found; a question needs at least two options; and the judge's guidance covers three situations it got wrong. I then took them back out, because I didn't run them and the code has to match the results. They are in commit `925a9bf` and are the first thing to try next. The comparison below therefore includes a judge with a known bug: it sometimes asks "which one?" when there is one option.

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

**Decision.** The risk setting isn't earning its place. It stays in the judge's code, which is switched off, only so these runs can be reproduced.

---

## Crowded test for every version

160 agents, 10 extra people per first name, 138 scored cases. One run each, except the original, which has three.

| | V0 | V1 | V2 | V3 | V4 | V5 |
|---|---|---|---|---|---|---|
| Right | 93% | 91% | 92% | 91% | 91% | 89% |
| Needless questions | 13 of 414 (3%) | 7 of 138 (5%) | 9 (7%) | 12 (9%) | 10 (7%) | 14 (10%) |

**Result.** No version does better than the original here. With eleven people called Felix, every version sometimes asks "which Felix?" even when the topic settles it.

**Decision.** Reported as a limit. The changes don't make name crowding worse, and don't fix it.

---


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

**Result.** As expected, every version is well below its main-set score: 62% for the original, 55% for the prompt alone, and 68 to 80% for the four with a lookup. With 40 cases, the gaps between the changed versions are within noise.

- **The lookup wins where there is no name to match:** a surname alone and no name at all, 16 of 16 against the original's 5 of 16. The original mostly creates a duplicate there.
- **The lookup loses on a short form of a first name:** "Wes" is not "Wesley", names are matched as whole words, so the right agent is never a candidate. The original reads the whole list and can make the leap.
- **Two people in one message** confuses the versions with a lookup: both people's agents are candidates, and the message is treated as two tasks or as a question.
- **The original reaches the wrong person 6 times in 40.** No version with the lookup does.

**Decision.** Reported as a limit. The two clear fixes are matching short forms and near-spellings of a name, and telling a recipient from someone merely mentioned. Neither is built.

---

## Heavy use · added because size alone was flat

| | |
|---|---|
| Question | In the normal roster nobody has more than two pieces of work, so a bigger roster never makes one person harder to place. What happens when the roster is the same size and more crowded around the people in a case? |
| Expected | The original gets worse. The versions with a lookup hold up better. Possibly the judge does best, since it weighs each candidate separately. |
| Setup | All six versions, all 448 cases, 160 agents, one run. Each person in a case has six more pieces of work and ten more people share their first name; none of it shares a topic with the case. `…-dev-v*-heavy` |

| | 160 agents | 160 agents, heavy use | Asks when it shouldn't | Duplicates | Right after the answer |
|---|---|---|---|---|---|
| V0 original | 78% | 83% | 3% | 7.4% | 59% |
| V1 prompt only | 81% | 83% | 10% | 7.9% | 66% |
| V2 records and lookup | 97% | 95% | 6% | 0.5% | 73% |
| V3 required to ask | 94% | 91% | 12% | 0.0% | 75% |
| V4 code rule | 90% | 85% | 15% | 0.0% | 49% |
| V5 judge | 93% | 94% | 8% | 0.0% | 64% |

**Result.** Partly as expected, and one surprise.

- **The original's total goes up, and it is worse underneath.** With eight agents for one person in the list it can see the ambiguity, so it asks when it should 83% of the time, up from 35%. But duplicates more than double, to 7.4%, and after the user answers it gets the next step right 59% of the time, down from 83%.
- **V2 holds: 95%.** It asks needlessly a little more.
- **The judge does not pull ahead.** It ties V2 again.
- **The code rule falls furthest,** to 85%, and gets the turn after an answer right less than half the time.
- **Every version is weaker on the turn after the user answers.** That is the clearest effect of crowding.

**Two grading notes, for every version.** Under heavy use a question counts if it is asked and nothing is sent, because a good question about eight pieces of work may not list them all. And corrections are left out: with ten more people sharing the name, "no, the other Gustavo" has no single right answer. I found that by reading seven "failures" in which V2 had cancelled the wrong draft and asked which Gustavo.

**Decision D7 closed: V2 is the default.** Best or tied on the overall rate in every column, and the simplest. The judge is better on the turn after the user answers at the normal roster sizes.

---

## E7 · Held-out world, run once

| | |
|---|---|
| Question | Does it hold on a world I never tuned on? |
| Expected | Close to the dev result. |
| Setup | V0 and V2, 158 cases, sizes 20 / 160 / 640, one run; V2 also under heavy use. Settings locked beforehand. `…-heldout-v0-main`, `…-heldout-v2-main`, `…-heldout-v2-heavy` |

| | 20 | 160 | 640 | 160, heavy use |
|---|---|---|---|---|
| V0 right | 78% | 78% | 74% | not run |
| **V2 right** | **90%** | **92%** | **92%** | **91%** |
| V0 asks when it should | 47% | 42% | 33% | |
| V2 asks when it should | 92% | 97% | 97% | 100% |
| V0 asks when it shouldn't | 2% | 0% | 1% | |
| V2 asks when it shouldn't | 7% | 7% | 7% | 11% |
| V2 right after the answer | 88% | 82% | 78% | 77% |
| V2 reaches the wrong person | 0% | 0% | 0% | 0% |
| V2 tokens per message | 10,300 | 10,500 | 10,700 | 11,900 |
| V0 tokens per message | 11,400 | 17,700 | 39,700 | |

**Result.** It holds, about 4 points below the dev world (92% against 96%), and it asks needlessly about twice as often (7% against 3%). The gain over the original is 12 to 18 points.

**Against the pass bars** (written before any changed version ran):

| Bar | Result on held-out | |
|---|---|---|
| Right, 88% or more | 90 / 92 / 92% | met |
| Asks when it should, 80% or more | 92 / 97 / 97% | met |
| Asks when it shouldn't, 5% or less | 7 / 7 / 7% | **missed** |
| Right after the answer, 85% or more | 88 / 82 / 78% | **missed at two sizes** |
| Wrong person, 1% or less | 0% | met |
| Duplicates, 1% or less | 1.4 / 2.1 / 1.4% | **missed** |
| 640 agents within 3 points of 20 | +2 | met |
| Tokens per message, 15,000 or less | about 10,500 | met |

Five met, three missed. The misses are needless questions, the turn after an answer, and duplicates.

**Not run.** The original under heavy use on this world: the credit ran out.

**What this run cannot show.** The held-out world is built by the same generator as the dev world, from the same kinds of work and the same phrasings. It shows the result isn't tied to particular names or to a client-heavy inbox. It does not show how the system handles a different style of message; the stress set is the only look at that.

---

## Second iteration of V2 · after the held-out run

| | |
|---|---|
| Question | V2 asks needlessly on 3 to 4% of clear messages on dev and 7% on held-out. Can that be cut? |
| Expected | Yes. Reading the needless questions suggested a cause: the lookup also returns agents that only share a topic with the message, and the orchestrator treats them as alternatives ("did you mean Kendrick or Amara?"). |
| Setup | V2 with one change: each candidate says how it was found, and the prompt says a topic-only match belongs to someone the message didn't name. All 448 dev cases, three sizes and heavy use, one run. `…-dev-v2b-main`, `…-dev-v2b-heavy`. The held-out world was not re-run. |

| 20 / 160 / 640 / heavy use | V2 | With the change |
|---|---|---|
| Right | 96 / 97 / 95 / 95% | 96 / 97 / 97 / 96% |
| Asks when it shouldn't | 3.3 / 3.0 / 4.3 / 5.6% | 4.3 / 3.3 / 3.0 / 4.5% |
| Asks when it should | 100 / 100 / 100 / 100% | 99 / 99 / 97 / 100% |
| Right after the answer | 87 / 85 / 82 / 73% | 89 / 88 / 84 / 72% |
| Duplicates, of 406 runs (434 under heavy use) | 5 / 3 / 5 / 2 | 2 / 1 / 3 / 3 |

**Result.** Wrong again. The needless questions did not move. The change is a tie overall, slightly better on the turn after an answer, and it missed a few questions it should have asked, which V2 never did.

**Decision.** Off by default (`OPENPOKE_EXPLAIN_CANDIDATES`). V2 as measured on the held-out world stays the default. The cause of the needless questions is still open.
