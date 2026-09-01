---
name: brief-me
description: Quick context recap for when the user returns to a session after a break. Summarizes the mission, current status, and any pending question or decision in a few lines.
---

The user just came back to this session and needs to re-orient. Produce a short recap with exactly these sections:

**Mission** — What we're working on (one sentence).

**Status** — Where we stand right now: what's done, what's in progress (2-3 bullets max).

**Waiting on you** — If there's an unanswered question or decision the user needs to make, state it clearly. If nothing is blocking, omit this section entirely.

Rules:
- Keep the entire output under 10 lines.
- No preamble, no "welcome back", no fluff.
- If the conversation just started and there's no context yet, say: "Fresh session — no prior context. What are we working on?"
