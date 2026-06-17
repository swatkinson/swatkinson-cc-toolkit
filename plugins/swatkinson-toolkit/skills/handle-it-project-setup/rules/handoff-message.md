<!--
  Default seed for `.claude/handle-it/rules/handoff-message.md`. Setup copies it into the repo
  (stripping this comment). Keep the section headings — the engine reads by heading.
-->

## About

The message handle-it posts to **you** at the manual-review gate (Phase 10), once the PR is 🪰 passing (Quality & Standards 5/5), conflict-free, CI-green with a preview, and the auto-tester has ticked the headless items. The PR stays a **draft**; handle-it waits for your approval before un-drafting.

## Template

```
## Ready for your manual review

**Preview:** <preview-url>
**Local:** `cd <worktree-absolute-path> && <dev/run command>`

**Manual criteria:**
- [ ] <remaining unticked test-plan item 1>
- [ ] <remaining unticked test-plan item 2>
…

Tell me if it looks good and I'll check off the manual tests and mark it as ready for you.
```

## Rules

- **Preview line:** use the URL from where `config.md` → CI/preview says it lives. If there's no preview (or the deploy failed), replace with `**Preview:** ⚠️ No preview — test locally` (or `Deploy failed`) and include the failed-job URL when relevant.
- **Local line:** use `config.md` → Commands → dev/run. Where the project has no dev server (e.g. a plugin DLL loaded by a host app), replace with the project's described load/run-locally steps.
- **Manual criteria:** the still-unticked `- [ ]` items from the current PR description (the human/visual ones the auto-tester couldn't run). Re-read them from the PR each time you re-emit this, so the list is always current.

## Engine invariants

> Fixed — the engine depends on this.

- handle-it advances to un-draft (Phase 12) when **you** reply with approval ("looks good" or similar) — keep an explicit approval prompt as the closing line so it's clear what reply it's waiting for. The Preview / Local / criteria slots are filled by the engine from `config.md` and the PR.
