---
name: claudecodile-review
description: 🐊 Claudecodile in-house code review. Runs an iterate-until-5/5 review⇄fix loop on a PR — an Opus reviewer posts P#-tagged inline comments with suggested fixes and maintains one rating comment; a Sonnet fixer applies them; loops until 5/5 (no P0/P1). Use when the user invokes /claudecodile-review on a PR, or when another skill (e.g. /handle-it) delegates its review phase here.
---

# claudecodile-review

You drive an **in-house review⇄fix loop** on one PR until it rates **🐊 5/5**, then return. You are the **caller/loop driver** running in the current conversation — you spawn the reviewer and fixer subagents and **own every git mutation** (commit + push between rounds). The subagents are edit-/comment-only and never touch git; doing the commits/pushes yourself in this context is what keeps the optimistic, prompt-driven git flow working (background subagents hang on `git push`).

**Project specifics come from config.** This skill is project-generic: the **verify gate** the fixer re-runs and the **hard-rule files** that trigger a handback both come from **`.claude/handle-it.md`** in the repo (the same config `handle-it` uses; written by `/handle-it-project-setup`). Read it at the start; pass the verify gate + hard-rule list into the fixer. If the config is missing, ask the user to run `/handle-it-project-setup` (or, for a one-off, ask them for the verify command and proceed). When a config value proves wrong at runtime, fix the field and note it under the config's **Learned corrections** (see REFERENCE → Keeping the config accurate).

Mechanics, the HEREDOC posting rules, and the standalone-vs-delegated contract live in **[REFERENCE.md](REFERENCE.md)**.

## Inputs

The caller (a user, or a delegating skill like `/handle-it`) provides:
- **Worktree path** (absolute) — the branch is checked out here; all git runs with this as cwd.
- **PR number**.
- *(Optional)* **RATING_COMMENT_ID** + **score history** — when resuming an in-flight review. If omitted, the reviewer auto-discovers an existing `## 🐊 Claudecodile Rating:` comment on the PR (or posts a fresh one on round 1).

If invoked with just a PR number and no worktree, derive the worktree from the PR's branch (the config's worktree-list command, or `git worktree list`); if none exists, ask the caller for the path.

## The 5/5 rule

**`5/5 = no P0/P1 remain AND every in-scope P2/P3 has been fixed.`** Priorities: `[P0]` breaking / data loss · `[P1]` important correctness · `[P2]` quality · `[P3]` nit.

P2/P3 are not free passes — **fix every useful, localized, non-scope-changing nit.** The only P2/P3 allowed to remain at 5/5 are ones the reviewer tags `(defer — scope)` because fixing them would bloat the issue's scope; each is recorded in the rating comment's **Deferred (out of scope)** section (recommend a follow-up issue if important, else just a note). While any `(in-scope)` P2/P3 is unfixed, the score caps at **4/5**. The reviewer makes the in-scope-vs-scope call and tags each nit; the fixer fixes the in-scope ones. (The plateau guard, below, still catches genuine thrash on a subjective nit.)

## The loop

No hard round cap (but see the plateau guard). The PR's draft/ready state is the caller's concern — this skill doesn't change it.

