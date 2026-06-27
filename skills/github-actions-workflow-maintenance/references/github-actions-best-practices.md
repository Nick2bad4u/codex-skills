# GitHub Actions Best Practices

Use this reference when creating or heavily revising workflows. Prefer current GitHub and action-specific docs for exact syntax, inputs, and permissions.

## Workflow Shape

- Keep each workflow focused on one durable responsibility: CI, security scan, dependency automation, release, publish, docs deploy, or scheduled maintenance.
- Use `pull_request` for untrusted PR validation and avoid privileged execution of PR code.
- Use `workflow_dispatch` for manual release or maintenance workflows with typed inputs.
- Use `workflow_call` for reusable workflows. Declare typed inputs, required secrets, permissions expectations, and outputs.
- Add `concurrency` for deploys, releases, scheduled jobs, and expensive branch workflows.
- Set top-level `permissions: contents: read`, then add job-level writes only where required.

## Jobs And Steps

- Prefer repo scripts over long YAML command blocks.
- Split jobs when they need different permissions, runners, dependencies, or retry behavior.
- Use `needs` only for real ordering constraints.
- Keep matrix jobs bounded and name matrix dimensions for the behavior being tested.
- Add `timeout-minutes` for jobs that can hang.
- Upload artifacts when another job needs the exact output or when debugging requires test reports, coverage, screenshots, logs, or package tarballs.

## Supply Chain And Security

- Follow local action-pinning policy. For high-security repos, pin third-party actions to full commit SHA and verify the SHA belongs to the upstream repository.
- Avoid mutable refs such as `main` or `latest` for third-party actions.
- Treat action source, composite actions, Docker actions, workflow commands, issue text, PR text, branch names, labels, and artifact contents as untrusted input.
- Avoid `pull_request_target` unless the workflow never checks out or executes attacker-controlled code.
- Prefer OIDC or registry trusted publishing over long-lived secrets when supported.
- Keep secrets scoped to the job or environment that needs them and do not dump contexts to logs.

## Node And npm Repos

- Use the repository's Node version source of truth, such as `.node-version`, `.nvmrc`, `package.json#engines`, or workflow policy.
- Use lockfile-respecting installs, such as `npm ci`, unless the repo has a documented reason not to.
- Prefer `actions/setup-node` package-manager cache support before custom `actions/cache` blocks.
- For npm publishing, verify package contents with the repo's release gate and `npm pack --dry-run` when package surface changed.
- Use trusted publishing or provenance when the package and registry setup support it.

## Failure Triage

1. Identify the exact branch, commit, workflow, job, step, annotation, and failing command.
2. Read the failing log before editing.
3. Compare the failing remote command with local scripts and environment assumptions.
4. Fix the root cause, not the symptom. Do not weaken checks or delete gates to make CI green.
5. Run the closest local reproduction, then the broader workflow or release gate.
6. Rerun remote checks only after a fix or when evidence shows a transient platform failure.

## Validation

Prefer repo-local checks:

```powershell
npm run lint:actions
actionlint
npm run validate
npm run release:verify
```

When action syntax or input names are uncertain, inspect the action's current metadata or official docs before encoding the workflow.
