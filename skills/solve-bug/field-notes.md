# solve-bug — field notes (Piqk)

Hard-won recipes the phases point at. Consult the section for the phase you're in.
Everything here is Piqk-specific; there is no WebTrader/Sirix/Jenkins content.

## Intake — attachments & a reopened ticket (phase 1)

- Jira REST creds are in **`~/.local/secrets.env`** (`JIRA_BASE_URL`, `JIRA_EMAIL`,
  `JIRA_API_TOKEN`). The Atlassian MCP enumerates attachments but does **not** hand
  you bytes — download with
  `curl -sL -u "$JIRA_EMAIL:$JIRA_API_TOKEN" <JIRA_BASE_URL>/rest/api/3/attachment/content/{id} -o <file>`.
- **Video attachments → frames** with `ffmpeg` (`-vf fps=3` around the suspect
  moment; 1 fps can miss the failure). On a **reopened** ticket with several videos,
  match each to its comment by the dates/state visible in the frames, never by
  filename or attachment order.

## Jira transitions for the autonomous walk (verified 2026-07-29)

All enumerated with `getTransitionsForJiraIssue` on real Bug-type tickets. **Never
discover a transition by attempting one** — that mutates the ticket.

| from → to | id |
|---|---|
| To Do → In Progress | **333** |
| Reopen → In Progress | **353** |
| In Progress → **On Hold** | **473** |
| In Progress → Code Review | **433** |
| Code Review → Awaiting TL Merge | **2** |
| Awaiting TL Merge → **Waiting For Deployment To QA ENV** | **4** |

- **On Hold (473) requires a reason field.** The transition screen validates
  `customfield_12019` "On Hold Reason" (a picklist) even though
  `expand=transitions.fields` reports it `required:false`. A bare
  `{"transition":{"id":"473"}}` → **400 `["Please add Reason"]`**. Send it:
  `{"transition":{"id":"473"},"fields":{"customfield_12019":{"value":"<option>"}}}`.
  Allowed values include `Awaiting Core Team Development`, `Awaiting Product
  Clarification`, `Awaiting QA`, `Awaiting External Provider`, `Awaiting Design
  Update`, … — pick the one matching *why* it's parked (a fix needing crypto/core
  dropdown = Core Team Development; a decision needed = Product Clarification).
  Lesson: `editmeta`'s `required` flag is not authoritative for transition-screen
  validators — if a transition 400s with "add X", set that field and retry.
- **`Awaiting TL Merge` is unavoidable** — it is the only route to 11353. Pass
  through it in one go after the merge lands; never leave a ticket resting there,
  because that status claims a human TL is about to merge something already merged.
- **No transition out of In Progress requires any field** (checked with
  `expand=transitions.fields`), so the 20m worklog is house convention, not a
  validator. Log it, but never treat a missing worklog as a blocker.
- The merger owns `433 → 2 → 4`. A fixer only ever applies `333`/`353` (pick-up) and
  `473` (hold).

## Holding a ticket (any stop condition)

Three writes, always together — a hold with any one missing is worse than no hold,
because the work silently stalls with nothing explaining why:

```bash
# 1. the comment: why, and what would unblock it
curl -sS -u "$JIRA_EMAIL:$JIRA_API_TOKEN" -X POST -H "Content-Type: application/json" \
  "$JIRA_BASE_URL/rest/api/3/issue/<KEY>/comment" \
  -d '{"body":{"type":"doc","version":1,"content":[{"type":"paragraph","content":[
      {"type":"text","text":"Autonomous fix stopped: <reason>. To resume: <what is needed>."}]}]}}'
# 2. On Hold
curl -sS -u "$JIRA_EMAIL:$JIRA_API_TOKEN" -X POST -H "Content-Type: application/json" \
  "$JIRA_BASE_URL/rest/api/3/issue/<KEY>/transitions" -d '{"transition":{"id":"473"}}'
# 3. the run report
python3 ~/.agents/skills/solve-bug/scripts/runs.py hold <runId> \
  --reason "<reason>" --needed "<what is needed>"
```

Write the comment for **the human who picks it up tomorrow**, not for a log: name the
surface, what you tried, and the single thing that would let it proceed.

## The two boards — both mandatory

