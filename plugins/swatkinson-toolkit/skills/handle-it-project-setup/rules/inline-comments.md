<!--
  Default seed for `.claude/handle-it/rules/inline-comments.md`. Setup copies it into the repo
  (stripping this comment). Used by claudecodile-review's reviewer (the fixer reads the tags).
  Keep the section headings — the engine reads by heading.
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

- Write a brief, concrete **why it matters** under the summary; reviewers and the fixer act on it.
- Include a GitHub ` ```suggestion ` block for any small, localized fix so the fixer/human can apply it directly; describe the approach for larger ones.
- When unsure whether a P2/P3 is in-scope, default to `(in-scope)` — only defer when the scope cost is real.

## Engine invariants

> Fixed — the fixer and the loop depend on these.

- Every finding carries a **priority prefix** — `[P0]` breaking / data loss · `[P1]` important correctness · `[P2]` quality · `[P3]` nit — and every **P2/P3 carries a scope tag** `(in-scope)` or `(defer — scope)`. The fixer parses these tokens to decide what to fix; the vocabulary is fixed even if you reword the descriptions.
- One comment per finding, anchored at the line. Post bodies as **HEREDOC-literal strings** — never `--body "@path"` / `-f body=@path`. Re-read after posting to confirm real content rendered.
- On later/final rounds the reviewer **resolves (never deletes) the thread of every finding it verifies fixed**, preserving the flagged→fixed history; unfixed/re-broken findings keep their threads open.
