---
name: swarm-handoff
description: >-
  Pause a running herdr multi-agent swarm — capture every worker's agent session
  id, branch, worktree, and a supervisor handoff into a manifest — so the
  workspace can be closed with zero state lost, and later RESUME it (relaunch
  each agent by session id with full memory, one command). Use when the user
  wants to "pause / checkpoint / capture the swarm", "close the workspace and
  resume later", "relaunch / stand back up the paused sessions", "/swarm-handoff".
  Companion to swarm-flow (which builds the swarm); complements piqk-takeover
  (cold forensic recovery when there is NO manifest). Requires herdr (HERDR_ENV=1).
  HUMAN-INVOKED ONLY — run solely on an explicit user request (/swarm-handoff or
  "pause/resume the swarm"); never auto-invoke.
disable-model-invocation: true
---

# swarm-handoff — pause & resume a herdr swarm

A `swarm-flow` run is N long-lived agent sessions in a herdr workspace, each on its own
worktree/branch. This skill lets you **suspend** that whole topology (close the workspace, walk away)
and later **resume** it exactly — agents relaunched by session id so they still remember what they
built. The single source of truth is a `manifest.json`; PAUSE writes it, RESUME reads it, the
handoff doc renders from it.

## When to use
- A live swarm needs to stop for a while (blocked on a decision, incoming spec changes, end of day) and you want it back later intact.
- You want a durable, human-readable record of a swarm's topology + how to stand it up.

## When NOT to use
- `HERDR_ENV` unset → no session substrate; stop and say so.
- There is NO manifest and sessions are orphaned/crashed → that's **cold forensic recovery**: use `piqk-takeover`, not this.
- You just want to build/spawn a swarm → that's `swarm-flow`.

## The one invariant
**Resume by session id needs the original project cwd.** Every relaunch tab is opened with
`--cwd <project_root>` (the dir the sessions were created in) or the transcript is not found and the
agent comes back empty. The manifest records `project_root`; never resume from elsewhere.

---

## PAUSE (capture)
Run while the swarm is still live, before closing anything.

1. **Preflight.** Confirm `HERDR_ENV=1`. Identify the target workspace id (the current one, or resolve by label via `herdr workspace list`).
2. **Capture (and close on success).** Run the harvester with `--close`:
   ```bash
   scripts/swarm-capture.py <workspace-id> --close --out <swarm-docs-dir> \
       --swarm <NAME> --held-reason "<why>" --not-done "merge,e2e,tracker" \
       --docs "<abs plan>,<abs contracts>,<abs briefs dir>"
   ```
   `--close` closes the herdr workspace once the capture succeeds cleanly (pause = capture + walk
   away) — this also ends the orchestrator's own session, which is fine: it's captured and resumes by
   id like any worker. **It refuses to close if any worktree has real uncommitted work** (see step 3),
   so nothing is lost. Omit `--close` if you want to inspect before closing.
   It reads each pane (`herdr pane get` → agent + `agent_session.value`), maps each tab label to
   `<repo>/.worktrees/<label>` across the repos under `project_root` (branch/HEAD/dirty), and writes
   `manifest.json` + a rendered `SUPERVISOR-HANDOFF.md`. **The manifest always registers in the single
   canonical location `<project_root>/.swarm-handoff/<swarm>/`** (override with `$SWARM_HANDOFF_ROOT`) so
   resume can find every parked swarm in one place. `--out` is optional and only drops an extra
   human-readable copy of the handoff doc in the swarm's own docs dir (e.g. `_research/<swarm>/`).
3. **Uncommitted work.** If the harvester flags a `DIRTY` worktree it will NOT close — commit each
   pin's green work on its feature branch first (reuse `~/.claude/skills/swarm-flow/scripts/commit-pin.sh`;
   never auto-commit silently, never a red pin), then re-run capture with `--close` so HEADs are current.
   (`dirty` counts only real work — untracked `node_modules`/`.next`/`dist` are ignored.)
4. **Tracker.** Record the pause on the project tracker per its own convention (read the project
   CLAUDE.md). On Piqk: set the epic `.pin-board` item → `status: blocked`, `blocked_on`, and a `note`
   that points at the handoff + inlines the branch/HEAD manifest. Do not invent tracker fields.
5. **Confirm.** With `--close` the workspace is already down; report what was captured + the one-line
   resume command (`swarm-relaunch.sh <swarm>`). Without `--close`, tell the user it's safe to close.

