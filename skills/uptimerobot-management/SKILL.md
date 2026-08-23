---
name: uptimerobot-management
description: Inspect and manage UptimeRobot monitors, incidents, integrations, alert contacts, maintenance windows, groups, public status pages, tags, API v3, CLI, and MCP access. Use whenever the user mentions UptimeRobot, uptime monitoring, outages, status pages, notification routing, API or CLI automation, or asks to audit or safely change UptimeRobot state.
---

# UptimeRobot Management

Operate UptimeRobot from evidence, keep credentials out of output, and make every mutation deliberate and reviewable.

## Choose the interface

- Prefer the official UptimeRobot CLI for routine monitor, incident, group, maintenance-window, alert-contact, integration, tag, and status-page work. It provides schemas, redaction, structured output, dry runs, and delete confirmations.
- Prefer the official remote MCP server at `https://mcp.uptimerobot.com/mcp` when an MCP-capable client is already connected. Use OAuth when practical; use an API key only when OAuth is unavailable.
- Use `scripts/manage_uptimerobot.py` for credential-safe context checks, current OpenAPI operation discovery, repeatable request previews, constrained API escape hatches, or bounded cursor pagination.
- Use the dashboard for visual confirmation, OAuth setup, policy/account settings not exposed by the other interfaces, and final human review. Do not infer hidden state from a screenshot.

Read [references/command-guide.md](references/command-guide.md) for exact commands and [references/api-reference.md](references/api-reference.md) for API, authentication, pagination, rate-limit, and redaction details.

## Establish context

1. Identify the intended account, monitor or resource IDs, environment, and time range. Do not assume similarly named monitors are interchangeable.
2. Run `python scripts/manage_uptimerobot.py context`. Report credential presence and source names only, never values.
3. For read-only work, prefer `UPTIMEROBOT_READ_ONLY_API_KEY`. Fall back to `UPTIMEROBOT_API_KEY` only when necessary.
4. For mutations, require the main account key in `UPTIMEROBOT_API_KEY` or an OAuth-authorized MCP session. A monitor-specific or read-only key is insufficient.
5. Confirm whether the user asked for inspection, a proposed change, or execution. Inspection never implies mutation.

## Inspect before changing

1. Capture the target resource and its current state with normalized JSON.
2. Correlate monitor status with incidents, response-time or uptime statistics, maintenance windows, alert contacts, integrations, and status-page visibility as relevant.
3. Distinguish an active outage from a paused monitor, scheduled maintenance, notification delivery failure, stale status-page data, or a monitor configuration defect.
4. Record IDs, status, timestamps, affected destinations, filters, pagination bounds, and source interface. Redact credential-like monitor fields and custom request secrets.
5. If a result is paginated, follow only validated same-origin cursors and state the page cap used.

## Apply safe mutations

1. Restate the exact resource, requested end state, user-visible impact, and rollback or compensating action.
2. Preview first. Use CLI `--dry-run` where supported, omit helper `--send`, or present the MCP tool arguments before invoking a mutating tool.
3. Obtain explicit authorization for the specific mutation when the current request does not already authorize it. Treat delete, bulk pause/start/update, incident publication, integration changes, status-page publication, and credential-bearing monitor edits as high impact. The helper additionally requires its reported exact `--confirm` value for deletes and bulk monitor operations.
4. Execute once. Do not automatically retry a mutation after a timeout or ambiguous failure.
5. Re-read the resource and adjacent state. Verify the intended fields, monitor runtime status, incident/status-page effect, and notification routing rather than trusting only the write response.
6. Report the before/after state, interface used, verification evidence, and any unresolved warnings.

## Triage common requests

### Monitor outage or flapping

Inspect the monitor, current and recent incidents, activity/alerts, response-time and uptime statistics, maintenance overlap, and relevant integrations. Do not reset statistics or pause the monitor merely to clear a noisy dashboard.

### Monitor creation or update

Use `uptimerobot monitors schema <type>` before authoring a request. Confirm URL/host, interval, timeout, regions, HTTP method, expected status, keyword/JSON checks, authentication, SSL behavior, alert contacts, group, and tags. Keep secrets in supported secret inputs or environment variables and verify with a follow-up `get` while retaining default redaction.

### Integrations and alert contacts

Inventory both resources and map which monitors or account policies use them. Test or replace routing deliberately; deleting an integration or contact can silently reduce outage notification coverage.

### Maintenance windows

Check timezone, recurrence, scope, start/end, and overlap. Verify affected monitors after creation or update. Do not use maintenance windows as a permanent suppression mechanism.

### Public status pages and incidents

Separate internal monitor state from public communication. Review page monitors, visibility, custom domain, subscriber behavior, active incidents, announcements, and pinned content. Publishing or resolving a public incident is an external communication and requires explicit intent.

### Bulk operations

Resolve the exact group/tag filters and enumerate the projected monitor set before a bulk pause, start, or update. Set an explicit safety bound and verify every per-monitor result.

## MCP rules

- Configure `https://mcp.uptimerobot.com/mcp` as a streamable HTTP server and prefer OAuth authorization.
- Treat MCP and API/CLI calls as sharing the account quota.
- Keep a read-only API key read-only; do not replace it with the main key merely to make a mutation succeed.
- OAuth client revocation may require UptimeRobot support. Disconnecting a client locally or rotating an API key does not necessarily revoke an OAuth grant.
- Apply the same preview, authorization, single-write, and post-write verification rules to MCP tools.

## Output contract

Return:

- account/resource scope and interface used;
- findings with IDs, status, timestamps, and filters;
- redacted preview for proposed mutations;
- execution and post-write verification evidence when authorized;
- pagination/rate-limit bounds and any incomplete coverage;
- risks, rollback guidance, and next actions.

Never print API keys, authorization headers, monitor passwords, custom HTTP headers, post bodies, or other credential-like values.
