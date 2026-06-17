---
name: handle-it-project-setup
description: Generates the `.claude/handle-it.md` config that makes the `handle-it` and `claudecodile-review` skills project-generic. Scans the repo (package.json / build files for commands, CLAUDE.md + AGENTS.md for domain/architecture/hard-rules, .github/workflows for CI/preview, and the available MCP tools + git remote for the issue tracker), drafts the config favoring pointers over copies, shows it for confirmation, and writes it. Use when the user invokes /handle-it-project-setup, when `handle-it`/`claudecodile-review` report no config exists, or asks to "set up handle-it for this project".
---

# handle-it-project-setup

You produce **one file** — `.claude/handle-it.md` in the target repo — that carries every project-specific fact the `handle-it` and `claudecodile-review` engines need. Those skills hold zero project specifics of their own; this config is their entire knowledge of the project. Get it right and the same engine runs unchanged on a Bun/TanStack repo, a .NET solution, or an AutoCAD C++ plugin.

The skeleton you fill is **[TEMPLATE.md](TEMPLATE.md)** — copy it verbatim, then replace the `<angle-bracket>` slots from your scan. Keep the section headings exactly; the engine locates values by heading. Tracker profiles and a full worked example live in **[REFERENCE.md](REFERENCE.md)**.

**Guiding principle — point, don't copy.** Every fact that lives somewhere authoritative (package.json scripts, AGENTS.md, a workflow file) gets a `Source:` pointer rather than a transcribed copy, so it stays fresh and a re-run can refresh it. Only copy a value when there's no stable source to point at.

## Phase 0 — Existing config?

If `.claude/handle-it.md` already exists, this is a **refresh**, not a first run: read it, re-scan the sources, and propose a diff (updated commands/paths/CI). **Never discard the `Learned corrections` section** — those are runtime-earned fixes; carry them forward verbatim. Otherwise, first run → continue.

## Phase 1 — Scan the repo

Gather each field from its authoritative source (record the source as a pointer):

1. **Project + stack.** `package.json` (name/scripts/deps), or `*.sln`/`*.csproj`, `*.vcxproj`, `Cargo.toml`, `go.mod`, `pyproject.toml` — whatever's present. Pick the signal that uniquely identifies the repo.
2. **Commands.** Read the build manifest's scripts/targets for: the verify gate (typecheck/lint + tests), whether a **test runner actually exists** (no `test` script / no vitest·jest·playwright·xunit → tests = `none`; never invent one), worktree create/list (a repo `worktree:*` script if present, else raw `git worktree`), the dev/run command, and migration commands (+ what diff signals a migration). Prefer pointing at the script name over copying the full command line.
3. **Conventions + hard rules.** Read `CLAUDE.md`, `AGENTS.md`, `CONTEXT.md`, `docs/adr/` for branch naming, commit conventions, testing policy, the architecture/domain docs to **point at**, and the do-not-touch files (auth, permissions, env, deploy). Don't copy their contents — list them as pointers.
4. **CI / preview.** Read `.github/workflows/*` (or other CI config) for check names and the preview-deploy mechanism; note where the real preview URL is posted (and any trap, like a disabled native Vercel integration that posts a useless "Ignored Build Step").
5. **Issue tracker.** Detect from the session's available tools + the git remote: a Linear MCP present → likely `linear`; only `gh` + GitHub remote → likely `github`; a Jira MCP/CLI → `jira`; nothing → `none`. **Confirm with the user** — detection is a guess. Then fill that profile (REFERENCE → Tracker profiles).
6. **Engine skills.** Default to `agentsystem-core:ship` / `diagnose` / `agentsystem-core:open-pr` / `agentsystem-core:resolve-conflict` / `agentsystem-core:fix-pr-tests` / `code-review` + `simplify`. If those plugins/skills aren't installed, note it and ask the user what to route to.

For anything you genuinely can't determine, leave the `<slot>` with a clear `<TODO: ...>` and flag it in Phase 2 rather than guessing.

## Phase 2 — Draft, confirm, write

1. **Draft** the full config in chat (the filled TEMPLATE). Call out every value you inferred low-confidence and every `<TODO>`.
2. **Confirm** with the user — especially the tracker type, the verify gate, the hard-rule files, and the preview-URL location (these four cause the most damage if wrong). Use `AskUserQuestion` for genuine forks; otherwise just present and let them correct.
3. **Write** `.claude/handle-it.md` with their corrections. Create `.claude/` if absent.
4. **Tell the user** it's ready and that `/handle-it` and `/claudecodile-review` will now use it — and that the engine will self-correct the file as it learns. If `.gitignore` excludes `.claude/`, mention they may want to commit this file so teammates share it.

## Principles

- **The four high-blast-radius fields are tracker type, verify gate, hard-rule files, and preview-URL location.** Spend your confirmation budget there.
- **`none` is a valid answer** for tests, migrations, tracker, CI, and preview — a config that honestly says "no test runner" is far better than one that invents `bun run test` on a repo that has none.
- **Pointers over copies.** A re-scan should refresh the config; that only works if values point at their source.
- **Don't reproduce the engine's logic here.** This file is data, not instructions — phases, gates, and the review loop stay in the engine skills.
