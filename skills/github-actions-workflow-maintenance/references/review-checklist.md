# GitHub Actions Review Checklist

Load this checklist for detailed reviews of `.github/workflows/*.yml` or `.yaml`, reusable workflow migrations, release workflows, or broad workflow audits.

## Trigger And Scope

- Does each workflow have a narrow, named responsibility?
- Do `push`, `pull_request`, `schedule`, `workflow_dispatch`, `workflow_call`, and `workflow_run` triggers match the intended trust boundary?
- Are branch, tag, and path filters precise enough without hiding required CI from protected branches?
- Are manual inputs typed, bounded, and safe to use in later shell commands?
- Are scheduled workflows useful when no repository files changed?
- Does the workflow avoid duplicate runs for the same PR or branch unless duplication is intentional?

## Permissions And Secrets

- Is top-level `permissions` present and read-only by default?
- Are write permissions granted at job level only where needed?
- Are `contents: write`, `pull-requests: write`, `issues: write`, `packages: write`, `actions: write`, and `id-token: write` justified by the job?
- Are secrets scoped to the job or environment that needs them?
- Are environment secrets protected by reviewers or branch rules when used for production or publishing?
- Is OIDC or trusted publishing available instead of long-lived credentials?
- Are entire contexts, tokens, secrets, webhook payloads, or env dumps kept out of logs?

## Action Supply Chain

- Are third-party actions pinned according to repo policy?
- If using full commit SHAs, does each SHA belong to the upstream action repository?
- If using tags, is the action trusted and allowed by local policy?
- Are action inputs checked against current action metadata, especially for renamed inputs?
- Are Docker actions, composite actions, and local actions reviewed as code with the same permissions as the job?
- Are Dependabot, Renovate, or another update path configured for action updates when appropriate?

## Jobs And Dependencies

- Do job names map to real phases such as lint, typecheck, test, build, package, scan, publish, or deploy?
- Does `needs` encode the required ordering without unnecessary serialization?
- Are matrix jobs bounded and meaningful?
- Is `fail-fast` chosen intentionally for compatibility matrices?
- Are job outputs mapped from step outputs and consumed by downstream jobs correctly?
- Are services configured with health checks or waits instead of fixed sleeps?
- Are `timeout-minutes` set for jobs likely to hang?

## Shell And Expressions

- Are shell scripts small enough to review?
- Are GitHub expressions kept out of shell command positions when they can contain untrusted text?
- Are untrusted values passed through `env` and quoted as shell variables?
- Are bash scripts using `set -euo pipefail` where appropriate?
- Are PowerShell steps using strict error behavior and proper quoting?
- Are `$GITHUB_OUTPUT`, `$GITHUB_ENV`, and `$GITHUB_PATH` writes quoted and newline-safe?
- Are OS-specific commands guarded by runner OS or split into OS-specific jobs?

## Caching And Artifacts

- Is cache use tied to lockfiles or stable dependency metadata?
- Does the workflow avoid caching `node_modules` unless repo policy says otherwise?
- Are release or publish jobs avoiding stale build caches when reproducibility matters?
- Are artifacts named, scoped, and retained for the minimum useful time?
- Are publish/deploy jobs consuming the exact artifact produced by verified build jobs?
- Are test reports, coverage, screenshots, logs, or package tarballs uploaded when needed for debugging or downstream jobs?

## Reusable Workflows

- Does each reusable workflow live under `.github/workflows/` and define `on.workflow_call`?
- Are inputs typed as `string`, `boolean`, or `number`?
- Are required secrets declared rather than inherited by accident?
- Are outputs declared at workflow level and mapped from job outputs?
- Do caller jobs use `jobs.<job_id>.uses` with only allowed caller keys?
- Are reusable workflow permissions documented and minimized?
- Are shared workflow refs following the owner's update policy?

## Node And npm Package Workflows

- Does Node version come from `.node-version`, `.nvmrc`, `package.json#engines`, or another repo source of truth?
- Are lockfiles present and used by `npm ci`, `pnpm install --frozen-lockfile`, or the repo's package-manager equivalent?
- Are release checks using the repo's aggregate gate before publish?
- Does `npm publish` use trusted publishing or provenance when available and configured?
- Are `id-token: write`, `contents: read`, registry setup, package access, and environment restrictions correct for publish jobs?
- Is the package tarball built once, uploaded, then published from that verified artifact when the repo requires reproducible release handoff?

## Deployment Workflows

- Are deploys gated by branch, tag, environment, or release event as intended?
- Are production jobs protected by GitHub environments when human approval is required?
- Is deployment concurrency keyed by environment or target?
- Are rollback steps documented or automated for the platform?
- Are smoke tests or health checks run after deployment?
- Are cloud credentials short-lived through OIDC where supported?

## Validation Commands

Prefer repo-local commands, then fall back to direct tools:

```powershell
npm run lint:actions
actionlint
npm run validate
npm run release:verify
```

When direct action metadata, workflow syntax, or publish authentication behavior is uncertain, verify against current official docs or the action repository before editing.
