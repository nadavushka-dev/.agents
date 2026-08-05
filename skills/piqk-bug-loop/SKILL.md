---
name: piqk-bug-loop
description: Autonomous 5-seat bug-fixing fleet for the Piqk RND board. Keeps up to 5 /solve-bug sessions (override with PIQK_BUG_LOOP_SEATS) running in parallel — one per bug assigned to you and in To Do — topping the pool up as bugs merge or park. Use when the user says "/piqk-bug-loop", "start the bug loop", "run the bug fleet", "resume/stop the bug loop", or wants the merge-gated bugfixer pool. Meant to be driven on an interval (via /loop) but a single cycle can be run on demand.
---

# piqk-bug-loop — merge-gated bugfixer pool (default 5 seats)

Run a fleet of autonomous `/solve-bug` sessions over the Piqk RND board, capped at
**`SEATS` concurrent seats (default 5)**. Each seat is a heavyweight session (its own
`next dev` + Playwright browser + Claude process), so the cap is a RAM ceiling — the
old default of 8 OOM-killed the host (44 GB peak on a 60 GB box). Each cycle: free
seats whose bug has merged or parked, then fill the free seats with the next To Do bugs.

## THE ONE HARD RULE (do not violate)

**You NEVER change a ticket's Jira status. The `/solve-bug` skill owns all
transitions** — it moves the ticket `To Do → In Progress` when it starts, and
merges + moves it onward when done. This loop is **status-read-only**: it only
*queries* status for seat accounting and *spawns* `/solve-bug` sessions. Never
POST a Jira transition from this loop.

## Config (defaults)

- **Seat cap:** `SEATS` concurrent bugfixers, **default 5**. Resolve it once at the top of every cycle from the environment: `SEATS=${PIQK_BUG_LOOP_SEATS:-5}`. To run a bigger/smaller fleet, export `PIQK_BUG_LOOP_SEATS=<n>` before starting the loop (or set it in the `/loop`/cron environment). Everywhere below that says "seats" or a seat number refers to this resolved `SEATS` value — never hardcode a number. Raising it above ~5 risks OOM-killing the host (see the header note).
- **Candidate queue (JQL):** `assignee = currentUser() AND issuetype = Bug AND status = "To Do" ORDER BY created ASC` — bugs assigned to the caller, in To Do, **oldest first (FIFO)**.
- **Spawn command:** `cld48` — an interactive-zsh alias = `claude --model claude-opus-4-8 --dangerously-skip-permissions`. `herdr pane run` uses interactive zsh, so the alias resolves. (Falls back: `claude --model claude-opus-4-8 --dangerously-skip-permissions` if `cld48` is undefined.)
- **herdr board (single workspace `BUG-FIXES`):** the loop keeps **one** workspace holding **only live In-Progress fixer tabs**. New `/solve-bug` tabs are created here; when a fixer's bug is **done or parked On Hold, its tab is CLOSED, not moved** (see the sweep) — closing frees the seat's RAM. There is deliberately **no `BUGS-DONE` / `BUGS-ON-HOLD` workspace**: the durable record of a finished/parked fixer lives in its **`.runs/<KEY>-*.json`** report — which carries `session` = the fixer's claude session id, so you can reopen it any time with **`claude --resume <session>`** — plus the **Jira** ticket (status + evidence comment + PR links) and the on-disk **transcript**. Nothing is lost by closing. Resolve `BUG-FIXES` by its **label** via `herdr workspace list` each cycle; **create it if missing** with `herdr workspace create --label "BUG-FIXES" --no-focus`. NEVER hardcode herdr ids (`w1K`, …) — they are not stable; always look them up by label. Requires `HERDR_ENV=1`.
- **Marker dir (dedup, persists across sessions):** `~/.piqk-bug-loop/dispatched/` — one `<KEY>.dispatched` file per dispatched bug. Create it if missing.
- **Jira access:** REST via curl (the claude.ai Atlassian MCP is unreliable / times out). Load creds once per cycle: `set -a; source ~/.local/secrets.env; set +a` → `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`. Use MCP read only if curl fails.

