---
name: pin-board
description: Render and manage the cross-session .pin-board task/decision DB for the current project — a file-per-item JSON "pinboard" of in-flight missions and (especially) deliberately postponed work / shortcuts / tech-debt. Use when the user asks "what's on the board", "what did we postpone / defer", "show progress", "what's left for <ticket>", "pin board", "pin-board", "/pin-board", or wants to know outstanding/deferred work across sessions. Also consult/update it autonomously when planning or implementing work that involves deferrals or shortcuts.
---

# Pin Board

A durable, cross-session task/decision DB at `<cwd>/.pin-board/` (override with the
`PIN_BOARD_DIR` env var or `--dir`) — one `<id>.json` per item, no central index,
derived on read. Full schema and rules live in that dir's `README.md`.

## Reading the board

Run the renderer (read-only). Prefer `/usr/bin/python3`:

```bash
python3 ~/.claude/skills/pin-board/render.py            # full board
python3 ~/.claude/skills/pin-board/render.py --status postponed
python3 ~/.claude/skills/pin-board/render.py --ticket TASK-1
python3 ~/.claude/skills/pin-board/render.py --type tech-debt
```

Filters combine. Output groups epics with their children, then standalone
decisions/deferrals, then a status summary. Items with a `due` (and not `done`)
surface in a "⏰ Upcoming deadlines" block at the top, soonest-first, with a
countdown (`⏳ 6d` / `⚠ OVERDUE 2d`).

## Maintaining the board (`pinboard.py`)

A subcommand CLI handles integrity, cleanup, and safe mutation so you don't
hand-edit JSON. Run `lint` at the start of a board session — it catches the
drift hand-editing causes (dangling links, orphaned parents, bad enums).

```bash
python3 ~/.claude/skills/pin-board/pinboard.py lint              # integrity report; exit 1 on errors
python3 ~/.claude/skills/pin-board/pinboard.py lint --stale-days 7
python3 ~/.claude/skills/pin-board/pinboard.py gc                # dry-run: list fully-done task subtrees
python3 ~/.claude/skills/pin-board/pinboard.py gc --execute      # ARCHIVE them → archive/ (never decisions/tech-debt)
python3 ~/.claude/skills/pin-board/pinboard.py set <id> status done --by <who>
python3 ~/.claude/skills/pin-board/pinboard.py set <id> due 2026-06-18     # 'due clear' removes it
python3 ~/.claude/skills/pin-board/pinboard.py link <id> blocks <other-id>
python3 ~/.claude/skills/pin-board/pinboard.py unlink <id> relatedTo <other-id>
```

- `lint` — ERRORS (id≠filename, bad type/status/rel enum, missing field, unparseable
  date, dangling link, orphaned/circular parent) · WARNINGS (past-due not-done,
  stale `in_progress`) · INFO (gc candidates, resolved decisions to drop).
- `gc` — **archives** (moves to `archive/`) only `epic`/`task`/`subtask` whose whole subtree
  is `done`; **never** `decision`/`tech-debt`/`shortcut` (lists those as manual-drop candidates).
  Archived pins stay recoverable under `<dir>/archive/` and are excluded from the live board /
  lint. Dry-run unless `--execute`.
- `set`/`link`/`unlink` — re-read + atomic write, auto-stamp `updatedAt`/`updatedBy` (`--by`, default `cli`).

## Writing to the board (do this autonomously while working)

Prefer `pinboard.py set/link/unlink` over hand-editing. Create new items as files
(the CLI doesn't create), then maintain them with the CLI.

- **New work:** create `<id>.json` per the README schema. Hierarchical ids
  (`TASK-1`, `TASK-1.1`), or `DEC-<slug>` for standalone decisions/deferrals.
  Check the filename doesn't already exist first.
- **Progress:** update the owning item's `status` + `updatedAt` + `updatedBy`.
- **Postponing something:** record it as its own item (`status: postponed`, a `note`
  explaining why + how to resume) and `links` it `relatedTo` its parent/ticket.
- **Self-management:** when an `epic`/`task`/`subtask` and all its children are `done`,
  **archive** it — move its file to `<dir>/archive/` (via `gc --execute`, or by hand),
  never delete. Archived pins stay recoverable and off the live board. NEVER auto-archive
  or delete `decision`/`tech-debt`/`shortcut` items — those are the pinboard rationale;
  they leave the live board only when the user resolves/drops them.
- **Concurrency:** several agents may use this DB at once. Only modify an item you own;
  re-read the file immediately before writing; always set `updatedBy`. Never bulk-rewrite.

## Notes

- `.pin-board/` is meant to be local and session-independent — if the project is a git
  repo, keep it untracked (e.g. via `.gitignore`) rather than committing it.
- This is separate from the in-session TaskCreate list (ephemeral, single session) and
  from `PLANS/` (human-authored plans). The board is the durable cross-session tracker.
