---
name: batch-handle-it
description: Fan a batch of Linear issues out into one t3 Code thread each, every thread running /handle-it on its own issue in the right repo — so the work executes on this box but shows up in the t3 sidebar and on the phone. Reads Linear's blocking relations to order the batch: unblocked issues launch now, blocked ones are held by a background poller that launches each as a stacked PR the moment its blocker reaches manual-review. With no arguments it picks up your AI-ready queue (current cycle · assigned to you · Todo · label `ai` · not `needs-info`); with issue ids it takes exactly those. Use when the user asks to "batch handle-it", "handle my cycle", "run all my ai issues", "kick off my queue", "spawn a session per issue", "/batch-handle-it", or gives a list of issue ids to start in parallel. Pass `-ask` to review the plan before anything launches, `-no-stack` to fall back to launching everything at once. Not for a single issue — call /handle-it directly for that.
argument-hint: "[KEY-#### KEY-#### ...] [-ask] [-no-stack]"
allowed-tools: Bash, Read, mcp__claude_ai_Linear__list_issues, mcp__claude_ai_Linear__get_issue, mcp__claude_ai_Linear__list_cycles, mcp__claude_ai_Linear__list_teams, mcp__claude_ai_Linear__list_issue_labels, mcp__claude_ai_Linear__create_issue_label, mcp__claude_ai_Linear__save_issue
---

# batch-handle-it

Turn a queue of Linear issues into a fleet of running `/handle-it` threads — one per issue, each drivable from the t3 web UI or the phone.

