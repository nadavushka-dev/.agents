---
name: piqk-ui-task
description: Execute a UI change task on piqk-app (or crm-admin-next) driven by a Figma frame and/or PRD section from the product team. Use whenever the user asks to implement, change, restyle, or align a screen/component/flow in the Piqk client UI — e.g. "implement the new dashboard design", "make the deposit screen match Figma", "product wants X changed on the trade page", "/piqk-ui-task <screen>". Enforces the demand-driven UI workflow (worktree → spec slice → GK orient → implement intent → PRD-derived tests → deviations log).
---

# Piqk UI Task

Standing workflow for UI changes on the vibe-coded piqk-app now that product produces Figma + PRDs. Canonical plan (read if context is needed): `/Users/nadav.barmatz/work/piqk/PLANS/features/2026-06-02-ui-task-workflow.md`.

**Posture:** Figma/PRD = product intent. Implement faithfully; flag ambiguity, never decide silently. Demand-driven — touch only what the task names.

## Steps

1. **Scope the task.** Identify: target screen(s)/route(s), the Figma frame, the PRD section. If any of the three is missing, ask the user for it before coding. Multi-repo? Same `<env-name>` everywhere.

2. **Worktree.** Per the CLAUDE.md HARD RULE: `git worktree add .worktrees/<env> -b feature/<env> origin/main` in every touched repo. Never work in the main checkout.

3. **Pull the spec slice.** Use the helper (REST API — NOT the MCP; the MCP seat is capped at 6 calls/month, REST follows file permissions with no quota):
   ```
   ~/.claude/skills/piqk-ui-task/figma-frame.sh <node-id>   # → PNG + node JSON in ./.figma-frames/
   ```
   The node-id comes from the Figma URL (`?node-id=1879-5958`). If the user gives a whole *page* (type CANVAS) instead of a frame, list its children first and ask which state/frame is meant — don't guess. Read the PNG as an image and the JSON for exact text/colors/spacing. Add `.figma-frames/` to the repo's `.gitignore` (rendered assets, not source). Read only the relevant PRD section. Do NOT expand scope to neighboring screens.
   - Default fileKey is the WallaCrypto file (`p2YZG89M0CAmUwbmua7gUT`); pass a different one as arg 2 if product points elsewhere.
   - Designs are **mobile, 375×812** (iPhone viewport) and Hebrew RTL — verify the implemented screen's responsive target matches before assuming a desktop layout.

4. **Orient with GK (GitNexus).**
   - Route → files: `piqk-docs/docs/architecture/software/piqk-app.md`
   - `mcp__gitnexus__query` / `context` (load via ToolSearch) for the screen's component/API structure
   - `mcp__gitnexus__impact` BEFORE modifying any shared component — report blast radius to the user if non-trivial

5. **Classify the change — one PR per kind, never mixed:**
   - **Restyle** (zero logic change) | **Bugfix** (no visual change) | **PRD-alignment** (behavior + visuals, cites the PRD section)

6. **Implement the intent — delegate to `figma-implement-design`.** Use that skill's translate → 1:1-parity → validate methodology (its Steps 5–7): map Figma tokens onto the Tailwind 4 / Shadcn theme, reuse existing components over recreation, and run its validation checklist (layout, typography, colors, states, RTL) before marking done. **But do NOT call the Figma MCP** (`get_design_context` / `get_screenshot` / `get_metadata`) — its seat is capped at 6 calls/month, and Step 3 already pulled the slice via REST. Feed the skill the `.figma-frames/` PNG + node JSON as the design source instead. While working, collect ambiguities — states Figma doesn't cover, code behavior the PRD never mentions, RTL questions (designs are often drawn LTR; app is Hebrew RTL). Batch into 2–3 questions for product; ship what's clear, don't block.

7. **Token check.** Touching the same hardcoded color/spacing/radius in ~5 places? Stop — propose extracting design tokens into the Tailwind 4 theme / Shadcn config as a separate zero-visual-change PR first.

8. **Test from the PRD.** Extend the Playwright spec (`piqk-app/e2e`) for the touched screen from the PRD's *described* behavior, not from current code behavior. Run it.

9. **Log deviations.** Append to `/Users/nadav.barmatz/work/piqk/docs/ui-deviations.md` (create on first use): `| <date> | <screen/route> | <Figma frame> | code did A, design says B | <product's answer or OPEN> |`. Include the frame ↔ route pairing.

10. **Merge gate.** The standard CLAUDE.md pre-merge checklist applies unchanged (build, piqkenv confirm, equalizer, suites, Confluence, piqk-docs). Remind the user to re-index GK after merge.

## Anti-goals

No app-wide audits, no conformance matrices, no restyling screens the task didn't name, no "improving" adjacent code (Karpathy rules apply).
