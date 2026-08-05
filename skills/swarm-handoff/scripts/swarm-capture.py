#!/usr/bin/env python3
"""
swarm-handoff PAUSE — harvest a live herdr swarm into a durable manifest.json
(+ a rendered SUPERVISOR-HANDOFF.md) so the workspace can be closed with zero
state lost and later resumed by swarm-relaunch.sh.

Usage:
    swarm-capture.py <workspace-id> [--out DIR] [--held-reason TEXT]
                     [--swarm NAME] [--not-done a,b,c] [--docs p1,p2]

What it harvests, per pane, from LIVE state:
  - agent type + resumable session id  <- `herdr pane get <pane>` .agent / .agent_session.value
  - git worktree/branch/HEAD/dirty     <- <repo>/.worktrees/<tab-label> across repos under project_root

It NEVER commits, merges, or touches worktrees. Dirty worktrees are flagged so
the caller can commit per-pin (swarm-flow/scripts/commit-pin.sh) before closing.
Tracker/pin updates are left to the SKILL.md procedure (project-specific).
"""
import argparse, json, os, re, subprocess, sys, datetime


def herdr(*args):
    """Run a herdr CLI command and return parsed result dict (or None)."""
    try:
        out = subprocess.run(["herdr", *args], capture_output=True, text=True, check=True).stdout
        return json.loads(out).get("result", {})
    except (subprocess.CalledProcessError, json.JSONDecodeError, FileNotFoundError) as e:
        print(f"herdr {' '.join(args)} failed: {e}", file=sys.stderr)
        return None


def git(repo, *args):
    try:
        return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, check=True).stdout.strip()
    except subprocess.CalledProcessError:
        return None


# Untracked build/dep dirs are not "uncommitted work" — every Piqk worktree has a
# node_modules, so counting them would make `dirty` always-true and hide real edits.
EPHEMERAL = {"node_modules", ".next", "dist", "__pycache__", ".turbo", "coverage"}


def is_dirty(wt):
    """True only for REAL uncommitted work (tracked changes or untracked non-ephemeral files)."""
    for line in (git(wt, "status", "--porcelain") or "").splitlines():
        if not line.strip():
            continue
        code, path = line[:2], line[3:].strip().rstrip("/")
        if code == "??" and os.path.basename(path) in EPHEMERAL:
            continue
        return True
    return False


def discover_repos(root):
    """Immediate subdirs of root that are git repos."""
    repos = []
    for name in sorted(os.listdir(root)):
        p = os.path.join(root, name)
        if os.path.isdir(os.path.join(p, ".git")):
            repos.append(p)
    return repos


def worktrees_for(label, repos):
    """Find <repo>/.worktrees/<label> across repos; record branch/head/dirty."""
    found = []
    for repo in repos:
        wt = os.path.join(repo, ".worktrees", label)
        if os.path.isdir(wt):
            found.append({
                "repo": os.path.basename(repo),
                "path": wt,
                "branch": git(wt, "branch", "--show-current") or "",
                "head": git(wt, "rev-parse", "--short", "HEAD") or "",
                "dirty": is_dirty(wt),
            })
    return found


def collect_sessions(ws, repos, current_pane):
    """Enumerate tabs -> panes -> agent/session, mapping worktrees by tab label."""
    tabs = herdr("tab", "list", "--workspace", ws) or {}
    tab_label = {t["tab_id"]: t.get("label", t["tab_id"]) for t in tabs.get("tabs", [])}
    panes_res = herdr("pane", "list", "--workspace", ws) or {}
    panes = panes_res.get("panes") or panes_res.get("items") or []
    sessions = []
    for p in panes:
        pane_id = p.get("pane_id")
        if not pane_id:
            continue
        info = (herdr("pane", "get", pane_id) or {}).get("pane", {})
        agent = info.get("agent")
        sess = (info.get("agent_session") or {}).get("value")
        label = tab_label.get(info.get("tab_id"), pane_id)
        row = {
            "label": label,
            "agent": agent,
            "session_id": sess,
            "worktrees": worktrees_for(label, repos),
        }
        if pane_id == current_pane:
            row["role"] = "conductor"
        sessions.append(row)
    # orchestrator (current pane) first
    sessions.sort(key=lambda s: s.get("role") != "conductor")
    return sessions


