---
name: piqk-takeover
description: Recover and take over interrupted Piqk work from Claude/Codex sessions. Use when the user asks to take over, resume, continue, audit, recover context, understand what happened in prior agent sessions, or finish partially completed Piqk work across .claude/.codex transcripts, herdr panes, git worktrees, piqkenv state, and the mandatory .pin-board tracker.
---

# Piqk Takeover

Use this skill to reconstruct the current state before coding. The goal is to
avoid acting from a stale chat, the wrong repo, or an incomplete agent handoff.

## Non-Negotiables

- Treat `/Users/nadav.barmatz/work/piqk` as the project root even if the shell
  starts elsewhere.
- Read `/Users/nadav.barmatz/work/piqk/AGENTS.md` or `CLAUDE.md` before taking
  task actions.
- Use the Piqk `.pin-board` workflow. It is mandatory for in-flight work,
  decisions, shortcuts, and completion state.
- Do not mark a pin-board item `done` until the work is committed, or until the
  pin explicitly says it is intentionally left uncommitted.
- For UI changes, verify with Playwright against the running worktree-served app
  unless the user explicitly says `skip playwright`; typecheck alone is not
  completion.
- Use GitNexus/GK first for high-level orientation when available. If unavailable
  or stale, say so and fall back to direct file inspection.
- Preserve user/other-agent changes. Do not reset or revert unrelated work.

## Takeover Workflow

1. Identify the real project root.
   - If `pwd` is not `/Users/nadav.barmatz/work/piqk` or a repo/worktree under it,
     explicitly say the session started from the wrong repo and switch context.
   - Read project instructions from the Piqk root.

2. Load durable state.
   - Use the `pin-board` skill if available.
   - Read relevant pins from `/Users/nadav.barmatz/work/piqk/.pin-board`.
   - Run the pin-board renderer or targeted file reads for the ticket/epic.
   - Note existing decisions, tech debt, blockers, and stale status.

3. Recover live/session context.
   - Claude transcripts live under:
     `/Users/nadav.barmatz/.claude/projects/<escaped-project-path>/*.jsonl`.
   - For Piqk root sessions, use:
     `/Users/nadav.barmatz/.claude/projects/-Users-nadav-barmatz-work-piqk`.
   - Check `session-env/<session-id>`, `file-history/<session-id>`, and any
     scratchpad status files under `/private/tmp/claude-*` when referenced.
   - If running in herdr, use the `herdr` skill/tooling to inspect panes before
     assuming a session is dead.

4. Reconstruct code state.
   - For each touched repo, inspect `git status --short`, branch, worktree path,
     latest commit, and staged changes.
   - Map ticket IDs to repo worktrees. Piqk service work must happen under
     `<repo>/.worktrees/<env-name>`, not main checkouts.
   - Separate uncommitted user changes from interrupted agent changes.

5. Build a takeover brief before editing.
   Include:
   - ticket/epic IDs
   - repo/worktree paths
   - current branches and commits
   - transcript/session IDs read
   - files already changed
   - tests already run
   - known blockers and assumptions
   - exact next actions

6. Continue the work.
   - Reuse existing local patterns.
   - Keep files under 300 lines.
   - Record product or implementation ambiguity as `DEC-*` or `TD-*` pins.
   - Update scratchpad/status files only when they are clearly part of the
     interrupted workflow.

7. Verify before completion.
   - Run repo-appropriate typechecks/tests.
   - For UI work, perform the Playwright verification required by Piqk rules.
   - Inspect `/Users/nadav.barmatz/work/piqk/piqkenv-run.log` for crashes after
     starting or using the environment.
   - If full lint is known to fail from unrelated debt, also run a scoped lint
     over touched files and report the distinction.

8. Commit and close.
   - Commit each repo separately with scoped messages.
   - Re-check `git status --short`.
   - Update `.pin-board` with status, commit hashes, verification, and remaining
     assumptions.
   - Do not claim done without commit hashes or an explicit uncommitted handoff.

## Piqkenv Crash Triage

When takeover includes running or checking local services:

```bash
rg -n -i "CRASHED|FATAL|panic|TurbopackInternalError|Unhandled|uncaught|exit code|EADDRINUSE|ECONNREFUSED|failed|error" /Users/nadav.barmatz/work/piqk/piqkenv-run.log
tail -n 200 /Users/nadav.barmatz/work/piqk/piqkenv-run.log
```

Known issue to recognize: a worktree `node_modules` symlink can make Next
Turbopack crash with `Symlink [project]/node_modules is invalid, it points out
of the filesystem root`. Report this as environment/worktree setup, not as an
application code crash.

## Output Shape

Use this structure for the initial takeover response:

```text
Takeover state:
- Project root:
- Tickets:
- Repos/worktrees:
- Sessions/transcripts read:
- Pin-board state:
- Current blockers:
- Next actions:
```

Use this structure for the final handoff:

```text
Completed:
- ...

Commits:
- repo: hash message

Verified:
- ...

Remaining:
- ...
```
