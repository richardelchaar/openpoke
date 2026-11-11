# 01 · How OpenPoke works today, and where overload comes from

Read against upstream commit `5b5f635`. Paths are under `server/`.

---

## 1. The system in one page

OpenPoke is a personal assistant for one user and their Gmail. It has two kinds of agent.

| | Orchestrator ("interaction agent") | Execution agents |
|---|---|---|
| Talks to the user | Yes | No |
| Tools | 4: message the user, hand off to an agent, show a draft, wait | 13: 9 Gmail and contacts tools, an email search task, 3 reminder tools |
| Gmail access | None | All of it |
| How many | One | As many as get created |
| Told apart by | | A name the orchestrator invented, and their history. Same prompt, same tools, same model. |

**One message, start to finish**

1. The message arrives at `POST /chat/send`. The server starts the orchestrator in the background and returns at once (`services/conversation/chat_handler.py:41-49`).
2. The orchestrator gets one prompt holding the conversation history, **the name of every agent that exists**, and the new message (`agents/interaction_agent/agent.py:20-58`).
3. To get work done it calls `send_message_to_agent(agent_name, instructions)`. If the name is in the roster, that agent is reused. If not, a new one is created (`agents/interaction_agent/tools.py:112-125`).
4. The execution agent runs with its whole past log in its system prompt, uses its tools, and returns a summary (`agents/execution_agent/runtime.py:43-136`).
5. Results are collected into a batch and sent back to the orchestrator, which tells the user (`agents/execution_agent/batch_manager.py:118-144`).

Two background jobs also start work: a reminder scheduler that runs an agent by name every time a reminder fires (`services/trigger_scheduler.py:93`), and an inbox watcher that tells the orchestrator about important new email (`services/gmail/importance_watcher.py`).

**Models:** all five roles are hardcoded to `anthropic/claude-sonnet-4` (`config.py:54-58`).

---

## 2. What I mean by agent overload

> The orchestrator has to pick the right agent from a list of bare names that only grows, with no record of what each agent did, under a prompt that tells it never to ask.

It shows up as three kinds of error:

| Error | What happens |
|---|---|
| **Wrong agent** | Work goes to an agent that holds someone else's context. The worst case is the wrong person. |
| **Duplicate** | A new agent is created for work an existing agent already holds, so the history is split. |
| **A guess** | Two agents could fit, and it picks one instead of asking. |

---

## 3. The causes, in the code

Ranked by how much damage I expected each to do, before measuring. What the baseline then showed is at the end of this section.

| # | Cause | Where | Effect |
|---|---|---|---|
| 1 | **The roster is a list of names, and every name goes into the prompt on every turn.** | `services/execution/roster.py:16`; `agents/interaction_agent/agent.py:45-58` | The orchestrator has nothing but a name to choose on, and the prompt grows with every agent. |
| 2 | **Reuse is an exact string match.** Any other spelling silently creates a new agent. | `agents/interaction_agent/tools.py:116-120` | "Email Alice" and "Email to Alice" become two agents. A typo looks the same as an intention. |
| 3 | **Nothing is ever removed.** The roster can add and clear, nothing else. | `roster.py:63-81` | A lookup done once in March is still on the list in November. |
| 4 | **The prompt pushes to act and never ask.** "Always assume you are capable"; "split it into as much concurrent calls … as possible"; "always prefer … a relevant existing agent"; "Don't worry if the agent name is unrelated"; "Never ask the user if they want extra detail". | `agents/interaction_agent/system_prompt.md:3,15,19,100` | With two plausible agents, it guesses. |
| 5 | **The orchestrator keeps no record of its own hand-offs.** The conversation log stores user messages, agent results, replies and waits. | `services/conversation/log.py:136-151` | On the next turn, the only trace of who got what is the agent's name in a result line. |
| 6 | **It uses an agent for everything.** "Always use the execution agents"; "you should use it often". | `system_prompt.md:3,13` | Chat and one-off questions create agents that then sit on the roster. |
| 7 | **Two different names can share one log file.** The file name lowercases the agent name and strips punctuation; the roster doesn't. | `services/execution/log_store.py:19-24,65-67` | "Email Alice" and "email alice!" are two agents on the roster reading and writing one history. |

Causes 1 to 6 are about too many agents and how one gets picked. Cause 7 turns a naming slip into mixed-up context.