HANDOFF_TMPL = """# {swarm} — Supervisor Handoff (swarm-handoff)

Captured {captured_at}. The swarm is **paused** — workspace can be closed; nothing is lost.
This file + `manifest.json` let the next supervisor stand the exact squad back up.

## Where things stand
Held reason: **{held_reason}**. Deliberately NOT done yet: {not_done}. Nothing merged without explicit human go.

## What survives a workspace close (durable, on disk)
- **Code** — commits on the feature branches below (git is untouched by closing herdr).
- **Agent memory** — each session transcript persists; resume-by-id restores full context.
- **Docs** — this handoff + `manifest.json` + the pointers under "Map".
- **Worktrees** — stay on disk.

## Squad table
| Tab label | Agent | Resume session ID | Repo · branch @ HEAD (dirty?) |
|---|---|---|---|
{rows}

> All sessions belong to cwd `{project_root}` — resume from there or the transcript won't be found.

## Relaunch (one command)
```bash
bash {relaunch_sh} {swarm}      # or: bash {relaunch_sh} --list   (see all parked swarms)
```
Recreates a workspace labeled **{swarm}**, one tab per session, and resumes each agent by id
(claude `--resume`, codex `resume`). A session whose transcript is gone launches FRESH — re-fire its brief.

## Map (read on resume)
{docs}

## Your job when the spec changes
1. Relaunch (above). 2. Re-pull the updated spec sources. 3. Diff vs the current build. 4. Re-brief ONLY
the affected worker(s) into their resumed session (they still remember their code). 5. Re-verify changed
pieces. 6. Then the held steps, on explicit human go only.

## Warnings (do not relearn)
- Resume needs the original cwd (`{project_root}`); briefs use ABSOLUTE paths (workers cd into worktrees).
- herdr pane ids are non-durable — re-resolve label→pane each time; never cache them.
- codex resume flag position can error → fallback `codex resume <id>`.
- Verify cross-repo seams yourself — per-repo tsc passes independently yet misses mismatches.
- Never merge to main / move the tracker without explicit human instruction.
- Safe worktree cleanup only (`git worktree remove`); never `rm -rf` a worktree path.
- Do not build in a live-served worktree (see project CLAUDE.md for env specifics).
"""


