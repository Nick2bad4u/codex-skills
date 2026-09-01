# Dependency Update Validation

## Contents

- [Update Mode](#update-mode)
- [Discovery and Ownership](#discovery-and-ownership)
- [Command Output Contract](#command-output-contract)
- [Risk Triage](#risk-triage)
- [Ecosystem Commands](#ecosystem-commands)
- [Fix Patterns](#fix-patterns)
- [Review Checklist](#review-checklist)

## Update Mode

- Default to validating existing changes. Only run mutating update commands when the user asks for AI-driven updates or approves that mode.
- Prefer repo scripts such as `update-all`, `update-deps`, `deps:update`, `renovate`, or `sync:*` when present.
- Keep one package manager per project directory. Independent nested projects may use different managers, but their commands must be directory-scoped.
- Preserve lockfile ownership: commit lockfile changes with manifest changes unless the repo intentionally ignores locks.
- Treat generated dependency updates as untrusted until local validation confirms install, test, lint, type, and build behavior.

## Discovery and Ownership

- Use NUL-delimited Git porcelain and name-status output. Preserve both status columns, literal spaces and quotes in names, deletions, and both sides of renames or copies across committed, staged, unstaged, mixed, and untracked changes. Use harder copy detection for committed and staged diffs.
- Surface Git execution and parsing errors. An unavailable Git executable, non-worktree directory, or failed status/diff command is not equivalent to zero changed files.
- Accept Git-validated SHA-1 and SHA-256 commit IDs. Reject malformed successful `rev-parse` output. Prefer a trusted remote base, fall back to `HEAD^`, and compare an initial commit against Git's empty-tree semantics instead of skipping it.
- Require every explicit `--changed-file` value to normalize to a repository-relative file path. Reject absolute paths, traversal, empty normalized values, and control characters.
- Treat arbitrary Git path bytes as data. JSON output must remain valid UTF-8 and byte-round-trippable through surrogate escapes; text output must escape surrogate code points instead of writing invalid Unicode.
- Resolve each surviving candidate, file read, and owner directory against the resolved repository root. If a symlink, junction, or other reparse point resolves outside it, retain the changed path as historical evidence but emit no owner or command from it. For a deleted path, apply the same check to its nearest surviving ancestor.
- Require `package.json` for every npm, pnpm, Yarn, or Bun owner. A supported `packageManager` declaration counts as explicit manager configuration and is authoritative; without it, pair `package.json` with a current local lock/config marker and use marker precedence. A bare package manifest or lock/config-only directory is inventory, not an owner. A nested Node directory under an existing Node owner must declare its own `packageManager` before it crosses that owner boundary; this conservative rule prevents workspace-member locks from becoming conflicting standalone owners without requiring package-manager-specific workspace glob interpretation.
- Resolve Python ownership independently: uv and Poetry require a current `pyproject.toml` plus their current config/lock evidence; requirements files select pip-style ownership when neither uv nor Poetry owns the directory. Lock/config-only Node, uv, and Poetry markers are orphan historical evidence and warnings, not executable owners.
- A stale competing marker may justify a warning, but must not produce install or update commands from multiple mutually exclusive managers in the same directory.
- Include deleted dependency surfaces and both rename paths in review, but never resolve an executable owner from a deleted marker, deleted directory, or rename source. Frozen install commands require the appropriate surviving lock.
- Build manifest/lock consistency warnings from the selected owner's currently surviving files only. Keep deleted, renamed-away, and competing-manager markers in historical inventory instead of letting them satisfy or trigger current-owner checks.

## Command Output Contract

- `owners` is the structured list of current executable contexts. Each entry contains `cwd`, `manager`, an optional manager `variant` such as Yarn `classic` or `modern`, and `version_major` when an npm `packageManager` major can be parsed without guessing.
- `install_command_specs`, `validation_command_specs`, and `update_command_specs` are authoritative. Each entry contains a repository-relative `cwd` and an `argv` array intended for direct process execution without a shell.
- `package_managers` is a legacy compatibility inventory of current and historical dependency markers. It may include deleted, renamed, stale, or competing managers and must not be used to choose commands.
- `install_commands`, `validation_commands`, and `update_commands` are compatibility-only renderings for the shell named by `legacy_command_shell`, currently PowerShell 7. Their quoting is PowerShell-specific and does not imply cross-shell safety.
- Keep update specs empty unless `--include-update-commands` is explicitly supplied. Even then, review the structured `cwd` and `argv` before execution.

## Risk Triage

- Major version changes, pre-1.0 minor changes, engine bumps, peer dependency changes, build tool upgrades, type package upgrades, lint/config package upgrades, test runner upgrades, and GitHub Action updates need deeper review.
- Transitive-only lock updates still need install and at least smoke validation when they affect runtime, build, native, security, or package-manager metadata.
- Type-only package changes can still break strict typechecks.
- Lint, formatter, and static-analysis package updates can create new valid findings; fix code/config rather than disabling rules.
- Security updates should prove the vulnerable package is actually upgraded in the lockfile and no override keeps the vulnerable version reachable in the affected dependency graph.
- Require zero unresolved known vulnerabilities in dependencies that ship with or execute in production. Include bundled and production optional dependencies.
- Do not make a nonzero development-only or consumer-supplied peer count an automatic failure. Triage severity, reachability, exploit conditions, fix availability, untrusted-input handling, CI or release secret access, and generated or published artifact impact.
- Block malware, actionable high or critical findings, and credible production, install, build, CI, release, or artifact exposure. Document accepted residual findings with their package path, scope, rationale, and remediation status.
- For applications, include peers and optional packages that execute in production. For libraries, preserve supported peer contracts unless evidence shows the package exposes vulnerable peer behavior; do not narrow a peer range merely to silence an audit.
- For owned sibling packages, prefer fixing the owned package's public types or metadata over downstream casts or suppressions.

## Ecosystem Commands

- npm 12+: [`npm ci` requires `package-lock.json`](https://docs.npmjs.com/cli/v12/commands/npm-ci/). Treat `npm-shrinkwrap.json` as obsolete historical evidence, warn to migrate it, and never let it satisfy npm 12 install or manifest/lock checks.
- npm 11 and earlier: [`npm ci` may use `package-lock.json` or `npm-shrinkwrap.json`](https://docs.npmjs.com/cli/v11/commands/npm-ci/). If the npm major is unknown and shrinkwrap exists, report ambiguity and require `package-lock.json` before suggesting `npm ci`. Run `npm update` only in approved update mode.
- pnpm: prefer `pnpm install --frozen-lockfile` for validation; use `pnpm update` only in approved update mode.
- Yarn classic: use `yarn install --frozen-lockfile`; use `yarn upgrade --latest` only in approved update mode.
- Yarn 2+: use `yarn install --immutable`; use `yarn upgrade-interactive` only in approved update mode so the project itself supplies the selector UI.
- Bun: prefer `bun install --frozen-lockfile`; use `bun update` only in approved update mode.
- Python/uv: from the owning directory, prefer `uv sync --frozen` or the repo's venv/bootstrap script; use `uv lock --upgrade` only in approved update mode.
- Python/Poetry: from the owning directory, prefer `poetry sync`; use `poetry update` only in approved update mode.
- Python/requirements: from the owning directory, install the selected requirements file with `python -m pip install -r <file>`; use `--upgrade` only in approved update mode.
- Go: run `go mod tidy` only when module files intentionally changed; validate with `go test ./...`.
- Rust: validate with `cargo test`; use `cargo update` only in approved update mode.
- GitHub Actions: check action metadata/current docs when inputs or major versions changed; validate with `actionlint` where available.

## Fix Patterns

- API migration: update call sites to the new public API and add tests around changed behavior.
- Config migration: rename removed options, split config files, or update schema references according to the dependency's migration guide.
- Type fallout: use typed adapters, narrower generics, or upstream-owned public type fixes before local casts.
- Peer dependency fallout: install or range-adjust peers only when the support contract and package manager resolution require it.
- Engine fallout: align CI/runtime versions before accepting dependency versions that require a newer Node/Python/etc.
- Lockfile conflict: regenerate with the same package manager and version used by the repo/CI; do not hand-edit locks except for documented lockfile formats.

## Review Checklist

- Confirm every changed manifest/lockfile belongs to the intended update.
- Compare changed direct dependency ranges to the installed lockfile versions.
- Check package scripts, CI workflows, engines, package-manager fields, overrides/resolutions, peerDependencies, and published files.
- Read release notes for high-risk packages and cite the migration point in the final answer when it drove code changes.
- Run one narrow failing command after each fix, then the aggregate gate.
- State skipped commands and why: missing credentials, unsupported platform, network issue, command too expensive, or user requested review-only.
