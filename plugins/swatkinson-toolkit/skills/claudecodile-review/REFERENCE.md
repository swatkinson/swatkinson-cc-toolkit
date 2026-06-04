# claudecodile-review — reference

Mechanics and runtime details for [SKILL.md](SKILL.md). This skill is the single source of truth for the 🐊 review⇄fix loop; `/handle-it` delegates its review phase here rather than duplicating the logic.

## The two agents

Both are **pre-built global subagents** in `~/.claude/agents/` — invoke via `Agent(subagent_type: …)`; their full briefs live in their files. They never touch git.

- **`claudecodile-reviewer`** (Opus) — runs `code-review` at HIGH, posts one inline comment per finding (`[P0]`–`[P3]` prefix + a ` ```suggestion ` block where it can apply), and maintains exactly **one** `## 🐊 Claudecodile Rating: N/5` comment (capital R; `Score history:` line; P#-grouped summary). Comments only.
- **`claudecodile-fixer`** (Sonnet) — fetches the open inline comments and applies the suggested fixes (every P0/P1 **and** every `(in-scope)` P2/P3 mandatory; leaves only the `(defer — scope)` nits), re-verifies. Edit-only.

## Skill invocation names

When a subagent or you invoke a skill via the `Skill` tool, **plugin skills need their fully-qualified `plugin:skill` name** — a bare name errors `Unknown skill`. `code-review` is a **bare-name** skill (it's not under the `agentsystem-core:` plugin in this repo). If the reviewer reports `code-review` errored `Unknown skill`, the name was wrong — fix it; don't accept a hand-rolled review that skipped its gates.

## Standalone vs delegated

The loop runs **in the caller's conversation context** (the Skill tool loads these instructions into the current agent — it does NOT spawn a fresh isolated agent). That's the design point:

- **Standalone** (`/claudecodile-review` invoked by a user on a PR): *you* are the top-level agent. You own the worktree, the git, and surface the plateau bail to the user via `AskUserQuestion`.
- **Delegated** (`/handle-it` Phase 6 invokes `Skill(claudecodile-review)`): the loop runs inside the **orchestrator's** context, so the orchestrator's foreground git allow-list (`Bash(git push:*)` / `Bash(git commit:*)`) applies and git ownership is unchanged from when this loop lived inline. You return the structured outcome; the orchestrator proceeds to its next phase (conflict gate / CI). **Functionally identical to the inline version** — same agents, same loop, same 5/5 gate, same rating comment.

Because it's the same context, the caller can mirror the live rating into its own status UI as each reviewer round reports — no special plumbing needed.

## Review scope per round

The reviewer reviews a different slice depending on the round (you tell it which):
- **Round 1** (or any round with no prior rating comment, e.g. a resumed review where one doesn't yet exist): FULL branch diff.
- **Later rounds:** the *incremental* diff since the previous round — cheaper, avoids re-surfacing addressed items.
- **Final pass:** one FULL-diff review before declaring 5/5 — the user's requirement, to catch cross-cutting regressions an incremental view hides. **Never declare 5/5 on an incremental round.**

## Rating comment — one, edited in place

The `## 🐊 Claudecodile Rating: N/5` comment is the **authoritative scoreboard** for the loop's exit and stays on the PR (it's a PR *issue* comment, never resolved/deleted).

- **Hold the rating-comment id** from round 1's report and pass it as `RATING_COMMENT_ID` to every later reviewer round, so it edits that one comment instead of re-discovering it (which risks duplicates).
- On a **resumed** review where you weren't given the id, the reviewer auto-discovers the existing `## 🐊 Claudecodile Rating:` issue comment (`gh pr view <N> --json comments` / `gh api repos/:owner/:repo/issues/comments`) and edits it.

**HEREDOC-literal posting (critical).** Pass comment bodies as a LITERAL string via inline HEREDOC — NEVER `--body "@path"` or `-f body=@path`, which post the literal path text (this is how rating comments came out as `@C:/…/.rating.txt` garbage in canary testing):
- post: `gh pr comment <N> --body "$(cat <<'EOF' … EOF )"`
- edit: `gh api repos/:owner/:repo/issues/comments/<id> -X PATCH -f body="$(cat <<'EOF' … EOF )"`

If you must read a body from a file use ONLY the file-reading flags — `--body-file <path>`, or `gh api … -F body=@<path>` (capital `-F`) — never `--body`/`-f` with an `@path`. **After posting/editing, re-read the comment and confirm it shows the content, not a path.**

## Loop control

- **5/5 = no P0/P1 AND every in-scope P2/P3 fixed.** The reviewer tags each P2/P3 `(in-scope)` (fix it) or `(defer — scope)` (fixing would bloat scope → record in the rating comment's Deferred section as a follow-up-issue recommendation or note). Only scope-deferred nits may remain at 5/5; while any in-scope P2/P3 is unfixed, the score caps at 4/5. This keeps small quality fixes in, while still preventing scope creep.
- **Plateau guard:** track the per-round score; no improvement across 2 rounds → plateau bail (standalone: `AskUserQuestion`; delegated: return it).
- **Handback bail:** the fixer returns a comment needing a product decision or a hard-rule file (`auth.ts` / `permissions.ts` / env / deploy) → return it; looping can't resolve those.

## Git

Between each reviewer→fixer→reviewer step **you** commit (Conventional Commit) + push from the worktree cwd. Subagents never run git (background agents hang on the `git push` permission prompt and ignore "don't push" — so the caller owns it). Never `main`, never amend/`--no-verify`/force-push.