## Seat model

- A dispatched bug **OCCUPIES** a seat while its Jira status is exactly **`In Progress`**.
- A seat **FREES** the moment the bug's status becomes **`Waiting For Deployment To QA ENV`** (merged), **`On Hold`** (skill parked it), or anything past merge — **even if its session/tab is still open.**
- `occupied = count(dispatched markers whose live status == "In Progress")`; `free = SEATS − occupied`. Never exceed `SEATS`.

## One cycle

Run these steps for a single tick:

1. **Ensure the board.** `herdr workspace list`; resolve `BUG-FIXES` by label. Create it if missing with `herdr workspace create --label "BUG-FIXES" --no-focus`. Keep its resolved id for this cycle only.
2. **Status.** Read every `<KEY>` from marker filenames in the marker dir. Batch-query live status via REST (`jql=key in (<all keys>)`, `fields=status`, `maxResults=200`).
3. **Sweep — close freed seats (do NOT move tabs).** List RND-labelled tabs in `BUG-FIXES` (with their tab + pane ids). For each whose live Jira status is **no longer `In Progress`** — i.e. `On Hold`, or `Waiting For Deployment To QA ENV` / any past-merge status (Awaiting TL Merge / QA / Code Review / Done) — **CLOSE its tab to free the seat and its RAM**, but only once its agent has actually finished:
   - **Gate on idle.** Confirm the fixer is done working, not mid-finalization: `herdr agent wait <pane> --until idle --until done --timeout 3000` (or `herdr agent get <pane>`). If it's still `working` (e.g. still writing its run report / Jira comment), **leave the tab this cycle** — it'll be swept next tick. Never close a `working` agent.
   - **Close.** `herdr tab close <tabId>`. This kills the tab's whole process tree in one shot — the `claude` session, its `--rm` `mcp-atlassian` docker child, and any `next dev` — which is the RAM the fleet must reclaim. Nothing recoverable is lost: the fixer already persisted its outcome to `.runs/<KEY>-*.json` (with `session` for `claude --resume`), Jira, and its on-disk transcript.
   After this, `BUG-FIXES` holds only live In-Progress fixers.