| board | holds | who writes |
|---|---|---|
| `.pin-board` | **intent**: epic/task/subtask breakdown at planning time, status as work proceeds, and every `decision` / `shortcut` / `tech-debt` / postponement. Also drives commit-per-pin. | every session, own items only |
| `.runs` | **execution**: what this run did — scope, evidence, gates, review, PRs, transitions, holds. | only the owning run (merger advances the queue) |

Neither replaces the other. Dropping the pin-board loses the *why* and the deferred
work; dropping `.runs` leaves a human unable to audit an autonomous merge.
`runs.py` reference: `new`, `phase`, `set` (dotted paths), `hold`, `enqueue`,
`queue`, `render`, `lint`, `gc`. Full schema in `.runs/README.md`.

## Scope adjudication (phase 1)

Replaces the old "ask the human if the scope is right" stop. Two independent reads
of the ticket; the human is called only when they genuinely conflict.

**Both sides emit exactly this object:**

```json
{"surface": "piqk-app | crm-admin | piqk-server | crm-service | crypto-service | <other>",
 "repos": ["piqk-app"],
 "defects": [{"id": "D1", "symptom": "...", "expected": "...", "actual": "..."}],
 "confidence": "high | low",
 "unreadable_attachments": ["video2.mp4"]}
```

**Spawning the verifier — blinding is the whole point.** Give it the raw ticket
material only: summary, description, the newest decisive comments, and the
attachment frames you extracted. Never your scope, your Actual/Expected, your
candidate files, or any hint of what you concluded. Anchored on your answer it
agrees ~always, and the gate becomes theatre that costs tokens.

```
You are scoping a Piqk bug ticket independently. Below is the raw ticket and its
attachments. Produce ONLY the scope object (schema above). Do not propose a fix.
If the ticket supports more than one reading, say confidence "low" rather than
picking one. List any attachment you could not read.
<raw ticket + frames>
```

**Comparing — on fields, never prose.** Free-text scopes never match verbatim; a
prose diff yields false disagreement on wording and false agreement on vagueness.

| outcome | condition | action |
|---|---|---|
| **agree** | same `surface`, same `repos` set, same defect count, both `high`, no unreadable attachments | proceed, no human stop |
| **union** | scopes differ *only* in defect count | take the superset and continue — one side missed one; phase 3 repro settles it |
| **escalate** | different surface or repo set · either `confidence: low` · any unreadable attachment | stop, show both objects side by side |

**Why the repro still rules.** Agreement between two same-model agents is weak
evidence — they share a model and the same ticket text, so ambiguity biases both
the same way. The real scope check is phase 3: a screenshot of the bug actually
reproduced. If repro fails, or shows something different from the agreed scope,
**stop and escalate** no matter how confidently the two agents agreed.

**Log every adjudication** (one JSON line) to
`~/.agents/skills/solve-bug/.scope-adjudications.jsonl`:
`{"ticket","outcome":"agree|union|escalate","mine":{…},"verifier":{…}}`.
The split rate is the evidence for whether to add a tier-2 **codex** verifier in a
herdr pane — a different *vendor* is the only thing that truly decorrelates these
errors, but it costs a pane spawn, a sentinel file and output scraping per ticket.
Not worth building until the log shows tier 1 actually splits.

## Worktree + piqkenv discipline (phase 2)

- **Branch name lowercase**, `feature/<env>` under `<repo>/.worktrees/<env>`; the
  **same `<env>` across every touched repo** so `piqkenv` groups them as one env
  (`piqkenv/src/discovery.js` strips the `feature/` prefix).
  ```bash
  cd ~/work/piqk/<repo> && git fetch origin
  git worktree add .worktrees/<env> -b feature/<env> origin/main
  ```
- **node_modules:** symlink a worktree's `node_modules` to main's is fine, but
  **NEVER `npm ci` through a symlink** (it wipes main → exit 127). Installs target
  main; break-symlink + real install only on lock divergence.
  **piqk-app is the exception** — Next 16 + Turbopack panics on a symlinked
  `node_modules` (hangs ~700% CPU); give piqk-app worktrees a **real `npm ci`** then
  `rm -rf .next`.
### Raise your own slot (don't share, don't ask)

`piqkenv` has a headless surface built for exactly this — several agent flows
running at once, each with a full isolated stack:

```bash
cd ~/work/piqk/piqkenv
./piqkenv slots                                  # who holds what
./piqkenv up --env <env> --json > $SCRATCH/slot.json
./piqkenv down --slot <n>                        # release (phase 10)
```

