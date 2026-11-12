# 08 · Report: agent overload in OpenPoke

OpenPoke's orchestrator picks an agent from a list of bare names. I measured how well that works, changed what the orchestrator is shown, and measured again.

## Summary

| | Chosen configuration | Original |
|---|---|---|
| Routing decisions right | **92%** | 78% |
| Asks when it should | **97%** | 42% |
| Asks when it shouldn't | **7%** | 0 to 2% |
| Tokens per message, 640 agents | **10,700** | 39,700 |

Held-out test world, run once, 160 agents unless stated. The original is the app as it came, on the same cases.

- **The original's largest error is acting when it should ask.** Given "nudge Tessa, it's been a week" when Tessa has two pieces of work, or "send Omar my number" when there are two Omars, it asks in only 33 to 47% of cases. The rest of the time it picks one, or messages them all. It has only a list of agent names to go on, and its prompt tells it never to ask.
- **A work record per agent and a lookup fix most of that.** Each agent now keeps a record of who it has dealt with and on which threads, filled in from its own tool calls. For each message, code searches those records and the user's contacts and shows the orchestrator about ten candidates in place of every name. With that in front of it, it asks when it should 92 to 97% of the time.
- **A one-line description per agent gets part of the way, and the work record gets the rest.** I also ran the lookup over a title and a single line of description for each agent. That scores 86%, against 97% with the work record and contacts. The difference is in specific places: people who have no agent yet, a go-between copied on someone else's work, and fewer duplicates.
- **The gain is on messages where it is unclear who or what is meant.** Those go from between 0 and 58% right to between 80 and 100%. On clear messages the chosen version is 7 to 22 points worse on a few kinds, because it sometimes asks when it didn't need to. Nothing is sent to the wrong place when that happens, but the test still counts each one as a wrong outcome: part of the goal is to keep the user out of unnecessary back-and-forth, and an assistant that asks about everything would be useless. So those drops are real errors in the scores here. The test set has the rule.
- **A longer roster does not make the original less accurate** on the model I used. From 10 agents to 1,280 it stays between 73 and 80% right, because finding a named person in a long list is easy for a current model. What grows is the prompt, and so the cost: nearly four times the tokens per message at 640 agents as at 20. Two qualifications: the original does get worse when many agents belong to the same few people, and this was measured on one capable model, Claude Haiku 5.5. A weaker model may lose accuracy with size as well.
- **Forcing the orchestrator to ask made things worse.** I expected a step that decides when to ask, in code or with a second model call, to be the heart of the solution. I built it three ways and measured each on the same cases. All three asked more needless questions and no more correct ones, so they are switched off. The simplest arrangement, where the orchestrator sees the candidates and decides for itself, did best.

Model calls for the whole project cost about $30.

## The problem

OpenPoke is a personal assistant for one user and their Gmail. An orchestrator talks to the user. It does no email work itself: it hands each task to an execution agent, and each agent keeps the history of the work it has done. After days of use there are hundreds of agents.

**How the original chooses an agent**

1. **User message**: "nudge Tessa, it's been a week"
2. **Orchestrator**: sees the name of every agent that exists, and nothing else about them
3. **send_message_to_agent(name)**: if the name matches an agent it is reused; any other spelling creates a new one

*The orchestrator has no record of what an agent did, and no way to know about a person the user knows who has no agent yet. Its prompt tells it to assume it can always act and to prefer any existing agent.*

"Agent overload" is what the project's own write-up calls the result: every agent's name is sent on every request, and the agents compete for the orchestrator's attention. I took the problem to be this: **choosing the right agent, creating one only when needed, and asking when the message doesn't say enough.**

I expected the growing list to be the cause. The first thing I measured said otherwise.

## The test set

The repository had no tests and no example of the failure. So before changing anything I built a set of messages where the right routing decision is known in advance, and froze it.

### How it is made

A script builds it in two steps.

1. **It builds a world.** About 1,040 people and 1,380 agents. Each agent is one piece of work for one person, drawn from 40 kinds: claims, renewals, invoices, meetings, a dentist appointment. For example, it gives Tessa Saldanha two agents, one for a rental repair and one for a group gift.
2. **It writes messages about that world.** Each kind of situation has a few phrasings written as templates, such as "nudge {person}, it's been a week". The script fills one in with a person who fits. For a vague request about someone with two pieces of work, it picks Tessa.

The right answer is recorded as the message is written. The script gave Tessa two pieces of work itself, so it knows that "nudge Tessa Saldanha, it's been a week" should be met with a question, and which two agents the question should offer. No case is judged one at a time, and no language model writes the wording, so rebuilding from the same seed gives exactly the same cases.

### The situations it is built around

About 83 of the agents are the ones the messages are about. They are laid out to create the situations where routing goes wrong. The rest are filler that makes the roster as big as a test needs. Filler never shares a name with anyone in a message, so adding it cannot change the right answer.

