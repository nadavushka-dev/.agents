---
name: session-retro
description: Run a retrospective on the CURRENT Claude Code session — score how well it went and extract Good / Bad / Drop / Change / Evolve, plus a real (counted, not guessed) skill-usage table. Use when the user says "/session-retro", "session retro", "retro this session", "how did this session go", "retrospective", or wants a post-mortem of the work just done. Persists each retro to a log so recurring pain points and automation candidates surface across sessions.
---

# Session Retro

A retrospective whose subject is **this session** — how well it went and what to
change. Output is terse, evidence-backed, and scored. Every number comes from the
transcript (via the helper script); every qualitative point cites the moment it
happened. No self-congratulation, no fluff.

## 1. Pull the facts (always first)

```bash
python3 ~/.claude/skills/session-retro/scripts/retro-stats.py
```

This reads the current session's transcript (`$CLAUDE_CODE_SESSION_ID`) and emits
the factual backbone: metrics strip, **real skill-usage counts**, top tools,
human-interruption moments (with the correction that followed each), files
touched, token spend. Treat these counts as authoritative — do not re-estimate
them. If the script errors (no transcript), fall back to the live conversation
and say the counts are approximate.

## 2. Read prior retros (for the Evolve gate)

```bash
cat ~/.claude/session-retro/retros.jsonl 2>/dev/null | tail -20
```

The point of the log: tell a **one-off from a recurring pattern**. An annoyance
that shows up in three retros is an automation candidate; the same thing once is
not. If a past `change`/`evolve` item recurred this session, escalate it (say
"raised in N prior retros").

## 3. Score the session (rubric)

Start at **100%**, deduct with judgment, floor at 0, cite each deduction:

| Signal | Deduction |
|---|---|
| Human had to course-correct / interrupt (real redirection) | −8 each (cap −40) |
| Rework — redid or reverted work already "done" | −10 each |
| Gate failure that needed fixing (tests, lint, CI, review, type errors) | −6 each |
| Hallucination / false claim the human caught | −10 each |
| Token waste — thrash, long unproductive loops, re-reading | −5 to −15 (judgment) |

Not every interruption is a correction — a scope-add or new instruction isn't a
deduction. Show the arithmetic in one line. Bands: **≥90** excellent · **75–89**
good · **60–74** mixed · **<60** rough.

If a skill or a `/loop` ran, assess it explicitly: did it deliver, or thrash?
Use its share of tool calls / interruptions as evidence.

## 4. Write the report

Exactly these sections, each **tight** — bullets, not paragraphs. Omit a section
only if genuinely empty (say "— none").

```
## Retro — <score>% (<band>)  · <one-line verdict>

<metrics strip from the script: prompts · turns · interruptions · tools · skills · files · tokens>

## Good
- <what worked, with evidence>. If a skill/loop ran, how well it went.
## Bad
- <what went wrong: corrections, wrong results, hallucinations — cite the moment>
## Drop
- STOP doing <specific thing>: <what it cost>. → drop it next time.
## Change
- KEEP doing <thing> but <how to do it better>: <expected gain>.
## Evolve
- <automation worth building — ONLY if the pattern recurs; cite frequency/count>

## Skill usage
<the counted table from the script>
```

Rules:
- **Good** is not a participation trophy — anchor it to the score and to real
  outcomes. If little went well, say so.
- **Bad** is observation — just name what went wrong. No fix required here.
- **Drop** is a *directive to stop*, not an observation. Each bullet names a
  concrete thing to **abandon** next time — a tool, a skill step, a loop, a
  habit, a whole approach — and the cost it removes. Imperative voice ("stop
  grepping the broad JQL", "drop the retry loop — it never converged"). If a
  step *in a skill we ran* is dead weight, say to drop it, by name. Nothing to
  cut → "— nothing to drop."
- **Drop vs Change**: Drop = remove it entirely. Change = keep it, do it better.
  Each bullet belongs to exactly one. If you'd still do the thing, it's Change.
- **Evolve** gate: propose an automation only for something done *often enough to
  be worth automating* — cite the count or "seen in N retros". Skip speculative
  "would be cool" ideas. Prefer a skill/hook/loop that removes a repeated manual step.
- Cite evidence inline (an interruption snippet, a tool count, a file). No vibes.

## 5. Persist the retro

Append one JSON line so patterns accumulate (create the dir on first run):

```bash
mkdir -p ~/.claude/session-retro
python3 - <<'PY'
import json, os
rec = {
  "session": os.environ.get("CLAUDE_CODE_SESSION_ID",""),
  "score": 0,                      # <-- fill from step 3
  "verdict": "",                   # one line
  "bad": [], "change": [], "evolve": [],   # short tags, lowercase, for recurrence grep
}
with open(os.path.expanduser("~/.claude/session-retro/retros.jsonl"), "a") as f:
    f.write(json.dumps(rec) + "\n")
PY
```

Fill the record from your report before running it. Keep tags short and
consistent (e.g. `"jql-scope-correction"`, `"token-thrash-loop"`) so the same
issue matches across sessions — that consistency is what makes step 2 work.

## Guardrails

- Subject is **this session only**. Don't groom the backlog or review code here.
- Counts come from the script, never from memory. Judgment comes from the convo.
- Concise over complete. If a section is thin, one honest bullet beats five padded ones.
- The score must be defensible from the cited deductions — no gut-feel numbers.
