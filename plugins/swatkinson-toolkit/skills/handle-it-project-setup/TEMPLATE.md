<!--
  This is the TEMPLATE for `.claude/handle-it/config.md` — the per-project config that drives
  `handle-it` and `swat-review`. The setup skill copies this skeleton into the target
  repo at `.claude/handle-it/config.md`, fills the <ANGLE_BRACKET> slots from a repo scan, and
  asks the user to confirm. Alongside it, setup writes `.claude/handle-it/rules/*.md` — the
  per-unit PR / commit / review templates (see the Rules files manifest below). Keep the
  section headings EXACTLY as written — the engine locates values by heading.

  Guiding principle: POINT, don't COPY, wherever the source stays fresh on its own.
  Every fact that lives somewhere authoritative (package.json scripts, AGENTS.md, a
  workflow file) gets a `Source:` pointer so the engine can re-derive it when it drifts,
  and so a re-scan refreshes it. Only copy a value when there is no stable source to point at.
-->

# handle-it config

> Project config for `handle-it` and `swat-review`. The engine skills read this file (and the rule files it points to); do not hardcode project specifics in the skills themselves. When the engine discovers a value here is wrong at runtime, it corrects the field and appends a note to **Learned corrections** — so this config gets more accurate over time.

## Rules files

The text artifacts handle-it and swat-review author are templated, one file per unit, under `.claude/handle-it/rules/`. Each rule file has `## About`, `## Template`, and `## Rules` sections; edit them to change exactly how each artifact is written. Phases below name the rule file(s) they consume.

| Rule file | Authored by | Consumed at |
|---|---|---|
| `rules/pr-title.md` | handle-it | Phase 5 (open PR) |
| `rules/pr-description.md` | handle-it | Phase 5 (open PR); Test plan feeds Phases 9–10 |
| `rules/commit-message.md` | handle-it | Phase 4 + every review-loop fix commit |
| `rules/handoff-message.md` | handle-it | Phase 10 (manual-review handoff) |
| `rules/rating-comment.md` | swat-review | every review round |
| `rules/inline-comments.md` | swat-review | every review round |

## Project

- **Name:** <project name>
- **Stack:** <e.g. TanStack Start / React 19 / Bun · or .NET 8 class library · or AutoCAD ObjectARX C++ plugin>
- **Identifies as:** <the signal that confirms "this is that repo" — e.g. `name` in package.json is `app.caivanos`, or a specific .sln/.csproj, or a remote URL pattern>

## Issue tracker

<!--
  type is one of: linear | github | jira | none
  Fill ONLY the profile that matches `type`; delete the others. For `none`, handle-it runs
  in freeform / copy-paste mode (it still does the full git+PR pipeline; it just can't
  auto-read/write issues — see handle-it REFERENCE → Trackerless / manual mode).
  The engine needs these OPERATIONS regardless of tracker; the profile says how to do each:
  resolve-me · read-issue (+ blocking relations) · create-issue · set-status · comment ·
  labels-to-apply · attach-to-cycle/sprint · issue-id format.
-->

- **Type:** <linear | github | jira | none>

### If `linear`
- **Tools:** the Linear MCP tools exposed this session (namespace is harness-dependent — e.g. `mcp__linear-server__*`).
- **Team:** <team name> — match `key === "<KEY>"` from `list_teams` (its `query` searches names, not keys). Team id may be cached here once resolved: `<id or "resolve at runtime">`.
- **Issue id format:** `<KEY>-####` (e.g. `BE-1234`).
- **Labels to apply on create:** <e.g. `ai` (+ keep planning-skill labels like `ready-for-agent`)>.
- **Status mapping:** Backlog / Todo / In Progress / In Review / Done — resolve ids via `list_issue_statuses team=<team-id>`; a blocker clears only at **Done** (merged).
- **Cycle/sprint:** attach new issues to the **active cycle** (`list_cycles type=current`).
- **Relations:** set real `blockedBy`/`blocks` relations (not just body text); `get_issue` needs `includeRelations: true`.

### If `github`
- **Tools:** `gh issue` / `gh api`. Repo: `<owner>/<repo>`.
- **Issue id format:** `#<number>`.
- **Labels to apply on create:** <e.g. `ai`>.
- **Status mapping:** open/closed, plus a Project board column or a label if you use one (`<how In Progress / In Review are represented>`). A blocker clears when its issue/PR is **merged/closed**.
- **Blocking:** <task-list `- [ ] #123` in the body, or a `blocked-by` label, or a Projects field — say which>.

### If `jira`
- **Tools:** <Jira MCP / `acli` / REST — whichever is wired this session>.
- **Project key + id format:** `<KEY>-###`.
- **Status / labels / sprint / links:** <map In Progress / In Review / Done, the label(s) to apply, the active sprint, and how "is blocked by" links are set>.

### If `none`
- handle-it runs **freeform**: it takes a feature/bug description directly, runs the full plan→implement→PR→review→test→handoff pipeline, and skips all issue read/write. Status lives only in the chat table. See handle-it REFERENCE → Trackerless / manual mode.

