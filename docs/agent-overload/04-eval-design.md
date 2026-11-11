# 04 · Eval design

How the router is tested: the worlds, the cases, how answers are checked, what gets traced, and the rules that keep it honest. The code is in `evals/`.

---

## 1. What one eval run does

1. Take a world and a roster size.
2. For each case: write the roster and the recent chat into a fresh data directory, then send the message through the **real orchestrator code** with the version's switches set.
3. Capture everything the orchestrator does in that turn: every hand-off, every new agent, any question, any direct reply.
4. If the case called for a question and got one, send each scripted answer as a second turn.
5. Grade against the expected outcome and save the trace.

Three things are swapped out, and nothing else: execution agents don't run (a hand-off is recorded and stops there), model responses are saved so the same request replays for free, and the clock for log entries is fixed so a replay sends identical prompts.

Each case runs in its own process, because the app binds its data directory when it starts.

---

## 2. The worlds

A generator builds each world from a seed. Nothing in the test set is written by a model: the facts and the wording both come from code.

**What a world contains**

| Part | What it is | Dev world |
|---|---|---|
| Core | The people and work that cases are about, laid out around the traps below | 83 agents |
| Filler | Everyone else, there to make the roster big | 1,300 agents |
| Crowd | Extra people who share a first name with someone in the core. Used only by the crowded test. | 784 agents |

**How it is generated**

