#!/usr/bin/env python3
"""Post proof images INLINE in a Jira comment (ADF media), not as bare attachments.

Why a script: the recipe is three non-obvious steps and it got skipped on the
first real autonomous run.

  1. POST /rest/api/3/attachment  (multipart, header `X-Atlassian-Token: no-check`)
     → attachment id. On its own this only produces a file in the Attachments
     panel, which nobody looks at.
  2. GET /rest/api/3/attachment/content/{id} WITHOUT following the redirect. The
     `Location` header points at the media service and contains the **media UUID**
     — that is the id an ADF `media` node needs. The attachment id will NOT work.
  3. Comment with `mediaSingle` > `media` nodes using that uuid and
     `collection: ""` so the image renders in the comment body.

Usage:
    jira-evidence-comment.py RND-1338 \
      --intro "Fixed — before/after on an isolated env." \
      --image before.png="BEFORE — search typed, list unfiltered (76 rows)" \
      --image after.png="AFTER — filters to the single match" \
      [--execute]

Credentials from ~/.local/secrets.env unless already exported.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile

SECRETS = os.path.expanduser("~/.local/secrets.env")


def creds():
    env = {}
    try:
        for line in open(SECRETS):
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


def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        sys.exit(f"curl failed: {p.stderr.strip()[:300]}")
    return p.stdout


def upload(base, email, token, path, issue):
    out = run(["curl", "-sS", "-u", f"{email}:{token}", "-X", "POST",
               "-H", "X-Atlassian-Token: no-check",
               "-F", f"file=@{path}",
               f"{base}/rest/api/3/issue/{issue}/attachments"])
    try:
        return json.loads(out)[0]["id"]
    except Exception:
        sys.exit(f"unexpected upload response for {path}: {out[:300]}")


def media_uuid(base, email, token, att_id):
    """The media UUID lives in the redirect Location, not in the attachment JSON."""
    headers = run(["curl", "-sS", "-D", "-", "-o", "/dev/null", "-u", f"{email}:{token}",
                   f"{base}/rest/api/3/attachment/content/{att_id}"])
    m = re.search(r"^location:\s*(\S+)", headers, re.I | re.M)
    if not m:
        sys.exit(f"no redirect Location for attachment {att_id} — cannot resolve media uuid")
    loc = m.group(1)
    u = re.search(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})", loc)
    if not u:
        sys.exit(f"no uuid in Location: {loc[:200]}")
    return u.group(1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("issue")
    ap.add_argument("--intro", required=True)
    ap.add_argument("--image", action="append", required=True, metavar="PATH=CAPTION")
    ap.add_argument("--outro", default=None)
    ap.add_argument("--execute", action="store_true")
    a = ap.parse_args()

    pairs = []
    for item in a.image:
        if "=" not in item:
            sys.exit(f"--image must be PATH=CAPTION, got {item}")
        path, caption = item.split("=", 1)
        if not os.path.exists(path):
            sys.exit(f"missing image: {path}")
        pairs.append((path, caption))

    base, email, token = creds()
    if not a.execute:
        print(f"[dry-run] would upload {len(pairs)} image(s) to {a.issue} and embed them inline:")
        for p, c in pairs:
            print(f"  {os.path.basename(p)} — {c}")
        print("  re-run with --execute")
        return

    content = [{"type": "paragraph", "content": [{"type": "text", "text": a.intro}]}]
    for path, caption in pairs:
        att = upload(base, email, token, path, a.issue)
        uuid = media_uuid(base, email, token, att)
        print(f"  uploaded {os.path.basename(path)} → attachment {att} → media {uuid}")
        content.append({"type": "paragraph",
                        "content": [{"type": "text", "text": caption,
                                     "marks": [{"type": "strong"}]}]})
        content.append({"type": "mediaSingle", "attrs": {"layout": "center"},
                        "content": [{"type": "media",
                                     "attrs": {"type": "file", "id": uuid, "collection": ""}}]})
    if a.outro:
        content.append({"type": "paragraph", "content": [{"type": "text", "text": a.outro}]})

    tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    json.dump({"body": {"type": "doc", "version": 1, "content": content}}, tmp)
    tmp.close()
    out = run(["curl", "-sS", "-u", f"{email}:{token}", "-X", "POST",
               "-H", "Content-Type: application/json", "-d", f"@{tmp.name}",
               f"{base}/rest/api/3/issue/{a.issue}/comment"])
    os.unlink(tmp.name)
    try:
        cid = json.loads(out)["id"]
    except Exception:
        sys.exit(f"comment failed: {out[:400]}")
    # verify the media actually landed in the stored body
    stored = run(["curl", "-sS", "-u", f"{email}:{token}",
                  f"{base}/rest/api/3/issue/{a.issue}/comment/{cid}"])
    n = stored.count('"type": "media"') + stored.count('"type":"media"')
    print(f"  comment {cid} posted with {n} inline image(s) — verified in the stored body")
    if n != len(pairs):
        sys.exit(f"expected {len(pairs)} inline images, stored body has {n}")


if __name__ == "__main__":
    main()
