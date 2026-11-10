# 02 · Options, choices and decisions

What I considered for each cause in [01-codebase.md](01-codebase.md), what I chose, and why. How each choice is built is in [03-technical-design.md](03-technical-design.md). Decisions that depend on an experiment are marked open and get closed in [07-journal.md](07-journal.md).

---

## 1. The design in one page

```
user message
   │
   ▼
1. LOOK UP (code)      recently used agents
                       ∪ agents whose record matches a name or address
                       ∪ agents whose record matches the topic
                       → a handful of candidates
   │
   ▼
2. JUDGE (one small    chat or work?  which tasks?
   model call)         one label per candidate
   │
   ▼
3. DECIDE (code)       one clear match  → route
                       more than one    → ask
                       none             → create (after a duplicate check)
   │
   ▼
4. ORCHESTRATOR        writes the hand-off, the question, or the reply.
                       It can only hand off to agents step 3 approved.
```

Underneath, each agent has **one work record**: who it has dealt with, which threads, which drafts and reminders, and a line on what the work is about. The lookup searches these records. The agent uses its own record as memory.

---

## 2. Options for each problem

The post that introduces OpenPoke names four ideas for this problem. Where each one lands here:

| The post's idea | Here |
|---|---|
| Semantic search over agent descriptions, which it calls the naive solution | Not first. I search a record of what each agent did, by name and keyword, and add embeddings only if the lookup misses too often. |
| A hot cache of recently active agents | Yes: recently used agents are always among the candidates. |
| Archiving dormant agents | Not needed once there's a lookup: an agent that doesn't match never reaches the prompt. |
| Clustering related agents | Not stored. Matching on the person groups a person's agents at lookup time. |

### Too many names in the prompt (causes 1, 3)

| Option | Verdict | Why |
|---|---|---|
| Leave the list, use a model with a bigger context | No | The prompt fits already. The problem is choosing from names, not length. |
| Put a description next to each name, still list everything | No | Better choices, but the prompt still grows with every agent. |
| **Search a record per agent and show only a handful** | **Yes** | The prompt stops growing, and the choice is made on what the agent did. |
| Search by meaning (embeddings) | Not first | Names, addresses and subjects are exact matches, and keyword search needs no extra model or service. I track how often the right agent is among the candidates and add this only if that number is poor. |
| Group agents into a tree (per person, then per piece of work) | No | Matching on the person already groups that person's agents at lookup time, from the records. A stored tree would need maintaining, and would only pay off if the flat search stopped scaling. |

### Picking by name (causes 2, 7)

| Option | Verdict | Why |
|---|---|---|
| Match names loosely | No | Hides the problem. Two similar names can be two different pieces of work. |
| **Give each agent an ID; hand off by ID** | **Yes** | A typo can no longer create an agent, and two agents can no longer share a log. |
| **Separate "create" from "hand off"** | **Yes** | Today one tool does both, so a wrong name creates an agent without anyone deciding to. |
| **Check for a duplicate before creating** | **Yes** | Catches the case where the right agent wasn't chosen and a second one is about to be made. |

### Guessing when it should ask (cause 4)

This is the part I most want evidence on, so each option is built as a version and compared on the same cases. The versions are listed in [05-plan.md](05-plan.md).

| Option | Version | Why it might work or fail |
|---|---|---|
| Rewrite the prompt so it stops forbidding questions | V1 | Necessary, and probably not enough. |
| Tell the orchestrator to ask when more than one agent fits | V3 | The simplest fix. The risk is that a model with a plausible match in front of it takes it. |
| Let code ask when two or more candidates match the person and the message doesn't favour one | V4 | No extra model call. May miss cases where the difference is in meaning, not words. |
| Have a small model label each candidate, and let code count | V5 | Judging each candidate separately doesn't force a single answer. Costs one extra call. |

**Open decision D7:** which becomes the default. If V4 does as well as V5, V4 wins because it's simpler.

Whichever wins, the question is enforced the same way: the hand-off tool only accepts the agents that code approved for that turn. A request like "ask Bob for the invoice and update Alice" can still route Bob while asking about Alice.

### An agent for everything (cause 6)

| Option | Verdict | Why |
|---|---|---|
| **The judging call also says whether this is chat or work** | **Yes** | Chat and general questions never reach an agent. |
| **One-off lookups get a throwaway agent** | **Yes** | It answers and is discarded, so it never crowds the roster. |
| Archive agents that go idle | No | It mattered when every name was in the prompt. With the lookup, an idle agent only reaches the prompt when it matches the message, which is when it's wanted. |

### Each agent's own history (gap 5)

