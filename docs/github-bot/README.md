# Swat Reviewer Bot — automated PR reviews on company projects

Runs the 🪰 `swat-reviewer` on every pull request in a repo, headlessly via
`claude -p` in GitHub Actions. It posts **P#-tagged inline comments** (with
suggested-fix blocks) and maintains the single **`## 🪰 Swat Reviewer Rating`** comment
scoring Code Quality / Spec. Adherence / Risk.

**Non-mutating by design.** The bot never edits code, commits, pushes, or changes a
PR's draft state. (The workflow additionally hard-disallows the edit tools.) Fixes stay
with humans — or run `/swat-review` or `/handle-it` locally to drive the fix loop. The
one review verdict it does submit: on a **non-draft** PR scoring **Code Quality 5/5 ∧
Spec. Adherence 5/5 ∧ Risk and Complexity ≥ 4**, it submits a formal GitHub **Approve**
(risk-based auto-approval; requires the branded App identity, since a bot can't approve
as the PR author). On a `ready_for_review` re-trigger it **fast-paths** — if the rating
already passed against the current head SHA (read from the `<!-- swat-reviewed-sha: … -->`
marker in the rating comment), it approves without a full re-review. Enable "dismiss
stale approvals on push" in branch protection so an approval clears if a later commit
regresses.

## How it fits together

```
swatkinson-cc-toolkit
  .github/workflows/swat-review.yml   ← reusable workflow (the engine)

each company repo
  .github/workflows/swat-review.yml   ← tiny caller (copied from caller-workflow.yml)
        │  on: pull_request [opened, synchronize, ready_for_review]
        ▼
  reusable workflow → checks out PR head + toolkit plugin
        → claude -p (OAuth token) → runs /swat-review (single pass)
        → spawns swat-reviewer (Opus)
        → posts inline comments + 🪰 Rating comment via gh
```

Re-running on each push is safe: the reviewer **auto-discovers and edits the existing
rating comment** (no duplicates) and marks now-fixed findings **`[FIXED]`**.

> **Thread resolution needs an App/PAT token.** Actually *resolving* the inline thread
> of a fixed finding (`resolveReviewThread`) is **not permitted** for the default
> `github-actions[bot]` `GITHUB_TOKEN` — GitHub returns `Resource not accessible by
> integration` even with `pull-requests: write`. On the default setup, fixed findings
> are still marked `[FIXED]` in the rating comment, but their inline threads stay
> visibly open. To get real thread resolution, run the bot under a **custom GitHub App
> identity** (see below) or a bot-user PAT — those tokens can resolve threads.

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
`.github/workflows/swat-review.yml` and commit it to the default branch.
That's the only file each project needs.

### 4. (Recommended) Add a project config for best results

The reviewer reads two optional files from the **target repo** for comment formatting
and project rules:

- `.claude/handle-it/rules/inline-comments.md`
- `.claude/handle-it/rules/rating-comment.md`

…plus `.claude/handle-it/config.md` (hard-rule files, conventions). Generate all of
them once per repo by running **`/handle-it-project-setup`** locally in that repo. If
they're absent the reviewer falls back to sensible built-in defaults — so this step is
optional but improves consistency with your other Swat Reviewer tooling.

## Behavior & tuning

- **Triggers:** PR `opened`, `synchronize` (new commits), `ready_for_review`.
- **Drafts ARE reviewed by default** (that's what feeds `/handle-it`'s CI-mode fix loop
  while the PR is still a draft). To skip drafts, uncomment the caller's
  `if: github.event.pull_request.draft == false` line — `ready_for_review` still reviews
  (and, at the bar, approves) the PR once it leaves draft.
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

The review job needs:

```yaml
permissions:
  contents: read         # read the diff and surrounding code
  pull-requests: write   # post inline comments + the rating comment
```

**These must be granted by the *caller* workflow** (already in `caller-workflow.yml`).
A reusable workflow's job can't request more permission than the caller's token
grants, and many repos/orgs default `GITHUB_TOKEN` to restricted (`pull-requests:
none`) — in which case GitHub rejects the call at parse time with
`is requesting 'pull-requests: write', but is only allowed 'pull-requests: none'`.
The caller's top-level `permissions:` block fixes that.

It uses the run's built-in `GITHUB_TOKEN` (`GH_TOKEN`) for all `gh` calls — no PAT
required. Because the bot only posts comments (never pushes), there's no risk of it
re-triggering itself.

## Custom bot identity (instead of `github-actions[bot]`)

By default comments post as **`github-actions[bot]`** — that's whoever the
`GITHUB_TOKEN` belongs to, and it can't be renamed. To brand the reviewer (its own
name + avatar, e.g. **Swat Reviewer**), post with a **GitHub App** token instead.

One-time setup:

1. **Create the App** — GitHub → Settings → Developer settings → GitHub Apps → New.
   Give it a name (e.g. `Swat Reviewer`) and an avatar. Under **Permissions →
   Repository → Pull requests: Read & write** (and **Contents: Read-only**). No
   webhook needed (uncheck Active).
2. **Generate a private key** (App settings → Private keys → Generate) — downloads a
   `.pem`. Note the **App ID** shown at the top.
3. **Install the App** on your org/repos (App settings → Install App).
4. **Store the credentials** on the consuming repo/org:
   - `SWAT_REVIEWER_APP_ID` as an Actions **variable** (App ID isn't secret), and
   - `SWAT_REVIEWER_APP_PRIVATE_KEY` as an Actions **secret** (paste the full `.pem`).
5. **Pass them in the caller** (uncomment in `caller-workflow.yml`):
   ```yaml
   jobs:
     review:
       uses: swatkinson/swatkinson-cc-toolkit/.github/workflows/swat-review.yml@main
       secrets:
         claude_code_oauth_token: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}
         app_private_key: ${{ secrets.SWAT_REVIEWER_APP_PRIVATE_KEY }}
       with:
         app_id: ${{ vars.SWAT_REVIEWER_APP_ID }}
   ```

When `app_id` is set, the workflow mints a short-lived installation token
(`actions/create-github-app-token`) and posts as your App. Leave it unset and it
falls back to `github-actions[bot]` — no other change needed.

> Alternative: a dedicated **bot user account + PAT** also works (comments appear as
> that user), but it consumes a seat and the PAT is broader-scoped than an App's
> per-install token. The App is recommended.

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
