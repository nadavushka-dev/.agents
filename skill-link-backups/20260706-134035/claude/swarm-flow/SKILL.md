---
name: swarm-flow
description: >-
  Orchestrate parallel, delegated development across many agent sessions — ONE human-facing
  orchestrator mediating N worker sessions (one per ticket/task; they need NOT be in the same
  epic), with an async human decision gate, per-session code review, and verify-before-merge.
  Use when the user wants to run several tickets/tasks in parallel through delegated sessions
  with a single point of contact — e.g. "swarm-flow", "/swarm-flow", "delegate these tickets",
  "run these in parallel as sessions", "orchestrate this across sessions", "spin a session per
  ticket". Project-agnostic: reads project specifics (repos, dev env, deploy, tracker) from the
  project's own CLAUDE.md / skills — do NOT hardcode them here. Requires a herdr-managed terminal
  (HERDR_ENV=1). Optional but recommended: the `hunk` CLI for changeset review.
---

# swarm-flow — parallel delegated development, one human-facing conductor

You (this session) become the **Orchestrator**: the single surface the human talks to, mediating
many worker sessions. The human deals with one conversation; you deal with the swarm.

## When to use
- 3+ tickets/tasks that can progress in parallel (same epic or not).
- The human wants a single point of contact + the ability to drop into any session for detail.

## When NOT to use
- A single task, or work that's inherently sequential with no parallelism.
- Trivial/mechanical changes (just do them).
- No herdr (`HERDR_ENV` unset) → you have no session substrate; stop and say so.

## The one invariant
**The Orchestrator never implements.** You do recon, planning, delegation, mediation,
verification-sequencing, and bookkeeping. Code is written by worker sessions. If you catch
yourself editing feature code, you've drifted out of role.

## Roles (spin each as its own herdr session unless noted)
```
Human (Product / Architect)   decisions · irreversible approvals · priorities · talks ONLY to ↓
Orchestrator (you)            recon→plan→decision-brief · delegate · mediate · sequence · bookkeep
  ├─ Recon agents             EPHEMERAL, read-only fan-out → Agent-tool subagents, NOT herdr panes
  ├─ Worker sessions          1 per ticket (herdr tab, labeled by ticket key)
  ├─ Integrator               owns merges/rebases to main (kills shared-file races + rebase churn)
  ├─ Reviewer                 independent code review of each diff (branch-code-reviewer / pr-review-toolkit)
  ├─ Verifier                 owns spinning envs + running e2e/tests (decouples verify from the human)
  └─ Infra/Tooling            env & tooling health; fixes cross-cutting infra bugs
```
For small runs, the Orchestrator may play Integrator/Reviewer/Verifier itself — but keep the
*independent-reviewer* property (never let a worker be the sole reviewer of its own diff).

## Tool selection
| Use a **herdr pane/tab** | Use an **Agent-tool subagent** / **Workflow tool** |
|---|---|
| long-lived, interactive, human might watch/intervene | ephemeral, read-only or self-contained |
| needs its own terminal/services (dev server, e2e) | result aggregates back to you |
| worker / integrator / verifier / infra | recon fan-out, quick lookups, adversarial verify |
Workflow tool = deterministic headless fan-out for the *mechanical* phases (recon, review-fan-out);
herdr = the long-lived sessions you want eyes on. They compose; neither replaces the other.

## The 7 phases

1. **Recon** — fan out read-only subagents (one per ticket/subsystem), GK/codebase-first. Each
   returns: what exists, gaps, exact touch points, reuse, open questions. Aggregate to you.
2. **Plan** — synthesize: **collision map** (shared files edited by >1 ticket), **dependency graph**
   (hard vs soft), **waves**, and a **decision register** (every open architectural call + a
   recommendation + blast radius). Save it as a durable plan doc.
3. **DECIDE — human gate (blocking, NO timeout).** See Hard Rule #1. Batch every architectural
   decision to the human at once; wait. Do not fan out to build until ratified.
4. **Foundation** — land shared prerequisites FIRST on a stable main (god-file refactors, shared
   modules, cross-service bridges), so workers branch off a stable base and stop colliding.
