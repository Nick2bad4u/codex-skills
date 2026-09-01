# WakaTime API Reference

## Contents

- [Official Sources](#official-sources)
- [Authentication And Scopes](#authentication-and-scopes)
- [Rate Limits And Status](#rate-limits-and-status)
- [Read Surfaces](#read-surfaces)
- [Write Surfaces](#write-surfaces)
- [Privacy And Sharing](#privacy-and-sharing)
- [Collection Troubleshooting](#collection-troubleshooting)

## Official Sources

- API v1 reference: <https://wakatime.com/developers>
- Official CLI repository: <https://github.com/wakatime/wakatime-cli>
- Plugin documentation: <https://wakatime.com/plugins>
- Account API key settings: <https://wakatime.com/settings/api-key>
- OAuth application settings: <https://wakatime.com/apps>

All resource URLs use `https://api.wakatime.com/api/v1/` and HTTPS. The helper normalizes this to `https://api.wakatime.com/api/v1` and rejects every other credential-bearing base, including foreign hosts, sibling subdomains, explicit ports, and misleading suffixes. Malformed IPv6, invalid ports, and normalization-invalid authorities become sanitized helper errors rather than tracebacks. Endpoint paths are repeatedly percent-decoded for at most five passes and rejected if any layer contains dot segments, encoded slash or backslash separators, delimiters, residual escapes, or deeper unstable encoding. The API reference is authoritative for endpoint availability, request bodies, plan restrictions, and required OAuth scopes.

## Authentication And Scopes

WakaTime supports:

- OAuth 2.0 bearer access tokens in `Authorization: Bearer <token>`;
- an API key sent with HTTP Basic authentication after Base64 encoding the key;
- credential query parameters, which this skill deliberately forbids because URLs leak through logs and history.

The helper normalizes query and JSON field names across camel case, Pascal case, snake case, kebab case, concatenation, and singular/plural forms. It treats client secrets, access/refresh/API tokens and keys, authorization and header containers, cookies and sessions, signatures, and AWS-style signed URL credentials as sensitive. Query names or values containing the loaded OAuth token or API key in raw, encoded, prefixed, or Basic form are rejected. The same classifier recursively redacts request previews, rendered URLs, response metadata, and nested success/error JSON.

OAuth endpoints are `https://wakatime.com/oauth/authorize`, `/oauth/token`, and `/oauth/revoke`. Use authorization code flow for durable server integrations, validate `state`, keep client secrets server-side, reuse refresh tokens, and revoke tokens when an integration disconnects.

Request only the required scopes. Important read scopes include fine-grained `read_summaries.*`, `read_stats.*`, `read_goals`, `read_orgs`, and `read_heartbeats`. `write_heartbeats`, `write_orgs`, and `write_private_leaderboards` authorize external mutations. `read_heartbeats` exposes much more detailed personal data than summary scopes.

WakaTime documents at most eight active OAuth tokens per user, ten newly created tokens per user per hour, 365-day expiration for authorization-code access tokens, and 12-hour expiration for implicit-flow tokens. Recheck the live docs before building an OAuth application.

## Rate Limits And Status

Keep requests below an average of ten per second over any five-minute period. HTTP `429` means too many requests. WakaTime may return `302` instead of `429`; do not follow that redirect with credentials. Spread requests out and retry later.

The helper automatically retries only GET after `302`, `429`, `500`, `503`, `504`, or a transport failure. `--timeout` must be finite, greater than zero, and no more than 300 seconds; `--retries` must be an integer from 0 through 10. The timeout ceiling prevents platform socket overflow before a request is opened. A `Retry-After` delay is honored only when finite and nonnegative, and is capped at 60 seconds; missing, malformed, negative, or nonfinite values use an overflow-safe capped exponential fallback. Transport retries use the same overflow-safe pattern with a 10-second cap.

POST, PUT, PATCH, and DELETE are always single-attempt because replaying them can duplicate a mutation. Every transient or response-read write failure includes indeterminate-outcome guidance, even if its error body is empty, malformed, undecodable, oversized, incomplete, or raises an HTTP protocol read exception. Response streams are closed, and read-failure details are redacted. Inspect current WakaTime state before retrying manually. Successful and error response bodies are byte-bounded with actual `limit + 1` reads, so missing or inaccurate `Content-Length` values cannot bypass the limit.

Request bodies, successful JSON responses, and error JSON must be standards-compliant and contain only finite numbers. The helper rejects `NaN`, `Infinity`, `-Infinity`, and finite-syntax values that overflow to infinity. Request serialization, safe error rendering, previews, and stdout all disable non-finite encoding and serialize fully before writing, so a rejected value cannot produce a partial request body, marker, or JSON document.

HTTP `202` means accepted but still calculating. Stats and other aggregates can report `is_up_to_date`, `percent_calculated`, `is_already_updating`, `is_cached`, or `is_stuck`. Preserve those fields and bound retries. An old cached response is not proof of current activity.

## Read Surfaces

### Summaries And Stats

`GET /users/current/summaries` returns daily aggregates for an explicit start/end range. Summaries join heartbeats within the account's keystroke-timeout window. The helper's exact summary query contract is required `start` and `end`, plus optional `project` and `branches`; it does not expose a client-side category filter or relabel totals.

`GET /users/current/stats/{range}` returns aggregates for ranges such as `last_7_days`, `last_30_days`, months, years, or other documented values. It can include languages, projects, editors, dependencies, categories, machines, operating systems, best day, daily average, and AI/human coding fields. Use response status fields before comparing periods.

Prefer summaries for a daily time series and stats for a range aggregate. Preserve the response timezone and do not add daily values that overlap.

### Projects, Goals, And Insights

`GET /users/current/projects` lists projects and accepts a search query. Project names and connected repositories can be private.

`GET /users/current/goals` and the individual goal endpoint expose progress and subscribers. Goal visibility does not make subscriber email or member metrics suitable for public reporting.

Insights provide range-specific analysis such as stats, weekdays, days, AI days, best day, projects, languages, editors, categories, machines, and operating systems. Long ranges may be recalculated on request.

### Durations, Heartbeats, Commits, And Exports

Durations are assembled activity blocks. Heartbeats are raw plugin events and can contain absolute file paths, project and branch names, editor/OS data, dependencies, cursor positions, line counts, AI-session fields, and timestamps. Query raw heartbeats only when troubleshooting or when the user explicitly needs event-level evidence.

`GET /users/current/projects/{project}/commits` associates recorded time with commits and can expose author information. Supply the branch filter and an explicit page when using the raw helper. A raw request returns one API response and does not aggregate pages; advance the `page` query manually when complete pagination is required.

`GET /users/current/data_dumps` lists generated exports. Completed export `download_url` values and equivalent signed or bearer-like links are always redacted by the helper, including JSON output; the helper provides no unsafe stdout opt-in.

Organization dashboard endpoints require `read_orgs` and can expose member activity. Apply organization access and privacy policy before retrieving or sharing them.

## Write Surfaces

### Heartbeats And External Durations

The API can create individual or bulk heartbeats; bulk creation is documented as limited to 25 heartbeats per request. Normally use `wakatime-cli`, which supplies editor and OS metadata correctly. Do not fabricate historic activity or use the API to make a dashboard look complete.

Heartbeat bulk deletion permanently removes stats. Review the date and every heartbeat ID; preview the exact body; get explicit authorization; then verify raw and aggregate data after recalculation.

External durations represent activity from non-editor sources and also alter tracked totals. Preserve their source semantics and avoid double counting activity already represented by heartbeats.

### Data Dumps, Organizations, And Leaderboards

Creating a data dump queues an export and may email the account. Its download contains extensive coding history. Treat creation, download, storage, and deletion as privacy-sensitive operations.

Organization and private-leaderboard writes require elevated scopes. Membership additions/removals, dashboard configuration, and sharing changes affect other people and need explicit scope and authorization.

## Privacy And Sharing

Use WakaTime's one-time embeddable SVG or JSON URLs for public client-side display. They can be retracted and do not expose the account key. WakaTime intentionally does not support ordinary API CORS because client-side API-key use would expose the account.

For reports, aggregate and minimize. Omit raw paths, heartbeat IDs, machine names, emails, download URLs, and precise timestamps unless needed. Never turn hours into a performance ranking without an explicit, defensible policy and the affected people's context.

## Collection Troubleshooting

Check the following before adding or modifying data:

1. Confirm the editor plugin and official `wakatime-cli` are current and executable.
2. Inspect plugin logs and the effective `.wakatime.cfg` without printing the API key.
3. Check proxy, certificate, firewall, and API reachability errors.
4. Verify project, branch, language, and category detection plus exclude/include patterns.
5. Compare raw heartbeats for one affected day with summaries in the account timezone.
6. Account for keystroke timeout, offline queueing, imported activity, and aggregate recalculation.
7. Use the dashboard or support when raw events exist but aggregates remain stuck.
