#!/usr/bin/env bash
# deploy-stg — trigger / check the Piqk on-prem staging deploy (Jenkins `deploy-all`).
# Creds come from ~/.local/secrets.env: JENKINS_USER, JENKINS_API_TOKEN, JENKINS_URL.
#
# Usage:
#   deploy-stg.sh trigger [PIQK_APP_REF=main] [CRM_ADMIN_REF=main] ...   # defaults: all 5 = main
#   deploy-stg.sh status [<build-number>]                                # default: lastBuild
#
# Always targets piqkprotect/deploy-all (never a per-service job) — the standing rule.
set -euo pipefail

SECRETS="${HOME}/.local/secrets.env"
JOB_PATH="job/piqkprotect/job/deploy-all"

[ -f "$SECRETS" ] || { echo "ERROR: $SECRETS not found"; exit 1; }
set -a; . "$SECRETS"; set +a
: "${JENKINS_USER:?JENKINS_USER missing in secrets.env}"
: "${JENKINS_API_TOKEN:?JENKINS_API_TOKEN missing in secrets.env}"
: "${JENKINS_URL:?JENKINS_URL missing in secrets.env}"
AUTH="${JENKINS_USER}:${JENKINS_API_TOKEN}"

api() { curl -fsS --user "$AUTH" "$@"; }

crumb() {
  api "${JENKINS_URL}/crumbIssuer/api/json" \
    | python3 -c "import sys,json;d=json.load(sys.stdin);print(d['crumbRequestField']+':'+d['crumb'])"
}

trigger() {
  # Defaults: every service on main. Any KEY=VALUE arg overrides a single ref.
  declare -A P=( [PIQK_APP_REF]=main [CRM_ADMIN_REF]=main [CRM_SERVICE_REF]=main
                 [CRYPTO_SERVICE_REF]=main [PIQK_SERVER_REF]=main [CONTINUE_ON_ERROR]=true )
  for kv in "$@"; do P[${kv%%=*}]="${kv#*=}"; done
  local data=()
  for k in "${!P[@]}"; do data+=(--data-urlencode "${k}=${P[$k]}"); done

  echo "Triggering deploy-all with:" >&2
  for k in "${!P[@]}"; do printf '  %s=%s\n' "$k" "${P[$k]}" >&2; done

  local loc
  loc=$(curl -fsS -D - -o /dev/null --user "$AUTH" -H "$(crumb)" -X POST \
          "${JENKINS_URL}/${JOB_PATH}/buildWithParameters" "${data[@]}" \
        | awk 'tolower($1)=="location:"{print $2}' | tr -d '\r')
  [ -n "$loc" ] || { echo "ERROR: no queue Location returned"; exit 1; }
  echo "Queued: $loc"
  echo "Resolving build number..."
  # Poll the queue item until the executable (build) is assigned.
  for _ in $(seq 1 30); do
    local ex
    ex=$(api "${loc}api/json" | python3 -c "import sys,json;d=json.load(sys.stdin);e=d.get('executable');print(e['url'] if e else '')" 2>/dev/null || true)
    if [ -n "$ex" ]; then echo "Build: $ex"; echo "Console: ${ex}console"; return 0; fi
    sleep 3
  done
  echo "Still queued (executor busy?). Check: ${JENKINS_URL}/${JOB_PATH}/"
}

status() {
  local n="${1:-lastBuild}"
  api "${JENKINS_URL}/${JOB_PATH}/${n}/api/json" | python3 -c "
import sys,json
d=json.load(sys.stdin)
print('build #',d.get('number'),'->',d.get('url'))
print('building:',d.get('building'),' result:',d.get('result'))
ps=[(p['name'],p.get('value')) for a in d.get('actions',[]) if a.get('parameters') for p in a['parameters']]
if ps: print('params:',ps)
"
}

cmd="${1:-trigger}"; shift || true
case "$cmd" in
  trigger) trigger "$@";;
  status)  status "$@";;
  *) echo "Usage: deploy-stg.sh {trigger [KEY=VAL...] | status [build#]}"; exit 2;;
esac
