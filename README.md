# Codex Skills

Personal multi-skill repository for reusable Codex workflows that are useful locally but not ready to publish as standalone packages.

## Skills

- `ci-release-readiness`: debug CI failures, dependency-update fallout, and release readiness.
- `code-review-maintenance`: review code, triage review claims, normalize drift, and fix brittle paths.
- `documentation-maintenance`: maintain docs, TSDoc, TypeDoc, and Docusaurus sites.
- `eslint-plugin-maintenance`: bootstrap, audit, and maintain ESLint plugin repositories.
- `lint-cleanup`: fix lint and ESLint diagnostics without weakening rules.
- `stylelint-plugin-maintenance`: bootstrap, audit, and maintain Stylelint plugin repositories.
- `test-quality-maintenance`: add, repair, and improve tests, coverage, e2e, and benchmarks.
- `workspace-continuation`: continue active work, implement plans, and write handoffs.

## Install Locally

```powershell
npm run install:local
```

This installs all skills from this repo into the shared user skill location for supported agents.

## Validate

```powershell
npm run validate
npm run format:check
npm run release:verify
```

This repo is intentionally private/local-first for now. Individual skills can be promoted to standalone package repositories later if they prove stable enough to publish.