| Trap | In the core | What it tests |
|---|---|---|
| Two people with the same first name, each with one piece of work | 12 pairs | Does it tell them apart by topic, and ask when it can't? |
| One person with two pieces of work | 12 people | Does it pick the right one when the topic is named, and ask when it isn't? |
| A person with an agent, and a contact with the same first name and no agent | 12 pairs | Does it know the second person exists? |
| A person with one piece of work and a first name nobody else has | 18 or more | The plain case |
| An adjuster copied on several people's claims | 3 | Does it route by the client, not the go-between? |
| An agent that read the whole inbox once and acted on nobody | 1 | Is it wrongly treated as knowing everyone it read about? |

### The cases

448 cases in 22 categories. Each is a message, the chat that came before it, and the right outcome.

| Right outcome | Category | Example | Cases |
|---|---|---|---|
| Hand off to an existing agent | Clear follow-up | "ask Dalia Eriksen about the jewellery rider" | 22 |
|  | Pronoun follow-up | "ok send that", after a draft was shown | 16 |
|  | Follow-up after a gap | "any update from Noor on the expense report?", after chat about someone else | 15 |
|  | Same person, two pieces of work, topic named | "ask Fiona about the commercial policy audit" | 34 |
|  | Same first name, topic settles it | "ask Felix about the missed premium payment" | 34 |
|  | Different wording | "where are we with Vera on the coverage for the trip?" for travel insurance | 18 |
|  | Shared contact | "ask Greta Rossi where Anton Greenwood's claim stands" | 12 |
|  | Follow-up on an email alert | "reply to that and say I'll call this afternoon" | 12 |
|  | Correction | "no, the other Bruno" | 14 |
| Create a new agent | Known first name, different person | "email Omar Kaur …" when only Omar Ivanov has an agent | 30 |
|  | Brand-new person | "email Xavier Appleton with feedback on the team page mockup" | 14 |
| Ask the user | Same person, vague | "nudge Tessa Saldanha, it's been a week" (she has two pieces of work) | 34 |
|  | Same first name, nothing settles it | "send Kofi a quick note that I'll call tomorrow" (two Kofis) | 34 |
|  | A person with an agent, or a contact | "invite Yara to the open house on the 20th" (two Yaras, one has no agent) | 30 |
| Answer directly | Chat or a general question | "thanks!", "what's a deductible?" | 15 |
| Robustness | Two tasks in one message | Both hand-offs right, and no question | 14 |
|  | Topic switch | Chat about one person, then a request about another | 12 |
|  | Inbox-scanner trap | The agent that read everything isn't used for "email Maria" | 12 |
|  | Messy text | Lowercase, shorthand and a typo: "tell caleb i need the paperowrk back by friday" | 20 |
|  | After a question | A question was asked and answered earlier; a follow-up must not ask again | 14 |
| Reported, not scored | Same person, new topic | "email Leila Sorensen that the final installment did not go through" (she has a claim agent) | 30 |
|  | One-off lookup | "find the wifi password someone sent me last year" | 12 |

About three quarters of the scored cases have a clear answer and a quarter call for a question. The last two categories run for every version but count toward no rate: the original and I disagree by design about what is right there, so I report how often each version reuses an agent and score neither.

### One case, start to finish

**"nudge Tessa Saldanha, it's been a week"**

1. **The world**: Tessa has two agents: a rental repair (a radiator) and a group gift (a baby shower)
2. **The right outcome**: Ask which one. Hand off to nothing.
3. **Checked by rule**: No hand-off, and the reply is a question that names both: it must mention "repair" or "radiator", and "gift" or "shower"
4. **Then a scripted answer**: "the rental repair" → must go to that agent. "neither, it's about a tax return" → must create one. "the usual one" → may ask once more.

*Every case that calls for a question carries up to three scripted answers, so the turn after the question is tested as well as the question.*

### How a case is run and graded

- **Each case goes through the real orchestrator code,** at roster sizes of 20, 160 and 640 agents. Execution agents don't run: a hand-off is recorded and stops there.
- **Grading is by rule, with no judging model.** A turn is reduced to which agents got work, which were created, whether it asked, and what it said.
- **A needless question is a wrong outcome.** The goal is the right agent with as little back-and-forth as possible, so asking when the message was already clear counts against the overall rate like any other error. About three quarters of the cases have a clear answer. A strategy that asks every time, naming every option perfectly, scores 30%.
- **Every wrong answer gets a type:** wrong person, wrong agent, duplicate, missed question, needless question, and so on.

### Keeping it fair

- **The cases were frozen before the solution existed.** They were committed with a checksum and tagged, and have not changed since. A validator checks every case against the whole world.
- **The original was measured first.** Bars for the new version were written down after that and before any changed version ran.
- **Every version runs on the same cases at the same roster sizes.**
- **A second world was held back and run once at the end:** 158 cases, different people, a different mix of work. Its figures are the ones in the summary.
- **The original was run three times.** Its overall rate moved 1.2 points between repeats, so later versions were run once per size and I treat a gap under 2 points as a tie.

