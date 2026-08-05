#!/usr/bin/env bash
# swarm-handoff RESUME — recreate a herdr workspace and resume every worker agent
# by session id from a manifest.json written at pause time.
#
# Usage:
#   swarm-relaunch.sh --list             # list every parked swarm in the registry
#   swarm-relaunch.sh <swarm-name>       # resume that swarm by name
#   swarm-relaunch.sh <path/manifest.json>  # resume an explicit manifest
#   swarm-relaunch.sh                    # resume the only parked swarm, else list + ask
# Registry = $SWARM_HANDOFF_ROOT, else the nearest .swarm-handoff/ walking up from $PWD.
#
# Reads project_root / workspace_label / transcript_slug / sessions[] from the
# manifest (see the swarm-handoff SKILL.md for the schema). For each session it
# validates the transcript exists, then resumes claude (`--resume <id>`) / codex
# (`resume <id>`); if the transcript is gone it launches the agent FRESH so the
# orchestrator can re-fire its brief. Never touches git/worktrees — those are
# already durable. Never merges. Idempotent-friendly: safe to re-run (makes a
# fresh workspace each time).
set -euo pipefail

command -v herdr >/dev/null || { echo "herdr not on PATH (are you inside herdr?)" >&2; exit 1; }

find_registry() {  # $SWARM_HANDOFF_ROOT, else nearest .swarm-handoff walking up from PWD
  if [ -n "${SWARM_HANDOFF_ROOT:-}" ] && [ -d "$SWARM_HANDOFF_ROOT" ]; then echo "$SWARM_HANDOFF_ROOT"; return 0; fi
  local d="$PWD"
  while [ "$d" != "/" ]; do
    [ -d "$d/.swarm-handoff" ] && { echo "$d/.swarm-handoff"; return 0; }
    d=$(dirname "$d")
  done
  return 1
}

list_swarms() {  # <registry-dir> -> table of parked swarms
  python3 - "$1" <<'PY'
import json, os, sys, glob
reg = sys.argv[1]
rows = []
for mp in sorted(glob.glob(os.path.join(reg, "*", "manifest.json"))):
    try: m = json.load(open(mp))
    except Exception: continue
    rows.append((m.get("swarm", "?"), m.get("captured_at", "?"),
                 str(len(m.get("sessions", []))), (m.get("held_reason", "") or "")[:44]))
if not rows:
    print(f"(no parked swarms in {reg})"); sys.exit(0)
w = max(len(r[0]) for r in rows + [("SWARM", )])
print(f"{'SWARM'.ljust(w)}  CAPTURED               SESS  HELD REASON")
for s, c, n, h in rows:
    print(f"{s.ljust(w)}  {c:<21}  {n:>4}  {h}")
PY
}

ARG="${1:-}"
if [ "$ARG" = "--list" ] || [ "$ARG" = "-l" ]; then
  REG=$(find_registry) || { echo "no .swarm-handoff registry found from $PWD" >&2; exit 1; }
  list_swarms "$REG"; exit 0
fi

if [ -n "$ARG" ] && [ -f "$ARG" ]; then
  MANIFEST="$ARG"                                   # explicit manifest path
elif [ -n "$ARG" ] && [ "${ARG%.json}" != "$ARG" ]; then
  echo "manifest not found: $ARG" >&2; exit 1        # looked like a path but missing
else
  REG=$(find_registry) || { echo "no .swarm-handoff registry found; pass a manifest path" >&2; exit 2; }
  if [ -n "$ARG" ]; then                             # resume by name
    MANIFEST="$REG/$ARG/manifest.json"
    [ -f "$MANIFEST" ] || { echo "no parked swarm named '$ARG' in $REG:" >&2; list_swarms "$REG" >&2; exit 1; }
  else                                               # bare: one -> go, many -> ask
    FIRST=$(ls -1 "$REG"/*/manifest.json 2>/dev/null | head -1)
    CNT=$(ls -1 "$REG"/*/manifest.json 2>/dev/null | wc -l | tr -d ' ')
    [ -n "$FIRST" ] || { echo "no parked swarms in $REG" >&2; exit 1; }
    if [ "$CNT" = "1" ]; then MANIFEST="$FIRST"; echo "resuming the only parked swarm:";
    else echo "multiple parked swarms — re-run with a name (swarm-relaunch.sh <name>):" >&2; list_swarms "$REG" >&2; exit 2; fi
  fi
