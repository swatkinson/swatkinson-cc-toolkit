# Claudecodile Review Bot — automated PR reviews on company projects

Runs the 🐊 `claudecodile-reviewer` on every pull request in a repo, headlessly via
`claude -p` in GitHub Actions. It posts **P#-tagged inline comments** (with
suggested-fix blocks) and maintains the single **`## 🐊 Claudecodile Rating`** comment
scoring Code Quality / Spec. Adherence / Risk.

**Review-only by design.** The bot never edits code, commits, pushes, or changes a
PR's draft state. It only posts review comments. (The reviewer agent is comment-only,
and the workflow additionally hard-disallows the edit tools.) Fixes stay with humans —
or run `/claudecodile-review` or `/handle-it` locally to drive the fix loop.

## How it fits together

```
swatkinson-cc-toolkit
  .github/workflows/claudecodile-review.yml   ← reusable workflow (the engine)

each company repo
  .github/workflows/claudecodile-review.yml   ← tiny caller (copied from caller-workflow.yml)
        │  on: pull_request [opened, synchronize, ready_for_review]
        ▼
  reusable workflow → checks out PR head + toolkit plugin
        → claude -p (OAuth token) → runs /claudecodile-review (single pass)
        → spawns claudecodile-reviewer (Opus)
        → posts inline comments + 🐊 Rating comment via gh
```

Re-running on each push is safe: the reviewer **auto-discovers and edits the existing
rating comment** (no duplicates) and **resolves the threads it verifies are fixed**.

## One-time setup

### 1. Generate a Claude OAuth token

On a machine logged into a Claude **Pro / Max / Team / Enterprise** subscription:

```bash
claude setup-token
```

Copy the printed token. It's a long-lived (≈1 year) inference token tied to your
subscription — it does **not** save itself anywhere, so paste it straight into the
secret below.

### 2. Add it as a GitHub secret

Add `CLAUDE_CODE_OAUTH_TOKEN` as an **organization secret** (Settings → Secrets and
variables → Actions → New organization secret), scoped to the repos that should get
reviews. A per-repo secret works too if you only want it on one project.

> **Do not also set `ANTHROPIC_API_KEY`** in these workflows. The API key takes
> precedence over the OAuth token and would bill the API instead of your subscription.

### 3. Add the caller workflow to each company repo

Copy [`caller-workflow.yml`](caller-workflow.yml) into the repo at
`.github/workflows/claudecodile-review.yml` and commit it to the default branch.
That's the only file each project needs.

### 4. (Recommended) Add a project config for best results

The reviewer reads two optional files from the **target repo** for comment formatting
and project rules:

- `.claude/handle-it/rules/inline-comments.md`
- `.claude/handle-it/rules/rating-comment.md`

…plus `.claude/handle-it/config.md` (hard-rule files, conventions). Generate all of
them once per repo by running **`/handle-it-project-setup`** locally in that repo. If
they're absent the reviewer falls back to sensible built-in defaults — so this step is
optional but improves consistency with your other Claudecodile tooling.

## Behavior & tuning

- **Triggers:** PR `opened`, `synchronize` (new commits), `ready_for_review`.
- **Drafts are skipped** by the caller's `if: github.event.pull_request.draft == false`.
  Delete that line in the caller to review drafts too.
- **Concurrency:** a new push cancels the in-flight review for that PR (set in the
  caller workflow).
- **Model:** Opus by default; override with `model:` in `with:`.
- **Pinning:** the caller references the reusable workflow `@main`. For reproducible
  reviews, cut a tag in the toolkit repo and pin both the `uses:` ref and
  `toolkit_ref:` to it.
- **Cost / noise control:** because every push re-reviews the full diff, lean on the
  draft-skip + `ready_for_review` trigger for WIP branches, and consider a path filter
  (`paths:` / `paths-ignore:`) in the caller for docs-only changes.

## Permissions the bot uses

The reusable workflow requests:

```yaml
permissions:
  contents: read         # read the diff and surrounding code
  pull-requests: write   # post inline comments + the rating comment
```

It uses the run's built-in `GITHUB_TOKEN` (`GH_TOKEN`) for all `gh` calls — no PAT
required. Because the bot only posts comments (never pushes), there's no risk of it
re-triggering itself.

## Troubleshooting

- **"Invalid API key" / auth errors** — the OAuth token is missing/expired, or
  `ANTHROPIC_API_KEY` is also set and overriding it. Re-run `claude setup-token` and
  update the secret; remove any `ANTHROPIC_API_KEY`.
- **No comments posted, job green** — check the job log for the reviewer's summary. If
  it analyzed but didn't post, confirm `pull-requests: write` is granted and the PR
  isn't a fork from a public repo (forked-PR runs get a read-only token by default;
  see GitHub's `pull_request_target` docs if you need fork coverage — use with care).
- **Plugin/agent not found** — verify `toolkit_repo`/`toolkit_ref` point at a repo
  containing `plugins/swatkinson-toolkit`, and that the ref exists.
- **Reviews on every tiny push are noisy** — keep branches as drafts until ready, or
  switch the caller to a label/mention trigger (the reusable workflow's logic is the
  same; only the `on:` block changes).
