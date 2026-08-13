#!/usr/bin/env python3
"""Spawn one remote-controlled Claude session per issue, each running /handle-it.

Reads a JSON array of targets on stdin, writes a JSON report on stdout.
All human-readable progress goes to stderr so stdout stays parseable.

Input  (stdin):  [{"id": "KEY-2968", "repo": "/home/me/src/app.acme"}, ...]
Output (stdout): {"launched": [...], "skipped": [...], "failed": [...], "deferred": [...]}

A target may carry `stack_on: "<blocker-id>"` to say "this issue is blocked by <blocker-id>
and should STACK on it rather than wait for it to merge". Such a target is only launchable
once the blocker's PR has reached /handle-it's Phase 10; with --defer-stacked (implied by
--watch) it goes to the `deferred` bucket instead of launching, and --watch hands the
deferred set to stack_watcher.py, which polls GitHub and launches each one at the right
moment. Optional `stack_on_pr` / `stack_on_branch` are passed through to the prompt when
already known, saving /handle-it a lookup.

Each session is a detached tmux session running an interactive `claude
--remote-control <id>`, so it appears in the claude.ai/code sidebar and the
mobile app while executing on this box.
"""

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import time
import uuid

URL_RE = re.compile(r"https://claude\.ai/code/session_[A-Za-z0-9_-]+")
# Signs the pre-filled prompt has been consumed: the TUI is working, or a
# response line has already been rendered.
ACTIVITY = ("esc to interrupt", "\n● ")
# Polls (of 2s) to let the TUI auto-submit before nudging it with an Enter.
NUDGE_AFTER_POLLS = 3
# Sidebar titles have to stay scannable on a phone.
TITLE_MAX = 45
EFFORTS = ("low", "medium", "high", "xhigh", "max")
HERE = os.path.dirname(os.path.abspath(__file__))
WATCHER = os.path.join(HERE, "stack_watcher.py")

# Deliberately NOT auto-registered with claude-rc-watchdog. These sessions are
# exactly the ones you archive when the work is done, and the watchdog's only
# signal for "needs reviving" (no sockets, process alive) is indistinguishable
# from "the human archived it" — so auto-registering would make every finished
# batch session resurrect itself once. Register one by hand if you specifically
# want it kept alive: `claude-rc-session register bh-KEY-#### <session_uuid>`,
# using the session_uuid this script reports below.

# Session-scoped vars a tmux pane inherits from its server. A tmux server that
# was first started from inside a Claude session keeps that session's vars
# forever and hands them to every pane it spawns — including a
# CLAUDE_CODE_SESSION_ACCESS_TOKEN that expires. Sessions then start fine and
# hard-exit ~45 min later on their first token refresh ("session_token expired
# — no refresh was delivered, exiting"), which is what wedged eleven sessions
# on 2026-08-03. Stripping them makes each session establish its own auth.
# CLAUDE_CODE_EXECPATH / _ENABLE_TELEMETRY are kept: not session-scoped.
SCRUB_VARS = (
    "CLAUDE_CODE_SESSION_ACCESS_TOKEN",
    "CLAUDE_CODE_SESSION_ID",
    "CLAUDE_CODE_CHILD_SESSION",
    "CLAUDE_CODE_ENVIRONMENT_KIND",
    "CLAUDE_CODE_ENTRYPOINT",
    "CLAUDE_CODE_WORKER_EPOCH",
    "CLAUDE_PID",
    "CLAUDE_EFFORT",
    "CLAUDECODE",
    "AI_AGENT",
)


def log(msg):
    print(msg, file=sys.stderr, flush=True)


def tmux(*args, check=False):
    return subprocess.run(
        ["tmux", *args], capture_output=True, text=True, check=check
    )


def session_exists(name):
    return tmux("has-session", "-t", f"={name}").returncode == 0


def capture(name):
    # Plain session name only — a "=<name>" exact-match target resolves for
    # has-session but NOT for capture-pane, which wants a pane.
    r = tmux("capture-pane", "-t", name, "-p")
    return r.stdout if r.returncode == 0 else ""


def extract_url(text):
    """Pull the claude.ai remote-control URL out of a captured pane."""
    m = URL_RE.search(text)
    return m.group(0) if m else None


