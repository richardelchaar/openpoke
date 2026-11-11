# 03 · Technical design

What is built, part by part, and why. The reasons for the larger choices are in [02-solutions.md](02-solutions.md).

---

## 1. The flow

```
message
   │
   ▼
lookup         code, SQLite       → up to 10 candidate agents, and the contacts the names matched
   │
   ▼
orchestrator   the existing loop  → hands off by id, creates an agent, or asks
```

The lookup runs at the top of the orchestrator's turn, before its existing loop (`agents/interaction_agent/runtime.py`). Everything is behind switches in `config.py`:

| Switch | Values | Default |
|---|---|---|
| `OPENPOKE_LOOKUP` | `none` (every name in the prompt, as the original) or `records` | `records` |
| `OPENPOKE_PROMPT` | `v1` (the original prompt) or `v2` (the rewrite) | `v2` |
| `OPENPOKE_DECIDER` | `orchestrator`, `told_to_ask`, `code_rule`, `judge` | `orchestrator` |

Setting the first two to `none` and `v1` gives the original behaviour, which is how the baseline was measured on the same code.

---

## 2. Storage (`services/agents/store.py`)

| Choice | Why |
|---|---|
| **SQLite**, in `data/agents.db` | The app already uses it for reminders. Writes are safe, which removes the roster file's lose-everything failure. Full-text search is built in. No new dependency. |
| **Every agent has an id** | A typo can't create an agent, and two agents can't share a log. The name becomes a title. |
| **One work record per agent:** people, threads, past search queries and reminders, a one-line summary | One thing to keep current. |
| **A person is an email address** | Two people called Omar are two people. |
| **At most 25 of each kind of fact** | A long-lived agent can't grow without limit. |
| **A local contacts table** | So the lookup can see a person the user knows who has no agent yet. |
| **One setting for the data directory** | Seven modules each computed their own path. The eval needs to point the app at a temporary world. |

---

## 3. Keeping the record current (`services/agents/records.py`)

| Choice | Why |
|---|---|
| **Facts come from the arguments of the agent's tool calls** | A reply already carries the exact thread id and address. Nothing is extracted from text. |
| **Only what the agent acted on:** drafts, replies, forwards, reminders | An agent that scanned the whole inbox must not end up matching every name. A search records the query and nothing from its results. |
| **The person named when the agent is created is added too** | So an agent is linked to its person before it does anything. |

The execution agent calls this after each successful tool call. The eval builds its worlds through the same function, so the rule above is what gets tested.

---

## 4. Lookup (`routing/lookup.py`)

No model call. It combines four sources:

| Source | How | Why |
|---|---|---|
| **Recent** | The agents in the last 3 hand-offs, read from the conversation log | What makes "ok send that" work. |
| **People** | Names in the message, matched as whole words against contacts and the people on records. A full name shuts out people who only share the first name. | Most requests name someone. |
| **Topic** | SQLite full-text search (BM25) over each record's title, summary, subjects, people and notes. The best 5 are added. | Rare words count more and word endings are ignored, so "renewals" finds "renewal". |
| **Last shown** | When the message names nobody: the people named in the last reply or agent report | What makes "reply to that" work after an email alert. Added after the lookup scored 0 of 12 on those cases. |

- **Combined and capped at 10.** Recent first, then name matches by keyword score, then topic matches.
- **Each candidate carries why it matched,** which goes into the trace.
- **The people the names matched are returned too,** including contacts with no agent. This is what lets the orchestrator see that "Omar" is two people.

Measured over every case: every agent a case needs is among the candidates 100% of the time, at every roster size, and the same with a cap of 3, 5, 10 or 20. Keyword search alone manages 88%.

**Known weaknesses**, both from the stress set:

- Names are matched as whole words. "Wes" is not "Wesley", so a short form finds nothing (1 of 6).
- Someone mentioned in a message is treated like the person it is for (2 of 6 on "tell A that B is covering for me").

And one that is untested: a topic in different words with no name. Every tested case that words a topic differently also names the person, and the name match finds the agent.

---

## 5. The orchestrator

| Choice | Why |
|---|---|
| **It sees the candidates, not every name** | The prompt stops growing with the roster. Each candidate shows who it has dealt with, its threads, and what its work is about. |
| **It sees the matched contacts** | Including people with no agent yet, so it can tell when a first name fits more than one person. |
| **`send_message_to_agent(agent_id, instructions)`**, limited to the candidates | It can't hand off to an agent that isn't in front of it, and a refused call says why. |
| **`create_agent(title, person_name, person_email, instructions, throwaway)`** | In the original one tool both reuses and creates, so a wrong name creates an agent without anyone deciding to. |
| **A duplicate check on create:** same person, and more than half the title's words already on one of their agents | Refuses, names the existing agent, and makes it available to hand off to. The orchestrator can override. |
| **Every hand-off is written to the conversation log** | The original keeps no record of who it sent what to. |
| **Prompt v2** | The original forbids questions, pushes parallel spawning, tells it to prefer any existing agent, and names a tool that doesn't exist. The rewrite permits one short question, keeps one agent per piece of work, and says chat needs no agent. |

---

## 6. The two deciders, switched off (`routing/decide.py`)

Built, measured, and not used by default. See [02-solutions.md](02-solutions.md), section 3.

Both write the same thing: which agents the orchestrator may hand off to this turn, whether it may create one, and a note saying what was decided. The hand-off tool refuses anything else.

- **Code rule.** Groups the people a message names. A full name is one person; a first name is everyone who has it. Within a group, the options are those people's agents plus any of them with no agent. If the best option's keyword score doesn't beat the next by a margin, it asks.
- **Judge.** One model call, temperature 0, output forced into a fixed shape by a required tool call. It says whether the message is chat or work, lists the tasks, and labels every candidate for each task. Code then counts: one exact match routes; more than one, or something plausible in the way, asks; nothing that fits creates. If the output is unusable twice, the orchestrator picks from the candidates as in the default.

---

## 7. Cost

Measured, per message, with prompt caching on for every version:

| | 20 agents | 160 agents | 640 agents |
|---|---|---|---|
| Original, tokens | 11,700 | 18,200 | 40,100 |
| Records and lookup, tokens | 10,300 | 11,000 | 11,100 |
| Original, dollars | $0.0005 | $0.0009 | $0.0023 |
| Records and lookup, dollars | $0.0007 | $0.0008 | $0.0008 |

At 20 agents the new path costs slightly more, because the candidates carry more text than 20 bare names. From 160 agents up it costs less, and it stops growing.

---

## 8. Traces

One record per message: the candidates and why each matched, the people the names matched, what was approved, and what the orchestrator did. The eval saves these for every case; `routing/pipeline.py` builds them.
