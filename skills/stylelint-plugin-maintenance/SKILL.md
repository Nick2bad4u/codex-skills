---
name: stylelint-plugin-maintenance
description: Builds, audits, and maintains Stylelint plugin repos. Use when scaffolding plugins, auditing best practices, discovering/implementing domain-specific rules, or syncing docs, tests, configs, and package validation.
---

# Stylelint Plugin Maintenance

Use this skill for Stylelint plugin authoring workflows where runtime shape, PostCSS traversal, metadata, docs, configs, tests, and package surfaces must stay coherent.

## Bootstrap A New Plugin

1. Treat the current repository as a structure and quality baseline, not as source rule content.
2. Extract package name, namespace/rule prefix, short purpose, and requested initial rules from the user's message.
3. Re-identify package metadata, README, docs site, URLs, Docusaurus branding, examples, generated tables, and release config.
4. Remove unrelated template rule artifacts surgically while preserving shared infrastructure.
5. Implement only requested rule behavior. If no rules are requested, produce a clean minimal plugin scaffold.
6. Keep rule metadata and docs statically authored.
7. Update Stylelint plugin exports, shareable configs, tests, docs, generated surfaces, and package exports.

## Audit Best Practices

1. Inspect package versions, runtime shape, rule naming, metadata, messages, `meta.url`, fixability, PostCSS traversal strategy, custom syntax behavior, shareable configs, tests, docs, package exports, and publish readiness.
2. Verify current official Stylelint documentation when behavior depends on recent tooling.
3. Prefer deterministic fixer behavior and avoid generic CSS-lint advice that another established plugin already covers unless this repo has a clear domain-specific reason.
4. Fix high-confidence issues directly.

## Discover Rules

Research nearby Stylelint plugins and domain-specific CSS ecosystems. Choose rules that are useful, non-duplicative, and realistic to diagnose reliably. Implement typed rule modules, Stylelint/PostCSS-safe traversal, static metadata, docs, tests using real `stylelint.lint(...)`, config wiring, and deterministic fixers only when safe.

## Validation

Run the repository's lint, typecheck, tests, docs, sync, package checks, and publish dry run when available. Finish with ideas evaluated, changes made, gaps intentionally left, and validation results.
