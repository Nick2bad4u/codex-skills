# Google Tag Manager API v2 reference

Use the live Discovery document for operation IDs, request schemas, parameters, and scopes rather than freezing the full API contract in this skill.

## Contents

- [Authoritative sources](#authoritative-sources)
- [Service contract](#service-contract)
- [OAuth scopes](#oauth-scopes)
- [Resource paths and IDs](#resource-paths-and-ids)
- [Fingerprints and concurrency](#fingerprints-and-concurrency)
- [Workspace/version lifecycle](#workspaceversion-lifecycle)
- [Pagination](#pagination)
- [Quotas](#quotas)
- [Error handling](#error-handling)
- [Sensitive data](#sensitive-data)

## Authoritative sources

- API overview: <https://developers.google.com/tag-platform/tag-manager/api/v2>
- Developer guide: <https://developers.google.com/tag-platform/tag-manager/api/v2/devguide>
- Authorization: <https://developers.google.com/tag-platform/tag-manager/api/v2/authorization>
- Quotas: <https://developers.google.com/tag-platform/tag-manager/api/v2/limits-quotas>
- REST reference: <https://developers.google.com/tag-platform/tag-manager/api/reference/rest/v2/accounts.containers.workspaces>
- Discovery document: <https://tagmanager.googleapis.com/$discovery/rest?version=v2>

## Service contract

- API root: `https://tagmanager.googleapis.com/`
- Service path: `tagmanager/v2/`
- Authentication: OAuth 2.0 bearer access token
- Discovery API name/version: `tagmanager` `v2`
- The helper locks live discovery and API requests to the exact Google production origins and rejects redirects, credential-like query parameters, path traversal, and other service paths.

The current API exposes account-scoped containers and nested resources including:

- destinations and Google tag configuration;
- environments, container versions, and version headers;
- workspaces and workspace status/sync/conflict resolution;
- tags, triggers, variables, built-in variables, and folders;
- custom templates;
- web/server clients, transformations, and zones;
- user permissions;
- accounts and container metadata.

Use:

```powershell
python scripts/manage_google_tag_manager.py operations --search workspace
```

to inspect current operation IDs and required scopes.

## OAuth scopes

| Scope suffix                        | Capability                                                     |
| ----------------------------------- | -------------------------------------------------------------- |
| `tagmanager.readonly`               | Read accounts, containers, workspaces, versions, and resources |
| `tagmanager.edit.containers`        | Create and edit containers and workspace resources             |
| `tagmanager.delete.containers`      | Delete containers and related resources where required         |
| `tagmanager.edit.containerversions` | Create or edit container versions                              |
| `tagmanager.publish`                | Publish container versions                                     |
| `tagmanager.manage.users`           | Manage account/container user permissions                      |
| `tagmanager.manage.accounts`        | Manage account-level configuration                             |

Use the narrowest set for the current operation. A token's scopes are not proven merely because an environment variable exists; inspect the authorization grant or handle `403` without broadening automatically.

## Resource paths and IDs

API paths use numeric IDs and canonical names such as:

```text
accounts/{accountId}
accounts/{accountId}/containers/{containerId}
accounts/{accountId}/containers/{containerId}/workspaces/{workspaceId}
```

Nested resources commonly expose a canonical `path` and a `fingerprint`. Prefer canonical paths returned by the API when the operation accepts `{+path}`.

## Fingerprints and concurrency

- `fingerprint` values implement optimistic concurrency.
- Supply the current fingerprint when an update, delete, publish, or other operation documents it.
- A stale fingerprint means another actor changed the resource. Re-read, compare, and reconcile; do not discard the guard or retry with the newest value blindly.
- Workspace sync can return HTTP success with merge conflicts in the response. Inspect conflict arrays before continuing.

## Workspace/version lifecycle

1. Read workspace status.
2. Sync with the current container version.
3. Resolve every conflict.
4. Quick-preview/compile the workspace.
5. Create a version.
6. Publish the specific version with its fingerprint.
7. Verify live-version state and runtime behavior.

Creating a version removes the source workspace and bases subsequent work on the new version. The response must be retained because it contains the version identity and compiler information.

The publish response includes compiler status. Treat a truthy `compilerError` as a failed release even if transport succeeded.

## Pagination

- List responses can contain `nextPageToken`.
- Send that value as the next request's `pageToken`.
- Keep the original resource path and non-page query filters unchanged.
- Use a finite page cap and report whether traversal completed.
- Do not include access tokens, API keys, or OAuth tokens in query parameters.

## Quotas

The documented default quota is:

- 10,000 requests per Google Cloud project per day;
- 0.25 queries per second per project, implemented as 25 requests per rolling 100 seconds.

Quota excess commonly returns HTTP `403`, not only `429`. Serialize automation, cache stable metadata, avoid polling, and request a quota increase through Google Cloud when justified. The helper retries bounded safe reads only for `429` and transient `5xx`; it does not loop on `403`.

## Error handling

- `400`: malformed resource, invalid field, wrong path parameter, or compiler/request validation.
- `401`: missing, expired, malformed, or wrong-audience access token.
- `403`: missing GTM permission, missing OAuth scope, quota exhaustion, or service account not added to GTM.
- `404`: wrong account/container/workspace/version ID or inaccessible resource.
- `409`/`412`: concurrency or fingerprint conflict; re-read and reconcile.
- `429`: rate limit; honor bounded retry only for reads.
- `5xx`: transient service failure; retry only safe reads and verify mutation state manually.

## Sensitive data

Recursively redact authorization, access/refresh tokens, client secrets, private keys, passwords, and credential fields. The helper also redacts URL userinfo and values of credential-like URL query parameters. Tag/variable values can contain identifiers or endpoints even when they are not named like secrets; minimize output and do not publish container exports unnecessarily because the helper cannot infer whether every generic GTM variable value is sensitive.
