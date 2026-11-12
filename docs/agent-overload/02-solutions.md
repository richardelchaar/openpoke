# 02 · Options, choices and decisions

What I considered for each cause in [01-codebase.md](01-codebase.md), what I chose, and why. Where a choice was settled by an experiment, the entry says which; the experiments are in [07-journal.md](07-journal.md). How each choice is built is in [03-technical-design.md](03-technical-design.md).

---

## 1. The design in one page

```
user message
   │
   ▼
1. LOOK UP (code)      recently used agents
                       ∪ agents that have dealt with anyone the message names
                       ∪ agents whose record shares words with the message
                       ∪ if the message names nobody: the people in the last thing shown
                       → a handful of candidates, and the contacts the names matched
   │
   ▼
2. ORCHESTRATOR        sees the candidates, each with who it has dealt with and what
                       its work is about. It hands off by agent id, creates a new agent
                       with a separate tool, or asks the user.
```

Underneath, each agent has **one work record**: who it has dealt with, on which threads, what it searched for, and a line on what the work is about. The lookup searches these records.

I planned a third step between those two, where code or a second model call decides whether to route, create or ask, and the orchestrator is only allowed to do that. I built it two ways and measured both. Neither beat letting the orchestrator decide from the candidates, so the step is switched off (section 3).

---

## 2. Options for each problem

The post that introduces OpenPoke names four ideas for this problem. Where each one lands here:

| The post's idea | Here |
|---|---|
| Semantic search over agent descriptions, which it calls the naive solution | Search is most of the answer, and I say so. Keyword search over the records alone finds the agents a case needs 88% of the time. What I search is a record of what each agent did, not a description, and three more sources take it to 100%. I did not add embeddings: nothing I tested needed them, and one thing I did not test would (section 5). |
| A hot cache of recently active agents | Yes: the agents in the last few hand-offs are always among the candidates. |
| Archiving dormant agents | Not needed once there is a lookup: an agent that doesn't match never reaches the prompt. |
| Clustering related agents | Not stored. Matching on the person groups a person's agents at lookup time. |

### Too many names in the prompt (causes 1, 3)

| Option | Verdict | Why |
|---|---|---|
| Leave the list, use a model with a bigger context | No | The prompt fits already. On the model I used, accuracy doesn't fall as the list grows; cost does. |
| Put a description next to each name, still list everything | No | The prompt still grows with every agent. |
| Search a one-line description per agent and show only a handful | Tested, not chosen | Built as V2d and run on the same cases: 86% right against 97% with the work record. It has no way to see a person with no agent, or a go-between copied on someone else's work, and it makes more duplicates. |
| **Search a record per agent and show only a handful** | **Yes** | The prompt stops growing (11,100 tokens a message at 640 agents against 40,100), and the choice is made on what the agent did. |
| Search by meaning (embeddings) | Not built | Names and addresses are exact matches, and the name match found the right agent in every tested case where wording differed. |
| Group agents into a tree (per person, then per piece of work) | No | Matching on the person already groups that person's agents at lookup time. A stored tree would need maintaining. |

### Picking by name (causes 2, 7)

| Option | Verdict | Why |
|---|---|---|
| Match names loosely | No | Hides the problem. Two similar names can be two different pieces of work. |
| **Give each agent an id; hand off by id** | **Yes** | A typo can no longer create an agent, and two agents can no longer share a log. |
| **Separate "create" from "hand off"** | **Yes** | In the original one tool does both, so a wrong name creates an agent without anyone deciding to. |
| **Check for a duplicate before creating** | **Yes** | Catches the case where the right agent wasn't chosen and a second one is about to be made. |

### Guessing when it should ask (cause 4)

This is the part I most wanted evidence on, so each option was built as a version and run on the same cases.

| Option | Version | What happened |
|---|---|---|
| Rewrite the prompt so it stops forbidding questions | V1 | Asked more (about 66% of the time it should, up from about 38%) and was no better overall, because with only names to go on it created far more duplicates. |
| Show the candidates and their records; leave the choice to the orchestrator | V2 | Asked every time it should, and needlessly 3 to 4% of the time. **Chosen.** |
| V2, plus a firm rule to ask when more than one candidate could fit | V3 | No more correct questions, two to three times the needless ones. |
| Code asks when the candidates' keyword scores don't favour one | V4 | Can't read meaning, so it asks whenever the words don't overlap. The most needless questions of all. |
| A model call labels each candidate, and code counts the labels | V5 | Tied with V2 within one to two points, at the cost of an extra model call. Better only on the turn after the user answers. |

**Decision D7:** V2, which is configuration 3 in the report. The problem was never that the model wouldn't ask. The original gave it nothing to go on: a list of names, and no sign that a second person with that name existed. Given the candidates, it asks without being forced, and forcing it only adds questions.

### An agent for everything (cause 6)

| Option | Verdict | Why |
|---|---|---|
| **The prompt says chat and general questions need no agent** | **Yes** | Every version, including the original, already answers chat directly in the tests. |
| **One-off lookups get a throwaway agent** | **Yes** | It is marked as throwaway when created and left out of every later lookup. |
| Archive agents that go idle | No | It mattered when every name was in the prompt. With the lookup, an idle agent only reaches the prompt when it matches the message. |

### No record of hand-offs (cause 5)

Every hand-off is written to the conversation log: which agent, and what it was asked. The lookup reads the last few to know which agents were used recently.