## How the original performs

### A longer list alone is not the problem

A first sweep ran the original on about 64 cases at eight roster sizes. In this sweep a bigger roster means more unrelated people: the agents a case is about stay the same, and the rest of the list grows around them.

| Agents in the roster | 10 | 20 | 40 | 80 | 160 | 320 | 640 | 1,280 |
|---|---|---|---|---|---|---|---|---|
| Right | 73% | 73% | 78% | 80% | 75% | 77% | 77% | 79% |
| Tokens per message | 11,900 | 12,200 | 12,800 | 14,600 | 19,000 | 26,300 | 40,700 | 69,500 |

*Tokens per message over the same range: 11,900 at 10 agents, 69,500 at 1,280. This sweep ran before the test set was frozen, on an earlier draw of the cases, so its percentages are not comparable with the tables below. Its point is the shape.*

Finding a named person in 1,280 names is easy for this model. The mistakes come from the two or three agents that could fit, and they are there at every size.

### What it gets wrong

The full baseline ran all 448 cases at three roster sizes, three times each.

- **It doesn't ask.** About 200 of 1,218 runs at each size are a question it should have asked and didn't. In most of those it picks one of the options. In about a quarter it sends the work to every option at once.
- **A contact with no agent is invisible to it.** "Send Omar my new phone number", when one Omar has an agent and another is only a contact, was handled correctly in 0 of 270 runs. It usually went to the Omar with an agent.
- **Roster size changes which mistake it makes.** With few agents it reuses too readily. With many it creates too readily: duplicates rise from 1.5% to 3.9%.
- **One situation does degrade with size.** "Ask the adjuster where Anton's claim stands" reaches Anton's claim agent 92% of the time at 20 agents and 39% at 640.

### Why size was flat, and what I tested next

I had expected the original to get worse with more agents. The cause of the flat line was in my own test. A bigger roster only added filler: unrelated people who share no name with anyone in a message. The situations that cause mistakes, two people with one first name or one person with two pieces of work, were the same at 10 agents and at 1,280. The roster was getting longer without getting any more confusing.

In real use, more agents also means more people sharing a name, and more work piling up for the people you already deal with. So I added two tests, keeping the same 448 cases and their right answers.

1. **More people with the same name.** Ten extra people for each first name in a case. "Ask Felix about the missed premium payment" now ran with twelve people called Felix instead of two. The effect on the original was small: about 3 points on routing.
2. **More work for the same person as well.** A crowded roster: still 160 agents, with each person in a case holding six more pieces of work and having ten namesakes. None of it is about the same kind of thing as the message.

| The original at 160 agents | Normal roster | Crowded roster |
|---|---|---|
| Creates a duplicate agent | 3.2% | 7.4% |
| Right on the turn after the user answers a question | 83% | 59% |
| Asks when it should | 35% | 83% |

This is where the original changes. It creates more than twice the duplicates and handles the user's answer much worse. It also asks more, because eight agents for one person in the list make the ambiguity visible. So the number of agents does not hurt on its own. Many agents for the same few people does.

> **This is one model.** Everything here ran on Claude Haiku 5.5, which reads a very long prompt without losing track of what is in it. The flat line shows that this model's attention isn't diluted by 1,280 names. It doesn't show that the original design is safe at that size: an older or smaller model may well get worse as the list grows, which is what the project's own write-up expected. I did not test another model.

## What I built

### The approach

The baseline pointed at two possible causes. Either the orchestrator is told the wrong thing (its prompt forbids questions and pushes it to reuse), or it is shown the wrong thing (bare names, and nothing about who each agent works for). If neither was enough, the remaining option was to take the decision to ask away from it.

I did not want to pick one and argue for it. I laid the options out from cheapest to most involved, built each as a configuration behind a switch in the same code, and ran every one on the same cases. Each adds one idea to the one before, so a difference in the results can be put down to that idea. The seven configurations are numbered below, and the results use the same numbers.

#### Configuration 0: the original
- **What it is.** The app as it came. Every agent's name in the prompt, hand-off by name, the original instructions.
- **Why it is here.** The numbers to beat. It runs on the same code as everything else, with the new parts switched off.

#### Configuration 1: the prompt rewritten
- **What it is.** Configuration 0 with only the orchestrator's instructions changed. It still sees every name and nothing else.
- **How it is built.** Four edits to the prompt. "Always assume you are capable" and "never ask" become: you may ask one short question when you can't tell who or what is meant. "Always prefer an existing agent, even if the name is unrelated" becomes: reuse an agent only to continue its piece of work. "Always use the execution agents" becomes: chat and general questions need no agent. A tool the prompt names and that does not exist is removed.
- **Why I tested it.** It is a text edit with no new code. If it had been enough, nothing else here would have been worth building.

