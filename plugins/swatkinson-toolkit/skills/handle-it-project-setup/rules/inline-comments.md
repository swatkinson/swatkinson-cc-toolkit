<!--
  Default seed for `.claude/handle-it/rules/inline-comments.md`. Setup copies it into the repo.
  Used by claudecodile-review's reviewer (and the fixer reads the tags). Keep the headings.
-->

## About

The per-finding inline review comments the reviewer posts on the diff — one comment per finding, anchored at the relevant line — plus the round-1 `[Simplify Suggestion]` comments. The fixer reads these (especially the priority + scope tags) to decide what to fix.

## Template

**Finding (P#-tagged):**

```
[<P0|P1|P2|P3>] <one-line summary> <scope-tag if P2/P3>

<why it matters, briefly>

```suggestion
<the corrected code>
```
```

**Simplify suggestion (round 1 only, no P# / no scope tag):**

```
[Simplify Suggestion] <one-line summary>

<concrete approach; a ```suggestion block if the change is small and localized>
```

## Rules

- **Priority prefix**, required: `[P0]` breaking / data loss · `[P1]` important correctness · `[P2]` quality / maintainability · `[P3]` nit.
- **Scope tag on every P2/P3:** `(in-scope)` (the fixer MUST fix it) or `(defer — scope)` (fixing would bloat scope → leave it; record in the rating comment's Deferred section). When unsure, default to `(in-scope)`.
- Include a GitHub ` ```suggestion ` block for any small, localized fix so the fixer/human can apply it directly; describe the approach for larger ones.
- One comment per finding, anchored at the line. Post the body as a **HEREDOC-literal string** — never `--body "@path"` / `-f body=@path`. Re-read after posting to confirm real content rendered.
- On later/final rounds, **resolve the inline thread of every finding verified fixed** in the current diff (the reviewer authored them, so it owns resolving them — resolve, never delete, to preserve the flagged→fixed history). Leave unfixed/re-broken findings' threads open.
