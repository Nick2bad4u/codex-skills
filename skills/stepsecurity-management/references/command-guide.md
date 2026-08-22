# StepSecurity Command Guide

## Contents

- [Environment](#environment)
- [Context](#context)
- [OpenAPI discovery](#openapi-discovery)
- [Read requests](#read-requests)
- [Mutation previews](#mutation-previews)
- [Raw endpoint escape hatch](#raw-endpoint-escape-hatch)
- [MCP workflow](#mcp-workflow)
- [Terraform workflow](#terraform-workflow)
- [Troubleshooting](#troubleshooting)

## Environment

PowerShell:

```powershell
$env:STEP_SECURITY_API_KEY = '<organization-or-fine-grained-key>'
$env:STEP_SECURITY_CUSTOMER = 'Nick2bad4u'
```

Do not paste real values into a committed profile or script. Clear temporary values when finished:

```powershell
Remove-Item Env:STEP_SECURITY_API_KEY -ErrorAction SilentlyContinue
```

The helper accepts global context flags after the subcommand because each subcommand owns its arguments.

## Context

Inspect inferred context without revealing a key:

```powershell
python scripts/manage_stepsecurity.py context
python scripts/manage_stepsecurity.py context --org Nick2bad4u --customer Nick2bad4u
```

Use `--repo` when the current directory is not the intended repository:

```powershell
python scripts/manage_stepsecurity.py context --repo Nick2bad4u/example --org Nick2bad4u
```

The output reports whether a credential is present, never the credential value.

## OpenAPI Discovery

Download the current OpenAPI JSON from the authenticated StepSecurity dashboard API reference. Then list operations:

```powershell
python scripts/manage_stepsecurity.py operations --spec-file C:\Temp\stepsecurity-openapi.json
```

Filter by operation ID, summary, tag, or path:

```powershell
python scripts/manage_stepsecurity.py operations --spec-file C:\Temp\stepsecurity-openapi.json --match detection
python scripts/manage_stepsecurity.py operations --spec-file C:\Temp\stepsecurity-openapi.json --match suppression
```

Inspect output as JSON for scripting:

```powershell
python scripts/manage_stepsecurity.py operations --spec-file C:\Temp\stepsecurity-openapi.json --match incident | ConvertFrom-Json
```

## Read Requests

Use the exact operation ID reported by the downloaded specification:

```powershell
python scripts/manage_stepsecurity.py request --spec-file C:\Temp\stepsecurity-openapi.json --operation-id listDetections --org Nick2bad4u
```

Supply explicit path and query values:

```powershell
python scripts/manage_stepsecurity.py request --spec-file C:\Temp\stepsecurity-openapi.json --operation-id getWorkflowRunEvents --path runId=123456789 --query limit=100 --org Nick2bad4u
```

Follow `links.next` conservatively:

```powershell
python scripts/manage_stepsecurity.py request --spec-file C:\Temp\stepsecurity-openapi.json --operation-id listDetections --org Nick2bad4u --paginate --max-pages 20
```

Use `--dry-run` to inspect a GET request without sending it:

```powershell
python scripts/manage_stepsecurity.py request --spec-file C:\Temp\stepsecurity-openapi.json --operation-id listPolicies --org Nick2bad4u --dry-run
```

## Mutation Previews

Create the smallest possible JSON body in a temporary file. Do not put secrets in it.

```powershell
python scripts/manage_stepsecurity.py request --spec-file C:\Temp\stepsecurity-openapi.json --operation-id createSuppressionRule --body-file C:\Temp\suppression.json --org Nick2bad4u
```

Non-GET operations are previews unless `--execute` is present. Review:

- method and URL;
- tenant and repository scope;
- path and query parameters;
- redacted headers;
- exact request body;
- whether the operation creates, replaces, or deletes state.

After explicit authorization, execute the same operation:

```powershell
python scripts/manage_stepsecurity.py request --spec-file C:\Temp\stepsecurity-openapi.json --operation-id createSuppressionRule --body-file C:\Temp\suppression.json --org Nick2bad4u --execute
```

Re-read the created resource and capture its identifier. For a suppression, verify the intended detection is affected and unrelated detections remain visible.

## Raw Endpoint Escape Hatch

Prefer operation IDs. Use raw relative endpoints only when the downloaded specification does not describe a needed read:

```powershell
python scripts/manage_stepsecurity.py request --method GET --endpoint /detections --query organization=Nick2bad4u --dry-run
```

The endpoint must remain on `https://agent.api.stepsecurity.io/v1`. Absolute URLs, if used, must match that origin and base path exactly. Credential-like query names are rejected.

For a raw non-GET request, preview is still mandatory before `--execute`:

```powershell
python scripts/manage_stepsecurity.py request --method POST --endpoint /example --body '{"example":true}'
```

Raw endpoints receive less schema validation. State the exact source that established the endpoint and body contract.

## MCP Workflow

For the official remote MCP server:

1. Connect to `https://agent.api.stepsecurity.io/v1/mcp` using the supported OAuth flow.
2. Inspect the live tool list and schemas.
3. Establish organization, repository, run, and time-window scope.
4. Start with inventory or read tools.
5. Correlate detections with runtime events and checked-in workflow code.
6. Before any write-capable tool, show its exact arguments and obtain authorization.
7. Record returned resource IDs and verify the changed state with a read.

Do not assume tool names from an older transcript remain current.

## Terraform Workflow

Initialize and validate in the repository that owns the configuration:

```powershell
terraform init
terraform fmt -check -recursive
terraform validate
terraform plan -out stepsecurity.tfplan
terraform show stepsecurity.tfplan
```

Do not apply during analysis-only work. When explicitly authorized:

```powershell
terraform apply stepsecurity.tfplan
```

Re-plan afterward. A clean plan plus an API/MCP read is stronger verification than a successful exit code alone.

## Troubleshooting

### Missing key

Set `STEP_SECURITY_API_KEY`. The helper deliberately does not accept a key argument.

### Wrong organization or customer

Pass `--org`, `--customer`, and, when relevant, `--repo`. Do not assume the GitHub owner is the StepSecurity customer slug.

### Operation not found

Re-download the current organization-specific specification and run `operations --match <term>`. Product and plan availability can change the operation surface.

### Permission denied

Confirm key type, organization scope, and required permission. Do not solve a missing permission by switching automatically to a broader administrator key.

### Redirect rejected

The helper rejects cross-origin and out-of-base redirects. Inspect the response and current documentation instead of disabling the safeguard.

### Partial results

Use `--paginate`, raise `--max-pages` deliberately, and report the limit. Preserve the original filter and time window when comparing repeated queries.
