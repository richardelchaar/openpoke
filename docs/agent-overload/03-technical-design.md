# 03 · Technical design

What I picked for each part and why.

Two numbers are tuned on the dev world: how many candidates the lookup returns, and the margin in the code rule (V4). Both live in code, so trying other values re-uses saved results and needs no new model runs. Every other number below is a stated default, not an optimised one.

---

## 1. The flow

```
message
   │
   ▼
1. lookup      code, SQLite       → up to ~10 candidate agents
2. judge       one model call     → chat or work; one label per candidate
3. decide      code               → route / ask / create, per task
   │
   ▼
orchestrator   existing loop      → can hand off only to approved agents
```

The three steps run at the top of the orchestrator's turn (`agents/interaction_agent/runtime.py:65-97`), before its existing loop. Every step writes to one trace record per message.

---

## 2. Storage

| Choice | Why |
|---|---|
| **SQLite**, in `data/agents.db` | The app already uses it for reminders. Writes are safe, which removes the roster's lose-everything failure. Search is built in. No new dependency. |
| **Every agent has an ID** | A typo can't create an agent, and two agents can't share a log. The name becomes a display title. |
| **One work record per agent:** people, threads, drafts, reminders, past search queries, a one-line summary | It serves both the lookup and the agent's own memory, so there's one thing to keep current. |
| **A person is an email address** | Two people called Alice are two people. |
| **A cap on each kind of fact** | A long-lived agent can't grow without limit. |
| **One setting for the data directory** | Seven modules each compute their own path today. The eval needs to point the app at a temporary world. |

---

## 3. Keeping the record current

| Choice | Why |
|---|---|
| **Facts come from the arguments of the agent's tool calls** | A reply already carries the exact thread ID and address. Nothing is extracted from text. |
| **Only what the agent acted on:** drafts, sends, replies, forwards, reminders | An agent that scanned the whole inbox must not end up matching every name. Searches record the query, never the results. |
| **The person named in the hand-off is added too** | So an agent asked to find someone's email is linked to them before it does anything. |
| **A model writes only the one-line summary** | It's the one thing tool calls can't give: what the work is about. |

---

## 4. Lookup

No model call. It takes the union of three sources:

| Source | How | Why |
|---|---|---|
| **Recently used** | The agents in the last 3 hand-offs, and any agent with a draft waiting for the user's answer | This is what makes "reply to her" and "send it" work without resolving the pronoun. |
| **People** | Names and addresses in the message, matched against the people on records and a local contacts table | Most requests name someone. It returns every agent for every matching person, and tells the next step when a name matches more than one person. |
| **Topic** | Keyword search over each record's title, summary, subjects, people and past queries, ranked by BM25 | Built into SQLite. Rare words count more, and word endings are ignored, so "renewals" finds "renewal". |

- **Combined and capped at about 10.** Recent ones first, then people matches ordered by keyword score, then topic matches.
- **Each candidate carries why it matched,** which goes into the trace.
- **The contacts table is local.** A live contacts search would add a network call to every message, and old contacts with a common first name would cause needless questions.

**Known weakness:** keyword search can't match different wording, such as "the fender-bender" for "auto claim". The eval has a category for this and tracks how often the right agent is among the candidates. If that rate is poor, I add an embedding of each summary as a fourth source. I'm not adding it without that evidence.

---

## 5. The judge call

| Choice | Why |
|---|---|
| **One call per message,** skipped when there are no candidates | One extra call is the whole cost of this design. |
| **It returns three things:** chat or work; the tasks in the message; a label for each candidate | One call covers "does this need an agent at all", multi-part requests, and the judgment. |
| **Output forced into a fixed JSON shape,** temperature 0 | Code reads it, so it has to be parseable and repeatable. |
| **Four labels:** exact / plausible / same person, other work / unrelated | "It's Alice, and it isn't her claim" is an answer, not a doubt, so it gets its own label and never triggers a question. Only "plausible" does. |
| **If the output is invalid:** retry once, then fall back to letting the orchestrator pick from the candidates | A failed helper call must not block the user. |

---

## 6. The decision

Code, applied to each task:

```python
if exactly one "exact" and nothing blocks it:   route to it
elif two or more "exact", or any "plausible":   ask, with those as options
elif the name matches several people:           ask which person
else:                                           create (after a duplicate check)
```

