---
name: handle-it
description: End-to-end orchestrator that takes a Linear issue (or a freeform feature/project) and drives it through planning → implementation → draft PR → an in-house review⇄fix loop (rated to 5/5) → conflict-free CI + preview → an auto-tester → your manual review (PR stays a draft) → ready-for-review on your approval, with a live status table and Linear blocking awareness. Stops after un-drafting — senior review and merge are fully manual. Use when the user invokes /handle-it, or asks to take an issue/feature all the way to a review-ready PR.
---

# handle-it

You are the **orchestrator** (run as Opus, in the main conversation). You route the request to the right planning entrypoint, then drive each target issue through the full lifecycle — implement (Sonnet) → draft PR → review⇄fix loop (🐊 to 5/5) → resolve conflicts → CI + preview → test-and-tick → manual-review handoff (**PR stays a draft**) → mark ready on your approval — keeping a live status table and honoring the tracker's blocking relations. **Stops after un-drafting** — senior review and merge are fully manual.

**Project specifics live in config, not here.** This skill is a project-generic **engine**: every concrete command, tracker detail, path, preview-URL location, and hard-rule file comes from **`.claude/handle-it/config.md`** in the target repo, and every authored-text format (PR title/description, commit message, manual-review handoff) comes from **`.claude/handle-it/rules/*.md`** — both written by `/handle-it-project-setup`. Wherever a phase below says "the verify gate", "the tracker", "the worktree command", "the preview", "the hard-rule files", it means *the value in `config.md`*; wherever it names a `rules/*.md` file, read that file's `Template` + `Rules` and follow them. **Read the config in Phase 0 and treat the `.claude/handle-it/` directory as the single source of project truth.** When a config value or a rule proves wrong at runtime, fix it (see [Keeping the config accurate](#keeping-the-config-accurate)).

**Autonomy contract:** Run autonomously from implementation through the review loop, conflict resolution, CI/preview, and the auto-tester — don't checkpoint between those. When waiting on external state (a blocker to merge), **loop and wait yourself** (`ScheduleWakeup`). The human gates are exactly: (a) `/grill-with-docs` during planning, (b) handle-it's own PR-create confirm gate (Phase 5 shows you the drafted title + body before `gh pr create`), (c) a **setup-secret ask** when the config flags one as needed for a migration/DB change (e.g. a DB connection string, or confirming a copied `.env`) — only for that change type; a non-migration change just quick-confirms and proceeds, (d) the **manual-review gate** — the PR stays a **draft** through review/CI/preview/test-and-tick; you hand it off for manual testing and WAIT; on the user's "looks good" you un-draft (mark ready for review) and tell them to request senior review — **then stop**, (e) a **bail** when you genuinely cannot proceed (`PushNotification`, update the table, stop).

Lifecycle mechanics, subagent prompt templates, tracker runtime resolution, and trackerless mode live in **[REFERENCE.md](REFERENCE.md)** — load it before Phase 4. Invoke skills by their **exact** names — plugin skills need their `plugin:` prefix or `Skill(...)` errors `Unknown skill` (see REFERENCE → Skill invocation names). **This toolkit is itself a plugin (`swatkinson-toolkit`):** spawn its bundled agents with `subagent_type: "swatkinson-toolkit:<agent>"` and invoke its sibling skills as `Skill(swatkinson-toolkit:<skill>)` — bare names won't resolve. The engine skills the config routes to keep their own prefixes (default `agentsystem-core:ship`, etc.; `code-review`/`diagnose` are bare).

## Phase 0 — Preflight & resume detection

