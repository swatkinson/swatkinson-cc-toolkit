#!/usr/bin/env python3
"""Open one t3 Code thread per issue, each running /handle-it.

Reads a JSON array of targets on stdin, writes a JSON report on stdout.
All human-readable progress goes to stderr so stdout stays parseable.

Input  (stdin):  [{"id": "KEY-1234", "repo": "/home/me/src/app.acme"}, ...]
Output (stdout): {"launched": [...], "skipped": [...], "failed": [...], "deferred": [...]}

Drop-in replacement for spawn_sessions.py: same stdin/stdout contract, so
stack_watcher.py delegates here unchanged. The difference is the transport —
instead of driving a detached tmux pane and injecting keystrokes into a TUI,
each launch is a pair of commands dispatched to the local t3 Code server —
`thread.create` then `thread.turn.start`. There is no URL to poll for and no
prompt-submission race: each dispatch either returns a receipt or an error.

Two commands rather than one because the single-shot `bootstrap` form of
`thread.turn.start` (which also creates the thread, and can prepare a worktree
and run a setup script) is implemented only in the server's WebSocket handler —
`src/ws.ts`. The HTTP dispatch route forwards raw commands to the decider, which
rejects a turn against a thread that does not exist yet. If `thread.create`
lands and the turn does not, the empty thread is deleted again, so a re-run
starts clean rather than skipping a thread that was never prompted.

A target may carry `stack_on: "<blocker-id>"` to say "this issue is blocked by
<blocker-id> and should STACK on it rather than wait for it to merge". Such a
target is only launchable once the blocker's PR has reached /implement's
Phase 10; with --defer-stacked (implied by --watch) it goes to the `deferred`
bucket instead of launching. Optional `stack_on_pr` / `stack_on_branch` are
passed through to the prompt when already known, saving /handle-it a lookup.
"""

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone

# Sidebar titles have to stay scannable on a phone.
TITLE_MAX = 45
EFFORTS = ("low", "medium", "high", "xhigh", "max")
RUNTIME_MODES = ("approval-required", "auto-accept-edits", "auto", "full-access")
INTERACTION_MODES = ("default", "plan")
HERE = os.path.dirname(os.path.abspath(__file__))

# Thread ids are free-form strings server-side, so we mint ours deterministically
# from the issue id. That makes a launch idempotent by construction: re-running a
# batch finds the existing thread in the shell snapshot and skips it, without a
# local state file to lose and without keying on the title — which the user can
# rename live from the web UI or the phone.
THREAD_NS = uuid.UUID("e290cfcd-516c-407c-abf9-c168129b4364")

DEFAULT_BASE_URL = "http://127.0.0.1:3773"


def log(msg):
    print(msg, file=sys.stderr, flush=True)


def thread_id_for(issue):
    return str(uuid.uuid5(THREAD_NS, f"batch-handle-it:{issue}"))


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class T3Error(Exception):
    pass


class T3Client:
    def __init__(self, base_url, token):
        self.base_url = base_url.rstrip("/")
        self.token = token

    def _request(self, method, path, payload=None):
        url = f"{self.base_url}{path}"
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", f"Bearer {self.token}")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                body = r.read().decode()
        except urllib.error.HTTPError as e:
            detail = e.read().decode()[:400]
            raise T3Error(f"{method} {path} → HTTP {e.code}: {detail}") from e
        except urllib.error.URLError as e:
            raise T3Error(f"{method} {path} → {e.reason} (is the t3 server running?)") from e
        # A path the server doesn't route falls through to the SPA, which returns
        # HTML with a 200. Treating that as an empty result would silently look
        # like "no projects" rather than "wrong endpoint".
        try:
            return json.loads(body) if body else {}
        except json.JSONDecodeError:
            raise T3Error(f"{method} {path} returned non-JSON (got {body[:80]!r})") from None

    def snapshot(self):
        return self._request("GET", "/api/orchestration/snapshot")

    def shell(self):
        return self._request("GET", "/api/orchestration/shell")

    def dispatch(self, command):
        return self._request("POST", "/api/orchestration/dispatch", command)


