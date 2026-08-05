---
name: solve-bug
description: Autonomously solve one Piqk (RND board) bug end-to-end from its ticket key — UI OR backend/logic/data/async — reproduce with a concrete proof in the medium the bug lives in (screenshot for UI; a failing→passing test, HTTP response, DB state, or log for non-UI), root-cause via the GitNexus KG, implement the fix, prove it fixed, review, merge it (its own PRs, via gh) and move the ticket to Waiting For Deployment To QA ENV. No human gates on the happy path; anything doubtful is parked On Hold with a Jira comment explaining why. Writes a live run report to .runs/ and keeps using .pin-board for intent. Runs in parallel with other runs, each on its own piqkenv slot. Use when the user gives an RND key and wants it worked autonomously ("solve RND-432", "fix this ticket end to end"), or invokes /solve-bug <KEY> [--gated]. For just reading a ticket, don't use this.
---

# solve-bug — one RND bug from ticket key to merged, autonomously

Take one Piqk bug from its ticket key to a merged fix in QA, moving through
**gates**. Each gate ends a phase one of two ways: a **proof** is produced, or the
ticket is **held** with a reason. Nobody is waiting to answer a question, so a gate
that can't be satisfied becomes a hold — never a guess.

The proofs are the point, and more so now that no human reviews before the merge:
**never claim reproduced or fixed without a concrete artifact** — and the artifact
takes the shape of the bug. A UI bug's proof is a screenshot (judged against the
Expected + any Figma, by measured pixels). A **backend/logic/data/async** bug's
proof is just as concrete but a different medium: a **failing→passing test**, an
**HTTP request/response**, a **DB query result**, or a **log line**. See *Proof
taxonomy* below. What is never proof: prose, "the code looks right", or a green
build — build/tsc pass on the exact bugs that only running the system reveals.

**This flow handles non-UI bugs.** A bug not being screenshot-able is **never** a
reason to hold — it just means the proof is a test/HTTP/DB/log artifact instead of
an image. (RND-1338 was a backend route-shadowing bug proved by an API probe + a
unit test, no screenshot needed for the mechanism.) Only stop for a real stop
condition, not because "there's nothing to screenshot."

## Proof taxonomy — pick the medium the bug lives in

Every bug needs a **red** artifact (the actual broken behaviour) and a matching
**green** one (it now behaves) captured **against your running slot**, not asserted:

| bug class | red → green proof |
|---|---|
| **UI / visual** | Playwright before/after **screenshots** (the current default) |
| **API / contract** | `curl` the endpoint → wrong status/body, then correct (save both) |
| **backend logic / calculation / money-math** | a **unit/integration test at the root cause** that fails first, then passes |
| **data / DB state** | a `mongosh` query showing the wrong stored state, then correct (+ any migration) |
| **event / Kafka / async** | produce the trigger, observe the wrong consumer effect (log/DB), then the right one |
| **concurrency / atomicity** | a contention/property test that's red under load, then green |
| **cron / scheduled** | trigger the job, capture wrong output → right output |

The rule is identical across media: **no red artifact = stop condition 1 (hold);
no matching green artifact = not fixed.** Record every artifact path in the run
file (`evidence`).

**This skill is autonomous end to end.** It takes the ticket from *To Do / Reopen*
to **Waiting For Deployment To QA ENV** — including **merging its own PRs** — with no
human stop on the happy path. Each run merges the PRs it opened, via `gh`; there is
no separate merge worker. Many runs execute in parallel in separate sessions.

There is no git-level race to serialize away: GitHub merges each PR atomically
against the current `main`, so a later merge either applies cleanly or reports a
conflict you redo. Each run makes its *own* merge safe by updating the branch with
latest `main` and re-running that PR's CI **before** merging (phase 9) — which is
where a stale-base break would show up. (The one residual is semantic merge-skew
between two truly-simultaneous same-repo merges; GitHub's native merge queue is the
fix if that ever actually bites — not a bespoke worker.)

The human's involvement is reduced to two things, and both must therefore work:
- **The report** — `.runs/<TICKET>-<runId>.json`, written *as each phase completes*,
  rendered by `runs.py render`. Everything goes in it.
