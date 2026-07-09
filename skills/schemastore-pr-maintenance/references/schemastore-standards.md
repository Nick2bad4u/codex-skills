# SchemaStore Standards

## Contents

- [Repository Shape](#repository-shape)
- [Schema Authoring](#schema-authoring)
- [Catalog Rules](#catalog-rules)
- [Tests And Validation](#tests-and-validation)
- [References And Exceptions](#references-and-exceptions)
- [PR Readiness](#pr-readiness)
- [Source Links](#source-links)

## Repository Shape

- Schemas live in `src/schemas/json/<schemaName>.json`.
- Local schema tests live in `src/test/<schemaName>/` and `src/negative_test/<schemaName>/`.
- The public catalog lives in `src/api/json/catalog.json`; entries require `name`, `description`, and `url`, while `fileMatch` is optional for formats without stable filenames.
- Validation exceptions and targeted validator options live in `src/schema-validation.jsonc`.
- The PR template is intentionally only a pointer to `CONTRIBUTING.md`; the actual standards are in repo files and maintainer comments.
- SchemaStore CI uses Node 20, `npm clean-install`, `npm run typecheck`, `npm run eslint`, `node ./cli.js check`, and `node ./cli.js coverage`.

## Schema Authoring

- Prefer `http://json-schema.org/draft-07/schema#` unless an existing schema or upstream requirement proves another draft is needed.
- Validate actual tool behavior, including undocumented and deprecated options. SchemaStore wants editor validation to match real-world config files, not only ideal documentation.
- Avoid overconstraint: do not add complex regexes, exhaustive enums without a fallback, or `additionalProperties: false` unless false positives are unlikely and the upstream format is genuinely closed.
- Add `description` fields where they help editor UX. Prefer short descriptions with an upstream documentation URL when available.
- Mark undocumented behavior with `UNDOCUMENTED.` in `description` or a precise `$comment`.
- Mark deprecated behavior with `DEPRECATED.` in `description`; do not remove it unless upstream removal and compatibility impact are clear.
- Preserve public schema names, old schema URLs, and important subschema JSON Pointer paths when refactoring.

## Catalog Rules

- Register local schemas with a `https://www.schemastore.org/<schemaName>.json` catalog URL unless the entry intentionally points at a remote schema.
- Keep catalog entries alphabetized/formatted by the repo formatter rather than manual whitespace.
- Make `fileMatch` specific enough to avoid stealing common filenames from unrelated tools.
- Prefer multiple simple patterns over clever glob syntax because language-server glob behavior varies.
- For remote/self-hosted schemas, catalog-only changes are valid when `url` points at the maintained upstream schema.
- For versioned schemas, keep older schema files and add a `versions` map; point `url` at the latest supported version.

## Tests And Validation

- Add positive tests for every new schema and every new meaningful object/branch/enum/path.
- Add negative tests for constraints that should reject invalid files, especially required fields, enum-only values, incompatible options, and strict object boundaries.
- JSON, YAML, YML, and TOML test files are supported.
- Every test file needs the correct schema association as enforced by `node ./cli.js check`.
- Run `node ./cli.js check --schema-name=<schemaName.json>` for touched local schemas.
- Run full `node ./cli.js check` after touching `catalog.json`, `schema-validation.jsonc`, shared `$ref` targets, CLI helpers, or multiple schemas with shared behavior.
- Use `node ./cli.js coverage --schema-name=<schemaName.json>` only for schemas opted into `coverage`; strict coverage entries fail CI.

## References And Exceptions

- Local `$ref` targets must exist in SchemaStore, use the same draft, and list transitive `externalSchema` values in `src/schema-validation.jsonc` when the CLI needs them.
- Self-hosted `$ref` targets are not generally supported by SchemaStore validation; prefer local copies or remote catalog entries.
- Use `ajvNotStrictMode` only when strict-mode failures are intentional and cannot be corrected without worsening compatibility.
- Use `highSchemaVersion` when a schema must use a newer JSON Schema draft despite weaker editor support.
- Use `missingCatalogUrl` for partial schemas, subschemas, redirects, and intentional local files without catalog entries.
- Use `skiptest` mainly for empty redirect schemas or schemas with external-reference behavior the local validator cannot test.
- Use `options.unknownKeywords` and `options.unknownFormat` when upstream schemas or ecosystem validators rely on non-standard extensions.

## PR Readiness

- Keep PRs scoped to one schema family or one catalog concern.
- Include evidence in the PR description or comments: upstream docs, source links, released examples, or failing/passing config examples.
- Explain any validator exceptions and why a schema fix was not better.
- Check `.github/CODEOWNERS`; owned schemas may require team review or can be handled by the code-owner self-merge workflow.
- If pre-commit formatting fails in CI, run `npm run prettier:fix` locally and commit the formatting change.
- Do not treat one green targeted schema command as enough when catalog, shared refs, or validation config changed.

## Source Links

- SchemaStore repository: <https://github.com/SchemaStore/schemastore>
- Contribution guide: <https://github.com/SchemaStore/schemastore/blob/master/CONTRIBUTING.md>
- Public catalog/API description: <https://www.schemastore.org/>
- Current PR template: <https://github.com/SchemaStore/schemastore/blob/master/.github/PULL_REQUEST_TEMPLATE.md>
- Validation workflow: <https://github.com/SchemaStore/schemastore/blob/master/.github/workflows/validate.yml>
