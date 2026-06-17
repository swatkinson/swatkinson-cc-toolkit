<!--
  Default seed for `.claude/handle-it/rules/rating-comment.md`. Setup copies it into the repo
  (stripping this comment). Used by claudecodile-review's reviewer. Keep the section headings.
-->

## About

The single `## 🐊 Claudecodile Rating` issue comment the reviewer maintains on the PR — the authoritative scoreboard for the review⇄fix loop's exit. Exactly **one** per PR, edited in place across rounds.

## Template

```
## 🐊 Claudecodile Rating: <N>/5

Score history: <a → b → … → N>

### Findings
- [P0] <breaking / data-loss issue> — <status: open / FIXED>
- [P1] <important correctness issue> — <status>
- [P2] <quality issue> (in-scope) — <status>
- [P3] <nit> (in-scope) — <status>

### Deferred (out of scope)
- [P3] <nit> (defer — scope) — follow-up issue recommended: <why> / or: note only
```

## Rules

- Edit the **layout** below the first line freely — how Findings are grouped, the Score-history rendering, the Deferred-section wording.
- Be honest: don't inflate to end the loop; don't withhold 5/5 over a genuinely scope-deferred nit (record it under Deferred instead). Hold at 4/5 while any useful in-scope P2/P3 is unfixed.

## Engine invariants

> Fixed — the review loop cycles on these. Changing them breaks the loop.

- The rating is an **N/5 scale**, and **`5/5` = no P0/P1 AND every in-scope P2/P3 fixed** is the loop's **exit condition** (defined in the claudecodile-review skill, not here). The scale and that gate can't be changed in this file.
- The comment's **first line must be exactly `## 🐊 Claudecodile Rating: N/5`** (capital R) — the loop greps for it.
- **Exactly one** rating comment per PR, PATCHed in place each round — never a second. It is a PR *issue* comment, so it is **never resolved or deleted**.
- Post/edit with a **HEREDOC-literal body** (`--body "$(cat <<'EOF' … EOF )"`) — never `--body "@path"` / `-f body=@path` (those post the path text). Re-read after writing to confirm real content rendered.
