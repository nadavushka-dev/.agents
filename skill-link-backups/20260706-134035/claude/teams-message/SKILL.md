---
name: teams-message
description: Formulate a Microsoft Teams / chat message in Nadav's preferred terse, signal-first style. Use when the user asks to draft, write, or formulate a Teams/Slack/chat message to a colleague or team (e.g. "help me write a teams message to X about Y", "/teams-message <name>"). Optionally takes the recipient name as an argument and opens with "Hi <name>,".
---

# /teams-message — draft a chat message in Nadav's style

Produce a ready-to-send Teams/chat message about the topic at hand (drawn from the current conversation context), formatted to Nadav's house style.

## Input

- `args` (optional): the **recipient's name**. If given, open the message with `Hi <name>,` on its own line, then a blank line. If no name is given, omit the greeting (do not invent one).
- The **subject** is whatever is being discussed in the conversation. Do not re-interview; synthesize from context. If genuinely unclear what the message is about, ask one short question, otherwise proceed.

## Style rules (hard)

- **No em dashes.** Use periods, commas, parentheses, or the word "to".
- **No emojis or icons.**
- **Concise.** Cut filler. Do not narrate what we are working on or the backstory. Lead with the issue or the ask itself.
- **Monotonic, flat tone.** No enthusiasm, no "amazing", no exclamation marks, no softening pleasantries beyond the greeting.
- **Link first.** If a relevant Jira ticket / PR / doc URL exists, put it at (or near) the top on its own line.
- **Grammar can be sacrificed for concision.** Sentence fragments are fine.
- **End with the concrete decision or ask.** Put non-blocking caveats last.

## Output

Print only the message body (ready to copy-paste). After it, in a separate line outside the message, offer to adjust tone/length or tag a person. Do not send anything anywhere — drafting only.

## Shape (reference)

```
<ticket/PR/doc link, if any>

Hi <name>,

<the issue or ask, stated directly in 1-3 short lines or fragments>

<options / decision needed, numbered if more than one>

<non-blocking caveat, if any>
```

Keep it short. When in doubt, cut.
