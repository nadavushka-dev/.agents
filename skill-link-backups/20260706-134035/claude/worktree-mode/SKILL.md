---
name: worktree-mode
description: Start "worktree mode" — create/resume a git worktree under .worktrees/ for the current task (named after a Jira ticket when given), do all work inside it, and on completion offer squash-merge / GitLab MR / leave-as-is. Use when the user says "/worktree-mode", "start worktree mode", "work on this in a worktree", or gives a ticket + asks to work in worktree mode.
---

# Worktree Mode

A session mode: all task work happens inside a dedicated git worktree under `<repo-root>/.worktrees/<name>`, on its own branch. The mode stays active until the user declares the task done and picks an exit action.

## Phase 1 — Repo setup checks

Run from the repo root (`git rev-parse --show-toplevel`). If not in a git repo, stop and tell the user.

1. **`.worktrees/` dir** — if it does not exist, `mkdir -p <root>/.worktrees`.
2. **`.gitignore` entry** — check `.gitignore` for a line matching `.worktrees` or `.worktrees/`. If missing, append `.worktrees/` to `.gitignore` (create the file if it doesn't exist) and tell the user you did so. Do NOT commit this change yourself; just mention it's there.

## Phase 2 — Resolve the worktree name and branch

**If a Jira ticket key was provided** (e.g. `CZ-666`, any `ABC-123` pattern in the user's request):

1. Fetch the issue via the Atlassian MCP (`mcp__claude_ai_Atlassian__getJiraIssue` — load via ToolSearch if deferred). Map the issue type to a prefix:
   - `Bug` → `bugfix/`
   - anything else (Story, Task, Improvement, …) → `feature/`
2. If the Jira fetch fails or the MCP is unavailable, ask the user (AskUserQuestion) which prefix to use (`feature/`, `bugfix/`, `chore/`) — do not guess.
3. Names: worktree dir = `.worktrees/<TICKET-KEY>`, branch = `<prefix><TICKET-KEY>` (e.g. dir `.worktrees/CZ-666`, branch `feature/CZ-666`).

**If no ticket but the user gave a name:** use it — dir `.worktrees/<name>`, branch `feature/<name>` (or another prefix if the user's wording implies a bug fix).

**If neither ticket nor name was given:** ask the user (AskUserQuestion) for a name/ticket before doing anything else.

## Phase 3 — Create or resume the worktree

1. Detect the repo's default branch: `git symbolic-ref --short refs/remotes/origin/HEAD` (strip `origin/`); fallback: prefer `dev` if it exists, else `main`/`master`. Call this `<base>`.
2. `git fetch origin <base>` (best-effort; skip silently if offline).
3. If `.worktrees/<name>` already exists as a registered worktree (`git worktree list`), **resume** it — don't recreate. Tell the user you're resuming.
4. Otherwise create it:
   - Branch doesn't exist yet: `git worktree add .worktrees/<name> -b <branch> origin/<base>` (fall back to local `<base>` if no remote).
   - Branch already exists: `git worktree add .worktrees/<name> <branch>`.

### node_modules (make the worktree runnable)

If the repo root has a `package.json`, the worktree needs `node_modules` — **symlink** it from the main checkout instead of installing:

1. If `<root>/node_modules` doesn't exist, tell the user and ask whether to `npm install` in the main checkout first.
2. `ln -s <root>/node_modules <root>/.worktrees/<name>/node_modules` (skip if the worktree already has one, e.g. on resume).
3. If the repo has nested packages with their own `node_modules` (check only when relevant), symlink those the same way.

Symlink caveats — enforce while the mode is active:

- `node_modules` is **shared** with the main checkout. Never run `npm install`/`npm ci` inside the worktree through the symlink — it would mutate the main checkout's modules.
- If the task changes `package.json`/`package-lock.json`: remove the symlink (`rm <worktree>/node_modules` — it's a symlink, this is safe) and run a real `npm install` in the worktree so the branch gets its own modules. Tell the user this happened.
- Don't run dev servers from the main checkout and the worktree at the same time (shared `node_modules/.vite` cache + same port); warn the user if they ask for it.

## Phase 4 — Working in the mode

While the mode is active:

- **Every** file read/edit/write and every build/test/lint command targets the worktree path, never the main checkout. Use absolute paths rooted at `<root>/.worktrees/<name>/`.
- Start your first response after activation with a clear banner, e.g.:
  `🌳 WORKTREE MODE — .worktrees/CZ-666 (branch feature/CZ-666, base dev)`
  and re-state the worktree path whenever you resume work after a long gap, so it stays obvious where work is happening.
- Commits happen on the worktree branch, inside the worktree dir.
- If at any point you notice you touched a file in the main checkout by mistake, stop, tell the user, and move the change into the worktree.

The mode ends only when the **user** says the task is done (e.g. "done", "finish up", "wrap it up", "exit worktree mode").

## Phase 5 — Task done: ask for the next step

When the user declares done, make sure all work is committed on the worktree branch (ask before committing leftover changes), then ask via AskUserQuestion:

1. **Squash-merge into `<base>`**
2. **Open a GitLab MR**
3. **Leave as is**

### Option A — Squash merge

The user choosing this option counts as explicit instruction to merge into `<base>`.

1. In the **main checkout**: verify it's clean (`git status --porcelain`). If dirty, stop and ask the user how to proceed.
2. `git checkout <base>` and `git pull origin <base>` (best-effort).
3. `git merge --squash <branch>`.
4. On conflict: stop, report the conflicting files, and let the user decide — do not resolve silently.
5. Commit: `git commit -m "<TICKET-KEY>: <short summary of the work>"` (no ticket → `<name>: <summary>`).
6. **Only after the merge commit succeeds:** first remove the `node_modules` symlink (`rm .worktrees/<name>/node_modules` — only if it's a symlink; never `rm -rf` a real dir without asking), then `git worktree remove .worktrees/<name>` (use `--force` only if the user confirms discarding stray files) and `git branch -D <branch>`.
7. Do NOT push `<base>` unless the user asks.

### Option B — GitLab MR (glab)

1. Push the branch: `git push -u origin <branch>` (from the worktree dir; never force-push).
2. Create the MR with the `glab` CLI, targeting `<base>`:
   - Title: `<TICKET-KEY>: <short summary>` (no ticket → just the summary).
   - Description: a link to the Jira ticket — `https://leverate.atlassian.net/browse/<TICKET-KEY>` — plus a brief bullet list of the changes. No ticket → just the bullets.
   - `glab mr create --source-branch <branch> --target-branch <base> --title "..." --description "..."`
3. If an open MR for this branch already exists (`glab mr list --source-branch <branch>`), report its URL instead of creating a duplicate.
4. Keep the worktree and branch in place (the MR may need fixes).
5. Report the MR URL.

### Option C — Leave as is

Do nothing. State the worktree path and branch so the user knows where the work lives, and that they can resume later with this skill.
