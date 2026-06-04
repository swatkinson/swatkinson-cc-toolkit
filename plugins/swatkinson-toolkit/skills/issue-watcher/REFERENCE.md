# issue-watcher — reference

Mechanics for [SKILL.md](SKILL.md). Linear runtime resolution mirrors `/handle-it` (same `mcp__linear-server__*` namespace, same team/status id resolution) — see `~/.claude/skills/handle-it/REFERENCE.md` → Linear runtime resolution if you need the details.

## Watch set

Default scope is **assignee = me**. The buckets:

- **In Progress** — `list_issues` assignee=me, state = In Progress.
- **In Review** — assignee=me, state = In Review.
- **Blocked** — two sources, unioned:
  - a workflow state literally named **Blocked / Paused** if the team has one (`list_issue_statuses` reveals it); and
  - any watched issue a scanner reports with an **open `blockedBy`** (a blocker not yet `Done`) — bucket it as Blocked regardless of its workflow state.
- **Blocked-and-waiting in Todo** — handle-it parks blocked issues in **Todo** (it doesn't claim until unblocked), so also pull assignee=me **Todo issues with the `ai` label**. These surface as Blocked once a scanner confirms the open blocker; if a Todo+ai issue turns out to have no block and no work started, drop it from the board (it's not "active" yet).

`list_issues` truncates descriptions and hides relations — that's fine here: Phase 1 only needs `{id, identifier, title, status}`. The descriptions + relations are read by the scanners, in isolation. De-dupe across buckets (an issue can match more than one filter).

Scope can be widened by the user (e.g. "watch the whole team's in-flight") — pass a different assignee/team filter; the rest of the pipeline is unchanged.

## Scanner contract

One `issue-watcher-scanner` (Haiku) per issue, spawned in parallel. **Input:** the issue `id`, `identifier`, and the branch convention `<domain>/<be-id>/<kebab>`. **Output:** exactly one compact JSON row, no description text:

```json
{
  "identifier": "BE-1234",
  "title": "<≤40 chars>",
  "status": "In Progress",
  "source": "handle-it" | "derived",
  "pr": 659,
  "prState": "draft" | "ready" | "merged" | null,
  "blockedBy": ["BE-1230"],
  "phases": {"Plan":"…","Implement":"…","Draft PR":"…","Review":"…","CI+Preview":"…","Manual Test":"…","Senior Review":"…","Merged":"…"},
  "note": "<short phrase>"
}
```

- `source:"handle-it"` → the scanner parsed the `<!-- handle-it:status -->` block from the description (authoritative).
- `source:"derived"` → no block; the scanner derived from ground truth (see below). The orchestrator prefixes the issue cell with `*`.
- An unreadable issue returns `{"identifier":…, "error":…}` → footnote it, don't let it break the table.

## Derivation (no handle-it block)

The scanner's best-effort mapping from git/gh to a coarse phase→state:

| Ground truth | Derived signal |
|---|---|
| PR `state = MERGED` | `Merged ✅` |
| PR ready (not draft), in review | `Senior Review` per `reviewDecision` (`✅` approved / `⏳` pending / `❌` changes) |
| PR is a **draft** | `Draft PR ✅`; `CI+Preview` from `statusCheckRollup`; Review/Manual unknown (`—`) |
| Worktree/branch exists, no PR | `Implement ⏳` |
| Neither worktree nor PR | reflect the Linear workflow status only; phases `—` |

Derived rows are guesses — never presented as a true handle-it status. They exist so issues that were *not* driven by handle-it still appear on the board.

## Table format

One table, sorted **Blocked → In Review → In Progress**, then by identifier. Phase columns mirror handle-it's status table.

```markdown
🔭 **Issue Watcher** · refreshed <time> · cycle #<n> · <N> issues

| Bucket | Issue | Title | Plan | Impl | Draft PR | Review | CI+Prev | Manual | Senior | Merged | Note |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 🟥 Blocked | BE-1230 (#651) | Contract origin field | ✅ | ✅ | ✅ | ✅ 5/5 | ✅ | ✅ | ⏳ | — | waiting on senior |
| 🟦 In Review | BE-1234 (#659) | Single assignee per issue | ✅ | ✅ | ✅ | ✅ 5/5 | ✅ | ✅ | ⏳ | — | senior review |
| 🟨 In Progress | *BE-1240 | Region rich list | ✅ | ⏳ | — | — | — | — | — | — | worktree only* |

\* = derived (no handle-it table) · blockers shown in Note (e.g. "⛔ BE-1230")
```

- **Issue cell:** `BE-#### (#PR)`; append `(#N)` only when a PR exists. Prefix `*` for derived rows.
- **Title:** truncate to ~30–40 chars.
- **Blocked Note:** name the open blocker(s) — `⛔ BE-1230` — so the user sees *what* it's waiting on.
- Keep the **Review** cell's live rating (`⏳ 4/5`, `✅ 5/5`) straight from the handle-it block.
- Stamp the **refresh time** with Bash `date` and a **refresh counter** so the user can see it's live.

## Loop cadence

`ScheduleWakeup(delaySeconds, prompt = "<original /issue-watcher invocation>")` after each print. Pick `delaySeconds`:
- **Active** ~240s (frequent, cache-warm; don't use exactly 300s — the cache boundary).
- **Background** ~900–1800s (each refresh spawns N Haiku scanners; longer = cheaper).
- Honor an explicit interval from the invocation; the user can `/loop` it instead, or say "stop".

Re-entry is stateless — every refresh re-gathers the watch set and re-fans the scanners, so issues that left/entered the buckets self-correct. The only cross-refresh state worth keeping is the **previous table** (for the delta callout); if context was compacted and it's gone, skip the delta.

## Cost note

Per refresh ≈ one light `list_issues` sweep + N Haiku scanner spawns. That's cheap, but it's **not free × every 4 minutes × all day** — if the user leaves it running in the background, nudge them toward a longer interval. Log the watch-set size each refresh so the cost is visible.
