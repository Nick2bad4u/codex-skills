# WakaTime Command Guide

## Contents

- [Authentication Context](#authentication-context)
- [Summary And Stats Commands](#summary-and-stats-commands)
- [Detailed Activity Commands](#detailed-activity-commands)
- [Raw Request Escape Hatch](#raw-request-escape-hatch)
- [Write Preview And Verification](#write-preview-and-verification)
- [Troubleshooting](#troubleshooting)

## Authentication Context

```powershell
Set-Item -Path Env:WAKATIME_ACCESS_TOKEN -Value (Get-Secret WAKATIME_ACCESS_TOKEN -AsPlainText)
# Or, for personal server-side work:
Set-Item -Path Env:WAKATIME_API_KEY -Value (Get-Secret WAKATIME_API_KEY -AsPlainText)

python "<path-to-skill>/scripts/manage_wakatime.py" context --json
```

The context command reports only `oauth`, `api-key`, or `missing`, plus the environment-variable name. It never emits the secret.

## Summary And Stats Commands

```powershell
python "<path-to-skill>/scripts/manage_wakatime.py" user --json
python "<path-to-skill>/scripts/manage_wakatime.py" summaries --start 2026-08-01 --end 2026-08-07 --json
python "<path-to-skill>/scripts/manage_wakatime.py" summaries --start 2026-08-01 --end 2026-08-07 --project codex-skills --json
python "<path-to-skill>/scripts/manage_wakatime.py" stats --range last_7_days --json
python "<path-to-skill>/scripts/manage_wakatime.py" projects --search codex --json
python "<path-to-skill>/scripts/manage_wakatime.py" goals --json
```

Use ISO dates. The helper rejects an end date before the start. The API response timezone controls day boundaries.
The summaries helper sends exactly required `start` and `end` plus optional `project` and `branches`. It has no `--category` option and does not filter or relabel returned totals client-side.

## Detailed Activity Commands

```powershell
python "<path-to-skill>/scripts/manage_wakatime.py" durations --date 2026-08-22 --project codex-skills --json
python "<path-to-skill>/scripts/manage_wakatime.py" heartbeats --date 2026-08-22 --json
python "<path-to-skill>/scripts/manage_wakatime.py" data-dumps --json
```

Raw heartbeats expose more sensitive detail than summaries. Do not export or paste them wholesale when a count, aggregate, or selected metadata field answers the question.

## Raw Request Escape Hatch

Relative endpoints stay under the exact official base `https://api.wakatime.com/api/v1`:

```powershell
python "<path-to-skill>/scripts/manage_wakatime.py" request /users/current/all_time_since_today --json
python "<path-to-skill>/scripts/manage_wakatime.py" request /users/current/insights/projects/last_30_days --json
python "<path-to-skill>/scripts/manage_wakatime.py" request /users/current/projects/codex-skills/commits --query branch=main --query page=1 --json
```

The raw `request` command sends one HTTP request and returns one response; it does not aggregate paginated results. Increment `--query page=<number>` manually when all pages are required.

Use `--query name=value`; URL query strings are rejected so secrets cannot hide in an endpoint. Query names are normalized across camel/Pascal/snake/kebab/concatenated/plural forms, and credential-bearing names are rejected. Names and values are also rejected when they contain the loaded OAuth token or API key in raw, repeatedly URL-encoded, Bearer-prefixed, or Basic-encoded form. Structured previews, rendered URLs, response metadata, bodies, and nested success/error JSON use the same classifier for redaction.

Absolute endpoints must remain under the exact official host and `/api/v1` base; foreign hosts, sibling subdomains, ports, and misleading host suffixes are rejected. Malformed IPv6, invalid ports, and normalization-invalid URL authorities fail with sanitized helper errors and no traceback. Relative and absolute paths are repeatedly decoded with a strict five-pass limit. Dot segments, raw or encoded backslashes, encoded slashes or delimiters, residual escapes, and unstable deeper encodings are rejected.

## Write Preview And Verification

Preview a data export:

```powershell
python "<path-to-skill>/scripts/manage_wakatime.py" request /users/current/data_dumps --method POST --body-json '{"type":"daily","email_when_finished":false}' --json
```

Apply only after review:

```powershell
python "<path-to-skill>/scripts/manage_wakatime.py" request /users/current/data_dumps --method POST --body-file export.json --send --json
```

POST, PUT, PATCH, and DELETE are always single-attempt. If `302`, `429`, `500`, `503`, `504`, a transport failure, or a success/error response read failure occurs, the outcome may be indeterminate: inspect the current resource or data-dump state before retrying manually. This guidance remains present when the error body is incomplete, raises an HTTP protocol exception, or cannot be safely read or decoded; response streams are closed and read details are redacted. Only GET is retried automatically. Completed export `download_url` values and equivalent bearer-like URLs are redacted in every output mode and cannot be enabled on stdout.

Bodies must be strict JSON with finite numbers. `NaN`, `Infinity`, `-Infinity`, and numbers that overflow to infinity are rejected. Request bodies, errors, previews, and stdout are fully encoded before use so failure does not send a request or emit a partial marker/document.

For heartbeats, prefer the official CLI. If the API is specifically required, use a body file so shell quoting cannot corrupt file paths or timestamps. Bulk creation accepts at most 25 items per documented request.

Heartbeat deletion is irreversible:

```powershell
python "<path-to-skill>/scripts/manage_wakatime.py" request /users/current/heartbeats.bulk --method DELETE --body-file exact-heartbeats.json --json
```

The preview must show the exact date and redacted IDs/body. Require explicit user authorization before repeating with `--send`. Re-read raw heartbeats and wait for summary recalculation afterward.

## Troubleshooting

- `401`: invalid/expired OAuth token, wrong API key, or incorrect authentication method.
- `403`: missing OAuth scope, private resource, plan limitation, or organization permissions.
- `404`: wrong resource identity, unsupported range, or private/unavailable data.
- `202`: calculation queued; check status fields and retry later.
- `302` or `429`: rate limited; do not follow the redirect and reduce request rate.
- `500`, `503`, or `504`: transient server or gateway failure; only GET is retried automatically.
- Invalid runtime controls: use a finite `--timeout` greater than zero and no more than 300 seconds, plus an integer `--retries` from 0 through 10. Retry delays are bounded even when `Retry-After` is malformed or extreme.
- Missing dashboard time: compare plugin logs, local queue, raw heartbeat date in the account timezone, keystroke timeout, filters, and aggregate status.
- Duplicate time: check overlapping heartbeats and external durations before deleting anything.