- **The holds** — anything doubtful is parked on the ticket with a comment, not
  guessed at. See *Stop conditions*.

**Two boards, both mandatory, different jobs.** `.pin-board` is **intent**: the
task/subtask breakdown at planning time, status as work proceeds, and every
deferral / shortcut / tech-debt / decision — plus it drives the commit-per-pin
discipline. `.runs` is **execution**: what this run actually did. Keep using the
pin-board exactly as before; `.runs` is additional, never a replacement.

**Compose Piqk's own substrate, don't reinvent.** Reach for existing Piqk skills
and infra rather than hand-rolling: `piqkenv` + the worktree HARD RULE for the
stack, the GitNexus KG (`gk`) for orientation, `/pin-board` for tracking,
`piqk-app/e2e` Playwright for proofs, the Jira REST creds for ticket ops. Repo-,
tool-, and Jira-specific recipes and gotchas live in
[`field-notes.md`](field-notes.md) — open the section for the phase you're in.

## Autonomy

**There are no per-phase human gates.** Every former "stop for OK" becomes a
recorded decision in the run file plus its proof. You either proceed, or you
**hold** — there is no waiting-for-an-answer state, because nobody is watching.

**ABSOLUTE RULE — never ask; act.** Outside `--gated` you must **NOT** call
`AskUserQuestion`, render a numbered menu, or end a turn waiting for a human to
choose. There are exactly two outcomes for any decision point: **proceed** (record
it in the run file and continue) or **hold** (execute the hold below — comment +
473 + run file — then finish). A stop condition is a hold you *execute*, not an
option you *offer*. If you catch yourself writing "How do you want to proceed?" or
"1. Hold (recommended) 2. Override…", stop: pick the hold and do it.

- **Being invoked directly by a human is NOT `--gated`.** A person typing
  `/solve-bug RND-x`, or having moved the ticket to In Progress by hand, does
  **not** license you to ask — the default is autonomous regardless of who
  launched you. Only the literal `--gated` flag (or an explicit waiver phrase in
  the prompt, e.g. "skip stop-condition 7") turns asking back on.
