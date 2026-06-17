<!--
  Default seed for `.claude/handle-it/rules/commit-message.md`. Setup copies it into the repo.
  Keep the section headings (About / Template / Rules) — the engine reads by heading.
-->

## About

The commit the **orchestrator** composes after an implement/fix subagent returns (Phase 4, and each review-loop round). Subagents propose a subject; the orchestrator writes the final message to these rules and commits from the foreground.

## Template

```
<type>(<scope>): <imperative summary>

<optional body — why, not what; wrap at ~72 cols>

Refs: <ISSUE-ID>
```

Review-loop fix commits may use a fixed subject, e.g. `fix(<scope>): address review`.

## Rules

- Conventional Commits (`feat`/`fix`/`refactor`/`perf`/`docs`/`test`/`chore`).
- Include the **`Refs: <ISSUE-ID>`** trailer so the tracker links the commit (omit in trackerless mode). Use `Refs:`, not `Closes:` — a human merges; the engine never auto-closes the issue.
- Subject imperative, ≤ 72 chars, no trailing period.
- **Never** `--no-verify` or any skip-flag. **Never** amend an existing commit — make a new one. Run `git commit` and `git push` as two separate foreground calls (not chained).
- Stage only the paths the change touched (`git add <path> …`) — never `git add -A`; confirm with `git diff --cached --stat` first.
