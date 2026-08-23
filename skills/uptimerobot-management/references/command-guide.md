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

For an operation-based delete or bulk request, use the reported operation ID as the confirmation value. Never reuse a confirmation value for a different target.

For bounded collection traversal:

```powershell
python scripts/manage_uptimerobot.py request /monitors `
  --query limit=200 `
  --paginate `
  --max-pages 25
```

The helper validates every `nextLink`, redacts sensitive fields, retries only safe reads, and rejects redirects.

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