fi
[ -f "$MANIFEST" ] || { echo "manifest not found: $MANIFEST" >&2; exit 1; }

ROOT=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['project_root'])" "$MANIFEST")
WSLABEL=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['workspace_label'])" "$MANIFEST")
[ -d "$ROOT" ] || { echo "project_root does not exist: $ROOT" >&2; exit 1; }

# Preflight + per-session resume mode. Emits TSV: label \t agent \t sid \t mode \t brief
ROWS=$(python3 - "$MANIFEST" <<'PY'
import json, os, sys
m = json.load(open(sys.argv[1]))
slug = m.get("transcript_slug", "")
home = os.path.expanduser("~")
warn = []
for s in m.get("sessions", []):
    label = s.get("label", "?"); agent = s.get("agent", ""); sid = s.get("session_id") or ""
    mode = "resume"
    if not sid or agent not in ("claude", "codex"):
        mode = "fresh"
    elif agent == "claude":
        # claude transcripts are discoverable on disk; codex resolves its own store by id
        p = os.path.join(home, ".claude", "projects", slug, sid + ".jsonl")
        if not os.path.exists(p):
            mode = "fresh"; warn.append(f"{label}: claude transcript missing ({sid}) -> FRESH")
    print("\t".join([label, agent, sid, mode, s.get("brief", "")]))
for w in warn:
    print("WARN\t" + w, file=sys.stderr)
PY
)
# surface preflight warnings (stderr of the heredoc)
[ -n "${ROWS}" ] || { echo "no sessions in manifest" >&2; exit 1; }

resume_cmd() { # agent sid mode -> launch string
  local agent=$1 sid=$2 mode=$3
  if [ "$mode" = "resume" ] && [ -n "$sid" ]; then
    case "$agent" in
      claude) echo "claude --dangerously-skip-permissions --resume $sid" ;;
      codex)  echo "codex --dangerously-bypass-approvals-and-sandbox resume $sid" ;;
    esac
  else
    case "$agent" in
      claude) echo "claude --dangerously-skip-permissions" ;;
      codex)  echo "codex --dangerously-bypass-approvals-and-sandbox" ;;
      *)      echo "" ;;
    esac
  fi
}

echo "Creating workspace '$WSLABEL' (cwd $ROOT) ..."
WS=$(herdr workspace create --label "$WSLABEL" --cwd "$ROOT" --no-focus \
     | python3 -c "import sys,json;r=json.load(sys.stdin).get('result',{});print(r.get('workspace_id') or r.get('workspace',{}).get('workspace_id') or '')")
[ -n "$WS" ] || { echo "failed to create workspace" >&2; exit 1; }
echo "workspace = $WS"

FRESH_NOTES=""
while IFS=$'\t' read -r label agent sid mode brief; do
  [ -z "$label" ] && continue
  pane=$(herdr tab create --workspace "$WS" --label "$label" --cwd "$ROOT" --no-focus \
         | python3 -c "import sys,json;print(json.load(sys.stdin)['result']['root_pane']['pane_id'])")
  cmd=$(resume_cmd "$agent" "$sid" "$mode")
  if [ -z "$cmd" ]; then echo "  $label: unknown agent '$agent' — left as a shell ($pane)"; continue; fi
  echo "  $label ($agent, $mode) -> $pane"
  herdr pane run "$pane" "$cmd" >/dev/null 2>&1
  if [ "$mode" = "fresh" ] && [ -n "$brief" ]; then
    FRESH_NOTES+=$'\n'"    - $label launched FRESH (no transcript) — re-fire its brief: $brief"
  fi
done <<< "$ROWS"

echo
echo "Relaunched '$WSLABEL' ($WS)."
[ -n "$FRESH_NOTES" ] && echo "Fresh (context lost, re-brief needed):$FRESH_NOTES"
echo "Next: in the orchestrator tab say — 'resume orchestration: read the SUPERVISOR-HANDOFF + tracker pin for $WSLABEL'."
echo "If a codex tab drops to a shell instead of resuming, run manually: codex resume <SESSION_ID>"
