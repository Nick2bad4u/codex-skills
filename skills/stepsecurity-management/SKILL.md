---
name: stepsecurity-management
description: Audit and manage StepSecurity Actions posture, runtime detections, incidents, policies, suppressions, and hardening through MCP, REST, Terraform, and reviewed pull requests. Use whenever the user mentions StepSecurity, Harden-Runner, Actions runtime security, or StepSecurity findings.
---

# StepSecurity Management

Use StepSecurity as four connected surfaces rather than treating its dashboard as the source of truth:

1. Prefer the official remote MCP server for interactive, read-heavy investigation.
2. Use `scripts/manage_stepsecurity.py` for reproducible REST inspection and narrowly scoped API calls.
3. Use the official Terraform provider for durable organization configuration.
4. Use Secure Repo or Secure Workflow only when the user authorizes repository-changing pull requests.

Read [references/api-reference.md](references/api-reference.md) for authentication, endpoint, MCP, and Terraform behavior. Read [references/command-guide.md](references/command-guide.md) before making a write or proposing a repository change.

## Operating Rules

- Default to read-only inventory and triage.
- Treat creating policies, suppression rules, or incidents and changing their state as external mutations.
- Treat Secure Repo and Secure Workflow output as proposed code changes. Inspect the complete patch, workflow permissions, action pins, and runner behavior before asking to create a pull request.
- Do not suppress a detection merely to make a dashboard green. Establish the event, process, network destination, workflow, action, runner, and recurrence first.
- Keep tenant scope explicit. Resolve the GitHub organization or StepSecurity customer before querying or changing state.
- Never put API keys in commands, query strings, committed files, workflow logs, or chat output.
- Prefer fine-grained organization keys, short-lived personal access tokens, or GitHub OIDC over broad long-lived credentials.
- Use `STEP_SECURITY_API_KEY` for local API or Terraform authentication. `STEPSECURITY_API_KEY` is accepted by the helper only as a compatibility fallback.
- Preserve evidence before resolving an incident, dismissing a finding, or adding a suppression.
- Require a user-approved reason, scope, and expiry/review plan for every suppression.
- Prefer a policy or suppression as code when it is intended to be durable.

## Establish Context

Start with:

```powershell
python skills/stepsecurity-management/scripts/manage_stepsecurity.py context
python skills/stepsecurity-management/scripts/manage_stepsecurity.py context --org Nick2bad4u --customer Nick2bad4u
```

The helper can infer a GitHub owner from the current repository. Confirm that the inferred owner is the intended StepSecurity organization; repository owners, GitHub organizations, and StepSecurity customer slugs are related but not always identical.

For REST operations, download the organization-specific OpenAPI document from the API reference in the authenticated StepSecurity dashboard and keep it outside the repository unless the user explicitly wants it versioned. StepSecurity documents the download flow; do not invent or depend on an undocumented public specification URL.

## Choose the Interface

Use MCP when it is connected and the task is interactive investigation, such as:

- listing or explaining Actions runtime detections;
- correlating a workflow run with process, file, DNS, or network activity;
- inspecting Actions security posture, policies, suppression rules, or incidents;
- investigating an action, workflow, repository, or organization across related queries.

Use the REST helper when the result must be reproducible, MCP is unavailable, or the exact response needs to be saved or piped to another local tool:

```powershell
python skills/stepsecurity-management/scripts/manage_stepsecurity.py operations --spec-file C:\Temp\stepsecurity-openapi.json --match detection
python skills/stepsecurity-management/scripts/manage_stepsecurity.py request --spec-file C:\Temp\stepsecurity-openapi.json --operation-id listDetections --org Nick2bad4u
```

Use Terraform for reviewed, durable configuration. Inspect the plan, restrict the key to the intended organization, and never apply without explicit authorization.

Use the web application when a visual event timeline or authenticated Secure Repo/Secure Workflow preview materially helps. Do not create a pull request, change a policy, or suppress a finding just because the UI offers a one-click action.

