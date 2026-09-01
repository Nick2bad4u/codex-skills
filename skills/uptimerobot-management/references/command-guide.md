# UptimeRobot command guide

Examples are non-mutating unless explicitly marked. Keep keys in environment variables or the CLI keychain; never paste them into shell history or chat output.

## Contents

- [Official CLI](#official-cli)
- [Constrained Python helper](#constrained-python-helper)
- [MCP setup](#mcp-setup)
- [Dashboard checkpoints](#dashboard-checkpoints)
- [Troubleshooting](#troubleshooting)

## Official CLI

Install or invoke the pinned known version:

```powershell
npm install --global @uptimerobot/cli@1.0.0
uptimerobot --version
```

For one-off use:

```powershell
npx --yes @uptimerobot/cli@1.0.0 --help
```

The current package requires Node.js 22.12 or newer. Before upgrading the pin, inspect release notes and rerun representative commands.

Authenticate through the keychain prompt:

```powershell
uptimerobot auth login
uptimerobot auth status
uptimerobot auth whoami --json
```

Prefer a read-only key for inspection sessions. Logout removes the stored CLI session:

```powershell
uptimerobot auth logout
```

### Inventory and triage

```powershell
uptimerobot monitors list --format json --limit 200
uptimerobot monitors list --format jsonl --status DOWN,LOOKS_DOWN
uptimerobot monitors get 123456789 --json
uptimerobot incidents list --json
uptimerobot incidents get 123456 --json
uptimerobot monitor-groups list --json
uptimerobot maintenance-windows list --json
uptimerobot alert-contacts list --json
uptimerobot integrations list --json
uptimerobot status-pages list --json
uptimerobot tags list --json
```

Retain default redaction. `--all`, `--raw`, and especially `--reveal-secrets` expand sensitive output and should not be routine agent flags.

### Monitor schemas and statistics

Inspect the official request schema before creating or updating a subtype:

```powershell
uptimerobot monitors schema http
uptimerobot monitors schema keyword --example
uptimerobot monitors schema ping --example
uptimerobot monitors uptime-stats --time-frame DAY --json
uptimerobot monitors stats response-time 123456789 --json
```

Use `uptimerobot monitors --help` and the nested command help for the exact installed CLI version; subtype flags evolve with the API.

### Mutation pattern

1. Run the command with `--dry-run` when the command supports it.
2. Review the normalized request and target ID.
3. Execute only after authorization.
4. Re-read the affected resource.

Illustrative flow:

```powershell
uptimerobot monitors pause 123456789 --dry-run
uptimerobot monitors pause 123456789
uptimerobot monitors get 123456789 --json
```

Deletes require the CLI confirmation flow. Do not bypass confirmation merely for automation. Bulk actions require an enumerated target set and per-result verification.

## Constrained Python helper

The helper is standard-library-only and does not store credentials.

Inspect context:

```powershell
python scripts/manage_uptimerobot.py context
```

Discover live OpenAPI operations:

```powershell
python scripts/manage_uptimerobot.py operations --search monitor --method GET
python scripts/manage_uptimerobot.py operations --tag "Public Status Pages"
```

Use a reviewed local OpenAPI fixture when offline:

```powershell
python scripts/manage_uptimerobot.py operations --spec-file .\openapi.yaml --search incident
```

Preview an operation-based request:

```powershell
python scripts/manage_uptimerobot.py request `
  --operation-id MonitorsController_list `
  --query limit=200 `
  --dry-run
```

Repeat OpenAPI array-valued query parameters once per value. The current monitor-list operation declares `customField` as an array, while repeated scalar parameters are rejected:

```powershell
python scripts/manage_uptimerobot.py request `
  --operation-id MonitorsController_list `
  --query 'customField=environment:production' `
  --query 'customField=team:platform' `
  --dry-run
```

Raw requests preserve ordinary repeated query names in the supplied order because no OpenAPI parameter schema is available to classify them.

Preview a raw endpoint mutation. The absence of `--send` keeps every non-GET request non-mutating:

```powershell
python scripts/manage_uptimerobot.py request /monitors/123456789/pause --method POST
```

Execute only after reviewing the preview and establishing the main-key environment variable through an approved secret store:

```powershell
python scripts/manage_uptimerobot.py request /monitors/123456789/pause --method POST --send
```

Deletes and bulk monitor operations require the preview's exact `confirmationValue` in addition to `--send`:

```powershell
python scripts/manage_uptimerobot.py request /monitors/123456789 --method DELETE
python scripts/manage_uptimerobot.py request /monitors/123456789 --method DELETE `
  --confirm 'DELETE /monitors/123456789' `
  --send
```

The confirmation phrase is generated only after the full plan is resolved. It includes the operation ID when available, HTTP method, normalized API-relative path, exact encoded query, and `body-sha256=<digest>` whenever a JSON body exists. Raw bulk bodies are included through the same canonical JSON SHA-256 digest. Copy the complete reported value; never reuse it after changing an operation, target, query pair, or body.

For bounded collection traversal:

```powershell
python scripts/manage_uptimerobot.py request /monitors `
  --query limit=200 `
  --paginate `
  --max-pages 25
```

The helper validates every `nextLink`, requires the exact normalized collection endpoint path on every page, preserves repeated query/filter pairs while replacing advancing cursor values, rejects malformed, cross-collection, or repeated resolved links, redacts every emitted page URL/link/payload, retries only GET requests, and rejects redirects. Both configured keys must contain at least eight characters and are forbidden at token boundaries in request paths, queries, and JSON bodies in raw, percent-encoded, form-encoded, or repeatedly encoded form; the helper rechecks immediately before preview, transport, and each pagination request.

Before building an authenticated opener, the transport repeats exact HTTPS origin and `/v3` confinement and rejects userinfo, explicit ports, fragments, controls, traversal, encoded structural path changes, and residual encodings. This applies to ordinary CLI plans and synthetic direct callers.

`--body-json` and `--body-file` use strict UTF-8 JSON. Duplicate object keys are rejected rather than keeping the last value; `NaN`, infinity, and float overflow are invalid. Body files use a binary `limit + 1` read and are always closed, and the parsed tree is checked iteratively before atomic `allow_nan=False` encoding.

Exact helper limits are:

- 16 MiB for a local or remote OpenAPI document;
- 2 MiB for request JSON source bytes and the final encoded body;
- 64 request JSON container levels, 100,000 request value/container/object-key nodes, and 1,000,000 characters per request key/string;
- 8 MiB for one successful API response;
- 64 response JSON container levels, 250,000 response value/container/object-key nodes, and 4,194,304 characters per response key/string;
- 16 KiB for one consumed, non-reflected error response body;
- 32 MiB of cumulative paginated response bytes, checked before retaining the overflowing page;
- 25 pages by default and at most 500 pages;
- 2,000 retained characters for a non-JSON response and 1,000 redacted characters for a transport reason;
- a timeout greater than zero and at most 300 seconds, plus zero through ten configured GET retries.

Every stream is read with an actual `limit + 1` check and closed. `Content-Length` can reject an oversized response early but cannot authorize a missing, malformed, negative, or dishonest body size. `Retry-After` accepts standards-compliant non-negative integer delta-seconds or an HTTP-date relative to UTC and caps either at 60 seconds. Fractional extensions, absent/malformed values, non-finite/negative values, and invalid dates use exponential fallback capped at 30 seconds.

POST, PUT, PATCH, and DELETE receive one attempt. Write-side HTTP `500`, `502`, `503`, and `504`, transport loss, and every post-attempt response-consumption failure are reported as indeterminate because the mutation may have succeeded. Direct responses and `HTTPError` bodies enforce size/read/protocol/incomplete-read safety; successful returned payloads additionally enforce UTF-8, strict JSON, and depth safety. Re-read the exact target before retrying manually. A write-side `4xx`, including `429`, is definitive only after its bounded response is consumed successfully.

Output key names are classified after repeated percent/form decoding with semantic tokens and exact sensitive suffixes. UptimeRobot heartbeat/integration fields and known-provider callback capabilities remain redacted, while ordinary monitor URLs—including generic `/hooks/status` paths on ordinary hosts—and fields such as `tokenizationMode` remain visible.

## MCP setup

Configure a streamable HTTP MCP server:

```yaml
name: uptimerobot
transport: streamable_http
url: https://mcp.uptimerobot.com/mcp
```

Authorize with OAuth when the client supports it. If API-key fallback is required, use a read-only key for inspection. Review mutating tool arguments before invocation and verify state afterward with an independent read.

## Dashboard checkpoints

- Monitors: <https://dashboard.uptimerobot.com/monitors>
- Integrations and API keys: <https://dashboard.uptimerobot.com/integrations>
- Status and incidents: <https://dashboard.uptimerobot.com/status>

Use the dashboard to confirm account identity, routing, rendered status-page behavior, and settings absent from API/CLI output. Avoid exposing key values in screenshots.

## Troubleshooting

- Authentication failure: run `uptimerobot auth status`, confirm key role, and test a minimal GET.
- Empty inventory: confirm account/key scope and pagination before concluding no resources exist.
- CLI/API disagreement: compare CLI `--raw` only in a secure channel, inspect the current OpenAPI operation, and record versions.
- Repeated `429`: stop parallel enumeration, honor `Retry-After`, and reduce page concurrency.
- Ambiguous mutation timeout: re-read the resource; do not resend blindly.
- MCP authorization cannot be revoked: disconnect locally and contact UptimeRobot support for OAuth revocation.
