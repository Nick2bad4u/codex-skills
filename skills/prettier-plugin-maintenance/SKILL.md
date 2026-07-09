---
name: prettier-plugin-maintenance
description: Builds, audits, and maintains Prettier plugin and shared config repos. Use when scaffolding plugins, fixing parsers/printers/options, auditing doc-builder behavior, testing formatting output, or validating package/editor/CI integration.
---

# Prettier Plugin Maintenance

Use this skill for Prettier plugin and shared Prettier config workflows where parser registration, printer output, doc builders, options, package exports, editor behavior, and formatting tests must stay coherent.

## Source Of Truth

- Verify current official Prettier docs when plugin API, CLI/API loading, config resolution, or option behavior matters.
- Treat the repository's `package.json`, Prettier config, TypeScript config, tests, fixtures, package exports, README, editor docs, and CI scripts as the operational source of truth.
- Prefer Prettier 3-compatible ESM and async APIs unless the repository explicitly supports older Prettier versions with tests.
- Do not use old blog posts as API authority when they conflict with current Prettier docs.

## Bootstrap A New Plugin

1. Identify whether the package is a language plugin, embedded-language plugin, printer extension, shared config, or integration helper.
2. Extract package name, supported languages or file extensions, parser names, AST source, intended formatting behavior, supported Prettier versions, and requested options from the user's message.
3. Re-identify package metadata, README, examples, fixtures, test runner, build output, package exports, release config, and editor/CI guidance.
4. Preserve mature root tooling. Remove unrelated template artifacts surgically instead of replacing shared config, workflows, release scripts, or docs.
5. Implement only requested parser/printer/config behavior. If no behavior is requested, produce a clean minimal scaffold rather than speculative formatting rules.
6. Wire `languages`, `parsers`, `printers`, `options`, and `defaultOptions` together with docs, fixtures, tests, package exports, and generated surfaces.

## Audit Best Practices

1. Inspect Prettier version range, module format, plugin entrypoint, parser names, AST format names, printer keys, option schemas, defaults, config examples, CLI/API loading examples, package exports, fixtures, snapshots, and CI coverage.
2. Verify parser and printer implementations are deterministic, side-effect free, and independent of filesystem, network, locale, or current time unless explicitly documented and tested.
3. Prefer composing Prettier `doc.builders` such as `group`, `indent`, `line`, `softline`, `hardline`, `join`, `ifBreak`, and `lineSuffixBoundary` over string concatenation with manual newlines.
4. Keep `print` functions focused on AST-to-doc conversion. Do not run heavy type-checking, global scans, installs, network calls, or uncached file I/O while printing.
5. Preserve comments, pragmas, ignored ranges, source locations, embedded languages, and parser errors intentionally. Add tests for each behavior the plugin claims to support.
6. Fix high-confidence drift directly and leave broad formatting taste changes out unless the repository owns that format policy.

## Parser And Printer Design

- Use existing parsers when practical, and only introduce a custom parser when the target language or transformed AST requires it.
- Keep AST adapters small and typed. Normalize external AST nodes into minimal internal shapes with type guards instead of leaking parser-specific structures through every printer.
- Return Prettier docs, not partially formatted source strings. Avoid raw newline characters inside strings unless preserving literal text is required.
- Use `path.call(print, ...)`, `path.map(...)`, and local printer helpers to recurse through child nodes.
- Prefer stable option names with explicit defaults, descriptions, CLI categories, docs examples, and invalid-option tests.
- Make formatting idempotent: formatting already formatted output should produce the same output.
- Treat shared Prettier config packages separately from plugins: they should export config only, document required plugin dependencies, and avoid hidden runtime behavior.

## Surface Sync

Identify the source of truth for plugin registration, parser/printer exports, option metadata, shared config exports, README tables, docs examples, fixture snapshots, package exports, TypeScript declarations, editor snippets, and release notes. Fix drift at the source and rerun the repository's generation or snapshot update scripts instead of hand-editing generated output.

## Validation

Run the repository's relevant lint, typecheck, unit tests, fixture/snapshot tests, `prettier --check`, package validation, and publish dry run when available. For plugin behavior, add focused tests that call Prettier's `format` API with the plugin loaded, assert exact output, and cover parser inference through `filepath` or configured language extensions when relevant.

Finish with parser/printer/options behavior changed, docs and package surfaces updated, fixtures or snapshots added, compatibility assumptions, validation results, and any Prettier API uncertainty that remains.
