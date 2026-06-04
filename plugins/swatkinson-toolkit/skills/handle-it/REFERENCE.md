# handle-it — reference

Mechanics, prompt templates, and runtime details for [SKILL.md](SKILL.md). The Linear tool namespace, the worktree command, the Linear state machine, and the hard rules are established by the repo's own `drain-queue` skill — this skill reuses them. The review loop is in-house (Phase 6), not Greptile.

## Skill invocation names

When a subagent or the orchestrator invokes a skill via the `Skill` tool, **plugin skills need their fully-qualified `plugin:skill` name** — a bare name errors `Unknown skill` (this is what made a canary subagent "fall back" to hand-implementing). In this repo:

- **`agentsystem-core:` prefix required:** `agentsystem-core:ship`, `agentsystem-core:open-pr`, `agentsystem-core:resolve-conflict`, `agentsystem-core:address-pr-comments`, `agentsystem-core:fix-pr-tests`, `agentsystem-core:commit`, `agentsystem-core:commit-and-push`.
- **Bare name works** (user/project skills): `diagnose`, `code-review`, `resolve-migration-conflict`, `tdd`, `grill-with-docs`, `to-issues`, `to-prd`.

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
| Ready (non-draft) PR, `In Review`, not approved | **Phase 13** (watch to merge) |
| PR `MERGED` | Phase 13 tail — fire the unblock notice for `relations.blocks`, then done |

