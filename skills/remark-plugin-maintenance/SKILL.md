---
name: remark-plugin-maintenance
description: Builds, audits, and maintains remark and remark-lint plugin repos. Use when scaffolding plugins, creating or repairing remark-lint rules, auditing unified/Markdown AST usage, syncing docs/tests/configs, or validating package/CLI behavior.
---

# Remark Plugin Maintenance

Use this skill for unified/remark plugin authoring workflows where mdast traversal, lint messages, docs, fixtures, presets, package exports, and Markdown processing behavior must stay coherent.

## Bootstrap A New Plugin

1. Treat the current repository as a structure and quality baseline, not as source rule content.
2. Identify whether the package is a transformer plugin, a `remark-lint` rule, a preset, or a shared remark config.
3. Extract package name, rule or plugin name, intended Markdown behavior, target syntax extensions, and requested options from the user's message.
4. Re-identify package metadata, README, docs site, examples, fixtures, generated tables, release config, and CI gates.
5. Remove unrelated template artifacts surgically while preserving shared infrastructure.
6. Implement only requested behavior. If no rules are requested, produce a clean minimal scaffold rather than speculative checks.
7. Update exports, TypeScript declarations, docs, fixtures, tests, presets/configs, generated surfaces, and package metadata together.

## Audit Best Practices

1. Inspect package versions, ESM shape, plugin exports, option schemas or validation, AST traversal, node type coverage, vfile messages, source positions, CLI compatibility, config examples, fixtures, docs, and publish surface.
2. Verify current unified, remark, mdast, and remark-lint documentation when behavior depends on recent ecosystem conventions.
3. Prefer narrow mdast utilities and syntax-aware parsing over regex across raw Markdown unless the rule explicitly targets source text.
4. For `remark-lint` rules, report through `file.message`/vfile diagnostics with useful locations and stable rule names.
5. Avoid destructive rewrites, unstable formatting changes, or autofix-style behavior unless the package is intentionally a transformer and tests prove idempotence.
6. Fix high-confidence issues directly and leave speculative stylistic rule ideas out unless the user asks for discovery.

## Rule And Plugin Design

- Choose transformer plugins for intentional AST changes and `remark-lint` rules for diagnostics.
- Keep option names small, typed, documented, and covered by invalid-option tests.
- Use mdast/unist node types and utilities consistently. Preserve positional data where diagnostics depend on it.
- Handle CommonMark, GFM, frontmatter, MDX, directives, math, and custom syntax only when the repository parser/config supports them.
- Make messages actionable and deterministic. Do not depend on object iteration order, filesystem order, current locale, network calls, or live registries in tests.
- Keep preset/config packages honest: document which plugins they enable, option defaults, ignored generated paths, and compatibility with `remark-cli`.

## Surface Sync

Identify the source of truth for plugin registration, presets, docs, examples, CLI config, fixtures, snapshots, generated README tables, package exports, and changelog/release notes. Fix drift at the source and rerun generation scripts instead of editing generated output by hand.

## Discover Rules

Research nearby remark, markdownlint, MDX, docs-site, and prose-lint ecosystems. Choose rules that are useful, non-duplicative, domain-specific, and realistic to diagnose from Markdown AST or configured source text. Implement typed modules, docs, examples, valid/invalid fixtures, option coverage, config wiring, and package exports.

## Validation

Run the repository's relevant lint, typecheck, unit tests, fixture tests, docs checks, `remark` CLI checks, package checks, and publish dry run when available. Finish with plugin/rule behavior changed, docs and config surfaces updated, validation results, and any syntax extensions or compatibility gaps intentionally left out.
