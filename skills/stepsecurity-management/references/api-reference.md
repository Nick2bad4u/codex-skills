# StepSecurity API, MCP, and Terraform Reference

## Contents

- [Service surfaces](#service-surfaces)
- [Authentication](#authentication)
- [REST API](#rest-api)
- [Remote MCP server](#remote-mcp-server)
- [Terraform provider](#terraform-provider)
- [GitHub Actions integration](#github-actions-integration)
- [Pagination and retries](#pagination-and-retries)
- [Safety boundaries](#safety-boundaries)
- [Official sources](#official-sources)

## Service Surfaces

StepSecurity exposes complementary management surfaces:

| Surface                       | Best use                                             | Mutation boundary                                                     |
| ----------------------------- | ---------------------------------------------------- | --------------------------------------------------------------------- |
| Actions dashboard             | Visual posture and run investigation                 | UI controls can change external state                                 |
| Remote MCP server             | Interactive investigation and cross-resource queries | Default OAuth connection is read-oriented; inspect every exposed tool |
| REST API                      | Reproducible inventory and targeted operations       | Non-GET calls can change organization state                           |
| Terraform provider            | Durable reviewed configuration                       | `terraform apply` changes external state                              |
| Secure Repo / Secure Workflow | Proposed GitHub hardening changes                    | Creating or merging a PR changes GitHub state                         |
| `harden-runner`               | Runtime monitoring and egress enforcement            | Workflow edits and policy changes affect job behavior                 |

Do not assume all product features are available to every plan or credential type. Inspect the authenticated organization's current API reference and permissions.

## Authentication

The production REST and MCP base is:

```text
https://agent.api.stepsecurity.io/v1
```

StepSecurity documents these credential paths:

- organization API keys for organization-scoped automation;
- fine-grained API keys when a narrower permission set is sufficient;
- short-lived personal access tokens for interactive use;
- GitHub OIDC for supported GitHub Actions automation;
- OAuth for the hosted remote MCP connection.

For local REST and Terraform use, place the credential in:

```text
STEP_SECURITY_API_KEY
```

The Terraform provider also uses:

```text
STEP_SECURITY_CUSTOMER
```

Never pass the key in a query parameter, command-line argument, committed `.tfvars`, workflow log, or generated report. Prefer a narrowly scoped key and rotate it after suspected disclosure.

## REST API

Use the organization-specific OpenAPI document downloaded from the API reference in the authenticated dashboard. The helper intentionally has no guessed live specification URL:

```powershell
python scripts/manage_stepsecurity.py operations --spec-file C:\Temp\stepsecurity-openapi.json
```

List matching operations:

```powershell
python scripts/manage_stepsecurity.py operations --spec-file C:\Temp\stepsecurity-openapi.json --match policy
```

Inspect a safe request plan before execution:

```powershell
python scripts/manage_stepsecurity.py request --spec-file C:\Temp\stepsecurity-openapi.json --operation-id listDetections --org Nick2bad4u --dry-run
```

The helper supports:

- OpenAPI 3 path, query, and request-body metadata;
- operation-ID or raw relative-endpoint requests;
- `{organization}`, `{org}`, `{owner}`, `{customer}`, and `{tenant}` inference from explicit context;
- repeated `--path name=value`, `--query name=value`, and `--header name=value` inputs;
- inline JSON or `--body-file` request bodies;
- preview-only non-GET operations unless `--execute` is passed;
- no mutation redirects and a separate five-hop, cycle-checked, same-origin `/v1` redirect budget for reads;
- bounded success and error bodies, finite JSON with at most 64 container levels, and redacted depth-safe output;
- complete preservation of every accepted non-JSON or malformed-JSON body, without a hidden character-level truncation;
- bounded `links.next` pagination for JSON:API-like responses when requested.

The helper is a transport safety layer. The downloaded specification and organization permissions remain authoritative.

## Remote MCP Server

The hosted MCP endpoint is:

```text
https://agent.api.stepsecurity.io/v1/mcp
```

The official OAuth connection is the preferred interactive setup. StepSecurity documents read-oriented access by default. The exact tools can evolve, so inspect the connected server's live tool list instead of freezing tool names into automation.

The documented MCP capabilities cover areas such as:

- Actions runtime detections and event timelines;
- workflow-run process, file, DNS, and network activity;
- Actions security posture and action provenance;
- policies and suppression rules;
- incidents and investigation context;
- repositories, workflows, actions, and organization scope.

For a headless API-key connection, StepSecurity documents passing the customer context to the MCP endpoint. Keep the key in `STEP_SECURITY_API_KEY`; do not embed it in checked-in MCP configuration. OAuth is preferable for user-driven connections.

MCP is not a reason to skip mutation review. Before invoking a write-capable tool, inspect its input schema, obtain explicit authorization, and capture the resulting resource identifier.

## Terraform Provider

The official provider source is:

```hcl
terraform {
  required_providers {
    stepsecurity = {
      source = "step-security/stepsecurity"
    }
  }
}
```

Use environment variables for credentials and organization/customer context. Pin a reviewed provider version according to the repository's dependency policy; do not copy a latest-version number from prose without checking the registry.

Safe workflow:

1. Read current configuration through the API, MCP, or provider data sources when available.
2. Express only the intended durable resources in Terraform.
3. Run formatting and validation.
4. Inspect the complete `terraform plan` for replacement, deletion, and broadening effects.
5. Apply only after explicit authorization.
6. Re-read the resource and verify a representative workflow or detection behavior.

Never import or apply an entire organization opportunistically during an unrelated triage task.

## GitHub Actions Integration

StepSecurity's GitHub integration includes posture analysis, Secure Repo, Secure Workflow, and `step-security/harden-runner`.

Treat generated pull requests as untrusted proposals until reviewed. In particular, verify:

- action commit pins and repository pinning policy;
- top-level and job-level GitHub token permissions;
- OIDC permissions and cloud trust conditions;
- secrets exposure and fork behavior;
- outbound endpoint allowlists or block mode;
- artifact and cache behavior;
- self-hosted runner compatibility;
- reusable workflow and composite-action boundaries;
- placement of `harden-runner` before untrusted execution.

An observed endpoint is not automatically safe. Establish which action or process owns it and whether the destination is required.

## Pagination and Retries

Do not assume one response is complete. Follow documented cursors or `links.next` values until exhausted, while retaining the original same-origin and base-path restrictions. The helper detects repeated validated next URLs and limits pagination to 1,000 pages and 32 MiB cumulatively; each success body is limited to 8 MiB and each error body to 16 KiB. Accepted text bodies are preserved in full, so pagination `complete` never hides a second, character-level evidence truncation.

Every executed response bundle reports `complete`, `pageCount`, `maxPages`, and a fully validated `nextLink`. Natural exhaustion means `links.next` is absent or explicitly `null`; it sets `complete` to `true` and `nextLink` to `null`. Empty, scalar, list, or malformed next-link metadata fails with an explicit incomplete-page count. Reaching `--max-pages`, or choosing not to follow an available next link, sets `complete` to `false`; treat those pages as a partial inventory. A repeated next link is also an error with an explicit incomplete-page count.

For transient `429`, `502`, `503`, and `504` responses:

- honor `Retry-After` when present;
- otherwise use bounded exponential backoff;
- retry only GET automatically;
- never replay a mutation automatically.

After any attempted non-read request fails—including a redirect, HTTP error, timeout, connection reset, other operating-system transport error, incomplete success/error-body read, excessive valid-JSON nesting, or response-close failure—the helper reports an indeterminate outcome. POST, PUT, PATCH, and DELETE each remain exactly one request. Verify the exact resource or StepSecurity audit log before a manual retry; a local failure is not proof that the remote mutation was not applied. Open, body-read, and close-failure details are bounded and stripped of the configured authorization value, and expected failures become concise CLI errors without tracebacks.

The helper attempts closure for every acquired success and HTTP-error response path. Closure cannot be guaranteed when `close()` itself raises; that failure is surfaced through the same bounded transport boundary. Request, response, redaction, and command-output JSON are validated iteratively for finite numbers, cycles, supported JSON types, and explicit nesting limits before recursive library serialization. Validation, programmer errors, `KeyboardInterrupt`, and `SystemExit` are not misclassified as transport failures.

`--retries` is capped at 10, and timeout values must be positive and finite. Redirects do not consume or expand the retry budget.

Report partial pagination, permission errors, and unavailable telemetry explicitly.

## Safety Boundaries

The following always require explicit authorization:

- creating, changing, or deleting a policy;
- creating, broadening, or deleting a suppression rule;
- resolving, closing, or otherwise changing incident state;
- creating a Secure Repo or Secure Workflow pull request;
- applying Terraform;
- changing organization integrations, members, keys, or billing;
- changing `harden-runner` enforcement in a repository.

Use a narrow resource identifier and preserve before/after evidence. Avoid bulk operations unless the user explicitly requested and reviewed the exact scope.

## Official Sources

- StepSecurity documentation index: <https://docs.stepsecurity.io/llms.txt>
- Organization API access: <https://docs.stepsecurity.io/workspace/settings/stepsecurity-api-org-access>
- StepSecurity MCP server: <https://docs.stepsecurity.io/administration/admin-console/integrations/stepsecurity-mcp-server>
- Terraform provider: <https://registry.terraform.io/providers/step-security/stepsecurity/latest/docs>
- Harden-Runner: <https://github.com/step-security/harden-runner>
