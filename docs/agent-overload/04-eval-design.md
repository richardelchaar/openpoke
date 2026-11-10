# 04 · Eval design

How I test the router: the worlds, the cases, how answers are checked, what gets traced, and the rules that keep it honest.

---

## 1. What one eval run does

1. Build a fake world at a chosen roster size (the number of agents that already exist).
2. For each case: load the recent chat, send the message through the **real orchestrator code**, with the version switches set.
3. Capture **everything the orchestrator does in its first response**: every hand-off, every new agent, any question, any direct reply. Sub-agents don't run; Gmail is fake.
4. If it asked a question, send the case's scripted answer and capture the next response too.
5. Grade against the expected outcome. Write a trace.

One run = one version × one roster size × one set of cases × one repeat.

---

## 2. The worlds

A generator script builds each world from a seed, so it's reproducible.

**What a world contains**
- **People:** name, email address, and who they are to the user. Some share a first name. Some share a surname.
- **Pieces of work:** each has an agent with a work record and a short history log.
- **Contacts with no agent yet:** people the user knows but hasn't worked with through the assistant.
- **Standing agents:** reminders, a daily digest.
- **Distractors** to fill the roster to size: half are look-alikes (same first names, overlapping topics), half are unrelated.

**How a world is generated**

The facts come from code and the wording comes from the model.

1. People are drawn from name lists, with deliberate clashes.
2. Each person gets one to three pieces of work from a catalogue of about 40 kinds.
3. Each kind has a storyline: the ordered steps a real thread would follow, with slots for names, dates and details.
4. The generator plays the first few steps of each storyline and writes them in the app's own log format. The thread, the people and the dates carry through, so each agent's history is one consistent story.
5. The model rewrites the instructions and replies so they don't all read alike. A validator then checks the names, addresses and thread IDs survived.
6. **Each agent is named by replaying its first task through the original orchestrator.** The original picks agents by name only, so it should be tested on names it would really have produced, not on tidy ones I wrote.

**Roster sizes**

I choose them from my own runs. I run the original at doubling sizes on a small set of cases, then pick three or four: one where it's still fine, one where it clearly struggles, and one or two between. Each size maps to real use: the original creates an agent for nearly every task and never removes one.

**Known limit:** with about 40 kinds of work, many agents share a kind and differ in people and details. That's realistic and is what makes routing hard, but the worlds are synthetic.

**Two worlds**

| World | Domain | Used for |
|---|---|---|
| Dev | A broker's inbox that isn't only insurance: client work (claims, renewals, quotes) mixed with vendors, colleagues, newsletters and personal errands | Building and tuning |
| Held-out | A different mix of people and work | One final run, never looked at before |

**Traps built into both worlds**
- Two people with the same first name.
- One person with two open pieces of work.
- A contact who appears across many people's work (an adjuster, an assistant).
- Two people on one account with the same surname.
- A person in the contacts with the same first name as someone who has an agent.
- An agent that scanned the whole inbox once.
- A noreply sender.

---

## 3. The cases

### Where cases come from

| Source | Share | How the right answer is known |
|---|---|---|
| Templates filled in from the world | ~75% | By construction: the generator knows which agent owns which work |
| Written case by case to cover the traps | ~25% | The answer is stated when the case is written, then confirmed by the validator |

### Case format

```json
{
  "id": "vague-014",
  "category": "same_person_vague",
  "risk": "send",
  "recent_chat": [],
  "message": "update alice on where things stand",
  "expected": {"outcome": "ask", "options_must_include": ["a_044", "a_045"]},
  "option_terms": {"a_044": ["claim"], "a_045": ["boat", "quote"]},
  "answers": [
    {"kind": "picks",  "text": "the boat quote",                       "expected": {"outcome": "route", "agents": ["a_045"]}},
    {"kind": "new",    "text": "neither, it's about her home policy",  "expected": {"outcome": "create", "person": "alice.park@…"}},
    {"kind": "vague",  "text": "the usual one",                        "expected": {"outcome": "ask_or_act"}}
  ]
}
```

`outcome` is one of: `route` (to a set of agents), `create` (a new agent for a named person), `ask`, `none` (answer directly, no agent).

**Recent chat is stored the way the app stores it.** Each case's earlier turns are written as the app's own log entries, including the result lines agents send back. Versions that record hand-offs also get the hand-off entries, because in real use they would have written them. So every version sees exactly what it would have seen had it been running all along.

### Categories

**Should route to an existing agent**

| # | Category | Example | Must also |
|---|---|---|---|
| 1 | Clear follow-up | "tell Bob Tran the renewal date moved to the 14th" | Not ask |
| 2 | Pronoun follow-up | "reply to her and say yes" | Use the recent chat |
| 3 | Follow-up after a gap | "any news on the police report?" (nothing in recent chat) | |
| 4 | Same person, two pieces of work, topic named | "ask Alice about the boat quote" | Pick the right one of her two |
| 5 | Same first name, topic settles it | "chase Alice on the police report" (only one Alice has a claim) | Not ask |
| 6 | Different wording | "the fender-bender" when the record says "auto claim" | |
| 7 | Shared contact | "email the adjuster about Park" | Route by the client, not the adjuster |
| 8 | Follow-up on an email alert | "reply to that" after a watcher notification | Go to the agent that owns it |
| 9 | Correction | "no, the other Alice" | Switch, and not ask again |

