# 06 · Tasks

In the order the work was done. Items that were planned and dropped are marked, with the reason in [02-solutions.md](02-solutions.md) or [07-journal.md](07-journal.md).

## 0. Planning
- [x] Read the codebase; write up how it works and where overload comes from (`01`)
- [x] Options and decisions (`02`)
- [x] Technical design (`03`)
- [x] Eval design (`04`)
- [x] Experiment plan (`05`)

## 1. Make it run
- [x] `gap:` models set by config
- [x] `gap:` cap output tokens on model calls
- [x] One setting for the data directory, read by every module that stores data
- [x] One message gets a reply
- [x] `gap:` cache the stable parts of the prompt

## 2. Worlds and cases
- [x] Catalogue of 40 kinds of work
- [x] Generator: people, work, histories as tool calls, agent names in the original's style
- [x] Dev world and held-out world
- [x] Case builder, 22 categories, 448 dev and 158 held-out cases
- [x] Case validator
- [x] A random 20 cases checked against the world
- [x] Checksum file; commit; tag `cases-frozen`

## 3. Harness and baseline
- [x] Runner: one process per case, the real orchestrator, execution agents not run
- [x] Saved model responses with replay
- [x] Grader, error types, scripted answers after a question
- [x] E1 size sweep; sizes chosen
- [x] E2 baseline, three repeats
- [x] Pass bars written into `05`
- [x] Reference strategies: always right, most recent, always create, always ask

## 4. Records and lookup
- [x] SQLite store, agent ids, contacts table
- [x] Record updates from tool calls, hooked into the execution agent
- [x] Lookup: recent, people, topic; then last shown, added after E6
- [x] Hand-off by id; separate create tool; duplicate check; throwaway agents
- [x] Hand-off entries in the conversation log
- [x] Prompt v2
- [x] Unit tests
- [x] E3: V1 and V2; E6 lookup quality

## 5. The deciders
- [x] V3: the prompt rule
- [x] V4: the code rule
- [x] V5: the judge, with forced output and a fallback
- [x] Hand-off limited to approved agents
- [x] Unit tests for the decision branches
- [x] E4; E5 ask settings
- [ ] Second round for the judge with the three changes from reading its failures: not run

## 6. Harder conditions
- [x] Crowded test: ten namesakes
- [x] Stress set: 40 messier messages
- [x] Heavy-use roster: six more pieces of work per person and ten namesakes, all six versions

## 7. Final
- [x] The winner set as the default
- [x] E7 held-out run
- [x] Results tables built from the saved runs (`python -m evals.report`)
- [x] Checks on every push
- [ ] Report (`08`)
- [ ] Pull request

## Planned and not done
- Agent memory from the work record, and its check
- Send approval for reply and forward; recipient check
- One run per agent at a time
- End-to-end stories against a fake mailbox
- Archiving, the Router Inspector, the roster-growth simulation: dropped on purpose