#### Configuration 2: a lookup over a description of each agent
- **What it is.** Each agent keeps a title and one line of description, such as "missed payment (annual premium); with Pavel Pellegrino". Before the orchestrator runs, code searches those descriptions and shows it about ten candidates in place of every name.
- **How it is built.** The lookup takes the agents used in the last three hand-offs, then adds the agents whose title or description shares words with the message, by keyword search. It makes no model call. The orchestrator hands off by agent id, and creating an agent is a separate tool.
- **Why I tested it.** It is the simplest version of a lookup: nothing to keep up to date beyond one line per agent. It tests whether a short list alone is the fix, before adding anything heavier.

#### Configuration 3: a lookup over a work record of each agent
- **What it is.** Configuration 2, with more kept about each agent: the people it has written to, by email address; its threads; what it searched for. There is also a table of the user's contacts. The orchestrator is shown the candidates and the people the message's names matched, and is free to route, create or ask.
- **How it is built.** The record is filled in from the arguments of the agent's own tool calls, and only from what it acted on. The lookup matches the names in the message against the people on records and in the contacts, as well as searching by keyword. The parts are described under The parts in detail.
- **Why I tested it.** A description names a person. It cannot tell two people with one name apart, and it knows nothing of a person who has no agent yet. A record keyed on email address and a contacts table can.

Configurations 4, 5 and 6 all start from configuration 3. Each is a stronger way of making the orchestrator ask when it should.

#### Configuration 4: required to ask, by a rule in the prompt
- **What it is.** Configuration 3 with one firm instruction added.
- **How it is built.** One line in the prompt, marked as important: if more than one candidate could be the one the user means, and the message doesn't settle it, do not pick one and do not send it to several. Ask one short question that names the options and offers "something new", then stop. Nothing in code checks that it does.
- **Why I tested it.** Configuration 3 only permits a question. This is the cheapest way to push harder. If a sentence could do it, no machinery would be needed.

#### Configuration 5: code decides when to ask
- **What it is.** Configuration 3 with a step in code, before the orchestrator runs, that decides whether to route, create or ask. The orchestrator can only carry out that decision.
- **How it is built.** The code groups the people the message names. A full name is one person; a first name is everyone who has it. For each group, the options are those people's agents, plus any of them who has no agent. Each option has a score for how well its record matches the words of the message. If the best score beats the next by a set margin, the code approves that one agent. If not, the words have not settled it, and the code calls for a question listing the options. One named person with no agent means create. If the message names nobody, the code decides nothing and the orchestrator chooses as in configuration 3. The decision is enforced, not suggested. The hand-off tool only accepts the agents the code approved for that message and refuses any other, and when the decision is to ask, no hand-off or create tool is offered at all.
- **Why I tested it.** A prompt is a request and can be ignored. This cannot be. It adds no model call, gives the same answer every time, and every branch can be unit tested. Its known weakness going in: it compares words, not meaning.

#### Configuration 6: a second model call decides when to ask
- **What it is.** Configuration 5 with the scoring done by a model in place of keyword matching. One extra model call per message.
- **How it is built.** Before the orchestrator runs, a separate call is given the recent chat, the message, the candidates and the matched contacts. It does not choose an agent. It says whether the message is chat or work, lists the tasks in it, and gives every candidate one of four labels for each task: *exact* (this continues that agent's work), *plausible* (it could be, and the message doesn't say enough), *same person, other work*, or *unrelated*. Its output is forced into a fixed shape and it runs at temperature zero, so code can read it. Code then counts the labels. One exact and nothing plausible in the way: route. More than one exact, or something plausible: ask, with those as the options. Nothing that fits: create. Chat: no agent. As in configuration 5, the tools enforce the result. If the call's output is unusable twice, the orchestrator chooses as in configuration 3.
- **Why I tested it.** Code cannot read meaning: "tell Colin the medication is running out" is plainly about a vet visit and shares no word with it. A model can. And judging each candidate on its own, instead of asking for one pick, lets two both come back "plausible", which is what should trigger a question. The fourth label exists so that "it is Tessa, and it isn't about her claim" counts as an answer and not as a doubt. This is the configuration I expected to win.

### The parts in detail

Configurations 2 to 6 share a lookup and a changed orchestrator. Configurations 3 to 6 share the work record and the contacts.

**How the new version chooses an agent**

1. **User message**
2. **Lookup**: code, no model call. Gathers the recently used agents, the agents for anyone the message names, and the agents whose record matches the topic.
3. **Orchestrator**: sees about ten candidates, each with who it has dealt with and what it is about, plus the contacts the names matched
4. **One of three**: hand off to a candidate by id · create a new agent · ask the user

#### The work record

| Choice | What I chose | What I chose it over, and why |
|---|---|---|
| Where the facts come from | The arguments of the agent's own tool calls | Reading them out of the agent's log with a model. A reply call already carries the thread id and the address, so copying them is exact and free. |
| What goes on the record | Only what the agent acted on. A search keeps the query, not the results. | Everything it saw. An agent that once searched the whole inbox would then match every name in it. |
| Who a person is | An email address | A name. Two people called Omar are two people. |
| Where it is stored | SQLite, beside the app's other data | The original's JSON file, which can empty itself, or a vector database, which nothing here needs. SQLite is already in the app, writes safely and has keyword search built in. |

