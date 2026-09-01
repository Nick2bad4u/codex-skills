# UptimeRobot API, MCP, and authentication reference

Use this reference for contract details. Re-check the live OpenAPI document before relying on fields that may have changed.

## Contents

- [Authoritative sources](#authoritative-sources)
- [API v3 contract](#api-v3-contract)
- [API-key types](#api-key-types)
- [Pagination](#pagination)
- [Rate limits and retries](#rate-limits-and-retries)
- [Helper safety limits](#helper-safety-limits)
- [Sensitive response fields](#sensitive-response-fields)
- [MCP](#mcp)
- [Error handling](#error-handling)

## Authoritative sources

- API v3 documentation: <https://uptimerobot.com/api/v3/>
- API overview and key types: <https://uptimerobot.com/api/>
- OpenAPI document: <https://cdn.uptimerobot.com/api/openapi.yaml>
- Official CLI: <https://uptimerobot.com/cli/>
- MCP integration guide: <https://help.uptimerobot.com/en/articles/12928342-uptimerobot-mcp-integration-guide>
- Dashboard integration/API-key page: <https://dashboard.uptimerobot.com/integrations>

## API v3 contract

- Base URL: `https://api.uptimerobot.com/v3`
- Authentication: `Authorization: Bearer <api-key>` according to the current OpenAPI security scheme and operation definitions.
- Media type: JSON for request and response bodies unless an endpoint documents otherwise.
- The helper locks requests to the exact production HTTPS origin and `/v3` base path, rejects redirects, userinfo, explicit ports, fragments, controls, traversal, encoded structural path changes, and encodings that remain after three path-decode rounds. It repeats this validation inside the transport before constructing authentication or an opener, including for synthetic direct callers.
- Query names are classified after raw, percent, form, and up to three repeated mixed decode rounds. Semantic key tokens and exact sensitive suffixes catch values such as encoded `apiKey`, `Set-Cookie`, and `accessToken` without misclassifying ordinary keys such as `tokenizationMode`.
- Both configured credentials are reserved exclusively for the generated `Authorization` header and must contain at least eight characters. The helper rejects either active credential at token boundaries in path, query, or JSON body keys/values through the same encoded forms. It performs the check during plan construction and again immediately before preview and transport, including every pagination request.
- Request JSON uses UTF-8, rejects duplicate object keys, `NaN`/infinity constants and float overflow, and is validated iteratively for byte, depth, node, and string limits before atomic `allow_nan=False` encoding.

The current OpenAPI surface includes:

- monitors: list, create, get, update, delete, pause, start, reset, uptime statistics, response-time statistics, storm protection, and bulk pause/start/update;
- incidents: list, detail, comments, activity, and alerts;
- monitor groups: create, list, get, update, and delete;
- maintenance windows: create, list, get, update, and delete;
- public status pages (`psps`): create, list, get, update, delete, announcements, pinning, and unpinning;
- alert contacts and integrations: create, list, get, update, and delete where documented;
- tags: list and delete;
- user/account context and contacts.

Use `python scripts/manage_uptimerobot.py operations --search <term>` to inspect current operation IDs without copying the full specification into the skill.

## API-key types

| Key type              | Intended capability                | Safe default                                                                                  |
| --------------------- | ---------------------------------- | --------------------------------------------------------------------------------------------- |
| Main account key      | All methods allowed by the account | Store only in `UPTIMEROBOT_API_KEY`; use only for an explicitly authorized mutation           |
| Read-only account key | Account-wide GET operations        | Prefer for inventories, incidents, statistics, and audits via `UPTIMEROBOT_READ_ONLY_API_KEY` |
| Monitor-specific key  | GET access limited to one monitor  | Use only for that monitor and do not infer account-wide completeness                          |

The helper chooses the read-only key first for GET requests and requires the main key for a sent mutation. It never prints either value.

## Pagination

- Collection operations commonly return `data` plus nullable `nextLink`.
- Monitor listing accepts a numeric cursor and a limit from 1 through 200.
- Monitor listing declares `customField` as an array query parameter. Serialize multiple filters as repeated `customField=key:value` pairs; repeated scalar operation parameters are invalid.
- MCP list tools return pages of up to 100 items.
- Follow `nextLink` only when it remains on `https://api.uptimerobot.com` under `/v3`, contains no credential-like query key, and retains the exact fully decoded endpoint path of the first collection page. The helper has no cross-collection allowlist.
- Preserve ordered repeated filter pairs when applying an advancing pagination cursor. Raw requests preserve ordinary repeated query names because they have no OpenAPI schema.
- Set a finite page cap. The helper defaults to 25 and refuses values below 1 or above 500.
- Reject malformed links, absolute/root-relative/relative cross-collection links, and an exact repeated resolved URL as incomplete pagination. Preserve the validated ordered query pairs when merging a relative cursor. A rejected page chain emits no mixed or falsely complete result.
- Enforce a 32 MiB cumulative actual-response limit and reject the page that would cross it before retaining or emitting that page.
- A bounded result is not a complete inventory unless `nextLink` becomes null.

## Rate limits and retries

- Free accounts are documented at 10 requests per minute.
- Paid-account allowance is tied to monitor count and capped at 5,000 requests per minute.
- HTTP `429` responses can include `X-RateLimit-*` and `Retry-After` headers.
- Retry only GET requests. The helper retries HTTP `429`, `500`, `502`, `503`, and `504`, `URLError`, and direct `TimeoutError` within the configured budget. The default is two retries and the accepted range is zero through ten, so attempts are always finite.
- Honor standards-compliant non-negative integer delta-seconds or an HTTP-date in `Retry-After`, computed from UTC and capped at 60 seconds. Fractional provider extensions are rejected. Use exponential fallback of 1, 2, 4, and so on, capped at 30 seconds, when the header is absent, malformed, fractional, non-finite, negative, or overflowing.
- POST, PUT, PATCH, and DELETE always receive one transport attempt regardless of the configured GET retry budget. Write-side HTTP `500`, `502`, `503`, and `504` plus `URLError` or direct `TimeoutError` are indeterminate: the mutation may have succeeded, was not retried, and requires an exact target re-read. Any post-attempt write response-consumption failure is also indeterminate: direct responses and `HTTPError` bodies cover read/size/OS/protocol/incomplete-read failures, while successful returned payloads additionally enforce UTF-8, strict JSON, and depth limits. A `4xx`, including `429`, is definitive only when its bounded response was consumed successfully.
- MCP and direct API usage share the same account quota.

## Helper safety limits

The helper enforces declared and actual sizes. A valid oversized `Content-Length` is an early rejection only; missing, malformed, negative, or understated headers never bypass a single `limit + 1` read of the real stream. Local files, successful responses, error responses, and remote documents are closed on every success or failure path.

| Surface                              | Limit                                                                                     |
| ------------------------------------ | ----------------------------------------------------------------------------------------- |
| Request JSON body                    | 2 MiB (`2,097,152` UTF-8 bytes), for both source input and atomic encoded output          |
| Request JSON structure               | 64 container levels; 100,000 value/container/object-key nodes; 1,000,000 chars per string |
| Local or remote OpenAPI document     | 16 MiB (`16,777,216` bytes)                                                               |
| One successful API response          | 8 MiB (`8,388,608` bytes)                                                                 |
| Successful response JSON structure   | 64 container levels; 250,000 value/container/object-key nodes; 4,194,304 chars per string |
| One HTTP/OpenAPI error response body | 16 KiB (`16,384` bytes); content is consumed but never reflected                          |
| Cumulative paginated responses       | 32 MiB (`33,554,432` bytes), checked before retaining an overflow page                    |
| Non-JSON response text retained      | 2,000 UTF-8 characters                                                                    |
| Transport-reason text retained       | 1,000 characters after whitespace normalization and redaction                             |
| Pagination pages                     | default 25; accepted range 1 through 500                                                  |
| Timeout                              | greater than zero and at most 300 seconds                                                 |

## Sensitive response fields

Monitor details may contain operational secrets, including fields such as `apiKey`, `httpPassword`, `customHttpHeaders`, and `postValueData`. Integrations and alert contacts can also contain sensitive destinations or tokens.

Default output must recursively redact:

- authorization, API-key, token, secret, credential, and password fields;
- custom, nested request, and nested response HTTP header collections, including `Cookie` and `Set-Cookie`;
- heartbeat monitor `url` and `pingUrl` capability URLs;
- passphrases and private-key fields;
- UptimeRobot `webhookURL`, `urlToNotify`, `customHeaders`, and `postValue` fields;
- integration `value` fields when the surrounding object identifies a webhook or supported integration;
- configured POST/body values and capability URLs on known heartbeat/integration providers;
- exact configured credential values if reflected in preview URLs, result URLs, pagination links/cursors, payloads, or error text.

The helper routes every emitted JSON document through one sanitizer, including operation discovery, previews, confirmations, result URLs, pagination links/cursors, payloads, embedded diagnostic URLs, and CLI errors. It repeatedly percent/form-decodes structured key names and credential variants, redacts URL userinfo and sensitive query values, and replaces active configured credentials only at token boundaries. Generic `/hooks/`, `/webhook/`, or `/webhooks/` paths on ordinary hosts remain visible unless their surrounding UptimeRobot field/object identifies a heartbeat or integration capability. Ordinary monitor URLs, `tokenizationMode`, and other non-secret fields remain visible.

## High-impact confirmation binding

Delete and bulk-monitor confirmations are derived only after the full request plan is resolved. The reported value binds:

- operation ID, when an OpenAPI operation was selected;
- HTTP method;
- normalized API-relative path;
- exact encoded query pairs, including repeated array values;
- canonical JSON SHA-256 whenever a body exists, including raw bulk request bodies.

Any target, query, or body change produces a different confirmation value.

Do not enable CLI `--reveal-secrets` unless the user explicitly needs a secret value and accepts the disclosure channel.

## MCP

- Remote URL: `https://mcp.uptimerobot.com/mcp`
- Transport: streamable HTTP
- Preferred authentication: OAuth
- Fallback authentication: bearer API key
- A read-only API key cannot invoke mutating tools.
- Tool coverage includes monitors, monitor groups, maintenance windows, incidents/comments, public status pages/announcements, integrations, and tags.
- Response-history queries support ranges from one hour through 90 days.

The current guide notes that individual OAuth clients cannot be revoked from the dashboard. Contact UptimeRobot support when revocation is required. Rotating an API key does not revoke an OAuth grant.

## Error handling

Classify failures before acting:

- `400`: validate schema, path/query names, types, and monitor subtype.
- `401`: key missing, malformed, revoked, or sent with the wrong auth scheme.
- `403`: key role or account permission does not allow the operation.
- `404`: wrong resource ID, deleted resource, or wrong account context.
- `409`/`422`: state conflict or semantic validation failure; re-read before retrying.
- `429`: retry only GET within bounds; a write-side `429` is definitive and is not retried.
- `500`/`502`/`503`/`504`: retry GET within bounds. A write response is indeterminate and requires an exact target re-read before any manual retry.
- transport loss or timeout: retry GET within bounds. A write outcome is indeterminate and requires the same target re-read.
- post-attempt response consumption: a write is one-shot and indeterminate regardless of the apparent status; report the status when available and re-read the exact target. GET retry behavior remains limited to the documented status/transport rules.

Error response bodies are bounded and consumed without reflection. Successful JSON is strict UTF-8 with duplicate-key, finite-number, depth, node, and string checks. Transport reasons are whitespace-normalized, centrally redacted, and capped at 1,000 characters. Never turn a failed mutation into a loop: a timeout, connection loss, truncated body, oversized body, or unreadable response can mean the write succeeded but its response was lost.