**Requires a running [t3 Code](https://github.com/pingdotgg/t3code) server** on this box — that's the transport. Without one, there is nothing to dispatch to.

**You resolve and route; the script dispatches.** Your job is to produce a clean list of `{id, repo}` targets and hand it to `scripts/dispatch_sessions.py` (under `${CLAUDE_PLUGIN_ROOT}/skills/batch-handle-it/`). The script owns the t3 server connection, auth, thread ids, and prompt submission. Don't hand-roll `curl` calls against the orchestration API.

**Never pre-create a worktree.** `/handle-it` creates and owns its own worktree (Phase 3) — one per issue, isolated. Each thread opens at the **project root** with `branch`/`worktreePath` null and lets it do that. t3 can prepare a worktree itself, but only over its WebSocket path, and using it would collide with the branch `/handle-it` makes.

## Step 1 — Parse the invocation

| Argument | Meaning |
|---|---|
| *(nothing)* | Auto-query mode — build the queue from Linear (Step 2) |
| `KEY-2400 KEY-2465` (or `2400, 2465`) | Explicit mode — take exactly these, in this order. Bare numbers get the team-key prefix (resolve it per Step 2). |
| `-ask` | Present the plan and **wait for confirmation** before launching. Combinable with either mode. |
| `-no-stack` | Ignore blocking relations entirely — launch every issue immediately, as if stacking didn't exist. Each blocked session then parks in `/handle-it`'s Phase 2 wait. Escape hatch for when the DAG is wrong or stacking is misbehaving. |

Without `-ask`, launch as soon as the plan is resolved — no confirm gate. Always **print** the plan either way.

Explicit ids are a deliberate override: **skip the `ai` / `needs-info` / cycle / status filters** for them. If the user named it, they want it. Do still resolve its repo (Step 3) and still skip it if a session is already running.

## Step 2 — Build the queue (auto-query mode only)

**Resolve the team first.** The team key comes from the repos' `.claude/handle-it/config.md` files (Issue tracker → `### If linear` → Team / Issue id format), or from the ids the user passed. If the configured repos span several teams and the user didn't scope the request, ask which team's queue to run.

Three non-obvious traps here; all three are verified, not theoretical.

1. **Resolve the current cycle to an ID first.** `list_cycles(teamId, type: "current")` → take `.id`. Passing `cycle: "current"` to `list_issues` returns **zero results silently** — it looks like an empty queue rather than an error.
2. **Pass `includeArchived: false`.** It defaults to *true*, so archived issues leak into the batch.
3. **Filter `needs-info` client-side.** Linear has no negative-label filter, so the API can't do this. Drop any issue whose `labels` contain `needs-info` after the call returns.

```
list_issues(team: "<KEY>", assignee: "me", state: "Todo",
            cycle: "<resolved cycle id>", label: "ai",
            includeArchived: false, limit: 100)
```

Then drop `needs-info`. What remains is the queue. If it's empty, say so plainly — report the cycle number you queried and how many were dropped for `needs-info`, so an empty result is legibly empty rather than ambiguous.

In explicit mode, `get_issue` each id instead (you need its labels and project to route it).

**Either way you must `get_issue` every id with `includeRelations: true`** — `list_issues` returns neither relations nor full descriptions, and relations are what Step 2.5 orders the batch by. This is one call per issue; don't try to batch it.

## Step 2.5 — Build the dependency DAG

Blocking relations decide **what launches now and what stacks on what**. Nothing else does — not labels, not project, not issue number order.

1. **Collect edges.** For each queued issue, read `relations` for `blockedBy` / `blocks`. Note that a blocker may **not be in the queue** — it might be `In Progress` (so it failed the `state: "Todo"` filter) or in another cycle. `get_issue` those too: you need their id and status even though you won't launch them.
2. **Resolve each blocker to one of three dispositions:**

   | Blocker's state | The dependent issue… |
   |---|---|
   | Done / merged | is effectively unblocked — treat as a **root** |
   | Has any other state (Todo, In Progress, In Review) | **stacks** on it — `stack_on: "<blocker-id>"` |
   | Not in the batch **and** not started, and you aren't launching it | is **unlaunchable** — report it, don't queue it. Its blocker will never move during this run. |

3. **Layer topologically.** Roots (no unresolved blocker) are layer 0; each issue sits one layer above its deepest blocker. Order the plan bottom-up.
4. **Detect cycles.** A `blockedBy` loop (A ← B ← A) makes the batch unorderable. **Report the cycle and launch neither issue** — don't guess a winner and don't silently break the edge; a wrong guess burns two worktrees and two PRs.
5. **Flag depth > 3.** Stacks deeper than 3 get fragile — a 4th layer will wait for a merge rather than stack. Say so under the table rather than letting the user discover it hours later.

### Inferring missing relations — propose, never write unasked

Some issues genuinely depend on another but have no relation set. Infer a candidate edge only from **hard evidence in the issue text**: an explicit `Blocked by KEY-####` line, a "depends on / after KEY-#### / once KEY-#### lands" phrase, or a `## Blocked by` section (issue-breakdown templates often emit one). **Do not** infer from "these two issues sound related", shared project, or adjacent numbering — a wrong edge mis-orders the batch *and* leaves a false dependency in Linear that outlives this run.

Then, before writing anything: list each proposed edge with the sentence that justifies it, and **wait for confirmation**.

```
Proposed blocking relations (not yet written to Linear):
  KEY-2885 blockedBy KEY-2884 — "Blocked by KEY-2884 (needs the closing-tag column)"
  KEY-2890 blockedBy KEY-2884 — "once KEY-2884 lands, mirror the same filter here"
Write these 2 relations and use them to order the batch? (existing relations are used as-is)
```

On approval, write them with `save_issue` (set the real `blockedBy` relation — not body text) and fold them into the DAG. On refusal, treat those issues as roots. **This gate is unconditional — it applies even without `-ask`**, because it mutates your tracker rather than just launching a session. Existing relations never prompt.

### Write `stack/queued` on every issue that will stack

The `stack/` label group is how a stacked run is legible in Linear and how state survives a crashed session. `/handle-it` reads `stack/queued` to know it's running unattended (so it never stops to ask a question), and **replaces it with `stack/ready`** itself when that issue's PR reaches manual-review.

- `list_issue_labels team=<team-id>` → find the `stack/queued` label id; if the `stack/` group doesn't exist, `create_issue_label` it (group `stack`, children `queued` and `ready`).
- Apply `stack/queued` to every issue you're launching with a `stack_on`, via `save_issue`.
- **A failed label write is a note, not a bail.** The labels mirror state; the authority is Linear's relations plus the blocker's PR on GitHub. Say the write failed and launch anyway.

## Step 3 — Route each issue to a repo

`/handle-it` is project-generic, so a batch can span repos. Route each issue to the repo whose handle-it config claims it — never by vibes:

1. **Build the candidate set once:** the repos on this box that have a `.claude/handle-it/config.md` (e.g. `ls -d ~/src/*/.claude/handle-it 2>/dev/null`). Only these are launchable — the script refuses a repo without the config.
2. **Match by team key first:** each config's Issue tracker section declares the team / issue-id format (`KEY-####`). One candidate claims the issue's key → route there.
3. **Several repos share the team** → disambiguate with documented signals only, in this order: a repo-routing label the configs/user have established (a label group that names the repo or product area) → the issue's Linear **project** prefix → otherwise **unroutable**.

**A routing label wins over the project name** — project names routinely describe cross-repo migrations and point at the wrong codebase. Unroutable issues are **reported, never guessed**: list them with their labels/project and let the user say where they belong (or re-run with explicit ids after fixing the label). Once the user rules on one, note the rule in that repo's `config.md` → **Learned corrections** so the next batch routes it automatically. Routing one wrong burns a worktree and a PR in the wrong repo.

## Step 4 — Title and triage each issue

Two per-issue judgement calls. Both are yours to make — the script just passes them through.

**`title`** — the thread name shown in the t3 sidebar and on the phone. **Max 45 chars** (the script truncates past that). A few words, Title Case, enough to recognise the work at a glance. The user already knows their own issues, so don't restate the whole summary: *"Add closing tag to inspection types"* → **`Closing Tags`**. Don't include the `KEY-####` — the thread is already keyed on the issue id, and repeating it wastes the 45 chars on something the user can't act on. Omitting `title` falls back to the bare id, which is worse; always write one.

**`effort`** — reasoning budget, from the issue's description:

| Effort | When |
|---|---|
| `low` | Mechanical or well-precedented. A filter, a new tag mirroring an existing one, a collapsible section like one already shipped. |
| `high` | Genuinely complex, or needs **debugging** (a bug with no known cause, "replicate locally and report back") or **planning** (changes a data model, a submission flow, cross-system APIs). |
| `medium` | Everything else — the default. Multi-part but understood work. |

Bias toward `high` when the issue asks a question rather than states a change ("investigate", "look into", "why does…"), since those spend their budget on diagnosis. Bias toward `low` only when a near-identical pattern already exists in the repo to copy.

**Calibration** — real issues, user-approved. Match this altitude:

| Issue title | → | Title / effort | Why |
|---|---|---|---|
| Add closing tag to inspection types | | `Closing Tags` · low | Mirrors an existing tag — copy a pattern |
| Export changes (PDF name, priority, SMS format) | | `Issue Export Changes` · medium | Several parts, all understood |
| 'Add issue to already submitted inspection' not working | | `Fix: Add Issue To Submitted Inspection` · high | Unknown-cause bug; asks to replicate and report |
| Make issues progressively upload while filling out checklist | | `Progressive Issue Upload` · high | Changes when data persists — a wrong plan corrupts records |
| Second half of the external API | | `External API, Part 2` · high | Cross-system; migrates a team's workflow |

Note how much shorter the titles are than the issue summaries. That's the point — the user knows their own backlog, so the title only has to be recognisable, not descriptive.

**Present the plan** as exactly this table — always, whether or not `-ask` was passed:

| ID | Session | Effort | Project | Stacks On |
|---|---|---|---|---|
| 2884 | Closing Tags | Low | app.acme | — |
| 2885 | Closing Tag Filters | Med | app.acme | 2884 |
| 2799 | External API, Part 2 | High | workbench | — |

- **ID** — the number only. Trim the key prefix.
- **Session** — the title from above.
- **Effort** — `Low` / `Med` / `High` for display. The JSON still takes `low` / `medium` / `high`; passing `Med` to the script is rejected.
- **Project** — the repo resolved in Step 3.
- **Stacks On** — the blocker's number, or `—` for a root. Order rows so a blocker always appears above what stacks on it.

**No emojis or status markers in any cell.** Anything that needs flagging — a routing conflict, an issue already running, a memory concern — goes in prose under the table, not in the grid. Keep the table scannable.

Then list, below the table: anything dropped for `needs-info`, anything unroutable, anything already running, any **cycle** or **unlaunchable** issue from Step 2.5, and how many issues will be **held by the watcher** rather than launched now. With `-ask`, **stop here and wait**. Without it, launch immediately — but the Step-2.5 relation-write gate still applies.

## Step 5 — Launch

Pipe the targets in as JSON, with `stack_on` on anything that stacks, and pass **`--watch`**:

```bash
echo '[{"id":"KEY-101","repo":"/home/me/src/app.acme","title":"Closing Tags","effort":"low"},
       {"id":"KEY-102","repo":"/home/me/src/app.acme","title":"Closing Tag Filters","effort":"medium","stack_on":"KEY-101"}]' \
  | python3 ${CLAUDE_PLUGIN_ROOT}/skills/batch-handle-it/scripts/dispatch_sessions.py --watch
```

Each launch is two commands POSTed to the local t3 server's `/api/orchestration/dispatch` — `thread.create`, then `thread.turn.start` carrying the prompt. **There is no prompt-submission race**: a dispatch either returns a receipt or an error, so there is no URL to poll for and no keystroke to nudge.

**`--watch` is what makes stacking work** (it implies `--defer-stacked`):

- Targets **without** `stack_on` — the roots — open immediately.
- Targets **with** `stack_on` go to the `deferred` bucket and are handed to a **detached `stack_watcher.py`**, which polls each blocker's PR and opens the child the moment that blocker is stackable. The watcher survives this session closing (`start_new_session=True`), and delegates the actual launch back to `dispatch_sessions.py`, so thread creation stays in one place.
- Without `--watch`, a `stack_on` target opens right away and its `/handle-it` does its own Phase-2 wait. That's the `-no-stack` behaviour — correct, just slower and it holds ~480 MiB idling.

**What the watcher waits for** is `/handle-it`'s Phase 10 — the blocker's PR reviewed to **Quality 5/5 ∧ Spec 5/5 on its current head** (read from the `<!-- swat-scores: … -->` / `<!-- swat-reviewed-sha: … -->` markers on the 🪰 rating comment), **not `CONFLICTING`**, and **CI not failing or pending**. It reads all of that from `gh` — never from a Linear label, because a label lags a crashed session and `gh` doesn't. Special cases it handles: blocker **merged** while waiting → launch unstacked against the base branch; blocker's PR **closed** unmerged, or still no PR after `--no-pr-grace-mins` (90m) → give up on that child and report it. In a chain (A ← B ← C) the grace clock for C doesn't start until B is out of the queue.

Watcher flags: `--watch-interval` (default 300s — a review round takes minutes, so polling faster only burns API quota), `--watch-max-hours` (default 12), `--watch-log` (default `$TMPDIR/bh-stack-watch.log`).

Other useful flags: `--dry-run` (validate, print the commands and the root/deferred split, dispatch nothing), `--stagger N`, `--model` (default `claude-opus-5`), `--effort` (fallback when a target sets none, default `medium`), `--runtime-mode` (default `full-access`), `--interaction-mode` (`plan` opens every thread in plan mode), `--context-window` (default `1m`), `--base-url` / `--token` (default `$T3CODE_URL` → `http://127.0.0.1:3773`, and a token minted on the fly). Leave `--prompt` alone outside of harness testing — a stacked child's stack directive is appended to it automatically.

Roots still have **no concurrency cap** by design; `--stagger` only spaces out thread startup.

The script refuses a repo with no `.claude/handle-it/config.md` (`/handle-it` needs it) and refuses a repo that isn't a registered t3 project — it resolves `repo` against each project's `workspaceRoot` rather than guessing, and prints the known roots when it can't match. Add a missing one with `t3 project add`.

**Re-running is safe.** Each issue's thread id is a UUIDv5 derived from the issue id, so a launch is idempotent by construction: the script looks the id up in the shell snapshot and skips an issue whose thread is already open. That keys on the **id**, never the title — a thread renamed live from the web UI or the phone is still recognised, so **never delete a running thread just to rename it**. The title passed here is only the starting name.

## Step 6 — Report

Read the JSON on stdout and give the user a table: issue · title · effort · repo · thread URL. Then the skipped and failed rows with reasons. The URLs are the deliverable — they're how the batch gets driven from the phone.

**Then report the deferred set separately** — these have no URL yet, which is expected, not a failure. Give the issue, its blocker, and the watcher's pid + log path from `report.watcher`:

```
Held for stacking (2) — watcher pid 48213, polling every 300s → /tmp/bh-stack-watch.log
  KEY-102  waiting on KEY-101   → opens as a stacked PR once its blocker hits manual-review
  KEY-107  waiting on KEY-101   → same blocker; both stack on it independently
```

Be explicit that **a deferred thread appears in the sidebar only when it opens** — otherwise the user will look for a URL that isn't there yet and assume it broke.

Close with the fleet-management commands:

```bash
TOK=$(t3 auth session issue --ttl 1h --token-only)          # scoped bearer for the calls below
H="Authorization: Bearer $TOK"; API=http://127.0.0.1:3773/api/orchestration

curl -s $API/shell -H "$H" | jq -r '.threads[] | "\(.id)  \(.session.status // "-")  \(.title)"'
curl -s $API/threads/<thread-id> -H "$H" | jq '.turns[-1]'   # peek at one thread's last turn

# stop a thread's session / delete it outright
curl -s -X POST $API/dispatch -H "$H" -H 'content-type: application/json' \
  -d '{"type":"thread.session.stop","commandId":"'$(uuidgen)'","threadId":"<id>","createdAt":"'$(date -u +%FT%T.000Z)'"}'
curl -s -X POST $API/dispatch -H "$H" -H 'content-type: application/json' \
  -d '{"type":"thread.delete","commandId":"'$(uuidgen)'","threadId":"<id>"}'

tail -f /tmp/bh-stack-watch.log        # what the stack watcher is waiting on
pgrep -af stack_watcher.py             # is the watcher still alive
pkill -f stack_watcher.py              # stop deferred launches (open threads unaffected)
```

Then **stop**. Each thread runs `/handle-it` autonomously to its own manual-review gate and opens its own draft PR; the watcher opens the stacked children on its own schedule. Don't poll either from here — this skill's job ends once the roots are up, the watcher is detached, and the user has the URLs.

## Notes

- Threads open with `runtimeMode: full-access`; unattended `/handle-it` stalls below it (it runs builds, `gh`, and migrations constantly). The other modes — `approval-required`, `auto-accept-edits`, `auto` — all park the run on an approval prompt nobody is watching.
- **The single-shot `bootstrap` form of `thread.turn.start` is WebSocket-only.** It lives in the t3 server's `src/ws.ts`; the HTTP dispatch route forwards raw commands to the decider, which rejects a turn against a thread that doesn't exist yet. That's why launching is two dispatches (`thread.create`, then `thread.turn.start`) rather than one. It also means `bootstrap.prepareWorktree` and `runSetupScript` are unavailable on this path — which is fine, because `/handle-it` owns its own worktree anyway.
- **A half-created thread is rolled back.** If `thread.create` lands and `thread.turn.start` fails, the script deletes the empty thread, so the deterministic-id skip doesn't treat it as already-open on the next run and leave it forever unprompted. If the rollback itself fails, the report names the thread id to delete by hand.
- **Auth is a scoped bearer token.** `$T3CODE_TOKEN` if set, otherwise minted per run with `t3 auth session issue --ttl 12h --label batch-handle-it --token-only`. Dispatch needs the orchestration *operate* scope; the snapshot reads need *read*. The watcher outlives the launching process and can't mint interactively later, so it inherits the run's token through its environment — which is why the default TTL (12h) matches `--watch-max-hours`.
- **A minted token is full-scope.** `t3 auth session issue` has no scope flag, so every token it mints carries the lot — `orchestration:*`, `terminal:operate`, `access:write`, `relay:write` — not just the orchestration scopes dispatch needs. Prefer a short `--token-ttl`, and `t3 auth session revoke <id>` a token you minted for a one-off (`t3 auth session list` shows them, labelled `batch-handle-it`).
- **Archiving a thread in the t3 UI does not stop it.** Archiving only sets `archivedAt`; the provider session keeps running. To actually finish one, dispatch `thread.session.stop` (or `thread.delete`). The already-open check ignores archived threads, so an archived-but-unfinished issue will be relaunched on the next run.
- **Thread ids are deterministic** — UUIDv5 over `batch-handle-it:<issue-id>` — so the id for an issue is stable across runs and machines, and re-running never double-claims. The namespace is distinct from any sibling batch skill's, so two skills launching the same issue id can't collide onto one thread.
- The reported URL is `<base>/threads/<thread-id>`. It is built from the base URL, not returned by the API; if the web UI's route ever changes, that's the line to fix.
- **Memory is the real constraint, and there is deliberately no concurrency cap.** Measured on a 4-core/31 GiB box: a session idles at **~480 MiB**, but a verify gate's typecheck can spike to **~3.7 GB**. Roughly **two concurrent typechecks fit** there; the third is at the edge. Check `free -h` before a wide batch.
- **Stacking cuts idle memory but raises peak memory.** Deferring a blocked issue saves its ~480 MiB of doing-nothing, which is the win. But stacking exists to make blocked work *run* instead of wait, so more sessions reach a verify gate — and the gate is the multi-GB spike, not the idle. If a batch has several issues stacking on one blocker, consider raising `--watch-interval` so they don't all land in the same minute.
- **The watcher is a plain detached process, not a service.** It dies with a reboot and is not restarted. Its state lives in `$TMPDIR/bh-stack-plan.json`, so a lost watcher is recoverable — re-run it by hand against that file (giving it a token), or just re-run `/batch-handle-it` (the already-open check skips whatever is already up):
  ```bash
  T3CODE_TOKEN=$(t3 auth session issue --ttl 12h --token-only) \
  python3 "${CLAUDE_PLUGIN_ROOT}/skills/batch-handle-it/scripts/stack_watcher.py" \
    --plan /tmp/bh-stack-plan.json --log /tmp/bh-stack-watch.log &
  ```
- **Swap does not save you.** A fast-allocating typechecker loses the reclaim race and gets OOM-killed rather than thrashing. Don't treat free swap as headroom.
- **The failure mode is invisible.** When a build child dies to the OOM killer, the session survives with its turn killed — it reports "stuck mid-conversation" and otherwise looks healthy. Afterwards, spot wedged threads by looking for a turn that never completed:
  ```bash
  curl -s http://127.0.0.1:3773/api/orchestration/shell \
    -H "Authorization: Bearer $(t3 auth session issue --ttl 5m --token-only)" \
  | jq -r '.threads[] | select(.latestTurn.state != "completed")
           | "\(.title)  \(.latestTurn.state)  \(.latestTurn.requestedAt)"'
  ```
  Recovery is safe: delete the wedged thread and re-run — the queue skips what's still open, and `/handle-it` resumes its issue from ground truth rather than restarting.
