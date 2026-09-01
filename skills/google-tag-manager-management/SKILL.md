---
name: google-tag-manager-management
description: Inspect and manage Google Tag Manager accounts, containers, workspaces, resources, versions, permissions, consent, previews, and publishing through API v2. Use whenever the user mentions Google Tag Manager or GTM, tags, triggers, variables, consent mode, container versions, publishing, permissions, or API automation.
---

# Google Tag Manager Management

Treat every GTM change as production instrumentation work: identify the exact account/container/workspace, preserve concurrency fingerprints, preview the mutation, and verify both the API resource and runtime behavior.

## Select the surface

- Use the web application for visual workspace review, Preview/Tag Assistant, consent debugging, environment links, version comparison, and final publication review.
- Use `scripts/manage_google_tag_manager.py` for current Discovery API operation lookup, credential-safe context, deterministic JSON request previews, bounded pagination, and reviewed API v2 execution.
- Use direct REST or an official Google client library for application code that needs token refresh, typed models, or long-running automation. Keep OAuth acquisition outside the bundled helper.
- GTM has no first-party operational CLI equivalent to the UptimeRobot CLI. Do not invent command behavior or route GTM management through unrelated Google Analytics tools.

Read [references/command-guide.md](references/command-guide.md) for exact helper/API examples, [references/api-reference.md](references/api-reference.md) for resources, scopes, quotas, and concurrency, and [references/consent-and-publishing.md](references/consent-and-publishing.md) for consent and release gates.

## Establish exact context

1. Resolve numeric `accountId`, `containerId`, and `workspaceId`; record the container type and environment. Names are not unique identifiers.
2. Determine whether the task targets a web container, server container, mobile container, destination/Google tag, or account permissions.
3. Run `python scripts/manage_google_tag_manager.py context`. Report only whether an access token is configured and its environment-variable name.
4. Start with the read-only OAuth scope. Add edit, publish, delete, account, or user-management scopes only for the specifically authorized operation.
5. Use a test account/container for development whenever possible. GTM API destructive operations do not provide the web UI's warning and undo experience.

## Inspect before editing

1. Read account/container/workspace metadata and the current container version.
2. Read workspace status before any change. Sync when the workspace base is stale, then inspect every merge conflict.
3. Inventory the affected tags, triggers, variables, folders, templates, clients, transformations, zones, built-in variables, and consent settings. Trace references by ID.
4. Preserve each resource `fingerprint`; it is the optimistic-concurrency guard. Never silently overwrite a newer revision.
5. Capture the current live version and environment deployment so post-change verification has a stable baseline.

Use `current workspace resources, reference links, conflict status, and fingerprints` to produce `a redacted mutation preview and coherent reviewed change set`.

1. Prefer an isolated, purpose-named workspace with one coherent change set.
2. Use the smallest resource mutation that achieves the request. Do not rewrite an entire container export for a one-resource edit.
3. Keep secrets and user identifiers out of tags, variables, request URLs, logs, fixtures, and commits. Prefer GTM-supported secret handling and server-side controls.
4. Maintain tag firing and blocking relationships, trigger filters, variable references, sequencing, consent requirements, zones, and environment constraints.
5. Preview every write. The helper executes GET by default, but all non-GET requests remain dry runs until `--send` is supplied.
6. Automatic retries apply only to `GET`. POST, PUT, PATCH, and DELETE receive exactly one attempt; after a retryable HTTP failure, URL error, or timeout, treat the outcome as indeterminate and verify GTM state before any manual retry.

## Resolve, version, and publish

1. Call workspace status and sync before version creation. A successful sync response can still contain merge conflicts; success does not mean conflict-free.
2. Resolve conflicts explicitly and re-read the changed resources and fingerprints.
3. Run quick preview/compile checks and use Tag Assistant against the intended environment. Verify firing and non-firing cases, payloads, consent state, duplicates, and console/network errors.
4. Creating a container version deletes the source workspace and moves the base version forward. Treat `create_version` as high impact and preserve the response version ID.
5. Publish the reviewed version with its current fingerprint and the helper's exact target-bound confirmation value. The helper exits nonzero for `compilerError`, synchronization errors, and unresolved sync conflicts even when the HTTP request succeeds; retain and inspect its redacted response.
6. Re-read the live container version and exercise the deployed runtime. API success alone does not prove tag delivery or analytics ingestion.

## High-impact operations

Require explicit target and confirmation for:

- publishing a version;
- creating a version from a workspace;
- deleting accounts, containers, versions, workspaces, or resources;
- adding, changing, or removing user permissions;
- changing environments, zones, destinations, custom templates, or server-container clients;
- changing consent defaults or consent update behavior.

The helper requires the exact previewed `confirmationValue` for publish, version creation, delete, and user-permission writes. That value binds the operation ID when available, HTTP method, normalized path, encoded query, and a SHA-256 digest when a body is present. Copy it from the preview instead of constructing it manually. Raw high-risk requests without a query or body retain the shorter `METHOD /path` shape.

## Consent mode

- Set consent defaults before measurement commands or tags can fire.
- Model `ad_storage`, `analytics_storage`, `ad_user_data`, and `ad_personalization` deliberately; do not infer legal requirements.
- In custom templates, use Tag Manager consent APIs such as `setDefaultConsentState` and `updateConsentState` rather than queued `gtag` calls when ordering matters.
- Verify default, denied, granted, update, regional, and navigation cases in Tag Assistant and network traffic.
- Treat consent configuration as privacy-sensitive and obtain the appropriate legal/product decision outside this skill.

## Permissions and credentials

- OAuth is required. The helper reads a short-lived access token from `GOOGLE_TAG_MANAGER_ACCESS_TOKEN`, falling back to `GTM_ACCESS_TOKEN`.
- The resolved token is allowed only in the generated `Authorization` header. The helper rejects it if it appears in a path, query value, or request body and redacts it defensively from output metadata and transport errors.
- The helper byte-bounds local/live Discovery, successful responses, error responses, and cumulative pagination. Unexpected non-JSON success text is omitted behind a fixed untrusted-data marker.
- Never store access tokens, refresh tokens, OAuth client secrets, service-account keys, or authorization headers in the repository.
- A service account must be explicitly granted access inside GTM; Google Cloud IAM alone does not grant container access.
- Inventory user permissions before changing them and preserve at least one verified administrator path.

## Output contract

Return:

- account/container/workspace/version IDs and environment;
- current state, fingerprints, live-version baseline, and conflict status;
- redacted request preview and acceptable OAuth scopes, whose Discovery semantics are any-of;
- test/preview evidence and firing/non-firing cases;
- mutation response, compiler status, new version ID, and live-version verification;
- pagination/quota bounds, unresolved conflicts, privacy risks, and rollback version.

Never claim a container is safely published without API state plus runtime preview or deployment evidence.
