# Codex Skills

[![NPM license.](https://flat.badgen.net/npm/license/@typpi/codex-skills?color=purple)](https://github.com/Nick2bad4u/codex-skills/blob/main/LICENSE) [![NPM total downloads.](https://flat.badgen.net/npm/dt/@typpi/codex-skills?color=pink)](https://www.npmjs.com/package/@typpi/codex-skills) [![Latest GitHub release.](https://flat.badgen.net/github/release/Nick2bad4u/codex-skills?color=cyan)](https://github.com/Nick2bad4u/codex-skills/releases) [![GitHub stars.](https://flat.badgen.net/github/stars/Nick2bad4u/codex-skills?color=yellow)](https://github.com/Nick2bad4u/codex-skills/stargazers) [![GitHub forks.](https://flat.badgen.net/github/forks/Nick2bad4u/codex-skills?color=orange)](https://github.com/Nick2bad4u/codex-skills/forks) [![GitHub open issues.](https://flat.badgen.net/github/open-issues/Nick2bad4u/codex-skills?color=red)](https://github.com/Nick2bad4u/codex-skills/issues) [![Repo Checks.](https://flat.badgen.net/github/checks/nick2bad4u/codex-skills?color=green)](https://github.com/Nick2bad4u/codex-skills/actions)

Personal multi-skill repository for reusable Codex workflows that are useful locally but not ready to publish as standalone packages.

## Skills

- `agent-skill-instruction-creation`: Creates agent skill and instruction surfaces. Use when authoring SKILL.md folders, AGENTS.md/AGENTS.override.md, CLAUDE.md, Copilot or Cursor rules, or when asked to bootstrap, design, scaffold, or migrate reusable agent guidance.
- `agent-skill-instruction-review`: Audits and improves agent skill and instruction surfaces. Use when reviewing SKILL.md, AGENTS.md/AGENTS.override.md, CLAUDE.md, Copilot or Cursor rules, or when asked to lint, score, modernize, deduplicate, secure, or repair agent guidance.
- `ci-release-readiness`: Validates release readiness and debugs CI failures. Use when inspecting GitHub Actions runs, failed checks, dependency-update validation, release gates, release-candidate prep, or readiness loops that must not publish without approval.
- `codacy-management`: Manages and audits Codacy Cloud or Self-hosted repositories, issues, security findings, pull requests, coverage, tools, patterns, quality gates, coding standards, and API operations. Use whenever the user mentions Codacy or asks to inspect, explain, configure, or safely change Codacy state.
- `code-review-maintenance`: Maintains code-review quality across repos, files, configs, and low-confidence claims. Use when reviewing codebases/files, brittle implementations, consistency drift, comment triage, correctness, maintainability, security, release, or test risks.
- `dependency-update-maintenance`: Validates and optionally performs dependency updates without weakening quality gates. Use when handling Dependabot/Renovate/npm-check-updates changes, lockfile review, update-tool runs, or code/config/type/lint/build/test fallout.
- `documentation-maintenance`: Maintains repository docs, TSDoc, TypeDoc output, API comments, and Docusaurus sites. Use when fixing docs drift, TypeDoc diagnostics, TSDoc quality, broken examples/links, or polishing an existing Docusaurus portal.
- `eslint-plugin-maintenance`: Builds, audits, and maintains ESLint plugin repos. Use when scaffolding plugins, auditing best practices, syncing rule docs/tests/presets/generated surfaces, or discovering and implementing high-value net-new ESLint rules.
- `github-actions-workflow-maintenance`: Maintains GitHub Actions workflows. Use when creating, reviewing, editing, or hardening .github/workflows YAML, workflow_call callers, CI/CD automation, action pinning, permissions, npm publishing, caching, matrices, actionlint, or review comments.
- `google-tag-manager-management`: Inspect and manage Google Tag Manager accounts, containers, workspaces, resources, versions, permissions, consent, previews, and publishing through API v2. Use whenever the user mentions Google Tag Manager or GTM, tags, triggers, variables, consent mode, container versions, publishing, permissions, or API automation.
- `lint-cleanup`: Validates and repairs lint, ESLint, and static-analysis diagnostics at the root cause. Use when running lint, resolving errors/warnings, removing unnecessary disable comments, or replacing suppressions with code, type, config, or test fixes.
- `mermaid-diagram-maintenance`: Maintains Mermaid diagrams and config. Use when creating, editing, reviewing, theming, or debugging Mermaid flowcharts, sequence/ER/Gantt diagrams, dark themes, themeVariables, frontmatter config, renderer issues, or Markdown blocks.
- `npm-12-migration`: Migrates npm-managed repositories from npm 11 or older to npm 12 with lifecycle-script allowlisting, Node and CI alignment, config and lockfile review, breaking-output fixes, and full validation. Use when explicitly invoked for an npm 12 upgrade, migration audit, or allowScripts rollout.
- `powershell-development`: Develops, audits, repairs, and tests PowerShell. Use whenever the user asks to create, review, debug, harden, or test .ps1, .psm1, or .psd1 files, functions, modules, profiles, PSScriptAnalyzer, Pester, native tools, cross-platform automation, remoting, packaging, or PowerShell CI.
- `prettier-plugin-maintenance`: Builds, audits, and maintains Prettier plugin and shared config repos. Use when scaffolding plugins, fixing parsers/printers/options, auditing doc-builder behavior, testing formatting output, or validating package/editor/CI integration.
- `python-strict-development`: Maintains strict Python projects with Ruff, mypy, Pyright, pytest, editor, and package-script gates. Use when creating, auditing, or repairing strict lint, format, typecheck, test, compile, or VS Code tooling practices.
- `release-publish-loop`: Executes authorized release publishing. Use when the user explicitly asks Codex to commit/push, watch CI and SonarCloud/SonarQube gates, fix failed checks, choose semver, dispatch publish or release workflows, and verify artifacts.
- `remark-plugin-maintenance`: Builds, audits, and maintains remark and remark-lint plugin repos. Use when scaffolding plugins, creating or repairing remark-lint rules, auditing unified/Markdown AST usage, syncing docs/tests/configs, or validating package/CLI behavior.
- `schemastore-pr-maintenance`: Maintains SchemaStore PRs. Use when working in SchemaStore/schemastore on JSON schemas, catalog entries, fileMatch patterns, tests, schema-validation.jsonc exceptions, CODEOWNERS-owned schemas, or PR readiness.
- `snyk-management`: Inspect and manage Snyk organizations, groups, projects, targets, issues, policies, ignores, tests, monitored snapshots, SBOMs, audit logs, settings, and safe REST API operations. Use whenever the user mentions Snyk posture, findings, scans, projects, imports, configuration, or remediation.
- `socket-management`: Inspect and manage Socket.dev organizations, repositories, scans, dependency and supply-chain alerts, policies, resolutions, reports, SBOMs, analytics, audit logs, and safe API operations. Use whenever the user mentions Socket Security or Socket.dev posture, findings, scans, configuration, or remediation.
- `stepsecurity-management`: Audit and manage StepSecurity Actions posture, runtime detections, incidents, policies, suppressions, and hardening through MCP, REST, Terraform, and reviewed pull requests. Use whenever the user mentions StepSecurity, Harden-Runner, Actions runtime security, or StepSecurity findings.
- `stylelint-plugin-maintenance`: Builds, audits, and maintains Stylelint plugin repos. Use when scaffolding plugins, auditing best practices, discovering/implementing domain-specific rules, or syncing docs, tests, configs, and package validation.
- `test-quality-maintenance`: Generates, repairs, and improves tests and coverage. Use when writing unit tests, fixing failures, improving meaningful coverage, testing error handling, adding Playwright E2E tests, or creating focused benchmarks.
- `uptimerobot-management`: Inspect and manage UptimeRobot monitors, incidents, integrations, alert contacts, maintenance windows, groups, public status pages, tags, API v3, CLI, and MCP access. Use whenever the user mentions UptimeRobot, uptime monitoring, outages, status pages, notification routing, API or CLI automation, or asks to audit or safely change UptimeRobot state.
- `verify-oxlint-plugin-compatibility`: Validates and finishes Oxlint compatibility in ESLint plugin repositories. Use when testing or documenting an ESLint plugin with Oxlint, diagnosing JS-plugin loading or rule failures, assessing type-aware rule limits, adding README guidance, or adding compatibility regression coverage.
- `vsicons-association-recommender`: Generates deduplicated, copy-pasteable vscode-icons associations after checking existing VS Code settings. Use when mapping workspace filenames, extensions, generated files, dotfolders, or folders to verified icon names without duplicate file or folder assignments.
- `wakatime-management`: Inspect and manage WakaTime coding-activity summaries, stats, projects, goals, durations, heartbeats, data exports, organization dashboards, API access, and privacy-safe reporting. Use when the user mentions WakaTime dashboards, tracked coding time, plugins, heartbeats, exports, or API troubleshooting.
- `workspace-continuation`: Generates compact handoffs and continues active plans from workspace state. Use when resuming work, carrying a plan through implementation and validation, or summarizing work for a fresh session without rediscovery.

## Install Locally

```powershell
npm run install:local
```

This installs all skills from this repo into the shared user skill location for supported agents.

## Validate

```powershell
npm run validate
npm run test:skills
npm run test:python
npm run format:check
npm run release:verify
```

`npm run test:skills` runs an explicit contract for every skill. The matrix covers routing terms, core workflow
sections, owned references and scripts, generated invocation metadata, parseable local icons, coverage registration,
and executable helper entry points. Adding or removing a skill without updating its contract fails the suite.

`npm run test:python` adds the deeper behavior and failure-path tests for every Python helper and enforces aggregate
branch coverage. It also rejects Cobertura reports whose filenames cannot be mapped back to tracked helper files, so
Codecov cannot silently accept an upload that it will later fail to process. Both layers run in CI through
`npm run release:verify`.

This repo is intentionally private/local-first for now. Individual skills can be promoted to standalone package repositories later if they prove stable enough to publish.
