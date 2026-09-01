# Codacy Command Guide

## Contents

- [Setup and authentication](#setup-and-authentication)
- [Repository identity](#repository-identity)
- [Account and repository inventory](#account-and-repository-inventory)
- [Files and metrics](#files-and-metrics)
- [Issues](#issues)
- [Security findings](#security-findings)
- [Pull requests](#pull-requests)
- [Tools and patterns](#tools-and-patterns)
- [Reanalysis](#reanalysis)
- [Coverage](#coverage)
- [Bundled API helper](#bundled-api-helper)
- [Mutation checklist](#mutation-checklist)
- [Troubleshooting](#troubleshooting)

## Setup and authentication

Inspect the current package and CLI before installation:

```powershell
npm view @codacy/codacy-cloud-cli version dist-tags --json
codacy --version
codacy --help
```

Install globally only when the user wants it available outside the current run:

```powershell
npm install --global @codacy/codacy-cloud-cli@<reviewed-version>
```

For a one-off reviewed invocation:

```powershell
npx --yes --package @codacy/codacy-cloud-cli@<reviewed-version> codacy --help
```

Prefer environment-variable authentication in agent and CI sessions:

```powershell
$env:CODACY_API_TOKEN = Get-Secret CODACY_API_TOKEN -AsPlainText
codacy info --output json
```

Interactive `codacy login` stores an account token encrypted in the user's Codacy credentials store. Do not automate interactive token entry or inspect the credentials file. Use `codacy logout` only when the user asks to remove the stored credential.

For a supported repository-scoped CI operation:

```powershell
$env:CODACY_PROJECT_TOKEN = Get-Secret CODACY_PROJECT_TOKEN -AsPlainText
codacy repository --output json
```

If both variables exist, `CODACY_PROJECT_TOKEN` currently wins in the official CLI. Unset it for a command that deliberately requires account scope:

```powershell
Remove-Item Env:CODACY_PROJECT_TOKEN -ErrorAction SilentlyContinue
codacy findings gh <organization> --output json
```

## Repository identity

Inside a standard GitHub, GitLab, or Bitbucket Cloud checkout, omit provider, organization, and repository so the CLI reads `origin`:

```powershell
codacy repository --output json
codacy issues --output json
```

Use explicit identity outside a checkout or when auto-detection is ambiguous:

```powershell
codacy repository gh <organization> <repository> --output json
```

Run the helper's local-only context command before a raw API call:

```powershell
python "<path-to-skill>/scripts/manage_codacy.py" context --repo "." --json
```

## Account and repository inventory

```powershell
codacy info --output json
codacy repositories gh <organization> --output json
codacy repositories gh <organization> --search <name> --output json
codacy repository --output json
```

Repository mutations execute immediately after CLI confirmation or option parsing. Inspect first:

```powershell
codacy repository --output json
codacy repository --add
codacy repository --follow
codacy repository --unfollow
codacy repository --remove
```

Treat `--remove` as destructive Codacy state deletion. Confirm the provider/organization/repository and whether history/settings can be recovered before executing it.

## Files and metrics

```powershell
codacy ls --output json
codacy ls --path src --sort issues --direction desc --output json
codacy ls --path src --search config --output json
codacy directories --plus-children --sort coverage --direction asc --output json
```

Correlate poor file metrics with current issue data and local source. Do not delete or ignore generated files based on metrics alone.

## Issues

List active issues:

```powershell
codacy issues --output json
codacy issues --branch main --severities Critical,High --output json
codacy issues --categories Security,ErrorProne --output json
codacy issues --tools eslint,semgrep --output json
codacy issues --false-positives --output json
codacy issues --overview --output json
```

Inspect ignored issues and one issue:

```powershell
codacy issues --ignored --severities Critical --output json
codacy issue <issue-id> --output json
```

The CLI accepts issue severities `Critical`, `High`, `Medium`, and `Minor`, with API aliases `Error`, `High`, `Warning`, and `Info`.

After reviewing source and rule semantics:

```powershell
codacy issue <issue-id> --ignore --ignore-reason FalsePositive --ignore-comment "Rule does not match the parsed runtime behavior."
codacy issue <issue-id> --unignore
```

Bulk ignore uses the current filters. Print and save the matching JSON set first, confirm every target and the reason, then run the same filters with `--ignore`. Avoid `--skip-confirmation` in interactive agent work.

Supported ignore reasons currently include `AcceptedUse`, `FalsePositive`, `NotExploitable`, `TestCode`, and `ExternalCode`.

## Security findings

Organization-wide:

```powershell
codacy findings gh <organization> --severities Critical,High --output json
codacy findings gh <organization> --statuses Overdue,DueSoon --output json
codacy findings gh <organization> --scan-types SAST,Secrets,SCA,IaC --output json
```

Repository-scoped:

```powershell
codacy findings --severities Critical,High --output json
```

Inspect and mutate one finding:

```powershell
codacy finding gh <organization> <finding-id> --output json
codacy finding gh <organization> <finding-id> --ignore --ignore-reason NotExploitable --ignore-comment "Reviewed dependency chain and affected-function reachability."
codacy finding gh <organization> <finding-id> --unignore
```

Security finding status filters currently include `Overdue`, `OnTrack`, `DueSoon`, `ClosedOnTime`, `ClosedLate`, and `Ignored`. Scan types currently include `SAST`, `Secrets`, `SCA`, `CICD`, `IaC`, `DAST`, `PenTesting`, `License`, and `CSPM`. Re-run `codacy findings --help` before relying on this list.

## Pull requests

```powershell
codacy pull-requests --state open --output json
codacy pull-requests --search "fix flaky" --base main --output json
codacy pull-request 42 --output json
codacy pull-request 42 --diff
codacy pull-request 42 --issue <issue-id> --output json
```

After inspecting the issue and local diff:

```powershell
codacy pull-request 42 --ignore-issue <issue-id> --ignore-reason FalsePositive --ignore-comment "Verified against the changed code."
codacy pull-request 42 --unignore-issue <issue-id>
```

`--ignore-all-false-positives` is a broad mutation. Export the PR analysis and inspect every candidate first.

## Tools and patterns

```powershell
codacy tools --output json
codacy tool eslint --enable
codacy tool eslint --disable
codacy tool eslint --configuration-file true
codacy patterns eslint --output json
codacy patterns eslint --enabled --categories Security --output json
codacy patterns eslint --search no-unused-vars --output json
codacy pattern eslint <pattern-id> --output json
codacy pattern eslint <pattern-id> --parameter max=120
```

Before a tool or pattern mutation, determine whether:

- the tool uses a repository configuration file;
- a coding standard enforces the state or parameters;
- the pattern ID belongs to the intended tool;
- the next analysis can be safely triggered;
- changing a parameter is more correct than disabling the pattern.

Bulk `--enable-all` and `--disable-all` operate on every matching pattern. Export the filtered pattern set first.

Import local Analysis CLI configuration only after diffing it against Cloud settings:

```powershell
codacy tools --import .codacy/codacy.config.json
```

Avoid `--force` unless the user explicitly authorizes unlinking coding standards.

## Reanalysis

Prefer waiting for the new analysis and delta:

```powershell
codacy repository --reanalyze-and-wait --output json
codacy pull-request 42 --reanalyze-and-wait --output json
```

Use fire-and-forget only when the user does not need completion in this turn:

```powershell
codacy repository --reanalyze
codacy pull-request 42 --reanalyze
```

Do not repeatedly trigger reanalysis while one is running. Poll the repository or PR state.

## Coverage

Inspect repository and PR analysis first:

```powershell
codacy repository --output json
codacy pull-request 42 --output json
```

Use the API helper for detailed coverage status not exposed by the installed CLI:

```powershell
python "<path-to-skill>/scripts/manage_codacy.py" request --repo "." --operation-id listCoverageReports --json
python "<path-to-skill>/scripts/manage_codacy.py" request --repo "." --operation-id getPullRequestCoverageReports --path pullRequestNumber=42 --json
```

For setup, follow the current official Coverage Reporter documentation. Never pipe a downloaded installer into a shell without reviewing the current official URL, version/pinning options, and CI trust boundary.

## Bundled API helper

### Discover operations

```powershell
python "<path-to-skill>/scripts/manage_codacy.py" operations --search repository --json
python "<path-to-skill>/scripts/manage_codacy.py" operations --search gate --method GET --json
python "<path-to-skill>/scripts/manage_codacy.py" operations --search audit --json
```

For a saved OpenAPI document:

```powershell
python "<path-to-skill>/scripts/manage_codacy.py" operations --spec-file .cache/codacy-openapi.yaml --search security --json
```

### Read by operation ID

```powershell
python "<path-to-skill>/scripts/manage_codacy.py" request --repo "." --operation-id getRepositoryWithAnalysis --json
python "<path-to-skill>/scripts/manage_codacy.py" request --repo "." --operation-id listRepositoryTools --json
python "<path-to-skill>/scripts/manage_codacy.py" request --repo "." --operation-id getRepositoryQualitySettings --json
python "<path-to-skill>/scripts/manage_codacy.py" request --repo "." --operation-id listAuditLogsForOrganization --query limit=100 --paginate --json
```

Path parameters not available from the Git remote must be supplied separately:

```powershell
python "<path-to-skill>/scripts/manage_codacy.py" request --repo "." --operation-id getIssue --path issueId=12345 --json
```

### POST search

The first command previews because it is non-GET; the second sends it:

```powershell
python "<path-to-skill>/scripts/manage_codacy.py" request --repo "." --operation-id searchRepositoryIssues --body-json '{"levels":["Error","Warning"],"categories":["Security"]}' --paginate --json
python "<path-to-skill>/scripts/manage_codacy.py" request --repo "." --operation-id searchRepositoryIssues --body-json '{"levels":["Error","Warning"],"categories":["Security"]}' --paginate --send --json
```

Automatic retries apply only to GET requests. A POST search is logically read-only in this example, but the helper's current OpenAPI metadata cannot prove that property, so every non-GET request is single-attempt even when `--retries` is nonzero. A non-GET HTTP 408, 429, or any 5xx response is potentially indeterminate, as is a transport, bounded-read, decode, redaction, serialization, or output failure after send. In each case, inspect current Codacy state before deciding whether to send a new request.

The helper's safety limits are part of its command contract:

- The loaded account token appears only in the `api-token` header. Plain, form-encoded, percent-encoded, or repeatedly encoded reuse in an operation ID, URL authority/hostname, final path/query, or recursive body scalar is rejected before lookup or preview and again before authenticated transport.
- Preview and result URLs, including URL strings nested in JSON, redact the active token and credential-like query values such as unknown tokens, keys, or signatures. Reconstructed URLs are rescanned and fail closed; sensitive structured JSON keys are also redacted.
- JSON is strict: request bodies, structured errors, API responses, redaction trees, and output reject `NaN`, `Infinity`, and `-Infinity` and allow at most 64 container levels.
- `--timeout` must be finite, greater than 0, and at most 300 seconds; `--retry-delay` must be finite and between 0 and 60 seconds; `--retries` is from 0 through 10; and `--max-pages` is from 1 through 500.
- `Retry-After` accepts only ASCII decimal delay-seconds or a timezone-aware HTTP date. Delays cap at 60 seconds; past dates become zero delay; fractional, scientific, negative, non-ASCII, malformed, and timezone-less values use bounded exponential fallback.
- OpenAPI downloads are limited to 16 MiB, individual API responses to 8 MiB, cumulative pagination to 32 MiB, and captured HTTP error bodies to 16 KiB. Missing or dishonest `Content-Length` headers do not bypass these limits.

Prefer `--body-file` for a complex reviewed body so shell quoting cannot change it:

```powershell
python "<path-to-skill>/scripts/manage_codacy.py" request --repo "." --operation-id searchSecurityItems --body-file .cache/security-search.json --paginate --send --json
```

### Raw endpoint

```powershell
python "<path-to-skill>/scripts/manage_codacy.py" request --repo "." "/analysis/organizations/{provider}/{remoteOrganizationName}/repositories/{repositoryName}/quality-settings" --json
```

For Self-hosted, pass both API and spec identity when the derived path is not correct. The host may be custom, but it must be present, IPv6 literals must be bracketed, any explicit port must be from 1 through 65535, and implicit HTTPS is same-origin with explicit port 443. The HTTPS API base path must normalize exactly and case-sensitively to `/api/v3`:

```powershell
python "<path-to-skill>/scripts/manage_codacy.py" operations --base-url "https://codacy.example.com/api/v3" --spec-url "https://codacy.example.com/api/api-docs/swagger.yaml" --search repository --json
```

## Mutation checklist

Before executing a mutation:

- Confirm provider, organization, repository, branch/PR, and object IDs.
- Export the current object and controlling policy/configuration.
- Inspect source or dependency evidence.
- Use a narrow reason and comment.
- Preview raw API requests without `--send`.
- Avoid broad flags unless every target was reviewed.
- Execute once.
- Read back the state.
- Wait for a new analysis when required.

## Troubleshooting

### Unauthorized or not found

- Check which token variable won; do not print its value.
- Confirm account versus repository-token support.
- Confirm Codacy role and Git-provider membership.
- Confirm provider, organization, and repository case/spelling.
- For Self-hosted, use the instance-specific base URL and live specification.

### Empty or incomplete lists

- An absent `pagination` object or absent cursor completes pagination. If present, `pagination` must be an object and its cursor must be a nonblank string without surrounding whitespace; malformed metadata fails closed.
- Check `pagination.total` and whether a cursor remains. A cursor on the configured final page fails as incomplete, and `fetchedPages` always reports the actual number of fetched responses.
- Raise `--limit` only up to 1000.
- Raise `--max-pages` only up to the helper cap of 500.
- Verify branch, status, severity, category, tool, and ignored filters.
- Distinguish unavailable sections under repository-token scope from zero results.
- If a response or cumulative pagination result reaches the helper's byte safety limit, narrow the filters or page size instead of bypassing the limit.

### Tool or pattern change has no effect

- Wait for or trigger a fresh analysis.
- Check local configuration-file mode.
- Check organization coding-standard enforcement.
- Check whether `.codacy.yml` controls the relevant file/path behavior.

### Missing pull-request coverage

- Verify a complete report was generated and uploaded for the PR head.
- Verify coverage exists for the common ancestor.
- Confirm commit SHA/provider/repository identity in the upload job.
- Inspect Codacy coverage report status rather than assuming upload success means processing success.