#### The lookup's four sources

| Source | What it adds | Why it is there |
|---|---|---|
| Recently used | The agents in the last three hand-offs, always included | "Ok send that" names nobody and has no topic words. The only clue is which agent was just used. |
| People (3 to 6) | Agents that have dealt with anyone the message names. A full name shuts out people who only share the first name. | A name is an exact thing to match, and it finds the agent even when the topic is worded differently. |
| Topic | Agents whose record or description shares words with the message | For a request with no name. |
| Last shown | When the message names nobody: who was named in the last thing the user was shown | "Reply to that", after an email alert. Added after the first lookup test found the right agent in 0 of 12 such cases. |

#### The people the names matched (3 to 6)

Alongside the candidates, the lookup returns every person the user knows whose name is in the message, including people with no agent yet.

**"send Omar my new phone number"**

- **What the original sees:** Agent names only. One contains "Omar": `Omar Ivanov jewellery rider` To the original, there is one Omar. It sends him the number.
- **What the new version sees:** One candidate agent, and two matched people: `Omar Ivanov: has 1 agent` `Omar Kaur: no agent yet` Two people fit, so it asks which Omar.

*The original handled this kind of message correctly in 0 of 270 runs. It is not choosing badly between two people. It never sees the second one.*

#### The orchestrator

- **It hands off by agent id, and only to a candidate.** In the original, a name that doesn't match exactly creates a new agent, so a typo and an intention look the same.
- **Creating an agent is a separate tool,** with a check for work that already has one.
- **Every hand-off is written to the conversation log.** The original kept no record of who it had sent what to. The "recently used" source reads these entries.

## Results for every configuration

All seven configurations on the same 448 cases, on the world I built and tuned on. The numbers are the ones the configurations are given above.

### The full picture at 160 agents

| Configuration | Right | Asks when it should | Asks when it shouldn't | Right after the user answers | Makes a duplicate | Tokens per message |
|---|---|---|---|---|---|---|
| 0. Original | 78% | 35% | 1% | 83% | 3.2% | 18,200 |
| 1. Prompt rewritten | 81% | 67% | 3% | 80% | 7.4% | 15,600 |
| 2. Lookup over a description | 86% | 74% | 3% | 84% | 2.5% | 10,700 |
| 3. Lookup over a work record | 97% | 100% | 3% | 85% | 0.7% | 11,000 |
| 4. …required to ask | 94% | 100% | 7% | 88% | 0.7% | 11,200 |
| 5. …code decides | 90% | 96% | 12% | 77% | 0.2% | 11,300 |
| 6. …second model call decides | 93% | 100% | 9% | 90% | 1.2% | 13,700 |

- **Asks when it should:** of the messages where a question was the right move, how often it asked.
- **Asks when it shouldn't:** of the messages with a clear answer, how often it asked anyway. Lower is better.
- **Right after the user answers:** when it asked and the user replied, how often the next turn did the right thing.

### As the roster grows, and when it is crowded

| Right outcome | 20 agents | 160 agents | 640 agents | 160 agents, crowded |
|---|---|---|---|---|
| 0. Original | 81% | 78% | 77% | 83% |
| 1. Prompt rewritten | 81% | 81% | 81% | 83% |
| 2. Lookup over a description | 87% | 86% | 85% | 89% |
| 3. Lookup over a work record | 96% | 97% | 95% | 95% |
| 4. …required to ask | 94% | 94% | 91% | 91% |
| 5. …code decides | 91% | 90% | 91% | 85% |
| 6. …second model call decides | 94% | 93% | 93% | 94% |

The crowded roster is the one from How the original performs: each person in a case has six more pieces of work and ten namesakes. It is graded with two allowances: a question there need not list every option, and corrections are left out, because "no, the other Gustavo" has no single answer when there are eleven. Under the normal rules, configuration 0 scores 68% there and configuration 3 scores 85%.

### What each configuration showed

- **1. The prompt rewritten does nothing overall.** It asks more often and is no better. With only names to go on, "new work gets a new agent" makes it start fresh too often: duplicates more than double.
- **2. A lookup over a description gets most of the way, and falls short in two places.** Its lookup finds the right agent as often as configuration 3's, and it asks needless questions just as rarely. But it never asks about a contact who has no agent, because it has no contacts to see: 0% on those messages, against 100%. And it sends "ask the adjuster where Anton's claim stands" to the right agent 31% of the time, against 100%: a work record shows that the adjuster was copied on Anton's claim, and a one-line description does not. It also makes two to three times as many duplicates.
- **3. A lookup over a work record fixes most of it.** Once the orchestrator can see who each candidate works for, and that a name fits two people, it asks every time it should, without being forced to.
- **4. Requiring it to ask adds needless questions and no correct ones.** It takes "more than one candidate could fit" too broadly, and asks about new people and about requests the topic already settles.
- **5. Letting code decide asks the most needless questions.** It cannot read meaning. "Tell Caleb we want the new seats live on Monday" shares no word with his subscription record, so it calls a tie and asks. It also handles the user's answer worst, because a short answer has few words to match.
- **6. A second model call ties configuration 3 overall, and is better on the turn after the user answers.** It asks more needless questions, partly from a flaw found afterwards: it sometimes asks "which one?" when there is only one option. It costs one more model call on every message.

