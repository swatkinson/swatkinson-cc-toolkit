#!/usr/bin/env python3
"""Poll blocker PRs and launch each stacked child session the moment its blocker is ready.

Reads a JSON array of DEFERRED targets (each carrying `stack_on`) and polls GitHub until
each one's blocker reaches /handle-it's Phase 10 — the "stackable" point: the blocker's PR
is reviewed to the gate ON ITS CURRENT HEAD, conflict-free, and not failing CI. At that
moment the blocker's branch has stopped churning, so a child can safely branch off it
instead of waiting for a human to merge.

Launching is delegated to spawn_sessions.py (one target at a time) so all the tmux /
remote-control-URL / already-running logic lives in exactly one place.

Ground truth is GitHub, never a Linear label: a label can lag a crashed session, `gh` can't.

Input  (stdin or --plan FILE):
    [{"id": "BE-101", "repo": "/path", "title": "...", "effort": "medium",
      "stack_on": "BE-100"}, ...]
Output (stdout): {"launched": [...], "gave_up": [...], "still_waiting": [...]}

Run detached; it is meant to outlive the session that started it:
    nohup python3 stack_watcher.py --plan plan.json --log watch.log &
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SPAWN = os.path.join(HERE, "spawn_sessions.py")

RATING_MARKER = "🪰 Swat Reviewer Rating"
# The reviewer closes every rating comment with these two invisible lines. The scores
# marker is what CI's approve job greps; the sha marker is what proves the scores belong
# to the CURRENT head rather than a rating earned two pushes ago.
SCORES_RE = re.compile(
    r"<!--\s*(?:swat|ccr)-scores:\s*quality=([0-5])\s+spec=([0-5])\s+risk=([0-5])\s*-->"
)
SHA_RE = re.compile(r"<!--\s*(?:swat|ccr)-reviewed-sha:\s*([0-9a-f]{7,40})\s*-->")
# Fallback for ratings written before the markers existed, or a repo whose
# rules/rating-comment.md omits them.
TABLE_QUALITY_RE = re.compile(r"Code Quality\s*\|\s*([0-5])\s*/\s*5")
TABLE_SPEC_RE = re.compile(r"Spec\.?\s*Adherence\s*\|\s*([0-5])\s*/\s*5")

BAD_CONCLUSIONS = {"FAILURE", "TIMED_OUT", "CANCELLED", "ACTION_REQUIRED", "STARTUP_FAILURE"}
PENDING_STATES = {"QUEUED", "IN_PROGRESS", "WAITING", "PENDING", "REQUESTED"}


LOGFILE = None


def log(msg):
    print(msg, file=sys.stderr, flush=True)
    if LOGFILE:
        LOGFILE.write(msg + "\n")


def gh(repo, *args):
    """Run gh in `repo`. Returns (ok, parsed-or-text)."""
    r = subprocess.run(["gh", *args], cwd=repo, capture_output=True, text=True)
    if r.returncode != 0:
        return False, (r.stderr or r.stdout).strip()
    out = r.stdout.strip()
    if not out:
        return True, None
    try:
        return True, json.loads(out)
    except json.JSONDecodeError:
        return True, out


def find_blocker_pr(repo, issue_id):
    """Locate the blocker's PR. /handle-it Phase 5 guarantees the bare issue id is in the body.

    Returns (state, pr_dict|None, note). state ∈ {"open", "merged", "closed", "none"}.
    """
    ok, prs = gh(repo, "pr", "list", "--search", f"{issue_id} in:body",
                 "--state", "all", "--limit", "20",
                 "--json", "number,state,isDraft,headRefName,baseRefName,url,body")
    if not ok:
        return "none", None, f"gh pr list failed: {prs}"
    if not prs:
        return "none", None, "no PR references this issue yet"

    # `--search` is full-text and matches loosely: searching "BE-307" happily returns a PR
    # whose body says "BE-3070", and an unrelated PR can match on incidental text. Confirm
    # the id appears as a whole token before trusting the hit — branching a child off the
    # wrong blocker puts its work on top of unrelated code.
    token = re.compile(rf"\b{re.escape(issue_id)}\b", re.I)
    prs = [pr for pr in prs if token.search(pr.get("body") or "")]
    if not prs:
        return "none", None, "no PR genuinely references this issue (loose search hits discarded)"

    for want in ("OPEN", "MERGED"):
        for pr in prs:
            if pr.get("state") == want:
                return want.lower(), pr, ""
    return "closed", prs[0], "blocker's PR is closed without merging"


def read_rating(body):
    """(quality, spec, reviewed_sha) from a rating comment body. None where unavailable."""
    m = SCORES_RE.search(body or "")
    if m:
        sha = SHA_RE.search(body)
        return int(m.group(1)), int(m.group(2)), (sha.group(1) if sha else None)
    q = TABLE_QUALITY_RE.search(body or "")
    s = TABLE_SPEC_RE.search(body or "")
    if q and s:
        sha = SHA_RE.search(body)
        return int(q.group(1)), int(s.group(1)), (sha.group(1) if sha else None)
    return None, None, None


def checks_verdict(rollup):
    """"pass" | "pending" | "fail" from a statusCheckRollup list.

    An EMPTY rollup passes: on a non-CONFLICTING PR it means the repo simply runs no
    checks for it. (An empty rollup on a CONFLICTING PR is the no-merge-ref trap — the
    caller has already excluded that case via `mergeable`.)
    """
    if not rollup:
        return "pass"
    pending = False
    for c in rollup:
        concl = (c.get("conclusion") or "").upper()
        status = (c.get("status") or c.get("state") or "").upper()
        if concl in BAD_CONCLUSIONS or status in BAD_CONCLUSIONS:
            return "fail"
        if not concl and status in PENDING_STATES:
            pending = True
        elif status in PENDING_STATES:
            pending = True
    return "pending" if pending else "pass"


def stackable(repo, pr):
    """Is this blocker PR at /handle-it's Phase 10? Returns (bool, reason)."""
    n = pr["number"]
    ok, d = gh(repo, "pr", "view", str(n),
               "--json", "headRefOid,mergeable,statusCheckRollup,comments")
    if not ok:
        return False, f"gh pr view failed: {d}"

    if (d.get("mergeable") or "").upper() == "CONFLICTING":
        return False, "PR is CONFLICTING (runs zero workflows until resolved)"

    ratings = [c for c in (d.get("comments") or []) if RATING_MARKER in (c.get("body") or "")]
    if not ratings:
        return False, "no 🏗️ rating comment yet"
    quality, spec, sha = read_rating(ratings[-1].get("body"))
    if quality is None:
        return False, "rating comment present but scores unparseable"
    if quality < 5 or spec < 5:
        return False, f"rating not at the gate (Q{quality} Sp{spec})"

    head = d.get("headRefOid") or ""
    if not sha:
        return False, f"Q{quality} Sp{spec} but no swat-reviewed-sha — can't prove it's the current head"
    if not (head.startswith(sha) or sha.startswith(head)):
        return False, f"rating is stale (reviewed {sha[:8]}, head is {head[:8]})"

    verdict = checks_verdict(d.get("statusCheckRollup"))
    if verdict == "fail":
        return False, "CI is failing"
    if verdict == "pending":
        return False, "CI still running"
    return True, f"Q{quality} Sp{spec}, checks green, head {head[:8]}"