5. **Build** — one worker per ticket in its own herdr tab (labeled by ticket key), branched off the
   stabilized main. Give each a **structured brief** (below). **Spawn is an atomic 3-tuple, fire all
   together:** (a) create the pin/tracker item `in_progress`, (b) **transition the tracker ticket →
   In Progress**, (c) launch the session. Do NOT leave tickets in To Do while their work is underway
   (Hard Rule #10).
6. **Verify + Review + Integrate** — **pipeline, don't barrier.** Process each worker the moment IT
   reaches a terminal state, not when the whole wave settles (see `scripts/bus-waiter.py` + Hard
   Rule #6). Per ticket, before merge: (a) **Reviewer** agent reviews the diff (independent) →
   blocking findings; (b) **hunk** review surface for the human on diffs that matter; (c) **Verifier**
   runs e2e/tests; (d) **Integrator** merges local-then-push, sequenced to avoid shared-file races.
   Verify against ground truth (Hard Rule #4). Commit each pin cwd-safe (`scripts/commit-pin.sh`).
7. **Bookkeep + Cleanup** — tracker transitions + worklogs (ask the human for values; don't invent).
   **Before moving a ticket, enumerate the workflow first** — `getTransitions(includeUnavailableTransitions=true)`
   from the current state, and validate any target status name (e.g. JQL `status = "X"` errors if it
   doesn't exist). NEVER transition a ticket just to *discover* what's reachable. Then worktree/branch
   housekeeping per the project's rules.

## Worker brief (structured contract — send this when spawning each worker)
- Ticket key + one-line goal; repos it touches; its **ownership boundary** (exact files/dirs).
- Dependencies (what must land first) and what it must reuse (name the components).
- Constraints pulled from the **project's** CLAUDE.md/skills (not invented here).
- Branch/worktree convention (from the project).
- **Report format:** it must emit a status line to the status bus (see helper) and, when done,
  report: what landed, where, verification result.
- **Questions:** NEVER prompt the human directly (no AskUserQuestion / grill-me to your tab). When
  blocked on something you can't resolve from this brief + the project spec, write it to the status
  bus (`question` field) and either pause or proceed on a flagged REVERSIBLE assumption. The
  Orchestrator answers it, relays a cross-session answer, or batches it to the human — you never
  interrupt the human yourself.
- "Do NOT merge / bring up shared services yourself — the Orchestrator sequences that."

## Hard rules (learned the hard way — do not skip)
1. **Never auto-default an architectural decision on a timer.** Interactive prompt tools may time
   out in seconds; the human then never really answered. Split decisions into *reversible
   defaults* (you may proceed, and say so) vs *irreversible/architectural* (BLOCK — batch them into
   the decision brief and wait, however long). The human belongs in design, not in a 60s race.
2. **Tooling pre-flight before fan-out; never broadcast an unvalidated convention.** A bad
   convention sent to N workers multiplies into N failures. Probe infra/tooling assumptions once
   (env boots? deps sane? services up?) before releasing the swarm.
3. **Reference herdr sessions by tab LABEL, not pane id.** Pane ids compact when tabs/panes close;
   a stored `w7:pA` can silently become a different pane. Re-resolve label→pane each time.
4. **Verify against ground truth; never trust a session's self-report of a side effect.** "It
   landed" → check `git ... origin/main`. "It's up" → probe the port/health. "Done" → read the diff.
5. **Code review is a gate, not optional.** Every diff gets an *independent* reviewer pass before
   merge (see Code review). Merging N tickets to main with only compile+tests is how bugs ship.
6. **Status bus, not pane-scraping; pipeline per-completion, don't barrier.** Workers write
   structured status; you read that. Drive integration off PER-WORKER terminal events
   (`scripts/bus-waiter.py`, run under Monitor — one ping per worker as it finishes) so you
   verify+commit each as it lands. Reserve `scripts/settle-waiter.py` (all-settle / stuck) for a
   genuine barrier or a stuck-detection backstop — using it as the sole signal makes finished
   workers idle-wait on the slowest.
7. **Human UP, human OUT of ops.** Escalate design decisions up; push integration/verification/env
   bring-up down to specialist sessions or automation. Don't make the human a serial semaphore.
8. **Destructive or outward-facing ops → confirm scope + back up first.** Deletes, prod pushes,
   force-merges: enumerate the exact target, snapshot it, confirm, then act.
9. **Project specifics live in the project.** Read repos/env/deploy/tracker from the project's
   CLAUDE.md/skills at runtime. Keep this skill generic.
10. **Transition the tracker at spawn, not later.** Moving a ticket to In Progress is part of the
    atomic spawn step (Phase 5), not a retroactive pass. A ticket in To Do whose work is already
    underway is a lie the team acts on. Same for terminal states: reflect reality as it changes.
11. **cwd-safe git in multi-repo scripts.** The Bash tool persists cwd across calls, so relative
    paths / `[ -e path ]` guards silently target the wrong repo. Always `git -C <abs-repo>` and use
    a staged-diff check, never a relative `-e` guard (see `scripts/commit-pin.sh`).

## Question & decision flow (everything funnels through the Orchestrator)
Workers **never ask the human.** The human has exactly one counterpart: the Orchestrator.
```
worker hits a question it can't resolve
  → writes it to the status bus (question field); pauses OR proceeds on a flagged reversible default
  → Orchestrator aggregates all open questions across sessions and triages each:
       • answerable from plan / spec / decisions / recon   → answer + relay to the worker
       • another session knows it (cross-session)          → query that session, relay the answer
       • truly needs the human (architectural/product/     → BATCH into the decision brief (Rule #1),
         irreversible)                                         present as ONE consolidated ask
  → Orchestrator relays the answer back to the asking worker
```
Result: the human only ever sees a **curated, batched** set of decisions from the Orchestrator —
never scattered per-session prompts, never a per-question timer. This is what makes the mediator a
single low-friction surface, and it's the direct fix for fragmented questions + decision-prompt
timeouts. Rule #7 (human UP, human OUT of ops) applies to questions too: aggregate, triage, batch.

## herdr cheatsheet
```bash
herdr tab create --workspace <ws> --label "<TICKET>" --no-focus   # returns result.root_pane.pane_id
herdr pane run  <pane> "claude"                                    # spawn a worker session
herdr pane run  <pane> "<structured brief>"                        # give it its task
herdr pane read <pane> --source recent --lines 20                  # inspect (sparingly)
herdr pane send-keys <pane> Escape                                 # dismiss a modal / clear input
# Resolve label -> current pane id every time (ids compact):
herdr tab list --workspace <ws>    # map label -> tab_id ; herdr pane list -> pane_id per tab_id
```

## Code review (WORKER-owned, before merge)
CR belongs to the **implementor**, not the orchestrator. The orchestrator never reviews, never reads
findings, never routes fixes — it gates ONLY on the outcome ("QA-approved") via the status bus.
- **Layer 1 — worker ↔ QA reviewer (blocking, self-contained):** when a worker is code-complete, the
  **worker spawns its OWN QA reviewer subagent** (Agent tool: `branch-code-reviewer` /
  `pr-review-toolkit:code-reviewer` / `silent-failure-hunter`) on its diff vs main. Fresh + adversarial:
  it sees only the ticket spec + diff (NOT the worker's rationale) and uses a STANDARD review brief
  (not author-written), so it can't be soft-balled. Worker addresses findings → re-invokes QA → loops
  until sign-off → reports "QA-approved + summary" to the status bus. Independence holds (distinct
  agent) even though the worker launches it. QA is a **subagent of the worker, NOT a separate herdr
  session** — two herdr sessions can't talk directly, so this keeps the loop self-contained and the
  orchestrator OUT of it.
- **Layer 2 — `hunk` (human surface, risk-gated):** for diffs that matter (auth, money, schema,
  migrations) the human reviews in Hunk while the reviewer agent posts inline findings:
  ```bash
  # Human launches the TUI on the changeset (a herdr pane can launch it):
  hunk diff main...feature/<ticket> --agent-context <rationale.json>
  # Reviewer AGENT annotates the LIVE session (do NOT run `hunk diff` as the agent):
  hunk session list
  hunk session review  --repo <worktree> --json          # inspect files/hunks
  hunk session comment apply   # batch inline notes via stdin
  ```
  Topology: Layer 1 reads `git diff` directly (needs NO hunk) and runs on EVERY diff. hunk is ONE
  transient session on the diff currently under review (relaunch or `hunk session reload` per
  ticket) — NEVER one-per-worker-tab. Skip hunk entirely for diffs the human won't eyeball; the
  reviewer agent still covers them. hunk is an optional enhancement, not a dependency — the flow
  works without it (reviewer agent + raw diff).
  Don't make the human review all N diffs — Layer 1 is the always-on net; Layer 2 is where the
  human engages with the *important* diffs at their own pace (this is the real fix for "the human
  wasn't in the technical decisions").

## Bundled helpers
- `scripts/bus-waiter.py <status-dir> <ticket...>` — **PER-COMPLETION** event stream off the status
  bus. Run under **Monitor** (one notification per worker the moment it turns terminal), so you
  pipeline — verify+commit each as it lands instead of waiting for the whole wave. Emits
  `DONE`/`BLOCKED`/`FAILED <ticket>`, exits when all terminal. This is the DEFAULT integration signal.
- `scripts/settle-waiter.py <workspace> <LABEL...>` — polls sessions by **label** (re-resolving pane
  ids each time) and prints when they've ALL settled or one's gone stuck ~2min. Run in background.
  Use as a **barrier / stuck backstop**, not as the per-completion signal (that idle-waits finished
  workers on the slowest — use bus-waiter for pipelining).
- `scripts/commit-pin.sh` — cwd-safe `commit_pin <abs-repo> "<msg>" <pathspec...>` for the Integrator:
  `git -C <repo>` scoping + staged-diff guard + co-author trailer. Source it or copy the function.
  Prevents the persisted-cwd footgun (Hard Rule #11).
- **Status bus convention:** workers append one JSON line per state change to a shared file
  (`<scratch>/swarm-status/<ticket>.jsonl`: `{ts, state, blocked_on, needs}`); you read that instead
  of scraping panes. Tell workers to write it in their brief.
