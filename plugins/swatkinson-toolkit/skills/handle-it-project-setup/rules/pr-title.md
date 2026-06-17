<!--
  Default seed for `.claude/handle-it/rules/pr-title.md`. The setup skill copies this into
  the target repo (stripping this comment); the user (and the engine, via self-correction)
  tweaks it there. Keep the section headings — the engine reads by heading.
-->

## About

The title handle-it writes when it opens the draft PR (Phase 5). One line. Its job is to tell a reviewer **what problem the PR solves**, in plain language — not how the code solves it. Source it from the **issue**, not the diff.

## Template

```
<type>(<scope>): <plain-language problem or outcome>
```

- `<type>` ∈ feat · fix · refactor · perf · docs · test · chore
- `<scope>` = the affected area, or `general` for a cross-cutting change
- summary = the user-visible problem being fixed / capability being added, phrased so a reviewer who hasn't read the code understands what it's for

Good — describes the problem: `fix(general): no longer hitting 'permission denied' on page refresh`

Bad — describes the mechanism: `fix: narrow over-broad refresh-only route auth gates to primary resource` (a reviewer can't tell what it's for)

## Rules

- **Describe the problem/outcome, not the implementation.** Come from the issue (the symptom, the user impact), not the code change. If the title reads like a code-review note, rewrite it from the user's perspective.
- Keep the `<type>(<scope>):` prefix; pick a real area for `<scope>`, or `general` when it's cross-cutting.
- Aim for ≤ 72 characters, no trailing period.
- One change = one focused title; if it needs "and", the PR is probably too broad.
- The bare issue id goes in the **description** (for tracker auto-link), not the title.