## RESUME (relaunch)
1. **Pick the swarm — list, don't guess.** Show the human what's parked and let them choose by name:
   ```bash
   bash scripts/swarm-relaunch.sh --list      # name · captured · #sessions · held-reason
   ```
   If nothing is parked → this is a cold case: use `piqk-takeover`, not this skill.
2. **Relaunch** by name (or bare when exactly one is parked — never silently pick among several):
   ```bash
   bash scripts/swarm-relaunch.sh <swarm-name>
   ```
   Creates a fresh workspace labeled after the swarm, one tab per session (`--cwd project_root`,
   `--no-focus`), and resumes each agent by id. A session whose transcript is gone launches FRESH and
   is reported — re-fire that worker's brief. (An explicit `manifest.json` path also works.)
3. **Re-orient.** In the orchestrator tab, read the `SUPERVISOR-HANDOFF.md` + the tracker pin. If the
   spec changed while paused: re-pull the spec sources, diff against the current build, and re-brief
   ONLY the workers whose scope moved (this is where `swarm-flow` re-engages) — don't rebuild untouched
   workers. The held steps (browser/e2e verify, merge, tracker transition) stay gated on explicit human go.

---

## manifest.json schema
```jsonc
{
  "swarm": "RND-1019", "workspace_label": "RND-1019",
  "project_root": "/Users/.../piqk", "transcript_slug": "-Users-...-piqk",
  "captured_at": "<iso>", "held_reason": "...", "not_done": ["merge","e2e"],
  "docs": ["<abs handoff/plan/contracts/briefs>"],
  "sessions": [                                   // conductor first
    { "label":"orchestrator","agent":"claude","session_id":"<uuid>","role":"conductor","worktrees":[] },
    { "label":"W-STATUS","agent":"codex","session_id":"<uuid>","brief":"<abs>",
      "worktrees":[{"repo":"piqk-server","path":"<abs>","branch":"feature/W-STATUS","head":"80a735d","dirty":false}] }
  ]
}
```
Multi-repo workers = multiple `worktrees[]`. `dirty` drives the uncommitted-work warning.

## herdr cheatsheet (session id + relaunch)
```bash
herdr workspace list                                   # find the workspace id/label
herdr pane get <pane> | python3 -c "import sys,json;print(json.load(sys.stdin)['result']['pane']['agent_session']['value'])"  # the resumable session id
herdr workspace create --label <L> --cwd <root> --no-focus     # -> result.workspace_id
herdr tab create --workspace <ws> --label <L> --cwd <root> --no-focus  # -> result.root_pane.pane_id
herdr pane run <pane> "claude --dangerously-skip-permissions --resume <id>"
herdr pane run <pane> "codex --dangerously-bypass-approvals-and-sandbox resume <id>"   # fallback: codex resume <id>
```
Pane ids are non-durable — re-resolve label→pane each time; never cache them. Transcripts:
claude `~/.claude/projects/<transcript_slug>/<id>.jsonl`; codex resolves its own store by id.

## Hard rules
1. **Resume from the original `project_root`** — the cwd invariant (above). The scripts enforce `--cwd`.
2. **Never merge to main / transition the tracker on resume** without explicit human instruction. Pause records held state; resume does not un-hold it.
3. **Commit before you close, don't lose it.** Dirty worktrees get a per-pin commit first; capture never commits for you.
4. **The manifest is the source of truth.** Regenerate the handoff/pin from it; never hand-maintain the session table in parallel.
5. **Safe worktree cleanup only** — `git worktree remove <path>`; never `rm -rf` a worktree; branches (the code) survive a workspace close regardless.
6. **No manifest → not this skill.** Orphaned/crashed sessions with no capture are `piqk-takeover`'s job.

## Bundled helpers
- `scripts/swarm-capture.py <ws>` — PAUSE: live herdr+git → `manifest.json` + `SUPERVISOR-HANDOFF.md`.
- `scripts/swarm-relaunch.sh [--list | <swarm-name> | <manifest.json>]` — RESUME: list parked swarms, or relaunch one → workspace + tabs + resumed agents.
- Reuse (not bundled): `swarm-flow/scripts/commit-pin.sh` (dirty-worktree commits); `piqk-takeover` (cold fallback).

## Boundaries
- **swarm-flow** builds and drives; **swarm-handoff** suspends/restores what it built; **piqk-takeover** reconstructs from scratch when there's no manifest. **worktree-mode** owns single-worktree create/resume — this skill records worktrees but never mutates them.
