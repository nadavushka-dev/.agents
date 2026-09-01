#!/usr/bin/env python3
"""session-retro: deterministic metrics for the CURRENT session's transcript.

Emits a markdown block that is the FACTUAL backbone of the retro. Every count in
the report (skill usage, tool calls, human interruptions, files touched, token
spend) comes from here so the model never guesses a number. The qualitative
judgment (Good/Bad/Drop/Change/Evolve) is the model's job, done from the live
conversation, citing these facts.

Transcript resolution:
    session id = argv[1] or $CLAUDE_CODE_SESSION_ID
    file       = first match of ~/.claude/projects/*/<id>.jsonl

Stdlib only. Prints markdown to stdout; prints a one-line error to stderr and
exits non-zero if the transcript can't be found.
"""
import os, sys, glob, json, collections

# Tools that mutate files — used to compute "files touched".
WRITE_TOOLS = {"Edit", "Write", "NotebookEdit", "MultiEdit"}
# Sub-agent spawn tools (harness-dependent naming).
AGENT_TOOLS = {"Agent", "Task"}
INTERRUPT_MARK = "Request interrupted by user"


def find_transcript(sid):
    hits = glob.glob(os.path.expanduser(f"~/.claude/projects/*/{sid}.jsonl"))
    return hits[0] if hits else None


def text_of(content):
    """Flatten a message.content (str | list of blocks) to plain text."""
    if isinstance(content, str):
        return content
    out = []
    for b in content or []:
        if isinstance(b, dict) and b.get("type") == "text":
            out.append(b.get("text", ""))
    return "\n".join(out)


def main():
    sid = (sys.argv[1] if len(sys.argv) > 1 else "") or os.environ.get("CLAUDE_CODE_SESSION_ID", "")
    if not sid:
        sys.exit("no session id (pass one or set CLAUDE_CODE_SESSION_ID)")
    path = find_transcript(sid)
    if not path:
        sys.exit(f"transcript not found for session {sid}")

    tools = collections.Counter()
    skills = collections.Counter()
    agents = 0
    files = set()
    out_tokens = 0
    peak_ctx = 0              # high-water mark of a single request's input context
    assistant_msgs = 0
    user_prompts = 0          # real human turns (not tool-result carriers / meta)
    interrupts = []           # (correction_snippet,) captured after each interrupt marker
    pending_interrupt = False
    first_prompt = None

    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            o = json.loads(line)
        except json.JSONDecodeError:
            continue
        typ = o.get("type")
        msg = o.get("message", {}) if isinstance(o.get("message"), dict) else {}
        content = msg.get("content")

        if typ == "assistant":
            assistant_msgs += 1
            u = msg.get("usage") or {}
            out_tokens += u.get("output_tokens", 0) or 0
            ctx = (u.get("input_tokens", 0) or 0) + (u.get("cache_read_input_tokens", 0) or 0)
            peak_ctx = max(peak_ctx, ctx)
            for b in content or []:
                if not (isinstance(b, dict) and b.get("type") == "tool_use"):
                    continue
                name = b.get("name", "?")
                tools[name] += 1
                inp = b.get("input", {}) if isinstance(b.get("input"), dict) else {}
                if name == "Skill":
                    skills[inp.get("skill") or inp.get("command") or "?"] += 1
                elif name in AGENT_TOOLS:
                    agents += 1
                elif name in WRITE_TOOLS:
                    fp = inp.get("file_path") or inp.get("notebook_path")
                    if fp:
                        files.add(fp)

        elif typ == "user":
            txt = text_of(content)
            is_tool_result = isinstance(content, list) and any(
                isinstance(b, dict) and b.get("type") == "tool_result" for b in content
            )
            if INTERRUPT_MARK in txt:
                pending_interrupt = True
                continue
            # Slash-command turns are commands, not prose — skip without clearing a
            # pending interrupt, so the real correction prompt that follows is captured.
            if "<command-name>" in txt or "<local-command-stdout>" in txt:
                continue
            # A genuine human prompt: has text, isn't a pure tool-result carrier, not meta.
            if txt.strip() and not is_tool_result and not o.get("isMeta"):
                user_prompts += 1
                if first_prompt is None:
                    first_prompt = txt.strip()
                if pending_interrupt:
                    interrupts.append(txt.strip().replace("\n", " ")[:160])
                    pending_interrupt = False

    # interrupts with no following prompt still count
    interrupt_count = len(interrupts) + (1 if pending_interrupt else 0)

    # ---- render ----
    p = print
    p(f"<!-- session {sid} | {os.path.basename(path)} -->")
    p("### Session metrics (factual)\n")
    p(f"- **Human prompts:** {user_prompts}")
    p(f"- **Assistant turns:** {assistant_msgs}")
    p(f"- **Human interruptions/corrections:** {interrupt_count}")
    p(f"- **Tool calls:** {sum(tools.values())}  |  **Skill calls:** {sum(skills.values())}  |  **Sub-agents:** {agents}")
    p(f"- **Files touched:** {len(files)}")
    p(f"- **Output tokens:** ~{out_tokens:,}  |  **Peak context:** ~{peak_ctx:,}")

    p("\n### Skill usage (real, counted)\n")
    if skills:
        p("| Skill | Calls |")
        p("|---|---|")
        for name, n in skills.most_common():
            p(f"| {name} | {n} |")
    else:
        p("_No skills invoked this session._")

    p("\n### Top tools\n")
    if tools:
        p("| Tool | Calls |")
        p("|---|---|")
        for name, n in tools.most_common(10):
            p(f"| {name} | {n} |")
    else:
        p("_No tool calls._")

    if interrupts:
        p("\n### Interruption moments (correction after each)\n")
        for i, snip in enumerate(interrupts, 1):
            p(f"{i}. {snip}")

    if files:
        p("\n<details><summary>Files touched</summary>\n")
        for f in sorted(files):
            p(f"- {f}")
        p("</details>")


if __name__ == "__main__":
    main()
