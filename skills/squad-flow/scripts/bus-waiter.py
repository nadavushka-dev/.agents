#!/usr/bin/env python3
"""
swarm-flow bus-waiter — PER-COMPLETION event stream off the status bus.

Why this exists (vs settle-waiter): settle-waiter fires only when ALL labels settle, which
turns a wave into a barrier — finished workers sit idle, un-verified, waiting on the slowest.
This watcher instead emits ONE line the moment each ticket's status-bus entry first turns
terminal, so the orchestrator can PIPELINE: verify+commit each worker as it lands while the
rest keep running.

Run it under the **Monitor** tool (each stdout line becomes one notification):
    Monitor(command="bus-waiter.py <status-dir> RND-1 RND-2 ...", ...)
It prints:
    DONE <ticket>       when the ticket's last status line is a success-terminal state
    BLOCKED <ticket>    when it's blocked (orchestrator should unblock / relay / batch)
and exits once every ticket is terminal (or after the ceiling), ending the watch.

Terminal states (last-line `state`): success = {code-complete, done, complete};
blocked = {blocked}; failure = {failed, error}. Emits each ticket exactly once.
Verify ground truth yourself after an event fires (git / tsc / diff) — the bus is a claim.
"""
import json, os, sys, time

POLL_SECS = 10
MAX_POLLS = 360          # ~60 min ceiling
SUCCESS = {"code-complete", "done", "complete"}
BLOCKED = {"blocked"}
FAILURE = {"failed", "error"}
TERMINAL = SUCCESS | BLOCKED | FAILURE


def last_state(path):
    try:
        with open(path) as f:
            lines = [l for l in f.read().splitlines() if l.strip()]
        if not lines:
            return None
        return (json.loads(lines[-1]).get("state") or "").strip().lower()
    except (OSError, ValueError):
        return None


def main():
    if len(sys.argv) < 3:
        print("usage: bus-waiter.py <status-dir> <ticket> [<ticket> ...]", file=sys.stderr)
        return 2
    status_dir, tickets = sys.argv[1], sys.argv[2:]
    emitted = set()
    for _ in range(MAX_POLLS):
        for t in tickets:
            if t in emitted:
                continue
            st = last_state(os.path.join(status_dir, f"{t}.jsonl"))
            if st in TERMINAL:
                tag = "BLOCKED" if st in BLOCKED else ("FAILED" if st in FAILURE else "DONE")
                print(f"{tag} {t} ({st})", flush=True)
                emitted.add(t)
        if len(emitted) == len(tickets):
            print(f"ALL-TERMINAL {len(tickets)} tickets", flush=True)
            return 0
        time.sleep(POLL_SECS)
    remaining = [t for t in tickets if t not in emitted]
    print(f"CEILING reached; still-open: {','.join(remaining)}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
