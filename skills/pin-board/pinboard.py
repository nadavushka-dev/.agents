#!/usr/bin/env python3
"""Pin-board maintenance CLI — integrity, garbage-collection, and safe mutation.

Usage:
  pinboard.py lint   [--dir PATH] [--stale-days N]
  pinboard.py gc     [--dir PATH] [--execute]
  pinboard.py set    <id> <field> <value> [--dir PATH] [--by WHO]
  pinboard.py link   <id> <rel> <target>  [--dir PATH] [--by WHO]
  pinboard.py unlink <id> <rel> <target>  [--dir PATH] [--by WHO]

Stdlib only. Shares schema/helpers with render.py via _common.py. Honors the
board rules: file-per-item, never auto-prune decision/tech-debt/shortcut,
always stamp updatedBy, atomic writes. `gc` ARCHIVES fully-done task subtrees
(moves them to <dir>/archive/) rather than deleting — finished work stays
recoverable and off the live board.
"""
import argparse
import glob
import json
import os
import sys

from _common import (
    DEFAULT_DIR, PRUNABLE, STATUS, TYPE, REL, REQUIRED, ARCHIVE_SUBDIR,
    load, parse_iso, iso_now, write_item, item_path, archive_item,
)

SETTABLE = {"status", "title", "note", "due", "ticket"}


# ── helpers ──────────────────────────────────────────────────────────────────

def _children_map(items):
    kids = {}
    for it in items.values():
        p = it.get("parent")
        if p:
            kids.setdefault(p, []).append(it["id"])
    return kids


def _descendants(root_id, kids, seen=None):
    seen = seen if seen is not None else set()
    for c in kids.get(root_id, []):
        if c not in seen:
            seen.add(c)
            _descendants(c, kids, seen)
    return seen


def _load_item_or_exit(d, item_id):
    path = item_path(d, item_id)
    if not os.path.isfile(path):
        print(f"error: no item '{item_id}' at {path}", file=sys.stderr)
        sys.exit(1)
    with open(path) as f:
        return json.load(f)


# ── lint ─────────────────────────────────────────────────────────────────────

def _archived_ids(d):
    """Ids of pins already moved to archive/ — they still 'exist' (done), so a
    link/parent pointing at one is valid, not dangling."""
    ids = set()
    for p in glob.glob(os.path.join(d, ARCHIVE_SUBDIR, "*.json")):
        try:
            with open(p) as f:
                it = json.load(f)
            if isinstance(it, dict) and it.get("id"):
                ids.add(it["id"])
        except (json.JSONDecodeError, OSError):
            pass
    return ids


def cmd_lint(a):
    items = load(a.dir)
    known = set(items) | _archived_ids(a.dir)  # live + archived both "exist"
    errors, warns, infos = [], [], []

    # filename ↔ id
    for p in glob.glob(os.path.join(a.dir, "*.json")):
        stem = os.path.basename(p)[:-5]
        try:
            with open(p) as f:
                it = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            errors.append(f"{stem}: unreadable ({e})")
            continue
        if it.get("id") != stem:
            errors.append(f"{stem}: id field '{it.get('id')}' != filename")

    kids = _children_map(items)
    now_iso = iso_now()

    for it in items.values():
        i = it.get("id", "?")
        for fld in REQUIRED:
            if not it.get(fld):
                errors.append(f"{i}: missing required field '{fld}'")
        if it.get("type") not in TYPE:
            errors.append(f"{i}: invalid type '{it.get('type')}'")
        if it.get("status") not in STATUS:
            errors.append(f"{i}: invalid status '{it.get('status')}'")
        for ts in ("createdAt", "updatedAt", "due"):
            if it.get(ts) and parse_iso(it[ts]) is None:
                errors.append(f"{i}: unparseable {ts} '{it[ts]}'")
        for l in it.get("links", []) or []:
            if l.get("rel") not in REL:
                errors.append(f"{i}: invalid link rel '{l.get('rel')}'")
            tgt = l.get("id")
            if not tgt:
                errors.append(f"{i}: link missing target id")
            elif tgt not in known:
                errors.append(f"{i}: dangling link → '{tgt}' (no such item)")
        par = it.get("parent")
        if par and par not in known:
            errors.append(f"{i}: orphaned parent → '{par}' (no such item)")
        # circular parent chain
        chain, cur = set(), it
        while cur and cur.get("parent"):
            nxt = cur["parent"]
            if nxt in chain:
                errors.append(f"{i}: circular parent chain at '{nxt}'")
                break
            chain.add(nxt)
            cur = items.get(nxt)
        # warnings
        if it.get("due") and it.get("status") != "done":
            dt = parse_iso(it["due"])
            if dt and dt < parse_iso(now_iso):
                warns.append(f"{i}: past due ({it['due']}) and not done")
        if it.get("status") == "in_progress" and it.get("updatedAt"):
            d_upd = parse_iso(it["updatedAt"])
            d_now = parse_iso(now_iso)
            if d_upd and (d_now - d_upd).days > a.stale_days:
                warns.append(f"{i}: in_progress, untouched {(d_now - d_upd).days}d (>{a.stale_days})")
        # info
        if it.get("type") in PRUNABLE and it.get("status") == "done":
            desc = _descendants(i, kids)
            if all(items[c].get("status") == "done" for c in desc):
                infos.append(f"{i}: prunable subtree fully done → gc candidate")
        if it.get("type") in (TYPE - PRUNABLE) and it.get("status") == "done":
            infos.append(f"{i}: resolved {it.get('type')} → manual-drop candidate")

    def dump(label, rows):
        if rows:
            print(f"\n{label} ({len(rows)})")
            print("-" * 60)
            for r in rows:
                print(f"  {r}")

    print(f"PIN BOARD LINT — {len(items)} items @ {a.dir}")
    dump("ERRORS", errors)
    dump("WARNINGS", warns)
    dump("INFO", infos)
    if not (errors or warns or infos):
        print("\n✓ clean — no issues")
    elif not errors:
        print("\n✓ no errors (warnings/info only)")
    return 1 if errors else 0


