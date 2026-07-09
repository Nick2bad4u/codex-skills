---
name: eslint-plugin-maintenance
description: Builds, audits, and maintains ESLint plugin repos. Use when scaffolding plugins, auditing best practices, syncing rule docs/tests/presets/generated surfaces, or discovering and implementing high-value net-new ESLint rules.
---

# ESLint Plugin Maintenance

Use this skill for ESLint plugin authoring workflows where rule metadata, docs, tests, presets, package exports, and generated surfaces must stay coherent.

## Bootstrap A New Plugin

1. Treat the current repository as a structure and quality baseline, not as source rule content.
2. Extract the package name, namespace/rule prefix, short purpose, and requested initial rules from the user's message.
3. Re-identify package metadata, README, docs site, URLs, Docusaurus branding, examples, generated tables, and release config.
4. Remove unrelated template rule artifacts surgically. Do not wipe mature root config, docs, scripts, workflows, or tests just to get green checks.
5. Implement only requested rule behavior. If no rules are requested, produce a clean minimal scaffold rather than speculative rules.
6. Keep rule metadata and docs statically authored. Do not inject real docs content at runtime.
7. Update plugin registration, flat configs, presets, docs URLs, tests, generated surfaces, package exports, and docs site navigation.

## Audit Best Practices

1. Inspect package versions, plugin exports, flat configs, rule metadata, schemas, docs URLs, fixer/suggestion behavior, RuleTester coverage, TypeScript/parser-service use, package exports, README/site docs, and compatibility claims.
2. Verify current official ESLint and typescript-eslint guidance when behavior depends on recent tooling.
3. Prefer official guidance over local habit when they conflict, but do not cargo-cult patterns that do not fit the plugin.
4. Fix high-confidence issues directly.

## Rule Surface Sync

Identify the source of truth for rule metadata, docs generation, preset wiring, and generated tables. Check source implementation, registration, docs, examples, options, messages, tests, fixtures, snapshots, README tables, generated docs, site navigation, presets, package exports, config names, and public metadata. Fix drift at the source of truth and rerun sync/generation scripts.

## Discover Rules

Research nearby ESLint ecosystems and the repository's current rule catalog. Choose rules that are useful, non-duplicative, domain-specific, and realistic to implement reliably. Implement typed source, complete metadata and schema, tests, docs, registration, config wiring, and generated surfaces.

## Validation

Run the repository's relevant lint, typecheck, tests, docs, sync, package checks, and publish dry run when available. Finish with ideas rejected or drift found, changes made, preset/config placement, and validation results.