### Which one I chose

The original was run three times, and its overall rate moved 1.2 points between repeats. So I treat a gap under 2 points as a tie, and where two configurations tie, the simpler one wins.

**I chose configuration 3.** It is best or tied on the overall rate at every roster size, it asks needless questions as rarely as any configuration with a lookup, and it needs no extra model call.

- **Against configuration 2, the simpler one:** 9 to 11 points better. The work record and the contacts earn their place, and the gain is in specific places: people with no agent yet, a go-between copied on someone else's work, and fewer duplicates. Leaving out the messages about a contact with no agent, the gap is 1 to 4 points (94 / 93 / 91% against 95 / 96 / 95%), so most of what the record buys is the contacts.
- **Against configuration 6, the most involved one:** a tie. Configuration 6 is better at handling the user's answer, at the price of a second model call on every message.
- **Configurations 4 and 5** are worse on every count.

> Once the orchestrator can see the candidates, it already asks every time it should. The problem was not that the model wouldn't ask. The original gave it nothing to go on. Each stronger push to ask added questions that weren't needed.

Configurations 4, 5 and 6 are still in the code, switched off, so these runs can be reproduced.

## The chosen configuration, in detail

Everything in this section is configuration 3, a lookup over a work record, against configuration 0, the original.

### On a world it was not tuned on

The results above are from the world I built and tuned on. A second world, with different people and a different mix of work, was held back and run once after the choice was made: 158 cases, of which 143 are scored. These are the figures in the summary. The chosen configuration scores 3 to 6 points lower here than on the first world, so these are the ones to rely on.

![What happened to each message, 160 agents](img/outcomes-heldout.svg)

*Configuration 3 trades the original's main error, acting without asking, for a smaller number of questions it didn't need to ask.*

|  | 20 agents | 160 agents | 640 agents |
|---|---|---|---|
| Original, right | 78% | 78% | 74% |
| Configuration 3, right | 90% | 92% | 92% |
| Original, asks when it should | 47% | 42% | 33% |
| Configuration 3, asks when it should | 92% | 97% | 97% |
| Original, asks when it shouldn't | 2% | 0% | 1% |
| Configuration 3, asks when it shouldn't | 7% | 7% | 7% |

### Cost

![Tokens per message by roster size, held-out world](img/tokens.svg)

*In dollars configuration 3 costs slightly more per message at 20 agents ($0.0008 against $0.0005), about the same at 160, and a third as much at 640 ($0.0008 against $0.0023).*

### Where the gain comes from, and where it loses

By kind of message, pooled over the three sizes. Each kind has only 4 to 12 cases on this world, so single rows are noisy. The pattern is what matters.

| Kind of message | Original | New | Change |
|---|---|---|---|
| A person with an agent, or a contact with none | 0% | 88% | +88 |
| Same person, vague ("nudge Tessa") | 47% | 97% | +50 |
| Same first name, nothing settles it | 53% | 100% | +47 |
| Shared contact (the adjuster) | 58% | 100% | +42 |
| Correction ("no, the other one") | 47% | 80% | +33 |
| Same person, two pieces of work, topic named | 81% | 97% | +17 |
| Known first name, different person | 91% | 100% | +9 |
| Follow-up on an email alert | 92% | 100% | +8 |
| Messy text, different wording, chat, after a question | 80–100% | same | 0 |
| Brand-new person | 87% | 80% | −7 |
| Topic switch | 92% | 83% | −8 |
| Inbox-scanner trap | 100% | 92% | −8 |
| Clear follow-up | 100% | 88% | −12 |
| Follow-up after a gap | 100% | 87% | −13 |
| Pronoun follow-up ("ok send that") | 100% | 83% | −17 |
| Two tasks in one message | 100% | 80% | −20 |
| Same first name, topic settles it | 100% | 78% | −22 |

The original acts without asking, so it is right on clear messages and wrong on unclear ones. Configuration 3 asks more readily, so it is right on unclear ones and sometimes over-cautious on clear ones. Nearly every loss in the lower half of the table is a question that wasn't needed, not work sent to the wrong place.

> The top row is a category the original cannot pass, because it has no way to see a contact who has no agent. Leaving it out, the comparison is 85 / 85 / 80% for the original against 91 / 92 / 92%.

### The bars I set beforehand