def render_handoff(m, relaunch_sh):
    rows = []
    for s in m["sessions"]:
        wts = s.get("worktrees") or []
        if wts:
            wt = "; ".join(f"{w['repo']} · {w['branch']} @ {w['head']}"
                            + (" **DIRTY**" if w.get("dirty") else "") for w in wts)
        else:
            wt = "— (conductor)" if s.get("role") == "conductor" else "—"
        rows.append(f"| {s['label']} | {s.get('agent')} | `{s.get('session_id') or 'n/a'}` | {wt} |")
    docs = "\n".join(f"- `{d}`" for d in m.get("docs", [])) or "- (none recorded)"
    return HANDOFF_TMPL.format(
        swarm=m["swarm"], captured_at=m["captured_at"], held_reason=m["held_reason"],
        not_done=", ".join(m.get("not_done", [])) or "(none)",
        rows="\n".join(rows), project_root=m["project_root"],
        relaunch_sh=relaunch_sh,
        docs=docs,
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("workspace")
    ap.add_argument("--out", help="optional dir to ALSO drop a human-readable "
                    "SUPERVISOR-HANDOFF.md (e.g. the swarm's _research/<name>/). The machine "
                    "manifest ALWAYS registers under <root>/.swarm-handoff/<swarm>/ "
                    "(override root with $SWARM_HANDOFF_ROOT).")
    ap.add_argument("--held-reason", default="paused by supervisor")
    ap.add_argument("--swarm")
    ap.add_argument("--not-done", default="")
    ap.add_argument("--docs", default="")
    ap.add_argument("--close", action="store_true",
                    help="on a successful, clean capture, close the herdr workspace (pause = "
                    "capture + walk away). Refuses to close if any worktree has real uncommitted work.")
    a = ap.parse_args()

    if not os.environ.get("HERDR_ENV"):
        print("Not inside herdr (HERDR_ENV unset) — nothing to capture.", file=sys.stderr)
        return 1

    ws = a.workspace
    ws_meta = herdr("workspace", "get", ws) or {}
    ws_label = (ws_meta.get("workspace") or {}).get("label") or a.swarm or ws
    current_pane = os.environ.get("HERDR_PANE_ID")

    # project_root: cwd of the current pane (falls back to first pane / cwd)
    cur = (herdr("pane", "get", current_pane) or {}).get("pane", {}) if current_pane else {}
    project_root = cur.get("cwd") or os.getcwd()
    repos = discover_repos(project_root)

    sessions = collect_sessions(ws, repos, current_pane)
    if not sessions:
        print("no panes found in workspace", file=sys.stderr)
        return 1

    swarm = a.swarm or ws_label
    manifest = {
        "swarm": swarm,
        "workspace_label": ws_label,
        "project_root": project_root,
        # Claude escapes the project cwd into its transcript dir by replacing every
        # non-alphanumeric char (/, ., _, space, ...) with '-'. Match that exactly.
        "transcript_slug": re.sub(r"[^A-Za-z0-9]", "-", project_root),
        "captured_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "held_reason": a.held_reason,
        "not_done": [x.strip() for x in a.not_done.split(",") if x.strip()],
        "docs": [x.strip() for x in a.docs.split(",") if x.strip()],
        "sessions": sessions,
    }

    # Machine manifest ALWAYS lands in the canonical registry so resume can find every
    # parked swarm in one place. $SWARM_HANDOFF_ROOT overrides the default location.
    reg_root = os.environ.get("SWARM_HANDOFF_ROOT") or os.path.join(project_root, ".swarm-handoff")
    registry_dir = os.path.join(reg_root, swarm)
    os.makedirs(registry_dir, exist_ok=True)
    mpath = os.path.join(registry_dir, "manifest.json")
    with open(mpath, "w") as f:
        json.dump(manifest, f, indent=2)

    relaunch_sh = os.path.join(os.path.dirname(os.path.abspath(__file__)), "swarm-relaunch.sh")
    handoff = render_handoff(manifest, relaunch_sh)
    with open(os.path.join(registry_dir, "SUPERVISOR-HANDOFF.md"), "w") as f:
        f.write(handoff)
    # Optional human-facing copy of the handoff doc in the swarm's own docs dir.
    if a.out and os.path.abspath(a.out) != os.path.abspath(registry_dir):
        os.makedirs(a.out, exist_ok=True)
        with open(os.path.join(a.out, "SUPERVISOR-HANDOFF.md"), "w") as f:
            f.write(handoff)

    dirty = [f"{w['repo']}:{w['path']}" for s in sessions for w in (s.get("worktrees") or []) if w.get("dirty")]
    print(f"captured {len(sessions)} sessions -> {mpath}")
    print(f"handoff -> {os.path.join(registry_dir, 'SUPERVISOR-HANDOFF.md')}"
          + (f" (+ copy in {a.out})" if a.out and os.path.abspath(a.out) != os.path.abspath(registry_dir) else ""))
    print(f"resume with: bash {relaunch_sh} {swarm}    # or --list to see all parked")
    if dirty:
        print("\nWARNING — uncommitted work in worktrees (commit per-pin before closing, "
              "e.g. swarm-flow/scripts/commit-pin.sh):", file=sys.stderr)
        for d in dirty:
            print(f"  DIRTY {d}", file=sys.stderr)

    if a.close:
        if dirty:
            print("\nNOT closing workspace — commit the DIRTY worktrees above first, "
                  "then re-run with --close.", file=sys.stderr)
            return 3
        print(f"\nclosing workspace {ws} — safe to walk away. resume: bash {relaunch_sh} {swarm}")
        herdr("workspace", "close", ws)   # ends this workspace (incl. the orchestrator pane); state already persisted
    return 0


if __name__ == "__main__":
    sys.exit(main())
