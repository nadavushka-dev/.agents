---
name: pinboard-retro
description: Run a retrospective on the PIN-BOARD SYSTEM ITSELF (schema, tooling, conventions) — not the day-to-day items, but how well the board+CLI serve the work — and drive concrete improvements over time. Use when the user says "/pinboard-retro", "pinboard retro", "pinboard retrospective", "improve the pinboard", "how is the pinboard working", or wants to evolve the board's schema/tooling. Gathers evidence (lint output, board shape, prior retro decisions, friction), decides improvements WITH the user, then ACTS — applies quick wins to the tooling and records larger ones as DEC-pinboard-* pins so the system's own evolution is tracked on the board.
---

# Pin-board Retro (system improvement)

A recurring retrospective whose subject is the **pin-board system**: its schema
(`.pin-board/README.md`), its tooling (the pin-board skill directory:
`render.py`, `pinboard.py`, `_common.py`), and the conventions around it. The
goal is to make the board serve the work better over time — not to groom
individual tasks (that's just `render.py`/`pinboard.py gc`).

This skill **acts**: small improvements are implemented in-session; larger ones
are captured as `DEC-pinboard-<slug>` pins (with a `due` if time-boxed) so the
board tracks its own evolution. Continuity across runs lives in a single
`DEC-pinboard-retro-log` pin.

**pin-board is a prerequisite.** If the pin-board tooling/skill is not installed or no `.pin-board` dir is resolvable, there is nothing to retro — tell the user and stop. Otherwise proceed.

Paths:
- Board dir: resolved by the pin-board tooling itself (`PIN_BOARD_DIR` env → `<cwd>/.pin-board` → `~/Code/.pin-board`)
- Tooling: `~/.claude/skills/pin-board/{render.py,pinboard.py,_common.py}`, `SKILL.md`

## 1. Open the retro — read continuity

```bash
cat <pinBoardDir>/DEC-pinboard-retro-log.json 2>/dev/null
python3 ~/.claude/skills/pin-board/render.py --type decision | grep -i pinboard
```

If `DEC-pinboard-retro-log` doesn't exist yet, this is the first retro — create
it at the end (step 5). Read the last retro date + which improvement pins were
opened, so this run builds on the last instead of repeating it.

## 2. Gather evidence (read-only)

Collect signals about how the system is performing — facts, not opinions:

```bash
python3 ~/.claude/skills/pin-board/pinboard.py lint            # recurring error CLASSES = schema/tooling signal
python3 ~/.claude/skills/pin-board/render.py                   # shape: counts by type/status, deadline pressure
```

Then look for friction patterns:
- **Recurring lint errors** — e.g. lots of dangling links ⇒ deletes should
  auto-scrub references; many bad timestamps ⇒ a field needs a stricter writer.
- **Stale `in_progress` / long `postponed`** (lint warns) — process signal, or a
  status the schema doesn't express well.
- **Open `DEC-pinboard-*` pins** — did prior retro improvements get done? Overdue?
- **Schema pressure** — facts repeatedly stuffed into `note` that deserve their
  own field (owner, priority, effort, blocked-reason).
- **CLI gaps** — operations done by hand because `pinboard.py` lacks a verb
  (e.g. item creation, bulk status, reparenting).
- **(optional, heavier)** scan recent transcripts under
  `~/.claude/projects/<escaped-project-path>/*.jsonl` (the escaped dir is the
  project's absolute path with `/` replaced by `-`) for "I had to
  hand-edit" / "the board didn't capture" moments. Only if the above is thin.

## 3. Synthesize candidate improvements

Turn evidence into a short list of concrete, scoped changes. Each candidate is
one of: **schema** (new field / enum value), **tooling** (new lint rule, CLI
verb, render change), **convention** (a rule in README/SKILL), or **process**
(how we use it). For each: the friction it removes + rough size (quick-win vs
backlog). Prefer few high-leverage changes over many speculative ones.

## 4. Decide WITH the user, then ACT

Present the candidates and get a decision on each (adopt now / backlog / drop).
Use AskUserQuestion when choices are non-obvious. Then:

- **Quick win (adopt now):** implement it. Schema → edit `.pin-board/README.md`
  + the relevant `_common.py` enums/helpers; tooling → edit
  `pinboard.py`/`render.py`; convention → edit `README.md`/`pin-board/SKILL.md`.
  Re-run `lint` after. Keep changes stdlib-only, surgical, and backward-compatible
  (render.py's documented invocation must keep working).
- **Backlog:** create a pin `DEC-pinboard-<slug>` (type `tech-debt` for
  tooling/schema debt, `decision` for a settled convention) via a JSON file, then
  `pinboard.py set <id> due <date>` if time-boxed and
  `pinboard.py link <id> relatedTo DEC-pinboard-retro-log`.
- **Drop:** note it in the retro log so it isn't re-raised every run.

Record meta-decisions as pins — never let "we decided to change X" live only in
chat. Apply all mutations through `pinboard.py` (atomic + stamped), not by hand.

## 5. Close — update the retro log + verify

Append this run to `DEC-pinboard-retro-log` (create it on first run): date,
evidence highlights, decisions (adopted / backlogged / dropped), and the pins
opened. Then:

```bash
python3 ~/.claude/skills/pin-board/pinboard.py lint    # must be clean (exit 0)
```

If any tooling changed, sanity-check `render.py` still renders. If a plan-sized
change was adopted, also record it wherever the project keeps its plans/docs.

## Cadence

On-demand. "Over time" means running it periodically — suggest the user pair it
with `/schedule` (e.g. monthly) or run it after a big board-heavy stretch. The
`DEC-pinboard-retro-log` `updatedAt` tells you how long since the last one.

## Guardrails

- Subject is the SYSTEM, not the tickets. Don't spend the retro grooming
  individual tasks — point at `pinboard.py gc` for that.
- Backward-compatible, stdlib-only tooling changes; never break `render.py`'s
  documented usage.
- Every decision becomes a pin. The retro improves the board by using the board.