**Should create a new agent**

| # | Category | Example | Must also |
|---|---|---|---|
| 10 | Same person, new topic | "Alice Park also wants a quote for her boat" | Not reuse her claim agent |
| 11 | Known first name, different person | "email Alice Wu" when only Alice Park has an agent | Not reuse |
| 12 | Brand-new person and work | "email Dan Ortiz about the audit" | |

**Should ask**

| # | Category | Example |
|---|---|---|
| 13 | Same person, vague | "update Alice" when she has two pieces of work |
| 14 | Same first name, nothing settles it | "email Alice and ask if she got the form" |
| 15 | Name matches an agent and a contact without one | "text Sam the address" |

**Should not use a lasting agent**

| # | Category | Example | Expected |
|---|---|---|---|
| 16 | Chat or general question | "thanks!" / "what's a deductible?" | Answer directly |
| 17 | One-off lookup | "any newsletters today?" | A throwaway agent, not an existing one |

**Robustness**

| # | Category | What it checks |
|---|---|---|
| 18 | Two tasks in one message | Both hand-offs correct; no question |
| 19 | Topic switch mid-chat | Follows the latest message |
| 20 | Inbox-scanner trap | The agent that read everything isn't picked for "email Alice" |
| 21 | Messy text | Typos, lowercase, text-message style versions of the above |
| 22 | After a question | The recent chat already holds a question and the user's answer; a later follow-up must route without asking again |

### Sizes

- **Dev:** ~400 cases. At least 30 in every category the fix targets (4, 5, 10, 11, 13, 14, 15). About 60% of all cases are clear, because most real requests are.
- **Held-out:** ~150 cases from the second world, run at the same roster sizes as the dev runs.
- **Repeats:** 3 per run.
- **Reporting:** the 22 categories are reported in their five groups (route, create, ask, no lasting agent, robustness), with the per-category table in an appendix.

---

## 4. How answers are checked

### Grading is by rule, with no judging model

| Expected | Counts as right when |
|---|---|
| `route` | The set of agents contacted equals the expected set. Any extra agent makes it wrong. |
| `create` | No existing agent was contacted, and the new agent's record names the expected person (by address). |
| `ask` | Nothing was handed off that turn, and the options offered include every required one. Then the turn after the scripted answer is graded as `route` or `create`. |
| `none` | No hand-off and no new lasting agent. |

### Grading versions that work differently

The right answers and the rules are the same for every version. What differs is how the grader reads what a version did, because the original hands off by name and the later versions hand off by ID:

| Check | Versions that use names (V0, V1) | Versions that use IDs (V2 to V5) |
|---|---|---|
| Which agent was contacted | The name is looked up in the world's roster | The ID |
| "Created a new agent" | A hand-off to a name that isn't on the roster | A call to the create tool |
| "For the right person" | The person's name appears in the new agent's name or instructions | The address on the new agent's record |
| "It asked" | No hand-off, and the reply to the user is a question | The same |
| "The options were right" | The reply mentions each required option, checked with the case's `option_terms` | The same |
| One-off lookup (category 17) | Right if it creates a new agent and doesn't reuse one | Right if it creates a throwaway agent |

**Questions are scored the same way for every version:** from the text of the reply. V4 and V5 also record the option IDs they offered, which I use to diagnose failures and never to score, because the original has nothing equivalent.

**Limit:** checking a question by its words is crude. A question that names the right options in unusual words would be marked wrong. I count how often this happens in the sample I review.

### What's tracked when it asks

| Tracked | Meaning |
|---|---|
| Asked when needed | It asked on a case where asking is right |
| Good question | The options included the right one, plus "something new" |
| Right after the answer | The next turn went to the right agent or created the right one |
| Asked again | It asked a second question (should be rare) |
| Turns to done | How many messages until the work was handed off correctly |

Each "ask" case is run with three kinds of scripted answer:
- **Picks an option:** "the boat quote" → route to that agent.
- **Says it's something new:** "neither, it's about her home policy" → create a new agent.
- **Answers vaguely:** "the usual one" → it may ask once more, then must act.

### Every wrong answer gets a type

| Error type | Meaning |
|---|---|
| Wrong agent | Right person, wrong piece of work |
| **Wrong person** | An agent belonging to someone else |
| Duplicate | Created a new agent when one existed |
| Wrong reuse | Reused an agent when it should have created one |
| Missed ask | Acted when it should have asked |
| Unnecessary ask | Asked when the answer was clear |
| Bad question | Asked, but the right option wasn't offered |
| Extra agents | Contacted more agents than needed |
| Unnecessary agent | Used an agent when none was needed |
| Failed | Error, empty reply, or invalid tool call |