## Commands

<!--
  These are the calls the engine makes. Give the actual command AND a Source pointer so the
  engine can re-derive it if it's renamed (and so a re-scan refreshes it). If a capability
  doesn't exist, write `none` — do NOT invent one (e.g. a repo with no test runner: tests = none).
-->

- **Verify gate:** <e.g. `bun run check` && `bun run test`  ·  or `pnpm check` (no test runner)  ·  or `dotnet build && dotnet test`>
  - Source: <where these live — e.g. package.json `scripts.check`/`scripts.test`, or AGENTS.md → Testing, or the .sln>
- **Test runner exists:** <yes | no — if no, the verify gate is the build/lint step alone; never invent a `test` command>
- **Worktree — create:** <e.g. `bun run worktree:new <name>` (add a DB-branch flag only for migration changes)  ·  or raw `git worktree add .claude/worktrees/<name> -b <branch> <base>`>
- **Worktree — list:** <e.g. `bun run worktree:ls --json`  ·  or `git worktree list --porcelain`>
- **Dev / run (for the local-handoff line):** <e.g. `bun dev`  ·  `pnpm dev`  ·  `dotnet run`  ·  none>
- **Migrations:** <command(s), e.g. `bun run db:branch` to start one + `bun run db:rebase` to resolve index conflicts  ·  or `none` if the project has no DB migrations>
  - **A change is "migration-bearing" when:** <the diff touches `<migrations dir>` / a schema file — say what>

## Repo conventions

- **Branch naming:** <e.g. `<domain>/<issue-id>/<short-kebab>` per AGENTS.md  ·  or `<issue-id>`  ·  or `feature/<kebab>`>
- **Worktree location:** <e.g. `.claude/worktrees/`>
- **Commit ref convention:** see `rules/commit-message.md` (the full commit template + rules live there)
- **Staging discipline:** stage only the paths the change touched — never `git add -A`/`.`. <Note any repo-specific churn trap, e.g. Windows worktree checkouts carry CRLF↔LF churn in tracked `.pi/`/`.claude/` files that `git add -A` would sweep in.>
- **Architecture / domain docs (POINTERS — do not copy):** <e.g. AGENTS.md, CONTEXT.md, docs/adr/ — list the files an implementer should read for conventions, so handle-it points agents at them instead of duplicating their content here>

## Hard-rule files

<!-- Files/areas an agent must NEVER edit to satisfy a step — touching one is a BAIL, not a fix. -->

- <e.g. `src/server/auth.ts`>
- <e.g. `src/lib/auth/permissions.ts`>
- <e.g. environment/secret handling, deploy/CI config>

## CI / preview

<!-- How handle-it reads CI and finds the deployed preview. If there's no CI or no preview, write `none`. -->

- **CI:** <yes | no>. Check name(s): <e.g. "Next Check", "check", "build" — or "discover via `gh pr checks`">.
- **Preview deploys:** <yes | no>.
  - **Where the URL is:** <e.g. the `github-actions` PR comment posted by the `deploy-vercel` action, on the custom domain `<pattern>` — NOT a `*.vercel.app` URL; the native Vercel check shows "Ignored Build Step" and has no usable URL>.
  - **Draft behavior:** <e.g. drafts DO deploy as long as the PR is conflict-free — a CONFLICTING PR runs zero workflows>.

## Code review

<!--
  How the swat-review (Phase 6) is driven. swat-review is a single review
  pass either way; this flag only says WHERE the review comes from in handle-it's fix loop.
-->

- **Swat Reviewer runs in CI (GitHub Action):** <true | false — default **false**>
  <!--
    false (default): handle-it runs the reviewer locally each round — it calls
      Skill(swatkinson-toolkit:swat-review) for one pass, then fixes + pushes, then re-runs it.
    true: the repo auto-reviews every PR push via a swat-reviewer GitHub Action. handle-it does NOT
      run the reviewer — it waits for the Action's review, fixes + pushes (re-triggering the Action),
      and loops to the double-5/5 gate. Set true only once the Action is actually installed in the repo.
  -->

## Engine skills

<!-- Which skills the engine routes to. Defaults assume the agentsystem-core plugin + the bare diagnose skill are installed. Override if your repo uses different ones. NOTE: opening the PR is in-housed by handle-it (Phase 5, native `gh pr create --draft`), and the code review is in-housed by swat-review (no external code-review/simplify skill) — neither is an engine skill. -->

- **Implement (feature / clear bug):** <default `agentsystem-core:ship`>
- **Investigate (unclear bug):** <default `diagnose`>
- **Resolve conflicts:** <default `agentsystem-core:resolve-conflict`; migration-index conflicts → the Commands → Migrations resolve command>
- **Fix CI tests:** <default `agentsystem-core:fix-pr-tests`>

## Learned corrections

<!--
  Append-only. When the engine finds a value above was wrong at runtime (a command renamed,
  a wrong preview domain, a hard-rule path that moved), it fixes the field above AND adds a
  dated line here so the correction is visible and never silently lost.
-->

- _(none yet)_
