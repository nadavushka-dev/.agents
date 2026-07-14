#!/usr/bin/env python3
"""Shared helpers for the .pin-board tooling (render.py + pinboard.py).

Stdlib only. The board is file-per-item JSON with no central index — derived
by globbing <dir>/*.json. See <dir>/README.md for the schema + rules.
"""
import glob
import json
import os
import sys
import tempfile
from datetime import datetime, timezone

DEFAULT_DIR = os.environ.get(
    "PIQK_PIN_BOARD_DIR", "/Users/nadav.barmatz/work/piqk/.pin-board"
)

MARK = {"planned": "○", "in_progress": "◐", "blocked": "⊘",
        "postponed": "⏸", "done": "✓"}

# epic/task/subtask may be auto-deleted once their whole subtree is done.
# decisions/tech-debt/shortcut are the board's rationale — never auto-pruned.
PRUNABLE = {"epic", "task", "subtask"}

STATUS = {"planned", "in_progress", "blocked", "postponed", "done"}
TYPE = {"epic", "task", "subtask", "decision", "shortcut", "tech-debt"}
REL = {"blocks", "relatedTo", "supersedes"}
REQUIRED = ("id", "type", "title", "status")


def load(d):
    """Glob the dir → {id: item}. Skips unreadable/index-less files (warns)."""
    items = {}
    for p in glob.glob(os.path.join(d, "*.json")):
        try:
            with open(p) as f:
                it = json.load(f)
            if isinstance(it, dict) and it.get("id"):
                items[it["id"]] = it
        except (json.JSONDecodeError, OSError) as e:
            print(f"  ! skipped {os.path.basename(p)}: {e}", file=sys.stderr)
    return items


def iso_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(s):
    """Parse an ISO 8601 date or datetime → aware UTC datetime, or None."""
    if not s or not isinstance(s, str):
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def due_countdown(due):
    """'⏳ 6d' / '⏳ 5h' / '⚠ OVERDUE 2d' / '' (no/invalid due)."""
    dt = parse_iso(due)
    if dt is None:
        return ""
    delta = dt - datetime.now(timezone.utc)
    secs = delta.total_seconds()
    days = int(abs(secs) // 86400)
    hours = int(abs(secs) // 3600)
    if secs < 0:
        return f"⚠ OVERDUE {days}d" if days else f"⚠ OVERDUE {hours}h"
    return f"⏳ {days}d" if days else f"⏳ {hours}h"


def item_path(d, item_id):
    return os.path.join(d, f"{item_id}.json")


def write_item(d, item, by):
    """Stamp updatedAt/updatedBy and write atomically (temp + os.replace).

    File-per-item is the concurrency invariant; an atomic replace means a
    reader never sees a half-written file. Callers load → mutate → write_item.
    """
    item["updatedAt"] = iso_now()
    item["updatedBy"] = by
    path = item_path(d, item["id"])
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(item, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    return path