## Triage Workflow

For a detection, incident, or suspicious workflow run:

1. Record the organization, repository, workflow path, run ID, job, runner, event time, and detection identifier.
2. Retrieve the full runtime evidence: processes, command lines, file writes, DNS requests, network destinations, and action provenance.
3. Compare the activity with the checked-in workflow and action versions at the run commit.
4. Determine whether the behavior is expected, compromised, overprivileged, or merely unfamiliar.
5. Check recurrence across runs, repositories, and actions before scoping a response.
6. Prefer remediation: pin or replace an action, reduce permissions, add egress controls, or harden the runner.
7. If suppression is justified, make it as narrow as the platform permits, include a reason, and set a review or expiry expectation.
8. Re-query the affected run or posture after remediation and retain before/after evidence.

Do not infer compromise solely from a severity label. Conversely, do not dismiss an unexpected outbound request merely because the job succeeded.

## REST Safety Pattern

List and inspect before mutation:

```powershell
python skills/stepsecurity-management/scripts/manage_stepsecurity.py request --spec-file C:\Temp\stepsecurity-openapi.json --operation-id getIncident --path incidentId=INCIDENT_ID --org Nick2bad4u
```

Preview non-GET operations by default:

```powershell
python skills/stepsecurity-management/scripts/manage_stepsecurity.py request --spec-file C:\Temp\stepsecurity-openapi.json --operation-id createSuppressionRule --org Nick2bad4u --body-file .\suppression.json
```

Execute only after the preview is reviewed and the user authorizes that exact mutation:

```powershell
python skills/stepsecurity-management/scripts/manage_stepsecurity.py request --spec-file C:\Temp\stepsecurity-openapi.json --operation-id createSuppressionRule --org Nick2bad4u --body-file .\suppression.json --execute
```

The helper constrains requests to `https://agent.api.stepsecurity.io/v1`, blocks credential-like query parameters, rejects every redirect for mutations, and follows only a small, cycle-checked set of same-origin `/v1` redirects for reads. Success/error bodies, transport diagnostics, cumulative pagination bytes, and JSON nesting are bounded and redacted. Bounded non-JSON or malformed-JSON bodies are preserved in full. Transport failures while opening, reading, or closing either kind of response become concise CLI errors. Closure is attempted for every acquired response path; a failed close is reported safely rather than claimed as closed. Every failed attempted mutation—including an incomplete body read, excessive JSON nesting, or close failure—is single-shot and reported as indeterminate; re-read the exact resource or audit log before retrying. Only GET can retry. Pagination output reports `complete`, `pageCount`, `maxPages`, and the validated `nextLink`; malformed next-link metadata fails incomplete, and a result is never a complete security inventory when `complete` is false. The helper validates OpenAPI path/query/body inputs and redacts sensitive output, but it does not decide whether a suppression or policy change is appropriate.

## Actions Hardening

When StepSecurity proposes a hardening change:

- inspect every changed workflow, not only the summary;
- keep action references pinned consistently with repository policy;
- verify `permissions`, secrets, OIDC, network access, artifacts, caches, and reusable-workflow boundaries;
- ensure `harden-runner` placement and configuration cover the intended jobs;
- preserve self-hosted runner requirements and legitimate endpoints;
- run local workflow validation and repository tests when available;
- verify the StepSecurity posture and a representative workflow run after merge.

Creating the PR is a mutation and needs explicit authorization. Merging it is a separate mutation.

## Completion Standard

Report:

- organization/customer, repositories, runs, and time window inspected;
- interface used: MCP, API, Terraform, or authenticated UI;
- detections/incidents/posture findings and supporting evidence;
- mutations performed, including exact policy or suppression scope;
- repository changes or pull requests created;
- verification performed after each change;
- unresolved ambiguity, missing permissions, pagination limits, or unavailable telemetry.