- **Money/auth is worked, not bounced — but only through the Security Gate.**
  A money/balance/ledger-logic, auth/permissions, secrets, or migration fix is
  **not** an auto-hold and **not** a menu to offer the user. You implement it and
  take it through the mandatory **Security Gate** (below); it merges only if that
  gate passes, and holds (with the gate's findings) only if it fails. Still never
  *ask* — the gate decides, not a human prompt.
- **Phase 1 scope** is adjudicated by a **blinded** second agent (below). Conflict →
  hold, not a question. Scope is reading comprehension, where two independent reads
  genuinely help; do **not** extend this to phase 4, where choosing an approach is a
  judgement call with legitimate alternatives and agreement proves much less — there
  you *decide and record*, you do not ask.
- **`--gated`** restores the old behaviour (stop at each phase) for when you *are*
  watching and want to steer. It is the exception now, not the default.

**Stop conditions are the safety valve, and they must fire loudly.** The risk you
are carrying is that this skill's own verification is the only thing between a bad
fix and `main`. That is acceptable only while every gate below **fails loudly
instead of being worked around**. Never soften a gate to keep a run moving: a held
ticket costs someone five minutes, a bad merge costs a lot more.

## Stop conditions → hold the ticket, don't guess

When any of these fires, **stop implementing** and do all three, never one without
the others:

1. **Jira comment** — why you stopped, and precisely **what's needed to resume**.
2. **`On Hold`** — transition **473** from In Progress.
3. **Run file** — `runs.py hold <runId> --reason … --needed …`.

Then finish cleanly: release your slot, leave the worktree, and report.

| # | condition |
|---|---|
| 1 | **The bug does not reproduce.** No **red artifact** in any medium (see *Proof taxonomy*), no fix — this is the hard gate the whole flow rests on. "It isn't screenshot-able" is NOT this condition: use a test / HTTP / DB / log artifact and proceed. |
| 2 | **The ticket contradicts the PRD.** |
| 3 | **The ticket contradicts an older ticket** — a decision already taken (check `PLANS/`, the pin-board's `decision` items, and linked issues). |
| 4 | **Scope adjudication conflict** — different surface or repo set, either side low confidence, or an attachment neither agent could read. |
| 5 | **Gates still red after 3 honest attempts** — so a run can't grind forever. Report what you tried. |
| 6 | **GitNexus `impact` returns HIGH/CRITICAL** on a shared symbol. (It under-reports enums/consts — grep value-symbols too.) |
| 7 | **The fix changes money/balance/ledger *logic* (amounts, balance math, reservations, settlement, pricing), auth/permissions, secrets, or runs a data migration.** This is **NOT an automatic hold** — it **mandates the Security Gate** (see below) before merge, and you hold only if that gate can't be cleared. Judge by what the change *does*, not where it sits: a cosmetic/annotation field added inside a money-movement function is not even in scope; altering how much moves, who's authorized, or rewriting stored records **is**. When unsure, treat it as in scope (gate it). |
| 8 | **A merge conflict or post-update CI failure you can't resolve cleanly** after 3 attempts (phase 9). |
| 9 | **A trade/pricing fix while the Bitstamp float is under the floor** — hold; the equalizer's `--execute` sells real crypto and is **out of scope for this skill entirely** (see phase 9). |

A hold is a **success** for this skill, not a failure. The failure mode to fear is
an unjustified fix merged autonomously.

**Whole-ticket hold is the default, even when part of the fix is safe.** When a
ticket splits into a safe part (e.g. a forward-only code change) and a
stop-condition part (e.g. a ledger backfill), do **not** merge the safe part and
hold the rest. Two reasons: the safe part usually doesn't satisfy the ticket's own
repro on its own (a forward-only fix leaves the reported rows unchanged, so phase 6
can't prove it solved), and a merged-but-not-actually-fixed ticket reads as done
when it isn't — a worse failure than a clean hold. Hold the whole ticket, and in
the comment name **both** the safe part you *could* do and the part that needs a
decision, so the human can say "ship the safe part" if they want it. Only split
when the user has explicitly asked the flow to prefer partial progress.

## Security Gate — money / auth / secrets / migrations (no flag, no human click)

A stop-7 fix (money/balance/ledger logic, auth/permissions, secrets, or a data
migration) **is worked autonomously and merged with no human in the loop** — but
only after it clears this gate. The gate is the automated stand-in for the human
`/security-review` we used to require: it must *prove* the property that makes the
change safe, not just that it compiles. **Default is REJECT** — the gate passes
only on affirmative green evidence; anything unproven fails and the ticket holds.

Run it as **phase 7.5**, after the normal adversarial review and before the PR.
All three parts are mandatory; a miss on any → **hold** with the findings (comment
+ 473 + run file), never merge.

1. **A safety test that turns the risk red→green — this is the crux.** The fix
   isn't provable without it. Match the risk class:
   - **money/ledger atomicity** (e.g. RND-1124): a **concurrency/contention test** —
     hammer the path with parallel/interleaved calls + injected mid-transaction
     failure; assert no double-spend, no lost decrement, reservation released iff
     committed, idempotent on retry. Red on the old code, green on the fix.
   - **balance/amount/pricing math:** a unit/property test pinning the exact
     figures (rounding, Decimal128, fee direction), red→green.
   - **auth/permissions:** a test that **performs the exploit and asserts it's now
     blocked** — the unauthorized caller gets 401/403, the token is no longer
     readable/stealable, the bypass 404s. Red→green.
   - **secrets:** assert the secret is absent from logs/responses/client bundle.
2. **Adversarial security review with teeth (REJECT-default).** Spawn a review
   subagent (or a small panel) handed the diff + threat model, prompted to **find**
   auth bypass, privilege escalation, fund loss / double-spend, race conditions,
   injection, secret leakage, and — for migrations — data loss / non-idempotency /
   no-rollback. It must default to *unsafe* unless it can affirmatively argue each
   is closed. **Any unresolved high/critical → hold**, don't self-clear.
3. **Migrations must be dry-run + idempotent + reversible.** Run it against your
   slot's **cloned** DB first (never dev/prod), assert the row counts/shape are
   exactly as intended, **run it twice** (idempotent), and record how to reverse
   it. No dry-run evidence → hold.

Record the gate outcome in the run file (`securityGate: {tests, review, migration,
verdict}`) — a green verdict there is the precondition phase 9 checks before
merging. **The gate governs merging money/auth *code*; it never authorizes the flow
to *move* money** — the Bitstamp equalizer stays `--execute`-forbidden (phase 9),
because actually selling funds is a different act from merging a code change.

## Cross-repo scope

A Piqk bug may span several of the 5 repos (`piqk-app`, `piqk-server`,
`crm-service`, `crypto-service`, `crm-admin-next`). Treat the touched-repo set as
something you discover during root-cause (phase 4), not something you fix upfront:
- Start with the repo(s) the ticket points at; **add a worktree in another repo
  the moment root-cause proves the fix reaches into it** — always with the **same
  env-name** so `piqkenv` groups them as one env (worktree HARD RULE).
- Every per-repo action downstream (build, test, commit, PR) runs **once per
  touched repo**. Commit exactly that repo's files (commit-per-pin HARD RULE).

## Piqk hard rules that bind every phase

These are not optional and several are invisible to `tsc`/build — enforce them
inside the relevant phase, not as an afterthought:
- **GitNexus KG first** for orientation/blast-radius (phase 4) — `gk`, not manual
  grep-mapping. Re-index touched repos is a post-merge concern (out of skill scope).
- **Verify against the *running piqkenv instance*, in the bug's medium** (phases 3
  & 6) — build/tsc passing is never proof. UI change → Playwright in a real
  browser. Backend/logic → `curl` the endpoint, or a test that fails-then-passes.
  Data → a `mongosh` query. Async → produce the event and observe the effect. The
  mandate is the same for all: demonstrate red then green against the live system,
  never infer from the code.
- **Strings/localization** — user-facing copy resolves through the locale-reactive
  layer (`STR`/`useT` in piqk-app; `defineStrings`/`useStrings` in crm-admin-next),
  both `he` + `en`. Verify in the non-default locale (EN) when copy is touched.
- **SOLID · ≤300 lines/file · reuse over rebuild** — search for an existing
  component/util before writing one; split files you push past 300 lines.
- **CRM audit** — if the fix adds/changes a CRM_USER mutation, follow
  `crm-service/docs/AUDIT.md` (auto / `@Audit` / `auditService.log`).
- **Tenant isolation** — new/changed code paths stay tenant-mode-isolated.
- **Worktree-only** — feature work never happens in a repo's main checkout; and
  never run `next dev`/`next build`/`nest build` in a worktree piqkenv is serving
  (clobbers shared `.next`/`dist`) — use `tsc --noEmit` for the compile gate.

## Phases

1. **Claim, then intake.**

   **Claim the ticket FIRST — before any slow work — so parallel runs can't
   double-grab it.** Read its current status; if it is **not `To Do` or `Reopen`**,
   another run already owns it → **stop immediately, don't double-work** (say so).
   Otherwise transition it straight to **In Progress** (333 from *To Do*, 353 from
   *Reopen* — pick by the status you read) and open the run report
   (`runs.py new <KEY> --type <type> --start-status "<status>"`). This transition
   is the lock: the poller selects on `status IN (To Do, Reopen)`, so the instant
   you flip it no other run will pick it. Claiming first (not after intake) closes
   the window where two runs could both intake the same ticket. It also makes every
   later hold consistent — On Hold (473) always comes from In Progress.

   Then **intake.** Read the RND ticket via the Atlassian MCP + Jira REST creds
   (`~/.local/secrets.env`), and **view every attachment image/video** — download
   the bytes (`/rest/api/3/attachment/content/{id}`), sample videos to frames with
   `ffmpeg`; they carry the decisive detail (which surface, which service). On a
   reopened ticket, match each video to its comment by dates/state visible in the
   frames, not filename order. Fix the current state from Status + newest-decisive
   comments, and state **Actual vs Expected**. _Done when_ the ticket is claimed
   (In Progress), the run report exists, Actual/Expected are stated, and every
   attachment is viewed.

   **Gate — adjudicated, not human-by-default.** Write your scope as the structured
   object in [`field-notes.md`](field-notes.md#scope-adjudication-phase-1), then
   spawn a **blinded** subagent that scopes the same ticket from the raw material
   alone and emits the same object. It must never see your version — shown your
   answer it will simply agree, and you'll have bought a rubber stamp.
   - **Agree** on surface + repo set + defect count, both `confidence: high`, no
     unreadable attachment → **proceed to phase 2 with no human stop.**
   - **Defect-count mismatch** → take the **union** and carry on; one side missed
     a defect rather than contradicting the other, and phase 3 settles it — what
     you can't reproduce wasn't a defect.
   - **Genuine conflict** (different surface or repo set), **either side low
     confidence**, or **an attachment neither could read** → **hold** (you've
     already claimed, so On Hold via 473, with both scopes in the reason). Under
     `--gated`, surface both scopes to the user instead of holding.

   Compare **symptom surface + defect count**, and treat the **repo set as a
   candidate list refined at root-cause** (phase 4), not a hard match — a verifier
   naming an extra repo as a possible *fix-location* is not a conflict (that's a
   phase-4 discovery per Cross-repo scope). Append every adjudication to the log
   named in field-notes — the split rate is what decides whether a cross-vendor
   codex verifier is worth adding later.

2. **Worktree(s) + slot + pin.** Create a worktree on a **lowercase**
   `feature/<env>` branch under `.worktrees/<env>` in the repo(s) the ticket points
   at (same env-name across repos — see Cross-repo scope). Put the **canonical
   ticket key in the env name** (`rnd-1280-guesthome`, not `rnd1280-guesthome`) so
   the branch links itself to the ticket — see phase 8.

   Then **raise your own stack — don't ask the user for one and don't take theirs:**

   ```bash
   cd ~/work/piqk/piqkenv
   ./piqkenv up --env <env> --json > $SCRATCH/slot.json   # allocates a free slot
   ```

   `up` picks a free slot (2..5), gives it its own ports, its own Redis, its own
   Kafka namespace and **its own Mongo database cloned from dev `piqk`**, starts
   all 5 services detached, waits for every health check, and prints a descriptor.
   Slots 0/1 are the human's dev/stg stacks and are never taken automatically.
   Several solve-bug flows can therefore run at once — yours is isolated, so
   seeding and destructive repro steps can't touch anyone else's data.

   **Export the descriptor's `env` block into every shell that touches the stack**
   (Playwright, curl, mongosh) — `piqk-app/e2e/helpers/env.ts` reads exactly these
   names, so the whole harness follows your slot:

   ```bash
   eval "$(python3 -c "import json;print('\n'.join(f'export {k}={v}' for k,v in json.load(open('$SCRATCH/slot.json'))['env'].items()))")"
   ```

   **Verify before trusting it:** the descriptor's `unhealthy` array must be empty.
   If it isn't, read that service's log (`logs` map in the descriptor) — never
   proceed against a half-up stack. Create the `/pin-board` item(s) (`task` +
   `subtask` children, `status: planned → in_progress`). **The ticket is already
   In Progress from the phase-1 claim — don't re-transition it here.**
   **This worktree + slot are yours alone:** pin cwd + every path into them; never
   touch the main checkout, another agent's worktree, or another slot.
   _Done when_ the pin exists and `unhealthy` is empty.

3. **Reproduce → red.** Reproduce the bug live against your running slot and
   **capture the red artifact in the bug's medium** (*Proof taxonomy*) — do not
   proceed on a theory of the bug.
   - **UI:** a screenshot, via the `piqk-app/e2e` Playwright harness (CRM dev login
     `admin@piqk.com` / `Admin123!`; export a `JWT_SECRET` matching the running
     services or every session reads as expired — field-notes).
   - **API/contract:** `curl` the endpoint and save the wrong status/body (as
     RND-1338: `GET /api/crm/clients?search=zzz` still returned all 76).
   - **backend logic / money-math:** write the **unit/integration test at the root
     cause and watch it fail** — that red test *is* the repro, and it becomes the
     regression guard.
   - **data:** a `mongosh` query showing the wrong stored state.
   - **async/event:** produce the trigger, capture the wrong consumer effect
     (log/DB).
   Seed whatever state you need. _Done when_ a concrete red artifact of the actual
   broken behaviour exists and its path is in the run file. **No red artifact =
   stop condition 1** (hold). A bug that isn't screenshot-able is not a hold —
   switch medium.

4. **Root cause + best-practice plan.** Find the root cause **via the GitNexus KG
   first** (`gk` query/context/impact) → then open the exact files it surfaces.
   This is where you discover the full touched-repo set — add worktrees as needed
   (Cross-repo scope). If the ticket links a Figma, pull the exact spec via the
   figma REST helper (`FIGMA_TOKEN` in `~/.local/secrets.env`; NOT the seat-capped
   MCP) and match **design tokens**, not eyeballing. Design the fix within the
   hard rules above. _Done when_ a concrete plan + root cause + the touched-repo
   list are written. Check the plan against the PRD, `PLANS/`, and the pin-board's
   `decision` items — a contradiction is stop condition 2/3, and a HIGH/CRITICAL
   `impact` is stop condition 6. Otherwise **proceed to implement without sign-off**;
   record the plan in the run file and as pin-board items.

5. **Solve.** Implement in the worktree(s); add/adjust tests at the root cause
   (Jest unit for backend logic, e2e for UI/flow). Per **each touched repo** run the
   touched gates and report faithfully:
   - **compile:** `tsc --noEmit` (never a real build in a live piqkenv worktree).
   - **tests:** the repo's relevant suite (piqk-server: expand the glob or use
     node ≥21 — `node --test 'test/**'` silently runs zero on node 20).
   - **strings:** if copy changed, the locale check + a manual EN render.
   _Done when_ every touched-repo gate is green and reported.

6. **Prove solved.** Re-capture the **green artifact in the same medium as the red
   one** (phase 3) — the exact thing that was broken now behaving:
   - **UI:** after-images for every variant + edge state (success AND error,
     desktop AND mobile, EN AND HE if copy changed). With a Figma the bar is
     **pixel-perfect by default** — measured positions + design tokens, relax only
     if told.
   - **API/logic/data/async:** the same `curl` / test / `mongosh` query / event
     probe from phase 3, now returning the right result. The root-cause test that
     was red is now green.
   Then confirm **no adjacent surface regressed** (piqk-app ↔ crm-admin ↔ the BFF;
   for backend, the repo's relevant suite stays green). _Done when_ the green
   artifact matches Expected and its path is in the run file (`evidence`) next to
   the red one.

7. **Review → fix → re-prove.** Run an **adversarial review** on the diff — either
   the `branch-code-reviewer` agent or a review subagent handed the `git diff` +
   before/after intent, asked to hunt correctness / regression / cross-surface
   parity / i18n / shared-component blast-radius / tenant-isolation issues by
   severity. Fix every real finding, re-run the touched-repo gates, and re-prove
   live if UI changed. _Done when_ findings are resolved and gates are green again.

   **7.5 — Security Gate (only if the diff is money/auth/secrets/migration).** If
   this fix is a stop-7 change, it does **not** hold — but it may not ship until it
   clears the **Security Gate** (see that section): a red→green safety test for the
   risk class, a REJECT-default adversarial security review, and (for migrations) a
   dry-run + idempotency check on the cloned DB. Record `securityGate` in the run
   file. Gate green → continue. Gate red / unproven → **hold** with the findings.

8. **Ship — open the PR(s).** Revert any capture-only hacks (e.g. a bumped toast
   TTL). Then, **per touched repo:** stage exactly that repo's files, commit with a
   pin-scoped message (`RND-<n>.<k>: <what>` + the global co-author trailer), push
   the feature branch, and open a **PR** (`gh pr` to `origin`). Cross-link the PRs
   in each body when a bug spans repos.

   **Post the before/after proof INLINE on the ticket — a gate, not a nicety.**
   Whatever medium the proof is in (phase 3/6), it goes in a Jira comment so a
   reader sees red→green without leaving the ticket.
   - **UI (images):** use the script — the three-step media-UUID dance is easy to
     get wrong (the attachment id is *not* the media id):
     ```bash
     python3 ~/.agents/skills/solve-bug/scripts/jira-evidence-comment.py <KEY> \
       --intro "<one line: what was wrong, what changed>" \
       --image "<before.png>=BEFORE — <what it shows>" \
       --image "<after.png>=AFTER — <what it shows>" \
       --outro "<verification summary + known gaps>" --execute
     ```
   - **Backend/logic/data/async (no image):** post an ADF comment with the red→green
     artifact in a **code block** — the failing→passing test output, or the `curl`
     transcript (request + wrong response, then right response), or the before/after
     `mongosh` result. Same bar: concrete, red then green, in the comment body.
   For the image path, the script uploads, resolves each media UUID from the
   attachment content-redirect,
   builds the `mediaSingle`/`media` nodes, and then **re-reads the stored comment
   and fails if the images aren't really embedded**. Default is dry-run. Never a
   repo commit (bloat; private-repo raw embeds 404).

   **Associate every PR with the ticket** — a PR nobody can find from the ticket
   may as well not exist. Two things, both required:
   - **Carry the canonical key** (`RND-1280`, with the hyphen) in the branch name,
     every commit subject, and the **PR title**, and put `Fixes RND-1280` in the
     PR body. This is what Jira's dev-tool integration matches on; `rnd1280` does
     NOT match.
   - **Add a remote issue link** per PR, which shows up under the ticket's Links
     regardless of any integration:
     ```bash
     curl -sS -u "$JIRA_EMAIL:$JIRA_API_TOKEN" -X POST \
       -H "Content-Type: application/json" \
       "$JIRA_BASE_URL/rest/api/3/issue/<KEY>/remotelink" \
       -d '{"globalId":"pr-<repo>-<num>","application":{"type":"com.github","name":"GitHub"},
            "relationship":"is implemented by",
            "object":{"url":"<pr-url>","title":"<repo> PR #<num> — <summary>",
                      "icon":{"url16x16":"https://github.githubassets.com/favicon.ico"}}}'
     ```
     `globalId` makes it idempotent — re-running updates the same link instead of
     duplicating it.
   - **Add the PR links to `Dev Notes`** so they're visible in the ticket body,
     not just under Links:
     ```bash
     python3 ~/.agents/skills/solve-bug/scripts/jira-dev-notes-prs.py <KEY> \
       --pr "<repo>#<num>=<pr-url>" [--pr ...] --execute
     ```
     **Never `PUT` that field by hand.** It's a `textarea` custom field, so the
     value is an ADF document (not a string), `editmeta` allows only `set` (no
     append), and it already holds the team's template — Happy Flow Video / Edge
     Cases / Blast Radius / Credentials / Additional Notes. A naive write wipes
     that. The script does read-modify-write, preserves every existing node,
     skips URLs already present, and verifies after writing. Default is dry-run.

   _Done when_ a PR is open per touched repo, each is linked on the ticket, and
   evidence is inline on the ticket.

9. **Pre-merge checklist, then merge your own PRs.** **Per touched repo:**
   - build/tsc green (already from phase 5/7 — re-confirm if anything changed);
   - run the repo's pre-merge test gate;
   - **Security Gate must be green if this is a stop-7 fix.** Before merging a
     money/auth/secrets/migration change, the run file's `securityGate.verdict`
     must be a recorded pass (phase 7.5). No green gate → **do not merge**, hold.
     This is the hard precondition that lets money/auth merge with no human click.
   - **piqk-docs** — update the affected flow/endpoint/audit/runbook pages
     (Confluence is waived — do not touch it or re-flag it).

   **The Bitstamp equalizer step is dropped for this skill** — it sells real crypto
   on a live account, and nothing autonomous moves money. If the fix touches
   trade/pricing/MT/FX code and the float is under the floor, that's **stop
   condition 9**: hold the ticket. Never run it with `--execute`.

   **Merge each of your own PRs** — there is no separate merge worker; the run that
   opened the PR merges it. **Per touched repo, in this order** (the update + CI
   re-run is what makes *your* merge safe against a `main` that moved under you):
   ```bash
   gh pr update-branch <pr> --repo LeveratePiqkProtect/<repo>   # pull latest main into the branch
   gh pr checks <pr> --repo LeveratePiqkProtect/<repo> --watch  # CI on the UPDATED head must pass
   gh pr merge <pr> --repo LeveratePiqkProtect/<repo> --merge --delete-branch
   gh run watch <id> --repo LeveratePiqkProtect/<repo>          # post-merge CI on main
   ```
   - **`update-branch` reports a conflict** → resolve it in your worktree (you hold
     the code and the repro), re-run the touched gates, push, retry. Can't resolve
     cleanly after 3 attempts → **stop condition 8**, hold.
   - **CI red on the updated head** → same: fix on the branch, re-run gates, retry.
   - **post-merge CI on `main` red** → this is the loud one: comment on the ticket,
     transition to **On Hold (473)**, record it in the run file, and stop. A red
     `main` outranks finishing the ticket.
   - **Cross-repo: all or nothing.** If repo A merged and repo B hits a conflict, do
     NOT walk the ticket — leave it *In Progress* until B lands. A half-merged fix
     in QA is worse than a late one.

   **Then, once every repo is merged and `main` CI is green**, do it yourself
   (no worker splits this off any more):
   - **Comment** on the ticket: what merged, the PR links, that `main` CI is green.
   - **Walk the status** `433 → 2 → 4` to *Waiting For Deployment To QA ENV*
     (`Awaiting TL Merge` is only a pass-through — don't leave it resting there),
     logging the 20m worklog before leaving In Progress (convention; no transition
     requires a field). Record every transition in the run file.
   _Done when_ every PR is merged, `main` CI is green, and the ticket is at
   *Waiting For Deployment To QA ENV*. **Never push straight to `main`** — always
   through the PR, so there's a reviewable artifact, CI, and a clean revert.

10. **Housekeeping.** Purge `.playwright-mcp/` (its a11y snapshots write plaintext
    credential-field values to disk — secret leak) and your screenshots; surface
    (never delete) strays you didn't create. **Release your slot** —
    `./piqkenv down --slot <n>` stops its services, drops its cloned database and
    removes its Redis container, freeing it for the next flow. Only ever your own
    slot number, read from your descriptor; never slot 0/1 and never another
    agent's. Your PR merges deleted the branches (`--delete-branch`), so remove
    your worktrees too once their merges have landed. Mark the pin(s) `done`
    (and record any deferral / shortcut / tech-debt as its own pin — that's the
    pin-board's job, not the run report's).

    **Verify the ticket actually shows what you claim**, don't assume phase 8
    landed — on the first real run the inline evidence was silently skipped and
    only the human noticed:
    ```bash
    curl -s -u "$JIRA_EMAIL:$JIRA_API_TOKEN" \
      "$JIRA_BASE_URL/rest/api/3/issue/<KEY>?fields=status,comment" \
      | grep -cE '"type": *"media"|"type": *"codeBlock"'   # must be >= 1
    ```
    (media for a UI proof; a `codeBlock` for a backend red→green transcript.) Zero →
    go back and post the evidence (phase 8). Also confirm the status is the one you
    expect (*Waiting For Deployment To QA ENV* on a clean run).

    **Close the run report.** Fill in anything still missing and set
    `humanShouldCheck` — the one line a human should read even on a clean run
    (e.g. "verify the EN string on the deposit screen in QA"). Then
    `runs.py lint` must come back clean, because a report nobody can trust is
    the only thing standing in for the review you didn't get.
    _Done when_ the slot is released, the run file is complete and lints clean, the
    pin state reflects reality, and every touched repo shows `merged`.

## Finish line

Fix merged to `main` in every touched repo, CI green on `main`, ticket at
**Waiting For Deployment To QA ENV**, evidence and PR links on the ticket, slot
released, and a complete run report on the board. No human was needed — **or** the
ticket is `On Hold` with a comment saying exactly why and what would unblock it,
which is an equally good outcome.
