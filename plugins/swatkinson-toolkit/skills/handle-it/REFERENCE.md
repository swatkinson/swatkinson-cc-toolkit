# handle-it — reference

Mechanics, prompt templates, and runtime details for [SKILL.md](SKILL.md). The Linear tool namespace, the worktree command, the Linear state machine, and the hard rules are established by the repo's own `drain-queue` skill — this skill reuses them. The review loop is in-house (Phase 6), not Greptile.

## Skill invocation names

When a subagent or the orchestrator invokes a skill via the `Skill` tool, **plugin skills need their fully-qualified `plugin:skill` name** — a bare name errors `Unknown skill` (this is what made a canary subagent "fall back" to hand-implementing). In this repo:

- **`swatkinson-toolkit:` prefix required** (this plugin's own skills + bundled agents): `Skill(swatkinson-toolkit:claudecodile-review)`; and `Agent(subagent_type: "swatkinson-toolkit:handle-it-shipper" | "…handle-it-investigator" | "…handle-it-test-runner" | "…claudecodile-reviewer" | "…claudecodile-fixer" | "…issue-watcher-scanner")`. Bare names won't resolve once installed as a plugin.
- **`agentsystem-core:` prefix required:** `agentsystem-core:ship`, `agentsystem-core:open-pr`, `agentsystem-core:resolve-conflict`, `agentsystem-core:address-pr-comments`, `agentsystem-core:fix-pr-tests`, `agentsystem-core:commit`, `agentsystem-core:commit-and-push`.
- **Bare name works** (built-in / unprefixed skills): `diagnose`, `code-review`, `resolve-migration-conflict`, `tdd`, `grill-with-docs`, `to-issues`, `to-prd`.

If a subagent reports it "implemented directly because /ship wasn't available," that's this bug — the name was unqualified. Fix the name; never accept a hand-implementation that skipped the routed skill's gates.

## Linear runtime resolution

The Linear MCP tools in this setup are namespaced **`mcp__linear-server__*`** (namespace is harness/config-dependent — if it differs, use whatever Linear tools the session exposes). Resolve IDs once per run (teams/labels/statuses/cycles are referenced by **ID**, not string) and reuse:

- **Me / assignee:** `mcp__linear-server__get_user` query=`me` → your user id. "Assign to myself" = this id, valid only if the Linear MCP is authed as you.
- **Team:** the `BE` prefix is the **key** of the team named **"Software Development"** (id `3412f0ba-a308-4017-8ebf-912b4d4c8454`). `list_teams`'s `query` searches *names*, not keys — searching "BE" returns empty. Match `key === "BE"` from `list_teams`, or read it from `get_user(me).teams[]` (each entry has `{id, name, key}`). Pass the team **id** to the calls below.
- **Statuses:** `mcp__linear-server__list_issue_statuses` team=`<team-id>` → capture the Backlog / Todo / In Progress / In Review / Done ids. Confirm exact names against the result.
- **`ai` label:** `mcp__linear-server__list_issue_labels` team=`<team-id>` name=`ai` → the `ai` label id. Create only if the harness can; else bail and ask the user.
- **Active cycle:** `mcp__linear-server__list_cycles` teamId=`<team-id>` type=`current` → the current cycle id for new-issue attachment.

`mcp__linear-server__get_issue` needs **`includeRelations: true`** to return `relations` (`blockedBy`/`blocks`) — omitted by default. `list_issues` truncates descriptions and hides relations — always `get_issue` (with `includeRelations: true`) per issue before judging context-completeness or blockers. (`list_issues` filters: `assignee="me"`/`"null"`, `state`, `label`, `team`, `cycle`.)

## Linear-down fallback (manual mode)

When the Linear MCP (`mcp__linear-server__*`) is unavailable, the Linear half goes manual; the git/gh pipeline is unchanged.

- **Announce:** "Linear isn't connected — switching to copy-paste mode. Paste issue text in, and I'll hand back anything to create/edit as one copyable block."
- **Reading an issue (EP1/EP4):** ask the user to paste title + description + any "Blocked by". Judge context-completeness from that.
- **Transitions + blocking detection:** you can't auto-claim (`In Progress`), un-draft, move to `In Review`, or read `relations`. State the transition for the user to make by hand, and ask them to confirm whether the issue is blocked (and by what). The Phase 2 wait becomes: ask the user to confirm the blocker is merged before you implement.
- **Writing/editing issues:** emit ALL of them in ONE fenced markdown block the user copies wholesale into Linear. The metadata line tells the user what to set by hand (assignee / labels / cycle / relations — no API to do it). Blockers first. Template per issue:

```
---
### <title>
**Assignee:** <you> · **Labels:** ai, ready-for-agent · **Cycle:** current · **Blocked by:** BE-#### (or none)

## What to build
<end-to-end behavior>

## Acceptance criteria
- [ ] ...

## Blocked by
- BE-#### (or "None - can start immediately")
---
```

## Resume detection (Phase 0)

`/handle-it ####` can be dropped at any stage — already implemented, mid-review, awaiting senior, etc. Phase 0 derives the **furthest-completed phase** and jumps there instead of restarting at Phase 1.

**An explicit user pick-up instruction wins** ("I've implemented on worktree X, start at review") — but verify its preconditions from ground truth first; if a precondition is missing (no worktree / no PR), say so and fall back to detection.

**Ground truth is authoritative; the Linear status block is only a hint** (it can lag a crash or a manual git action). Gather:
- Worktree for the branch: `bun run worktree:ls --json` (branch follows `<domain>/<be-id>/<kebab>`).
- PR for the branch: `gh pr view <branch> --json number,state,isDraft,mergeable,reviewDecision,comments` — and whether a `## 🐊 Claudecodile Rating:` issue comment exists + its score.
- Linear status (`get_issue`) + the `<!-- handle-it:status -->` block.

**Map evidence → entry phase:**

| Ground truth | Resume at |
|---|---|
| No worktree, no PR, issue `Backlog`/`Todo` | **Phase 1** (route/plan) — or Phase 2/3 if planned + a blocker to check |
| Worktree exists, edits present, no PR | **Phase 5** (open draft PR) — or Phase 4 if implementation looks incomplete |
| Draft PR, no 🐊 comment or `< 5/5` | **Phase 6** — pass the existing `RATING_COMMENT_ID` + score history into `/claudecodile-review` |
| Draft PR, 🐊 5/5, `mergeable` unknown / `CONFLICTING` | **Phase 7** (conflict gate) |
| Draft PR, 5/5, mergeable, CI not green | **Phase 8** (CI + preview) |
| Draft PR, 5/5, CI green, test boxes unticked | **Phase 9** (test-and-tick) |
| Draft PR, all four gates green | **Phase 10** (handoff) → WAIT (Phase 11) |
| Ready (non-draft) PR, `In Review`, not approved | Done — un-draft already happened (Phase 12). Tell the user the PR is already ready for senior review and stop. |
| PR `MERGED` | Done — fire the unblock notice for `relations.blocks` if relevant, then stop. |

**Reconcile + announce:** if ground truth contradicts the status block, trust ground truth, rewrite the block (see [Linear status block](#linear-status-block)), and tell the user where you're resuming and why: *"Resuming BE-#### at Phase 6 — found draft PR #N at 🐊 3/5, worktree present."*

## Assessing context-completeness (EP routing)

Context-complete when title + description (or the project docs it explicitly points to) would let a fresh agent implement with **no follow-up questions**: clear what-to-build, acceptance criteria, non-obvious constraints. Vague titles, "fix the thing", or a one-line description with no acceptance criteria → not complete → EP1 (grill).

## Creating issues (EP2 / EP3)

Use `/to-issues` (and `/to-prd` first for EP3) for the breakdown + body template. After each issue is created, apply the defaults the planning skills don't set:

- `save_issue`: assignee = me, cycle = active cycle, add the `ai` label (alongside `ready-for-agent` / category labels).
- Set the real Linear **relations**: for each "Blocked by BE-X", create the `blockedBy` relation (and inverse `blocks`). Publish in dependency order so blocker ids exist first.

## Implement subagent (Phase 4)

The implementer is a **pre-built custom subagent**, not an inline prompt — its full brief lives in its agent file (bundled in this plugin: `agents/handle-it-*.md`). The orchestrator classifies the issue and spawns the right one in the already-created worktree (shared filesystem — **no** `isolation: "worktree"`; the worktree exists, with `--db-branch` only if the issue is migration-bearing):

- **Feature / enhancement / clear bug** → `Agent(subagent_type: "swatkinson-toolkit:handle-it-shipper", …)` (Sonnet) — routes through `agentsystem-core:ship`.
- **Unclear bug** (symptom / error log / perf, no root cause) → `Agent(subagent_type: "swatkinson-toolkit:handle-it-investigator", …)` (Opus) — routes through `diagnose`. It may report a fix is feature-sized → orchestrator re-routes to the Shipper.

Pass the agent: the absolute worktree path, the full issue brief (title + description + acceptance criteria), and the issue id. The agent files already encode the AFK rule (invoke the routed skill, decide confirm/plan gates yourself), the qualified-skill-name rule, in-scope discipline, the `check`+`test` verify gate, the edit-only/no-git rule, and the hard-rule bail list — don't restate them inline. If a subagent reports it "implemented directly because /ship wasn't available," that's the unqualified-name bug (see [Skill invocation names](#skill-invocation-names)) — fix the name; never accept a hand-implementation that skipped the routed skill's gates.

**Git ownership:** the subagent leaves its edits in the worktree and reports a proposed Conventional Commit subject; the **orchestrator** commits (`Refs: BE-####`) + pushes from the foreground after it returns. Background subagents *hang* on `git push` (the permission prompt can't be answered from a background agent) and ignore "don't push" instructions (findings #12/#13), so all git runs in the foreground where the prompt surfaces.

**Stage explicit paths — never `git add -A` / `git add .`.** Windows `worktree:new` / `EnterWorktree` checkouts leave pre-existing CRLF↔LF line-ending churn in tracked `.pi/` and `.claude/` files; `git add -A` sweeps that churn (commonly 1000+ lines across a dozen files) into the commit and the PR. Stage only the paths the implementer reported touching (`git add <path> …`), then `git diff --cached --stat` to confirm the staged set is exactly the intended files before committing. (Verify a suspicious diff with `git show` — pure `-`/`+` line churn with no content change is the EOL tell.)

**Run `git commit` and `git push` as two separate foreground calls — not a `git commit && git push` chain.** A chained `commit && push` can be denied by the auto-mode classifier as a sub-agent-boundary breach (it reads as "the agent committed *and* pushed in one action"); splitting them avoids the false-positive and is cleaner anyway. `Bash(git push:*)` + `Bash(git commit:*)` are allow-listed in this repo's `.claude/settings.local.json` so the foreground push/commit is prompt-free — an agent can't self-widen permissions, so the user added that rule by hand.

## Open DRAFT PR (Phase 5)

Run `agentsystem-core:open-pr` (qualified — bare `open-pr` errors) at **`mode=balanced`** and **as a draft** (put `draft` / `--draft` intent in the args; open-pr opens `--draft` when asked). Rationale for balanced: Phase 4 already ran the full `check` + `test`, so balanced's diff-scoped gate is right; `production` re-runs the whole suite and **blocks on pre-existing unrelated failures**. open-pr writes the title + Summary/Test-plan body (markdown checkboxes) and **requires a confirm gate** (let it fire). Ensure the bare `BE-####` appears in the Summary so Linear auto-links. Run it with the **worktree as cwd**. Then `save_comment` the PR URL on the issue but keep Linear `In Progress` — a draft is not review-ready.

## Stacked PRs (blocker-override)

The default flow waits for a blocker to merge (Phase 2) and opens the PR against `main` (Phase 5). When the **user explicitly overrides** ("branch it off BE-XXXX / PR #M, stack it") — implementing on top of an unmerged blocker instead of waiting — use this procedure. Only on an explicit override; the default stays wait-then-`base=main`.

1. **Branch (Phase 3):** create the worktree off the blocker's branch, not `main` — `git worktree add <path> -b <branch> origin/<blocker-branch>` — and **unset the inherited upstream** (`git branch --unset-upstream`) so the first push sets its own.
2. **Open PR (Phase 5):** open the draft with **`--base <blocker-branch>`** (not `main`), so the diff/review/CI see only *this* issue's change stacked on the blocker — note in the PR body that it's stacked on #M and will retarget on merge.
3. **After Phase 12 (un-draft):** when the blocker merges, GitHub usually auto-retargets the stacked PR to `main` — tell the user to **verify** (`gh pr view <N> --json baseRefName`) and run `gh pr edit <N> --base main` if it didn't. Rebase (Phase 7 flow) if the diff drifted. handle-it does not watch for this; the user handles it manually.

## Review ⇄ fix loop (Phase 6) — delegated to /claudecodile-review

The entire review⇄fix loop lives in the **`claudecodile-review`** skill (bundled in this plugin), so the logic isn't duplicated and the loop is reusable on any PR. Phase 6 just calls `Skill(swatkinson-toolkit:claudecodile-review)` with the **worktree path** + **PR number** (+ existing `RATING_COMMENT_ID`/score history on a resume).

**It's still functionally the inline loop** — the Skill tool loads those instructions into *this orchestrator's context* (not a fresh isolated agent), so:
- The loop spawns `swatkinson-toolkit:claudecodile-reviewer` (Opus) + `swatkinson-toolkit:claudecodile-fixer` (Sonnet) exactly as before; **the orchestrator still owns every commit + push** between rounds (its foreground git allow-list applies).
- Same `5/5 = no P0/P1 AND every in-scope P2/P3 fixed` gate (only scope-deferred nits may remain), same round-1-full → incremental → final-full-pass scope, same single `## 🐊 Claudecodile Rating: N/5` comment held by id, same plateau guard.
- As the loop reports each round, the orchestrator mirrors the latest rating into the **Review** status cell.

**The orchestrator handles the skill's return outcome:**
- `5/5` → Phase 7; any returned P2/P3 are scope-deferred (in-scope nits were fixed in-loop) — file the important ones as Linear follow-up comments.
- `plateau-bail` → `AskUserQuestion` (accept-as-is / guide / keep iterating).
- `handback-bail` (product decision / hard-rule file) → bail + surface.

Full loop mechanics, the HEREDOC-literal posting rule, and the standalone-vs-delegated contract are in the **`claudecodile-review` skill's REFERENCE.md** (bundled in this plugin) — the single source of truth. Agents: `swatkinson-toolkit:claudecodile-reviewer`, `swatkinson-toolkit:claudecodile-fixer`.

## Resolving review threads (Phase 12)

On the user's "looks good":

**Step 1 — tick off all remaining unchecked manual items.** The user's approval confirms manual testing passed. Read the PR body, flip every remaining `- [ ]` in the test-plan section to `- [x]`, and write it back:

```bash
# read current body, edit in place, update PR
gh pr view <N> --json body --jq '.body' > /tmp/pr-body.md
# (sed or edit: replace all remaining "- [ ]" with "- [x]")
gh pr edit <N> --body "$(cat /tmp/pr-body.md)"
```

**Step 2 — resolve inline review threads.** Clean up the review threads the loop accumulated so the senior reviewer sees only genuinely-open conversations. By the time the user approves, every thread is addressed → resolve them all in one batch (no per-comment matching needed):

```bash
# 1. node IDs of UNRESOLVED threads (paginate with endCursor if >100)
gh api graphql -f query='query($o:String!,$r:String!,$n:Int!){repository(owner:$o,name:$r){pullRequest(number:$n){reviewThreads(first:100){nodes{id isResolved}}}}}' \
  -F o=<owner> -F r=<repo> -F n=<N> \
  --jq '.data.repository.pullRequest.reviewThreads.nodes[] | select(.isResolved==false) | .id'
# 2. resolve each id
gh api graphql -f query='mutation($t:ID!){resolveReviewThread(input:{threadId:$t}){thread{isResolved}}}' -F t=<thread-id>
```

**Only inline review threads are resolved.** The `## 🐊 Claudecodile Rating: N/5` comment is a PR *issue* comment, not a review thread — `resolveReviewThread` can't and won't touch it, so the final rating + bug summary stays on the PR. Resolve (don't delete) so the flagged-then-fixed history is preserved. This is the one GraphQL touch in the skill; everything else is REST (`gh pr comment` / `gh api .../comments` / `gh pr edit`). After resolving, `gh pr ready <N>` (un-draft) and move Linear to **In Review**.

## No-merge-conflicts gate (Phase 7)

After 5/5 and before reading CI, confirm the PR is mergeable: `gh pr view <N> --json mergeable,mergeStateStatus`. If `CONFLICTING`, resolve it now (see [Merge conflicts](#merge-conflicts-phase-7-gate--phase-13-watch)) — **don't read CI yet**. This gate exists because of finding #21: a `CONFLICTING` PR has **no merge-ref**, so **zero `pull_request` workflows run** (CI *and* Vercel show 0 runs). An empty checks list almost always means "conflicting", not "CI broken" — check mergeability first before diagnosing CI as down.

## CI/CD green + preview (Phase 8)

With the PR mergeable, `gh pr checks <N>`. Classify failures:
- **Code/test failure** (e.g. `check`, a failing test job) → spawn `swatkinson-toolkit:handle-it-shipper` in the worktree (or `agentsystem-core:fix-pr-tests` for failing CI tests specifically); the orchestrator commits + pushes; re-check.
- **Infra/workflow failure** (env, `deploy-vercel`, neon/electric setup) → NOT code-fixable; **surface to the user**. One self-inflicted case: a `--db-branch` worktree on a *non-migration* issue pre-creates the preview Electric env, which can collide with CI's `deploy-vercel` env-creation (finding #8) — the fix is upstream (Phase 3 gating `--db-branch` to migration issues only), not patchable on this PR.

**Drafts deploy.** A draft PR **does** run CI and Vercel as long as it's conflict-free — there is no draft-skip in `preview-deploy.yml`. (Earlier canary diagnoses wrongly blamed "drafts skip preview" / "Actions outage"; the real cause was always the PR being `CONFLICTING`.) So the preview link is available while the PR is still a draft — fetch it here.

**Where the preview URL actually is — read this, it's repo-specific and not where you'd guess.** On both CaivanOS and workbench the **native Vercel integration is disabled** — its check/comment shows *"Ignored Build Step" / "1 Skipped Deployment (Ignored)"* and has **no usable URL** (don't chase it; `rg vercel.app` returns empty — there is no `*.vercel.app` URL on these repos). The real preview is built by the **`deploy-vercel` GitHub Action** and its URL is posted/edited into the **`github-actions` PR comment**, on a **custom domain**:
- **CaivanOS:** `…dev.caivanos.app` (e.g. `caivanos-git-<branch>-…dev.caivanos.app`).
- **Workbench:** stable alias `workbench-git-<branch>.caivan.dev`.

So: `gh pr view <N> --comments` and read the URL from the **`github-actions`** comment (or the `deploy-vercel` job log) — not the Vercel-bot comment. Builds take minutes — poll, re-check if still building, give up after ~5 attempts. On success surface `✅ Preview ready: …` (format in Phase 10).

## Test-and-tick (Phase 9)

Spawn `Agent(subagent_type: "swatkinson-toolkit:handle-it-test-runner", …)` (Haiku) with the worktree path + the PR's Test-plan items. It runs only the **headless** items (`bun run check`, full `bun run test`, builds/focused suites if listed) and reports pass/fail per item — it does **NOT** edit the PR, tick boxes, commit, or push.

The **orchestrator** then ticks the boxes the tester confirmed: `gh pr view <N> --json body`, flip `- [ ]`→`- [x]` for the passed automatable items, `gh pr edit <N> --body`. Leave click-through / visual / browser items unticked for the human (Phase 10). The tester calls out pre-existing unrelated failures separately so the orchestrator doesn't tick or treat them as new.

## Manual-review handoff (Phase 10)

All four pre-handoff gates are now green — 🐊 5/5, no merge conflicts, CI passed with a Vercel link, tester ran + ticked the bun-run items. **Re-verify mergeability one last time** (`gh pr view <N> --json mergeable` — main may have moved since Phase 7) before handing off; resolve if it drifted. Then emit the structured handoff template (PR stays a draft):

```
## Ready for your manual review

**Preview:** <preview-url>
**Local:** `cd <worktree-absolute-path> && <bun|pnpm> dev`

**Manual criteria:**
- [ ] <unticked test-plan item 1>
- [ ] <unticked test-plan item 2>
…

Tell me if it looks good and I'll check off the manual tests and mark it as ready for you.
```

Populate **Manual criteria** by reading the PR description (`gh pr view <N> --json body`) and extracting all remaining `- [ ]` lines from the test-plan section — these are the click-through / visual items the tester couldn't auto-run.

**The PR stays a DRAFT through this handoff and the user's manual testing** — it is un-drafted only on the user's "looks good" (Phase 12). Then **WAIT** for the user's verdict (Phase 11) — do not poll, do not un-draft, do not request reviewers.

**If the Vercel deploy failed** (Phase 8) — `deploy-vercel` red, or native `Vercel` "Canceled by Ignored Build Step" with no URL — replace the Preview line with `**Preview:** ⚠️ Deploy failed — test locally` and include the failed-job URL. A 14–16s `deploy-vercel` failure is usually pre-build (env/secret/collision), not the change — a `--db-branch` worktree on a non-migration issue is a known cause.

## Manual-review interaction (Phase 11)

While waiting, if the user reports a problem with their manual testing, treat it as a mini Phase 4: classify and spawn `swatkinson-toolkit:handle-it-shipper` (clear fix/feature) or `swatkinson-toolkit:handle-it-investigator` (unclear bug) to fix it in the worktree, orchestrator commits + pushes, then — if the change is non-trivial — re-invoke `Skill(swatkinson-toolkit:claudecodile-review)` (incremental + a final full pass) so the fix stays at 5/5. The PR remains a draft throughout.

**After each fix**, before waiting again:
1. **If the fix or new feature introduces new manually-testable behavior**, append those as new `- [ ]` items to the test-plan in the PR description: `gh pr view <N> --json body` → add under the existing manual items → `gh pr edit <N> --body`.
2. **Re-emit the Phase 10 handoff template** — re-read the current unticked `- [ ]` items from the PR description (including any just added) so the criteria list is always current.

On the user's **"looks good"** → Phase 12.

## Merge conflicts (Phase 7 gate)

Conflicts are resolved at two points: the Phase 7 pre-CI gate, and while watching to merge (Phase 13). Both use the same flow — `gh pr view <N> --json mergeable,mergeStateStatus`; on `CONFLICTING` (main moved), resolve instead of waiting:

- **Migration-index collision** (diff confined to `migrations/` + `_journal.json`/snapshot) → **`bun run db:rebase`** (#633; automates the old 11-step `/resolve-migration-conflict`). Rebases onto main, regenerates the migration on main's snapshot, re-migrates the Neon preview, then `db:migrate` + `check`. Run in a **`--db-branch` worktree**. Three fail-closed behaviors:
  - **Never pushes** — run the `git push --force-with-lease …` it prints (the one sanctioned force-push).
  - **Stops on hand-authored SQL** (`DO $$`/`RAISE`, DML backfills, `CHECK` drop/recreate, comments) and prints the statements → **bail**, surface them (a human splices them in).
  - **Aborts on any code-file conflict** → not meta-only; handle code first, commit, re-run `db:rebase`.
- **Non-migration / code conflicts** → `agentsystem-core:resolve-conflict`, then re-push normally (no force).
- **Mixed** → resolve code with `agentsystem-core:resolve-conflict`, commit, then `bun run db:rebase`.

> #633 still open as of writing — until it merges, `bun run db:rebase` won't exist; fall back to the `resolve-migration-conflict` skill (the manual equivalent).

## Waiting / re-entrancy (Phase 2 blockers)

One point waits on external state: **Phase 2** (after planning, before claim — a blocker hasn't merged). Use `ScheduleWakeup`.

**Don't pass `"<the original /handle-it invocation>"` as the wakeup prompt.** Re-firing the full slash-command re-expands this entire SKILL.md into context on *every* tick. Instead pass a **lean, self-contained instruction string** (no `/handle-it` prefix) that carries the state and the branch logic inline.

- **Phase 2 (blocker wait):** `ScheduleWakeup(delaySeconds: 1200–1800, prompt: "Re-check Linear blocker for BE-####: get_issue (includeRelations) → if blockedBy BE-XXXX is Done, re-invoke /handle-it BE-#### to claim + implement; else ScheduleWakeup again (same prompt). Do not claim while blocked.")`. The issue is never claimed (`In Progress`) while blocked, so a re-fire can't double-claim.

## Status columns

| Column | `✅` | `⏳` | `❌` |
|---|---|---|---|
| Plan | issue context-complete | grilling / PRD in progress | — |
| Implement | `handle-it-shipper`/`-investigator` done + orchestrator pushed | implementing | bailed |
| Draft PR | `open-pr` opened the draft (append `(#N)` to the issue cell) | opening | — |
| Review | 🐊 rated 5/5 (no P0/P1, in-scope P2/P3 fixed) | mid review⇄fix loop — show the rating (`⏳ 4/5`) | loop bailed (product/hard-rule) |
| CI | all checks green + preview link | fixing failures | infra failure surfaced to user |
| Manual Test | user confirms passed | handoff delivered, awaiting user | user reports a problem |
| Ready | PR un-drafted + Linear `In Review` (user said "looks good") | — | — |

handle-it auto-detects CI via `gh`; Manual Test only flips when the user tells you; Ready flips on Phase 12. The PR is a **draft** through Review + CI + Manual Test; it un-drafts only on the user's "looks good" (Phase 12) — handle-it stops there.

## Linear status block

Mirror the live status table into the **top of the Linear issue's description** so the issue page reflects pipeline state without the user reading the chat. Maintain it as a fenced HTML-comment-delimited block so it can be rewritten idempotently without clobbering the human-authored description:

```
<!-- handle-it:status -->
| Phase | State |
|---|---|
| Plan | ✅ |
| … | … |
_Updated by /handle-it · PR #<N>_
<!-- /handle-it:status -->
```

Read-modify-write each update: `get_issue` → if the `<!-- handle-it:status -->…<!-- /handle-it:status -->` markers exist, replace **only** that region; else **prepend** the block (keep the original description below it untouched) → `save_issue` with the new description. Never drop or reorder the human's prose. Update it at each phase transition (same beats as the chat status table). In Linear-down manual mode there's no API to write it — skip the mirror and keep the chat table only.

**Wrap URLs and issue-id-like substrings in the block in backticks.** A bare preview URL such as `workbench-git-be-2240.caivan.dev` contains the substring `be-2240`, which Linear auto-parses into an `<issue>` mention and mangles the footer. Backtick any preview URL / branch name you put in the block (`` `workbench-git-be-2240.caivan.dev` ``) so Linear renders it literally.

## Workbench (best-effort)

Workbench is **Next.js 15 / React 19 / pnpm 10 / Drizzle + Neon**. The facts below were confirmed on a real run (BE-2240); update if the repo changes. Differences from CaivanOS:

- **Package manager: `pnpm`** (not bun). All commands use `pnpm`.
- **Worktree:** no repo worktree script — `git worktree add .claude/worktrees/<be-id> -b <be-id> main` (branch = the Linear `gitBranchName`, e.g. `be-2240`), then copy `.env` from the primary checkout. **DB-string ask is conditional** (see Phase 3 / autonomy gate c): hard-block-and-wait for a connection string only on a DB/schema/migration change; a non-DB change just quick-confirms the copied `.env`.
- **Verify gate: `pnpm check` only** (= `next lint && tsc --noEmit`). **There is NO test runner** — no `test` script, no vitest/jest/playwright. Do **not** run `pnpm test` / `bun run test`; `check` green is the full gate.
- **CI / preview: wired.** The CI check is named **"Next Check"**. Vercel deploys on draft PRs; the preview URL is the **`github-actions` `deploy-vercel`** comment on the stable alias **`workbench-git-<branch>.caivan.dev`** (the native Vercel integration shows "Ignored Build Step" — see Phase 8).
- Everything else (Linear routing, sonnet/opus split, status table, hard rules) is identical.
