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

The helper adds the selected `version` query, JSON:API headers, and configured token authentication. `--base-url` accepts only `https://api.snyk.io/rest`, `https://api.us.snyk.io/rest`, `https://api.eu.snyk.io/rest`, or `https://api.au.snyk.io/rest`. Absolute request and OpenAPI URLs must match that selected official region and remain under `/rest`. Before token lookup or attachment, repeated path decoding rejects literal, encoded, or double-encoded traversal, slash/backslash, query/fragment delimiters, controls, malformed `%2`/`%GG`, and dangerous residual escapes. Properly encoded spaces, plus signs, equals signs, non-ASCII text, and nonstructural literal percent signs in parameters remain allowed.

Helper resource and control limits are explicit:

| Control                               | Contract     |
| ------------------------------------- | ------------ |
| Local OpenAPI document                | 16 MiB       |
| Remote OpenAPI document               | 16 MiB       |
| OpenAPI version catalog               | 1 MiB        |
| One successful REST response          | 8 MiB        |
| One HTTP error response               | 16 KiB       |
| Cumulative paginated response bytes   | 32 MiB       |
| Displayed untrusted transport reason  | 1000 chars   |
| `--timeout`                           | finite, `>0` |
| `--retries`                           | `0..10`      |
| `--max-pages`                         | `1..1000`    |
| `Retry-After` or fallback retry delay | at most 60 s |

The body limits are actual-byte limits. One valid oversized decimal `Content-Length` rejects early; a missing, duplicate, malformed, or understated declaration cannot bypass the limit-plus-one read. The exact boundary is accepted. Pagination rejects an overflow page before extending retained `data`, using the explicit 32 MiB cumulative safety limit and reporting retained-page context. Equivalent repeated `links.next` URLs stop the traversal before a repeated request and report the pages already fetched. Missing or null `links`, and a mapping with missing or null `next`, complete normally; present non-mapping `links` and malformed non-null `next` fail.

Nested output redaction tokenizes separators and camel/Pascal case, then recognizes semantic access/API/provider/integration/secret/Sentinel keys, authorization, tokens, cookies, sessions/session IDs, credentials, passwords, secrets, and webhooks. It preserves ordinary evidence such as `possessions`, token-expiration/session-timeout controls, webhook enablement, project keys, provider names, and secret-scanning enablement. Scalar and transport-reason redaction removes credible authorization/scheme/assignment/query/URL-user-info syntax while preserving `token expiration`, `basic configuration`, and `Bearer is the auth scheme`. Raw, quoted, scheme-wrapped/stripped, form, URL, and partial or full percent encodings of the active credential are removed; percent-triplet hex case varies independently while raw text remains case-sensitive. This supports `/`, `+`, `=`, spaces, and non-ASCII credentials, and transport output is bounded to 1000 characters.

All request bodies, OpenAPI documents, version responses, REST responses, and helper output use strict finite JSON. `NaN`, positive/negative infinity, and exponent overflow fail. Request and output serialization use `allow_nan=False` atomically. Status `204` alone may have an empty successful body and then returns `response: null`; every nonempty `2xx`, including nonempty `204`, must parse as strict JSON regardless of media type. Empty or plain-text `200` fails.

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

`--retries` applies only to `GET`, for HTTP `408`, `429`, `500`, `502`, `503`, and `504`, plus transport failures. POST, PUT, PATCH, and DELETE receive one network attempt. For writes, HTTP `408`, `429`, every `5xx`, or a transport failure is indeterminate. A read/OSError, size rejection, strict-decode failure, or invalid empty body after a non-GET `2xx` is likewise indeterminate and preserves the known status; verify the target resource or audit log before any retry. Invalid, negative, and nonfinite `Retry-After` values use a finite overflow-safe fallback, and every retry delay is capped at 60 seconds.

## Troubleshooting

- `401`: missing/invalid token, wrong `token` versus `bearer` scheme, or wrong account region.
- `403`: plan restriction, missing role/service-account permission, or wrong org/group scope.
- `404`: wrong region/ID, unavailable endpoint at the selected version, or completed API migration.
- `409`/`422`: resource state or JSON:API schema conflict; inspect the error source pointer.
- `408`, `429`, `500`, `502`, `503`, `504`: GET can retry with bounded backoff. A write never replays automatically, and every `5xx` is ambiguous for a write even though GET retries use only the explicit set.
- Post-`2xx` write response failure: the service may have applied the operation even when the body cannot be read, bounded, strictly decoded, or is invalidly empty. Use the preserved status and verify remote state before retrying.
- CLI and REST disagree: compare org ID, target reference, project type/origin, scan flags, manifest/lockfile, monitoring timestamp, REST version, and ignore policy.
- Pagination appears incomplete: follow a valid nonempty string `links.next`; do not invent cursors or assume the first `limit` rows are complete. Missing/null `links` or missing/null `next` in a mapping are terminal. Other present shapes are errors. Treat repeated-next or 32 MiB cumulative safety-limit errors as explicitly incomplete reads and report their fetched/retained-page context.
