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

## Read-only examples

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
  --path accountId=123456 `
  --paginate `
  --max-pages 25
```

Inspect workspace status:

```powershell
python scripts/manage_google_tag_manager.py request `
  --operation-id tagmanager.accounts.containers.workspaces.getStatus `
  --path accountId=123456 `
  --path containerId=789012 `
  --path workspaceId=3
```

Set the short-lived token through an approved process before executing reads:

```powershell
$env:GOOGLE_TAG_MANAGER_ACCESS_TOKEN = '<short-lived token from an approved broker>'
```

The helper reports only the variable name and never the value.

## Mutation preview

Preview a workspace resource update from a reviewed JSON file:

```powershell
python scripts/manage_google_tag_manager.py request `
  --operation-id tagmanager.accounts.containers.workspaces.tags.update `
  --path path='accounts/123456/containers/789012/workspaces/3/tags/42' `
  --query fingerprint='<current fingerprint>' `
  --body-file .\tag-update.json
```

No non-GET request is sent without `--send`. After authorization, repeat the reviewed command once with `--send`, then re-read the resource.

## High-impact confirmation

Publish, create-version, delete, and user-permission writes require both `--send` and an exact confirmation value. The preview reports `confirmationRequired` and `confirmationValue`.

Example publication shape:

```powershell
python scripts/manage_google_tag_manager.py request `
  --operation-id tagmanager.accounts.containers.versions.publish `
  --path path='accounts/123456/containers/789012/versions/17' `
  --query fingerprint='<current version fingerprint>'
```

After reviewing Preview/Tag Assistant and the dry-run output:

```powershell
python scripts/manage_google_tag_manager.py request `
  --operation-id tagmanager.accounts.containers.versions.publish `
  --path path='accounts/123456/containers/789012/versions/17' `
  --query fingerprint='<current version fingerprint>' `
  --confirm tagmanager.accounts.containers.versions.publish `
  --send
```

Do not use placeholder IDs or fingerprints from these examples.

## Raw endpoint escape hatch

Raw requests must stay under `https://tagmanager.googleapis.com/tagmanager/v2`:

```powershell
python scripts/manage_google_tag_manager.py request /accounts --dry-run
```

For a high-risk raw request, confirmation is the exact method plus normalized path, for example:

```text
DELETE /accounts/123/containers/456
```

Prefer operation IDs because live Discovery metadata validates methods, path parameters, query names, request-body expectations, and required OAuth scopes.

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
- Run quick preview/compile and inspect `compilerError`.
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