| slot | offset | who | Mongo | Redis | Kafka ns | Next dist |
|---|---|---|---|---|---|---|
| 0 | +0 | **human's dev** — never take it | `piqk` | 6379 | `piqk-local` | `.next` |
| 1 | +10 | **human's stg** — never take it | `piqkSTG` | 6380 | `piqk-stg` | `.next-stg` |
| 2..5 | +20..+50 | agent flows (`--slot auto`) | `piqk_s<n>` (clone of `piqk`) | 6379+n | `piqk-s<n>` | `.next-s<n>` |

- Slot n's ports are `base + n*10` → slot 2 is CRM 4031 / CS 4032 / PS 4033 /
  app 3020 / crm-admin 3021.
- **The database is a fresh clone of dev `piqk`** (~7.5k docs, ~2s), so realistic
  repro data is there AND destructive seeding is safe — it can't reach dev or
  another flow. It's dropped on `down`.
- **Export the descriptor's `env` block** into every shell that touches the stack.
  Those key names are exactly what `piqk-app/e2e/helpers/env.ts` reads
  (`PIQK_APP_URL`, `CRM_URL`, `CRYPTO_URL`, `PIQK_SERVER_URL`, `MONGO_URL`,
  `MONGO_DB_NAME`, `REDIS_URL`, `REDIS_KEY_PREFIX`), so Playwright follows your
  slot with no other change. Add `--with-secrets` to also get `E2E_JWT_SECRET`
  (omitted by default — descriptors get pasted into reports; never paste that one).
- **`unhealthy` must be empty.** `up` waits on each service's real health check
  and reports what didn't come up; the descriptor's `logs` map points at each
  service's `logs/combined.log`. Never repro against a half-up stack.
- Services run as **detached daemons**, not in your shell and not in a
  multiplexer — they outlive the command. Debug them with
  `tail -f <logs[SVC]>`; the slot registry (`~/.piqk-slots/<n>.json`) holds their
  pgids, which is how `down` kills them.
- **Only ever `down` your own slot number**, read from your descriptor.
- A crashed flow leaves a registry entry with nothing alive; the next `up` reaps
  it automatically. Nothing to clean by hand.

### Legacy note

Before slots existed this skill assumed the user had `piqkenv` running and
verified it by hand (`lsof -iTCP:4011 -sTCP:LISTEN`, `curl localhost:4011/api/crm/health/live`).
That's still the right check when you're deliberately working on **their** slot 0
stack — but for a bug flow, raise your own instead.
- **Pin cwd + paths.** Bash cwd drifts back to the umbrella after some tools —
  prefix commands with an explicit `cd`, use `git -C <abs-repo>` for git, and
  Read/Edit only worktree-absolute paths. Never `rm -rf` a variable path; tear down
  with `git worktree remove <explicit path>` + prune, only your own worktree.

## Reproduce / prove live — piqk-app Playwright (phases 3 & 6)

