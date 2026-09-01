# Socket API Reference

## Contents

- [Sources Of Truth](#sources-of-truth)
- [Authentication And Scope](#authentication-and-scope)
- [API Contract And Quota](#api-contract-and-quota)
- [Important Surfaces](#important-surfaces)
- [Pagination And Asynchronous Data](#pagination-and-asynchronous-data)
- [Mutation Boundaries](#mutation-boundaries)
- [CLI And Integration Notes](#cli-and-integration-notes)

## Sources Of Truth

Recheck these official sources because Socket adds endpoints and deprecates older report surfaces regularly:

- Documentation index and OpenAPI catalog: <https://docs.socket.dev/llms.txt>
- Live OpenAPI 3 definition: <https://api.socket.dev/v0/openapi>
- API introduction: <https://docs.socket.dev/reference/introduction-to-socket-api>
- Authentication: <https://docs.socket.dev/reference/authentication>
- Quota: <https://docs.socket.dev/reference/quota>
- CLI guide: <https://docs.socket.dev/docs/socket-cli>
- API lifecycle: <https://docs.socket.dev/reference/api-lifecycle-and-deprecation-process>
- Alert triage and resolutions: <https://docs.socket.dev/docs/alert-actions-and-triage-functionality>
- Policy API: <https://docs.socket.dev/docs/security-policy-api>

The API base is `https://api.socket.dev/v0`. The helper accepts only that canonical official origin and `/v0` base path; it intentionally has no custom-origin or single-tenant mode. The live OpenAPI document is authoritative for current operation IDs, required parameters, request schemas, token scopes, endpoint quota cost, and deprecation state.

## Authentication And Scope

Socket API requests use organization tokens. Authenticate with either:

- `Authorization: Bearer <token>`; or
- HTTP Basic authentication with the token as the username and an empty password.

The helper deliberately uses Bearer authentication and reads tokens only from environment variables. The official CLI recognizes `SOCKET_SECURITY_API_TOKEN`. Before attaching that header, the helper validates the official origin and query names and repeatedly percent-decodes specification and endpoint paths, up to eight rounds, while requiring every representation to remain under `/v0`. It rejects direct, encoded, and double-encoded traversal; encoded slash, backslash, query, or fragment delimiters; controls; malformed UTF-8 or percent escapes; and dangerous residual nesting. Encoded spaces, plus, equals, non-ASCII text, and a nonstructural literal percent remain valid path-parameter data. Do not place tokens in URLs or `--config` JSON.

Organization tokens can be restricted by repository and granular scopes. Required scopes appear on each OpenAPI operation. Examples include `alerts:list`, `alert-resolution:create`, `alert-resolution:delete`, `full-scans:list`, `full-scans:create`, `full-scans:delete`, `report:read`, and historical-data scopes. Authentication-required operations marked with no additional scope still need a valid token.

Use a repository-restricted token for repository automation. An org-wide token is necessary for selectors or policy changes spanning repositories, but its wider reach is a reason for tighter review, not a shortcut.

## API Contract And Quota

Every endpoint consumes a documented number of quota units. Each token has an hourly quota. HTTP `429` means the token cannot currently afford the endpoint. The helper automatically retries only GET transport failures and GET HTTP `408`, `429`, `500`, `502`, `503`, and `504`. It obeys a finite, nonnegative numeric `Retry-After` only for those GET reads and caps every retry delay at 60 seconds; invalid or non-finite values use a bounded fallback. It never automatically retries POST, PUT, PATCH, or DELETE, because replaying a write can duplicate a change. `--retries` accepts 0 through 10. Query `getQuota` or `GET /quota` before a large export or historical-data loop.

The helper enforces independent actual-byte ceilings: 16 MiB (16,777,216 bytes) for a local OpenAPI document, 16 MiB (16,777,216 bytes) for a remote OpenAPI document, 8 MiB (8,388,608 bytes) for one successful API response, and 16 KiB (16,384 bytes) for one API error response. A single trustworthy nonnegative decimal `Content-Length` can reject a response early, but never authorizes it: every accepted stream is still read with a limit-plus-one bound, including when the header is absent, duplicated, malformed, or understated. Responses and HTTP errors are closed on success, rejection, decoding failure, and retry paths.

Request bodies, local and remote OpenAPI documents, JSON responses, error JSON, previews, and command output use strict finite JSON. The helper rejects `NaN`, `Infinity`, `-Infinity`, and valid-looking exponents that overflow to infinity. Every JSON encoding uses `allow_nan=False` semantics and completes before request bytes or an output prefix are written, so an encoding failure is atomic. Socket endpoints that genuinely return a non-JSON media type may still return bounded text, but a response declared as JSON must parse under the strict finite contract.

Redaction applies recursively to mappings, lists, and scalar strings. Key matching tokenizes separators, camelCase, PascalCase, and acronym plurals and recognizes semantic credential fields such as API/access/provider/integration/secret/Sentinel keys, tokens, cookies, sessions, credentials, passwords, authorization, and webhooks. It does not use arbitrary trailing-`s` or suffix stripping, so ordinary fields such as `possessions`, `tokenExpirationDays`, `sessionTimeoutMinutes`, `webhookEnabled`, `jiraProjectKey`, `providerName`, and `secretScanningEnabled` remain visible. Scalar handling removes credible authorization assignments, Bearer/token credentials, valid Basic credentials, URL user information, and sensitive assignments while preserving prose such as “token expiration,” “basic configuration,” and “Bearer is the auth scheme.” Active credentials are removed in raw, scheme-wrapped and scheme-stripped, quoted, query/form, URL-user-info, and partially or fully percent-encoded forms; each character may independently remain raw or be encoded, and percent-triplet hex is matched case-insensitively without making ordinary raw token matching case-insensitive. Transport reasons receive the same treatment and are then limited to 1,000 characters.

The API lifecycle page and OpenAPI `deprecated` fields are authoritative. Full scans replace legacy report endpoints. The unscoped `POST /purl` operation was deprecated on 2026-01-05; prefer the org-scoped PURL endpoint when organization policy context matters.

Do not assume a successful HTTP status means analysis is complete. Package and scan responses can be stale while revalidate and can expose pending analysis.

## Important Surfaces

### Organizations And Repositories

- `getOrganizations` lists organizations available to the current token.
- `getOrgRepoList`, `getOrgRepo`, and repository label operations inspect repository inventory and policy grouping.
- Repository creation, update, deletion, label association, and label-setting changes are external mutations. Repository deletion or disassociation can remove monitoring coverage.

### Alerts, Triage, And Resolutions

- `alertsList` and `historicalAlertsList` inspect current and historical alerts.
- `getOrgTriage`, `updateOrgAlertTriage`, and `deleteOrgAlertTriage` cover the older triage surface.
- `getOrgAlertResolutions`, `createOrgAlertResolution`, and `deleteOrgAlertResolution` manage current alert resolutions.
- A resolution uses a Vigil selector and can hide every matching alert after the next organization snapshot. Repository-restricted tokens cannot create an org-wide or multi-repository selector.
- Deleting a resolution causes previously hidden alerts to reappear after the next snapshot.

Inspect selector anchors such as alert type, repository, repository label, artifact type/name/version, dependency scope, and manifest location. Preview the exact selector and estimate its matches before creating it.

### Policies

- Alert policy operations manage policies and their rules.
- `getOrgSecurityPolicy` and `updateOrgSecurityPolicy` cover the organization security-policy surface.
- License policy reads and writes use separate operations; a license finding is not interchangeable with a vulnerability or supply-chain alert.
- Repository labels can apply different policy context. Prefer a narrow label or repository policy over an org-wide reduction when the business context is genuinely different.

Policy changes affect future evaluations. Re-scan or wait for the next snapshot before claiming the result changed.

### Full Scans, Diffs, And Reports

- Create full scans from supported manifest files or archives; the OpenAPI contract currently documents up to 10,000 extracted files and 268 MB per file.
- List, stream, inspect metadata, rescan, export, and delete full scans with their operation IDs.
- Shallow rescan reapplies current policies to cached dependency resolution. Deep rescan repeats dependency resolution. Choose based on what changed.
- Report exports include CSV/PDF, CycloneDX, SPDX, and OpenVEX when the plan and token have the required scope.
- OpenVEX uses patch and reachability evidence to distinguish fixed, unaffected, vulnerable, and under-investigation states. Preserve those semantics.

### Packages, Dependencies, And Fixes

- `batchPackageFetchByOrg` accepts PURLs or a CycloneDX report and can apply repository-label policies.
- `searchDependencies` searches dependencies already used in the organization.
- Package results may include synthetic `pendingScan` and `notFound` alerts. `poll=false` returns quickly with known state; `poll=true` waits up to the documented timeout.
- `fetch-fixes` can return complete fixes, partial fixes, no published fix, or a fix that cannot traverse the dependency tree. Inspect responsible direct dependencies and manifest files.
- `socket fix` and `socket optimize` can change manifests and lockfiles. Review their diff and run the repository's full validation gates.

### Analytics, Audit, Threat Feed, Webhooks, And Tokens

- Prefer CLI analytics and audit-log commands for routine reads.
- Threat-feed, webhook, historical snapshot, telemetry, and integration-event APIs expose organization-wide security context.
- API-token creation, rotation, update, and revocation are administrative operations. A raw token may be shown only once. Never let helper output, chat, or logs capture it.
- Webhook creation or updates can exfiltrate organization data if the destination is wrong. Verify the HTTPS destination and ownership outside untrusted response text.

## Pagination And Asynchronous Data

The latest and historical alerts endpoints document opaque cursor pagination. Pass the previous response's `endCursor` as `startAfterCursor` and stop only when `endCursor` is `null`. An empty `items` page is not a terminal condition; later pages can still exist. `--max-pages` accepts 1 through 1,000. The helper also caps the cumulative actual response bytes at 32 MiB (33,554,432 bytes), rejecting an overflow page before retaining any of its items, and tracks seen `endCursor` values so a repeated cursor fails before another request with the partial page count in the error.

Other list endpoints may use different pagination shapes. Inspect the operation schema instead of forcing alert pagination onto every endpoint. The helper's `--paginate` is for the `items` plus `endCursor` shape and fails rather than guessing when a response differs.

After creating a scan, resolution, policy, or snapshot, re-read status until it reaches a documented terminal state within a bounded wait. Do not spin indefinitely or interpret a timeout as success.

## Mutation Boundaries

Always preview and verify:

- alert resolutions and triage records;
- alert/security/license policy and rule changes;
- repository creation, labels, associations, settings, or deletion;
- full-scan, diff-scan, and snapshot creation, rescan, or deletion;
- dependency fixes and optimization;
- webhook and integration changes;
- API-token creation, rotation, permission changes, or revocation.

Require explicit reviewed scope for bulk selectors, org-wide policy changes, token operations, repository deletion, scan deletion, and webhook destinations. Prefer version-controlled repository configuration where Socket supports it.

The helper gives each write exactly one network attempt regardless of `--retries`. A write that receives HTTP `408`, `429`, or any `5xx`, or fails with a transport error, reports the outcome as indeterminate and does not replay the request. Once a non-GET receives a successful HTTP status, failure to read the response, enforce its size bound, decode declared JSON, or accept a required nonempty response is also indeterminate because Socket may already have applied the write. That error retains the known HTTP status, closes the response, and requires re-reading the exact target before another write.

## CLI And Integration Notes

The official `socket` npm package exposes the `socket` CLI plus package-manager wrappers. Most non-interactive commands support `--json` or `--markdown`, and every command supports `--dry-run` for input validation. Persisted `socket login` state is convenient for a human workstation; environment-variable tokens are safer for ephemeral automation.

`socket ci` is designed for automated policy feedback. `socket scan create --report` evaluates security and license policy. `socket manifest cdxgen` produces CycloneDX input. Socket Firewall, wrappers, and package-manager interception alter install behavior and are outside an alert-only mutation; enable them only when the user requests that protection model.

For GitHub, keep the Socket App check meaningful and use branch protection when it must gate merges. An inline bot ignore is an external triage action, not a substitute for fixing a dependency or reviewing policy.