1. **Load the config.** Read `.claude/handle-it/config.md` (note its **Rules files** manifest — you'll read individual `rules/*.md` as each phase calls for them). **If it's missing**, tell the user this project isn't set up yet and offer to run **`Skill(swatkinson-toolkit:handle-it-project-setup)`** to generate it — then stop until it exists. Everything below reads from this directory.
2. **Confirm the tracker.** Per config → Issue tracker. If `type: none` → run in **trackerless/freeform mode** (REFERENCE → Trackerless mode); the git/PR pipeline is unaffected. If a tracker is configured but its tools are absent this session (e.g. `linear` but no Linear MCP) → tell the user and fall back to **manual mode** for that tracker: read issues from pasted text, emit issues you write/edit as **one copyable block** (REFERENCE → Trackerless mode).
3. **Resolve runtime IDs once** and reuse, per the config's tracker profile: my user id, the team/project/repo handle, any label(s) to apply, the active cycle/sprint, and the status mapping (the states that mean Todo/In Progress/In Review/Done). See REFERENCE → Tracker runtime resolution.
4. **Detect where to resume.** `/handle-it` can be dropped on an issue at **any** stage — don't assume Phase 1. Derive the furthest-completed phase and jump straight there:
   - **Explicit user pick-up instruction wins.** If the invocation says where to start ("already implemented on worktree X, pick up at review"), honor it — but first **verify its preconditions** from ground truth (worktree exists, PR exists, etc.); if one is missing, say so and fall back to detection.
   - **Else derive from ground truth** (authoritative — the tracker's status block is only a hint, and can be stale): worktree present (config → Commands → worktree list)? PR for the branch (`gh pr view`)? draft or ready? is there a `## 🐊 Claudecodile Rating:` comment and what's the score? CI state, `mergeable`, `reviewDecision`, `state`? Map these to the entry phase (full table in REFERENCE → Resume detection).
   - **Reconcile + announce.** If ground truth and the status block disagree, trust ground truth, rewrite the block, and tell the user: *"Resuming <issue-id> at Phase N (…) — found <evidence>."*

   Skip this only when there's clearly nothing to resume (no worktree, no PR, issue still in a not-started state) → start at Phase 1.

## Phase 1 — Route to a starting point

Parse the invocation argument and pick ONE entry point. Context-complete means: **a new person or agent could pick this up from the title + description alone (or the docs it points to) with zero further questions.**

| Argument | Condition | Entry point | Action |
|---|---|---|---|
| Issue id(s) given | Context-complete | **EP4** | Skip planning → Phase 2 |
| Issue id(s) given | Lacks context | **EP1** | `/grill-with-docs` → rewrite the issue's title + description in `/to-issues` template form (don't create new issues) |
| No issue | One coherent feature | **EP2** | `/grill-with-docs` → create the Linear issue(s) with the defaults below |
| No issue | A large/multi-feature project | **EP3** | `/grill-with-docs` → `/to-prd` → `/to-issues` (atomic, dependency-ordered) with the defaults below |

If "one feature vs project" is unclear with no issue given: anything that would yield **3+ issues** is EP3.

**Issue-creation defaults (EP2/EP3, and any `/to-issues` slice):** apply the config's tracker defaults — assignee = me; add the configured label(s) (keep the planning skill's `ready-for-agent`/category labels); set the real `blockedBy`/`blocks` **relations** the tracker supports (not just body text); attach to the **active cycle/sprint**. Leave other labels for the user. See REFERENCE → Creating issues.

After Phase 1 you hold one or more **context-complete** target issues. Order by dependency (blockers first) and run Phases 2–13 on each leaf. Most invocations are a single issue. **On any (re-)entry** (e.g. after a `ScheduleWakeup`), skip issues already `In Review`/done and resume the unfinished ones — tracker status is your source of truth, so you never double-claim or re-PR.

## Phase 2 — Blocking check (per issue)

Read the issue's blocking relations (per config → tracker; Linear needs `get_issue includeRelations: true`). A blocker is cleared only when it's **merged/done**. `In Review` is NOT done.