def launch(target, extra_args):
    """Delegate to spawn_sessions.py so tmux/URL logic lives in one place."""
    payload = json.dumps([target])
    r = subprocess.run([sys.executable, SPAWN, *extra_args],
                       input=payload, capture_output=True, text=True)
    try:
        report = json.loads(r.stdout)
    except json.JSONDecodeError:
        return False, {"error": f"spawn_sessions.py returned no JSON: "
                                f"{(r.stderr or r.stdout).strip()[:400]}"}
    for bucket in ("launched", "skipped", "failed"):
        for rec in report.get(bucket, []):
            # Under --dry-run spawn_sessions.py reports "skipped"; that's a success here.
            ok = bucket == "launched" or "dry run" in (rec.get("note") or "")
            return ok, rec
    return False, {"error": "spawn_sessions.py reported nothing"}


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--plan", help="JSON file of deferred targets (default: stdin)")
    p.add_argument("--interval", type=int, default=300,
                   help="seconds between polls (default: 300 — a review round takes minutes, "
                        "not seconds; polling faster just burns API quota)")
    p.add_argument("--max-hours", type=float, default=12.0,
                   help="give up on anything still waiting after this long (default: 12)")
    p.add_argument("--no-pr-grace-mins", type=int, default=90,
                   help="how long a blocker may have NO PR at all before we give up on its "
                        "children — it probably bailed (default: 90)")
    p.add_argument("--log", help="also append progress lines to this file")
    # Forwarded to spawn_sessions.py.
    p.add_argument("--prefix", default="bh-")
    p.add_argument("--model", default="opus")
    p.add_argument("--effort", default="medium")
    p.add_argument("--permission-mode", default="bypassPermissions")
    p.add_argument("--dry-run", action="store_true",
                   help="poll and decide as normal, but forward --dry-run to "
                        "spawn_sessions.py so nothing is actually launched")
    p.add_argument("--once", action="store_true",
                   help="make a single pass instead of looping — for testing the predicate "
                        "against live PRs")
    opts = p.parse_args()

    if opts.log:
        global LOGFILE
        LOGFILE = open(opts.log, "a", buffering=1)

    raw = open(opts.plan).read() if opts.plan else sys.stdin.read()
    try:
        pending = json.loads(raw)
    except json.JSONDecodeError as e:
        log(f"plan is not valid JSON: {e}")
        return 2
    pending = [t for t in pending if t.get("stack_on")]
    if not pending:
        log("nothing to watch — no targets carry 'stack_on'")
        json.dump({"launched": [], "gave_up": [], "still_waiting": []}, sys.stdout)
        return 0

    forwarded = ["--prefix", opts.prefix, "--permission-mode", opts.permission_mode]
    if opts.model:
        forwarded += ["--model", opts.model]
    if opts.effort:
        forwarded += ["--effort", opts.effort]
    if opts.dry_run:
        forwarded.append("--dry-run")

    launched, gave_up = [], []
    deadline = time.time() + opts.max_hours * 3600
    first_seen = {}
    # Issues this watcher has launched. A child whose blocker is in here must keep waiting:
    # the blocker's session exists but hasn't reached Phase 5, so it has no PR to stack on.
    launched_ids = set()

    log(f"watching {len(pending)} stacked target(s); poll every {opts.interval}s, "
        f"giving up after {opts.max_hours}h")

    while pending and time.time() < deadline:
        for target in list(pending):
            issue, blocker, repo = target["id"], target["stack_on"], target["repo"]
            state, pr, note = find_blocker_pr(repo, blocker)

            if state == "none":
                # In a chain (A ← B ← C), C's blocker B has no PR until B itself launches,
                # which can't happen until A is ready. Only start C's grace clock once B is
                # no longer waiting on someone else, or the deeper layers time out first.
                # Two ways the blocker legitimately has no PR yet: it's still queued behind
                # its own blocker, or WE launched it moments ago and it hasn't got to Phase 5.
                # Neither is a bail — don't even start the grace clock.
                if any(t["id"] == blocker for t in pending):
                    log(f"  . {issue:<9} {blocker} hasn't started yet (deeper in the chain)")
                    continue
                if blocker in launched_ids:
                    log(f"  . {issue:<9} {blocker} launched this run — no PR yet")
                    continue
                age_mins = (time.time() - first_seen.setdefault(issue, time.time())) / 60
                if age_mins > opts.no_pr_grace_mins:
                    pending.remove(target)
                    gave_up.append({**target, "reason": f"blocker {blocker} still has no PR "
                                                        f"after {int(age_mins)}m — likely bailed"})
                    log(f"  ! {issue:<9} gave up — {blocker} has no PR after {int(age_mins)}m")
                else:
                    log(f"  . {issue:<9} {blocker}: {note}")
                continue

            if state == "closed":
                pending.remove(target)
                gave_up.append({**target, "reason": note})
                log(f"  ! {issue:<9} gave up — {note}")
                continue

            # Blocker merged while we waited: no stack needed, run against the base branch.
            if state == "merged":
                t = {k: v for k, v in target.items() if k != "stack_on"}
                ok, rec = launch(t, forwarded)
                pending.remove(target)
                if ok:
                    launched_ids.add(issue)
                (launched if ok else gave_up).append(
                    {**rec, "stacked_on": None,
                     "note": f"{blocker} merged before it was needed — launched unstacked"})
                log(f"  {'+' if ok else '!'} {issue:<9} {blocker} merged — launched unstacked")
                continue

            ready, reason = stackable(repo, pr)
            if not ready:
                log(f"  . {issue:<9} waiting on {blocker} (#{pr['number']}): {reason}")
                continue

            # Hand the child the resolved PR number + branch so /handle-it doesn't re-derive them.
            ok, rec = launch({**target, "stack_on_pr": pr["number"],
                              "stack_on_branch": pr["headRefName"]}, forwarded)
            pending.remove(target)
            if ok:
                launched_ids.add(issue)
            (launched if ok else gave_up).append({**rec, "stacked_on": pr["number"]})
            log(f"  {'+' if ok else '!'} {issue:<9} stacking on {blocker} "
                f"(#{pr['number']}) — {reason}")

        if opts.once:
            break
        if pending:
            time.sleep(opts.interval)

    why = "single --once pass finished" if opts.once else f"still not stackable after {opts.max_hours}h"
    for target in pending:
        gave_up.append({**target, "reason": why})
        log(f"  ! {target['id']:<9} not launched — {why}")

    log(f"done: {len(launched)} launched, {len(gave_up)} gave up")
    json.dump({"launched": launched, "gave_up": gave_up, "still_waiting": []},
              sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 1 if gave_up else 0


if __name__ == "__main__":
    sys.exit(main())
