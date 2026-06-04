---
name: issue-watcher
description: Live dashboard of your active Linear issues. Gathers your In Progress / In Review / blocked issues, fans out Haiku scanner subagents to read each issue's handle-it status block (or derive status from worktree + PR ground truth when there's no block), and compiles ONE consolidated glance-table — then keeps it refreshed on a loop. Use when the user invokes /issue-watcher, or asks for a status board / overview of all their in-flight issues.
---

# issue-watcher

You build and continuously refresh **one consolidated status table** across the user's active Linear issues. Each issue's handle-it status block lives at the top of its Linear description; you surface them all side-by-side so the user can glance at everything in flight.

**Core efficiency rule — fan out, don't read inline.** Never pull issue descriptions into your own context. For each issue, spawn an **`issue-watcher-scanner`** (Haiku) subagent that reads the description in its own context and returns only a **compact status row**. You assemble rows into the table. This keeps your context small no matter how many issues are watched.

Watch-set rules, the derivation logic, the scanner contract, and the table format live in **[REFERENCE.md](REFERENCE.md)**.

## Phase 0 — Preflight

1. **Detect the repo** (CaivanOS / workbench) for the worktree + `gh` derivation; if not a known repo, the handle-it blocks still work but derived rows will be Linear-status-only.
2. **Confirm the Linear MCP** (`mcp__linear-server__*`). If absent, tell the user this skill needs Linear and stop (there's nothing to compile without it).
3. **Resolve IDs once:** my user id (`get_user` query=`me`), team id, and the workflow status ids (so you know which states are In Progress / In Review / Blocked). Reuse across refreshes.
4. **Parse options** from the invocation: an optional refresh **interval** (e.g. `/issue-watcher every 10m`) and an optional **scope** (default: assignee = me). Default interval ≈ **4 min** while actively watching (see Phase 4).

## Phase 1 — Gather the watch set (light)

`list_issues` filtered by assignee = me for the buckets — **In Progress**, **In Review**, and **Blocked** (a Blocked/Paused state if the team has one). Also pull my **Todo issues carrying the `ai` label** so handle-it's *blocked-and-waiting* issues (which it parks in Todo) get caught. Collect just `{id, identifier, title, status}` — do **not** read descriptions here. De-dupe. See REFERENCE → Watch set.

## Phase 2 — Fan out scanners (Haiku, parallel)

Spawn one **`issue-watcher-scanner`** per issue, **in parallel** (multiple `Agent` calls in a single message), passing each its `id` + `identifier` + the branch convention. If there are many (>~15), batch them. Each returns the compact JSON row (handle-it status, or derived status flagged `source:"derived"`, plus any open `blockedBy`). Collect any `error` rows into a short "couldn't read" footnote rather than dropping them silently. See REFERENCE → Scanner contract.

## Phase 3 — Assemble + print the table

Pivot each scanner's `phases` map into the consolidated **one-table** layout (REFERENCE → Table format): a **Bucket** column (Blocked → In Review → In Progress, sorted in that order), the issue (`BE-#### (#PR)`), a truncated title, the handle-it phase columns, and a Status/note. **Prefix the issue cell with `*` when `source:"derived"`** and add the legend `* = derived (no handle-it table)`. Bucket an issue as **Blocked** whenever it has an open `blockedBy`, regardless of its workflow state. Stamp the table with a refresh time (`date` via Bash) and a refresh counter.

## Phase 4 — Keep it fresh (loop)

After printing, schedule the next refresh: `ScheduleWakeup(delaySeconds: <interval>, prompt: "<the original /issue-watcher invocation>")` so the skill re-enters and recompiles. Guidance on the interval:
- **Actively watching:** ~**240s** (4 min) — frequent, and stays inside the prompt-cache window (avoid exactly 300s).
- **Background:** ~**900–1800s** (15–30 min) if the user wants it light; each refresh spawns N Haiku scanners, so longer = cheaper.
- Honor an explicit interval from the invocation. The user can also wrap it in `/loop`, or just say "stop" to end the watch.

**Delta callout (best-effort):** if a prior table is still in your context, note what changed since last refresh above the table — *"BE-1234 moved Review 4/5 → 5/5; BE-1230 merged (unblocks BE-1234)."* Don't fabricate deltas you can't see.

## Principles

- **Read-only.** This skill observes; it never claims, edits, comments on, or transitions issues. (That's handle-it's job.)
- **Context stays flat.** All description-reading happens in scanner subagents. If you're tempted to `get_issue` a description yourself, spawn a scanner instead.
- **Derived ≠ authoritative.** A `*` row is a best-effort guess from git/gh; never present it as a real handle-it status.
- **Cheap by default.** Haiku scanners + a light `list_issues`. Don't widen the watch set or shorten the interval beyond what the user asked for.
