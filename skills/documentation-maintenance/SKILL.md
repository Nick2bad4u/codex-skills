---
name: documentation-maintenance
description: Maintains repository docs, TSDoc, TypeDoc output, API comments, and Docusaurus sites. Use when fixing docs drift, TypeDoc diagnostics, TSDoc quality, broken examples/links, or polishing an existing Docusaurus portal.
---

# Documentation Maintenance

Use this skill when documentation must match real code, commands, package metadata, generated docs, and site behavior.

## Ground Truth

Use implementation, tests, package metadata, CLI output, generated docs, docs scripts, and commit history as ground truth. When documentation depends on external tooling or APIs, verify current primary documentation before changing guidance.

## Workflows

### Repository Docs

1. Inspect docs structure, README, package metadata, docs scripts, examples, generated docs, and site config.
2. Fix stale commands, broken links, wrong examples, outdated API descriptions, duplicated sections, and missing setup or usage steps.
3. Preserve the repository's voice and structure. Do not invent behavior.
4. Validate with docs, link-check, lint, build, or package checks when available.

### TSDoc And TypeDoc

1. Run or inspect the TypeDoc/docs-validation command.
2. Trace referenced symbols before documenting them.
3. Describe actual behavior, parameters, type parameters, return values, thrown errors, defaults, examples, deprecations, and links only when useful.
4. Use only tags and visibility patterns accepted by the repository's TypeDoc/TSDoc setup.
5. Fix pipeline configuration instead of editing generated output when the pipeline is wrong.

### Docusaurus Polish

1. Inspect Docusaurus config, sidebars, homepage, CSS, docs package metadata, assets, generated docs, search dependencies, and validation scripts.
2. Preserve real package identity, route integrity, and generated-doc source-of-truth workflows.
3. Improve search, navbar, homepage, footer, sidebars, maintainer paths, and docs organization without inventing fake content.
4. Validate docs typecheck/build, lint, tests, and package checks that apply.

## Output

Finish with changed docs surfaces, why they changed, validation results, and any unknowns that could not be verified from source.
