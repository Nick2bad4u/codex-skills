---
name: dependency-update-maintenance
description: Validates and optionally performs dependency updates without weakening quality gates. Use when handling Dependabot/Renovate/npm-check-updates changes, lockfile review, update-tool runs, or code/config/type/lint/build/test fallout.
---

# Dependency Update Maintenance

Use this skill for dependency-update work where the goal is to prove the repository still works after changed package versions, not just make the installation command finish.

## Scope Modes

- Validate existing update: stay read-only until the changed manifests, lockfiles, release notes, and failing commands show an actionable fix.
- Apply updates: run updater commands only when the user explicitly asks Codex to do the update or accepts that mode.
- Repair fallout: fix compatibility issues in code, tests, configs, types, workflows, or package metadata without downgrading the gate unless the dependency itself is defective.
- Review-only: report impact and required action first; do not edit files.

## Workflow

1. Inspect user-provided update context, git status, dependency manifests, lockfiles, package-manager config, CI workflows, engines, overrides/resolutions, peer dependencies, and local aggregate validation scripts.
2. Run `scripts/audit_dependency_update.py <repo>` for a read-only summary of committed and uncommitted dependency surfaces and likely validation commands. Treat a Git discovery error as an audit failure, not as proof that nothing changed. Consume `owners` and the `*_command_specs` entries (`cwd` plus `argv`) as authoritative data; do not execute legacy rendered strings through a shell.
3. Identify the package manager and update source: Dependabot/Renovate, manual lock refresh, npm-check-updates, package-manager update, action pin update, Python lock update, or ecosystem-specific tool.
4. Resolve every surviving candidate and owner directory against the resolved repository root before reading it or emitting its `cwd`; reject symlink, junction, or other reparse-point targets outside that root as executable context. Require `package.json` plus a supported `packageManager` declaration or current local lock/config for Node owners, and require `pyproject.toml` plus uv/Poetry config or lock evidence for those owners. Lock-only markers, bare Node manifests without manager evidence, deleted markers, rename sources, and external-link paths are historical inventory only. Under an existing Node owner, require a nested project to declare its own `packageManager` before treating it as an independent owner; then keep every independent project's commands directory-scoped.
5. If applying updates, prefer the owning directory's updater script. Otherwise, use the native package-manager command that matches its surviving, version-compatible lockfile. Retain a declared npm major: npm 12 and later require `package-lock.json` for `npm ci`, npm 11 and earlier may use `npm-shrinkwrap.json`, and an unknown major must produce an ambiguity warning instead of assuming shrinkwrap support. Do not mix mutually exclusive managers in one project directory.
6. Read release notes, changelogs, migration guides, peer range changes, engine changes, and deprecations for packages that cross major versions or touch build/test/lint/type systems.
7. Install from the lockfile after updates and run the narrowest relevant command that proves the changed surface.
8. Fix root causes: API migration, config option changes, stricter types, changed lint rules, missing peer deps, lockfile metadata drift, workflow input changes, or test fixture expectations.
9. Broaden validation after targeted fixes: tests, typecheck, lint, build, docs, package checks, security scans, and release verification when the repo has those gates.
10. Classify vulnerability findings by shipped or deployed runtime, development-only, and peer-only exposure. Require zero unresolved known vulnerabilities in the production graph. Triage development-only and consumer-supplied peer findings instead of treating a nonzero full-tree count as an automatic failure; malware, actionable high or critical findings, or credible production, build, CI, release, or artifact exposure still require remediation.
11. Preserve support contracts. Do not broaden peer ranges, loosen engines, add overrides, pin transitive packages, or suppress diagnostics without evidence and a reason.
12. Review the final diff for unrelated churn, generated-file scope, lockfile consistency, deleted or renamed dependency surfaces, and dependency changes the user did not mention.

## Reference

Use [dependency-update-validation.md](references/dependency-update-validation.md) for ecosystem-specific commands, risk triage, and update-mode guardrails.

## Validation

Prefer repo scripts over generic commands. For Node projects, install with each owning directory's surviving, manager-version-compatible lockfile command and preserve Yarn classic versus modern behavior. For Python projects, use the selected uv, Poetry, or requirements/pip owner and run configured Ruff, mypy, Pyright, pytest, compile, or package checks from that directory. For workflow/action updates, run `actionlint` or the repo's workflow lint. For libraries, add package/pack/API checks when public surface or peer ranges changed.

## Output

Finish with dependency surfaces changed, resolved current owners, update mode used, structured commands run, important version or migration findings, files changed, whether validation proves the update, and any remaining blocker or risk.