**What measuring showed.** The ranking above was partly wrong ([07-journal.md](07-journal.md), E1 and E2):

- Cause 1 costs money more than accuracy. On the model I used, the original finds a named person as well in 1,280 names as in 10. What grows is the prompt: 11,700 tokens a message at 20 agents and 40,100 at 640.
- Cause 4 is the one that does the damage. The largest error at every size is acting when it should ask, and it usually acts on every option at once.
- Cause 1 has a second half I had not listed: with only names to look at, the orchestrator cannot see a person the user knows who has no agent yet. It never once asked about one.

---

## 4. Can it be reproduced?

Not from the repo as it stands. There are no tests, no evaluation, and no example of the failure.

So the first thing I build is a way to show it: a fake world with a known right answer for every request, a roster that can be filled to any size, and a runner that sends each request through the real orchestrator code and records what it does. The design is in [04-eval-design.md](04-eval-design.md).

---

## 5. Other gaps I found

Each of these is separate from overload. "Fixed" means fixed on this branch. The rest are in the report, each marked as fixed there or described with how I'd fix it.

| # | Gap | Where | Status |
|---|---|---|---|
| 1 | **The app can't be pointed at another model.** All five roles were hardcoded to `anthropic/claude-sonnet-4`, which OpenRouter no longer serves: a live call returns "no provider serves this model anymore". | `config.py:54-58` | fixed |
| 2 | **No cap on output tokens.** Without one the provider reserves the model's full output limit against the account balance, and refuses the request (402) when the balance can't cover it. | `openrouter_client/client.py:60-66` | fixed |
| 3 | **No prompt caching.** The system prompt, about 4,400 tokens, is paid for in full on every call, and each message makes at least two calls. Caching it cut the cost per message by 40 to 55%. | `openrouter_client/client.py` | fixed |
| 4 | **Seven modules each compute their own data path,** so the app can't be pointed at another data directory. | `services/**` | fixed |
| 5 | **Shared log files** (cause 7 above). | `log_store.py:19-24` | fixed by agent ids |
| 6 | **The roster file can wipe itself.** Saving opens the file for writing, which empties it, before taking the lock. A failed load then resets the list to empty, and the next save writes that. | `roster.py:27-29,44-45` | fixed by moving agents to SQLite |
| 7 | **Errors are swallowed.** When the orchestrator fails, the log says only "Interaction agent failed" (the detail is passed where the log format never prints it) and the user gets no reply at all. | `agents/interaction_agent/runtime.py:91-97` | fixed: the log has the error and the user gets a reply |
| 8 | **Hitting the 8-step limit raises an error** and the user gets nothing. | `agents/interaction_agent/runtime.py:47,186` | fixed: the user is told it stopped |
| 9 | **No retries.** One failed model call ends the turn. | `openrouter_client/client.py:70-88` | fixed: two retries on a timeout, rate limit or server error |
| 10 | **Prompt problems.** The orchestrator prompt tells it to use a `reacttomessage` tool that doesn't exist. The execution prompt still has `[TO BE FILLED IN BY USER …]` and lists 4 of its Gmail tools. | `interaction_agent/system_prompt.md:114,116`; `execution_agent/system_prompt.md:27,30-34` | fixed |
| 11 | **Reply and forward send immediately.** They call Gmail directly with no draft step. Only a line in the prompt asks for confirmation. | `agents/execution_agent/tools/gmail.py:387-428` | see the report |
| 12 | **Each agent's history grows without limit, and is cut short as it's written.** The whole log is replayed in the system prompt on every call; a cap exists in the code and is never set. Tool arguments are stored to 200 characters and results to 500, so a thread id the agent needs later can be missing. | `agents/execution_agent/agent.py:39,73-94,121-123`; `runtime.py:33` | partly: the agent is now given the people and thread ids from its work record; the log itself is unchanged. See the report. |
| 13 | **The same agent can run twice at once.** A reminder and a user request can both start it, on one log. | `agents/interaction_agent/tools.py`; `trigger_scheduler.py:93` | see the report |
| 14 | **No tests.** | | 36 unit tests and the eval added |
| 15 | **No login on the API.** Anyone who can reach the server can read the history or delete everything. | `routes/chat.py:18-45` | see the report |