### Checking the cases themselves

- **A validator script** checks every case against the world: the expected agent exists; an "ask" case really has two or more plausible targets (agents, or a person with an agent and one without); a "clear" case really has only one.
- **A second model votes on every label.** Where it disagrees, the case is re-examined against the world and either fixed or removed. The counts (checked, fixed, removed) go in the report.
- **I review 20 cases myself,** picked at random by a script: 10 "should ask" cases and 10 from the other categories. The report states how many were changed.

### Checking the grader

- **Unit tests** feed the grader scripted model outputs with known right answers.
- **Simple reference runs,** so the numbers have a floor and a ceiling:

| Reference | Expected result |
|---|---|
| Always gives the expected answer | 100% (proves the grader works) |
| Always picks the most recently used agent | A floor for routing |
| Always creates a new agent | Shows the duplicate rate at its worst |
| Always asks | Zero wrong sends, maximum unnecessary questions (one end of the trade-off curve) |

If "always ask" scored well, the scoring would be broken. It must not.

---

## 5. What gets measured

Reported per version, per roster size, per category. Never as one blended number only.

**Outcome rates**
- Right
- Each error type above
- Asked when needed / asked when not needed
- Right after the answer (for questions)

**Where the failure happened**
- **Lookup hit rate:** was the right agent among the candidates? This separates "lookup missed it" from "it was there and the decision was wrong".

**Cost**
- Model calls per message
- Tokens in and out per message
- Time per message (median and slowest 10%)
- Dollars per message

**Statistics**
- A range on every rate.
- Versions compared on the same cases, pair by pair.
- The spread across the 3 repeats.

---

## 6. What gets traced

One trace per case, saved as a line in the run's results file.

| Section | What's recorded |
|---|---|
| Run | Version switches, model names, roster size, world seed, code commit, time, repeat number |
| Input | Case ID, the message, the recent chat |
| Lookup | Every candidate, why it matched (name, address, topic words, recently used), its score, and whether the expected agent was among them |
| Judging | The exact prompt, the raw output, and the verdict and reason for each candidate |
| Decision | Which rule fired (one match → route; two → ask; none → create) |
| Orchestrator | Prompt size in tokens, the raw response, every tool call with its arguments |
| Question | The question text, the options, the scripted answer, and what happened next |
| Grade | Right or wrong, and the error type |
| Cost | Tokens, time and dollars for each model call |
| Problems | Errors and retries |

**The live app writes the same trace for every real message,** so a real message that went wrong can be read the same way as a failed case.

**Recorded responses:** every model response is saved, keyed by the exact request. A re-run with the same inputs replays for free and gives the same numbers, so anyone can rebuild the results page without an API key.

---

## 7. The other evals

Routing accuracy is the main one. These are smaller and separate.

| Eval | What it does | What it shows |
|---|---|---|
| **Trade-off curve** | Re-applies the decision rule at each "how readily it asks" setting to the saved search scores and judge labels. The decision is code, so this needs no new model runs. | Wrong-person sends against unnecessary questions |
| **Agent memory** | About 20 agents with long histories, each given a task that depends on something old. Run with the whole log, and with the work record plus the last few turns. | Whether the tool call uses the right thread ID and address, and the tokens per call |
| **End to end** | ~5 scripted stories with real sub-agents and fake Gmail | The right email, to the right address, on the right thread. These are also the live demo. |
| **Send approval** | Tries to send, reply and forward without approval; includes emails that tell the agent to forward things | Nothing leaves without approval |

---

## 8. Rules that keep it honest

1. Cases are committed before any fix code, with a checksum file for the worlds and cases.
2. The held-out world is run once, at the end, with the final settings.
3. Pass bars are written down after the baseline and before any fixed version is run. A missed bar is reported as missed.
4. Unnecessary questions count against the system, and a needed question only counts as right if the turn after the answer is right too.
5. Every version runs on the same cases. Every version that uses the lookup gets the same candidates from it.
6. Results are reported per category, including where the fix loses.
7. Every number in the report traces to a results file and a code commit.

---

## 9. What runs in CI

| Runs on every push | Why |
|---|---|
| Unit tests (decision rules, lookup, grader, send approval, record store) | Fast, free, no model |
| The case validator | Catches a broken case or world |
| A small smoke eval (~30 cases) replayed from recorded responses | Free and repeatable; fails if routing results change unexpectedly |

| Run by hand, not in CI | Why |
|---|---|
| The full eval with live model calls | Costs money, needs a key, and results vary slightly between runs |
| The held-out run | Run once only |

## 10. Folder layout

```
evals/
  worlds/        generator + the two world seeds
  cases/         dev.jsonl, heldout.jsonl, validator
  run.py         runs one version at one size
  grade.py       the rules in section 4
  report.py      builds the summary table and the results page
  references.py  the simple reference runs
  recorded/      saved model responses
  results/       one file per run, plus runs.csv (one row per run)
tests/           unit tests, no model calls
docs/agent-overload/07-journal.md   the journal, linking to results files
```