**Reconcile + announce:** if ground truth contradicts the status block, trust ground truth, rewrite the block (see [Linear status block](#linear-status-block)), and tell the user where you're resuming and why: *"Resuming BE-#### at Phase 6 — found draft PR #N at 🐊 3/5, worktree present."*

## Assessing context-completeness (EP routing)

Context-complete when title + description (or the project docs it explicitly points to) would let a fresh agent implement with **no follow-up questions**: clear what-to-build, acceptance criteria, non-obvious constraints. Vague titles, "fix the thing", or a one-line description with no acceptance criteria → not complete → EP1 (grill).

## Creating issues (EP2 / EP3)

Use `/to-issues` (and `/to-prd` first for EP3) for the breakdown + body template. After each issue is created, apply the defaults the planning skills don't set:

- `save_issue`: assignee = me, cycle = active cycle, add the `ai` label (alongside `ready-for-agent` / category labels).
- Set the real Linear **relations**: for each "Blocked by BE-X", create the `blockedBy` relation (and inverse `blocks`). Publish in dependency order so blocker ids exist first.

## Implement subagent (Phase 4)

The implementer is a **pre-built custom subagent**, not an inline prompt — its full brief lives in its agent file (`.claude/agents/handle-it-*.md`). The orchestrator classifies the issue and spawns the right one in the already-created worktree (shared filesystem — **no** `isolation: "worktree"`; the worktree exists, with `--db-branch` only if the issue is migration-bearing):

- **Feature / enhancement / clear bug** → `Agent(subagent_type: "handle-it-shipper", …)` (Sonnet) — routes through `agentsystem-core:ship`.
- **Unclear bug** (symptom / error log / perf, no root cause) → `Agent(subagent_type: "handle-it-investigator", …)` (Opus) — routes through `diagnose`. It may report a fix is feature-sized → orchestrator re-routes to the Shipper.

Pass the agent: the absolute worktree path, the full issue brief (title + description + acceptance criteria), and the issue id. The agent files already encode the AFK rule (invoke the routed skill, decide confirm/plan gates yourself), the qualified-skill-name rule, in-scope discipline, the `check`+`test` verify gate, the edit-only/no-git rule, and the hard-rule bail list — don't restate them inline. If a subagent reports it "implemented directly because /ship wasn't available," that's the unqualified-name bug (see [Skill invocation names](#skill-invocation-names)) — fix the name; never accept a hand-implementation that skipped the routed skill's gates.

**Git ownership:** the subagent leaves its edits in the worktree and reports a proposed Conventional Commit subject; the **orchestrator** commits (`Refs: BE-####`) + pushes from the foreground after it returns. Background subagents *hang* on `git push` (the permission prompt can't be answered from a background agent) and ignore "don't push" instructions (findings #12/#13), so all git runs in the foreground where the prompt surfaces. `Bash(git push:*)` + `Bash(git commit:*)` are allow-listed in this repo's `.claude/settings.local.json` so the foreground push/commit is prompt-free — an agent can't self-widen permissions, so the user added that rule by hand.

## Open DRAFT PR (Phase 5)

Run `agentsystem-core:open-pr` (qualified — bare `open-pr` errors) at **`mode=balanced`** and **as a draft** (put `draft` / `--draft` intent in the args; open-pr opens `--draft` when asked). Rationale for balanced: Phase 4 already ran the full `check` + `test`, so balanced's diff-scoped gate is right; `production` re-runs the whole suite and **blocks on pre-existing unrelated failures**. open-pr writes the title + Summary/Test-plan body (markdown checkboxes) and **requires a confirm gate** (let it fire). Ensure the bare `BE-####` appears in the Summary so Linear auto-links. Run it with the **worktree as cwd**. Then `save_comment` the PR URL on the issue but keep Linear `In Progress` — a draft is not review-ready.

## Review ⇄ fix loop (Phase 6) — delegated to /claudecodile-review

The entire review⇄fix loop lives in the **`/claudecodile-review`** skill (`~/.claude/skills/claudecodile-review/`), so the logic isn't duplicated and the loop is reusable on any PR. Phase 6 just calls `Skill(claudecodile-review)` with the **worktree path** + **PR number** (+ existing `RATING_COMMENT_ID`/score history on a resume).

**It's still functionally the inline loop** — the Skill tool loads those instructions into *this orchestrator's context* (not a fresh isolated agent), so:
- The loop spawns `claudecodile-reviewer` (Opus) + `claudecodile-fixer` (Sonnet) exactly as before; **the orchestrator still owns every commit + push** between rounds (its foreground git allow-list applies).
- Same `5/5 = no P0/P1 AND every in-scope P2/P3 fixed` gate (only scope-deferred nits may remain), same round-1-full → incremental → final-full-pass scope, same single `## 🐊 Claudecodile Rating: N/5` comment held by id, same plateau guard.
- As the loop reports each round, the orchestrator mirrors the latest rating into the **Review** status cell.

**The orchestrator handles the skill's return outcome:**
- `5/5` → Phase 7; any returned P2/P3 are scope-deferred (in-scope nits were fixed in-loop) — file the important ones as Linear follow-up comments.
- `plateau-bail` → `AskUserQuestion` (accept-as-is / guide / keep iterating).
- `handback-bail` (product decision / hard-rule file) → bail + surface.

Full loop mechanics, the HEREDOC-literal posting rule, and the standalone-vs-delegated contract are in **`~/.claude/skills/claudecodile-review/REFERENCE.md`** — the single source of truth. Agents: `claudecodile-reviewer`, `claudecodile-fixer` (both in `~/.claude/agents/`).

## Resolving review threads (Phase 12)

On the user's "looks good", before un-drafting, clean up the inline review threads the loop accumulated so the senior reviewer sees only genuinely-open conversations. By the time the user approves, every thread is addressed → resolve them all in one batch (no per-comment matching needed):

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
- **Code/test failure** (e.g. `check`, a failing test job) → spawn `handle-it-shipper` in the worktree (or `agentsystem-core:fix-pr-tests` for failing CI tests specifically); the orchestrator commits + pushes; re-check.
- **Infra/workflow failure** (env, `deploy-vercel`, neon/electric setup) → NOT code-fixable; **surface to the user**. One self-inflicted case: a `--db-branch` worktree on a *non-migration* issue pre-creates the preview Electric env, which can collide with CI's `deploy-vercel` env-creation (finding #8) — the fix is upstream (Phase 3 gating `--db-branch` to migration issues only), not patchable on this PR.

**Drafts deploy.** A draft PR **does** run CI and Vercel as long as it's conflict-free — there is no draft-skip in `preview-deploy.yml`. (Earlier canary diagnoses wrongly blamed "drafts skip preview" / "Actions outage"; the real cause was always the PR being `CONFLICTING`.) So the preview link is available while the PR is still a draft — fetch it here. Per the user's global rule: get the head SHA, read the Vercel check URL via `gh pr checks <N>` or the Vercel bot comment (`gh pr view <N> --comments`). Builds take minutes — poll, re-check if still building, give up after ~5 attempts. Prefer the stable branch-alias URL (`…-git-<branch>-….vercel.app`). On success surface `✅ Preview ready: …` (format in Phase 10).

## Test-and-tick (Phase 9)

Spawn `Agent(subagent_type: "handle-it-test-runner", …)` (Haiku) with the worktree path + the PR's Test-plan items. It runs only the **headless** items (`bun run check`, full `bun run test`, builds/focused suites if listed) and reports pass/fail per item — it does **NOT** edit the PR, tick boxes, commit, or push.

The **orchestrator** then ticks the boxes the tester confirmed: `gh pr view <N> --json body`, flip `- [ ]`→`- [x]` for the passed automatable items, `gh pr edit <N> --body`. Leave click-through / visual / browser items unticked for the human (Phase 10). The tester calls out pre-existing unrelated failures separately so the orchestrator doesn't tick or treat them as new.

## Manual-review handoff (Phase 10)

All four pre-handoff gates are now green — 🐊 5/5, no merge conflicts, CI passed with a Vercel link, tester ran + ticked the bun-run items. **Re-verify mergeability one last time** (`gh pr view <N> --json mergeable` — main may have moved since Phase 7) before handing off; resolve if it drifted. Then hand the user: the manual (click-through / visual) test-plan items still unticked, the branch + worktree `cd`, and the preview link:

```
✅ Preview ready: `<branch>` → <preview-url>
```

**The PR stays a DRAFT through this handoff and the user's manual testing** — it is un-drafted only on the user's "looks good" (Phase 12). Then **WAIT** for the user's verdict (Phase 11) — do not poll, do not un-draft, do not request reviewers.

**If the Vercel deploy failed** (Phase 8) — `deploy-vercel` red, or native `Vercel` "Canceled by Ignored Build Step" with no URL — do NOT claim a preview. Report the failed-job URL (`gh run view --job <id> --log-failed` to classify) and tell the user to test via the local `cd`. A 14–16s `deploy-vercel` failure is usually pre-build (env/secret/collision), not the change — a `--db-branch` worktree on a non-migration issue is a known cause.

## Manual-review interaction (Phase 11)

While waiting, if the user reports a problem with their manual testing, treat it as a mini Phase 4: classify and spawn `handle-it-shipper` (clear fix/feature) or `handle-it-investigator` (unclear bug) to fix it in the worktree, orchestrator commits + pushes, then — if the change is non-trivial — re-invoke `Skill(claudecodile-review)` (incremental + a final full pass) so the fix stays at 5/5. The PR remains a draft throughout. Loop back to the Phase 10 handoff. On the user's **"looks good"** → Phase 12.

## Merge conflicts (Phase 7 gate + Phase 13 watch)

Conflicts are resolved at two points: the Phase 7 pre-CI gate, and while watching to merge (Phase 13). Both use the same flow — `gh pr view <N> --json mergeable,mergeStateStatus`; on `CONFLICTING` (main moved), resolve instead of waiting:

- **Migration-index collision** (diff confined to `migrations/` + `_journal.json`/snapshot) → **`bun run db:rebase`** (#633; automates the old 11-step `/resolve-migration-conflict`). Rebases onto main, regenerates the migration on main's snapshot, re-migrates the Neon preview, then `db:migrate` + `check`. Run in a **`--db-branch` worktree**. Three fail-closed behaviors:
  - **Never pushes** — run the `git push --force-with-lease …` it prints (the one sanctioned force-push).
  - **Stops on hand-authored SQL** (`DO $$`/`RAISE`, DML backfills, `CHECK` drop/recreate, comments) and prints the statements → **bail**, surface them (a human splices them in).
  - **Aborts on any code-file conflict** → not meta-only; handle code first, commit, re-run `db:rebase`.
- **Non-migration / code conflicts** → `agentsystem-core:resolve-conflict`, then re-push normally (no force).
- **Mixed** → resolve code with `agentsystem-core:resolve-conflict`, commit, then `bun run db:rebase`.

> #633 still open as of writing — until it merges, `bun run db:rebase` won't exist; fall back to the `resolve-migration-conflict` skill (the manual equivalent).

## Waiting / re-entrancy (Phase 2 blockers)

The wait happens at one well-defined point: **after planning, before claim**. Use `ScheduleWakeup(delaySeconds: 1200–1800, prompt: "<the original /handle-it invocation>")`. On re-fire the skill is re-entrant: `get_issue` shows the issue context-complete but still `Todo` with an open `blockedBy` — re-check; still open → `ScheduleWakeup` again; `Done` → claim + implement. The issue is never claimed (`In Progress`) while blocked, so a re-fire can't double-claim. Don't pick 300s; 1200s+ is right for "a PR won't merge in the next few minutes."

## Status columns

| Column | `✅` | `⏳` | `❌` |
|---|---|---|---|
| Plan | issue context-complete | grilling / PRD in progress | — |
| Implement | `handle-it-shipper`/`-investigator` done + orchestrator pushed | implementing | bailed |
| Draft PR | `open-pr` opened the draft (append `(#N)` to the issue cell) | opening | — |
| Review | 🐊 rated 5/5 (no P0/P1, in-scope P2/P3 fixed) | mid review⇄fix loop — show the rating (`⏳ 4/5`) | loop bailed (product/hard-rule) |
| CI | all checks green + preview link | fixing failures | infra failure surfaced to user |
| Manual Test | user confirms passed | handoff delivered, awaiting user | user reports a problem |
| Senior Review | a **human** reviewer's latest state = APPROVED, no human CHANGES_REQUESTED (PR un-drafted, `In Review`) | awaiting a human verdict (a lone bot approval stays here) | a human requested changes |
| Merged | PR `state` = MERGED | awaiting merge | — |

handle-it auto-detects CI / Senior Review / Merged via `gh`; Manual Test only flips when the user tells you. The PR is a **draft** through Review + CI + Manual Test; it un-drafts (→ Senior Review) only on the user's "looks good" (Phase 12).

## Senior Review (human-only)

**Bot approvals never satisfy the senior-review gate.** `reviewDecision` is unreliable here — a bot review can flip it to `APPROVED`, which is exactly the false-pass that's been observed (`macroscopeapp[bot]` auto-approval read as the senior's sign-off). Compute the verdict from the reviews yourself:

```bash
gh pr view <N> --json latestReviews,reviews
```

Take the **latest review state per author**, then **drop bots and the PR author**:
- Explicit bot logins to ignore: `greptile`, `greptileai`, `macroscopeapp[bot]`.
- General rule: ignore any reviewer whose login ends in `[bot]` or whose author type is `Bot` (GitHub marks these), and the PR's own author.

From the remaining **human** reviews:
- `❌` — any human's latest state is `CHANGES_REQUESTED` → `agentsystem-core:address-pr-comments`, then resume the watch.
- `✅` — at least one human's latest state is `APPROVED` **and** no human is `CHANGES_REQUESTED`.
- `⏳` — otherwise (no human has weighed in yet; a lone bot approval does **not** advance the gate).

This gate only matters after Phase 12 un-drafts the PR; before that, bot reviews on the draft are ignored anyway.

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

## Workbench (best-effort)

Workbench isn't visible from here — this branch is from the user's description and needs confirmation on first use. Differences from CaivanOS:

- **Worktree:** no `bun run worktree:new`. Create it manually (the repo's own script if it has one, else `git worktree add`), copy `.env`, then **ask the user for the DB connection string** and put it in the worktree's `.env`. **Wait** — don't implement until given.
- **Verify / CI / preview commands:** assumed same shape (`bun run check`, `bun run test`, Vercel previews) but **unconfirmed** — verify on first run and update this section. The Phase 6 review loop and Phase 8 CI check are repo-agnostic (they use `code-review` + `gh`), so they carry over; only the worktree + verify commands differ.
- Everything else (Linear routing, sonnet/opus split, status table, hard rules) is identical.

> ⚠️ Placeholders to confirm the first time `/handle-it` runs in workbench: exact worktree setup command, check/test commands, and whether Vercel previews are wired.
