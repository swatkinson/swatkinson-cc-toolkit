# Swatkinson's Claude Code Toolkit

_Version 0.1.3_

## Install

```
/plugin marketplace add swatkinson/swatkinson-cc-toolkit
/plugin install swatkinson-toolkit
```

To update later:

```
/plugin marketplace update swatkinson-cc-toolkit
```

The `/plugin` menu shows when a newer version is available (driven by the `version` in the plugin manifest).


## What's inside — `swatkinson-toolkit`

### Skills
| Skill | What it does |
|-------|--------------|
| `handle-it` | End-to-end orchestrator: Linear issue (or freeform feature) → plan → implement → draft PR → review⇄fix loop (5/5) → CI + preview → auto-test → your manual review → ready-for-review. |
| `claudecodile-review` | 🐊 Iterate-until-5/5 in-house review⇄fix loop on a PR. Opus reviewer posts P#-tagged inline comments with suggested fixes; Sonnet fixer applies them. Standalone, or delegated to by `handle-it`. |
| `issue-watcher` | Live, self-refreshing dashboard of your active Linear issues. |
| `skill-evaluate` | Retrospective self-evaluation of a skill run, scored against a 6-dimension rubric. |

### Agents (spawned by the skills)
`claudecodile-reviewer`, `claudecodile-fixer`, `handle-it-shipper`, `handle-it-investigator`, `handle-it-test-runner`, `issue-watcher-scanner`.

## Prerequisites

These skills were built for my workflow and lean on tools/plugins beyond this one. Install/configure these or the affected skills won't fully work:

- **Linear MCP server** — `handle-it`, `issue-watcher` (and the `issue-watcher-scanner` agent) read/write Linear issues. Without it, those skills can't function.
- **[`agentsystem-core`](https://github.com/AgentSystemLabs/core) plugin** — `handle-it` delegates to `agentsystem-core:ship` and `agentsystem-core:fix-pr-tests`.
- **`diagnose` and `code-review` skills** — `handle-it`/`claudecodile-review` invoke these for the investigate and review passes. Both come from [Matt Pocock's skills toolkit](https://github.com/mattpocock/skills).
- **GitHub CLI (`gh`)**, authenticated — all PR operations.
- **`bun`** — the verification gates (`bun run check`, `bun run test`) assume a Bun project. Skills that run these are tuned to my repos' conventions; you may need to adapt the commands.

`skill-evaluate` is the only fully standalone skill — no external prerequisites.

## Notes on portability

- Some skill bodies reference paths like `~/.claude/skills/...` and `~/.claude/agents/...` for orientation. After install via this plugin the files actually live under the plugin's directory; those references are documentation only and don't affect execution.
- Git/PR conventions (Conventional Commits, `Refs: BE-####`, draft-PR flow, Vercel previews) reflect my setup — review and adjust for yours.

## Repo layout

```
.claude-plugin/marketplace.json     ← marketplace manifest (this repo)
plugins/swatkinson-toolkit/
  .claude-plugin/plugin.json        ← plugin manifest
  skills/<skill>/SKILL.md           ← + REFERENCE.md per skill
  agents/<agent>.md
scripts/sync-version.ps1            ← keep the version in sync across the 3 files
```

## Releasing

The version appears in three places that must stay in sync — `plugins/swatkinson-toolkit/.claude-plugin/plugin.json` (the source of truth), `.claude-plugin/marketplace.json`, and the subtitle at the top of this README. `scripts/sync-version.ps1` keeps them aligned:

```powershell
pwsh scripts/sync-version.ps1            # check: reports drift, exits 1 if the three disagree
pwsh scripts/sync-version.ps1 -Set 0.2.0 # bump: writes the new version to all three
```

Run the check before tagging a release (or wire it into a pre-commit hook / CI step).
