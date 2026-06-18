---
name: ci-release-readiness
description: Debug CI failures and validate release readiness. Use when Codex needs to inspect GitHub Actions runs, fix failed checks, validate dependency updates, run release gates, prepare a repository for release, or execute a full release-readiness loop without publishing unless explicitly requested.
---

# CI Release Readiness

Use this skill for GitHub Actions failures, release checks, dependency-update fallout, package validation, and release-candidate cleanup.

## CI Failure Workflow

1. Identify the branch, PR, commit, failed workflow, failed job, annotations, and logs.
2. Read the failing step output before changing files.
3. Compare the remote command with local scripts, lockfiles, environment assumptions, and workflow inputs.
4. Fix the root cause in code, tests, config, scripts, dependencies, or workflow files.
5. Do not skip checks, weaken gates, or rerun blindly unless evidence shows an external transient failure.
6. Run the closest local reproduction or validation. Rerun the remote job only when tooling is available and appropriate.

## Release Readiness Workflow

1. Determine the repository's real release gate from scripts, docs, workflows, and package metadata.
2. Prefer aggregate commands such as `release:verify`, `release:check`, `ci`, package validation, docs build, and publish dry run when they exist.
3. For dependency updates, verify manifests, lockfiles, workspace metadata, overrides, peers, engines, package manager metadata, generated outputs, and CI workflows agree.
4. Fix every actionable lint, type, test, build, docs, generated-output, package, or release-script failure at the root cause.
5. If the package is published, check whether the target/current version already exists before declaring it release-ready.
6. Rerun the full relevant gate after fixes.

## Boundaries

- Do not publish, tag, or bump versions unless the user explicitly asks.
- Do not weaken rules, delete tests, pin around an update, or add suppressions without a specific defensible reason.
- If a blocker is external, credential-related, network-related, or pre-existing, isolate it clearly and keep going with the closest local validation.

## Output

Finish with root cause or readiness verdict, changed files, exact commands run, remote rerun status if relevant, and remaining blockers.
