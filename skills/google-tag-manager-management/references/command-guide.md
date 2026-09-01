# Google Tag Manager command guide

The bundled helper is standard-library-only. It consumes a short-lived OAuth access token but does not acquire, refresh, cache, or print one.

## Contents

- [Prerequisites](#prerequisites)
- [Context and operation discovery](#context-and-operation-discovery)
- [Read-only examples](#read-only-examples)
- [Mutation preview](#mutation-preview)
- [High-impact confirmation](#high-impact-confirmation)
- [Raw endpoint escape hatch](#raw-endpoint-escape-hatch)
- [Direct REST shape](#direct-rest-shape)
- [Verification checklist](#verification-checklist)
- [Troubleshooting](#troubleshooting)

## Prerequisites

1. Create or select a Google Cloud project.
2. Enable the Google Tag Manager API.
3. Configure an OAuth client and consent screen appropriate to the application type.
4. Grant the Google identity or service account access inside the intended GTM account/container.
5. Request only the scopes required by the operation.

Keep OAuth client secrets, refresh tokens, and service-account key files outside the repository. Prefer an approved credential broker or workload identity over long-lived key files.

## Context and operation discovery

```powershell
python scripts/manage_google_tag_manager.py context
python scripts/manage_google_tag_manager.py operations --search accounts.list --method GET
python scripts/manage_google_tag_manager.py operations --search workspaces.getStatus
python scripts/manage_google_tag_manager.py operations --search publish
```

Use a reviewed local Discovery JSON document when offline:

```powershell
python scripts/manage_google_tag_manager.py operations `
  --discovery-file .\tagmanager-v2-discovery.json `
  --search workspace
```

Deprecated Discovery operations are hidden by default. Use `operations --include-deprecated` only to audit legacy surface area; invoking one requires the separate `request --allow-deprecated` acknowledgement after its replacement has been reviewed. Operation output exposes `scopes` with `scope_semantics: "anyOf"`; request previews use `acceptableScopes` and `scopeSemantics`. In both cases, satisfying one listed scope is sufficient for the API method.

## Read-only examples

Set the short-lived token through an approved process before executing reads:

```powershell
$env:GOOGLE_TAG_MANAGER_ACCESS_TOKEN = '<short-lived token from an approved broker>'
```

The helper reports only the variable name and never the value. It rejects any path, query value, or request body that contains the resolved credential, so the token cannot be concealed by preview redaction and then sent outside the `Authorization` header.

Preview the exact URL before making even a read:

```powershell
python scripts/manage_google_tag_manager.py request `
  --operation-id tagmanager.accounts.list `
  --dry-run
```

List containers with bounded pagination:

```powershell
python scripts/manage_google_tag_manager.py request `
  --operation-id tagmanager.accounts.containers.list `
  --path parent='accounts/123456' `
  --paginate `
  --max-pages 25
```

When `--paginate` is combined with Google's partial-response `fields` query, include top-level `nextPageToken` (for example, `fields=nextPageToken,container(containerId,name)`) or use `fields=*`. Otherwise the helper rejects the request because it cannot prove that traversal completed.

The helper accepts at most 500 pages. Local and live Discovery documents are limited to 16 MiB, each successful API body to 8 MiB, each HTTP error body to 16 KiB, and retained pagination responses cumulatively to 32 MiB. It checks a valid numeric `Content-Length` early but still reads at most `limit + 1`, so a missing or understated header cannot bypass the actual-byte limit. Response output reports `responseBytes`; unexpected non-JSON 2xx content is replaced by `[untrusted-gtm-text] non-JSON response body omitted` instead of being echoed.

Inspect workspace status:

```powershell
python scripts/manage_google_tag_manager.py request `
  --operation-id tagmanager.accounts.containers.workspaces.getStatus `
  --path path='accounts/123456/containers/789012/workspaces/3'
```

## Mutation preview

Preview a workspace resource update from a reviewed JSON file:

```powershell
python scripts/manage_google_tag_manager.py request `
  --operation-id tagmanager.accounts.containers.workspaces.tags.update `
  --path path='accounts/123456/containers/789012/workspaces/3/tags/42' `
  --query fingerprint='<current fingerprint>' `
  --body-file .\tag-update.json
```

No non-GET request is sent without `--send`. After authorization, repeat the reviewed command once with `--send`, then re-read the resource. `--retries` applies only to GET. POST, PUT, PATCH, and DELETE receive exactly one network attempt; a retryable HTTP status, URL error, or timeout means the write may have taken effect and has an indeterminate outcome. Verify the exact target state before deciding whether a manual retry is safe.

For a Discovery-backed non-GET operation that advertises a `fingerprint` query parameter, the helper requires `--query fingerprint=<current fingerprint>`. Re-read and reconcile on a stale fingerprint; do not bypass the concurrency guard.

## High-impact confirmation

Publish, create-version, delete, and user-permission writes require both `--send` and an exact confirmation value. The preview reports `confirmationRequired` and `confirmationValue`. The value is bound to the operation ID when available, method, target path, encoded query, and a canonical request-body SHA-256 digest when a body is present.

Example publication shape:

```powershell
python scripts/manage_google_tag_manager.py request `
  --operation-id tagmanager.accounts.containers.versions.publish `
  --path path='accounts/123456/containers/789012/versions/17' `
  --query fingerprint='<current version fingerprint>'
```

After reviewing Preview/Tag Assistant and the dry-run output, copy the reported value rather than reducing it to the operation ID:

```powershell
$confirmation = '<exact confirmationValue from the immediately preceding preview>'
python scripts/manage_google_tag_manager.py request `
  --operation-id tagmanager.accounts.containers.versions.publish `
  --path path='accounts/123456/containers/789012/versions/17' `
  --query fingerprint='<current version fingerprint>' `
  --confirm $confirmation `
  --send
```

Do not use placeholder IDs or fingerprints from these examples.

## Raw endpoint escape hatch

Raw requests must stay under `https://tagmanager.googleapis.com/tagmanager/v2`. Raw endpoint paths containing percent-encoded characters are rejected so encoded forms cannot bypass path-based safety classification:

```powershell
python scripts/manage_google_tag_manager.py request /accounts --dry-run
```

For a high-risk raw request without a query or body, confirmation is the exact method plus normalized path, for example:

```text
DELETE /accounts/123/containers/456
```

If a raw high-risk request has a query or body, use the complete previewed value; it includes the encoded query and body digest. Prefer operation IDs because live Discovery metadata validates methods, path parameters, query names, request-body expectations, acceptable OAuth scopes, deprecation, pagination support, and fingerprint requirements.

## Direct REST shape

```http
GET /tagmanager/v2/accounts HTTP/1.1
Host: tagmanager.googleapis.com
Authorization: Bearer <short-lived-access-token>
Accept: application/json
```

Never put the access token in a query string. Reject redirects rather than forwarding the bearer token.

## Verification checklist

- Re-read the mutated API resource and compare the fingerprint.
- Re-run workspace status and confirm no unresolved merge conflicts.
- Run quick preview/compile. The helper exits nonzero on `compilerError=true`, synchronization status errors, or unresolved sync conflicts while still printing the redacted response for diagnosis.
- Exercise Tag Assistant with positive and negative firing cases.
- Verify consent state and request payloads in the browser network panel.
- After publish, confirm the live version ID and intended environment.
- Retain the previous version ID as the rollback target.

## Troubleshooting

- `401`: obtain a fresh token through the approved OAuth flow; the helper does not refresh tokens.
- `403`: distinguish OAuth scope, GTM user permission, service enablement, and quota. Do not simply add every scope.
- Stale fingerprint: re-read and reconcile the other actor's change.
- Successful sync with conflicts: inspect and resolve the returned conflicts before version creation.
- Publish transport success with `compilerError`: treat as failed and do not claim deployment.
- Runtime tag missing: verify environment snippet, consent, trigger conditions, blocking triggers, zones, sequencing, and network policy.