| Bar | Result at 20 / 160 / 640 agents |  |
|---|---|---|
| Right, 88% or more | 90 / 92 / 92% | met |
| Asks when it should, 80% or more | 92 / 97 / 97% | met |
| Reaches the wrong person on the first turn, 1% or less | 0% | met |
| 640 agents within 3 points of 20 | 2 points higher | met |
| Tokens per message, 15,000 or less | about 10,500 | met |
| Asks when it shouldn't, 5% or less | 7% | missed |
| Right on the turn after the user answers, 85% or more | 88 / 82 / 78% | missed at two sizes |
| Duplicates, 1% or less | 1.4 / 2.1 / 1.4% | missed |

**On the wrong-person bar:** on the first turn, no run of configuration 3 handed work to an agent belonging to someone else. On the turn after the user answers a question, it did so once in 90 runs at 20 agents and not at the other sizes.

**On the turn after the user answers:** the original scores 80 / 84 / 89% there, on the far fewer occasions when it asks at all (35 to 50 runs, against 90 to 95). Configuration 3 gets worse on this step as the roster grows.

### On the crowded roster

| First world, 160 agents | Normal roster | Crowded roster |
|---|---|---|
| Original: creates a duplicate | 3.2% | 7.4% |
| Configuration 3: creates a duplicate | 0.7% | 0.5% |
| Original: right on the turn after the user answers | 83% | 59% |
| Configuration 3: right on the turn after the user answers | 85% | 73% |
| Configuration 3: asks when it shouldn't | 3% | 6% |

Configuration 3 holds up better: it does not create more duplicates under crowding. For every configuration, the turn after the user answers is what suffers most.

The overall rate under crowding depends on how a question is graded. A good question about eight pieces of work may not list them all, and "no, the other Gustavo" stops pointing at one person when there are eleven. With allowances for both, the original scores 83% and configuration 3 95% (91% on the held-out world). Under the same rules as the normal roster they score 68% and 85% (80% on the held-out world). Either way the gap is about the same. Of the others, configuration 6 ties it here as well (94%), configuration 2 reaches 89%, and configuration 5 falls furthest (85%).

### On messier messages

The main result looked high, and every case spells a name exactly as the contacts do. So after the main results I wrote 40 messages that don't: a short or misspelt name, a surname alone, no name at all. They were not used to tune anything.

| Right, of the cases in each kind | Original | Configuration 3 |
|---|---|---|
| A surname alone ("ask Oduya…") | 3 of 6 | 6 of 6 |
| No name, only the topic | 2 of 10 | 10 of 10 |
| A misspelt surname | 6 of 6 | 6 of 6 |
| A short form of a first name ("ask Wes…") | 4 of 6 | 1 of 6 |
| Lowercase with a typo in the first name | 5 of 6 | 3 of 6 |
| Two people named, one is the recipient | 5 of 6 | 2 of 6 |
| All 40 | 25 | 28 |

The lookup is much better where there is no first name to match, and worse where the first name is in a form it doesn't recognise. Names are matched as whole words, so "Wes" finds nothing, where the original reads the whole list and can make the leap. That is a regression. The original reached the wrong person 6 times in these 40. Configuration 3 did not.

### A second iteration

The chosen configuration still asks when it didn't need to, on 3 to 4% of clear messages on the first world and 7% on the held-out one. After the held-out run I went after that. Reading them suggested a cause: the lookup also returns agents that only share a topic with the message, and the orchestrator was treating them as alternatives. I changed the candidates to say how each was found, and ran it on the first world.

| First world, 20 / 160 / 640 agents | First | Second |
|---|---|---|
| Right | 96 / 97 / 95% | 96 / 97 / 97% |
| Asks when it shouldn't | 3 / 3 / 4% | 4 / 3 / 3% |
| Asks when it should | 100 / 100 / 100% | 99 / 99 / 97% |
| Right on the turn after the user answers | 87 / 85 / 82% | 89 / 88 / 84% |

It did not reduce the needless questions, so my reading of their cause was wrong or incomplete. It is a tie overall and stays off by default. I did not re-run the held-out world with it: that world is for one run.

## Other gaps

Found while working, separate from overload.

### Fixed on this branch

| Gap | Fix |
|---|---|
| Models hardcoded to one that is no longer served. The app could not run. | Models come from config |
| No cap on output tokens, so a request is refused outright when the account balance can't cover the model's full output limit | A default cap |
| The 4,400-token system prompt paid for in full on every call | The stable parts of the prompt are cached: 40 to 55% off the cost per message |
| Seven modules each computing their own data path | One setting |
| Two agent names could share one log file. The roster file could empty itself. | Agents have ids and live in SQLite |
| A failure left the user with no reply and the log with no detail | The user gets a reply and the log has the error |
| Hitting the step limit left the user with nothing | The user is told it stopped |
| No retries on a failed model call | Two retries on a timeout, a rate limit or a server error |
| The orchestrator's prompt names a tool that doesn't exist. The execution agent's prompt has an unfilled placeholder. | Both removed |
| An agent could lose a thread id it needs, because its log is cut short as it's written | The agent is given the people and thread ids from its work record |
| No tests | 39 unit tests, the eval, and checks on every push |

### Not fixed, and how I would