- **Blocked:** the issue is already context-complete, so **wait to implement**. Table row → `⏳ waiting on <blocker-id>`, then `ScheduleWakeup` (~20–30 min) to re-check; still open → sleep again; done → proceed. Do NOT claim until unblocked. (User may also wrap the whole thing in `/loop`.) **Override:** if the user explicitly says to *stack* on the blocker instead of waiting, don't wait — follow REFERENCE → Stacked PRs (branch off the blocker, PR `--base <blocker-branch>`, retarget on its merge).
- **Unblocked / no blockers:** → Phase 3.

## Phase 3 — Claim + worktree (per issue)

1. **Claim:** set the issue to **In Progress** and assign it to me (per config → tracker). In trackerless mode, skip — track state in the chat table only.
2. **Worktree** (orchestrator owns the path; all subagents `cd` into THIS one — never a second worktree for the same branch). Use the config's **worktree-create** command and **branch naming**; capture the absolute path.
   - **Migration/DB changes:** if the config defines a DB-branch flag or a setup-secret (connection string / `.env` copy) needed for migrations, apply it **only for a migration-bearing change** (per config → Commands → migration signal). For that change type, if the config flags a secret ask, **ask the user and WAIT** (overrides autonomy). For a non-migration change, omit the DB-branch flag and just **quick-confirm** any copied config, then proceed.

## Phase 4 — Implement (subagent)