---

## 3. What I built and switched off

Both deciders are in the code, behind a switch, so the results can be reproduced. Neither is on by default.

| | What it does | Why it is off |
|---|---|---|
| Code rule | Groups the people a message names. If the keyword scores of a group's options don't favour one by a margin, it asks. | 85 to 91% right against 95 to 97% for V2. Changing the margin from 0 to 1 moved needless questions from 8% to 14% and added no correct ones. |
| Judge | One model call labels each candidate exact, plausible, same person other work, or unrelated. Code counts. | 93 to 94% right, a tie with V2, for one more model call per message. Its strict, balanced and loose settings differed by one point. |

Reading the judge's failures showed one bug and two things worth tuning: it asked "which one?" with a single option; it treated candidates that only shared a topic as alternatives; and it was too cautious in a few plain cases. I changed all three and then took the changes back out, because I didn't have a measured run with them. They are in commit `925a9bf` and are the first thing I'd try next.

---

## 4. The work record

**What goes in.** Only what the agent acted on:

| Recorded | Not recorded |
|---|---|
| People it wrote to, with their addresses | People who merely appeared in search results |
| Threads it replied on or drafted to, with subjects | Threads it only read |
| Reminders it created | |
| The person named when it was created | |
| The search queries it ran | The results of those searches |

The right-hand column matters. An agent that once scanned the whole inbox would otherwise "know" everyone and match every request.

**Where facts come from.** The arguments of the agent's own tool calls. When it replies on a thread, the call carries the thread id and the recipient's address.

**Who is who.** A person is identified by email address, not by name. Two people called Omar are two people.

---

## 5. One agent per piece of work: a choice, not a finding

The original's prompt tells it to prefer an existing agent "if it contains useful context", even when the name is unrelated. So when a person who has a claim agent brings up a payment problem, the original puts it in the claim agent about 40% of the time, and that is it doing as designed.

I chose the opposite: new work gets a new agent, including for a person who already has one. The reason is what happens later. If a claim and a payment problem share an agent, "follow up with Leila" has two possible threads inside that agent, and nothing outside it can tell them apart. Separate agents keep that question where it can be asked.

That is an argument, not a measurement. The eval reports how often each version reuses an agent in that situation, and counts neither answer as right or wrong.

---

## 6. Things I considered and dropped

| Idea | Why I dropped it |
|---|---|
| A model call to "understand" the request before the lookup | Code matches names and includes recent agents without it, and the lookup found the right agent in every tested case. |
| Fixed fields on the record for the kind of work (claim, renewal, reference number) | Many requests aren't about a tracked piece of work. It would also shape the system to my own test world. |
| One agent per person | One agent would hold unrelated work, which is the mixed-context problem again. |
| No lasting agents at all; rebuild context each time | Throws away the one thing that works well: an agent that already has the thread. |
| A setting for how readily to ask before a send | Built for the judge and measured. It moved the result by one point. |
| A live contacts search during lookup | Adds a network call to every message. |
| A simulated month of use, starting from no agents | It needs a fake message stream, fake sub-agents and a fake clock all working together. Duplicates are counted at each roster size instead. |
| Routing incoming email straight to the agent that owns the thread | A separate problem. The orchestrator still has to decide what to do with the email. |
| A hosted experiment tracker | A results file per run, a summary table and a journal do the job and need nothing installed. |

---

## 7. Decision log

| # | Decision | Alternatives | Why | Settled by |
|---|---|---|---|---|
| D1 | Measure the original before changing anything | Fix first, measure after | Without a baseline there's nothing to compare to | Up front |
| D2 | Run everything on one small model | A larger model for the orchestrator | The original and every version run on the same model | Up front |
| D3 | One work record per agent | A separate card and memory | One thing to keep up to date | Up front |
| D4 | Facts on the record come from tool calls | Extract them from text | Exact, and nothing to guess | Up front |
| D5 | Lookup is code: name matching, recent hand-offs, keyword search | A model step first; embeddings | Found the needed agents in 100% of tested cases | E6 |
| D6 | Hand off by id; create is its own tool | One tool that does both | A wrong name can no longer create an agent | Up front |
| D7 | The orchestrator decides whether to ask, from the candidates | A prompt rule, a code rule, a second model call | Best or tied on the overall rate at every roster size, and the simplest. The second model call is better on the turn after the user answers. | E4, heavy use |
| D8 | Roster sizes 20, 160 and 640, plus a heavy-use roster | Fixed round numbers | Size alone was flat in a sweep to 1,280; crowding around a person is what changes behaviour | E1, heavy use |
| D9 | Grade by rule, with no judging model | A model as grader | Routing has a right answer | Up front |
| D10 | A second world, used once, for the final result | One world, split | Shows the result isn't tied to the names and mix it was tuned on | Up front |
| D11 | Store records in SQLite | A JSON file with a lock | The app already uses it; writes are safe; full-text search is built in | Up front |
| D12 | Unrelated fixes go in the same pull request | A second pull request | One place to review | Up front |
| D14 | A work record and contacts, over a one-line description per agent | A title and a description only | 9 to 11 points better on the same cases; 1 to 4 points leaving out the messages about a contact with no agent | V2d |
| D13 | One agent per piece of work | Reuse the person's agent, as the original does | Keeps a later vague request askable | A choice; reported, not scored |
