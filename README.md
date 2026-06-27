# Codex Skills

[![NPM license.](https://flat.badgen.net/npm/license/@typpi/codex-skills?color=purple)](https://github.com/Nick2bad4u/codex-skills/blob/main/LICENSE) [![NPM total downloads.](https://flat.badgen.net/npm/dt/@typpi/codex-skills?color=pink)](https://www.npmjs.com/package/@typpi/codex-skills) [![Latest GitHub release.](https://flat.badgen.net/github/release/Nick2bad4u/codex-skills?color=cyan)](https://github.com/Nick2bad4u/codex-skills/releases) [![GitHub stars.](https://flat.badgen.net/github/stars/Nick2bad4u/codex-skills?color=yellow)](https://github.com/Nick2bad4u/codex-skills/stargazers) [![GitHub forks.](https://flat.badgen.net/github/forks/Nick2bad4u/codex-skills?color=orange)](https://github.com/Nick2bad4u/codex-skills/forks) [![GitHub open issues.](https://flat.badgen.net/github/open-issues/Nick2bad4u/codex-skills?color=red)](https://github.com/Nick2bad4u/codex-skills/issues) [![Repo Checks.](https://flat.badgen.net/github/checks/nick2bad4u/codex-skills?color=green)](https://github.com/Nick2bad4u/codex-skills/actions)

Personal multi-skill repository for reusable Codex workflows that are useful locally but not ready to publish as standalone packages.

## Skills

- `ci-release-readiness`: debug CI failures, dependency-update fallout, and release readiness.
- `code-review-maintenance`: review code, triage review claims, normalize drift, and fix brittle paths.
- `documentation-maintenance`: maintain docs, TSDoc, TypeDoc, and Docusaurus sites.
- `eslint-plugin-maintenance`: bootstrap, audit, and maintain ESLint plugin repositories.
- `github-actions-workflow-maintenance`: create, review, edit, and harden GitHub Actions workflows.
- `lint-cleanup`: fix lint and ESLint diagnostics without weakening rules.
- `mermaid-diagram-maintenance`: create, edit, review, and dark-theme Mermaid diagrams.
- `prettier-plugin-maintenance`: bootstrap, audit, and maintain Prettier plugin repositories.
- `release-publish-loop`: push release candidates, watch CI, and publish verified releases.
- `remark-plugin-maintenance`: bootstrap, audit, and maintain remark and remark-lint plugins.
- `stylelint-plugin-maintenance`: bootstrap, audit, and maintain Stylelint plugin repositories.
- `test-quality-maintenance`: add, repair, and improve tests, coverage, e2e, and benchmarks.
- `vsicons-association-recommender`: recommend vscode-icons associations for workspace files.
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
