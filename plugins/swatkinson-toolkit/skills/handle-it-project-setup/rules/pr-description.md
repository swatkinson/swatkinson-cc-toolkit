<!--
  Default seed for `.claude/handle-it/rules/pr-description.md`. Setup copies it into the repo
  (stripping this comment). Keep the section headings — the engine reads by heading.
-->

## About

The PR body handle-it writes when it opens the draft PR (Phase 5). Structured so a reviewer reads **why** before **how**. The Test plan checkboxes drive the auto-tester (Phase 9) and the manual-review handoff (Phase 10), so write them as concrete, checkable items.

## Template

```
## Why

<the problem this PR solves, from the issue — the symptom / user impact, in plain language. Include the bare issue id (e.g. ISSUE-1234) so the tracker auto-links this PR.>

## How

<summary of the code change — what was changed to address the Why.>

## Test plan

- [ ] <automatable check — runs headlessly, e.g. the verify gate, a focused suite, a build>
- [ ] <manual / click-through item — needs a human, e.g. "refresh the page and confirm no permission error">

## Notes

<caveats, follow-ups, out-of-scope items, anything a reviewer should know. Omit the section if there's nothing.>
```

## Rules

- **Why = the problem (from the issue), in plain language; How = the change (from the diff), technical.** Why comes first. (How is what the old single "Summary" section held.)
- The **bare issue id** appears in **Why** (not back-ticked) for tracker auto-linking. Omit in trackerless mode.
- **Test plan:** automatable items first (the auto-tester runs and ticks those); human/visual items after.
- **Notes — migration callout:** if the change includes a database migration, start Notes with a bold warning, e.g. `> ⚠️ **This PR includes a database migration** — review/apply accordingly.` so it isn't missed. (handle-it knows a change is migration-bearing from `config.md` → migration signal.)
- Don't invent test items the change doesn't warrant; don't omit a manual step it clearly needs.
- If the repo has a `.github/pull_request_template.md`, fold its required sections in rather than overriding them.

## Engine invariants

> Fixed — the engine parses these. Changing them breaks ticking / handoff.

- The **Test plan** uses GitHub task-list syntax (`- [ ]` / `- [x]`) in a section the auto-tester can find. The tester ticks these and the Phase-10 handoff reads the still-unticked ones — renaming away from checkboxes breaks both.
- Leave any bot-managed section (coverage / Macroscope / etc.) untouched — only handle-it's sections are ours to write or edit.
