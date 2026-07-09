# Dependency Update Validation

## Contents

- [Update Mode](#update-mode)
- [Risk Triage](#risk-triage)
- [Ecosystem Commands](#ecosystem-commands)
- [Fix Patterns](#fix-patterns)
- [Review Checklist](#review-checklist)

## Update Mode

- Default to validating existing changes. Only run mutating update commands when the user asks for AI-driven updates or approves that mode.
- Prefer repo scripts such as `update-all`, `update-deps`, `deps:update`, `renovate`, or `sync:*` when present.
- Keep one package manager per repo. A package-lock update does not justify adding pnpm, yarn, or bun metadata.
- Preserve lockfile ownership: commit lockfile changes with manifest changes unless the repo intentionally ignores locks.
- Treat generated dependency updates as untrusted until local validation confirms install, test, lint, type, and build behavior.

## Risk Triage

- Major version changes, pre-1.0 minor changes, engine bumps, peer dependency changes, build tool upgrades, type package upgrades, lint/config package upgrades, test runner upgrades, and GitHub Action updates need deeper review.
- Transitive-only lock updates still need install and at least smoke validation when they affect runtime, build, native, security, or package-manager metadata.
- Type-only package changes can still break strict typechecks.
- Lint, formatter, and static-analysis package updates can create new valid findings; fix code/config rather than disabling rules.
- Security updates should prove the vulnerable package is actually upgraded in the lockfile and no override keeps the vulnerable version reachable.
- For owned sibling packages, prefer fixing the owned package's public types or metadata over downstream casts or suppressions.

## Ecosystem Commands

- npm: prefer `npm ci` for validation; use repo scripts or `npm update` / `npx npm-check-updates -i --install never` only in approved update mode.
- pnpm: prefer `pnpm install --frozen-lockfile` for validation; use `pnpm update` only in approved update mode.
- Yarn: prefer `yarn install --immutable` for modern Yarn; use the repo's documented command for Yarn classic.
- Bun: prefer `bun install --frozen-lockfile`; use `bun update` only in approved update mode.
- Python/uv: prefer `uv sync --frozen` or the repo's venv/bootstrap script; use `uv lock --upgrade` only in approved update mode.
- Python/Poetry: prefer `poetry install --sync`; use `poetry update` only in approved update mode.
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
