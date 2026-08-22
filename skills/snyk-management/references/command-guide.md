# Snyk Command Guide

## Contents

- [CLI Discovery And Authentication](#cli-discovery-and-authentication)
- [Local Test Surfaces](#local-test-surfaces)
- [Monitoring, Policy, And SBOM](#monitoring-policy-and-sbom)
- [REST Helper](#rest-helper)
- [Mutation Preview](#mutation-preview)
- [Troubleshooting](#troubleshooting)

## CLI Discovery And Authentication

```powershell
snyk --version
snyk --help
snyk config environment --help
snyk auth --help
snyk test --help
snyk monitor --help
```

For a non-default account region:

```powershell
snyk config environment SNYK-EU-01
snyk auth
```

For non-interactive use, set `SNYK_TOKEN`; do not pass it to `snyk auth <token>` in an agent-visible command.

## Local Test Surfaces

```powershell
snyk test --all-projects --json
snyk test --file=package-lock.json --severity-threshold=high --json
snyk code test --sarif-file-output=snyk-code.sarif
snyk secrets test --json
snyk container test <image>@<digest> --json
snyk iac test . --json
```

Keep the repository's package-manager and build prerequisites intact. Options such as `--all-projects`, `--dev`, `--strict-out-of-sync`, `--platform`, `--target-reference`, `--prune-repeated-subdependencies`, and ecosystem-specific flags materially change results. Match the monitored project before comparing inventories.

## Monitoring, Policy, And SBOM

```powershell
snyk monitor --all-projects --org=<org-id> --target-reference=main
snyk policy
snyk ignore --id=<issue-id> --expiry=2026-09-30 --reason="Reviewed temporary exception"
snyk sbom --format=cyclonedx1.6+json --json-file-output=sbom.json .
snyk container sbom --format=cyclonedx1.6+json --json-file-output=image-sbom.json <image>@<digest>
snyk sbom test sbom.json --json
```

`monitor` uploads a snapshot. `ignore` edits `.snyk`. Review and validate local diffs; never use a permanent ignore without a durable reason. Code Consistent Ignores use `snyk ignore create` with different finding IDs/types and may be Early Access.

## REST Helper

Show safe context and available OpenAPI versions:

```powershell
python "<path-to-skill>/scripts/manage_snyk.py" context --json
python "<path-to-skill>/scripts/manage_snyk.py" versions --json
```

Search a reviewed API date:

```powershell
python "<path-to-skill>/scripts/manage_snyk.py" operations --api-version 2024-10-15 --search projects --json
python "<path-to-skill>/scripts/manage_snyk.py" operations --api-version 2026-03-25 --search issues --method GET --json
```

Use a local OpenAPI document for reproducibility:

```powershell
python "<path-to-skill>/scripts/manage_snyk.py" operations --spec-file snyk-openapi.json --search targets --json
```

Read and paginate:

```powershell
python "<path-to-skill>/scripts/manage_snyk.py" request --operation-id listOrgs --paginate --json
python "<path-to-skill>/scripts/manage_snyk.py" request --operation-id listOrgProjects --path org_id=<uuid> --query limit=100 --paginate --json
python "<path-to-skill>/scripts/manage_snyk.py" request --operation-id listOrgIssues --path org_id=<uuid> --query limit=100 --paginate --json
python "<path-to-skill>/scripts/manage_snyk.py" request --operation-id listOrgAuditLogs --path org_id=<uuid> --paginate --json
```

Raw endpoint escape hatch:

```powershell
python "<path-to-skill>/scripts/manage_snyk.py" request /self --json
python "<path-to-skill>/scripts/manage_snyk.py" request /orgs/<uuid>/projects --query limit=100 --paginate --json
```

The helper adds the selected `version` query, JSON:API headers, and configured token authentication. Absolute URLs must match the selected region and `/rest` base.

## Mutation Preview

Use a body file for JSON:API documents:

```powershell
python "<path-to-skill>/scripts/manage_snyk.py" request --operation-id updateOrgProject --path org_id=<uuid> --path project_id=<uuid> --body-file update.json --json
```

The default output is a redacted preview. Apply only after reviewing IDs, region, version, and body:

```powershell
python "<path-to-skill>/scripts/manage_snyk.py" request --operation-id updateOrgProject --path org_id=<uuid> --path project_id=<uuid> --body-file update.json --send --json
```

For delete operations, explicitly inspect child projects/relationships and audit logs before sending. Re-read afterward.

## Troubleshooting

- `401`: missing/invalid token, wrong `token` versus `bearer` scheme, or wrong account region.
- `403`: plan restriction, missing role/service-account permission, or wrong org/group scope.
- `404`: wrong region/ID, unavailable endpoint at the selected version, or completed API migration.
- `409`/`422`: resource state or JSON:API schema conflict; inspect the error source pointer.
- `429`: API-key rate limit; obey `Retry-After` and reduce concurrency.
- CLI and REST disagree: compare org ID, target reference, project type/origin, scan flags, manifest/lockfile, monitoring timestamp, REST version, and ignore policy.
- Pagination appears incomplete: follow `links.next`; do not invent cursors or assume the first `limit` rows are complete.
