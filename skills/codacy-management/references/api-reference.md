# Codacy API and Platform Reference

## Contents

- [Source-of-truth order](#source-of-truth-order)
- [API versions and discovery](#api-versions-and-discovery)
- [Authentication and token scope](#authentication-and-token-scope)
- [Repository identity and providers](#repository-identity-and-providers)
- [Pagination and rate limits](#pagination-and-rate-limits)
- [High-value v3 operation families](#high-value-v3-operation-families)
- [Configuration precedence](#configuration-precedence)
- [Coverage](#coverage)
- [Security findings](#security-findings)
- [Gate policies and coding standards](#gate-policies-and-coding-standards)
- [Self-hosted](#self-hosted)
- [Mutation review rules](#mutation-review-rules)
- [Official sources](#official-sources)

## Source-of-truth order

Use these sources in order because Codacy's API and CLI are active products:

1. The installed `codacy <command> --help` output for current CLI syntax.
2. The target instance's live OpenAPI document for current endpoint paths, methods, parameters, and schemas.
3. Current official Codacy documentation for behavior, permissions, limits, and workflows.
4. The official `codacy/codacy-cloud-cli` source when token support or CLI orchestration is unclear.
5. This reference as a durable workflow summary, not a frozen endpoint contract.

Research snapshot: 2026-08-17. The live Cloud OpenAPI document identified itself as OpenAPI 3.0.1, Codacy API version 3.1.0. Older prose on the API overview still called the downloadable definition OpenAPI 2.0, so trust the live document over that stale label.

## API versions and discovery

Prefer API v3. Codacy documents it as the actively developed API.

- Cloud base URL: `https://api.codacy.com/api/v3`
- Cloud interactive documentation: `https://api.codacy.com/api/api-docs`
- Cloud OpenAPI document: `https://api.codacy.com/api/api-docs/swagger.yaml`
- Legacy v2 base: `https://api.codacy.com/`

Use v2 only when a required operation has no v3 equivalent or a maintained Codacy tool explicitly uses it. Do not mix v2 repository-token assumptions into v3 requests.

The bundled helper can inspect operation IDs without a YAML dependency:

```powershell
python "<path-to-skill>/scripts/manage_codacy.py" operations --search pull-request --json
```

For reproducibility, download the live definition separately and use `--spec-file`. Record its retrieval date or digest in audit output when exact endpoint behavior matters.

## Authentication and token scope

### Account API tokens

- Environment variable: `CODACY_API_TOKEN`.
- v3 header: `api-token: <value>`.
- Scope: the same organizations, repositories, and operations as the token owner's Codacy roles.
- Recommended for: v3 API calls, organization-wide queries, security findings, policy management, and supported Cloud CLI operations.
- Durable automation: use a dedicated service account so a person's departure or role change does not silently break automation.

### Repository API tokens

- Environment variable used by maintained tools: `CODACY_PROJECT_TOKEN`.
- Header on supporting endpoints: `project-token: <value>`.
- Scope: one repository.
- Recommended for: CI uploads and the limited official CLI/Analysis CLI operations that explicitly support repository tokens.
- Limit: Codacy currently allows up to 100 tokens per repository.

The official Cloud CLI currently gives repository tokens precedence over account tokens:

1. explicit `--repository-token`;
2. `CODACY_PROJECT_TOKEN`;
3. `CODACY_API_TOKEN`;
4. encrypted credentials from `codacy login`.

Avoid the explicit flag in agent-visible commands because it places a secret in process arguments. If `CODACY_PROJECT_TOKEN` is set ambiently but the desired command requires an account token, unset it for that process rather than assuming the account token will win.

The official CLI supports repository tokens for a limited set that includes repository inspection/reanalysis, issue listing, and tools/patterns. Account tokens are required for account and organization inventory, security findings, pull requests, issue state changes, repository add/remove/follow operations, and other organization-wide management. Re-run current `--help` and honor a CLI refusal instead of attempting a weaker raw fallback.

### Public data

Codacy documents unauthenticated `GET` access for public repositories. Require explicit `--allow-unauthenticated` in the helper so a missing secret does not silently change the authority model.

## Repository identity and providers

API provider values can include:

- `gh`: GitHub Cloud
- `ghe`: GitHub Enterprise
- `gl`: GitLab Cloud
- `gle`: GitLab Enterprise
- `bb`: Bitbucket Cloud
- `bbe`: Bitbucket Enterprise or Server

The official Cloud CLI documents automatic origin detection for the cloud providers `gh`, `gl`, and `bb`. The helper infers only the well-known public hosts. Pass `--provider`, `--organization`, and `--repository` for enterprise or nonstandard remotes rather than trusting a hostname guess.

URL-encode every path segment independently. Do not encode the entire endpoint path as one value.

## Pagination and rate limits

V3 list/search operations commonly return:

```json
{
 "data": [],
 "pagination": {
  "cursor": "next-page-cursor",
  "limit": 100,
  "total": 156
 }
}
```

- Pass the returned cursor as the next request's `cursor` query parameter.
- Stop only when `pagination.cursor` is absent.
- Default limit: 100.
- Maximum limit: 1000.
- Detect a repeated cursor and enforce a maximum-page boundary.

Codacy Cloud documents 2500 requests per five minutes per source IP. It may return HTTP 503 or 504 when rate-limited. Add delay between large request sequences, retry conservatively, and avoid parallel page storms. The documented Cloud limit does not apply to Self-hosted.

## High-value v3 operation families

Resolve these by `operationId` against the live specification before use. Representative operations observed in the 2026-08-17 Cloud definition include:

| Goal                               | Representative operation ID                   | Method |
| ---------------------------------- | --------------------------------------------- | ------ |
| Repository analysis summary        | `getRepositoryWithAnalysis`                   | GET    |
| Repository tools                   | `listRepositoryTools`                         | GET    |
| Configure a tool                   | `configureTool`                               | PATCH  |
| Repository tool patterns           | `listRepositoryToolPatterns`                  | GET    |
| Update tool patterns               | `updateRepositoryToolPatterns`                | PATCH  |
| Search current issues              | `searchRepositoryIssues`                      | POST   |
| Issue overview counts              | `issuesOverview`                              | POST   |
| Inspect one issue                  | `getIssue`                                    | GET    |
| Update issue state                 | `updateIssueState`                            | PATCH  |
| Repository pull requests           | `listRepositoryPullRequests`                  | GET    |
| Pull-request analysis              | `getRepositoryPullRequest`                    | GET    |
| Pull-request coverage reports      | `getPullRequestCoverageReports`               | GET    |
| Repository quality settings        | `getRepositoryQualitySettings`                | GET    |
| Coverage report status             | `listCoverageReports`                         | GET    |
| Organization security items        | `listSecurityItems`                           | GET    |
| Search security items              | `searchSecurityItems`                         | POST   |
| Ignore or unignore a security item | `ignoreSecurityItem` / `unignoreSecurityItem` | POST   |
| Coding standards                   | `listCodingStandards`                         | GET    |
| Gate policies                      | `listGatePolicies`                            | GET    |
| Organization audit log             | `listAuditLogsForOrganization`                | GET    |

POST does not always mean mutation: search and overview operations use POST bodies. The helper still previews every non-GET request by default because method alone cannot prove intent. Add `--send` after reviewing the resolved URL and redacted body.

## Configuration precedence

### Repository configuration file

Codacy recognizes `.codacy.yml` or `.codacy.yaml` at the repository root. It can control global, duplication, complexity, and tool-specific exclusions; include paths; analysis base directories; tool settings; and language enablement/extensions.

Important precedence:

- When this file exists, UI ignored-file settings do not apply. Move the intended ignores into the file.
- Codacy normally uses the default-branch configuration.
- Pull-request additions are considered, but existing default-branch configuration takes precedence in conflicts until the change is merged.
- Coverage-only exclusions belong in the coverage generator/report, not in `.codacy.yml`.

Validate locally with the current Analysis CLI command shown by `codacy-analysis-cli --help`. Official documentation currently shows:

```powershell
codacy-analysis-cli validate-configuration --directory "."
```

### Analysis CLI configuration

`.codacy/codacy.config.json` configures local Analysis CLI tools and patterns. Committing it does not update Codacy Cloud. `codacy tools --import` is the explicit Cloud mutation that imports compatible settings.

`tools --import --force` can unlink coding standards before import. Treat `--force` as a broad policy mutation, inspect linked standards first, and require explicit authorization.

## Coverage

Prefer Codacy Coverage Reporter or a maintained Codacy CI integration. Generate a complete supported report for each analyzed commit, including unchanged tested source files.

For pull-request coverage deltas, Codacy needs coverage for at least:

- the pull-request head commit;
- the common ancestor of the pull-request and target branches.

Use `getPullRequestCoverageReports` or the Cloud CLI's pull-request view to distinguish missing, pending, and processed reports. A successful upload command is not proof that Codacy associated and processed the report for the expected commit.

Repository tokens are usually the least-privilege choice for one-repository coverage jobs. Account-token uploads require provider, organization, and repository identity variables. Keep every token in CI secrets.

## Security findings

Codacy security findings are organization-level risk records and can represent SAST, secrets, SCA, CI/CD, infrastructure as code, DAST, penetration testing, license, and cloud posture surfaces.

Prioritize critical/high, overdue/due-soon, exploitable or reachable runtime paths, valid exposed secrets, and direct fixable dependencies. For SCA affected functions:

1. Determine whether the dependency is direct, transitive, or unresolved from the real manifest and lockfile.
2. Trace the complete dependency chain and the package that can be upgraded.
3. Search for direct calls, imports, re-exports, wrappers, reflection, plugin loading, framework callbacks, and generated entry points.
4. Prefer an upgrade or source/configuration fix.
5. Use `NotExploitable` only when the evidence supports non-reachability; record that evidence in the ignore comment.

Secret remediation normally requires revocation/rotation and history/exposure review before alert-state cleanup.

## Gate policies and coding standards

Gate policies apply shared quality gates across repositories. Only one can be the organization default, and changes apply on the next analysis. The built-in Codacy Gate Policy cannot be edited or deleted. Removing or deleting a custom gate policy restores the repositories' prior quality gates.

Coding standards apply shared tool and pattern configurations. Multiple standards can apply to a repository. A standard-enforced pattern cannot be overridden by repository-level pattern commands; update the organization standard or explicitly unlink it after reviewing the policy impact.

Do not weaken gates or standards to make a current analysis green. Determine whether the failure is code, test, coverage, analysis configuration, or an intentionally changed policy requirement.

## Self-hosted

Use the target instance's domain:

- v3 base: `https://<instance>/api/v3`
- OpenAPI: `https://<instance>/api/api-docs/swagger.yaml`

Do not assume Cloud endpoints, fields, or feature availability match an older Self-hosted version. Read the instance-specific live specification. The bundled helper refuses HTTP because token-bearing plaintext requests are unsafe.

## Mutation review rules

Before any write:

1. Resolve the exact operation and current schema from the live specification.
2. Read the current object and controlling source.
3. Record organization, repository, branch/PR, issue/finding/policy IDs, and filters.
4. Preview the helper request without `--send`, or show the equivalent official CLI read command and planned mutation.
5. Redact token-like response fields and never request secret values for display.
6. Apply the smallest authorized change.
7. Read the object again and, when analysis is required, wait for a fresh completed analysis.

Avoid generic raw calls for billing, token creation, destructive repository/organization deletion, SSH-key regeneration, integration replacement, DAST execution, and policy deletion when a maintained UI or CLI provides a safer workflow.

## Official sources

- [Using the Codacy API](https://docs.codacy.com/codacy-api/using-the-codacy-api/)
- [API tokens](https://docs.codacy.com/codacy-api/api-tokens/)
- [Live Codacy v3 OpenAPI](https://api.codacy.com/api/api-docs/swagger.yaml)
- [Codacy Cloud CLI](https://docs.codacy.com/codacy-cloud-cli/)
- [Official Cloud CLI source](https://github.com/codacy/codacy-cloud-cli)
- [Official Codacy skills](https://github.com/codacy/codacy-skills)
- [Codacy configuration file](https://docs.codacy.com/repositories-configure/codacy-configuration-file/)
- [Adding coverage](https://docs.codacy.com/coverage-reporter/)
- [Using gate policies](https://docs.codacy.com/organizations/using-gate-policies/)
- [Using coding standards](https://docs.codacy.com/organizations/using-coding-standards/)
- [Managing security and risk](https://docs.codacy.com/organizations/managing-security-and-risk/)
