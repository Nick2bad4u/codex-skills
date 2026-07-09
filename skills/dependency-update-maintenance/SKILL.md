---
name: dependency-update-maintenance
description: Validates and optionally performs dependency updates without weakening quality gates. Use when handling Dependabot/Renovate/npm-check-updates changes, lockfile review, update-tool runs, or code/config/type/lint/build/test fallout.
---

# Dependency Update Maintenance

Use this skill for dependency-update work where the goal is to prove the repository still works after changed package versions, not just make the install command finish.

## Scope Modes

- Validate existing update: stay read-only until the changed manifests, lockfiles, release notes, and failing commands show an actionable fix.
- Apply updates: run updater commands only when the user explicitly asks Codex to do the update or accepts that mode.
- Repair fallout: fix compatibility issues in code, tests, configs, types, workflows, or package metadata without downgrading the gate unless the dependency itself is defective.
- Review-only: report impact and required action first; do not edit files.

## Workflow

1. Inspect user-provided update context, git status, dependency manifests, lockfiles, package-manager config, CI workflows, engines, overrides/resolutions, peer dependencies, and local aggregate validation scripts.
2. Run `scripts/audit_dependency_update.py <repo>` for a read-only summary of changed dependency surfaces and likely validation commands.
3. Identify the package manager and update source: Dependabot/Renovate, manual lock refresh, npm-check-updates, package-manager update, action pin update, Python lock update, or ecosystem-specific tool.
4. If applying updates, prefer the repository's updater script. Otherwise, use the native package-manager command that matches the lockfile. Do not mix package managers.
5. Read release notes, changelogs, migration guides, peer range changes, engine changes, and deprecations for packages that cross major versions or touch build/test/lint/type systems.
6. Install from the lockfile after updates and run the narrowest relevant command that proves the changed surface.
7. Fix root causes: API migration, config option changes, stricter types, changed lint rules, missing peer deps, lockfile metadata drift, workflow input changes, or test fixture expectations.
8. Broaden validation after targeted fixes: tests, typecheck, lint, build, docs, package checks, security scans, and release verification when the repo has those gates.
9. Preserve support contracts. Do not broaden peer ranges, loosen engines, add overrides, pin transitive packages, or suppress diagnostics without evidence and a reason.
10. Review the final diff for unrelated churn, generated-file scope, lockfile consistency, and dependency changes the user did not mention.

## Reference

Use [dependency-update-validation.md](references/dependency-update-validation.md) for ecosystem-specific commands, risk triage, and update-mode guardrails.

## Validation

Prefer repo scripts over generic commands. For Node repos, install with the repo's lockfile command and run available scripts such as `release:verify`, `validate`, `check`, `test`, `typecheck`, `lint`, `build`, and `format:check`. For Python repos, run the configured Ruff, mypy, Pyright, pytest, compile, or package checks. For workflow/action updates, run `actionlint` or the repo's workflow lint. For libraries, add package/pack/API checks when public surface or peer ranges changed.

## Output

Finish with dependency surfaces changed, update mode used, important version or migration findings, files changed, commands run, whether validation proves the update, and any remaining blocker or risk.
