<!--
  Default seed for `.claude/handle-it/rules/inline-comments.md`. Setup copies it into the repo
  (stripping this comment). Used by claudecodile-review's reviewer (the fixer reads the tags).
  Keep the section headings — the engine reads by heading.
-->

## About

The per-finding inline review comments the reviewer posts on the diff — one comment per finding, anchored at the relevant line. The fixer reads these (especially the priority + scope tags) to decide what to fix; the reviewer uses the **facet tag** to compute the per-facet sub-scores in the rating comment.

## Template

**Finding (P#-tagged):**

```
[<P0|P1|P2|P3>][<Quality|Spec>] <one-line summary> <scope-tag if P2/P3>

<why it matters, briefly>

```suggestion
<the corrected code>
```
```

**Risk annotation (advisory — optional):**

```
[Risk] <one-line: the specific risky / complex spot and what breaks if it's wrong>
```

The **facet tags:**
- `[Quality]` — correctness / security / perf / design issues, **and** consistency / reuse issues (doesn't match how sibling features do it, reinvents something the project already has, simplifiable duplication). Standards-adherence is part of Code Quality.
- `[Spec]` — the change doesn't implement / fully satisfy what the issue or PRD asked. (A gap that isn't tied to a specific line — a feature simply missing — goes in the rating comment's Spec. Adherence section instead of inline.)
- `[Risk]` — an **advisory** pointer at a risky / complex spot. No scope tag; the fixer does **not** act on it (you can't "fix" inherent risk — a concrete code improvement would be tagged `[Quality]`). It feeds the holistic Risk and Complexity rationale.

## Rules

- Write a brief, concrete **why it matters** under the summary; reviewers and the fixer act on it.
- Include a GitHub ` ```suggestion ` block for any small, localized fix so the fixer/human can apply it directly; describe the approach for larger ones.
- When unsure whether a P2/P3 is in-scope, default to `(in-scope)` — only defer when the scope cost is real.

## Engine invariants

> Fixed — the fixer and the loop depend on these.

- Every **fixable** finding (`[Quality]` / `[Spec]`) carries a **priority prefix** — `[P0]` breaking / data loss · `[P1]` important correctness · `[P2]` quality · `[P3]` nit — a **facet tag**, and (for P2/P3) a **scope tag** `(in-scope)` or `(defer — scope)`. The fixer parses priority + scope to decide what to fix; the reviewer uses the facet to compute the Quality / Spec sub-scores. `[Risk]` comments are **advisory** — no priority/scope tag, the fixer ignores them. The vocabulary is fixed even if you reword the descriptions.
- One comment per finding, anchored at the line. Post bodies as **HEREDOC-literal strings** — never `--body "@path"` / `-f body=@path`. Re-read after posting to confirm real content rendered.
- On later/final rounds the reviewer **resolves (never deletes) the thread of every finding it verifies fixed**, preserving the flagged→fixed history; unfixed/re-broken findings keep their threads open.
