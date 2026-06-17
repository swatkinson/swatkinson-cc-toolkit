<!--
  Default seed for `.claude/handle-it/rules/pr-title.md`. The setup skill copies this into
  the target repo; the user (and the engine, via self-correction) tweaks it there.
  Keep the three section headings (About / Template / Rules) — the engine reads by heading.
-->

## About

The title handle-it writes when it opens the draft PR (Phase 5). One line. Read alongside `pr-description.md`.

## Template

Default (Conventional-Commit style):

```
<type>(<scope>): <imperative summary>
```

`<type>` ∈ feat · fix · refactor · perf · docs · test · chore. Pick `<scope>` from the area touched. Example: `feat(reviews): add reviewer assignment to PR list`.

If your project prefers the issue id in the title, use:

```
[<ISSUE-ID>] <type>(<scope>): <imperative summary>
```

## Rules

- Imperative mood, no trailing period, aim for ≤ 72 characters.
- Match the repo's existing PR-title style if it has one (check recent merged PRs); these defaults yield to an established convention.
- By default the bare issue id goes in the **description** (for tracker auto-link), not the title — unless you switch to the `[<ISSUE-ID>]` template above.
- One change = one focused title; if the title needs "and", the PR is probably too broad.
