<!--
  Default seed for `.claude/handle-it/rules/rating-comment.md`. Setup copies it into the repo.
  Used by claudecodile-review's reviewer. Keep the headings (About / Template / Rules).
-->

## About

The single `## 🐊 Claudecodile Rating` issue comment the reviewer maintains on the PR — the authoritative scoreboard for the review⇄fix loop's exit. Exactly **one** per PR, edited in place across rounds. It is a PR *issue* comment (not a review thread), so it is never resolved or deleted.

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

- **Scoring:** `5/5` = no P0/P1 **and** every `(in-scope)` P2/P3 fixed (only `(defer — scope)` nits remain, recorded under Deferred). `4/5` = no P0/P1 but in-scope P2/P3 still open. `2–3` = P1s remain. `0–1` = P0s remain.
- First line is exactly `## 🐊 Claudecodile Rating: N/5` (capital R) — the loop greps for it.
- Keep a `Score history:` line showing the per-round trend.
- **Exactly one** rating comment: post it round 1, **PATCH the same comment id** every later round — never a second.
- Be honest: don't inflate to end the loop; don't withhold 5/5 over a genuinely scope-deferred nit (record it instead). Hold at 4/5 while any useful in-scope P2/P3 is unfixed.
- **Post/edit with a HEREDOC-literal body** (`--body "$(cat <<'EOF' … EOF )"`) — never `--body "@path"` / `-f body=@path` (those post the path text). Re-read after writing to confirm real content rendered.