# ── gc ───────────────────────────────────────────────────────────────────────

def cmd_gc(a):
    items = load(a.dir)
    kids = _children_map(items)

    def eligible(it):
        if it.get("type") not in PRUNABLE or it.get("status") != "done":
            return False
        return all(items[c].get("status") == "done" for c in _descendants(it["id"], kids))

    elig_ids = {i for i, it in items.items() if eligible(it)}
    # Only delete a node when it has no parent, or its parent is also eligible —
    # so we remove whole done subtrees but never a done leaf under an active parent.
    to_delete = sorted(
        i for i in elig_ids
        if not items[i].get("parent") or items[i]["parent"] in elig_ids
    )
    manual = sorted(
        i for i, it in items.items()
        if it.get("type") in (TYPE - PRUNABLE) and it.get("status") == "done"
    )

    print(f"PIN BOARD GC — {'EXECUTE' if a.execute else 'dry-run'} @ {a.dir}")
    if to_delete:
        print(f"\nFully-done task subtrees to archive → {ARCHIVE_SUBDIR}/ ({len(to_delete)}):")
        for i in to_delete:
            print(f"  {i}")
    else:
        print("\nNo fully-done epic/task/subtree to archive.")
    if manual:
        print(f"\nResolved decisions/tech-debt/shortcuts (manual-drop only, NOT archived):")
        for i in manual:
            print(f"  {i}")

    if a.execute and to_delete:
        for i in to_delete:
            archive_item(a.dir, i)
        print(f"\n✓ archived {len(to_delete)} item(s) → {ARCHIVE_SUBDIR}/.")
    elif to_delete:
        print(f"\n(dry-run — re-run with --execute to move them to {ARCHIVE_SUBDIR}/)")
    return 0


# ── mutation ───────────────────────────────────────────────────────────────────

def cmd_set(a):
    if a.field not in SETTABLE:
        print(f"error: field must be one of {sorted(SETTABLE)}", file=sys.stderr)
        sys.exit(2)
    it = _load_item_or_exit(a.dir, a.id)
    if a.field == "status" and a.value not in STATUS:
        print(f"error: status must be one of {sorted(STATUS)}", file=sys.stderr)
        sys.exit(2)
    if a.field == "due":
        if a.value == "clear":
            it.pop("due", None)
        elif parse_iso(a.value) is None:
            print(f"error: due '{a.value}' is not ISO 8601", file=sys.stderr)
            sys.exit(2)
        else:
            it["due"] = a.value
    else:
        it[a.field] = a.value
    write_item(a.dir, it, a.by)
    print(f"✓ {a.id}: {a.field} = {a.value}")
    return 0


def cmd_link(a):
    if a.rel not in REL:
        print(f"error: rel must be one of {sorted(REL)}", file=sys.stderr)
        sys.exit(2)
    items = load(a.dir)
    if a.id not in items:
        print(f"error: no item '{a.id}'", file=sys.stderr)
        sys.exit(1)
    if not a.unlink and a.target not in items:
        print(f"warning: target '{a.target}' not on the board (adding anyway)", file=sys.stderr)
    it = _load_item_or_exit(a.dir, a.id)
    links = it.setdefault("links", [])
    if a.unlink:
        before = len(links)
        links[:] = [l for l in links if not (l.get("rel") == a.rel and l.get("id") == a.target)]
        if len(links) == before:
            print(f"(no '{a.rel}→{a.target}' link on {a.id})")
            return 0
    else:
        if any(l.get("rel") == a.rel and l.get("id") == a.target for l in links):
            print(f"(link '{a.rel}→{a.target}' already on {a.id})")
            return 0
        links.append({"rel": a.rel, "id": a.target})
    write_item(a.dir, it, a.by)
    print(f"✓ {a.id}: {'unlinked' if a.unlink else 'linked'} {a.rel}→{a.target}")
    return 0


# ── argparse ───────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(prog="pinboard")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("lint", help="integrity report (exit 1 on errors)")
    p.add_argument("--dir", default=DEFAULT_DIR)
    p.add_argument("--stale-days", type=int, default=14)
    p.set_defaults(fn=cmd_lint)

    p = sub.add_parser("gc", help="archive fully-done task subtrees → archive/ (dry-run unless --execute)")
    p.add_argument("--dir", default=DEFAULT_DIR)
    p.add_argument("--execute", action="store_true")
    p.set_defaults(fn=cmd_gc)

    p = sub.add_parser("set", help="set a field (status|title|note|due|ticket)")
    p.add_argument("id")
    p.add_argument("field")
    p.add_argument("value")
    p.add_argument("--dir", default=DEFAULT_DIR)
    p.add_argument("--by", default="cli")
    p.set_defaults(fn=cmd_set)

    for verb, unlink in (("link", False), ("unlink", True)):
        p = sub.add_parser(verb, help=f"{verb} a relation (blocks|relatedTo|supersedes)")
        p.add_argument("id")
        p.add_argument("rel")
        p.add_argument("target")
        p.add_argument("--dir", default=DEFAULT_DIR)
        p.add_argument("--by", default="cli")
        p.set_defaults(fn=cmd_link, unlink=unlink)

    a = ap.parse_args()
    if not hasattr(a, "unlink"):
        a.unlink = False
    if not os.path.isdir(a.dir):
        print(f"no pin-board dir at {a.dir}", file=sys.stderr)
        sys.exit(1)
    sys.exit(a.fn(a))


if __name__ == "__main__":
    main()