**Classify the brief, then spawn the matching pre-built agent** — `Agent(subagent_type: "swatkinson-toolkit:<agent>")` with the brief, the absolute worktree path, **and the config-resolved values the agent needs** (verify gate, hard-rule files, migration command/signal — see REFERENCE → Implement subagent):
- **Feature / enhancement, or a clear bug** (cause given in the brief) → **`swatkinson-toolkit:handle-it-shipper`** (Sonnet; runs the config's implement skill, default `agentsystem-core:ship`).
- **Unclear bug** (symptom / error log / perf regression, no root cause) → **`swatkinson-toolkit:handle-it-investigator`** (Opus; runs the config's investigate skill, default `diagnose`). If it reports the fix is feature-sized, re-route to the shipper.

The agent runs the **config's verify gate** and **reports back — it does NOT commit or push.** Once it returns, the **orchestrator** commits (composing the message per **`rules/commit-message.md`**) + pushes from the foreground (subagents hang on `git push` and ignore "don't push" — findings #12/#13; see REFERENCE → Git ownership). Agent defs ship with this plugin (`agents/handle-it-shipper.md`, `handle-it-investigator.md`). All agents inherit the [hard rules](#hard-rules).

## Phase 5 — Open DRAFT PR (orchestrator)

handle-it **opens the PR itself** — no external open-PR skill. **`cd` into the worktree first** (the branch is checked out there; from the primary checkout you're on the base branch), then:

1. **Build the title** per **`rules/pr-title.md`** and the **body** per **`rules/pr-description.md`** (Summary + Test-plan checkboxes). Ensure the **bare issue id** appears in the Summary so the tracker auto-links (skip in trackerless mode). Derive the Test-plan items from the change + the issue's acceptance criteria, automatable items first.
2. **Confirm gate (gate b):** show the user the drafted title + body and wait for a quick confirm/edit before creating. This is handle-it's own gate — it replaces the old open-PR skill's confirm.
3. **Create the draft:** `gh pr create --draft --title <title> --body <body> --base <base>` from the worktree (pass the body via `--body-file` or a HEREDOC-literal `--body "$(cat <<'EOF' … EOF )"` — never `--body "@path"`). Default `--base` = the repo's base branch; on a **stacked** run use `--base <blocker-branch>` (REFERENCE → Stacked PRs). Phase 4 already ran the verify gate, so don't re-verify here.
4. **Capture the PR number**, comment the PR URL on the issue (per config → tracker), and keep status **In Progress**.

**The PR stays a draft for the entire automated pipeline and your manual testing — it is un-drafted only on your "looks good" (Phase 12).**

## Phase 6 — Review ⇄ fix loop (until 5/5)

**Delegate the whole loop to `Skill(swatkinson-toolkit:claudecodile-review)`** — pass it the **worktree path** + **PR number** (and, on a resume, the existing **RATING_COMMENT_ID** + score history if you have them). That skill owns the iterate-until-🐊-5/5 review⇄fix loop: Opus `swatkinson-toolkit:claudecodile-reviewer` posts P#-tagged inline comments with suggested fixes + maintains the one `## 🐊 Claudecodile Rating: N/5` comment, Sonnet `swatkinson-toolkit:claudecodile-fixer` applies them, and it loops (round 1 full diff → incremental → **final full pass**) until `5/5 = no P0/P1 AND every in-scope P2/P3 fixed` (only scope-bloating nits may remain, recorded as follow-ups). The PR stays a **draft** throughout.

**Why a skill, not inline:** it runs in *your* context (the Skill tool loads it into this conversation, not a fresh agent), so **you still own every commit + push** between rounds exactly as before — functionally identical to when this lived inline, just deduplicated so `/claudecodile-review` is reusable standalone. As the loop reports each round, mirror its latest rating into the **Review** status cell (`⏳ 3/5` → `✅ 5/5`).

Handle the skill's **return outcome**:
- **`5/5`** → proceed to Phase 7. Any returned P2/P3 are the **scope-deferred** ones (in-scope nits were fixed in-loop) — file each important one as a tracker follow-up comment (per config → tracker), leave the rest as a note.
- **`plateau-bail`** (no score improvement across 2 rounds) → surface via `AskUserQuestion`: *"stuck at N/5 on <items> — accept as-is / guide me / keep iterating."*
- **`handback-bail`** (a comment needs a product decision or a hard-rule file) → [bail](#bail-dont-grind) and surface.

Skill: `swatkinson-toolkit:claudecodile-review` (bundled in this plugin). Agents it uses: `swatkinson-toolkit:claudecodile-reviewer`, `swatkinson-toolkit:claudecodile-fixer`.

## Phase 7 — No merge conflicts (gate)

A `CONFLICTING` PR has **no merge-ref, so GitHub runs zero `pull_request` workflows** — no CI, no preview (canary finding #21; this was the real cause of every "CI/preview didn't run" mystery). So resolve conflicts **before** CI/preview. `gh pr view <N> --json mergeable,mergeStateStatus`; if `CONFLICTING` (base branch moved):
- **Code / non-migration conflicts** → the config's resolve-conflict skill (default `agentsystem-core:resolve-conflict`) in the worktree, then re-push.
- **Migration-index conflicts** (diff confined to the config's migration paths) → the config's migration-rebase command if it defines one (fails closed on hand-authored SQL → bail + surface; run the printed `git push --force-with-lease`, the one sanctioned force-push). If the config has no migration tooling, treat as code conflicts.

See REFERENCE → Merge conflicts. The clean-branch push from resolving is also what triggers Phase 8's CI + preview.

## Phase 8 — CI/CD green + preview (still a draft)

If the config has **no CI and no preview**, skip this phase (note it in the table) and go to Phase 9. Otherwise a conflict-free PR — **even a draft** — runs CI and deploys a preview on each push (drafts deploy fine where the config says so; un-draft is NOT a trigger). Poll `gh pr checks <N>`:
- **Code/test failures** → spawn **`swatkinson-toolkit:handle-it-shipper`** (or the config's fix-CI-tests skill, default `agentsystem-core:fix-pr-tests`, for failing CI tests specifically) in the worktree → fix → orchestrator commits + pushes → re-check.
- **Infra/workflow failures** (env, deploy config) → can't fix in code → **surface to the user**, don't loop. **If CI shows 0 runs, re-check `mergeable` first** — a `CONFLICTING` PR (Phase 7) is the cause, not an outage.
- **Preview link:** read it from **where the config says it lives** (config → CI/preview). On some repos the native provider check shows *"Ignored Build Step" / "Canceled"* and has **no usable URL** — that is NOT a failure; the real preview is posted elsewhere (e.g. a `github-actions` PR comment on a custom domain). Grab it from the configured location (`gh pr view <N> --comments`), not the provider-bot comment. If the deploy genuinely failed (red job), note it + fall back to local in the handoff. See REFERENCE → CI/CD green + preview.

## Phase 9 — Test-and-tick

Spawn **`swatkinson-toolkit:handle-it-test-runner`** (Haiku) in the worktree to run the **automatable** Test-plan items — the config's verify gate plus any listed build/focused suite — and **report pass/fail per item** (pass it the verify gate from the config). The **orchestrator** then ticks those checkboxes on the PR (`gh pr edit`, editing **only the test-plan lines** — leave any bot-managed section untouched), leaving the human-only / click-through items for the user. (The test-runner never edits the PR — the orchestrator owns every PR/git mutation.) Agent def ships with this plugin (`agents/handle-it-test-runner.md`).

## Phase 10 — Manual-review handoff (PR stays a DRAFT, then WAIT)

**First re-verify the branch is current** (`gh pr view <N> --json mergeable`): if the base branch advanced and it's now `CONFLICTING`, rebase (Phase 7) and let CI/preview refresh — so the preview you hand over is built on the current base (#3). Then, only when **🐊 5/5 + conflict-free + (CI green with a working preview, where the config has them) + the tester has ticked the verify-gate items** — emit the handoff message per **`rules/handoff-message.md`**, **leaving the PR a draft**.

Fill that template's slots: the **preview** URL (from config → CI/preview; the no-preview/deploy-failed fallback per the rule file), the **local** run line (config → Commands → dev/run), and **Manual criteria** = the PR description's still-unticked `- [ ]` test-plan items (the click-through / visual ones the tester couldn't auto-run). Then **WAIT** for their verdict.

## Phase 11 — Manual-review interaction

When the user replies with questions/issues: answer directly. For each reported problem, treat it as a mini Phase 4 — classify and spawn **`swatkinson-toolkit:handle-it-shipper`** (clear fix/feature) or **`swatkinson-toolkit:handle-it-investigator`** (unclear bug) to fix it edit-only. **Ground the brief first:** read the reported surface(s) yourself and hand the agent **file:line pointers + a one-line reproduction / root-cause hypothesis** — don't pass the bare symptom (a symptom-only brief makes the agent re-derive what you already know, and can mis-target a runtime/sync bug as a missing render). Then → orchestrator commits + pushes → then, if the change is non-trivial, **re-run `Skill(swatkinson-toolkit:claudecodile-review)`** (Phase 6) to keep the rating honest at 5/5.

**After each fix, before handing back:**
1. **If the fix introduces new manually-testable behavior**, append those items to the PR description's unchecked test-plan list: `gh pr view <N> --json body` → add `- [ ] <new item>` lines under the existing manual items → `gh pr edit <N> --body`.
2. **Re-emit the Phase 10 handoff template** (re-read the current unticked `- [ ]` items from the PR description so the list is always up-to-date, including any newly added items).

Loop until they approve. The PR stays a draft.

## Phase 12 — Mark ready for review (on approval)

When the user says **"looks good"** (or similar):
1. **Tick off all remaining unchecked manual items in the PR description.** The user's "looks good" is their confirmation that manual testing passed — read `gh pr view <N> --json body`, flip every remaining `- [ ]` to `- [x]` in the test-plan section, then `gh pr edit <N> --body`.
2. **Resolve the inline review threads** (batch-resolve via GraphQL; keep the `## 🐊 Claudecodile Rating` comment — it's an issue comment, not a thread). See REFERENCE → Resolving review threads.
3. `gh pr ready <N>` — **un-draft** (now it's for seniors).
4. Move the issue → **In Review** and comment that it's review-ready (per config → tracker; skip in trackerless mode).
5. Tell the user: **"#<N> is ready — request review from your seniors."**

**Never** mark the issue **done** — a human merges. **Stop here** — do not initiate any polling or watch loop after un-drafting.

## Status table

Print every turn, updated in place. One row per issue. `✅` done · `⏳` in progress / waiting · `❌` blocked / bailed · `—` n/a. **Once the PR exists, append its number:** `<issue-id> (#123)`. The **Review** cell shows the live 🐊 rating (`⏳ 3/5` → `✅ 5/5`). The PR is a **draft** until the user approves (un-drafted on "looks good").

| Issue | Plan | Implement | Draft PR | Review | CI+Preview | Manual Test | Ready | Status |
|---|---|---|---|---|---|---|---|---|
| ISSUE-1234 (#123) | ✅ | ✅ | ✅ | ⏳ 3/5 | — | — | — | review⇄fix round 2 |

How each column is filled: REFERENCE → Status columns.

**Mirror it into the tracker** (where the tracker supports issue descriptions, e.g. Linear). On each status update, also write this table into a **delimited block at the top of the issue's description** — between `<!-- handle-it:status -->` and `<!-- /handle-it:status -->` markers — reading the current description and replacing only that block (**preserve the brief below it**). At-a-glance progress then lives in the tracker, not just the chat. In trackerless/manual mode, keep the chat table only. See REFERENCE → Tracker status block.

## Hard rules

Non-negotiable:
- **Never** edit a **hard-rule file** (config → Hard-rule files — auth, permissions, env/secret handling, deploy/CI config) to satisfy any step → **bail**.
- **Never** push to the base branch, merge your own PR, amend, or pass `--no-verify` / skip-flags. **Never force-push** — except the single `git push --force-with-lease` that the config's migration-rebase command prints after a migration-index rebase.
- **Never** mark an issue **done** — a human merges.
- **Always** work in a worktree; **always** run the **config's verify gate** green before commit. Run exactly what the config defines — where it says there's no test runner, run the lint/build step alone; **never invent a `test` command** the project doesn't have.
- **Stage only the paths your change touched — never `git add -A`.** Confirm with `git diff --cached --stat` before committing. Heed the config's staging-discipline note (e.g. Windows worktree checkouts carry CRLF↔LF churn `git add -A` would sweep in). See REFERENCE → Git ownership.
- **Never** generate DB migrations without the config's migration-start command on the worktree first (where the config defines migration tooling).
- Verify every concrete file/path/symbol claim in a brief against the repo before relying on it; note discrepancies in the PR body.
- Stay strictly in the issue's scope — adjacent improvements become a tracker follow-up comment.

## Keeping the config accurate

The `.claude/handle-it/` directory is the engine's only project knowledge — keep it true. When a config value proves **wrong at runtime** (a verify/worktree/migration command errors because it was renamed, the preview URL isn't where the config said, a hard-rule path moved), after you recover: `Edit` the offending field in `config.md` to the correct value (re-derive from its `Source:` pointer where one exists) and append a dated line to **Learned corrections**. When a **rule** proves wrong (e.g. the PR template is missing a section the repo's CI requires, the tracker mangled the handoff, a commit trailer was rejected), `Edit` the relevant `rules/*.md` so the next run gets it right. This is how the engine gets more accurate on a project over time — don't just work around a stale value silently.

## Bail (don't grind)

Notify (`PushNotification`) + table row `❌` + post a tracker comment, then stop, when: the brief needs a product decision; a step requires a hard-rule file; the verify gate is still red after fixes (one fix attempt = read→edit→re-run; third red → bail); the review loop hits a comment it can't address without a product decision or hard-rule file; or an infra CI failure can't be cleared in code. A returned issue is recoverable; wrong autonomous code is not.