Harness: `piqk-app/e2e` (`@playwright/test`, browsers installed). Run a throwaway
script with `NODE_PATH="$(pwd)/node_modules"` from `piqk-app/e2e`, screenshot to the
scratchpad, read the screenshot back to confirm. Drive the **worktree-served**
instance (piqkenv's port), not main.

- **Export `JWT_SECRET` matching the running services** or every session reads as
  expired (mass `session=expired`) — a classic phantom-fail.
- **Run the branch's e2e copy**, not the main-checkout's; and when triaging flakes,
  A/B against main to separate env flakiness (~17-20 known flaky: SMS 502 / seed /
  state-drift) from a real regression.
- **CRM login:** `admin@piqk.com` / `Admin123!` (seeded ADMIN). crm-admin form-login
  races — poll `crm_token` then fallback-seed via `/operations/auth/login`;
  `@playwright/test` is CJS (abs-path default import).
- **Screenshot transient toasts before they auto-dismiss** (~5s, shorter than
  step-to-step latency): temporarily bump the toast TTL for the capture, then
  **revert before finalizing** (phase 8). CSS-module hashes re-hash on HMR — query
  the live class first, then screenshot.
- **Never leave `.playwright-mcp/` behind** — its a11y snapshots write plaintext
  credential-field values to disk. Purge in housekeeping (phase 10).
- **BFF routing gotcha:** piqk-server modules mounted via
  `RouterModule.register([{path:'api/kyc',module}])` need a **relative**
  `@Controller('...')` (a full path doubles → 404). Route-stubbed Playwright can't
  catch BFF routing — curl the real route (401 = exists, 404 = missing).
- **Cross-origin `<img>` of piqk-server assets:** helmet's global CORP blocks it in
  the dev split-port setup (:3000 → :4013); needs route-scoped
  `Cross-Origin-Resource-Policy: cross-origin`. Only a browser `<img>` reveals it —
  build/tsc/curl pass.

## Root cause + Figma (phase 4)

- **GitNexus KG first** (`gk` = GitNexus; all 5 repos indexed): `query`, `context`,
  `impact`/`api_impact`, `route_map` to orient and get blast-radius — then open the
  files it surfaces. `impact` wants a **symbol**, not a file path. If it errors with
  "DB v41 vs build v40", the global binary is stale: `npm i -g gitnexus@latest` +
  reconnect the MCP.
- **Figma via REST**, not the MCP (6 calls/month seat cap). `FIGMA_TOKEN` in
  `~/.local/secrets.env`; helper `piqk-ui-task/figma-frame.sh`. Compare **design
  tokens to the Figma hex/px** per property (bg, border, radius, padding, gap, each
  text colour/size/weight) — the app tokens derive from the same Figma, so faithful
  = token equals Figma value. Fix only where the token diverges or you deviated.

## Compile + test gates (phases 5, 7, 9)

- **Compile in a live piqkenv worktree = `tsc --noEmit` only** — never `next dev`/
  `next build`/`nest build` (clobbers the shared `.next`/`dist` piqkenv is serving →
  crash). For the *pre-merge* real-build confidence on a Next app, run an isolated
  offline `next build` with a distinct `NEXT_DIST_DIR` (don't clobber piqkenv) —
  tsc-only misses prerender-time fetch hangs.
- **piqk-server tests false-green on node < 21:** `node --test 'test/**/*.test.ts'`
  runs ZERO tests + exits 0 (no glob expansion). Expand the glob (`test/*.test.ts`)
  or use node ≥ 21; verify real test counts printed.
- Pre-merge suites (run per touched repo, from `~/work/piqk/CLAUDE.md`): crm-service
  Jest, crypto-service Jest + `test:e2e:mt` / `test:e2e:tiers` (only if
  orders/pricing/MT/FX touched), piqk-server `npm test`, piqk-app e2e.

## Equalizer pre-gate (phase 9, trade/pricing fixes only)

Before any trade-flow test/e2e, ensure live Bitstamp USD ≥ $200:
```bash
cd ~/work/piqk/crypto-service
node --env-file=.env.local scripts/bitstamp-equalize-usd.mjs             # dry-run
node --env-file=.env.local scripts/bitstamp-equalize-usd.mjs --execute    # real market sell
```
Review the dry-run proposal in the same session, then `--execute`. Exit 0 = above
floor / sold cleanly; 1 = error/no sellable crypto/bad creds (gate blocks); 2 =
raise exceeds per-run cap (human investigates). **Never solo a money-moving
decision** — default to the non-charging path and stop+ask if a charge is required.

## Jira REST — status / worklog / comment / evidence (phases 2, 8, 9)

Creds in `~/.local/secrets.env`. One python/urllib round-trip per operation, not one
curl per field.
- **Enumerate before moving.** `getTransitions(includeUnavailable)` + a JQL status
  probe FIRST; fire the transition whose `to` steps toward the target. Never
  transition just to discover reachability (a wasted mutation).
- **RND transition map (from memory `reference-rnd-jira-workflow`):**
  - → **In Progress:** Story transition **333**, Sub-task **11** (→ status 10179).
  - → **Waiting Merge to version:** transition **10165** (from *Waiting Bug Fix* =
    14; from QA = 12 then 14). **Never** transition 13 (that's back to QA — where
    the bug came from).
  - A merged/dev ticket's resting path (not this skill's job): log time → 433 Code
    Review → 453 Waiting For Deployment To QA ENV (11353).
- **Worklog:** `POST /issue/<K>/worklog {"timeSpent":"40m"}`.
- **Evidence = INLINE ADF media in a comment, NOT a repo commit, NOT bare
  attachments** (your rule `feedback-qa-evidence-not-in-repo`): upload the image
  (`POST /issue/<K>/attachments`, header `X-Atlassian-Token: no-check`) → follow the
  attachment content redirect to grab the **media UUID** → build a v3 ADF comment
  with a `media` node (`type:"file"`, the UUID, `collection:""`). Repo commits bloat
  the tree and private-repo raw embeds 404 — don't do them.

## Commit / PR discipline (phase 8)

- **Commit-per-pin, per repo it touched.** Stage exactly that pin's files
  (`git -C <abs-repo> add <explicit paths>`) — not another pin's in-flight changes
  in the same worktree. Message references the pin/ticket id
  (`RND-<n>.<k>: <what>`), ends with the global co-author trailer. Only commit green.
- **PR per touched repo** to `origin` (GitHub `LeveratePiqkProtect/<repo>`); cross-link the
  PR bodies when a bug spans repos. **Never** push a branch ref onto `origin/main`,
  never merge — the skill stops at the open PR. When the user later merges, it's
  `gh pr merge --merge --delete-branch` (their call, batched).

### Associating the PR with the ticket

The ticket's **Development** panel (where a PR would normally surface) is fed
*only* by a connected dev-tool integration. As of 2026-07-27 this Jira site has
none — `/rest/dev-status/latest/issue/summary?issueId=<id>` returns
`byInstanceType: {}` with all counts 0, and the panel shows "Connect development
tools". **There is no API to write into that panel**; `/rest/dev-status/` is
read-only. So:

- **Always** add a **remote issue link** per PR (works today, no integration
  needed, lands under the ticket's Links):
  ```bash
  curl -sS -u "$JIRA_EMAIL:$JIRA_API_TOKEN" -X POST -H "Content-Type: application/json" \
    "$JIRA_BASE_URL/rest/api/3/issue/<KEY>/remotelink" \
    -d '{"globalId":"pr-<repo>-<num>","application":{"type":"com.github","name":"GitHub"},
         "relationship":"is implemented by",
         "object":{"url":"<pr-url>","title":"<repo> PR #<num> — <summary>",
                   "icon":{"url16x16":"https://github.githubassets.com/favicon.ico"}}}'
  ```
  A stable `globalId` makes it idempotent — re-posting updates that link rather
  than adding a duplicate.
- **Also** write the PR links into **Dev Notes** (`customfield_11739`) — visible in
  the ticket body rather than tucked under Links:
  ```bash
  python3 ~/.agents/skills/solve-bug/scripts/jira-dev-notes-prs.py <KEY> \
    --pr "piqk-app#21=https://github.com/LeveratePiqkProtect/piqk-app/pull/21" --execute
  ```
  **Never hand-roll this `PUT`.** Three traps, all verified 2026-07-27:
  1. Dev Notes is a `textarea` custom field → REST v3 wants an **ADF document**,
     not a string.
  2. `editmeta` exposes only `operations: ['set']` — there is no append, so the
     only correct approach is read-modify-write of the whole document.
  3. The field is **not empty** on RND bugs: it carries the team's 5-section
     template (Happy Flow Video / Edge Cases / Blast Radius / Credentials /
     Additional Notes). A blind `set` silently destroys it.

  The script handles all three, skips URLs already present (safe to re-run), and
  re-reads the field to verify the write landed. It defaults to **dry-run** —
  pass `--execute` to actually write. It shells out to `curl` on purpose: the
  python.org python3 here has no CA bundle (`CERTIFICATE_VERIFY_FAILED`).
- **Also** put the canonical key `RND-<n>` (with the hyphen) in the branch name,
  every commit subject and the PR title, with `Fixes RND-<n>` in the body. Costs
  nothing now and means the Development panel back-fills automatically the day
  someone connects the GitHub-for-Jira app for the `LeveratePiqkProtect` org
  (connected 2026-07-27 14:36, all repos in scope — backfill is asynchronous, so
  historical tickets populate with a lag; new pushes link within seconds). Note the
  old env-name style (`rnd1280-guesthome`) does **not** match — Jira needs
  `rnd-1280`.

## Adversarial review without /code-review (phase 7)

`/code-review` and `/security-review` are user-invoked only. Substitute the
`branch-code-reviewer` agent, or a review subagent handed the `git diff` + the
before/after intent, told to hunt correctness / regression / cross-surface parity
(piqk-app ↔ crm-admin ↔ BFF) / i18n (EN+HE) / shared-component blast-radius /
tenant-isolation issues and return findings by severity. Fix every real finding,
re-run the touched-repo gates, re-prove live if UI changed. Flag `/security-review`
to the user for any auth / permission / PII / secret / migration diff.
