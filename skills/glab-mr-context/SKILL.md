---
name: glab-mr-context
description: Use when the user asks for the diff and/or the latest comment of a GitLab MR by ID (e.g. "show me MR !404", "what was the last review on MR 123", "get the diff and last note for MR X"). Wraps the `glab` CLI.
---

# Fetching GitLab MR Context

## Overview
Pull the diff and the most recent **human/bot** note (skipping GitLab's auto-generated system notes) for a given MR ID using the `glab` CLI.

## When to Use
- User references an MR by `!ID` or `MR_ID` and wants its diff and/or latest comment.
- Inspecting CI bot output (e.g. the most recent `code.agent` review post).
- Pulling MR context into the conversation without leaving the terminal.

Skip when:
- You need the full comment thread → use `glab mr note list <ID>` directly.
- You need MR metadata (title, description, approvals) → use `glab mr view <ID>`.

## Commands

```bash
# Diff vs target branch
glab mr diff <MR_ID>

# Most recent non-system note (author + timestamp + body)
glab mr note list <MR_ID> -F json \
  | jq '[.[].notes[] | select(.system==false)]
        | sort_by(.created_at)
        | last
        | {author: .author.username, created_at, body}'
```

Run both in parallel (independent calls) when the user wants both.

## Why `select(.system==false)`
GitLab emits system notes for pushes, label changes, assignee changes, etc. Without the filter, "last note" frequently returns `"added N commits"` instead of the actual review comment. Always filter unless the user explicitly wants system events.

## Quick Reference
| Need | Command |
|------|---------|
| Diff | `glab mr diff <ID>` |
| Last real note | `glab mr note list <ID> -F json \| jq '[.[].notes[] \| select(.system==false)] \| sort_by(.created_at) \| last'` |
| All notes (raw) | `glab mr note list <ID>` |
| Last note body only | append `\| .body` to the jq pipeline |

## Common Mistakes
- Using `glab mr note list <ID> \| tail` — the trailing block is often a system push note, not the latest review.
- Forgetting `-F json` — the default text output cannot be reliably parsed for "last note".
- Passing `!404` instead of `404` — `glab` takes the bare numeric ID.
