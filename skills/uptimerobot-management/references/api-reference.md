# UptimeRobot API, MCP, and authentication reference

Use this reference for contract details. Re-check the live OpenAPI document before relying on fields that may have changed.

## Contents

- [Authoritative sources](#authoritative-sources)
- [API v3 contract](#api-v3-contract)
- [API-key types](#api-key-types)
- [Pagination](#pagination)
- [Rate limits and retries](#rate-limits-and-retries)
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
- The helper locks requests to the exact production API origin and `/v3` base path, rejects redirects, and rejects credential-like query keys.

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
- MCP list tools return pages of up to 100 items.
- Follow `nextLink` only when it remains on `https://api.uptimerobot.com` under `/v3` and contains no credential-like query key.
- Set a finite page cap. The helper defaults to 25 and refuses values below 1 or above 500.
- A bounded result is not a complete inventory unless `nextLink` becomes null.

## Rate limits and retries

- Free accounts are documented at 10 requests per minute.
- Paid-account allowance is tied to monitor count and capped at 5,000 requests per minute.
- HTTP `429` responses can include `X-RateLimit-*` and `Retry-After` headers.
- Retry only idempotent GET requests, honor a bounded `Retry-After`, and use capped exponential fallback for `429` and transient `5xx` responses.
- Never automatically retry POST, PUT, PATCH, DELETE, pause/start/reset, publication, or bulk operations after an ambiguous failure.
- MCP and direct API usage share the same account quota.

## Sensitive response fields

Monitor details may contain operational secrets, including fields such as `apiKey`, `httpPassword`, `customHttpHeaders`, and `postValueData`. Integrations and alert contacts can also contain sensitive destinations or tokens.

Default output must recursively redact:

- authorization, API-key, token, secret, credential, and password fields;
- custom HTTP header collections;
- configured POST/body values;
- exact credential values if reflected in strings.

The helper also redacts URL userinfo and values of credential-like URL query parameters before emitting JSON.

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
- `429`: stop, inspect rate-limit headers, and wait only for safe reads.
- `5xx`: service-side or transient failure; retry GET within bounds and verify mutation state manually.

Never turn a failed mutation into a loop. A timeout can mean the write succeeded but the response was lost.
