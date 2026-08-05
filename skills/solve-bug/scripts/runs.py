#!/usr/bin/env python3
"""Run-report board for autonomous /solve-bug runs — see .runs/README.md.

Concurrency model, and the reason this is a script rather than hand-written JSON:
many runs execute in parallel in separate sessions, so every write must be
(a) confined to that run's own file and (b) atomic. Writes go through a temp file
+ os.replace, and `phase`/`set` re-read immediately before writing so a run never
clobbers a field it didn't intend to touch.

  new      create a run file, print its runId
  phase    append a completed phase (also refreshes updatedAt)
  set      set a top-level field (dotted paths allowed: repos.piqk-app.pr)
  hold     record a hold: reason + what's needed to resume, status -> held
  render   aggregate every run into one human view
  lint     integrity report (exit 1 on errors)
  gc       archive merged runs older than N days (dry-run unless --execute)
"""

import argparse
import glob
import json
import os
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone

BOARD = os.path.expanduser("~/work/piqk/.runs")
ARCHIVE = os.path.join(BOARD, "archive")
TERMINAL_RUN = {"merged", "failed"}
MARK = {"in_progress": "◐", "held": "⊘", "merged": "✓", "failed": "✗"}


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_atomic(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    with os.fdopen(fd, "w") as fh:
        json.dump(data, fh, indent=2)
    os.replace(tmp, path)


def load(path):
    with open(path) as fh:
        return json.load(fh)


def run_path(run_id):
    hits = glob.glob(os.path.join(BOARD, f"*-{run_id}.json"))
    if not hits:
        sys.exit(f"no run with id {run_id} (looked in {BOARD})")
    return hits[0]


def cmd_new(a):
    run_id = a.run_id or f"{int(time.time()) % 100000:05d}"
    path = os.path.join(BOARD, f"{a.ticket}-{run_id}.json")
    if os.path.exists(path):
        sys.exit(f"{path} already exists")
    write_atomic(path, {
        "runId": run_id, "ticket": a.ticket, "issueType": a.type,
        "startStatus": a.start_status, "status": "in_progress",
        "slot": a.slot, "session": os.environ.get("CLAUDE_CODE_SESSION_ID") or os.environ.get("HERDR_PANE") or os.environ.get("TERM_SESSION_ID"),
        "repos": {}, "scope": None, "evidence": [], "rootCause": None,
        "gates": [], "review": [], "transitions": [], "hold": None,
        "phases": [], "humanShouldCheck": None,
        "createdAt": now(), "updatedAt": now(),
    })
    print(run_id)


def set_dotted(doc, path, value):
    parts = path.split(".")
    cur = doc
    for p in parts[:-1]:
        cur = cur.setdefault(p, {})
    cur[parts[-1]] = value


def cmd_phase(a):
    p = run_path(a.run_id)
    doc = load(p)
    doc.setdefault("phases", []).append({"phase": a.phase, "at": now(), "summary": a.summary})
    doc["updatedAt"] = now()
    write_atomic(p, doc)
    print(f"{a.run_id}: phase '{a.phase}' recorded")


def cmd_set(a):
    p = run_path(a.run_id)
    doc = load(p)
    try:
        value = json.loads(a.value)
    except json.JSONDecodeError:
        value = a.value
    set_dotted(doc, a.field, value)
    doc["updatedAt"] = now()
    write_atomic(p, doc)
    print(f"{a.run_id}: {a.field} set")


def cmd_hold(a):
    p = run_path(a.run_id)
    doc = load(p)
    doc["status"] = "held"
    doc["hold"] = {"reason": a.reason, "needed_to_resume": a.needed,
                   "commentUrl": a.comment_url, "at": now()}
    doc["updatedAt"] = now()
    write_atomic(p, doc)
    print(f"{a.run_id}: HELD — {a.reason}")
    print("  reminder: a hold is only complete with the Jira comment AND the On Hold "
          "transition (473) AND this entry.")


def cmd_render(a):
    runs = [load(f) for f in glob.glob(os.path.join(BOARD, "*.json"))]
    if not runs:
        print("  no runs on the board")
        return
    order = {"in_progress": 0, "held": 1, "failed": 2, "merged": 3}
    runs.sort(key=lambda r: (order.get(r.get("status"), 9), r.get("updatedAt", "")))
    print(f"\n  AUTONOMOUS SOLVE-BUG RUNS — {len(runs)} on the board\n")
    for r in runs:
        m = MARK.get(r.get("status"), "?")
        print(f"  {m} {r['ticket']:<11} run {r['runId']:<7} {r.get('status',''):<12} "
              f"slot={r.get('slot')}  updated {r.get('updatedAt','')}")
        if r.get("phases"):
            last = r["phases"][-1]
            print(f"      last phase: {last['phase']} — {last.get('summary','')}")
        if r.get("hold"):
            print(f"      ⊘ HELD: {r['hold']['reason']}")
            print(f"        to resume: {r['hold'].get('needed_to_resume')}")
        prs = [f"{k}#{v.get('pr')}({v.get('mergeStatus','?')})"
               for k, v in (r.get("repos") or {}).items() if isinstance(v, dict) and v.get("pr")]
        if prs:
            print(f"      PRs: {', '.join(prs)}")
        if r.get("scope", {}) and isinstance(r.get("scope"), dict) and r["scope"].get("outcome"):
            print(f"      scope adjudication: {r['scope']['outcome']}")
        if r.get("humanShouldCheck"):
            print(f"      → human should check: {r['humanShouldCheck']}")
    held = [r for r in runs if r.get("status") == "held"]
    if held:
        print(f"\n  ⊘ {len(held)} run(s) parked and waiting on a human: "
              f"{', '.join(r['ticket'] for r in held)}")
    print()


def cmd_lint(a):
    errs, warns = [], []
    for f in glob.glob(os.path.join(BOARD, "*.json")):
        try:
            r = load(f)
        except Exception as exc:
            errs.append(f"{os.path.basename(f)}: unparseable ({exc})")
            continue
        base = os.path.basename(f)
        if r.get("status") == "held" and not r.get("hold"):
            errs.append(f"{base}: status=held but no hold block")
        if r.get("hold") and not r["hold"].get("needed_to_resume"):
            errs.append(f"{base}: hold without needed_to_resume — nobody can resume it")
        if r.get("status") == "merged" and not r.get("transitions"):
            warns.append(f"{base}: merged but no Jira transitions recorded")
        if r.get("status") == "in_progress" and r.get("updatedAt", "") < (
                datetime.now(timezone.utc) - timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M:%SZ"):
            warns.append(f"{base}: in_progress but untouched for >6h — dead session?")
    for e in errs:
        print(f"  ERROR {e}")
    for w in warns:
        print(f"  warn  {w}")
    if not errs and not warns:
        print("  board clean")
    return 1 if errs else 0


def cmd_gc(a):
    cutoff = (datetime.now(timezone.utc) - timedelta(days=a.days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    moved = 0
    for f in glob.glob(os.path.join(BOARD, "*.json")):
        r = load(f)
        if r.get("status") == "merged" and r.get("updatedAt", "") < cutoff:
            print(f"  {'archiving' if a.execute else 'would archive'} {os.path.basename(f)}")
            if a.execute:
                os.makedirs(ARCHIVE, exist_ok=True)
                os.replace(f, os.path.join(ARCHIVE, os.path.basename(f)))
            moved += 1
    print(f"  {moved} run(s){'' if a.execute else ' (dry-run — pass --execute)'}")
    print("  held/failed runs are never auto-archived — a human resolves those.")


def main():
    ap = argparse.ArgumentParser(prog="runs")
    sub = ap.add_subparsers(dest="cmd", required=True)

    n = sub.add_parser("new"); n.add_argument("ticket")
    n.add_argument("--type", default=None); n.add_argument("--start-status", default=None)
    n.add_argument("--slot", type=int, default=None); n.add_argument("--run-id", default=None)
    n.set_defaults(fn=cmd_new)

    p = sub.add_parser("phase"); p.add_argument("run_id"); p.add_argument("phase")
    p.add_argument("--summary", required=True); p.set_defaults(fn=cmd_phase)

    s = sub.add_parser("set"); s.add_argument("run_id"); s.add_argument("field")
    s.add_argument("value"); s.set_defaults(fn=cmd_set)

    h = sub.add_parser("hold"); h.add_argument("run_id"); h.add_argument("--reason", required=True)
    h.add_argument("--needed", required=True); h.add_argument("--comment-url", default=None)
    h.set_defaults(fn=cmd_hold)

    sub.add_parser("render").set_defaults(fn=cmd_render)
    sub.add_parser("lint").set_defaults(fn=cmd_lint)

    g = sub.add_parser("gc"); g.add_argument("--days", type=int, default=14)
    g.add_argument("--execute", action="store_true"); g.set_defaults(fn=cmd_gc)

    a = ap.parse_args()
    sys.exit(a.fn(a) or 0)


if __name__ == "__main__":
    main()
