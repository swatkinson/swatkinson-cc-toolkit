---
name: swat-review
description: 🪰 Swat Reviewer in-house code review — ONE pass over a PR. An Opus reviewer does its own in-house diff review (no external code-review/simplify skill), posts P#-tagged inline comments with suggested fixes, and posts/updates the single rating comment scoring three facets (Code Quality, Spec. Adherence, Risk and Complexity). It does NOT fix or loop — re-run it (a human, /handle-it's loop, or a swat-reviewer GitHub Action) to advance toward the double-5/5 gate. Use when the user invokes /swat-review on a PR, when /handle-it delegates a review pass, or as the step a swat-reviewer GitHub Action runs.
---

# swat-review

You run **ONE review pass** over a PR, then return. You spawn the Opus reviewer subagent, confirm it posted, and report the resulting scores. **You do NOT fix, you do NOT loop, you do NOT touch git** — those belong to the *caller* (a human, `/handle-it`'s Phase-6 loop, or the repo's swat-reviewer GitHub Action), which re-runs you after each fix until the gate is met.

This skill is **stateless across passes** but **aware of looping**: it reads any existing `## 🪰 Swat Reviewer Rating` comment so a re-run shows the score progression (`4·3 → 4·5 → 5·5`), marks now-fixed findings `[FIXED]` and resolves their threads, and doesn't re-post still-open findings — so a series of single passes behaves like the old internal loop, just driven from outside.

**Project specifics come from config.** The **comment formats** come from **`.claude/handle-it/rules/rating-comment.md`** + **`rules/inline-comments.md`**, written by `/handle-it-project-setup`. Pass those two rule files (or their paths) to the reviewer. If the directory is missing, ask the user to run `/handle-it-project-setup` (or, for a one-off, the reviewer uses its built-in default formats). When a rule proves wrong at runtime, fix the relevant `rules/*.md` and note it under **Learned corrections** (see REFERENCE → Keeping the config accurate).

Mechanics, the HEREDOC posting rules, and the standalone-vs-delegated-vs-CI contract live in **[REFERENCE.md](REFERENCE.md)**.

## Inputs

The caller (a user, `/handle-it`, or a CI action) provides:
- **Worktree path** (absolute) — where the branch is checked out (so the reviewer can read the code). If only a PR number is given, derive it from the PR's branch (the config's worktree-list command, or `git worktree list`); if none exists, check out / ask for the path.
- **PR number**.
- **Issue / spec context** — the feature / PRD / acceptance criteria the change is meant to satisfy, so the reviewer can score **Spec. Adherence**. `/handle-it` passes the issue brief; standalone / CI, the reviewer derives it from the PR's linked issue + the **Why** section of the description.
- *(Optional)* **RATING_COMMENT_ID** — when the caller already holds it. If omitted, the reviewer auto-discovers an existing `## 🪰 Swat Reviewer Rating` comment on the PR (and edits it) or posts a fresh one.

## The three facets + the gate

The reviewer scores **three facets** in the `## 🪰 Swat Reviewer Rating` comment (full template + rubric in `rules/rating-comment.md`):
- **Code Quality** (N/5) — correctness, security, performance, design, **and** adherence to the rest of the codebase (matching sibling features' schema / perms / UI patterns, and reusing existing code rather than reinventing it).
- **Spec. Adherence** (N/5) — how well the change solves the feature / PRD / issue it's for (`5` = adheres greatly, `0` = missed the plot), judged against the issue/spec context.
- **Risk and Complexity** (N/5, 5 = safest) — how likely a bug is lurking (complexity) **and** how bad it'd be if one shipped (blast radius) — not a quality judgment.

**The gate the *caller* loops toward is `Code Quality = 5/5 AND Spec. Adherence = 5/5`** (double-5/5). **Risk and Complexity never gates** — it rides along as advice for the human reviewer. This skill doesn't enforce the gate; it just scores the current state honestly so the caller can decide whether to fix-and-re-run.

For each gating facet, `5/5 = no P0/P1 in that facet AND every in-scope P2/P3 in it fixed`. Priorities: `[P0]` breaking / data loss · `[P1]` important correctness · `[P2]` quality · `[P3]` nit. Every fixable finding is tagged with its **facet** (`[Quality]`/`[Spec]`) and (for P2/P3) a **scope tag**; `[Risk]` annotations are advisory. Only `(defer — scope)` nits may remain at 5/5 (recorded in the rating comment's **Deferred** section); while any in-scope P2/P3 in a gating facet is open, that facet caps at **4/5**.

## The pass

1. **Review** → spawn **`swatkinson-toolkit:swat-reviewer`** (Opus) via `Agent(subagent_type: …)`, passing the PR number, the **issue/spec context**, the **comment-format rule files** (`rules/inline-comments.md` + `rules/rating-comment.md`), and the **RATING_COMMENT_ID** if you hold it. It performs its **own in-house review** of the PR's current full diff (correctness / security / perf / design + codebase-consistency & reuse + spec adherence — **no** external `code-review`/`simplify` skill), then:
   - posts **inline comments per `rules/inline-comments.md`** for *new* findings (P# + `[Quality]`/`[Spec]` facet tag + scope tag + ` ```suggestion ` blocks for small ones, plus advisory `[Risk]` annotations) — it does **not** duplicate a finding that already has an open thread;
   - **marks now-fixed findings `[FIXED]` and resolves their inline threads** (reads the prior rating comment + open threads to know what was previously flagged);
   - posts/edits the ONE `## 🪰 Swat Reviewer Rating` comment **per `rules/rating-comment.md`**, appending this pass's scores to the `Score history` line.
2. **Verify the reviewer actually posted** (don't trust the report alone — a known failure mode is returning findings while posting nothing). Confirm a `## 🪰 Swat Reviewer Rating` comment exists and, when findings were reported, inline comments exist (`gh pr view <N> --json comments`, `gh api repos/:owner/:repo/pulls/<N>/comments`). If it reported findings but posted nothing, **re-spawn it with an explicit instruction that the writes are the deliverable**.
3. **Return** the scores + rating-comment id + open findings (below). That's the whole job — do not fix, do not re-review, do not commit.

## Return contract

Report back to the caller in a structured summary:
- **rating:** the three facet scores — **Code Quality N/5, Spec. Adherence N/5, Risk and Complexity N/5** (with the one-line Risk rationale).
- **gatePassed:** `true` iff Code Quality 5/5 AND Spec. Adherence 5/5.
- **ratingCommentId / URL** — so the caller can hold it and pass it back next pass.
- **openFindings:** the still-open P#-tagged findings (id, facet, priority, scope tag, file:line) the caller's fixer should address this round.
- **scopeDeferred:** the `(defer — scope)` P2/P3 recorded in Deferred (with each follow-up-issue recommendation / note).
- **handbackItems:** any finding needing a product decision or a hard-rule-file edit (the caller can't auto-fix these).

## Hard rules

- **Comment/review only — never edit code, commit, push, or change the PR's draft state.** Fixing and git belong to the caller.
- The `## 🪰 Swat Reviewer Rating` comment is a PR *issue* comment — never delete or resolve it; it's the authoritative scoreboard and stays on the PR.
- Post comment bodies as HEREDOC-literal strings — never `--body "@path"` / `-f body=@path` (REFERENCE → HEREDOC posting).