def build_prompt(target, opts):
    """The prompt each session opens with.

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


def spawn(target, opts):
    """Launch one session. Returns (bucket, record)."""
    issue = target["id"]
    repo = target["repo"]
    name = f"{opts.prefix}{issue}"
    rec = {"id": issue, "repo": repo, "tmux": name}

    if not os.path.isdir(repo):
        rec["error"] = f"repo path does not exist: {repo}"
        return "failed", rec
    if not os.path.isfile(os.path.join(repo, ".claude", "handle-it", "config.md")):
        rec["error"] = (
            f"{repo} has no .claude/handle-it/config.md — run "
            "/handle-it-project-setup there first"
        )
        return "failed", rec
    if session_exists(name):
        rec["note"] = "a session for this issue is already running — left alone"
        return "skipped", rec

    prompt = build_prompt(target, opts)

    # The sidebar/mobile display name. Defaults to the issue id, but a short
    # human summary is far easier to scan on a phone. The tmux session name
    # stays keyed on the id so the already-running check keeps working.
    display = str(target.get("title") or issue).strip()
    if len(display) > TITLE_MAX:
        display = display[:TITLE_MAX].rstrip()
        rec["warning"] = f"title truncated to {TITLE_MAX} chars"
    rec["title"] = display

    effort = target.get("effort") or opts.effort

    # Force the session id rather than letting claude pick one, so the
    # tmux-session -> transcript mapping is known by construction. Verified
    # 2026-08-05 that --session-id is honoured alongside --remote-control.
    session_uuid = str(uuid.uuid4())
    rec["session_uuid"] = session_uuid

    argv = ["claude", "--remote-control", display,
            "--session-id", session_uuid,
            "--permission-mode", opts.permission_mode]
    if opts.model:
        argv += ["--model", opts.model]
    if effort:
        argv += ["--effort", effort]
        rec["effort"] = effort
    argv.append(prompt)
    # env -u strips the stale per-session vars a tmux pane inherits (see
    # SCRUB_VARS). Belt-and-braces alongside scrubbing the tmux server's own
    # global environment, which only fixes the server that is running now.
    scrub = ["env"] + [a for v in SCRUB_VARS for a in ("-u", v)]
    cmdline = " ".join(shlex.quote(a) for a in scrub + argv)
    rec["command"] = cmdline

    if opts.dry_run:
        rec["note"] = "dry run — not launched"
        return "skipped", rec

    r = tmux("new-session", "-d", "-s", name, "-c", repo, cmdline)
    if r.returncode != 0:
        rec["error"] = f"tmux failed: {(r.stderr or r.stdout).strip()}"
        return "failed", rec

    # Keep a crashed pane readable instead of vanishing, for diagnosis.
    # remain-on-exit is a *window* option, so -w is required.
    opt = tmux("set-option", "-w", "-t", name, "remain-on-exit", "on")
    if opt.returncode != 0:
        rec["warning"] = f"could not set remain-on-exit: {opt.stderr.strip()}"

    return "launched", rec


def await_url(rec, opts):
    """Poll a launched session until its remote-control URL appears."""
    name = rec["tmux"]
    deadline = time.time() + opts.timeout
    while time.time() < deadline:
        if not session_exists(name):
            rec["error"] = "session died during startup (check: tmux capture-pane)"
            return False
        url = extract_url(capture(name))
        if url:
            rec["url"] = url
            return True
        time.sleep(2)
    rec["error"] = f"no remote-control URL after {opts.timeout}s"
    return False


def ensure_running(rec):
    """Make sure the pre-filled prompt actually got sent.

    `claude --remote-control <name> '<prompt>'` normally submits the positional
    prompt on its own once the TUI is ready. If it hasn't (the prompt is still
    sitting in the input box), nudge it with a single Enter — but only then, so
    we never inject a keystroke into a session that is already working.
    """
    name = rec["tmux"]
    for attempt in range(12):
        pane = capture(name)
        if any(sig in pane for sig in ACTIVITY):
            return True
        # Give the TUI a grace period to submit on its own before nudging —
        # the URL can appear a beat before the prompt is actually sent, and an
        # Enter fired into a not-yet-ready input is what we're avoiding.
        if attempt == NUDGE_AFTER_POLLS:
            tmux("send-keys", "-t", name, "Enter")
        time.sleep(2)
    rec["warning"] = "prompt may not have submitted — open the URL and press Enter"
    return False


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--prefix", default="bh-",
                   help="tmux session name prefix (default: bh-)")
    p.add_argument("--permission-mode", default="bypassPermissions")
    p.add_argument("--model", default="opus",
                   help="model for the spawned sessions; '' to inherit default")
    p.add_argument("--effort", default="medium", choices=[*EFFORTS, ""],
                   help="fallback effort when a target doesn't set its own "
                        "(default: medium; '' to inherit the session default)")
    p.add_argument("--stagger", type=float, default=2.0,
                   help="seconds between launches; NOT a concurrency cap (default: 2)")
    p.add_argument("--timeout", type=int, default=120,
                   help="seconds to wait for each remote-control URL (default: 120)")
    p.add_argument("--prompt", default="/swatkinson-toolkit:handle-it {id}",
                   help="prompt for each session; '{id}' is replaced by the issue id. "
                        "Override only to smoke-test the harness.")
    p.add_argument("--dry-run", action="store_true",
                   help="resolve and validate, but launch nothing")
    p.add_argument("--defer-stacked", action="store_true",
                   help="don't launch targets carrying 'stack_on' — report them in the "
                        "'deferred' bucket instead. Implied by --watch.")
    p.add_argument("--watch", action="store_true",
                   help="after launching the unblocked roots, hand every deferred (stacked) "
                        "target to a DETACHED stack_watcher.py that polls each blocker's PR "
                        "and launches the child once the blocker reaches manual-review. "
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
        # .get() rather than `in` — an empty id would name every session
        # "<prefix>" (colliding) and prompt /handle-it with no issue.
        if not isinstance(t, dict) or not t.get("id") or not t.get("repo"):
            log(f"every target needs a non-empty 'id' and 'repo': {t!r}")
            return 2
        if t.get("effort") and t["effort"] not in EFFORTS:
            log(f"{t['id']}: effort must be one of {', '.join(EFFORTS)} "
                f"(got {t['effort']!r})")
            return 2

    if subprocess.run(["which", "tmux"], capture_output=True).returncode != 0:
        log("tmux is not installed — required to hold the interactive sessions")
        return 2
    if subprocess.run(["which", "claude"], capture_output=True).returncode != 0:
        log("claude is not on PATH")
        return 2

    report = {"launched": [], "skipped": [], "failed": [], "deferred": []}

    # Split before launching so the roots go up first and the stacked children are handed
    # to the watcher as one set. Ordering matters: a child launched before its blocker has
    # a PR would fall back to waiting, which is the behaviour we're removing.
    roots = [t for t in targets if not (opts.defer_stacked and t.get("stack_on"))]
    deferred = [t for t in targets if opts.defer_stacked and t.get("stack_on")]
    for t in deferred:
        rec = {"id": t["id"], "repo": t["repo"], "stack_on": t["stack_on"],
               "note": f"deferred — will launch when {t['stack_on']} reaches manual-review"}
        report["deferred"].append(rec)
        log(f"  ~ {rec['id']:<9} {rec['note']}")

    for i, t in enumerate(roots):
        bucket, rec = spawn(t, opts)
        report[bucket].append(rec)
        marker = {"launched": "+", "skipped": "=", "failed": "!"}[bucket]
        detail = rec.get("error") or rec.get("note") or rec["tmux"]
        log(f"  {marker} {rec['id']:<9} {detail}")
        if bucket == "launched" and i < len(roots) - 1 and opts.stagger:
            time.sleep(opts.stagger)

    # Sessions boot in parallel; collect their URLs after all are launched.
    if report["launched"] and not opts.dry_run:
        log("waiting for remote-control URLs…")
        for rec in list(report["launched"]):
            if await_url(rec, opts):
                ensure_running(rec)
                log(f"  * {rec['id']:<9} {rec['url']}"
                    + (f"  [{rec['warning']}]" if "warning" in rec else ""))
            else:
                log(f"  ! {rec['id']:<9} {rec['error']}")
                # Launched but unreachable — surface as a failure, not a success.
                report["launched"].remove(rec)
                report["failed"].append(rec)

    if opts.watch and report["deferred"] and not opts.dry_run:
        report["watcher"] = start_watcher(deferred, opts)

    json.dump(report, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 1 if report["failed"] else 0


def start_watcher(deferred, opts):
    """Detach a stack_watcher.py that outlives this process (and the calling session)."""
    tmpdir = os.environ.get("TMPDIR", "/tmp")
    plan_path = os.path.join(tmpdir, "bh-stack-plan.json")
    log_path = opts.watch_log or os.path.join(tmpdir, "bh-stack-watch.log")
    with open(plan_path, "w") as f:
        json.dump(deferred, f, indent=2)

    argv = [sys.executable, WATCHER, "--plan", plan_path, "--log", log_path,
            "--interval", str(opts.watch_interval),
            "--max-hours", str(opts.watch_max_hours),
            "--prefix", opts.prefix, "--permission-mode", opts.permission_mode]
    if opts.model:
        argv += ["--model", opts.model]
    if opts.effort:
        argv += ["--effort", opts.effort]

    if not os.path.isfile(WATCHER):
        log(f"  ! watcher missing at {WATCHER} — deferred targets will NOT launch")
        return {"error": f"stack_watcher.py not found at {WATCHER}"}

    try:
        with open(log_path, "a") as logf:
            proc = subprocess.Popen(
                argv, stdout=subprocess.DEVNULL, stderr=logf,
                stdin=subprocess.DEVNULL, start_new_session=True)
    except OSError as e:
        log(f"  ! could not start watcher: {e}")
        return {"error": str(e)}

    log(f"  ~ watcher pid {proc.pid} polling every {opts.watch_interval}s → {log_path}")
    return {"pid": proc.pid, "log": log_path, "plan": plan_path,
            "watching": [t["id"] for t in deferred],
            "interval": opts.watch_interval, "max_hours": opts.watch_max_hours}


if __name__ == "__main__":
    sys.exit(main())