1. A catalogue of 40 kinds of work (claims, renewals, invoices, meetings, a dentist appointment). Each kind has a label, another way a user might say it, an email subject, details, a first request, and three follow-ups.
2. People are drawn from name lists. Each person gets one or two kinds of work, filled in with a detail.
3. Each piece of work gets a short history: the requests the agent received and the tool calls it made, with one address and one thread carried through.
4. Each agent gets a name in the style the original app uses (its prompt's examples are "Vercel Job Offer" and "Email to Sharanjeet"): sometimes the full name and topic, sometimes a first name and topic, sometimes only "Email to" and a name.

Kinds are grouped into families that share vocabulary. Two kinds from one family are never given to the same person, or to two people with the same first name, so a request that names a topic points at one of them.

**The traps in the core**

| Trap | Count |
|---|---|
| Two people with the same first name, each with one piece of work | 12 pairs |
| One person with two pieces of work | 12 people |
| A person with an agent, and a contact with the same first name and no agent | 12 pairs |
| A person with one piece of work and a first name nobody else has | 18 or more |
| An adjuster copied on several people's claims | 3 |
| An agent that read the whole inbox once and acted on nobody | 1 |

**Roster sizes**

The roster for a case is the agents that case needs, plus filler taken from the front of one fixed order. So a bigger roster is a smaller one with more added, and every case runs at every size.

Filler never shares a first name or surname with anyone in the core. That is deliberate: it keeps a case's right answer the same at every size. Half the filler uses near-miss names (Mara for Maria) so the list still looks crowded.

The sizes were chosen from a sweep of the original at eight sizes from 10 to 1,280. Accuracy turned out flat, so I use 20, 160 and 640: small, medium and large.

**Two worlds**

| World | Mix of work | Used for |
|---|---|---|
| Dev | Leans to client work, with vendors, colleagues and personal errands | Building and tuning |
| Held-out | Leans to personal and colleague work; different names | One final run |

**Known limits**

- The worlds are synthetic. Many agents share a kind of work and differ in people and details, which is realistic for a broker and is what makes routing hard.
- The size axis measures a longer list, not a more confusing one. More people sharing a name is tested separately (section 7) and only up to a point.
- Every case that uses different wording for a topic also names the person. A message with different wording and no name is where keyword search would miss, and it isn't tested.

---

## 3. The cases

448 in the dev world and 158 in the held-out world. Each is built from a template and a set of phrasings, filled in from the world, so the right answer is known by construction. Each category draws from its own random stream, so changing one never moves another.

### Case format

```json
{
  "id": "same_person_vague-034",
  "category": "same_person_vague",
  "group": "ask",
  "risk": "send",
  "recent_chat": [],
  "message": "nudge Tessa Saldanha, it's been a week",
  "expected": {"outcome": "ask", "options_must_include": ["a_0033", "a_0034"]},
  "required": ["a_0033", "a_0034"],
  "option_terms": {"a_0033": ["radiator", "rental", "repair"], "a_0034": ["baby", "gift", "group", "shower"]},
  "answers": [
    {"kind": "picks", "text": "the rental repair",                 "expected": {"outcome": "route", "agents": ["a_0033"]}},
    {"kind": "new",   "text": "neither, it's about a tax return",  "expected": {"outcome": "create", "person": {"…": "…"}}},
    {"kind": "vague", "text": "the usual one",                     "expected": {"outcome": "ask_or_act", "agents": ["a_0033", "a_0034"]}}
  ]
}
```

`required` is the agents that must be in the roster for the case to mean anything. `option_terms` are the words that show a question named an option.

**Recent chat is stored the way the app stores it,** as the app's own log entries. Versions that record hand-offs also get the hand-off entries, because in real use they would have written them. So every version sees what it would have seen had it been running all along.

### Categories

**Should route to an existing agent**

| Category | Example | Cases |
|---|---|---|
| Clear follow-up | "ask Dalia Eriksen about the jewellery rider" | 22 |
| Pronoun follow-up | "ok send that", after a draft was shown | 16 |
| Follow-up after a gap | "any update from Noor on the expense report?", after chat about someone else | 15 |
| Same person, two pieces of work, topic named | "ask Fiona about the commercial policy audit" | 34 |
| Same first name, topic settles it | "ask Felix about the missed premium payment" (only one Felix has one) | 34 |
| Different wording | "where are we with Vera on the coverage for the trip?" for travel insurance | 18 |
| Shared contact | "ask Greta Rossi where Anton Greenwood's claim stands" | 12 |
| Follow-up on an email alert | "reply to that and say I'll call this afternoon" | 12 |
| Correction | "no, the other Bruno" | 14 |

**Should create a new agent**

| Category | Example | Cases |
|---|---|---|
| Known first name, different person | "email Omar Kaur …" when only Omar Ivanov has an agent | 30 |
| Brand-new person | "email Xavier Appleton with feedback on the team page mockup" | 14 |

**Should ask**

| Category | Example | Cases |
|---|---|---|
| Same person, vague | "nudge Tessa Saldanha, it's been a week" (she has two pieces of work) | 34 |
| Same first name, nothing settles it | "send Kofi a quick note that I'll call tomorrow" (two Kofis) | 34 |
| A person with an agent, or a contact without one | "invite Yara to the open house on the 20th" (two Yaras, one has no agent) | 30 |

**Should need no agent**

| Category | Example | Cases |
|---|---|---|
| Chat or a general question | "thanks!", "what's a deductible?" | 15 |

**Robustness**

| Category | What it checks | Cases |
|---|---|---|
| Two tasks in one message | Both hand-offs right, no question | 14 |
| Topic switch | Chat about one person, then a request about another | 12 |
| Inbox-scanner trap | The agent that read everything isn't used for "email Maria" | 12 |
| Messy text | Lowercase, shorthand and a typo, on five of the categories above | 20 |
| After a question | A question was asked and answered earlier; a follow-up must not ask again | 14 |

**Reported as behaviour, not scored** (section 4)

| Category | Example | Cases |
|---|---|---|
| Same person, new topic | "email Leila Sorensen that the final installment did not go through" (she has a claim agent) | 30 |
| One-off lookup | "find the wifi password someone sent me last year" | 12 |

### Two rules about vague requests

- **"Same person, vague" only uses requests that depend on which work is meant** ("nudge", "chase her on that", "tell her it's approved"). "Let Paloma know I'm out until Monday" needs no question when Paloma has two pieces of work: either agent can send it.
- **"A person with an agent, or a contact" only uses requests that imply no earlier thread** ("send Omar my new phone number"). "Chase Omar on that" could only mean the Omar who has work open.

---

## 4. How answers are checked

### By rule, with no judging model

A turn is reduced to four facts: which existing agents got work, which new agents were created, whether it asked a question, and the text of its reply.

| Expected | Counts as right when |
|---|---|
| Route | The agents contacted are exactly the expected ones. Any extra makes it wrong. |
| Create | No existing agent was contacted, and a new agent was made for the expected person. |
| Ask | Nothing was handed off, and the reply is a question that names every required option. |
| None | No hand-off and no new agent. |

### The same rules for versions that work differently

The original hands off by agent name; the later versions hand off by id.

| Check | By name (V0, V1) | By id (V2 to V5) |
|---|---|---|
| Which agent was contacted | The name is looked up in the roster | The id |
| "Created a new agent" | A hand-off to a name not in the roster | A call to the create tool that was accepted |
| "For the right person" | The person's name is in the new agent's name or instructions | The address on the new agent's record |
| "It asked", "the options were right" | From the text of the reply | The same |

Questions are scored from the reply's text for every version, because the original has nothing else to score.

### What is not scored, and why

Two categories reflect a design choice of mine, not a mistake by any reasonable standard:

- **New work for a person who already has an agent.** The original's prompt tells it to prefer an existing agent that has useful context. Reusing the person's agent is it doing as designed. I prefer one agent per piece of work, and say why in [02-solutions.md](02-solutions.md).
- **One-off lookups.** Reusing a search agent for another search is reasonable.

Both run for every version and are reported as how often each version reuses an existing agent. Neither counts toward any rate.

Two further rules follow from the same reasoning, and were added after reading failures. All five grading changes made after results are listed with their effect in the report, section 7.

- **A correction may also contact the agent that was wrongly used,** to tell it to stop.
- **After a question about which person was meant,** a new agent for the chosen person counts as well as their existing one.

Three categories involve some judgment and are scored: same person vague, a person with an agent or a contact, and correction. `python -m evals.report --categories` prints every category for the original and the chosen version, and the overall rate without the contact category.

### When it asks

| Tracked | Meaning |
|---|---|
| Asked when it should | It asked on a case where asking is right. "Asked" means the reply contains a question mark and nothing was handed off. |
| Asked when it shouldn't | It asked when the answer was clear. This counts as an error. |
| Right after the answer | The turn after the scripted answer did the right thing |

Each "ask" case has up to three scripted answers: the user picks an option, says it's something new, or answers vaguely.

### Every wrong answer gets a type

| Error | Meaning |
|---|---|
| Wrong person | An agent belonging to someone else got the work |
| Wrong agent | The right person, the wrong piece of work |
| Duplicate | A new agent was made when the right one existed |
| Missed ask | It acted when it should have asked. Also records whether it acted on every option, one of them, or something else. |
| Unnecessary ask | It asked when the answer was clear |
| Bad question | It asked, and the question left out an option |
| Extra agents | It contacted more agents than needed |
| Unnecessary agent | It used an agent for chat |
| Failed | An error, or it did nothing |

### Checking the cases

- **A validator** checks every case against its whole world, filler included: every agent exists; no word in a message is also a filler person's name; a case that should route points at exactly the people its category says; a case that should ask has two things to choose between; a case that should create has nothing to reuse; a request that names a topic shares no telling word with the wrong work. It caught one real problem: "cross-town move" contained a filler surname.
- **A random sample of 20 cases** (10 that should ask, 10 others, fixed seed) was read against the world one by one. All 20 held.
- **A checksum file** pins the worlds and cases.

### Checking the grader

- **Unit tests** feed the grader made-up turns with known answers.
- **Four simple strategies** are scored by the same grader:

| Strategy | Right |
|---|---|
| Does what each case expects | 100% |
| Asks every time, naming every option perfectly | 30% |
| Creates a new agent every time | 11% |
| Uses the newest agent every time | 0% |

So the grader can give full marks, and asking every time scores badly.

---

## 5. What gets measured

Per version, per roster size, per category.

- **Outcome:** right; each error type; asked when it should; asked when it shouldn't; right after the answer.
- **Lookup:** whether every agent the case needs was among the candidates. This separates "the lookup missed it" from "it was there and the choice was wrong".
- **Cost:** model calls, tokens and dollars per message. Seconds are recorded but not reported: replayed responses make them meaningless.
- **Variation:** the original was run three times. Its overall rate moved 1.2 points between repeats, so later versions are run once per size and a gap under 2 points is a tie. Small categories (12 to 16 cases) move much more than that and are read with care.

---

## 6. What gets traced

One record per case, saved as a line in the run's results file.

| Section | What's recorded |
|---|---|
| Run | Version, switches, roster size, repeat, code commit |
| Lookup | Every candidate, why it matched, its keyword score; the people the names matched |
| Decision | For V4 and V5: the judge's labels, the step decided for each task, which agents were approved |
| Orchestrator | Every tool call with its arguments and whether it was accepted; the reply |
| Cost | Tokens, dollars and seconds for each model call, and whether it was replayed |
| Grade | Right or wrong, the error type, and the same for the turn after an answer |

---

## 7. The other evals

| Eval | What it does | What it shows |
|---|---|---|
| **Crowded test** | 160 agents, with 10 extra people sharing each first name in the case. The extras are filtered so none has the same kind of work or a telling word in common with the message. | Whether more people with the same name make things worse |
| **Lookup quality** | Runs the app's lookup over every case with no model | Whether the right agent is among the candidates |
| **Ask settings** | Recomputes the decision at each setting from the lookup's scores and the judge's saved labels, with no model | What asking more readily costs in needless questions |
| **Heavy use** | 160 agents, with six more pieces of work for each person in a case and ten namesakes. All six versions, all cases. A question need not list every option there, and corrections are left out. | What happens when the roster is crowded around one person |
| **Stress set** | 40 messier messages written after the main results: short and misspelt names, a surname alone, no name | Where the lookup's name matching breaks |

---

## 8. Rules I held to

1. The cases were committed and tagged before any changed version was run.
2. The held-out world is run once, at the end, with the settings locked.
3. Pass bars were written after the baseline and before any changed version. A missed bar is reported as missed.
4. A needless question is an error.
5. Every version runs on the same cases at the same sizes.
6. When a grading rule changed, it changed for every version, the reason is in the journal, and saved runs were re-graded.
7. Results are reported per category, including where a change made things worse.
8. Every number traces to a results file and a code commit.

---

## 9. What runs on every push

No model call and no API key in any of these.

| Check | Why |
|---|---|
| Unit tests | Records, lookup, both deciders, tool restrictions, grader |
| Checksums | The worlds and cases are the ones that were frozen |
| The case validator | Every case is consistent with its world |
| The reference strategies | The grader still gives them the scores it should |

The full eval is run by hand: it costs money, needs a key, and results vary slightly between runs.