This isn't the overload problem itself, but good reuse makes it worse: the more an agent is reused, the longer its log gets.

| Option | Verdict | Why |
|---|---|---|
| Keep the last N entries of the log | No | Cheap, but the thread ID from entry 3 is gone by entry 20. |
| Have a model summarise the log | No | Summaries drop exact IDs and addresses, which are what the agent needs. |
| **Fixed facts from the work record, plus the last few turns** | **Yes** | The facts come from the agent's own tool calls, so they're exact. No extra model call. |

### No record of hand-offs (cause 5)

Record every hand-off in the orchestrator's history: which agent, and what it was asked. A few lines of code.

---

## 3. The work record

**What goes in.** Only what the agent acted on:

| Recorded | Not recorded |
|---|---|
| People it wrote to, with their addresses | People who merely appeared in search results |
| Threads it replied on or drafted to, with subjects | Threads it only read |
| Drafts and reminders it created | |
| The person named in the hand-off | |
| The search queries it ran | The results of those searches |

The right-hand column matters. An agent that once scanned the whole inbox would otherwise "know" everyone and match every request.

**Where facts come from.** The arguments of the agent's own tool calls. When it replies on a thread, the call carries the thread ID and the recipient's address. Only the one-line summary is written by a model.

**Who is who.** A person is identified by email address, not by name. Two people called Alice are two people.

---

## 4. When the action is risky

Sending something to the wrong person is worse than running an unnecessary search. So the decision step asks more readily when the request would send, and less readily when it would only read.

This is one setting. Moving it trades wrong sends against unnecessary questions, and I plot that trade-off instead of reporting one number.

Two guards sit behind it, in case routing still goes wrong:
- Nothing is sent unless its exact text was shown to the user and they approved it.
- An agent can only send to people already on its record, or the person named in the hand-off.

---

## 5. Things I considered and dropped

| Idea | Why I dropped it |
|---|---|
| A model call to "understand" the request before the lookup | Code can match names and include recent agents without it. I'd add it only if the lookup misses candidates. |
| Fixed fields on the record for the kind of work (claim, renewal, reference number) | Many requests aren't about a tracked piece of work, and most don't mention a reference. It would also shape the system to my own test world. |
| One agent per person | One agent would hold unrelated work, which is the mixed-context problem again. |
| No lasting agents at all; rebuild context each time | Throws away the one thing that works well: an agent that already has the thread. |
| Hiding the hand-off tool whenever a question is needed | It would block the clear half of a two-part request. Restricting by agent ID does the same job without that. |
| A live contacts search during lookup | Adds a network call to every message, and old contacts with a common first name would cause needless questions. |
| Routing incoming email straight to the agent that owns the thread | A separate problem. The orchestrator still has to decide what to do with the email. Written up as a next step. |
| A simulated month of use, starting from no agents, to watch the roster grow | It needs a fake message stream, fake sub-agents and a fake clock all working together, and the main eval already counts duplicates and wrong reuse at each roster size. Written up as a next step. |
| A hosted experiment tracker | A results file per run, a summary table and a journal do the job and need nothing installed. |

---

## 6. Decision log

| # | Decision | Alternatives | Why | Status |
|---|---|---|---|---|
| D1 | Measure the original before changing anything | Fix first, measure after | Without a baseline there's nothing to compare to | Decided |
| D2 | Run everything on one small model | A larger model for the orchestrator | The original and every version run on the same model, and thousands of cases stay affordable | Decided |
| D3 | One work record per agent, serving both lookup and memory | A separate card and memory | One thing to keep up to date | Decided |
| D4 | Facts on the record come from tool calls | Extract them from text | Exact, and nothing to guess | Decided |
| D5 | Lookup is code: keyword search plus name matching | A model step first; embeddings | Simpler and free; revisit if candidates get missed | Decided, revisit on evidence |
| D6 | Hand off by ID, restricted to approved agents | Hide the tool on an "ask" turn | Hiding it would block the clear half of a two-part request | Decided |
| D7 | Who decides when to ask | V3, V4, V5 | To be settled by the experiment | **Open** |
| D8 | Which roster sizes to report | Fixed round numbers | Chosen from where the original starts to fail | **Open** |
| D9 | Grade by rule, with no judging model | A model as grader | Routing has a right answer | Decided |
| D10 | A second world, used once, for the final result | One world, split | Shows the fix wasn't tuned to the test | Decided |
| D11 | Store records in SQLite | A JSON file with a lock | The app already uses SQLite; writes are safe; full-text search is built in | Decided |
| D12 | Unrelated fixes go in the same pull request, as `gap:` commits | A second pull request | One place to review | Decided |