**What "blocks" means** is the risk setting:

| Setting | A "plausible" candidate stops a route to the one "exact" match when… |
|---|---|
| strict | always |
| balanced (default) | the task would send something |
| loose | never |

A wrong send is worse than a wrong search, so the default asks more readily before sending. These three settings are the points on the trade-off curve.

**The version with no judge call (V4)** uses the lookup's output directly. It asks which person when a name matches more than one person and the message doesn't give a full name. It asks which piece of work when two or more candidates match the person and their keyword scores are too close to call. Otherwise the orchestrator picks from the candidates. "Too close" is a margin, tried at a few values. If this does as well as the judge, the judge call goes.

---

## 7. The orchestrator

| Choice | Why |
|---|---|
| **It sees a handful of short views, not every name** | The prompt stops growing with the roster. |
| **Hand-off takes an agent ID, limited to the ones approved this turn** | It can't skip the question by guessing. |
| **Restricted by ID, not hidden** | "Ask Bob for the invoice and update Alice" still gets Bob done while asking about Alice. |
| **A separate "create" tool** | Today one tool does both, so a wrong name creates an agent without anyone deciding to (`tools.py:116-120`). |
| **Every hand-off is written to the conversation history** | Today the orchestrator has no memory of who it sent what to. |
| **One question, with options, always including "something new"** | Easy to answer in a few words. At most one follow-up, then it acts and says what it chose. |
| **Prompt rewrite** | The original forbids asking, pushes parallel spawning, and names a tool that doesn't exist. |

---

## 8. Roster and memory

| Choice | Why |
|---|---|
| **Duplicate check on create:** same person and half the words in common → refuse and point at the existing agent | Stops a second agent for work that already has one. The orchestrator can override. |
| **Throwaway agents** for one-off lookups | They answer and are discarded, so they never enter the lookup. |
| **No archiving** | An idle agent only reaches the prompt when it matches the message, so there's nothing for archiving to do. |
| **An agent's memory = its record's facts + its last 5 turns** | Exact IDs however old, and no extra model call. Keeping the last N log entries loses early IDs; a model summary loses exact ones. |
| **The log is stored in full** | Today it's cut to 500 characters as it's written, so the information is gone for good. |

---

## 9. Safety

| Choice | Why |
|---|---|
| **Reply becomes a draft on the thread** | Today it sends immediately (`tools/gmail.py:404-428`). The existing draft tool already accepts a thread. |
| **A draft can be sent only if its exact text was shown to the user and approved** | Today only a prompt line asks for confirmation. |
| **Approval is possible only on a turn the user started** | An email that says "forward this to…" can't trigger a send. |
| **An agent can send only to people on its record, or the person named in the hand-off** | If routing does go wrong, it's caught before anything leaves. |

**Stated limit:** the orchestrator still reads the user's "yes, send it". A button in the UI would remove that last judgment.

---

## 10. Reliability

| Choice | Why |
|---|---|
| **Models set by config** | They're hardcoded today, to a model that's no longer served. |
| **Three attempts with increasing waits** on failed model calls | One failure ends the turn today. |
| **One run per agent at a time** | A reminder and a user request can start the same agent together today. |
| **A message when the 8-step limit is hit** | Today it raises an error and the user gets nothing. |

---

## 11. Traces

One record per message: the candidates and why each matched, the judge's output, the rule that fired, what the orchestrator did, time and tokens.

The eval writes the same format, so a real message that went wrong can be read the same way as a failed test case.

---

## 12. Cost

Estimated from prompt sizes; the eval measures the real figures.

| | Original | New |
|---|---|---|
| Model calls before the orchestrator acts | 0 | 1 (the judge call) |
| Orchestrator prompt | ~2,600 tokens + ~14 per agent | ~2,600 + ~600 for the candidates |
| At 1,000 agents | ~17,000 tokens | ~3,200 + ~1,200 for the judge |

Past a few dozen agents the new path should cost less per message despite the extra call.

---

## 13. Open technical choices

| Choice | Settled by |
|---|---|
| Code rule (V4) or judge (V5) as the default | The decider experiment |
| Whether to add embeddings to the lookup | How often the right agent is among the candidates |
| The candidate count and the V4 margin | Tried at a few values on the dev world, in code |
