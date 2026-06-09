---
name: handle-it
description: End-to-end orchestrator that takes a Linear issue (or a freeform feature/project) and drives it through planning → implementation → draft PR → an in-house review⇄fix loop (rated to 5/5) → conflict-free CI + preview → an auto-tester → your manual review (PR stays a draft) → ready-for-review on your approval, with a live status table and Linear blocking awareness. Stops after un-drafting — senior review and merge are fully manual. Use when the user invokes /handle-it, or asks to take an issue/feature all the way to a review-ready PR.
---

# handle-it

You are the **orchestrator** (run as Opus, in the main conversation). You route the request to the right planning entrypoint, then drive each target issue through the full lifecycle — implement (Sonnet) → draft PR → review⇄fix loop (🐊 to 5/5) → resolve conflicts → CI + preview → test-and-tick → manual-review handoff (**PR stays a draft**) → mark ready on your approval — keeping a live status table and honoring Linear blocking relations. **Stops after un-drafting** — senior review and merge are fully manual.

**Autonomy contract:** Run autonomously from implementation through the review loop, conflict resolution, CI/preview, and the auto-tester — don't checkpoint between those. When waiting on external state (a blocker to merge), **loop and wait yourself** (`ScheduleWakeup`). The human gates are exactly: (a) `/grill-with-docs` during planning, (b) `agentsystem-core:open-pr`'s draft-publish confirm, (c) workbench's DB-connection-string ask (only for a DB/schema/migration change; a non-DB change just quick-confirms the copied `.env`), (d) the **manual-review gate** — the PR stays a **draft** through review/CI/preview/test-and-tick; you hand it off for manual testing and WAIT; on the user's "looks good" you un-draft (mark ready for review) and tell them to request senior review — **then stop**, (e) a **bail** when you genuinely cannot proceed (`PushNotification`, update the table, stop).

Lifecycle mechanics, subagent prompt templates, Linear runtime resolution, and workbench specifics live in **[REFERENCE.md](REFERENCE.md)** — load it before Phase 4. Invoke skills by their **exact** names — plugin skills need their `plugin:` prefix or `Skill(...)` errors `Unknown skill` (see REFERENCE → Skill invocation names). **This toolkit is itself a plugin (`swatkinson-toolkit`):** spawn its bundled agents with `subagent_type: "swatkinson-toolkit:<agent>"` and invoke its sibling skills as `Skill(swatkinson-toolkit:<skill>)` — bare names won't resolve. External skills keep their own prefixes (`agentsystem-core:ship`, etc.; `code-review`/`diagnose` are bare).

## Phase 0 — Preflight & resume detection

1. **Detect the repo.** CaivanOS (`app.caivanos`) is fully supported. Workbench is best-effort (see REFERENCE → Workbench). Anything else → tell the user it's not configured and stop.
2. **Confirm Linear tools.** Prefer the Linear MCP tools (`mcp__linear-server__*` in this setup). If absent, tell the user and switch to **manual Linear mode**: read issues from pasted text, emit issues you write/edit as **one copyable markdown block** (see REFERENCE → Linear-down fallback). The git/gh pipeline is unaffected.
3. **Resolve runtime IDs once** and reuse: my user id (`get_user` query=`me`), team id, the `ai` label id, the active cycle id, and the workflow status ids (Backlog/Todo/In Progress/In Review/Done). See REFERENCE → Linear runtime resolution.
4. **Detect where to resume.** `/handle-it` can be dropped on an issue at **any** stage — don't assume Phase 1. Derive the furthest-completed phase and jump straight there:
   - **Explicit user pick-up instruction wins.** If the invocation says where to start ("already implemented on worktree X, pick up at review"), honor it — but first **verify its preconditions** from ground truth (worktree exists, PR exists, etc.); if one is missing, say so and fall back to detection.
   - **Else derive from ground truth** (authoritative — the Linear status block is only a hint, and can be stale): worktree present (`bun run worktree:ls`)? PR for the branch (`gh pr view`)? draft or ready? is there a `## 🐊 Claudecodile Rating:` comment and what's the score? CI state, `mergeable`, `reviewDecision`, `state`? Map these to the entry phase (full table in REFERENCE → Resume detection).
   - **Reconcile + announce.** If ground truth and the status block disagree, trust ground truth, rewrite the block, and tell the user: *"Resuming BE-#### at Phase N (…) — found <evidence>."*

   Skip this only when there's clearly nothing to resume (no worktree, no PR, issue still `Backlog`/`Todo`) → start at Phase 1.

