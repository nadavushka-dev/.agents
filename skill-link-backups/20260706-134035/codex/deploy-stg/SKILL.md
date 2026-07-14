---
name: deploy-stg
description: Deploy Piqk to on-prem staging via the Jenkins `deploy-all` pipeline. Use when the user asks to deploy to stg / staging, ship a merged change to staging, or run a Piqk deploy — e.g. "deploy it to stg", "push this to staging", "/deploy-stg". Always triggers piqkprotect/deploy-all (never a per-service job); defaults all 5 services to `main`.
---

# deploy-stg

Trigger the Piqk **on-prem** staging deploy. The pipeline is Jenkins + PM2 on the
`piqkprotect` box (repo: `~/work/piqk/piqk-onprem-deploy`), NOT the GKE/ArgoCD path in
`piqk-docs`. Staging serves at `piqk-stg.piqk.com` / `crm-stg.piqk.com`.

## Hard rule

**Always use the `piqkprotect/deploy-all` umbrella job — never a per-service job.**
`deploy-all` fans out to all 5 `deploy-<svc>` jobs, one ref per service. This is Nadav's
standing instruction.

## Prerequisites

- Whatever you're deploying must already be merged to the target branch (default `main`)
  of its service repo. `deploy-all` deploys refs, not your working tree.
- Jenkins auth lives in `~/.local/secrets.env` (`JENKINS_USER`, `JENKINS_API_TOKEN`,
  `JENKINS_URL`). The helper sources these — never paste credential values into commands,
  this file, or chat.

## Usage

The helper script does the crumb + `buildWithParameters` dance and resolves the build number.

```bash
# Deploy everything at main (the common case):
~/.claude/skills/deploy-stg/deploy-stg.sh trigger

# Override a single service's ref (others stay on main):
~/.claude/skills/deploy-stg/deploy-stg.sh trigger PIQK_APP_REF=feature/foo

# Check status (defaults to the last build):
~/.claude/skills/deploy-stg/deploy-stg.sh status
~/.claude/skills/deploy-stg/deploy-stg.sh status 4
```

Valid trigger keys: `PIQK_APP_REF`, `CRM_ADMIN_REF`, `CRM_SERVICE_REF`,
`CRYPTO_SERVICE_REF`, `PIQK_SERVER_REF` (branch/tag each), `CONTINUE_ON_ERROR` (default `true`).

## Steps to follow

1. **Confirm what's being deployed.** If the user merged a change, the ref is `main`. If they
   name a branch/tag for a specific service, pass it as the matching `*_REF` and leave the rest
   on `main`. When unsure which services changed, deploy all at `main` — `deploy-all` redeploys
   the unchanged ones harmlessly.
2. **Trigger:** run `deploy-stg.sh trigger [overrides...]`. It prints the queued item, then the
   resolved build URL + console URL.
3. **Monitor** (offer this; it runs 5 builds sequentially on a RAM-tight box, ~15–30 min). Poll
   `deploy-stg.sh status <build#>` until `result` is non-null. For long waits, schedule a check
   rather than blocking. `result: SUCCESS` = clean; `UNSTABLE` = at least one service failed
   (`CONTINUE_ON_ERROR=true` lets the rest proceed) — read the build console for which.
4. **Report** the per-service outcome and the staging URLs. Each child job healthchecks and
   auto-reverts its own symlink on failure, so a red service is already rolled back to its prior
   release.

## Notes

- A successful trigger returns HTTP 201 with a `queue/item/<n>` Location; the build number is
  assigned a few seconds later once the single executor frees up.
- `deploy-all` is a scripted pipeline whose parameters live on the job (Active Choices), so it
  must be triggered with `buildWithParameters` + a CSRF crumb — the helper handles both.
- Rollback / per-service detail: see `~/work/piqk/piqk-docs/docs/runbooks/deploy.md` and the
  `deploy.sh` / `healthcheck.sh` in `piqk-onprem-deploy`.
