# 06 · Tasks

In order. Each block ends with a review before it's committed.

## 0. Planning
- [x] Read the codebase; write up how it works and where overload comes from (`01`)
- [x] Options and decisions (`02`)
- [x] Technical design (`03`)
- [x] Eval design (`04`)
- [x] Experiment plan (`05`)

## 1. Make it run
- [ ] `gap:` models set by config
- [ ] `OPENPOKE_DATA_DIR`, read by every module that stores data
- [ ] One message gets a reply
- [ ] Five-case run to check cost per case

## 2. Worlds and cases
- [ ] Catalogue of kinds of work, with storylines
- [ ] Generator: people, work, histories in the app's log format
- [ ] Model rewrite of wording; agents named by replay through the original
- [ ] World validator
- [ ] Dev world and held-out world
- [ ] Case templates and written cases, 22 categories
- [ ] Case validator; second-model vote on labels
- [ ] My review of a random 20 cases
- [ ] Checksum file; commit; tag `cases-frozen`

## 3. Harness and baseline
- [ ] Runner: temporary world, sub-agents replaced by a recorder, first response captured
- [ ] Recorded responses with replay
- [ ] Grader, error types, scripted answers after a question
- [ ] Reference runs: always right, most recent, always create, always ask
- [ ] Unit tests for the grader
- [ ] E1 size sweep; choose the roster sizes
- [ ] E2 baseline
- [ ] Write the pass bars into `05`

## 4. Records and lookup
- [ ] SQLite store, migration from `roster.json`, logs keyed by ID
- [ ] Record updates from tool calls
- [ ] Contacts table
- [ ] Lookup: recent, people, topic; combining and caps
- [ ] Hand-off by ID; separate create tool
- [ ] Duplicate check on create; throwaway agents
- [ ] Hand-off entries in the conversation log
- [ ] Prompt v2
- [ ] Unit tests
- [ ] E3: V1 and V2; E6 lookup quality

## 5. The decider
- [ ] V3: the prompt rule
- [ ] V4: the code rule; choose its margin from the lookup's scores
- [ ] Judge call with forced JSON output and fallback
- [ ] V5: decision rules and the ask setting
- [ ] Hand-off restricted to approved agents
- [ ] Question flow: options, the pending question, one follow-up at most
- [ ] Unit tests for every decision branch
- [ ] E4 decider; E5 trade-off

## 6. Agent memory
- [ ] Agent memory from the record
- [ ] Agent memory check (about 20 cases)

## 7. Other gaps
- [ ] `gap:` send approval for send, reply and forward
- [ ] `gap:` recipient must be on the agent's record
- [ ] `gap:` one run per agent at a time
- [ ] `gap:` retries
- [ ] `gap:` message at the step limit
- [ ] `gap:` prompt clean-up

## 8. End to end
- [ ] Traces written by the live app
- [ ] Fake mailbox
- [ ] About five stories

## 9. Final
- [ ] Lock settings
- [ ] Final dev run of the winner
- [ ] E7 held-out run
- [ ] Results page
- [ ] Report (`08`) and code tour
- [ ] Checks on every push
- [ ] Pull request
