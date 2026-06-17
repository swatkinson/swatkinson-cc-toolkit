# handle-it-project-setup — reference

Tracker profiles and a full worked example for [SKILL.md](SKILL.md). The skeleton you fill is [TEMPLATE.md](TEMPLATE.md).

## The engine ↔ config contract

`handle-it` and `claudecodile-review` read `.claude/handle-it.md` by **section heading**. Keep the headings exactly as the template has them: `Project`, `Issue tracker`, `Commands`, `Repo conventions`, `Hard-rule files`, `CI / preview`, `Engine skills`, `Learned corrections`. The engine needs, at minimum, these to work:

- a **verify gate** (Commands) — used by every implement/fix/test step and by `claudecodile-review`'s fixer;
- a **hard-rule file list** (Hard-rule files) — the bail set, shared by both skills;
- a **tracker type + operation map** (Issue tracker) — or `none` for freeform;
- **worktree create/list** (Commands) and **branch naming** (Repo conventions);
- **CI/preview** mechanics, or `none`.

Everything else sharpens behavior but the engine degrades gracefully (e.g. no migration command → it never attempts a migration rebase; no preview → the handoff line says "test locally").

## Tracker profiles

The engine abstracts the tracker behind a fixed set of operations. Fill the profile so each maps to a concrete tool call.

| Operation | linear | github | jira | none |
|---|---|---|---|---|
| resolve "me" | `get_user query=me` | `gh api user` | Jira myself endpoint | — |
| read issue + blockers | `get_issue includeRelations:true` | `gh issue view --json body,...` + parse task-list/labels | Jira issue + issue-links | user pastes text |
| create issue | `save_issue` | `gh issue create` | Jira create | emit a copyable block |
| set status | `save_issue` state id | label / Project column / close | transition id | user does it by hand |
| comment | `save_comment` | `gh issue comment` | Jira add-comment | n/a |
| labels on create | label ids | `--label` | labels field | n/a |
| attach to cycle/sprint | active cycle id | Project field | active sprint | n/a |

For `github` and `jira`, spell out in the config exactly how "In Progress" / "In Review" are represented (a label? a Projects column? closed-state?) and how "is blocked by" is encoded, since those have no single convention.

## Worked example — CaivanOS (reproduces today's hardcoded behavior)

Running setup on CaivanOS should produce a config equivalent to the values the engine used to hardcode. This is the reference for "did I capture enough":

```markdown
## Project
- Name: CaivanOS
- Stack: TanStack Start / React 19 / Bun · Drizzle + Neon + Electric
- Identifies as: package.json name `app.caivanos`

## Issue tracker
- Type: linear
### If `linear`
- Tools: `mcp__linear-server__*`
- Team: "Software Development" — key `BE` (id 3412f0ba-a308-4017-8ebf-912b4d4c8454)
- Issue id format: `BE-####`
- Labels to apply on create: `ai` (keep planning-skill `ready-for-agent`/category labels)
- Status mapping: Backlog / Todo / In Progress / In Review / Done via list_issue_statuses; blocker clears only at Done
- Cycle/sprint: active cycle (list_cycles type=current)
- Relations: real blockedBy/blocks; get_issue includeRelations:true

## Commands
- Verify gate: `bun run check` && `bun run test`
  - Source: package.json scripts; AGENTS.md → Testing
- Test runner exists: yes
- Worktree — create: `bun run worktree:new <domain>/<be-id>/<short-kebab>` (add `--db-branch` ONLY for a migration/schema change)
- Worktree — list: `bun run worktree:ls --json`
- Dev / run: `bun dev`
- Migrations: `bun run db:branch` (start) + `bun run db:rebase` (resolve migration-index conflicts; prints one sanctioned `git push --force-with-lease`)
  - Migration-bearing when: diff touches `migrations/` + `_journal.json`/snapshot

## Repo conventions
- Branch naming: `<domain>/<be-id>/<short-kebab>` per AGENTS.md
- Worktree location: `.claude/worktrees/`
- Commit ref convention: `Refs: BE-####` + Conventional Commits
- Staging discipline: stage touched paths only; Windows worktree checkouts carry CRLF↔LF churn in tracked `.pi/`/`.claude/` files — `git add -A` would sweep it in
- Architecture / domain docs (pointers): AGENTS.md

## Hard-rule files
- src/server/auth.ts
- src/lib/auth/permissions.ts
- environment/secret handling, deploy/CI config

## CI / preview
- CI: yes. Check via `gh pr checks`.
- Preview deploys: yes.
  - Where the URL is: the `github-actions` PR comment from the `deploy-vercel` action, on `…dev.caivanos.app` (e.g. `caivanos-git-<branch>-…dev.caivanos.app`) — NOT a `*.vercel.app` URL; native Vercel check shows "Ignored Build Step"
  - Draft behavior: drafts DO deploy as long as conflict-free; a CONFLICTING PR runs zero pull_request workflows

## Engine skills
- (all defaults: agentsystem-core:ship / diagnose / agentsystem-core:open-pr / agentsystem-core:resolve-conflict / agentsystem-core:fix-pr-tests / code-review + simplify)
```

## Worked example — Workbench (the second supported repo today)

Same shape, with the differences that used to live in handle-it's "Workbench (best-effort)" section:

- **Stack:** Next.js 15 / React 19 / pnpm 10 / Drizzle + Neon.
- **Commands → Verify gate:** `pnpm check` (= `next lint && tsc --noEmit`). **Test runner exists: no** — there is no `test` script; `check` green is the full gate.
- **Worktree — create:** `git worktree add .claude/worktrees/<be-id> -b <be-id> main` (branch = the Linear `gitBranchName`, e.g. `be-2240`), then copy `.env` from the primary checkout.
- **Migrations:** Drizzle/Neon present; DB-connection-string ask is conditional (hard-block only for a DB/schema/migration change; non-DB change just quick-confirms the copied `.env`).
- **CI / preview:** CI check named **"Next Check"**; preview on the stable alias `workbench-git-<branch>.caivan.dev` via the `deploy-vercel` `github-actions` comment.
- Tracker, status table, hard rules: identical to CaivanOS.

## Example — a trackerless / non-web project (.NET or AutoCAD plugin)

- **Issue tracker → Type: `none`** (or `github` if they use GitHub Issues). handle-it takes the feature/bug description directly and runs the full pipeline; status stays in the chat table.
- **Commands → Verify gate:** `dotnet build` + `dotnet test` (tests = yes), or build-only (tests = none). **Worktree:** raw `git worktree add`. **Dev/run:** `dotnet run` or `none` (a plugin DLL loaded by a host app has no dev server — the handoff line then describes how to load it into the host).
- **Migrations:** almost always `none`.
- **CI / preview:** CI = whatever's in the CI config (or `none`); **Preview = `none`** — the Phase-8 preview step is skipped and the manual-review handoff says "build locally / load into <host>".
- **Hard-rule files:** whatever the project guards (signing config, licensing, P/Invoke shims, etc.).

This is the case that proves the abstraction: no Linear, no Vercel, no migrations, maybe no tests — and the engine still drives plan → implement → PR → review → handoff off the config alone.
