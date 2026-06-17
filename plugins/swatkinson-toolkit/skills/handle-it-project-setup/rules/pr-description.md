<!--
  Default seed for `.claude/handle-it/rules/pr-description.md`. Setup copies it into the repo.
  Keep the section headings (About / Template / Rules) — the engine reads by heading.
-->

## About

The PR body handle-it writes when it opens the draft PR (Phase 5). The **Test plan** checkboxes here drive the auto-tester (Phase 9) and the manual-review handoff (Phase 10), so write them as concrete, checkable items.

## Template

```
## Summary

<what changed and why, 1–3 sentences. Include the bare issue id (e.g. ISSUE-1234) so the tracker auto-links this PR.>

## Test plan

- [ ] <automatable check — runs headlessly, e.g. the verify gate, a focused suite, a build>
- [ ] <manual / click-through item — needs a human, e.g. "open the reviews page and confirm the new column renders">
```

## Rules

- The **bare issue id** must appear in the Summary (not back-ticked) so the tracker links the PR to the issue. In trackerless mode, omit it.
- **Test plan** uses GitHub task-list syntax (`- [ ]`). Put **automatable** items first (the auto-tester runs and ticks those); leave human/visual items for manual review.
- Don't invent test items the change doesn't warrant; don't omit a manual step the change clearly needs.
- Leave any bot-managed section (e.g. a Macroscope/coverage block) untouched — only handle-it's Summary + Test plan are ours to write/edit.
- If the repo has a `.github/pull_request_template.md`, fold its required sections in rather than overriding them.
