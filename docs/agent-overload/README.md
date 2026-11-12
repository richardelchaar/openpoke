# Addressing Agent Overload in OpenPoke

An empirical analysis, architectural solution, and deterministic evaluation benchmark for agent routing overload in OpenPoke (built against upstream `shlokkhemani/openpoke` at commit `5b5f635`).

**Read the full technical report:**
- **Hosted HTML report (with charts and diagrams):** [https://richardelchaar.github.io/openpoke/agent-overload/report.html](https://richardelchaar.github.io/openpoke/agent-overload/report.html) *(local copy: [report.html](report.html))*
- **Markdown version:** [08-report.md](08-report.md)

---

## Core Problem

Upstream OpenPoke injects the bare display name of every execution agent ever created into the orchestrator's prompt on every turn, with no record of who each agent emailed, no visibility into contacts who do not yet have an agent, and prompt instructions that discourage asking clarifying questions.

## Methodology

1. **Built and froze a deterministic benchmark first (`cases-frozen`),** pairing synthetic multi-contact worlds with ground-truth routing outcomes across 22 scenario categories.
2. **Measured the unmodified baseline (`v0`).** Its largest failure mode is silently guessing instead of asking on ambiguous requests. On `anthropic/claude-haiku-5.5`, scaling unrelated roster length increased prompt cost nearly fourfold without hurting accuracy, whereas per-contact task crowding broke multi-turn accuracy and doubled duplicate creation.
3. **Evaluated seven incremental configurations (`v0`–`v5`, `v2d`)** behind environment switches in the same codebase to isolate each architectural change.
4. **Selected the simplest highest-performing architecture (`v2`, Work-Record Shortlist):** each execution agent maintains a SQLite work record populated automatically from its tool-call arguments, and a zero-LLM lookup retrieves up to 10 candidate agents plus matching contacts per turn.
5. **Validated once on an untuned held-out world.**

## Headline Results

All runs use `anthropic/claude-haiku-5.5` across all roles (448 development cases, 406 scored; 158 held-out cases, 143 scored).

### Overall Routing Accuracy Across All Seven Configurations (Development Set)

| Configuration | Code | 20 Agents | 160 Agents | 640 Agents | 160 Agents, Crowded |
|---|---|---:|---:|---:|---:|
| 0 · Baseline (original) | `v0` | 81% | 78% | 77% | 83% |
| 1 · Prompt Rewrite Only | `v1` | 81% | 81% | 81% | 83% |
| 2 · Description Shortlist | `v2d` | 87% | 86% | 85% | 89% |
| **3 · Work-Record Shortlist (Chosen)** | **`v2`** | **96%** | **97%** | **95%** | **95%** |
| 4 · Strict Clarification Prompt | `v3` | 94% | 94% | 91% | 91% |
| 5 · Deterministic Keyword Gate | `v4` | 91% | 90% | 91% | 85% |
| 6 · Pre-Routing LLM Judge | `v5` | 94% | 93% | 93% | 94% |

*(The crowded roster keeps 160 total agents while giving each active contact six extra tasks and ten namesakes; under strict unadjusted grading without crowding allowances, `v0` scores 68% and `v2` scores 85%.)*

### Held-Out Generalization (Single Untuned Run)

| Metric | 20 Agents | 160 Agents | 640 Agents |
|---|---:|---:|---:|
| Baseline (`v0`): Overall accuracy | 78% | 78% | 74% |
| **Work-Record Shortlist (`v2`): Overall accuracy** | **90%** | **92%** | **92%** |
| Baseline (`v0`): Clarifies when ambiguous | 47% | 42% | 33% |
| **Work-Record Shortlist (`v2`): Clarifies when ambiguous** | **92%** | **97%** | **97%** |
| Baseline (`v0`): Prompt tokens per message | 11,400 | 17,700 | 39,700 |
| **Work-Record Shortlist (`v2`): Prompt tokens per message** | **10,300** | **10,500** | **10,700** |

### Key Takeaways & Known Tradeoffs

- **Eliminates silent guessing:** Clarification recall on ambiguous requests jumps from 33–47% to 92–97%, with zero first-turn wrong-person misroutes on the held-out set.
- **Prompt tuning alone (`v1`) has zero net benefit,** while **structured tool-call records + contacts (`v2`)** outperform one-line description shortlisting (`v2d`) by 9–11 points via contact awareness, CC'd intermediary tracking, and duplicate prevention.
- **External forcing rules (`v3`, `v4`, `v5`) underperform or add unnecessary latency:** once accurate candidate records and contacts are shown, the orchestrator already clarifies reliably on its own.
- **Known limitations:** Unnecessary clarifications occur on 7% of clear held-out prompts (missing a pre-registered ≤5% target); whole-word contact matching misses nicknames like `"Wes"` for `"Wesley"` on the 40-case informal stress set (70% vs. 62% baseline); and live Google Contacts import is left as future work.

---

## Documentation Index

| Document | Contents |
|---|---|
| [report.html](report.html), [08-report.md](08-report.md) | **Main Technical Report:** benchmark design, baseline diagnosis, 7-step ablation, held-out results, limitations, and next steps |
| [01-codebase.md](01-codebase.md) | Upstream OpenPoke architecture audit, root causes of overload, and 15 codebase gaps |
| [02-solutions.md](02-solutions.md) | Design space evaluation and engineering decision log |
| [03-technical-design.md](03-technical-design.md) | Component-level specification (`store.py`, `records.py`, `lookup.py`, `decide.py`) |
| [04-eval-design.md](04-eval-design.md) | Synthetic world construction, ambiguity traps, and deterministic grading rules |
| [05-plan.md](05-plan.md) | Pre-registered execution plan and target pass thresholds |
| [06-tasks.md](06-tasks.md) | Implementation checklist |
| [07-journal.md](07-journal.md) | Chronological experiment log (hypotheses, raw runs, and post-experiment decisions) |

## Quick Verification Commands

```bash
python -m pytest tests -q                                       # 51 unit tests, zero LLM calls
python -m evals.cases.validate                                  # validate every case against world state
python -m evals.report dev                                      # print ablation tables from saved traces
python -m evals.run --world dev --version v2 --sizes 20,160,640 # live run (requires OPENROUTER_API_KEY)
```