| Gap | What I'd do |
|---|---|
| Reply and forward send immediately. Only a prompt line asks for confirmation. For a broker this is the one that matters most. | Make a reply a draft on the thread, and let a draft be sent only once its exact text has been shown and approved on a turn the user started |
| An agent's whole log is replayed in its prompt on every call | Replay only its last few turns, now that the facts it needs are on its record |
| The same agent can be started twice at once, by a reminder and a user request | One run per agent at a time |
| No login on the API | Out of scope here. Anyone who can reach the server can read the history. |

## Limits

### Of the solution

- **The contacts table and the summary line are thinner in the app than in the test.** The test gives the lookup the user's address book and a clean one-line summary for every agent. In the app, a contact is learned when an agent is created for that person, and the summary is the first sentence of the agent's first instructions. Importing the address book, and keeping the summary current, are not built.
- **It has not been run end to end against a mailbox.** The eval stops at the orchestrator's decision. I ran the app itself with the new defaults on a handful of messages: it answered chat directly, and for a request it created the agent with its record and contact and handed off to it. With no Gmail account connected, the agent could go no further than reporting that.
- **It asks when it didn't need to on 7% of clear messages,** and I don't yet know why.
- **Short forms of names find nothing,** and someone merely mentioned in a message is treated like its recipient.
- **It makes more agents, not fewer.** One agent per piece of work is a choice of mine. The lookup is what keeps a larger number of agents from costing more or confusing the choice.

### Of the test

- **The test set is generated, and I chose its categories.** It finds the failures I thought to look for. The 92% is what the design does when names resolve cleanly. The 40 messier messages, at 70%, are closer to an untidy inbox.
- **The held-out world is built by the same generator as the dev world.** It shows the result isn't tied to particular names or to a client-heavy mix. It does not test a different style of message.
- **One model.** The original and every version ran on Claude Haiku 5.5. The finding that roster size alone doesn't reduce accuracy may be a property of that model. On a model that handles long prompts less well, the lookup could matter for accuracy as well as for cost.
- **One run per roster size** for every version except the original on the dev world. Single categories move much more than the overall rate.
- **Configuration 2's descriptions are better than real ones might be.** The test writes each agent's one-line description, and always includes the person's full name. A description written during real use could be vaguer, which would widen the gap to the work record.
- **"Asked" is detected simply:** a reply with a question mark and no hand-off.
- **A topic in different words with no name is untested.** Every case that words a topic differently also names the person.

### Grading rules I changed after reading failures

Each applies to every version, and the saved runs were re-graded.

| Change | Why | Effect |
|---|---|---|
| Two categories are reported and not scored | The original reuses an agent there because its prompt tells it to. I was scoring my own design preference. | Raised the original by 1 to 3 points |
| A correction may also contact the agent that was wrongly used | The app tells that agent to stop, which is right. It was being marked as reaching the wrong person. | Raised the original by 1 to 2 points and the new version by about 3 |
| After a question about which person, a new agent for the chosen person counts | The same design choice as the first row | Raised both by about 5 points on the turn after an answer |
| On the crowded roster, a question need not list every option | A person there has up to eight pieces of work | Both figures are given above |
| On the crowded roster, corrections are left out | With eleven people of one name, "the other one" has no single answer | As above |

## What I'd do next

1. **Find out why it asks on clear messages.** Read the 7% one by one. My first explanation didn't survive a test.
2. **Import the user's contacts,** and keep each agent's summary current.
3. **Use the second model call for the turn after the user answers only,** where it is 5 to 10 points better, with its single-option flaw fixed.
4. **Match short forms and near-spellings of first names,** and tell a recipient from someone who is only mentioned.
5. **Approval in code before a reply or a forward is sent.**
6. **An end-to-end run against a test mailbox.**
7. **Repeat the size sweep on other models,** a smaller one and an older one. If their accuracy falls as the roster grows, the lookup is doing more than saving cost, and the case for it is stronger than the one made here.
8. **Test cases written by someone else,** from real messages if possible.

## Reproducing it

None of these call a model.

```
python -m pytest tests -q                  # 39 tests
shasum -a 256 -c evals/CHECKSUMS           # the worlds and cases are the frozen ones
python -m evals.cases.validate             # every case against its world
python -m evals.references dev             # the grader on four simple strategies
python -m evals.report dev                 # the results tables, from the saved runs
python -m evals.report heldout
python -m evals.report --categories heldout
python -m evals.offline lookup             # how often the lookup finds the right agent
```

A new run needs `OPENROUTER_API_KEY`.

```
python -m evals.run --world dev --version v2 --sizes 20,160,640
```

In the code the configurations are named `v0` (0), `v1` (1), `v2d` (2), `v2` (3), `v3` (4), `v4` (5) and `v5` (6). `v2b` is the second iteration of configuration 3.

The saved runs are in `evals/results/`. The test set was committed and tagged `cases-frozen` before any changed version was run. The design notes, the plan and a journal of every experiment are in `docs/agent-overload/`.
