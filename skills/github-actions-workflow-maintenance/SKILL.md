---
name: github-actions-workflow-maintenance
description: Create, review, edit, and harden GitHub Actions workflows. Use when Codex works on .github/workflows YAML, reusable workflows, workflow_call callers, CI/CD automation, action pinning, GITHUB_TOKEN permissions, npm publishing workflows, caching, matrix jobs, actionlint findings, or GitHub Actions review comments.
---

# GitHub Actions Workflow Maintenance

Use this skill to create, review, repair, or harden GitHub Actions workflows without turning workflow YAML into a generic CI/CD wish list. Start from the repository's actual commands, local policy, and existing workflow style.

## First Pass

1. Inspect `.github/workflows/`, nested `AGENTS.md` files, commit-message instructions, package metadata, lockfiles, tool versions, release scripts, and local validation scripts before editing.
2. Identify the workflow's job: CI, security scan, dependency maintenance, release, publish, docs deploy, labels/issues, scheduled maintenance, reusable workflow provider, or reusable workflow caller.
3. Preserve local policy. Examples: full-SHA pinning, owned shared workflow calls at `@main`, required comments beside pinned actions, forced package installs, custom shared configs, or release gates.
4. Check current docs or action metadata when exact syntax, inputs, permissions, or action versions matter. Do not guess action inputs from memory.
5. If reviewing a large workflow set, read `references/review-checklist.md` and use it as the audit frame.
6. If creating or heavily revising workflows, read `references/github-actions-best-practices.md` for the compact best-practices checklist.

## Create Or Edit Workflows

1. Use one workflow per durable responsibility. Split only when triggers, permissions, ownership, or failure recovery differ.
2. Choose triggers intentionally:
   - Use `pull_request` for untrusted PR validation.
   - Use `push` for branch or tag workflows.
   - Use `workflow_dispatch` for manual release or maintenance flows.
   - Use `schedule` only for work that remains useful without a code change.
   - Use `workflow_call` for reusable workflows; define typed inputs, explicit secrets, and documented outputs.
3. Set top-level `permissions: contents: read` unless the workflow cannot work with read-only repository access. Add narrower job-level writes where needed.
4. Add `concurrency` for deployments, releases, expensive branch CI, and scheduled maintenance. Use a group that includes workflow name plus branch, tag, environment, or package as appropriate.
5. Keep jobs cohesive: install, lint, typecheck, test, build, package, scan, publish, and deploy should be separate when they have different dependencies, permissions, runners, or retry semantics.
6. Prefer repository scripts such as `npm run release:verify`, `npm run lint:actions`, `npm test`, `pytest`, or `make ci` over duplicating long command sequences in YAML.
7. Use package-manager-native caches first. For Node projects, prefer `actions/setup-node` cache support when it fits; use `actions/cache` only for custom outputs or unsupported package managers.
8. Upload artifacts when downstream jobs need the exact built output, test report, coverage report, package tarball, or deployable bundle. Set `retention-days` when artifacts are large or sensitive.

## Security Rules

1. Treat workflow files as privileged code. Check for secret exposure, overbroad permissions, untrusted checkout, command injection, mutable third-party refs, and privileged triggers before style cleanup.
2. Avoid `pull_request_target` and `workflow_run` for untrusted code. If a privileged workflow is required, do not check out or execute attacker-controlled PR content in that job.
3. Pin third-party actions to full commit SHAs when repo policy requires maximum supply-chain hardening. Verify the SHA belongs to the upstream action repository. Tags are acceptable only when local policy allows that risk.
4. Prefer OIDC or trusted publishing over long-lived cloud or registry tokens when the target service supports it. For npm publishing, check current npm trusted publishing/provenance docs before changing authentication.
5. Use environment protection for production deploys and package publishing when approvals, scoped secrets, or branch restrictions are needed.
6. Never echo secrets, serialize entire contexts that contain sensitive fields, or pass secrets to untrusted commands. Mask non-secret sensitive values before logging them.
7. For agentic or issue/comment-driven workflows, treat issue bodies, PR text, labels, comments, branch names, and artifact contents as untrusted inputs. Do not feed them into shell commands, prompts, or write-capable agents without validation and permission boundaries.

## Reusable Workflows

1. Put reusable workflows directly under `.github/workflows/` and define `on.workflow_call`.
2. For called workflows, declare every input with a type, every required secret, and every output mapped from a job output.
3. For caller workflows, call reusable workflows at the job level with `jobs.<job_id>.uses`; do not mix `runs-on` or `steps` into a reusable workflow caller job.
4. Keep caller files thin. The caller should provide trigger, permissions, inputs, secrets, and repository-specific policy only.
5. If the reusable workflow is in an owner-controlled shared repository, follow the user's policy for refs. Do not replace `@main` with SHA pins when the user relies on live shared-template updates.

## Review Workflow

1. Parse the YAML mentally as GitHub will: triggers, permissions, defaults, concurrency, jobs, strategy, needs, environment, outputs, services, steps, and expressions.
2. List high-impact findings first: workflows that do not trigger, publish/deploy when they should not, expose secrets, use unsafe privileged triggers, grant broad write permissions, skip release gates, or cannot pass validation.
3. Check action inputs against the action's current metadata when an input is new, renamed, or suspicious.
4. Check shell snippets for quoting, error handling, OS portability, and untrusted expression interpolation. Prefer passing expressions through `env` and quoting shell variables.
5. Compare workflow commands to local scripts. If CI and local commands differ, determine whether the difference is intentional.
6. Confirm required artifacts, job outputs, caches, matrix values, path filters, and branch/tag filters are wired to the actual repo layout.

## Validation

1. Run the closest local workflow validation first: `npm run lint:actions`, `actionlint`, YAML lint, repo validation, or the repository's aggregate release/CI check.
2. Run touched package or language gates when workflow edits depend on scripts being present or producing expected artifacts.
3. For remote failures, inspect logs and annotations before rerunning. Rerun only after a fix or when evidence supports a transient service failure.
4. If a local tool cannot run, explain the missing binary, credentials, network condition, or platform mismatch, then run the next closest non-mutating validation.

## Output

For review-only requests, return findings first with file/line, impact, evidence, recommended fix, and validation. For edit requests, finish with files changed, policy choices preserved, commands run, and any remote follow-up needed.
