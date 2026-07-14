#!/usr/bin/env python3
"""Render the .pin-board file-per-item JSON DB as an organized table.

Usage:
  render.py [--status S] [--ticket T] [--type TY] [--dir PATH]

The board is DERIVED by globbing <dir>/*.json at read time — there is no
central index file (that would be a write-contention point for parallel agents).
Shared schema/helpers live in _common.py; mutation + lint/gc live in pinboard.py.
"""
import argparse
import os
import sys

from _common import DEFAULT_DIR, MARK, load, parse_iso, due_countdown


def links_str(it):
    parts = []
    for l in it.get("links", []) or []:
        parts.append(f"{l.get('rel')}→{l.get('id')}")
    return "  [" + ", ".join(parts) + "]" if parts else ""


def line(it, indent=0):
    m = MARK.get(it.get("status"), "?")
    pad = "  " * indent
    sid = it.get("id", "?")
    typ = it.get("type", "?")
    title = it.get("title", "")
    due = due_countdown(it.get("due")) if it.get("status") != "done" else ""
    due_s = f"  {due}" if due else ""
    print(f"{pad}{m} {sid:<22} [{typ:<9}] {it.get('status','?'):<11} {title}{links_str(it)}{due_s}")
    note = (it.get("note") or "").strip()
    if note and indent >= 0:
        wrap = (note[:150] + "…") if len(note) > 150 else note
        print(f"{pad}    └ {wrap}")


def deadlines_block(sel):
    """Top-of-board surfacing for time-sensitive items (due + not done)."""
    due_items = [v for v in sel.values()
                 if v.get("due") and v.get("status") != "done"
                 and parse_iso(v.get("due")) is not None]
    if not due_items:
        return
    due_items.sort(key=lambda x: parse_iso(x["due"]))
    print("⏰ Upcoming deadlines")
    print("-" * 60)
    for it in due_items:
        cd = due_countdown(it["due"])
        print(f"  {cd:<16} {it['id']:<26} {it.get('title','')}")
    print()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--status")
    ap.add_argument("--ticket")
    ap.add_argument("--type")
    ap.add_argument("--dir", default=DEFAULT_DIR)
    a = ap.parse_args()

    if not os.path.isdir(a.dir):
        print(f"no progress dir at {a.dir}", file=sys.stderr)
        sys.exit(1)

    items = load(a.dir)

    def keep(it):
        if a.status and it.get("status") != a.status:
            return False
        if a.ticket and it.get("ticket") != a.ticket:
            return False
        if a.type and it.get("type") != a.type:
            return False
        return True

    sel = {k: v for k, v in items.items() if keep(it=v)}
    if not sel:
        print("(no matching items)")
        return

    flt = [s for s in (a.status, a.ticket, a.type) if s]
    hdr = "PIN BOARD" + (f"  —  filter: {', '.join(flt)}" if flt else "")
    print(hdr)
    print("=" * max(len(hdr), 60))

    deadlines_block(sel)

    shown = set()
    epics = sorted([v for v in sel.values() if v.get("type") == "epic"],
                   key=lambda x: x["id"])
    for ep in epics:
        line(ep)
        shown.add(ep["id"])
        kids = sorted([v for v in sel.values() if v.get("parent") == ep["id"]],
                      key=lambda x: x["id"])
        for k in kids:
            line(k, indent=1)
            shown.add(k["id"])
        print()

    rest = sorted([v for v in sel.values() if v["id"] not in shown],
                  key=lambda x: (x.get("type", ""), x["id"]))
    if rest:
        print("Standalone items / decisions / deferrals")
        print("-" * 60)
        for it in rest:
            line(it)
        print()

    # summary
    by_status = {}
    for it in sel.values():
        by_status[it.get("status", "?")] = by_status.get(it.get("status", "?"), 0) + 1
    summary = "  ".join(f"{MARK.get(s,'?')} {s}:{n}" for s, n in sorted(by_status.items()))
    print(f"total {len(sel)}   {summary}")


if __name__ == "__main__":
    main()
