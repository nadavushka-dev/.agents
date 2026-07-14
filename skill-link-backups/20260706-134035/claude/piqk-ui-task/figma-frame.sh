#!/usr/bin/env bash
# figma-frame.sh — pull a single Figma frame's PNG + node JSON via the REST API.
# Uses FIGMA_TOKEN from ~/.local/secrets.env (NOT the MCP — REST follows file
# permissions and has no per-seat quota).
#
# Usage:
#   figma-frame.sh <node-id> [fileKey] [outdir]
#
#   node-id   e.g. 1876-1538 or 1876:1538 (either separator works)
#   fileKey   defaults to the WallaCrypto design file
#   outdir    defaults to ./.figma-frames (gitignore it if inside a repo)
#
# Output: <outdir>/<node>.png  +  <outdir>/<node>.json
set -euo pipefail

NODE_RAW="${1:?usage: figma-frame.sh <node-id> [fileKey] [outdir]}"
FILE_KEY="${2:-p2YZG89M0CAmUwbmua7gUT}"          # WallaCrypto - Idan/Sapir
OUTDIR="${3:-./.figma-frames}"
SCALE="${FIGMA_SCALE:-2}"                          # 2x for crisp inspection

# token
SECRETS="${PIQK_SECRETS_ENV:-$HOME/.local/secrets.env}"
[ -f "$SECRETS" ] || { echo "no secrets file at $SECRETS" >&2; exit 1; }
set -a; # shellcheck disable=SC1090
source "$SECRETS"; set +a
[ -n "${FIGMA_TOKEN:-}" ] || { echo "FIGMA_TOKEN not set in $SECRETS" >&2; exit 1; }

NODE_COLON="${NODE_RAW//-/:}"                      # API node ids use ':'
NODE_SAFE="${NODE_RAW//:/-}"                       # filenames use '-'
mkdir -p "$OUTDIR"
H=(-H "X-Figma-Token: $FIGMA_TOKEN")

# 1. node JSON (structure, text, colors, sizes)
curl -fsS "${H[@]}" \
  "https://api.figma.com/v1/files/$FILE_KEY/nodes?ids=$NODE_COLON" \
  -o "$OUTDIR/$NODE_SAFE.json"

# 2. rendered PNG (follow the short-lived render URL)
IMG_URL=$(curl -fsS "${H[@]}" \
  "https://api.figma.com/v1/images/$FILE_KEY?ids=$NODE_COLON&format=png&scale=$SCALE" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print((list(d.get('images',{}).values()) or [''])[0] or '')")
[ -n "$IMG_URL" ] || { echo "no render URL for $NODE_COLON (check node id / access)" >&2; exit 1; }
curl -fsS "$IMG_URL" -o "$OUTDIR/$NODE_SAFE.png"

echo "$OUTDIR/$NODE_SAFE.png"
echo "$OUTDIR/$NODE_SAFE.json"
