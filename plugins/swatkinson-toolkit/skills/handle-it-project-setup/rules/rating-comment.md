<!--
  Default seed for `.claude/handle-it/rules/rating-comment.md`. Setup copies it into the repo
  (stripping this comment). Used by claudecodile-review's reviewer. Keep the section headings.
-->

## About

The single `## 🐊 Claudecodile Rating` issue comment the reviewer maintains on the PR — the scoreboard for the review⇄fix loop. It rates **three facets**. Exactly one comment per PR, edited in place across rounds.

- **Code Quality** (N/5, 5 = best) — overall quality of the change: correctness, security, performance, design / OOP principles, **and adherence to the rest of the codebase** (does it implement schema, handle permissions, and build UI the way sibling features do, and **reuse existing code** where it should, rather than reinventing or simplifiable duplication). Compare to the nearest existing feature on every facet you can.
- **Spec. Adherence** (N/5, 5 = solves it fully) — how well the change actually solves the feature / PRD / issue it's for. `5` = adheres greatly to what was asked; `0` = missed the plot. Judge against the issue context the caller provided (or the PR's linked issue + its **Why** section).
- **Risk and Complexity** (N/5, 5 = safest) — how likely a bug is **lurking** (the complexity of the change — more complex ⇒ more chance of a defect) **and** how bad it would be if one shipped (blast radius — if this breaks, how much breaks with it). NOT a quality judgment.

## Template

```
## 🐊 Claudecodile Rating

| Facet | Score |
|---|---|
| Code Quality        | <N>/5 |
| Spec. Adherence     | <N>/5 |
| Risk and Complexity | <N>/5 |

Score history (Quality · Spec): <a·b → c·d → …>

### Code Quality — <N>/5
- [P#][Quality] <summary> <(in-scope)/(defer — scope) if P2/P3> — <FIXED / open>

### Spec. Adherence — <N>/5
- [P#][Spec] <what the issue/PRD asked that the change misses or only partly does> <scope tag if P2/P3> — <FIXED / open>

### Risk and Complexity — <N>/5 (advisory — does not gate the loop)
<complexity + blast radius read: how intricate the change is and what breaks if it's wrong, plus a concrete thing for the human reviewer to check>

### Deferred (out of scope)
- [P#][<facet>] <nit> (defer — scope) — follow-up issue recommended: <why> / or: note only
```

## Risk and Complexity rubric

Score on **complexity** (likelihood a bug is hiding) × **blast radius** (damage if one is), independent of how clean the code looks (5 = safest). Mark a low score with ⚠️.

- **5** — trivial and isolated: comments, copy / text, small UI tweaks
- **4** — small, contained logic; dependency bumps
- **3** — moderate: a schema change / migration, a shared-utility change, or non-trivial logic in one area
- **2** — complex logic, auth / permissions touched, a multi-table migration, or a cross-cutting change
- **0–1** — large **and** complex with broad blast radius (e.g. rewriting core tables like `users` + permissions)

## Rules

- Score **Code Quality** and **Spec. Adherence** on the usual bands: `5` = no P0/P1 in that facet **and** every in-scope P2/P3 in it fixed; `4` = in-scope P2/P3 remain; `2–3` = a P1 remains; `0–1` = a P0 remains. For **Spec**, a P0/P1 = a missing or violated **core acceptance criterion** (a "missed the plot" change is 0–1). Score **Risk and Complexity** on the rubric above.
- Code Quality covers both *intrinsic* quality (bugs, security, perf, design) and *consistency* with the codebase (matching patterns, reusing existing code) — a bespoke reimplementation of something the project already solves is a Code Quality finding.
- Edit the layout freely (table vs. lines, grouping) as long as the invariants below hold.
- Be honest: don't inflate the gating facets to end the loop; record genuinely scope-deferred nits under Deferred rather than withholding a 5. Score Risk and Complexity flatly — don't soften it because the PR is otherwise good.

## Engine invariants

> Fixed — the review loop cycles on these. Changing them breaks the loop.

- **Three facets, shown by full name at the top: Code Quality, Spec. Adherence, Risk and Complexity.** Their inline finding tags are `[Quality]`, `[Spec]`, and the advisory `[Risk]`.
- The loop's **exit condition is `Code Quality = 5/5 AND Spec. Adherence = 5/5`** (defined in the claudecodile-review skill). **Risk and Complexity never gates** the loop or the plateau guard — it is advisory only.
- The comment's **header must be exactly `## 🐊 Claudecodile Rating`**, and it must contain the two **gating** scores in a parseable `Code Quality … N/5` / `Spec. Adherence … N/5` form (the table is fine) — the loop greps these.
- Exactly **one** rating comment per PR, PATCHed in place each round — never a second. It is a PR *issue* comment, so it is **never resolved or deleted**.
- Post/edit with a **HEREDOC-literal body** (`--body "$(cat <<'EOF' … EOF )"`) — never `--body "@path"` / `-f body=@path`. Re-read after writing to confirm real content rendered.
