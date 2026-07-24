---
name: schemastore-pr-maintenance
description: Maintains SchemaStore PRs. Use when working in SchemaStore/schemastore on JSON schemas, catalog entries, fileMatch patterns, tests, schema-validation.jsonc exceptions, CODEOWNERS-owned schemas, or PR readiness.
---

# SchemaStore PR Maintenance

Use this skill for SchemaStore contribution work where the goal is a mergeable PR that follows current repository practice, validates locally, and avoids breaking editor/language-server users.

## Source Priority

1. Read the current SchemaStore checkout first: `CONTRIBUTING.md`, `.github/PULL_REQUEST_TEMPLATE.md`, `package.json`, `src/api/json/catalog.json`, `src/schema-validation.jsonc`, `.github/CODEOWNERS`, and touched adjacent schemas/tests.
2. Use [schemastore-standards.md](references/schemastore-standards.md) for the compact standards checklist and current command map.
3. Run `scripts/audit_schemastore_pr.py <repo>` to summarize changed schema surfaces and targeted validation commands before final review.
4. Check current upstream docs or PR comments when a maintainer asks for a project-specific convention, language-server behavior, or validator exception not covered by the local files.

## Workflow

1. Identify the PR type: local hosted schema, remote/self-hosted catalog entry, existing schema update, multi-version schema update, `$ref`/subschema refactor, catalog-only change, or validation tooling change.
2. Preserve SchemaStore compatibility. Prefer draft-07, avoid needless renames of schema files/names/paths, keep old `$ref` paths when refactoring public subschemas, and do not remove deprecated or undocumented tool behavior merely because it is awkward.
3. Ground schema content in upstream tool documentation, released behavior, example config files, source code, changelog entries, or fixtures. Do not invent unsupported options.
4. Add or update positive tests under `src/test/<schemaName>/`. Add negative tests under `src/negative_test/<schemaName>/` when adding constraints, enums, required fields, formats, mutually exclusive settings, or deprecated/invalid combinations.
5. Register local schemas in `src/api/json/catalog.json` unless they are intentional subschemas, redirects, or entries covered by `src/schema-validation.jsonc`.
6. Keep `fileMatch` specific. Avoid generic names such as `config.toml`, `settings.json`, `*.json`, or broad directory globs unless the upstream tool really owns that pattern.
7. Use validation exceptions only after proving the strict failure is intentional: `ajvNotStrictMode`, `highSchemaVersion`, `missingCatalogUrl`, `skiptest`, `options.externalSchema`, `options.unknownKeywords`, or `options.unknownFormat`.
8. Check `.github/CODEOWNERS` for touched schemas and expect owner review or self-merge behavior on owned paths.
9. Format with the repo formatter and rerun targeted validation after every meaningful schema/test change.

## Adoption Evidence

- When project adoption helps maintainers assess a new schema or external catalog entry, include concise, current metrics in the PR description.
- Prefer GitHub stars from the canonical repository and package downloads from the primary registry. Link the source and state the measurement date and download window.
- Treat adoption metrics only as evidence that the schema would benefit users. They do not prove schema correctness and never replace upstream documentation, released source, runtime behavior, fixtures, or validation.
- Omit metrics when they are unavailable, ambiguous, stale, or irrelevant. Do not add popularity fields to `src/api/json/catalog.json`.

## Validation

Prefer current repo scripts and CLI behavior:

```powershell
npm clean-install
npm run typecheck
npm run eslint
node ./cli.js check --schema-name=<schemaName.json>
node ./cli.js coverage --schema-name=<schemaName.json>
node ./cli.js check
node ./cli.js coverage
npm run prettier
```

Run targeted `check --schema-name` for touched local schemas, then run the full CI-equivalent commands when catalog, validation config, CLI helpers, or shared schemas changed. Run `coverage --schema-name` only for schemas listed in `src/schema-validation.jsonc` `coverage`; add coverage entries deliberately, not as a reflex.

## Output

Finish with the PR type, schema/catalog/test files changed, evidence source for schema behavior, validation commands run, remaining SchemaStore-specific risk, and any maintainer/owner follow-up needed.
