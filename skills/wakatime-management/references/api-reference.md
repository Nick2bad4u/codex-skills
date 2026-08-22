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

All resource URLs use `https://api.wakatime.com/api/v1/` and HTTPS. The API reference is authoritative for endpoint availability, request bodies, plan restrictions, and required OAuth scopes.

## Authentication And Scopes

WakaTime supports:

- OAuth 2.0 bearer access tokens in `Authorization: Bearer <token>`;
- an API key sent with HTTP Basic authentication after Base64 encoding the key;
- credential query parameters, which this skill deliberately forbids because URLs leak through logs and history.

OAuth endpoints are `https://wakatime.com/oauth/authorize`, `/oauth/token`, and `/oauth/revoke`. Use authorization code flow for durable server integrations, validate `state`, keep client secrets server-side, reuse refresh tokens, and revoke tokens when an integration disconnects.

Request only the required scopes. Important read scopes include fine-grained `read_summaries.*`, `read_stats.*`, `read_goals`, `read_orgs`, and `read_heartbeats`. `write_heartbeats`, `write_orgs`, and `write_private_leaderboards` authorize external mutations. `read_heartbeats` exposes much more detailed personal data than summary scopes.

WakaTime documents at most eight active OAuth tokens per user, ten newly created tokens per user per hour, 365-day expiration for authorization-code access tokens, and 12-hour expiration for implicit-flow tokens. Recheck the live docs before building an OAuth application.

## Rate Limits And Status

Keep requests below an average of ten per second over any five-minute period. HTTP `429` means too many requests. WakaTime may return `302` instead of `429`; do not follow that redirect with credentials. Spread requests out and retry later.

HTTP `202` means accepted but still calculating. Stats and other aggregates can report `is_up_to_date`, `percent_calculated`, `is_already_updating`, `is_cached`, or `is_stuck`. Preserve those fields and bound retries. An old cached response is not proof of current activity.

## Read Surfaces

### Summaries And Stats

`GET /users/current/summaries` returns daily aggregates for an explicit start/end range. Summaries join heartbeats within the account's keystroke-timeout window. Filters include project, branch, category, and other documented dimensions.

`GET /users/current/stats/{range}` returns aggregates for ranges such as `last_7_days`, `last_30_days`, months, years, or other documented values. It can include languages, projects, editors, dependencies, categories, machines, operating systems, best day, daily average, and AI/human coding fields. Use response status fields before comparing periods.

Prefer summaries for a daily time series and stats for a range aggregate. Preserve the response timezone and do not add daily values that overlap.

### Projects, Goals, And Insights

`GET /users/current/projects` lists projects and accepts a search query. Project names and connected repositories can be private.

`GET /users/current/goals` and the individual goal endpoint expose progress and subscribers. Goal visibility does not make subscriber email or member metrics suitable for public reporting.

Insights provide range-specific analysis such as stats, weekdays, days, AI days, best day, projects, languages, editors, categories, machines, and operating systems. Long ranges may be recalculated on request.

### Durations, Heartbeats, Commits, And Exports

Durations are assembled activity blocks. Heartbeats are raw plugin events and can contain absolute file paths, project and branch names, editor/OS data, dependencies, cursor positions, line counts, AI-session fields, and timestamps. Query raw heartbeats only when troubleshooting or when the user explicitly needs event-level evidence.

Commit endpoints associate recorded time with commits and can expose author information. Verify repository and branch filters.

`GET /users/current/data_dumps` lists generated exports. Completed export download URLs are sensitive bearer-like links; do not paste them into chat or logs.

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
