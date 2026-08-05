#!/usr/bin/env python3
"""
swarm-flow settle-waiter — watch herdr worker sessions BY TAB LABEL and notify on a milestone.

Why label-based: herdr pane ids compact when tabs/panes close, so a stored pane id can silently
point at the wrong pane. This re-resolves label -> tab -> pane(s) -> status on every poll.

Usage:
    settle-waiter.py <workspace_id> <LABEL> [<LABEL> ...]

Runs in the background (exits on the first event, which re-invokes the orchestrator). It fires when:
  * ALL target labels are non-working ("done"/"idle") for 2 consecutive polls  -> "SETTLED", or
  * any single label stays "blocked" for ~2 min (past a typical grill/limit prompt) -> "STUCK".
Verify ground truth yourself after it fires (git / health / diff) — do not trust status alone.
"""
import json, subprocess, sys, time

POLL_SECS = 15
MAX_POLLS = 80          # ~20 min ceiling
STUCK_POLLS = 8         # ~2 min blocked => genuinely stuck (past quick prompts/limits)

def _herdr(*args):
    return subprocess.run(["herdr", *args], capture_output=True, text=True).stdout

def snapshot(ws, labels):
    """Return {label: agent_status} by resolving label->tab->pane fresh each poll."""
    tabs = json.loads(_herdr("tab", "list", "--workspace", ws))["result"]["tabs"]
    label_to_tab = {t.get("label"): t["tab_id"] for t in tabs}
    panes = json.loads(_herdr("pane", "list"))["result"]["panes"]
    by_tab = {}
    for p in panes:
        by_tab.setdefault(p.get("tab_id"), []).append(p.get("agent_status"))
    out = {}
    for lbl in labels:
        tid = label_to_tab.get(lbl)
        statuses = by_tab.get(tid, [])
        # a tab is "working" if any of its panes is working
        out[lbl] = "working" if "working" in statuses else (statuses[0] if statuses else "missing")
    return out

def main():
    if len(sys.argv) < 3:
        print("usage: settle-waiter.py <workspace_id> <LABEL> [<LABEL> ...]"); sys.exit(2)
    ws, labels = sys.argv[1], sys.argv[2:]
    settled_streak = 0
    blocked_streak = {l: 0 for l in labels}
    for _ in range(MAX_POLLS):
        time.sleep(POLL_SECS)
        try:
            cur = snapshot(ws, labels)
        except Exception:
            continue
        working = [l for l, s in cur.items() if s == "working"]
        # stuck detection (per label)
        for l in labels:
            blocked_streak[l] = blocked_streak[l] + 1 if cur.get(l) == "blocked" else 0
            if blocked_streak[l] == STUCK_POLLS:
                print("SWARM-WATCH STUCK: %s blocked ~2min — read it + route." % l); sys.exit(0)
        # settle detection (all non-working)
        if not working:
            settled_streak += 1
            if settled_streak >= 2:
                print("SWARM-WATCH SETTLED: " + json.dumps(cur)); sys.exit(0)
        else:
            settled_streak = 0
    print("SWARM-WATCH timeout (~20min); still working: " + ", ".join(working))

if __name__ == "__main__":
    main()