## Phase 1 — Route to a starting point

Parse the invocation argument and pick ONE entry point. Context-complete means: **a new person or agent could pick this up from the title + description alone (or the docs it points to) with zero further questions.**

| Argument | Condition | Entry point | Action |
|---|---|---|---|
| Issue id(s) given | Context-complete | **EP4** | Skip planning → Phase 2 |
| Issue id(s) given | Lacks context | **EP1** | `/grill-with-docs` → rewrite the issue's title + description in `/to-issues` template form (don't create new issues) |
| No issue | One coherent feature | **EP2** | `/grill-with-docs` → create the Linear issue(s) with the defaults below |
| No issue | A large/multi-feature project | **EP3** | `/grill-with-docs` → `/to-prd` → `/to-issues` (atomic, dependency-ordered) with the defaults below |

If "one feature vs project" is unclear with no issue given: anything that would yield **3+ issues** is EP3.

**Issue-creation defaults (EP2/EP3, and any `/to-issues` slice):** assignee = me; add the `ai` label (keep the planning skill's `ready-for-agent`/category labels); set the real Linear `blockedBy`/`blocks` **relations** (not just body text); attach to the **active cycle**. Leave other labels for the user. See REFERENCE → Creating issues.

After Phase 1 you hold one or more **context-complete** target issues. Order by dependency (blockers first) and run Phases 2–13 on each leaf. Most invocations are a single issue. **On any (re-)entry** (e.g. after a `ScheduleWakeup`), skip issues already `In Review`/`Done` and resume the unfinished ones — Linear status is your source of truth, so you never double-claim or re-PR.

## Phase 2 — Blocking check (per issue)

`get_issue` (with `includeRelations: true`) → read `relations.blockedBy`. A blocker is cleared only at status **`Done`** (merged). `In Review` is NOT Done.

- **Blocked:** the issue is already context-complete, so **wait to implement**. Table row → `⏳ waiting on BE-####`, then `ScheduleWakeup` (~20–30 min) to re-check; still open → sleep again; `Done` → proceed. Do NOT claim until unblocked. (User may also wrap the whole thing in `/loop`.) **Override:** if the user explicitly says to *stack* on the blocker instead of waiting, don't wait — follow REFERENCE → Stacked PRs (branch off the blocker, PR `--base <blocker-branch>`, retarget on its merge).
- **Unblocked / no blockers:** → Phase 3.

## Phase 3 — Claim + worktree (per issue)

1. **Claim:** `save_issue` status = `In Progress`, assignee = me.
2. **Worktree** (orchestrator owns the path; all subagents `cd` into THIS one — never a second worktree for the same branch):
   - **CaivanOS:** `bun run worktree:new <domain>/<be-id>/<short-kebab>`. **Add `--db-branch` ONLY for a DB migration / schema change** (matches `lead-worktree-team`); for non-migration issues, omit it. Branch naming per AGENTS.md. Capture the absolute path.
   - **Workbench:** set up a worktree and copy `.env` from the primary checkout. **Condition the DB ask on change type:** for a DB / schema / migration-bearing issue, **ask the user for the DB connection string and WAIT** (this ask overrides autonomy); for a non-DB change (copy, styling, client-only logic) the copied `.env` is enough — just **quick-confirm** "reusing main's `.env` — ok?" and proceed without a hard block.

## Phase 4 — Implement (subagent)

**Classify the brief, then spawn the matching pre-built agent** — `Agent(subagent_type: "swatkinson-toolkit:<agent>")` with the brief + the absolute worktree path:
- **Feature / enhancement, or a clear bug** (cause given in the brief) → **`swatkinson-toolkit:handle-it-shipper`** (Sonnet; runs `agentsystem-core:ship`).
- **Unclear bug** (symptom / error log / perf regression, no root cause) → **`swatkinson-toolkit:handle-it-investigator`** (Opus; runs `diagnose`). If it reports the fix is feature-sized, re-route to the shipper.

The agent verifies (`bun run check` + full `bun run test`) and **reports back — it does NOT commit or push.** Once it returns, the **orchestrator** commits (`Refs: BE-####`) + pushes from the foreground (subagents hang on `git push` and ignore "don't push" — findings #12/#13; see REFERENCE → Git ownership). Agent defs ship with this plugin (`agents/handle-it-shipper.md`, `handle-it-investigator.md`). All agents inherit the [hard rules](#hard-rules).

## Phase 5 — Open DRAFT PR (orchestrator)

**`cd` into the worktree first** (the branch is checked out there; from the primary checkout you're on `main`). Run `agentsystem-core:open-pr` at **`mode=balanced`** and **as a draft** (`--draft`): Phase 4 already verified `check`+`test`, so balanced is right; `production` would block on pre-existing unrelated failures. It writes the title + Summary/Test-plan body (reference the bare `BE-####`) and shows its confirm gate — let it fire. (Default `--base main`; on a **stacked** run use `--base <blocker-branch>` — REFERENCE → Stacked PRs.) `save_comment` the PR URL on the Linear issue; keep status `In Progress`. **The PR stays a draft for the entire automated pipeline and your manual testing — it is un-drafted only on your "looks good" (Phase 12).** Capture the PR number.

## Phase 6 — Review ⇄ fix loop (until 5/5)

**Delegate the whole loop to `Skill(swatkinson-toolkit:claudecodile-review)`** — pass it the **worktree path** + **PR number** (and, on a resume, the existing **RATING_COMMENT_ID** + score history if you have them). That skill owns the iterate-until-🐊-5/5 review⇄fix loop: Opus `swatkinson-toolkit:claudecodile-reviewer` posts P#-tagged inline comments with suggested fixes + maintains the one `## 🐊 Claudecodile Rating: N/5` comment, Sonnet `swatkinson-toolkit:claudecodile-fixer` applies them, and it loops (round 1 full diff → incremental → **final full pass**) until `5/5 = no P0/P1 AND every in-scope P2/P3 fixed` (only scope-bloating nits may remain, recorded as follow-ups). The PR stays a **draft** throughout.

**Why a skill, not inline:** it runs in *your* context (the Skill tool loads it into this conversation, not a fresh agent), so **you still own every commit + push** between rounds exactly as before — functionally identical to when this lived inline, just deduplicated so `/claudecodile-review` is reusable standalone. As the loop reports each round, mirror its latest rating into the **Review** status cell (`⏳ 3/5` → `✅ 5/5`).

Handle the skill's **return outcome**:
- **`5/5`** → proceed to Phase 7. Any returned P2/P3 are the **scope-deferred** ones (in-scope nits were fixed in-loop) — file each important one as a Linear follow-up comment, leave the rest as a note.
- **`plateau-bail`** (no score improvement across 2 rounds) → surface via `AskUserQuestion`: *"stuck at N/5 on <items> — accept as-is / guide me / keep iterating."*
- **`handback-bail`** (a comment needs a product decision or a hard-rule file) → [bail](#bail-dont-grind) and surface.

Skill: `swatkinson-toolkit:claudecodile-review` (bundled in this plugin). Agents it uses: `swatkinson-toolkit:claudecodile-reviewer`, `swatkinson-toolkit:claudecodile-fixer`.

## Phase 7 — No merge conflicts (gate)

A `CONFLICTING` PR has **no merge-ref, so GitHub runs zero `pull_request` workflows** — no CI, no preview (canary finding #21; this was the real cause of every "CI/Vercel didn't run" mystery). So resolve conflicts **before** CI/preview. `gh pr view <N> --json mergeable,mergeStateStatus`; if `CONFLICTING` (main moved):
- **Code / non-migration conflicts** → `agentsystem-core:resolve-conflict` (in the worktree), then re-push.
- **Migration-index conflicts** (diff confined to `migrations/` + `_journal.json`/snapshot) → `bun run db:rebase` (#633) if present, else the `resolve-migration-conflict` skill. Fails closed on hand-authored SQL → bail + surface. Run the printed `git push --force-with-lease` (the one sanctioned force-push).

See REFERENCE → Merge conflicts. The clean-branch push from resolving is also what triggers Phase 8's CI + preview.

## Phase 8 — CI/CD green + preview (still a draft)

A conflict-free PR — **even a draft** — runs CI and deploys a Vercel preview on each push (`preview-deploy.yml` has no draft guard; drafts deploy fine — finding #15 corrected; un-draft is NOT a trigger). Poll `gh pr checks <N>`:
- **Code/test failures** → spawn **`swatkinson-toolkit:handle-it-shipper`** (or `agentsystem-core:fix-pr-tests` for failing CI tests specifically) in the worktree → fix → orchestrator commits + pushes → re-check.
- **Infra/workflow failures** (env, neon/electric) → can't fix in code → **surface to the user**, don't loop. **If CI shows 0 runs, re-check `mergeable` first** — a `CONFLICTING` PR (Phase 7) is the cause, not an outage.
- **Preview link:** the native **Vercel** check often shows *"Ignored Build Step" / "Canceled"* on these repos — that is NOT a failure and its comment has no usable URL. The real preview is published by the **`deploy-vercel` GitHub Action**, posted/edited in its **`github-actions` PR comment** on a **custom domain** (CaivanOS `…dev.caivanos.app`, workbench `workbench-git-<branch>.caivan.dev`) — **not** a `*.vercel.app` URL. Grab it from that comment (`gh pr view <N> --comments`), not the Vercel-bot comment. If `deploy-vercel` genuinely failed (red job), note it + fall back to local in the handoff. See REFERENCE → CI/CD green + preview.

## Phase 9 — Test-and-tick

Spawn **`swatkinson-toolkit:handle-it-test-runner`** (Haiku) in the worktree to run the **automatable** Test-plan items — `bun run check`, full `bun run test`, and any listed build/focused suite — and **report pass/fail per item**. The **orchestrator** then ticks those checkboxes on the PR (`gh pr edit`, editing **only the test-plan lines** — leave any bot-managed section, e.g. Macroscope, untouched), leaving the human-only / click-through items for the user. (The test-runner never edits the PR — the orchestrator owns every PR/git mutation.) Agent def ships with this plugin (`agents/handle-it-test-runner.md`).

## Phase 10 — Manual-review handoff (PR stays a DRAFT, then WAIT)

**First re-verify the branch is current** (`gh pr view <N> --json mergeable`): if main advanced and it's now `CONFLICTING`, rebase (Phase 7) and let CI/preview refresh — so the preview you hand over is built on current `main` (#3). Then, only when **🐊 5/5 + conflict-free + CI green with a working preview + the tester has ticked the bun-run items** — hand the user, **leaving the PR a draft**:
- The **Vercel preview link** → `✅ Preview ready: <branch> → <url>` (or, if the deploy genuinely failed, the failed-job URL + local fallback).
- The **remaining manual test items** (the click-through ones the tester couldn't auto-run).
- The **branch name** + a `cd` command for local testing.
- Tell them: **"#<N> is ready for your manual testing"** (still a draft — not yet for seniors).

Then **WAIT** for their verdict.

## Phase 11 — Manual-review interaction

When the user replies with questions/issues: answer directly. For each reported problem, treat it as a mini Phase 4 — classify and spawn **`swatkinson-toolkit:handle-it-shipper`** (clear fix/feature) or **`swatkinson-toolkit:handle-it-investigator`** (unclear bug) to fix it edit-only. **Ground the brief first:** read the reported surface(s) yourself and hand the agent **file:line pointers + a one-line reproduction / root-cause hypothesis** — don't pass the bare symptom (a symptom-only brief makes the agent re-derive what you already know, and can mis-target a runtime/sync bug as a missing render). Then → orchestrator commits + pushes → then, if the change is non-trivial, **re-run `Skill(swatkinson-toolkit:claudecodile-review)`** (Phase 6) to keep the rating honest at 5/5. Loop until they approve. The PR stays a draft.

## Phase 12 — Mark ready for review (on approval)

When the user says **"looks good"** (or similar):
1. **Resolve the inline review threads** (batch-resolve via GraphQL; keep the `## 🐊 Claudecodile Rating` comment — it's an issue comment, not a thread). See REFERENCE → Resolving review threads.
2. `gh pr ready <N>` — **un-draft** (now it's for seniors).
3. `save_issue` Linear → `In Review`; `save_comment` it's review-ready.
4. Tell the user: **"#<N> is ready — request review from your seniors."**

**Never** mark `Done` — a human merges. **Stop here** — do not initiate any polling or watch loop after un-drafting.

## Status table

Print every turn, updated in place. One row per issue. `✅` done · `⏳` in progress / waiting · `❌` blocked / bailed · `—` n/a. **Once the PR exists, append its number:** `BE-1234 (#123)`. The **Review** cell shows the live 🐊 rating (`⏳ 3/5` → `✅ 5/5`). The PR is a **draft** until the user approves (un-drafted on "looks good").

| Issue | Plan | Implement | Draft PR | Review | CI+Preview | Manual Test | Ready | Status |
|---|---|---|---|---|---|---|---|---|
| BE-1234 (#123) | ✅ | ✅ | ✅ | ⏳ 3/5 | — | — | — | review⇄fix round 2 |

How each column is filled: REFERENCE → Status columns.

**Mirror it into Linear.** On each status update, also write this table into a **delimited block at the top of the issue's description** — between `<!-- handle-it:status -->` and `<!-- /handle-it:status -->` markers — via `save_issue` (read the current description, replace only that block, **preserve the brief below it**). At-a-glance progress then lives in Linear, not just the chat. See REFERENCE → Linear status block.

## Hard rules

Inherited from `drain-queue` — non-negotiable:
- **Never** edit `src/server/auth.ts`, `src/lib/auth/permissions.ts`, env handling, or deploy config to satisfy any step → **bail**.
- **Never** push to `main`, merge your own PR, amend, or pass `--no-verify` / skip-flags. **Never force-push** — except the single `git push --force-with-lease` that `bun run db:rebase` prints after a migration-index rebase.
- **Never** mark a Linear issue `Done` — a human merges.
- **Always** work in a worktree; **always** run the repo's full verify gate green before commit — `bun run check` + `bun run test` where a test runner exists; **where the repo has no test runner (e.g. workbench → `pnpm check` only), run `check` alone — don't invent a `test` command.**
- **Stage only the paths your change touched — never `git add -A`.** Windows worktree checkouts carry pre-existing CRLF↔LF churn in tracked `.pi/`/`.claude/` files; `git add -A` sweeps it (often 1000+ lines) into the commit + PR. Confirm with `git diff --cached --stat` before committing. See REFERENCE → Git ownership.
- **Never** generate DB migrations without `bun run db:branch` on the worktree first.
- Verify every concrete file/path/symbol claim in a brief against the repo before relying on it; note discrepancies in the PR body.
- Stay strictly in the issue's scope — adjacent improvements become a Linear follow-up comment.

## Bail (don't grind)

Notify (`PushNotification`) + table row `❌` + post a Linear comment, then stop, when: the brief needs a product decision; a step requires a hard-rule file; `check`/`test` is still red after fixes (one fix attempt = read→edit→re-run; third red → bail); the review loop hits a comment it can't address without a product decision or hard-rule file; or an infra CI failure can't be cleared in code. A returned issue is recoverable; wrong autonomous code is not.
