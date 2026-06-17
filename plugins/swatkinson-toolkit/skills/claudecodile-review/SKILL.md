---
name: claudecodile-review
description: 🐊 Claudecodile in-house code review. Runs an iterate-until-pass review⇄fix loop on a PR — an Opus reviewer does its own in-house diff review (no external code-review/simplify skill), posts P#-tagged inline comments with suggested fixes, and maintains one rating comment scoring three facets (Code Quality, Spec. Adherence, Risk and Complexity); a Sonnet fixer applies them; loops until the two gating facets (Quality, Spec) are each 5/5 (Risk is advisory). Use when the user invokes /claudecodile-review on a PR, or when another skill (e.g. /handle-it) delegates its review phase here.
---

# claudecodile-review

You drive an **in-house review⇄fix loop** on one PR until it rates **🐊 Code Quality 5/5 AND Spec. Adherence 5/5** (a third facet, **Risk and Complexity**, is scored but advisory — it never gates), then return. You are the **caller/loop driver** running in the current conversation — you spawn the reviewer and fixer subagents and **own every git mutation** (commit + push between rounds). The subagents are edit-/comment-only and never touch git; doing the commits/pushes yourself in this context is what keeps the optimistic, prompt-driven git flow working (background subagents hang on `git push`).

**Project specifics come from config.** This skill is project-generic: the **verify gate** the fixer re-runs and the **hard-rule files** that trigger a handback come from **`.claude/handle-it/config.md`**, and the **comment formats** come from **`.claude/handle-it/rules/rating-comment.md`** + **`rules/inline-comments.md`** (the same `.claude/handle-it/` directory `handle-it` uses; written by `/handle-it-project-setup`). Read them at the start; pass the verify gate + hard-rule list into the fixer, and the two rule files (or their paths) into the reviewer. If the directory is missing, ask the user to run `/handle-it-project-setup` (or, for a one-off, ask for the verify command and use the built-in default formats). When a config value or a rule proves wrong at runtime, fix it and note it under **Learned corrections** (see REFERENCE → Keeping the config accurate).

Mechanics, the HEREDOC posting rules, and the standalone-vs-delegated contract live in **[REFERENCE.md](REFERENCE.md)**.

## Inputs

The caller (a user, or a delegating skill like `/handle-it`) provides:
- **Worktree path** (absolute) — the branch is checked out here; all git runs with this as cwd.
- **PR number**.
- **Issue / spec context** — the feature / PRD / acceptance criteria the change is meant to satisfy, so the reviewer can score **Spec. Adherence**. A delegating `/handle-it` passes the issue brief; standalone, the reviewer derives it from the PR's linked issue + the **Why** section of the description.
- *(Optional)* **RATING_COMMENT_ID** + **score history** — when resuming an in-flight review. If omitted, the reviewer auto-discovers an existing `## 🐊 Claudecodile Rating` comment on the PR (or posts a fresh one on round 1).

If invoked with just a PR number and no worktree, derive the worktree from the PR's branch (the config's worktree-list command, or `git worktree list`); if none exists, ask the caller for the path.

## The three facets + the exit rule

