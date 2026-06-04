# skill-evaluate — reference

Rubric, evidence-gathering technique, and the report template for [SKILL.md](SKILL.md).

## Gathering evidence

The transcript is the ground truth that counteracts your memory's recency bias and self-serving gaps. Get it, don't recall it.

**Find the transcript JSONL.** Sessions live under `~/.claude/projects/<project-slug>/<session-id>.jsonl`, where `<project-slug>` is the cwd with path separators replaced by `-` (e.g. `C:\src\app.caivanos` → `C--src-app-caivanos`). The current session is the most-recently-modified `.jsonl` there. If session-management tools are available (e.g. a `search_session_transcripts` / `list_sessions` MCP), use them to pull the relevant turns directly.

**What the JSONL gives you that memory doesn't:**
- Exact tool-error text and **how many times** you retried before it worked (or gave up).
- **Repeated tool calls** with near-identical inputs → thrash / a loop the skill didn't bound.
- **Timestamps** → real gaps (a hang), and which phase ate the wall-clock.
- The **verbatim user messages** — every correction, "it's stuck", screenshot, or "why did it do that" is a logged failure mode. Read what they actually said, not your paraphrase.
- Where a **confirm/permission gate** fired and whether it stalled progress.

**Cheap scans (ripgrep over the JSONL):** search for `"is_error":true`, tool-result error strings, your own bail/`PushNotification` calls, and the user turns between long assistant runs. Don't read the whole file top-to-bottom — target the friction.

**If the transcript is unavailable** (compacted away, no file access): say so explicitly, evaluate from working memory + any summary, and flag that the efficiency/robustness scores are lower-confidence because the friction signals couldn't be measured.

## Rubric

Six dimensions, each scored **0–5** with a one-line evidence-cited justification. 5 = exemplary, 3 = worked with notable friction, 1 = mostly failed, 0 = N/A or total miss. The **overall verdict** is a judgment call, not an average — a Critical finding caps the overall low regardless of the other dimensions.

| # | Dimension | Measures | Evidence to look for |
|---|---|---|---|
| 1 | **Outcome fidelity** | Did the run achieve the skill's stated intended outcomes / success criteria? | Each declared outcome → met / partial / missed; was "success" real or luck-of-the-user-catching-it |
| 2 | **Autonomy** | Did it run with the *intended* human involvement — no unplanned stalls, all real gates honored, no gate that should exist missing? | Unplanned user interventions; a human gate the skill skipped; a place it asked when it should've decided (or decided when it should've asked) |
| 3 | **Efficiency** | Minimal wasted motion | Retries, dead-ends, abandoned diagnoses, redundant tool calls, phases that ran more rounds/steps than the skill implies |
| 4 | **Robustness** | Handled errors / edge cases / environment quirks without breaking or needing rescue | Hangs, unhandled errors, things that broke and required the user; whether the skill's guards caught what they should |
| 5 | **Instruction quality** | Was the skill *itself* clear, complete, unambiguous, correctly sequenced? | Moments of hesitation, a step that was ambiguous, a missing step you had to improvise, contradictory guidance, mis-ordered phases |
| 6 | **Adherence** | Did the agent actually follow the skill — and were deviations justified? | Where the run departed from the written flow; classify each departure as *good* (skill should adopt it) or *bad* (skill should prevent it) |

## Owner classification (decides what each finding becomes)

- **Skill** — the instructions are wrong, missing, ambiguous, or mis-sequenced. → becomes a **skill edit**.
- **Operator** — how the user invoked or steered it (vague brief, invoked at the wrong stage, interrupted a gate, gave a blocked issue). → becomes an **operator tip**.
- **Environment / model** — a tool limitation (background agents hang on `git push`), a platform quirk, or the agent erring *despite* clear instructions. → environment quirks may still earn a **defensive guardrail** in the skill (e.g. "do X in the foreground because background hangs"); pure model slips earn a guardrail only if cheap, else just a note.

Many real findings are a chain (e.g. *background subagent hung on push* = environment cause → *skill should make the orchestrator own the push* = skill fix). Trace the chain; fix at the cheapest durable point.

## Severity

- **Critical** — caused a failure, a wrong result, or required a user rescue to avoid one.
- **Major** — significant wasted time/tokens, or a real correctness/safety risk that didn't fire this time.
- **Minor** — friction or rough edges; the run survived.
- **Polish** — wording, clarity, nice-to-have.

## Report template

```markdown
## 🔍 skill-evaluate: <skill-name>

**Verdict:** <1–2 sentences — did it do its job, and the single most important improvement.>

| Dimension | Score | Why |
|---|---|---|
| Outcome fidelity | n/5 | … |
| Autonomy | n/5 | … |
| Efficiency | n/5 | … |
| Robustness | n/5 | … |
| Instruction quality | n/5 | … |
| Adherence | n/5 | … |
| **Overall** | **n/5** | … |

### ✅ What went well (worth codifying)
- <pattern that worked — especially good improvisations the skill should adopt>

### 🔧 Findings
| # | Finding | Evidence (transcript ref) | Owner | Severity | Fix |
|---|---|---|---|---|---|
| 1 | <what> | <error / retry×N / user said "…" / phase ran N rounds> | skill/operator/env | Critical/Major/Minor/Polish | <concrete> |

### ✏️ Proposed skill edits
For each skill-owned finding — the file, the section, and the concrete change (new text or before→after), ready to apply:
- **`<file>` → `<section>`:** <what to change and the exact wording>

### 🧑‍✈️ Operator tips (run it better)
- <how the user could invoke/steer it to avoid the operator-owned friction>
```

## Notes

- Works on **any** skill — domain skills, orchestrators, planning skills. For a delegating orchestrator (like `/handle-it`), evaluate the bundled agents and sub-skills it invoked too; a finding may belong to a sub-skill's file.
- A clean run gets a short report — scorecard + "what went well" + maybe a polish note or two. Length should track the friction found, not a fixed format quota.
- Keep proposed edits **smallest-effective**: a one-line guard or a reordered step beats a rewrite. Flag when a finding genuinely needs a larger restructure rather than papering it with a guard.