4. **Occupancy.** `occupied` = markers whose status == `In Progress`. `free = SEATS − occupied`. Never exceed `SEATS`.
5. **Full?** If `free <= 0`: report `pool full (SEATS/SEATS occupied)` (with the actual number) plus the in-progress keys, and STOP (after sweeping).
6. **Candidates.** Only if `free > 0`: run the candidate JQL (READ ONLY). Skip any key that already has a marker.
7. **Dispatch** the first `free` candidates, oldest-first. For each `<KEY>` — **without transitioning it** (the skill does that):
   a. Create a new tab labeled `<KEY>` **in `BUG-FIXES`**, spawn `cld48`, then **wait for the claude TUI to be ready** with `herdr wait output <pane> --match "bypass permissions" --timeout 45000` (do NOT use `agent_status idle` — a fresh shell reports idle before claude's prompt accepts input). Run `/solve-bug <KEY>` (via `herdr pane run`) with the URL `https://leverate.atlassian.net/browse/<KEY>`. **Then read the pane back; if the command is still sitting unsent in the input box, send a bare Enter (`herdr pane send-keys <pane> Enter`)** — the initial Enter can race the TUI on fresh boot. Confirm a spinner/activity appeared.
   b. Write `~/.piqk-bug-loop/dispatched/<KEY>.dispatched` containing the timestamp + pane id.
8. **Report** (tight): closed→DONE (keys), closed→ON-HOLD (keys), left-to-finalize (keys still `working`, not yet closed), newly dispatched (keys + panes), occupied-now (`X/SEATS`), candidates still waiting.

## Starting / stopping (interval mode)

This loop is meant to run every ~5 minutes. Drive it with the `/loop` skill:

- **Start:** invoke `/loop 5m <the one-cycle prompt below>` (or schedule a CronCreate `*/5 * * * *` with the one-cycle prompt). Then run cycle 1 immediately.
- **Stop:** `CronDelete` the job. Stopping the loop only halts new dispatches — in-flight `/solve-bug` sessions keep running.
- On **resume**, occupancy is recomputed live from Jira status, so the seat math self-corrects (no double-counting, no over-fill).

### One-cycle prompt to schedule

```
[piqk-bug-loop cycle] Follow ~/.claude/skills/piqk-bug-loop/SKILL.md. NEVER transition a ticket
(the /solve-bug skill owns status). REST read-only via curl (creds ~/.local/secrets.env).
Marker dir ~/.piqk-bug-loop/dispatched/. Seat cap SEATS=${PIQK_BUG_LOOP_SEATS:-5} (resolve at
cycle start). Occupied = dispatched markers whose live Jira status == "In Progress"; a seat frees
on "Waiting For Deployment To QA ENV" / "On Hold" / past-merge.
BOARD: single herdr workspace BUG-FIXES (live In-Progress fixers only) resolved by label (herdr
workspace list); create if missing (herdr workspace create --label "BUG-FIXES" --no-focus); never
hardcode ids. NO BUGS-DONE/BUGS-ON-HOLD workspace — the done/parked record lives in .runs/<KEY>-*.json
(has `session` for `claude --resume`) + Jira + transcript.
SWEEP (close, don't move): for each RND tab in BUG-FIXES whose Jira status != In Progress (On Hold /
Waiting For Deployment To QA ENV / past-merge), if its agent is finished (herdr agent wait <pane>
--until idle --until done --timeout 3000; skip & leave if still `working`), CLOSE the tab
(herdr tab close <tabId>) to free the seat + its RAM (kills claude + its --rm mcp docker + next dev).
Then recompute occupancy.
Candidate JQL: assignee = currentUser() AND issuetype = Bug AND status = "To Do" ORDER BY created ASC.
If free>0, for each of the first `free` fresh candidates (oldest-first): open a herdr tab labeled
<KEY> IN BUG-FIXES, spawn `cld48`, wait output --match "bypass permissions", run `/solve-bug <KEY>`
with URL https://leverate.atlassian.net/browse/<KEY> (send a bare Enter if it didn't submit), write
a marker. Report closed-to-DONE / closed-to-ON-HOLD / left-to-finalize / newly-dispatched / occupied
X/SEATS / candidates waiting. Never exceed SEATS; never dispatch more than `free`; oldest-first.
```

## Notes & gotchas

- **herdr required** (`HERDR_ENV=1`). Verify before running; if unset, say so and stop.
- **zsh word-splitting:** unquoted `$var` does NOT split in zsh. In loops, use explicit arrays or `python3` to parse `herdr` JSON — don't rely on `set -- $x`.
- **Spawn readiness (IMPORTANT):** `agent_status idle` is UNRELIABLE for a fresh `cld48` boot — it reports `idle` before claude's prompt accepts input, so the `/solve-bug` command gets typed but never submitted (it sits in the input box). Instead: `herdr wait output <pane> --match "bypass permissions"`, send the command, then **read back and send a bare `Enter` if it's still unsent**. Do this per-pane even when spawning several at once.
- **On Hold is expected** — the autonomous `/solve-bug` parks anything too-doubtful-to-auto-merge On Hold with a Jira comment. That frees the seat and the pool flows on. To retry a parked bug later, it must be back in To Do (the skill/user handles that) and its marker cleared.
- **Dedup:** a bug with a marker is skipped as already-dispatched. Clear its marker to make it eligible again (e.g., after it's moved back to To Do for a re-run).
- **Legacy note:** older "Waiting Merge to version" tickets (a pre-merge PR-gate state from an earlier /solve-bug version) don't occupy seats and are not touched here; they're a separate manual-merge backlog.