The reviewer scores **three facets** in the `## 🐊 Claudecodile Rating` comment (full template + rubric in `rules/rating-comment.md`):
- **Code Quality** (N/5) — correctness, security, performance, design, **and** adherence to the rest of the codebase (matching sibling features' schema / perms / UI patterns, and reusing existing code rather than reinventing it).
- **Spec. Adherence** (N/5) — how well the change solves the feature / PRD / issue it's for (`5` = adheres greatly, `0` = missed the plot), judged against the issue/spec context.
- **Risk and Complexity** (N/5, 5 = safest) — how likely a bug is lurking (complexity) **and** how bad it'd be if one shipped (blast radius) — not a quality judgment.

**The loop's exit condition is `Code Quality = 5/5 AND Spec. Adherence = 5/5`.** **Risk and Complexity never gates** the loop or the plateau guard — it's inherent to the change, not something the fixer can fix; it rides along as advice for the human reviewer.

For each **gating** facet, `5/5 = no P0/P1 in that facet AND every in-scope P2/P3 in it fixed`. Priorities: `[P0]` breaking / data loss · `[P1]` important correctness · `[P2]` quality · `[P3]` nit. Every fixable finding is tagged with its **facet** (`[Quality]`/`[Spec]`) and (for P2/P3) a **scope tag**; `[Risk]` annotations are advisory and not fixed. The fixer fixes every `(in-scope)` nit in either gating facet; only `(defer — scope)` nits may remain (recorded in the rating comment's **Deferred** section). While any in-scope P2/P3 in a gating facet is unfixed, that facet caps at **4/5**. A **Spec** gap too large for the fixer (a feature-sized "missed the plot") is a **handback bail** — the caller decides (in `/handle-it`, it re-routes to the implementer). (The plateau guard, below, still catches genuine thrash.)

## The loop

No hard round cap (but see the plateau guard). The PR's draft/ready state is the caller's concern — this skill doesn't change it.

1. **Review** → spawn **`swatkinson-toolkit:claudecodile-reviewer`** (Opus) via `Agent(subagent_type: …)`, passing the PR number, the round number, the running **score history** (Quality · Spec), the **issue/spec context**, the **comment-format rule files** (`rules/inline-comments.md` + `rules/rating-comment.md`), and (after round 1) the held **RATING_COMMENT_ID**. It performs its **own in-house review** of the diff (correctness / security / perf / design + codebase-consistency & reuse + spec adherence — it does **not** call any external `code-review`/`simplify` skill), posts **inline comments formatted per `rules/inline-comments.md`** (P# prefix + `[Quality]`/`[Spec]` facet tag + scope tags + ` ```suggestion ` blocks for small ones, plus advisory `[Risk]` annotations), then posts/edits the ONE `## 🐊 Claudecodile Rating` comment **per `rules/rating-comment.md`** (Code Quality, Spec. Adherence, Risk and Complexity). On later rounds it also **resolves the inline thread of every finding it verifies is fixed** — a fixed comment is never left open, only marked-fixed-but-dangling. **Round 1 = full diff; later rounds = incremental diff only.** **Capture the rating-comment id from round 1's report and hold it** for every later round.
   - **Verify the reviewer actually posted (don't trust the report alone).** The reviewer's job is the GitHub writes, not the findings text — a known failure mode is returning a clean findings array while posting nothing. After it returns, confirm its writes landed: a `## 🐊 Claudecodile Rating` comment exists, and (when it reported findings) inline comments exist for this round — e.g. `gh pr view <N> --json comments` and `gh api repos/:owner/:repo/pulls/<N>/comments`. If the reviewer reported findings but no inline comments / rating comment are on the PR, **re-spawn it with an explicit instruction that the writes are the deliverable and it must post them** — do not proceed to the fixer on un-posted findings.
2. **Quality 5/5 AND Spec 5/5?** (Risk and Complexity is ignored here) → run **one final FULL-diff review** (`swatkinson-toolkit:claudecodile-reviewer`, full pass) to catch cross-cutting regressions the incremental view hides. Still passing → **return success (`pass`)** — but first confirm no inline thread for a fixed finding is still open (the reviewer resolves these each round; if any linger, resolve them before returning). Else keep looping. Never declare `pass` on an *incremental* round. **Exception — round 1 was already a clean full pass:** if round 1 (which is always a full diff) found nothing and applied no fixes, *it is* the final full pass — return `pass` immediately; don't run a redundant second full review on an unchanged diff.
3. **Else fix** → spawn **`swatkinson-toolkit:claudecodile-fixer`** (Sonnet) with the worktree path + PR number + **the config's verify gate + hard-rule file list**; it applies the suggested fixes (every P0/P1 **and** every `(in-scope)` P2/P3; leaves only the `(defer — scope)` nits), re-runs the verify gate, and **reports back — does NOT commit or push.** **You commit + push** the fix from the foreground (cwd = worktree). Genuine-bail only (product decision / hard-rule file) → return a **handback bail**.
4. Re-run the reviewer (step 1, incremental) on the now-pushed diff. Loop.

**Plateau guard.** Track the **Quality + Spec** scores per round (Risk and Complexity is excluded — it doesn't move with fixes). If neither improves across **2 consecutive rounds** (same scores, same class of open comments) — reviewer and fixer are thrashing — stop and return a **plateau bail** (the caller decides: accept-as-is / guide / keep iterating; a standalone user invocation surfaces this via `AskUserQuestion`). Not a round cap — the pass gate stays the goal; an escape from a non-converging loop.

## Git (you own it)

Between every reviewer→fixer→reviewer step **you** commit (Conventional Commit, e.g. `fix(scope): address review`) + push from the worktree. The subagents never run git. When delegated by `/handle-it`, this runs in the orchestrator's context, so its foreground push/commit allow-list applies. **Never** push to the base branch, amend, `--no-verify`, or force-push.

## Return contract

Report back to the caller in a structured summary:
- **outcome:** `pass` (Quality & Spec both 5/5) · `plateau-bail` · `handback-bail`
- **finalRating:** the three facet scores — **Code Quality N/5, Spec. Adherence N/5, Risk and Complexity N/5** (with a one-line Risk rationale) — and the **rating-comment id/URL** (so a delegating caller can keep editing it / link it).
- **p2p3FollowUps:** only the scope-deferred P2/P3 left open (with the reviewer's follow-up-issue recommendation or note for each). In-scope P2/P3 were fixed, not deferred.
- **handbackItems:** any product-decision / hard-rule comments the fixer couldn't address (on a handback bail).
- **rounds:** how many review rounds ran, with the score history.

## Hard rules

- Never edit a **hard-rule file** (config → Hard-rule files — auth, permissions, env/secret handling, deploy config) → handback bail.
- Never push to the base branch, merge, amend, `--no-verify`, or force-push.
- The `## 🐊 Claudecodile Rating` comment is a PR *issue* comment — never delete or resolve it; it's the loop's authoritative scoreboard and stays on the PR.
