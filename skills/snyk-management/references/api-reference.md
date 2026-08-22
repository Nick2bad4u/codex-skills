# Snyk API Reference

## Contents

- [Official Sources](#official-sources)
- [Regions And Authentication](#regions-and-authentication)
- [REST Versioning And JSON API](#rest-versioning-and-json-api)
- [Pagination And Rate Limits](#pagination-and-rate-limits)
- [Core Surfaces](#core-surfaces)
- [Mutations And Asynchronous Work](#mutations-and-asynchronous-work)
- [CLI Boundaries](#cli-boundaries)

## Official Sources

- Snyk API docs: <https://docs.snyk.io/developer-tools/snyk-api>
- REST API behavior: <https://docs.snyk.io/developer-tools/snyk-api/rest-api/about-the-rest-api>
- API authentication: <https://docs.snyk.io/developer-tools/snyk-api/authentication-for-api>
- REST reference/OpenAPI UI: <https://apidocs.snyk.io/>
- Live OpenAPI versions: <https://api.snyk.io/rest/openapi>
- CLI command summary: <https://docs.snyk.io/developer-tools/snyk-cli/snyk-cli/cli-commands-and-options-summary>
- Official CLI repository: <https://github.com/snyk/cli>
- API changelog and lifecycle: <https://docs.snyk.io/developer-tools/snyk-api/changelog>

Use the live OpenAPI document for the selected date when resolving paths, operation IDs, schemas, stability, and permissions. The helper defaults to the durable version `2024-10-15`, which Snyk recommends unless an endpoint needs a different version; override intentionally and record it.

## Regions And Authentication

REST base URLs:

| Region       | REST base                     |
| ------------ | ----------------------------- |
| `SNYK-US-01` | `https://api.snyk.io/rest`    |
| `SNYK-US-02` | `https://api.us.snyk.io/rest` |
| `SNYK-EU-01` | `https://api.eu.snyk.io/rest` |
| `SNYK-AU-01` | `https://api.au.snyk.io/rest` |

Tokens are region-specific. Configure the CLI with `snyk config environment <ENVIRONMENT_NAME>` before `snyk auth` for a non-default region.

Personal and service-account API tokens use `Authorization: token <token>`. Snyk App access tokens use `Authorization: bearer <access_token>`. Do not substitute the bearer scheme for an ordinary personal token.

Enterprise automation should use a service account for continuity and least privilege. Personal tokens are appropriate for local CLI work and one-off investigation. Snyk documents personal REST API access as Enterprise-only; CLI access has different plan boundaries.

## REST Versioning And JSON API

The REST API follows JSON:API with documented caveats and OpenAPI 3.0.3. Requests containing data must use `Content-Type: application/vnd.api+json`; the helper also sends `Accept: application/vnd.api+json`.

Every REST request requires `version=YYYY-MM-DD` or an older stability suffix where supported. Versions from 2024-10-15 onward use a date contract; the current day's date resolves to the most recent compatible API, but reproducible automation should pin a reviewed date. Earlier contracts can use `~beta` or `~experimental`.

GA endpoints have the strongest support promise. Beta and experimental endpoints can change more quickly. Inspect `Sunset` headers and the changelog before relying on old contracts. Do not silently migrate an endpoint version during a state-changing run.

Snyk also has a legacy v1 API. Prefer REST when the operation has migrated. Do not mechanically translate v1 IDs or response shapes; consult the endpoint-specific migration guide, especially for issue IDs and project listings.

## Pagination And Rate Limits

REST list endpoints use cursor pagination. Follow the response's `links.next` URL until it is null or absent. The link contains opaque `starting_after` and other parameters. Do not decode, edit, or combine the cursor with a new sort. The helper validates every next link against the configured region and `/rest` base before following it.

Snyk documents 1,620 requests per minute per API key. Handle HTTP `429`, honor `Retry-After` when present, and retry with bounded backoff. New protective limits may be introduced without being considered an API breaking change.

Sorting can make pagination inconsistent when new records are inserted. Prefer default insertion order when a complete stable inventory matters.

## Core Surfaces

### Identity, Groups, And Organizations

Use `self`, groups, organizations, memberships, roles, and service-account operations to establish scope. Group-level credentials and operations span multiple organizations and require a broader review.

Membership and service-account creation/update/deletion affect access. Secret rotation operations may return a secret once; never capture it in helper output or chat.

### Projects, Targets, Collections, And Assets

Projects represent scanned/monitored configurations. Targets group projects around a source such as a repository. Collections are curated project groupings. Inventory assets and relationships can span projects and targets.

List and inspect before changing attributes. Project or target deletion can remove monitoring history or every project beneath a target. A local repository name is not a project ID.

### Issues, Findings, Policies, And Ignores

Organization and group issue endpoints provide cross-product findings. Package issue endpoints accept PURLs. Test findings belong to asynchronous test jobs. Preserve surface-specific IDs and severity/state vocabularies.

Snyk Open Source ignores stored in `.snyk` are version-controlled local policy. Consistent Ignores for Snyk Code use separate API/CLI surfaces and may require approval workflows. Review reachability, exploitability, fix paths, expiration, ignore type, and the affected asset before ignoring.

Organization/group policy changes can alter every covered project. Prefer code fixes and narrow project configuration. Require explicit scope before creating, updating, or deleting policies.

### Tests, Monitoring, SBOM, And Exports

`snyk test` is local/read-only with respect to the Snyk service unless a command option explicitly reports results. `snyk monitor` uploads a snapshot and changes the project inventory.

REST test and SBOM-test creation return jobs. Poll the job/status endpoint and fetch findings/results only after a terminal successful status. Export endpoints likewise create jobs that must be checked.

Project SBOM export and local `snyk sbom` have different inputs and visibility. Preserve the requested CycloneDX/SPDX version and do not commit a sensitive SBOM without review.

### Settings, Audit Logs, And Integrations

REST settings cover SAST, Secrets, IaC, Open Source, languages, brokers, registries, Slack, and more. Inspect the current object and organization inheritance before PATCH/POST/DELETE. Group settings may override organization intent.

Audit-log search is the evidence surface for who changed Snyk state. Use explicit time windows and cursor pagination. Integration, broker, app, and credential changes can expose source or registry access and need heightened review.

## Mutations And Asynchronous Work

Preview exact IDs, bodies, and permissions for:

- project/target/collection create, update, or delete;
- policy and ignore operations;
- test, import, export, monitoring, and SBOM jobs;
- organization/group settings;
- memberships, invitations, roles, service accounts, or secrets;
- integrations, brokers, registries, notifications, and apps;
- cloud environment or scan operations.

The helper refuses non-GET execution without `--send`. A preview proves only request construction. After sending, re-read the resource or poll its documented job. Do not claim completion from `202 Accepted` or a queued state.

## CLI Boundaries

Use the CLI for local evidence across Open Source, Code, Secrets, Container, IaC, SBOM, and AI-BOM surfaces. Validate flags with the installed CLI because feature availability and command options change frequently.

`snyk monitor`, `--report`, `ignore`, authentication/config changes, and some IaC commands mutate local or remote state. `snyk test` exit codes distinguish findings from operational failure; do not erase that distinction by parsing only human text. Prefer JSON or SARIF output and keep sensitive artifacts outside the checkout unless the user requests them.
