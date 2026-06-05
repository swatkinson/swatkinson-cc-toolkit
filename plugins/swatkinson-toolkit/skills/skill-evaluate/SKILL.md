---
name: skill-evaluate
description: Retrospective self-evaluation of a skill you just ran. Reconstructs the skill's intended goals, reconstructs what ACTUALLY happened from the session transcript (errors, retries, stalls, hangs, user interventions, deviations), scores the run against a 6-dimension rubric, root-causes each friction point, and proposes concrete edits to the skill file plus ways the operator could run it better. Use at the end of a skill run, when the user invokes /skill-evaluate, or asks "how well did that skill go", "how could this skill be improved", "evaluate that run", "what slowed that down".
---

# skill-evaluate

You just ran a skill (or are wrapping one up). Turn the critical eye on the **skill itself**: did it do what it was built to do, where did it create friction, and how should its instructions change so the next run is smoother, faster, and more robust. Produce the grounded, evidence-cited retrospective a careful engineer writes after an incident — not a self-congratulatory recap.

**Core stance — three rules that make this useful instead of noise:**
1. **Every claim is backed by evidence** from what actually happened (a tool error, a retry count, a user correction, a ballooned phase). No invented problems; no glossing over real ones. If the run was clean, say so briefly — don't manufacture findings.
2. **Separate the three failure owners** that are easy to conflate: the **skill** (instructions wrong / missing / ambiguous / mis-sequenced), the **operator** (how the user invoked or steered it), and the **environment/model** (tool limits, or the agent erring *despite* clear instructions). Only skill-owned findings become skill edits; the rest become operator tips or defensive guardrails.
3. **Fix the friction you observed, not speculative gold-plating.** A proposed edit must trace to a real moment in this run. Also promote *good improvisations* — things the agent did that worked but the skill never told it to — into the skill.

The rubric, the evidence-gathering technique, and the report template live in **[REFERENCE.md](REFERENCE.md)** — load it in Phase 2.

## Phase 1 — Identify the target + reconstruct intent

1. **Which skill?** Explicit arg (`/skill-evaluate handle-it`) → that one. Else infer the skill that dominated this session. Multiple skills ran or it's ambiguous → ask which (or offer to evaluate each).
2. **Read the skill as-built.** Load its `SKILL.md` **and** everything it bundles — `REFERENCE.md`, any agent files it spawns (bundled in the skill's plugin under `agents/`, or under `~/.claude/agents/` for user-level skills), sub-skills it delegates to. Extract its **spec**: stated purpose, intended outcomes / success criteria, the phase/step flow, hard rules + invariants, and the human gates it *intends* to have. This is what you grade the run against.

## Phase 2 — Reconstruct what actually happened (ground truth, not memory)

Your working memory of the run is recency-biased and self-serving — it forgets your own wasted steps and smooths over stalls. **Back it with the transcript.**

1. Locate this session's transcript JSONL (under `~/.claude/projects/<project-slug>/`, most-recently-modified; or use the session-management search tools if available). See REFERENCE → Gathering evidence.
2. Scan for the **friction signals**, timestamped where it matters:
   - Tool **errors** and the **retries** that followed; the same/near-duplicate tool call repeated (thrash).
   - **Hangs / stalls** (long gaps, a tool that never returned, a background agent stuck).
   - **Permission denials** and confirm-gate stumbles.
   - **Bail points** and dead-ends (a wrong diagnosis pursued then abandoned).
   - **The highest-value signal: every place the user had to intervene** — correct you, repeat themselves, paste a screenshot of a bug, or say "that's wrong / it's stuck / why did it do that". Each is a skill or operator failure mode.
   - **Phase bloat:** a step/round-count or wall-time far above what the skill implies (e.g. a 2-round loop that ran 6).
3. Map each signal to the skill phase it occurred in.

## Phase 3 — Score + root-cause

1. **Score against the 6-dimension rubric** (REFERENCE → Rubric): Outcome fidelity · Autonomy · Efficiency · Robustness · Instruction quality · Adherence. Each 0–5 with a one-line justification citing evidence, plus an honest overall verdict (not a blind average).
2. **For each finding:** state the evidence (with a transcript reference), assign the **owner** (skill / operator / environment-model), a **severity** (Critical = caused a failure or rescue · Major = significant wasted time or real risk · Minor = friction · Polish), and the **concrete fix**.

## Phase 4 — Report

Write the report using the template in REFERENCE → Report template: verdict + scorecard, **what went well** (codify-worthy), the **findings table**, **proposed skill edits** (file + section + concrete new/changed text, ready to apply), and **operator tips** (how the user can run it better next time).

## Phase 5 — Offer to apply

Editing a skill is a real change — **don't silently rewrite it.** Group the proposed skill edits by confidence (high-confidence/mechanical vs. judgment-call) and offer to apply them, waiting for the user's go-ahead. Apply only what they approve; leave operator tips and environment notes as advice. If the evaluated skill is the one that's *currently running*, prefer to hand back the report and let the user run the edits as a separate pass rather than editing mid-flight.

## Principles

- **Be specific and falsifiable.** "Phase 6 looped 6× (rounds 3–6 added no new findings)" beats "the review felt slow."
- **Grade the skill, not the outcome's luck.** A run that succeeded only because the user caught a bug is a skill *failure* to surface.
- **Don't conflate a deviation with a defect.** If you departed from the skill and it worked better, the skill should adopt your path — that's a finding, not an apology.
- **Smallest effective edit.** Prefer a one-line guard or a reordered step over a rewrite; note when a bigger restructure is genuinely warranted.