def resolve_token(opts):
    """Env var first, otherwise mint a short-lived scoped bearer via the t3 CLI."""
    token = opts.token or os.environ.get("T3CODE_TOKEN")
    if token:
        return token.strip(), "env"
    try:
        r = subprocess.run(
            ["t3", "auth", "session", "issue", "--ttl", opts.token_ttl,
             "--label", "batch-handle-it", "--token-only"],
            capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise T3Error(f"could not run `t3 auth session issue`: {e}") from e
    if r.returncode != 0:
        raise T3Error(f"`t3 auth session issue` failed: {(r.stderr or r.stdout).strip()[:300]}")
    token = r.stdout.strip()
    if not token:
        raise T3Error("`t3 auth session issue --token-only` printed nothing")
    return token, f"minted (ttl {opts.token_ttl})"


def build_project_index(snapshot):
    """workspaceRoot -> projectId, realpath-normalised so /home vs symlink both hit."""
    index = {}
    for p in snapshot.get("projects") or []:
        root = p.get("workspaceRoot")
        if not root or p.get("deletedAt"):
            continue
        index[os.path.realpath(root)] = {"id": p["id"], "title": p.get("title") or root}
    return index


def build_prompt(target, opts):
    """The prompt each thread opens with.

    A stacked child gets an explicit directive appended, because /handle-it's Phase 2
    otherwise has to decide between waiting and stacking on its own — and the watcher has
    already established that the blocker is stackable, so re-deriving it wastes a round
    trip and risks disagreeing.
    """
    prompt = opts.prompt.replace("{id}", target["id"])
    blocker = target.get("stack_on")
    if not blocker:
        return prompt
    where = f"{blocker}"
    if target.get("stack_on_pr"):
        where += f" (PR #{target['stack_on_pr']}"
        if target.get("stack_on_branch"):
            where += f", branch {target['stack_on_branch']}"
        where += ")"
    return (
        f"{prompt} — stack on {where}. Its PR has already reached manual-review handoff "
        f"(Quality 5/5, Spec 5/5, conflict-free, CI green), so do NOT wait for it to merge: "
        f"branch the worktree off its head, open the draft PR with --base on its branch, and "
        f"`gh stack link` the two. This is an unattended batch run — never stop to ask a "
        f"question; bail with a PushNotification and a tracker comment if you genuinely can't "
        f"proceed."
    )


def build_model_selection(effort, opts):
    options = [{"id": "effort", "value": effort}] if effort else []
    options.append({"id": "fastMode", "value": opts.fast_mode})
    if opts.context_window:
        options.append({"id": "contextWindow", "value": opts.context_window})
    return {"instanceId": opts.instance, "model": opts.model, "options": options}


def build_commands(target, project, opts):
    """The (thread.create, thread.turn.start) pair that opens one thread."""
    issue = target["id"]
    display = str(target.get("title") or issue).strip()
    truncated = len(display) > TITLE_MAX
    if truncated:
        display = display[:TITLE_MAX].rstrip()
    effort = target.get("effort") or opts.effort
    created = now_iso()
    model_selection = build_model_selection(effort, opts)

    tid = thread_id_for(issue)
    create = {
        "type": "thread.create",
        "commandId": str(uuid.uuid4()),
        "threadId": tid,
        "projectId": project["id"],
        "title": display,
        "modelSelection": model_selection,
        "runtimeMode": opts.runtime_mode,
        "interactionMode": opts.interaction_mode,
        # Left to /handle-it, which creates and owns its own worktree
        # (its Phase 3). Pre-creating one here collides with the branch it makes.
        "branch": None,
        "worktreePath": None,
        "createdAt": created,
    }
    turn = {
        "type": "thread.turn.start",
        "commandId": str(uuid.uuid4()),
        "threadId": tid,
        "message": {
            "messageId": str(uuid.uuid4()),
            "role": "user",
            "text": build_prompt(target, opts),
            "attachments": [],
        },
        "modelSelection": model_selection,
        "runtimeMode": opts.runtime_mode,
        "interactionMode": opts.interaction_mode,
        "createdAt": created,
    }
    return create, turn, display, effort, truncated


def launch(target, client, projects, live_threads, opts):
    """Open one thread. Returns (bucket, record)."""
    issue = target["id"]
    repo = target["repo"]
    tid = thread_id_for(issue)
    rec = {"id": issue, "repo": repo, "thread_id": tid}

    if not os.path.isdir(repo):
        rec["error"] = f"repo path does not exist: {repo}"
        return "failed", rec
    if not os.path.isfile(os.path.join(repo, ".claude", "handle-it", "config.md")):
        rec["error"] = (
            f"{repo} has no .claude/handle-it/config.md — run "
            "/handle-it-project-setup there first"
        )
        return "failed", rec

    project = projects.get(os.path.realpath(repo))
    if not project:
        known = ", ".join(sorted(projects)) or "none"
        rec["error"] = (
            f"no t3 project has workspaceRoot {repo} — add it with "
            f"`t3 project add` (known roots: {known})"
        )
        return "failed", rec
    rec["project"] = project["title"]

    existing = live_threads.get(tid)
    if existing:
        rec["title"] = existing.get("title")
        rec["url"] = f"{opts.base_url.rstrip('/')}/threads/{tid}"
        rec["note"] = "a thread for this issue is already open — left alone"
        return "skipped", rec

    create, turn, display, effort, truncated = build_commands(target, project, opts)
    rec["title"] = display
    if truncated:
        rec["warning"] = f"title truncated to {TITLE_MAX} chars"
    if effort:
        rec["effort"] = effort
    rec["commands"] = [create, turn]

    if opts.dry_run:
        rec["note"] = "dry run — not dispatched"
        return "skipped", rec

    try:
        client.dispatch(create)
    except T3Error as e:
        rec["error"] = f"thread.create failed: {e}"
        return "failed", rec
    try:
        result = client.dispatch(turn)
    except T3Error as e:
        rec["error"] = f"thread.turn.start failed: {e}"
        # Roll the empty thread back, or the deterministic-id skip would treat it
        # as already open on the next run and it would never get its prompt.
        try:
            client.dispatch({"type": "thread.delete", "commandId": str(uuid.uuid4()),
                             "threadId": tid})
            rec["note"] = "empty thread rolled back — safe to re-run"
        except T3Error as cleanup:
            rec["note"] = (f"empty thread {tid} could NOT be rolled back ({cleanup}) — "
                           f"delete it before re-running")
        return "failed", rec

    rec["sequence"] = result.get("sequence")
    rec["url"] = f"{opts.base_url.rstrip('/')}/threads/{tid}"
    return "launched", rec


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base-url", default=os.environ.get("T3CODE_URL", DEFAULT_BASE_URL),
                   help=f"t3 Code server (default: $T3CODE_URL or {DEFAULT_BASE_URL})")
    p.add_argument("--token", help="bearer token; default $T3CODE_TOKEN, else minted via "
                                   "`t3 auth session issue`")
    p.add_argument("--token-ttl", default="12h",
                   help="TTL for a minted token (default: 12h — long enough for the watcher)")
    p.add_argument("--instance", default="claudeAgent",
                   help="provider instance id (default: claudeAgent)")
    p.add_argument("--model", default="claude-opus-5",
                   help="model for the opened threads (default: claude-opus-5)")
    p.add_argument("--context-window", default="1m",
                   help="contextWindow provider option; '' to omit (default: 1m)")
    p.add_argument("--fast-mode", action="store_true",
                   help="set the fastMode provider option (default: off)")
    p.add_argument("--effort", default="medium", choices=[*EFFORTS, ""],
                   help="fallback effort when a target doesn't set its own "
                        "(default: medium; '' to inherit the provider default)")
    p.add_argument("--runtime-mode", default="full-access", choices=RUNTIME_MODES,
                   help="permission posture; unattended /implement stalls below "
                        "full-access (default: full-access)")
    p.add_argument("--interaction-mode", default="default", choices=INTERACTION_MODES,
                   help="'plan' opens each thread in plan mode (default: default)")
    p.add_argument("--stagger", type=float, default=2.0,
                   help="seconds between dispatches; NOT a concurrency cap (default: 2)")
    p.add_argument("--prompt", default="/swatkinson-toolkit:handle-it {id}",
                   help="prompt for each thread; '{id}' is replaced by the issue id. "
                        "Override only to smoke-test the harness.")
    p.add_argument("--dry-run", action="store_true",
                   help="resolve and validate, print the commands, dispatch nothing")
    p.add_argument("--defer-stacked", action="store_true",
                   help="don't launch targets carrying 'stack_on' — report them in the "
                        "'deferred' bucket instead. Implied by --watch.")
    p.add_argument("--watch", action="store_true",
                   help="after opening the unblocked roots, hand every deferred (stacked) "
                        "target to a DETACHED stack_watcher.py that polls each blocker's PR "
                        "and opens the child once the blocker reaches manual-review. "
                        "Implies --defer-stacked.")
    p.add_argument("--watch-interval", type=int, default=300,
                   help="watcher poll interval in seconds (default: 300)")
    p.add_argument("--watch-max-hours", type=float, default=12.0,
                   help="watcher gives up on a child after this long (default: 12)")
    p.add_argument("--watch-log",
                   help="watcher progress log (default: <tmpdir>/bh-stack-watch.log)")
    opts = p.parse_args()
    if opts.watch:
        opts.defer_stacked = True

    try:
        targets = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        log(f"stdin is not valid JSON: {e}")
        return 2
    if not isinstance(targets, list) or not targets:
        log("expected a non-empty JSON array of {id, repo} objects")
        return 2
    for t in targets:
        # .get() rather than `in` — an empty id would collide every thread onto
        # the same deterministic uuid and prompt /handle-it with no issue.
        if not isinstance(t, dict) or not t.get("id") or not t.get("repo"):
            log(f"every target needs a non-empty 'id' and 'repo': {t!r}")
            return 2
        if t.get("effort") and t["effort"] not in EFFORTS:
            log(f"{t['id']}: effort must be one of {', '.join(EFFORTS)} "
                f"(got {t['effort']!r})")
            return 2

    try:
        token, token_source = resolve_token(opts)
        client = T3Client(opts.base_url, token)
        projects = build_project_index(client.snapshot())
        live_threads = {
            th["id"]: th for th in (client.shell().get("threads") or [])
            if not th.get("archivedAt")
        }
    except T3Error as e:
        log(str(e))
        return 2
    log(f"t3 {opts.base_url} · token {token_source} · "
        f"{len(projects)} project(s) · {len(live_threads)} open thread(s)")

    report = {"launched": [], "skipped": [], "failed": [], "deferred": []}

    # Split before dispatching so the roots go up first and the stacked children are handed
    # to the watcher as one set. Ordering matters: a child opened before its blocker has a
    # PR would fall back to waiting, which is the behaviour stacking removes.
    roots = [t for t in targets if not (opts.defer_stacked and t.get("stack_on"))]
    deferred = [t for t in targets if opts.defer_stacked and t.get("stack_on")]
    for t in deferred:
        rec = {"id": t["id"], "repo": t["repo"], "stack_on": t["stack_on"],
               "note": f"deferred — will open when {t['stack_on']} reaches manual-review"}
        report["deferred"].append(rec)
        log(f"  ~ {rec['id']:<9} {rec['note']}")

    for i, t in enumerate(roots):
        bucket, rec = launch(t, client, projects, live_threads, opts)
        report[bucket].append(rec)
        marker = {"launched": "+", "skipped": "=", "failed": "!"}[bucket]
        detail = rec.get("error") or rec.get("note") or rec.get("url") or rec["thread_id"]
        log(f"  {marker} {rec['id']:<9} {detail}"
            + (f"  [{rec['warning']}]" if "warning" in rec else ""))
        if bucket == "launched" and i < len(roots) - 1 and opts.stagger:
            time.sleep(opts.stagger)

    if opts.watch and report["deferred"] and not opts.dry_run:
        report["watcher"] = start_watcher(deferred, opts, token)

    json.dump(report, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 1 if report["failed"] else 0


def start_watcher(deferred, opts, token):
    """Detach a stack_watcher.py that outlives this process (and the calling session)."""
    watcher = os.path.join(HERE, "stack_watcher.py")
    tmpdir = os.environ.get("TMPDIR", "/tmp")
    plan_path = os.path.join(tmpdir, "bh-stack-plan.json")
    log_path = opts.watch_log or os.path.join(tmpdir, "bh-stack-watch.log")
    with open(plan_path, "w") as f:
        json.dump(deferred, f, indent=2)

    argv = [sys.executable, watcher, "--plan", plan_path, "--log", log_path,
            "--interval", str(opts.watch_interval),
            "--max-hours", str(opts.watch_max_hours),
            "--base-url", opts.base_url,
            "--instance", opts.instance,
            "--runtime-mode", opts.runtime_mode]
    if opts.model:
        argv += ["--model", opts.model]
    if opts.effort:
        argv += ["--effort", opts.effort]

    if not os.path.isfile(watcher):
        log(f"  ! watcher missing at {watcher} — deferred targets will NOT open")
        return {"error": f"stack_watcher.py not found at {watcher}"}

    # The watcher outlives this process, so it can't re-run `t3 auth session issue`
    # interactively later — it inherits this run's token via the environment. That is
    # why --token-ttl defaults to 12h, matching --watch-max-hours.
    env = dict(os.environ, T3CODE_TOKEN=token, T3CODE_URL=opts.base_url)
    try:
        with open(log_path, "a") as logf:
            proc = subprocess.Popen(
                argv, stdout=subprocess.DEVNULL, stderr=logf,
                stdin=subprocess.DEVNULL, start_new_session=True, env=env)
    except OSError as e:
        log(f"  ! could not start watcher: {e}")
        return {"error": str(e)}

    log(f"  ~ watcher pid {proc.pid} polling every {opts.watch_interval}s → {log_path}")
    return {"pid": proc.pid, "log": log_path, "plan": plan_path,
            "watching": [t["id"] for t in deferred],
            "interval": opts.watch_interval, "max_hours": opts.watch_max_hours,
            "token_ttl": opts.token_ttl}


if __name__ == "__main__":
    sys.exit(main())
