# claudecodile-review — reference

Mechanics and runtime details for [SKILL.md](SKILL.md). This skill is **one review pass** over a PR — it scores the current state and posts/updates comments. It does **not** fix or loop; the *caller* (a human, `/handle-it`, or a claudecodile GitHub Action) re-runs it after each fix until the double-5/5 gate.

## The reviewer (one agent)

`claudecodile-reviewer` (Opus) is a **pre-built subagent bundled with this plugin** (`agents/`) — invoke via `Agent(subagent_type: "swatkinson-toolkit:claudecodile-reviewer")` (the plugin namespaces it; a bare name won't resolve once installed). It does its **own in-house review** of the PR's current diff (no external `code-review`/`simplify` skill), posts one inline comment per *new* finding **formatted per `rules/inline-comments.md`** (`[P0]`–`[P3]` + `[Quality]`/`[Spec]` facet tag + scope tag + a ` ```suggestion ` block where it applies; plus optional advisory `[Risk]` annotations), **marks now-fixed findings `[FIXED]` and resolves their threads**, and maintains exactly **one** `## 🐊 Claudecodile Rating` comment **per `rules/rating-comment.md`**. Comments only — never code, git, or PR-state. If the rule files are absent it falls back to its built-in default formats.

**The fixer moved out.** `claudecodile-fixer` is now spawned by **`/handle-it`** (its Phase-6 fix loop), not by this skill — see the handle-it docs. This skill never fixes.

## Standalone vs delegated vs CI

This skill is the same review pass however it's driven:

- **Standalone** (`/claudecodile-review` invoked by a user on a PR): you do one pass and report. The user reads the rating comment and decides what to do; nothing is fixed automatically.
- **Delegated** (`/handle-it` Phase 6, **local mode**): handle-it calls `Skill(swatkinson-toolkit:claudecodile-review)` for one pass, then runs the fixer + commits + pushes itself, then calls this skill again — looping to the gate. The loop, plateau guard, and git all live in handle-it now.
- **CI** (the repo's claudecodile **GitHub Action**, config `Claudecodile runs in CI = true`): the Action runs this same review pass on each push and posts/updates the rating comment. handle-it then does **not** call this skill — it waits for the Action's review, fixes, pushes (re-triggering the Action), and loops. See handle-it REFERENCE → Review ⇄ fix loop.

In every case the pass is identical: review the current diff, update the one rating comment, resolve fixed threads, report scores.

## Rating comment — one, edited in place, shows progression

The `## 🐊 Claudecodile Rating` comment is the **authoritative scoreboard** and stays on the PR (it's a PR *issue* comment, never resolved/deleted). It scores three facets per `rules/rating-comment.md` — **Code Quality** (incl. codebase-consistency & reuse), **Spec. Adherence**, **Risk and Complexity** — and the caller reads `Quality 5/5 AND Spec 5/5` from it to decide whether to stop.

- **Progression across passes:** each pass appends to the `Score history (Quality · Spec): …` line (`4·3 → 4·5 → 5·5`) and flips addressed findings to `[FIXED]`, so the single comment tells the whole story even though each invocation is independent.
- **Hold the rating-comment id** and pass it back as `RATING_COMMENT_ID` so the reviewer edits that one comment. If not passed, the reviewer auto-discovers the existing `## 🐊 Claudecodile Rating` issue comment (`gh pr view <N> --json comments` / `gh api repos/:owner/:repo/issues/comments`) and edits it — never posts a second.

**HEREDOC-literal posting (critical).** Pass comment bodies as a LITERAL string via inline HEREDOC — NEVER `--body "@path"` or `-f body=@path`, which post the literal path text (this is how rating comments came out as `@C:/…/.rating.txt` garbage in canary testing):
- post: `gh pr comment <N> --body "$(cat <<'EOF' … EOF )"`
- edit: `gh api repos/:owner/:repo/issues/comments/<id> -X PATCH -f body="$(cat <<'EOF' … EOF )"`

If you must read a body from a file use ONLY the file-reading flags — `--body-file <path>`, or `gh api … -F body=@<path>` (capital `-F`) — never `--body`/`-f` with an `@path`. **After posting/editing, re-read the comment and confirm it shows the content, not a path.**

## Resolving fixed threads (each pass)

A fixed finding must not linger as an open inline thread — the bug we're closing is marking a comment "FIXED" in the summary while the thread stays open on the PR. Two distinct comment types, two distinct rules:

- **Inline review threads** (the per-finding comments) → each pass, the reviewer **resolves** the thread of every finding it verifies fixed in the current diff. It only resolves what it actually verified; an unfixed (or re-broken) finding keeps its thread open. Recipe:
  ```bash
  # list open threads + first comment (path/body) to match against confirmed-fixed findings
  gh api graphql -f query='query($o:String!,$r:String!,$n:Int!){repository(owner:$o,name:$r){pullRequest(number:$n){reviewThreads(first:100){nodes{id isResolved comments(first:1){nodes{path body}}}}}}}' -F o=<owner> -F r=<repo> -F n=<N>
  # resolve a verified-fixed thread (resolve, never delete — preserves the flagged→fixed history)
  gh api graphql -f query='mutation($t:ID!){resolveReviewThread(input:{threadId:$t}){thread{isResolved}}}' -F t=<thread-id>
  ```
- **The `## 🐊 Claudecodile Rating` comment** is a PR *issue* comment, not a review thread → `resolveReviewThread` can't touch it and it's **never** resolved or deleted; it stays as the scoreboard.

## What the caller does with the result

This skill returns scores + open findings (SKILL → Return contract). The caller (handle-it or a human) decides:
- **gate passed** (Quality 5/5 AND Spec 5/5) → done; stop re-running.
- **else** → run the fixer on the open findings, commit + push, re-run this skill (or, in CI, let the Action re-run on the push). handle-it owns the plateau guard (no Quality/Spec improvement across 2 rounds → bail) and the handback case (a finding needing a product decision or a hard-rule-file edit).

## Keeping the config accurate

The comment formats come from `.claude/handle-it/rules/rating-comment.md` + `rules/inline-comments.md`. If a comment format proves wrong at runtime (the tracker mangled it, a required section was missing), `Edit` the relevant `rules/*.md` and append a dated line to `config.md` → **Learned corrections** — the same self-correction contract `handle-it` uses, so both keep the shared `.claude/handle-it/` directory true.
