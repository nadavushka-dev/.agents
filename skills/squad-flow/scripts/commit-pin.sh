#!/usr/bin/env bash
# swarm-flow commit-pin — cwd-safe, per-pin, scoped commit for the Integrator role.
#
# Why: a multi-repo commit loop that uses the shell's cwd (relative paths, `[ -e path ]`
# guards) breaks silently — the Bash tool PERSISTS cwd across calls, so a guard written
# for repo A skips every commit in repo B. This helper never touches cwd: `git -C <repo>`
# resolves pathspecs relative to the REPO, and the staged-diff check replaces the -e guard.
#
# Usage:
#   commit_pin <abs-repo> "<message>" <pathspec> [<pathspec> ...]
#   # source this file, or copy the function into your commit script.
# Stages EXACTLY the given pathspecs (per-pin scoping), commits only if something staged,
# appends the project co-author trailer. Never pushes, never force, never --no-verify.

commit_pin() {
  local repo="$1" msg="$2"; shift 2
  if [ -z "$repo" ] || [ -z "$msg" ] || [ "$#" -eq 0 ]; then
    echo "commit_pin: need <repo> <msg> <pathspec...>" >&2; return 2
  fi
  local trailer=$'\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>'
  git -C "$repo" add -- "$@"
  if git -C "$repo" diff --cached --quiet; then
    echo "SKIP (nothing staged) [$repo]: $msg"
    return 0
  fi
  git -C "$repo" commit -q -m "${msg}${trailer}" \
    && echo "committed $(git -C "$repo" rev-parse --short HEAD) [$repo]: $msg"
}

# If executed (not sourced) with args, run once.
if [ "${BASH_SOURCE[0]}" = "${0}" ] && [ "$#" -gt 0 ]; then
  commit_pin "$@"
fi