1. **Review** → spawn **`swatkinson-toolkit:claudecodile-reviewer`** (Opus) via `Agent(subagent_type: …)`, passing the PR number, the round number, the running **score history**, and (after round 1) the held **RATING_COMMENT_ID**. It runs `code-review` (HIGH), posts **P#-tagged inline comments, each with a suggested fix** (` ```suggestion ` blocks for small ones), then posts/edits the ONE `## 🐊 Claudecodile Rating: N/5` comment (score-history line + P#-grouped summary). **Round 1 only:** it also runs `simplify` and posts each finding as a `[Simplify Suggestion]` inline comment (no P# prefix) — these are posted alongside the P#-tagged findings in the same pass; the Fixer applies them too. On later rounds it also **resolves the inline thread of every finding it verifies is fixed** — a fixed comment is never left open, only marked-fixed-but-dangling. **Round 1 = full diff (+ simplify); later rounds = incremental diff only (no simplify re-run).** **Capture the rating-comment id from round 1's report and hold it** for every later round.
   - **Verify the reviewer actually posted (don't trust the report alone).** The reviewer's job is the GitHub writes, not the findings text — a known failure mode is returning a clean findings array while posting nothing. After it returns, confirm its writes landed: a `## 🐊 Claudecodile Rating:` comment exists, and (when it reported findings) inline comments exist for this round — e.g. `gh pr view <N> --json comments` and `gh api repos/:owner/:repo/pulls/<N>/comments`. If the reviewer reported findings but no inline comments / rating comment are on the PR, **re-spawn it with an explicit instruction that the writes are the deliverable and it must post them** — do not proceed to the fixer on un-posted findings.
2. **5/5 (no P0/P1)?** → run **one final FULL-diff review** (`swatkinson-toolkit:claudecodile-reviewer`, full pass) to catch cross-cutting regressions the incremental view hides. Still 5/5 → **return success** — but first confirm no inline thread for a fixed finding is still open (the reviewer resolves these each round; if any linger, resolve them before returning). Else keep looping. Never declare 5/5 on an *incremental* round. **Exception — round 1 was already a clean full pass:** if round 1 (which is always a full diff) found nothing and applied no fixes, *it is* the final full pass — return 5/5 immediately; don't run a redundant second full review on an unchanged diff.
3. **Else fix** → spawn **`swatkinson-toolkit:claudecodile-fixer`** (Sonnet) with the worktree path + PR number + **the config's verify gate + hard-rule file list**; it applies the suggested fixes (every P0/P1 **and** every `(in-scope)` P2/P3; leaves only the `(defer — scope)` nits), re-runs the verify gate, and **reports back — does NOT commit or push.** **You commit + push** the fix from the foreground (cwd = worktree). Genuine-bail only (product decision / hard-rule file) → return a **handback bail**.
4. Re-run the reviewer (step 1, incremental) on the now-pushed diff. Loop.

**Plateau guard.** Track the score per round. If it doesn't improve across **2 consecutive rounds** (same score, same class of open comments) — reviewer and fixer are thrashing — stop and return a **plateau bail** (the caller decides: accept-as-is / guide / keep iterating; a standalone user invocation surfaces this via `AskUserQuestion`). Not a round cap — 5/5 stays the goal; an escape from a non-converging loop.

## Git (you own it)

Between every reviewer→fixer→reviewer step **you** commit (Conventional Commit, e.g. `fix(scope): address review`) + push from the worktree. The subagents never run git. When delegated by `/handle-it`, this runs in the orchestrator's context, so its foreground push/commit allow-list applies. **Never** push to the base branch, amend, `--no-verify`, or force-push.

## Return contract

Report back to the caller in a structured summary:
- **outcome:** `5/5` · `plateau-bail` · `handback-bail`
- **finalRating** (N/5) and the **rating-comment id/URL** (so a delegating caller can keep editing it / link it).
- **p2p3FollowUps:** only the scope-deferred P2/P3 left open (with the reviewer's follow-up-issue recommendation or note for each). In-scope P2/P3 were fixed, not deferred.
- **handbackItems:** any product-decision / hard-rule comments the fixer couldn't address (on a handback bail).
- **rounds:** how many review rounds ran, with the score history.

## Hard rules

- Never edit a **hard-rule file** (config → Hard-rule files — auth, permissions, env/secret handling, deploy config) → handback bail.
- Never push to the base branch, merge, amend, `--no-verify`, or force-push.
- The `## 🐊 Claudecodile Rating:` comment is a PR *issue* comment — never delete or resolve it; it's the loop's authoritative scoreboard and stays on the PR.
