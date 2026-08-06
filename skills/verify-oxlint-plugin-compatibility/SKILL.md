---
name: verify-oxlint-plugin-compatibility
description: Validates and finishes Oxlint compatibility in ESLint plugin repositories. Use when testing or documenting an ESLint plugin with Oxlint, diagnosing JS-plugin loading or rule failures, assessing type-aware rule limits, adding README guidance, or adding compatibility regression coverage.
---

# Verify Oxlint Plugin Compatibility

Prove the published plugin surface against the repository's actual Oxlint version, explain failures by ownership, make justified compatibility fixes, and document only the support that the evidence establishes.

Honor the requested scope. Keep assessment-only requests read-only; implement tests, compatibility fixes, CI wiring, and documentation only when the user asks to add or finish support.

## Establish The Current Contract

1. Read the current official Oxlint pages for [JS plugins](https://oxc.rs/docs/guide/usage/linter/js-plugins.html), [writing JS plugins](https://oxc.rs/docs/guide/usage/linter/writing-js-plugins.html), and [type-aware linting](https://oxc.rs/docs/guide/usage/linter/type-aware.html). Treat stability labels and unsupported APIs as version-sensitive.
2. Inspect the installed or locked `oxlint` version and its `--help` output. Prefer the repository's version over `latest` for the compatibility result; test a newer version separately only to diagnose a possible upstream fix.
3. Inspect package exports, build output, plugin `meta.name`, rule registration, presets, processors, parsers, fixtures, RuleTester cases, package scripts, lockfiles, and CI.
4. Separate these commonly conflated cases:
   - A plugin authored in TypeScript may work when its published build is loadable JavaScript.
   - A JS plugin rule that requests TypeScript type information is not made compatible by compilation.
   - Oxlint's native type-aware rules are a separate engine and do not make arbitrary type-aware JS-plugin rules work.
   - Custom parsers or file formats are separate from ordinary JavaScript and TypeScript syntax support.

## Inventory Rules Before Probing

Classify every exported rule and preset using source and tests, not names alone:

- syntax-only ESLint v9-compatible rules;
- rules using scope analysis, code paths, selectors, tokens, fixes, or suggestions;
- rules using `parserServices`, `ESLintUtils.getParserServices`, a TypeScript program or checker, or equivalent type information;
- rules requiring a custom parser, processor, nonstandard file format, Node process state, or filesystem access;
- deprecated or compatibility-only rules that should not be advertised.

Record the preset-to-rule mapping and file globs. Do not claim whole-plugin support after testing only one easy rule.

## Compatibility Probe

- **Inputs:** `package.json`, the emitted plugin entry, existing RuleTester fixtures, and a temporary Oxlint config.
- **Outputs:** a `rule-compatibility-matrix` plus reproducible command and diagnostic evidence.

1. Install dependencies and run the normal build or prepare step. Test emitted package code, not TypeScript source that consumers never load.
2. Use the repository's local Oxlint binary. If none is installed, perform an isolated one-off probe first; add `oxlint` to dev dependencies only when retaining automated compatibility coverage.
3. Create a uniquely named temporary root-level Oxlint config, verify that its path does not already exist, and pass it with the installed version's explicit config option so relative plugin resolution matches real consumer usage. Never overwrite, rename, or reuse the repository's real `.oxlintrc*` or `oxlint.config.*`. Give a local build an explicit alias when its filename cannot provide the intended namespace:

   ```jsonc
   {
    "jsPlugins": [{ "name": "compat-probe", "specifier": "./dist/index.js" }],
    "rules": {
     "compat-probe/example-rule": "error",
    },
   }
   ```

4. Start with one syntax-only rule and an existing invalid fixture that must emit a diagnostic. A zero-diagnostic exit is not proof that a rule ran.
5. Exercise every rule included in a compatibility claim. Reuse valid and invalid RuleTester cases where possible and cover options, suggestions, and autofixes that are part of the public behavior.
6. Run the same fixture with ESLint and Oxlint. Compare rule ID, diagnostic count, message or `messageId`, locations, and fixed output where applicable. Explain intentional runner-format differences instead of hiding them.
7. Test file overrides and globs. Translate ESLint-only pattern syntax when Oxlint does not support it; specifically re-check extglob support before reusing patterns such as `@(ts|tsx)`.
8. Pack the package and test its package-name specifier from a temporary consumer when exports, module format, generated files, or publish contents could differ from the local build path.
9. Remove only the exact temporary paths created by the probe in a `finally`-style cleanup after capturing commands and results. Preserve a focused fixture and automated test only when the repository will maintain the compatibility claim.

## Diagnose Failures By Ownership

Classify each failure before editing:

- **Plugin defect:** broken published export, missing build artifact, stale pre-ESLint-v9 API, invalid rule metadata, shared mutable state, or an avoidable environment assumption. Fix it and rerun ESLint plus Oxlint tests.
- **Oxlint limitation:** unsupported type-aware plugin rule, parser, processor, file format, or API. Do not weaken rule semantics to manufacture a passing result; document the boundary and identify a native Oxlint alternative only when behavior is genuinely equivalent.
- **Oxlint divergence:** a documented API behaves differently. Reduce it to a minimal reproducible case, check the current upstream issue tracker, and report or link the upstream bug. Keep any workaround narrow, tested, and removable.
- **Configuration translation:** plugin presets cannot be consumed as-is, namespaces collide, or glob syntax differs. Publish an explicit Oxlint configuration example derived from the preset's real rule map.
- **Intentional incompatibility:** the rule fundamentally depends on unavailable semantics. State that no plugin-side compatibility change is appropriate.

Do not add `@oxlint/plugins` merely to make an ordinary ESLint plugin load. Its compatibility wrapper and `createOnce` API are an optional optimization; if adopted, verify ESLint behavior and add it as a runtime dependency as required by the current official guidance.

## Finish A Supported Integration

When the supported surface works:

1. Add a deterministic smoke or conformance test that runs built code with the pinned local Oxlint dependency.
2. Route it through an existing required test or validation script so CI actually executes it. Avoid a decorative script that no workflow calls.
3. Keep the lockfile and package metadata synchronized. Do not add Oxlint as a peer dependency unless consumers must supply it for the plugin's normal ESLint operation.
4. Rerun the build, ESLint tests, Oxlint compatibility test, lint, typecheck, formatting, documentation generation, package validation, and pack dry run that the repository provides.
5. Review the packed file list and final diff. Do not publish or release without explicit authorization.

## Add Honest README Documentation

Use the pinned [Storybook plugin README section](https://github.com/storybookjs/storybook/blob/a51491e749453ebd10252ec96f7828c7ebf23da1/code/lib/eslint-plugin/README.md#usage-with-oxlint) as a structural example, not text to copy.

Place `Usage with Oxlint` near the ESLint usage instructions. Include:

- the tested Oxlint version and the current JS-plugin stability label;
- `jsPlugins` with the published package specifier;
- explicit supported rules and compatible `overrides`/`files` patterns derived from a real plugin preset;
- the command needed to run the example;
- unsupported rules or features, especially type-aware rules and custom formats;
- a link to Oxlint's current JS-plugin documentation.

Do not say a plugin is simply “Oxlint compatible” when support is partial. If nothing works, add an `Oxlint compatibility` limitation section explaining the observed error, why it occurs, whether the plugin can fix it, and what users should do instead. If the result depends on an alpha or experimental API, say so without promising semver stability.

## Report The Result

Finish with:

- exact ESLint, Oxlint, Node, and plugin versions tested;
- build path and packed-package path tested;
- compatible, partial, and unsupported rule groups;
- commands and representative diagnostics proving execution;
- fixes, tests, CI wiring, and README changes made;
- upstream issues or plugin-side follow-ups still needed;
- validation gates run and anything skipped.

Distinguish verified facts from inferences and recommendations.
