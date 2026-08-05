#!/usr/bin/env python3
"""Append PR links to a Jira issue's Dev Notes field, without destroying it.

Why a script and not a curl one-liner:

  * Dev Notes (customfield_11739) is a `textarea` custom field, so in REST v3 its
    value is an **ADF document**, not a string.
  * `editmeta` reports `operations: ['set']` — there is NO append primitive. The
    only way to add a line is read-modify-write of the whole document.
  * The field is **not empty** on RND bugs: it carries the team's template
    (Happy Flow Video / Edge Cases / Blast Radius / Credentials / Additional
    Notes). A blind `set` silently destroys that. This script preserves every
    existing node and appends after them.

Idempotent: a PR whose **label or URL** already appears anywhere in the document
is skipped, so re-running a solve-bug phase 8 never duplicates lines. Matching the
label too is deliberate — when the repos moved to the LeveratePiqkProtect org the
URLs changed, and a URL-only check re-added PRs that were already listed.

Usage:
    # dry run (default) — prints what would be written, touches nothing
    jira-dev-notes-prs.py RND-1280 \
        --pr piqk-app#21=https://github.com/LeveratePiqkProtect/piqk-app/pull/21

    # actually write
    jira-dev-notes-prs.py RND-1280 --pr ... --execute

Credentials come from ~/.local/secrets.env (JIRA_BASE_URL, JIRA_EMAIL,
JIRA_API_TOKEN) unless already exported.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile

FIELD_ID = "customfield_11739"  # Dev Notes
FIELD_NAME = "Dev Notes"
HEADING = "🔗 Pull requests"
SECRETS = os.path.expanduser("~/.local/secrets.env")


def load_creds():
    env = {}
    try:
        with open(SECRETS) as fh:
            for line in fh:
                m = re.match(r"^([A-Z0-9_]+)=(.*)$", line.strip())
                if m:
                    env[m.group(1)] = m.group(2).strip("'\"")
    except OSError:
        pass
    base = os.environ.get("JIRA_BASE_URL") or env.get("JIRA_BASE_URL")
    email = os.environ.get("JIRA_EMAIL") or env.get("JIRA_EMAIL")
    token = os.environ.get("JIRA_API_TOKEN") or env.get("JIRA_API_TOKEN")
    if not (base and email and token):
        sys.exit("missing JIRA_BASE_URL / JIRA_EMAIL / JIRA_API_TOKEN")
    return base.rstrip("/"), email, token


def request(method, url, email, token, payload=None):
    """HTTP via curl, not urllib.

    The python.org Python on this machine ships without a CA bundle
    (`CERTIFICATE_VERIFY_FAILED: unable to get local issuer certificate`), and
    which python3 is first on PATH varies. curl works everywhere here and is
    what the rest of the Jira recipes already use.
    """
    cmd = ["curl", "-sS", "--max-time", "30", "-u", f"{email}:{token}",
           "-X", method, "-w", "\n%{http_code}", url]
    tmp = None
    if payload is not None:
        # Body goes through a file — a large ADF document on the command line
        # would hit ARG_MAX and mangle quoting.
        tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        json.dump(payload, tmp)
        tmp.close()
        cmd += ["-H", "Content-Type: application/json", "-d", f"@{tmp.name}"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
    finally:
        if tmp:
            os.unlink(tmp.name)
    if proc.returncode != 0:
        sys.exit(f"{method} {url} → curl failed: {proc.stderr.strip()[:300]}")
    body, _, status = proc.stdout.rpartition("\n")
    if not status.strip().startswith("2"):
        sys.exit(f"{method} {url} → HTTP {status.strip()}: {body[:500]}")
    return json.loads(body) if body.strip() else {}


def flatten(node):
    """All text in an ADF node, including link hrefs — used for idempotency."""
    out = []
    if node.get("type") == "text":
        out.append(node.get("text", ""))
        for mark in node.get("marks", []):
            href = mark.get("attrs", {}).get("href")
            if href:
                out.append(href)
    for child in node.get("content", []):
        out.append(flatten(child))
    return " ".join(out)


def pr_paragraph(label, url):
    return {
        "type": "paragraph",
        "content": [
            {"type": "text", "text": f"{label} — "},
            {"type": "text", "text": url,
             "marks": [{"type": "link", "attrs": {"href": url}}]},
        ],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("issue", help="issue key, e.g. RND-1280")
    ap.add_argument("--pr", action="append", required=True, metavar="LABEL=URL",
                    help="repeatable, e.g. --pr piqk-app#21=https://github.com/.../pull/21")
    ap.add_argument("--execute", action="store_true", help="write (default is dry-run)")
    args = ap.parse_args()

    prs = []
    for item in args.pr:
        if "=" not in item:
            sys.exit(f"--pr must be LABEL=URL, got: {item}")
        label, url = item.split("=", 1)
        prs.append((label.strip(), url.strip()))

    base, email, token = load_creds()
    issue_url = f"{base}/rest/api/3/issue/{args.issue}"

    # Refuse to write a field the issue doesn't actually expose — better a clear
    # error than a 400 buried in a solve-bug transcript.
    meta = request("GET", f"{issue_url}/editmeta", email, token)
    if FIELD_ID not in meta.get("fields", {}):
        sys.exit(f"{FIELD_NAME} ({FIELD_ID}) is not editable on {args.issue} — "
                 f"fall back to the remote issue link only")

    current = request("GET", f"{issue_url}?fields={FIELD_ID}", email, token)
    doc = current.get("fields", {}).get(FIELD_ID)
    if not doc or doc.get("type") != "doc":
        doc = {"type": "doc", "version": 1, "content": []}

    existing_text = flatten(doc)
    new_nodes, skipped = [], []
    for label, url in prs:
        # Match on label OR url. URL alone is not enough: when piqk repos moved
        # from PiqkProtect to the LeveratePiqkProtect org the URL changed, the
        # substring check missed, and re-running duplicated a PR line that was
        # already there under its old URL.
        already = url in existing_text or (label and label in existing_text)
        (skipped if already else new_nodes).append((label, url))

    if not new_nodes:
        print(f"nothing to do — already present: {', '.join(l for l, _ in skipped)}")
        return

    content = list(doc.get("content", []))
    if HEADING not in existing_text:
        content.append({"type": "paragraph",
                        "content": [{"type": "text", "text": HEADING,
                                     "marks": [{"type": "strong"}]}]})
    for label, url in new_nodes:
        content.append(pr_paragraph(label, url))
    updated = {**doc, "content": content}

    print(f"{args.issue}: {len(doc.get('content', []))} existing node(s) preserved, "
          f"adding {len(new_nodes)}"
          + (f", skipping {len(skipped)} already linked" if skipped else ""))
    for label, url in new_nodes:
        print(f"  + {label} — {url}")

    if not args.execute:
        print("\n[dry-run] nothing written. Re-run with --execute to apply.")
        return

    request("PUT", issue_url, email, token, {"fields": {FIELD_ID: updated}})
    verify = request("GET", f"{issue_url}?fields={FIELD_ID}", email, token)
    written = flatten(verify.get("fields", {}).get(FIELD_ID) or {})
    missing = [url for _, url in new_nodes if url not in written]
    if missing:
        sys.exit(f"write reported OK but these are absent: {missing}")
    print(f"written and verified on {args.issue}")


if __name__ == "__main__":
    main()
