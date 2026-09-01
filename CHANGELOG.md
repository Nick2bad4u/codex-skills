<!-- markdownlint-disable -->
<!-- eslint-disable markdown/no-missing-label-refs -->

# 📜 Changelog

## ✨ What's Changed

- <b>Commit Range: ➡️</b> [`v1.4.1...e5c6382`](https://github.com/Nick2bad4u/codex-skills/compare/v1.4.1...e5c6382f82967e888ab305dc3df9aee054199e06 "View full commit range on GitHub")

### 🛠️ Bug Fixes

- [`967768a`](https://github.com/Nick2bad4u/codex-skills/commit/967768af583968cdaaefad31e7c7c677b5a7ad38 "Diff: 3 files, +412 | -315") — _(sonar)_ Refactor auditor quality findings&nbsp;<sub><em>(3&nbsp;files,&nbsp;+412,&nbsp;-315)</em></sub>
  - ♻️ [refactor] Decompose package-owner, strict-Python, and SchemaStore validation branches into smaller typed helpers.
  - 🧹 [chore] Replace repeated manifest, lockfile, script, cache, and schema literals with named domain constants.
  - ✅ [fix] Simplify parser and capability decisions without changing the auditors' fail-closed validation contracts.

- [`3ad26d0`](https://github.com/Nick2bad4u/codex-skills/commit/3ad26d0d736f7c0e7955b8cc5b13a9fc09dd0416 "Diff: 13 files, +8104 | -525") — _(auditors)_ Harden repository analysis boundaries&nbsp;<sub><em>(13&nbsp;files,&nbsp;+8104,&nbsp;-525)</em></sub>
  - 🔒️ [fix] Constrain repository discovery, path resolution, subprocess execution, and report parsing to explicit trusted boundaries.
  - 🧭 [fix] Make dependency, strict-Python, and SchemaStore audits deterministic across malformed, incomplete, and nested repository inputs.
  - 🧪 [test] Add dedicated adversarial suites for traversal, symlink, subprocess, parser, and configuration edge cases.
  - 📝 [docs] Document the stricter audit contracts and validation behavior.

- [`5ccfa70`](https://github.com/Nick2bad4u/codex-skills/commit/5ccfa7044132f7654c1ab48b1fd0e1289ef76e9e "Diff: 39 files, +14866 | -826") — _(management)_ Harden API helper boundaries&nbsp;<sub><em>(39&nbsp;files,&nbsp;+14866,&nbsp;-826)</em></sub>
  - 🔒️ [fix] Enforce approved origins, normalized paths, bounded pagination, credential redaction, and explicit mutation confirmation across the management helpers.
  - 🔁 [fix] Limit automatic retries to safe reads while preserving one-shot semantics for state-changing requests.
  - 🧪 [test] Add adversarial transport, pagination, path, redaction, and confirmation coverage for every affected service.
  - 📝 [docs] Align skill procedures and API references with the hardened command behavior.

### 📝 Documentation

- [`464afa5`](https://github.com/Nick2bad4u/codex-skills/commit/464afa53accab138cc5cccf327c8159022ad3f7c "Diff: 1 file, +761 | -4") — _(changelog)_ Regenerate complete release history&nbsp;<sub><em>(1&nbsp;file,&nbsp;+761,&nbsp;-4)</em></sub>
  - 📝 [docs] Preserve the full git-cliff history and add the complete post-v1.4.1 candidate range for the hardened helpers, auditors, package surface, and release workflow.

### 🎨 Styling

- [`6f577cd`](https://github.com/Nick2bad4u/codex-skills/commit/6f577cd35caf01ef7c069e9cfbc62e0f5b7055d1 "Diff: 1 file, +18 | -18") — _(changelog)_ Format generated tables&nbsp;<sub><em>(1&nbsp;file,&nbsp;+18,&nbsp;-18)</em></sub>
  - 🎨 [style] Apply the repository Prettier rules to two historical Dependabot tables without changing release content.

### 🧪 Testing

- [`8523cb6`](https://github.com/Nick2bad4u/codex-skills/commit/8523cb6ae0d39c8a4f8e49c42409b0176fc17b0a "Diff: 7 files, +390 | -232") — _(sonar)_ Isolate exception assertions&nbsp;<sub><em>(7&nbsp;files,&nbsp;+390,&nbsp;-232)</em></sub>
  - 🧪 [test] Hoist plans, contexts, payloads, and runtimes out of pytest.raises blocks so each assertion exercises one exception-producing call.
  - ✅ [test] Keep the original error types, match expressions, retry boundaries, and safety scenarios intact across all affected management suites.
  - 🏷️ [test] Add the narrow JSON value annotation required for the non-finite Tag Manager payload.

### 🧹 Chores

- [`60a91c9`](https://github.com/Nick2bad4u/codex-skills/commit/60a91c9c72c578ee0fad890fc50ae75924de5957 "Diff: 7 files, +521 | -509") — 🧹 [chore] Clean up unused code and comments&nbsp;<sub><em>(7&nbsp;files,&nbsp;+521,&nbsp;-509)</em></sub>
  - Removed redundant functions and variables to streamline the codebase.
- Updated comments for clarity and removed outdated ones.
- Ensured consistent formatting across files for better readability.

### 👷 CI/CD

- [`ec6a59e`](https://github.com/Nick2bad4u/codex-skills/commit/ec6a59ec23c0f33a659c8edf9bb33ffa535533ab "Diff: 1 file, +123 | -30") — _(release)_ Make publication fail closed&nbsp;<sub><em>(1&nbsp;file,&nbsp;+123,&nbsp;-30)</em></sub>
  - 🔒️ [ci] Serialize release runs and reject malformed, unreachable, or previously used version targets before mutation.
  - 📦 [ci] Build the GitHub bundle from the validated npm tarball so both release channels expose the same files.
  - 📝 [ci] Regenerate the full changelog on the versioned checkout before package validation.
  - 🚀 [ci] Publish npm and create the GitHub release exactly once without skip, edit, or clobber fallbacks.

### 🔧 Build System

- [`7c0b00a`](https://github.com/Nick2bad4u/codex-skills/commit/7c0b00ac02d82d1b61e9346f2d02d13a72bf0540 "Diff: 4 files, +2660 | -5376") — _(package)_ Refresh tooling and export surfaces&nbsp;<sub><em>(4&nbsp;files,&nbsp;+2660,&nbsp;-5376)</em></sub>
  - 📦 [build] Export only the typed root, package metadata, schemas, and packaged skill resources while removing stale file-list entries.
  - ⬆️ [build] Refresh the reviewed development toolchain and lockfile without adding runtime dependencies.
  - 🔎 [build] Tighten skill-surface auditing around the intended package contract.
  - 📝 [docs] Synchronize the README with all 29 repository skills.

### 🛡️ Security

- [`e5c6382`](https://github.com/Nick2bad4u/codex-skills/commit/e5c6382f82967e888ab305dc3df9aee054199e06 "Diff: 1 file, +1 | -1") — _(release)_ Run pinned Prettier binary&nbsp;<sub><em>(1&nbsp;file,&nbsp;+1,&nbsp;-1)</em></sub>
  - 🔒️ [security] Invoke the lockfile-installed Prettier CLI directly during release changelog formatting.
  - 👷 [ci] Avoid npx package resolution in the publish job while preserving the existing formatter version and arguments.
  - ✅ [ci] Keep the workflow valid under the repository's native actionlint gate.

- [`4b48489`](https://github.com/Nick2bad4u/codex-skills/commit/4b48489dfe6dcd1aa6f0d210cf1423fa445b11ce "Diff: 7 files, +828 | -424") — 🐛 [fix] (sonar) Refactor management quality findings&nbsp;<sub><em>(7&nbsp;files,&nbsp;+828,&nbsp;-424)</em></sub>
  - ♻️ [refactor] Split complex request, retry, pagination, redaction, and bounded-response paths into focused typed helpers.
  - 🔒️ [security] Preserve fail-closed URL, credential, JSON-shape, response-size, and indeterminate-write protections across all seven management clients.
  - 🎨 [style] Centralize repeated labels, patterns, and limits while simplifying regular expressions and exception handling flagged by Sonar.

## ✨ What's Changed in v1.4.1

- <b>Commit Range: ➡️</b> [`v1.4.0...v1.4.1`](https://github.com/Nick2bad4u/codex-skills/compare/v1.4.0...v1.4.1 "View full commit range on GitHub")

### 🛠️ Bug Fixes

- [`d50bd32`](https://github.com/Nick2bad4u/codex-skills/commit/d50bd32dc9ca5b5eeb3faac1bc468160e7ebf257 "Diff: 3 files, +72 | -41") — _(sonar)_ Resolve Python quality gate findings&nbsp;<sub><em>(3&nbsp;files,&nbsp;+72,&nbsp;-41)</em></sub>
  - 🐛 [fix] Replace backtracking-prone Codacy OpenAPI patterns with linear anchored expressions and validate dynamic argparse list values at a typed boundary.
  - 🚜 [refactor] Extract Codacy response decoding, centralize JSON and redaction literals, reduce request complexity, and derive the request handler exit code from the HTTP status.
  - 🔒️ [fix] Reuse a StepSecurity redaction constant across sensitive headers and payload values.
  - 🧪 [test] Isolate fixture construction from exception assertions and split transport contract coverage into focused tests.

- [`721305b`](https://github.com/Nick2bad4u/codex-skills/commit/721305bed87788cf4f8fc0ebb0b4514274dcb179 "Diff: 15 files, +909 | -67") — _(python)_ Harden management transports and discovery&nbsp;<sub><em>(15&nbsp;files,&nbsp;+909,&nbsp;-67)</em></sub>
  - 🐛 [fix] Close urllib HTTP error responses across the Codacy, Socket, Snyk, WakaTime, StepSecurity, UptimeRobot, and GTM helpers, including retry and specification-download paths.
  - 🔒️ [fix] Redact known StepSecurity request credentials when an API echoes them in success or error payload text.
  - 🐛 [fix] Discover nested untracked files in the dependency-update and SchemaStore auditors.
  - 🧪 [test] Add transport-boundary, terminal-error, pagination, retry, redaction, and untracked-file regression coverage; raise local and Codecov thresholds to 80 percent.
  - 🔧 [chore] Add strict Ruff, mypy, Pyright, pytest, and local-interpreter VS Code settings.

### 🧪 Testing

- [`1a1211e`](https://github.com/Nick2bad4u/codex-skills/commit/1a1211e08bd1fb33e7a77e8a2b355582acc0c583 "Diff: 1 file, +47 | -0") — _(codecov)_ Cover Codacy transport boundaries&nbsp;<sub><em>(1&nbsp;file,&nbsp;+47,&nbsp;-0)</em></sub>
  - 🧪 [test] Exercise invalid argparse list values, token redaction, empty and malformed response decoding, and JSON request serialization.
  - 📈 [test] Raise the Sonar follow-up commit's measured changed-line coverage from 72.97 percent locally to 97.30 percent without weakening the 80 percent patch gate.

> [!NOTE]
> **Release comparison**: https://github.com/Nick2bad4u/codex-skills/compare/v1.4.0...v1.4.1

## ✨ What's Changed in v1.4.0

- <b>Commit Range: ➡️</b> [`v1.3.0...v1.4.0`](https://github.com/Nick2bad4u/codex-skills/compare/v1.3.0...v1.4.0 "View full commit range on GitHub")

### ✨ Features

- [`556cf52`](https://github.com/Nick2bad4u/codex-skills/commit/556cf5218100210034c8e77c503967ac794d88fb "Diff: 20 files, +3885 | -11") — ✨ [feat] Add UptimeRobot and GTM management skills&nbsp;<sub><em>(20&nbsp;files,&nbsp;+3885,&nbsp;-11)</em></sub>
  - ✨ [feat] Add credential-safe UptimeRobot API v3, CLI, MCP, dashboard, reporting, and mutation workflows with a deterministic helper and official reference guides.
  - ✨ [feat] Add Discovery-driven Google Tag Manager v2 workflows for workspaces, concurrency, consent, permissions, preview, versioning, and publishing.
  - 🧪 [test] Register both skill contracts and cover authentication boundaries, operation discovery, request validation, confirmation gates, retries, pagination, and recursive redaction.
  - 🧹 [chore] Generate synchronized metadata and icons, declare the official UptimeRobot MCP dependency, preserve executable modes, and ignore local skillcheck history.

### 🛠️ Bug Fixes

- [`d973a1f`](https://github.com/Nick2bad4u/codex-skills/commit/d973a1f554977e108955b71a4448b05623fb1c0c "Diff: 3 files, +392 | -230") — _(sonar)_ Refactor new management helpers&nbsp;<sub><em>(3&nbsp;files,&nbsp;+392,&nbsp;-230)</em></sub>
  - 🐛 [fix] Replace complex credential and YAML regexes with deterministic normalization and parsing while preserving origin, path, and redaction safeguards.
  - 🚜 [refactor] Split UptimeRobot and GTM request planning, credential checks, pagination, and result rendering into focused helpers without changing CLI exit behavior.
  - 🧪 [test] Isolate the single throwing invocation in exception assertions and retain coverage for pagination, missing credentials, and high-impact confirmations.

- [`7623db4`](https://github.com/Nick2bad4u/codex-skills/commit/7623db4cca4c8e2b4addeb2a46bc129a12f820ff "Diff: 1 file, +1 | -0") — _(codecov)_ Bypass millisecond report expiry bug&nbsp;<sub><em>(1&nbsp;file,&nbsp;+1,&nbsp;-0)</em></sub>
  - 🐛 [fix] Disable Codecov's report-age filter after its GraphQL upload diagnostics confirmed current coverage.py reports were rejected as REPORT_EXPIRED.
  - 🦺 [test] Preserve YAML semantics with an explicit boolean and validate the resulting configuration against Codecov's live validator.

- [`ec071b0`](https://github.com/Nick2bad4u/codex-skills/commit/ec071b0cdb4028b48b02e4bf8f278fd1011537ce "Diff: 7 files, +544 | -20") — _(codecov)_ Emit repository-relative coverage reports&nbsp;<sub><em>(7&nbsp;files,&nbsp;+544,&nbsp;-20)</em></sub>
  - 🐛 [fix] Replace ambiguous multi-root coverage sources with a relative helper include pattern and remove the stale two-directory Codecov flag filter.
  - 🦺 [test] Validate generated Cobertura filenames against every packaged Python helper before uploads can proceed.
  - 🧪 [test] Add explicit routing, workflow, metadata, asset, resource, coverage, and entrypoint contracts for all 27 skills.
  - 🧹 [chore] Restore the StepSecurity helper copyright header required by the locked Python lint gate.
  - 📝 [docs] Document the all-skill and deep Python test layers.

### 🛡️ Security

- [`21e94f7`](https://github.com/Nick2bad4u/codex-skills/commit/21e94f7a88abba949ce71811bf55a83b5e01fbb5 "Diff: 2 files, +9 | -13") — _(coverage)_ Pin report validator input path&nbsp;<sub><em>(2&nbsp;files,&nbsp;+9,&nbsp;-13)</em></sub>
  - 🔒️ [fix] Remove the CLI-controlled filesystem path and bind Codecov validation to the repository's generated coverage/python/coverage.xml report.
  - 🧪 [test] Re-run all 98 Python tests and verify all nine report paths after constraining the input.

> [!NOTE]
> **Release comparison**: https://github.com/Nick2bad4u/codex-skills/compare/v1.3.0...v1.4.0

## ✨ What's Changed in v1.3.0

- <b>Commit Range: ➡️</b> [`v1.2.0...v1.3.0`](https://github.com/Nick2bad4u/codex-skills/compare/v1.2.0...v1.3.0 "View full commit range on GitHub")

### ✨ Features

- [`8f3f6d9`](https://github.com/Nick2bad4u/codex-skills/commit/8f3f6d9dbdbaf798a690b75470e935bafa0043d6 "Diff: 32 files, +5707 | -0") — _(skills)_ Add four service management skills&nbsp;<sub><em>(32&nbsp;files,&nbsp;+5707,&nbsp;-0)</em></sub>
  - ✨ [feat] Add operational Socket, Snyk, WakaTime, and StepSecurity workflows with API references, command guides, generated metadata, and icons.
  - 🔒️ [fix] Constrain helper authentication, origins, redirects, pagination, redaction, and mutation previews while preserving executable Git modes.
  - 🧪 [test] Cover command behavior and lower-level safety guards with strict Python typing and aggregate coverage integration.
  - 🔧 [chore] Register the new metadata surfaces and Python coverage sources for repository validation and packaging.

### 🛠️ Bug Fixes

- [`6356c77`](https://github.com/Nick2bad4u/codex-skills/commit/6356c773825085f597aaad5cb3711daba505ae0c "Diff: 5 files, +191 | -116") — _(sonar)_ Resolve new skill quality findings&nbsp;<sub><em>(5&nbsp;files,&nbsp;+191,&nbsp;-116)</em></sub>
  - 🚜 [refactor] Decompose OpenAPI parsing and StepSecurity retry, redirect, and error handling while preserving origin and credential boundaries.
  - 🐛 [fix] Replace noisy environment regexes, centralize repeated type and media literals, and derive command exits from response status.
  - 🧪 [test] Isolate exception-producing calls so failure assertions remain precise and Sonar-compliant.

> [!NOTE]
> **Release comparison**: https://github.com/Nick2bad4u/codex-skills/compare/v1.2.0...v1.3.0

## ✨ What's Changed in v1.2.0

- <b>Commit Range: ➡️</b> [`v1.1.1...v1.2.0`](https://github.com/Nick2bad4u/codex-skills/compare/v1.1.1...v1.2.0 "View full commit range on GitHub")

### 🛠️ Bug Fixes

- [`ce90b61`](https://github.com/Nick2bad4u/codex-skills/commit/ce90b614b660f43cc74994a28d7601d484d88c4e "Diff: 1 file, +0 | -0") — _(codacy)_ Mark helper script executable&nbsp;<sub><em>(1&nbsp;file,&nbsp;+0,&nbsp;-0)</em></sub>
  - 🐛 [fix] Align the Codacy Python helper mode with every existing shebang-bearing skill script.
- Satisfy Ruff EXE001 on Linux so CI can continue through coverage generation and Codecov upload.

### 🛡️ Security

- [`a5a38a4`](https://github.com/Nick2bad4u/codex-skills/commit/a5a38a4cc217aeafbac47e0aec022c597496dd63 "Diff: 10 files, +2111 | -0") — ✨ [feat] (codacy) Add secure Codacy management skill&nbsp;<sub><em>(10&nbsp;files,&nbsp;+2111,&nbsp;-0)</em></sub>
  - ✨ [feat] Add CLI-first workflows for repositories, issues, security findings, pull requests, coverage, tools, patterns, gates, coding standards, and self-hosted instances.
- Include current API, authentication, pagination, rate-limit, configuration-precedence, and command references.
  - 🔒️ [fix] Add an HTTPS-only OpenAPI helper with origin locking, redirect refusal, token redaction, mutation previews, bounded retries, and cursor pagination.
- Reject URL credentials, traversal paths, fragments, embedded query secrets, unsafe token handling, and conflicting request inputs.
  - 🧪 [test] Cover repository inference, operation discovery, request previews, redaction, authority checks, malformed input, and URL boundary failures.
- Add the helper to strict Python coverage and keep aggregate coverage above the repository threshold.
  - 🍱 [chore] Register generated Codacy metadata and icon assets for the packaged skill surface.

> [!NOTE]
> **Release comparison**: https://github.com/Nick2bad4u/codex-skills/compare/v1.1.1...v1.2.0

## ✨ What's Changed in v1.1.1

- <b>Commit Range: ➡️</b> [`v1.1.0...v1.1.1`](https://github.com/Nick2bad4u/codex-skills/compare/v1.1.0...v1.1.1 "View full commit range on GitHub")

### 🛠️ Bug Fixes

- [`580aa76`](https://github.com/Nick2bad4u/codex-skills/commit/580aa76b63423cff8a74fa290222a7be0e8d5862 "Diff: 5 files, +35 | -9") — _(skills)_ Scope vulnerability gates by exposure&nbsp;<sub><em>(5&nbsp;files,&nbsp;+35,&nbsp;-9)</em></sub>
  - 🐛 [fix] Require zero unresolved findings in shipped production graphs while triaging development-only and consumer-supplied peer findings by risk.
  - 🔒️ [fix] Keep malware, actionable high or critical findings, and credible production, build, CI, release, or artifact exposure as blockers.
  - 📝 [docs] Document npm production and full-tree audit comparison, peer-contract handling, residual-risk reporting, and stricter repository-gate boundaries.

### 🛡️ Security

- [`fbe03c6`](https://github.com/Nick2bad4u/codex-skills/commit/fbe03c68e378309856eb75ac803de371df0c494c "Diff: 1 file, +6 | -6") — _(deps)_ Refresh vulnerable dev transitive packages&nbsp;<sub><em>(1&nbsp;file,&nbsp;+6,&nbsp;-6)</em></sub>
  - 🔒️ [fix] Update js-yaml from 4.3.0 to 4.3.1 to resolve GHSA-5p4m-2wfm-xmqj across the development tooling graph.
  - 🔒️ [fix] Update nanoid from 3.3.16 to 3.3.18 to resolve GHSA-2v37-7h3g-55p8 without changing direct dependency ranges.

> [!NOTE]
> **Release comparison**: https://github.com/Nick2bad4u/codex-skills/compare/v1.1.0...v1.1.1

## ✨ What's Changed in v1.1.0

- <b>Commit Range: ➡️</b> [`v1.0.1...v1.1.0`](https://github.com/Nick2bad4u/codex-skills/compare/v1.0.1...v1.1.0 "View full commit range on GitHub")

### ✨ Features

- [`28f2bf3`](https://github.com/Nick2bad4u/codex-skills/commit/28f2bf3873015791609bb98f847384e490813b2e "Diff: 7 files, +263 | -0") — _(skills)_ Add Oxlint compatibility verifier&nbsp;<sub><em>(7&nbsp;files,&nbsp;+263,&nbsp;-0)</em></sub>
  - ✨ [feat] Add an explicit-only workflow that proves ESLint plugin behavior against built and packed artifacts, classifies type-aware and API limitations, and requires honest README and CI coverage.
  - 🦺 [chore] Register validated metadata and generated icon assets while enforcing disabled implicit invocation across sync and validation.
  - 📝 [docs] Catalog the new skill and harden temporary compatibility probes against config overwrites and unsafe cleanup.

> [!NOTE]
> **Release comparison**: https://github.com/Nick2bad4u/codex-skills/compare/v1.0.1...v1.1.0

## ✨ What's Changed in v1.0.1

- <b>Commit Range: ➡️</b> [`v1.0.0...v1.0.1`](https://github.com/Nick2bad4u/codex-skills/compare/v1.0.0...v1.0.1 "View full commit range on GitHub")

### 🛠️ Bug Fixes

- [`b18fb18`](https://github.com/Nick2bad4u/codex-skills/commit/b18fb18490307d16814a9441598bd2d021803025 "Diff: 1 file, +3 | -1") — _(vsicons)_ Offer to apply recommended associations&nbsp;<sub><em>(1&nbsp;file,&nbsp;+3,&nbsp;-1)</em></sub>
  - Clarify that recommendation-only runs should offer to make the approved VS Code settings changes in a separately authorized follow-up.
  - Preserve the explicit authorization boundary so the offer itself never permits editing user settings.

> [!NOTE]
> **Release comparison**: https://github.com/Nick2bad4u/codex-skills/compare/v1.0.0...v1.0.1

## ✨ What's Changed in v1.0.0

- <b>Commit Range: ➡️</b> [`v0.10.0...v1.0.0`](https://github.com/Nick2bad4u/codex-skills/compare/v0.10.0...v1.0.0 "View full commit range on GitHub")

### ✨ Features

- [`7b7b5de`](https://github.com/Nick2bad4u/codex-skills/commit/7b7b5de2181eb4fff0f25301dd02fefd30b55eee "Diff: 1 file, +2 | -2") — _(npm-12-migration)_ Offer audited fixes&nbsp;<sub><em>(1&nbsp;file,&nbsp;+2,&nbsp;-2)</em></sub>
  - ✨ [feat] Offer to apply audit recommendations after the user authorizes implementation.
  - 🔒️ [fix] Preserve the read-only boundary by clarifying that the offer itself grants no edit permission.

### 📦 Dependencies

- [`291ef27`](https://github.com/Nick2bad4u/codex-skills/commit/291ef27a8779e12264eac30d61364ecd0b11dd54 "Diff: 1 file, +6 | -6") — ⬆️ [build] Update npm_and_yarn dependencies&nbsp;<sub><em>(1&nbsp;file,&nbsp;+6,&nbsp;-6)</em></sub>

### 🛡️ Security

- [`e705f11`](https://github.com/Nick2bad4u/codex-skills/commit/e705f11540b3f1f0425ac87b79d615ff79b248b3 "Diff: 1 file, +7 | -7") — 🔒️ [fix] Refresh vulnerable transitive dependencies&nbsp;<sub><em>(1&nbsp;file,&nbsp;+7,&nbsp;-7)</em></sub>
  - 🔒️ [fix] Upgrade fast-uri to 3.1.5 and postcss to 8.5.25 in the npm lockfile.
  - 🧪 [test] Confirm npm audit reports zero vulnerabilities after the targeted refresh.

> [!NOTE]
> **Release comparison**: https://github.com/Nick2bad4u/codex-skills/compare/v0.10.0...v1.0.0

## ✨ What's Changed in v0.10.0

- <b>Commit Range: ➡️</b> [`v0.9.1...v0.10.0`](https://github.com/Nick2bad4u/codex-skills/compare/v0.9.1...v0.10.0 "View full commit range on GitHub")

### ✨ Features

- [`b0c0990`](https://github.com/Nick2bad4u/codex-skills/commit/b0c0990fc1257d124ba54d584cd52454b475debe "Diff: 1 file, +24 | -10") — ✨ [feat] Prevent duplicate VS Icons associations&nbsp;<sub><em>(1&nbsp;file,&nbsp;+24,&nbsp;-10)</em></sub>
  - Require inspecting active workspace and user settings before recommending associations. Report whether to omit, append, or add each target and verify exact-once placement across file and folder arrays.

- [`d272e7e`](https://github.com/Nick2bad4u/codex-skills/commit/d272e7e50249f95a47c3b246decfc1dfcce09f9b "Diff: 7 files, +607 | -0") — ✨ [feat] Add PowerShell development skill&nbsp;<sub><em>(7&nbsp;files,&nbsp;+607,&nbsp;-0)</em></sub>
  - ✨ [feat] Add a reusable PowerShell engineering workflow covering command contracts, mutation safety, native tools, modules, profiles, and compatibility.
  - 🧪 [test] Document behavior-focused Pester 5 and 6 practices, mocking boundaries, WhatIf coverage, cleanup, and cross-version execution.
  - 🍱 [chore] Generate aligned OpenAI metadata and branded icon assets through the repository metadata source.

- [`de7775f`](https://github.com/Nick2bad4u/codex-skills/commit/de7775feeb94c0af3e2c01a834603517e0f1f4ba "Diff: 22 files, +22 | -22") — ✨ [feat] Update schema references in OpenAI YAML files&nbsp;<sub><em>(22&nbsp;files,&nbsp;+22,&nbsp;-22)</em></sub>
  - Changed schema URL from json.schemastore.org to schemastore.org for consistency across multiple agent skill YAML files.
- Updated the schema reference in sync-skill-metadata.mjs and validate-skills.mjs to reflect the new URL.

- [`6c11d39`](https://github.com/Nick2bad4u/codex-skills/commit/6c11d39bba290082e3e02148c5687135fa30b83b "Diff: 1 file, +101 | -10") — ✨ [feat] Enhance PR labeler configuration&nbsp;<sub><em>(1&nbsp;file,&nbsp;+101,&nbsp;-10)</em></sub>
  - Add new label rules for breaking changes, bug fixes, builds, and enhancements
- Update file patterns for CI/CD, configuration, documentation, and testing
- Improve clarity and organization of label definitions

### 🛠️ Bug Fixes

- [`e743cd0`](https://github.com/Nick2bad4u/codex-skills/commit/e743cd0f2c987686d2e717b2b3c502544c083022 "Diff: 2 files, +6 | -4") — 💚 [fix] Isolate npm 12 workflow bootstrap&nbsp;<sub><em>(2&nbsp;files,&nbsp;+6,&nbsp;-4)</em></sub>
  - 💚 [fix] Install npm 12 under RUNNER_TEMP instead of replacing the runner-bundled npm in place, preventing partial self-upgrades and missing internal modules.
  - 👷 [build] Export the isolated npm binary through GITHUB_PATH for both CI validation and trusted-publishing jobs.

### 🔧 Build System

- [`766e65c`](https://github.com/Nick2bad4u/codex-skills/commit/766e65c4ad9a7769b38369eb48a100d6cce52440 "Diff: 9 files, +443 | -1183") — 👷 [build] Migrate repository to npm 12&nbsp;<sub><em>(9&nbsp;files,&nbsp;+443,&nbsp;-1183)</em></sub>
  - 🔧 [chore] Enforce project-scoped lifecycle-script allowlisting with exact functional package approvals and strict npm configuration.
  - 👷 [build] Align local Node pins and CI/release jobs on npm 12.0.2, allowing audited install scripts during clean installs.
  - ⬆️ [build] Refresh shared lint/config dependencies and regenerate the npm 12 lockfile without forced installs.
  - 🔒️ [fix] Override vulnerable frontmatter-schema transitive dependencies and resolve the audited tree to zero known vulnerabilities.
  - 🚨 [fix] Apply the updated ESLint condition ordering required by the refreshed shared config.

### 🛡️ Security

- [`303a743`](https://github.com/Nick2bad4u/codex-skills/commit/303a7434fe8edf3e600c9d484bbd51c0f754fef1 "Diff: 5 files, +895 | -776") — _(deps)_ [dependency] Update dependency group&nbsp;<sub><em>(5&nbsp;files,&nbsp;+895,&nbsp;-776)</em></sub>
  - Bumps the dependabot-all group with 6 updates:
  - | Package                                                                       | From     | To       |
    | ----------------------------------------------------------------------------- | -------- | -------- |
    | [actions/checkout](https://github.com/actions/checkout)                       | `7.0.0`  | `7.0.1`  |
    | [actions/setup-node](https://github.com/actions/setup-node)                   | `6.4.0`  | `7.0.0`  |
    | [actions/setup-python](https://github.com/actions/setup-python)               | `6.3.0`  | `7.0.0`  |
    | [github/codeql-action/init](https://github.com/github/codeql-action)          | `4.36.2` | `4.37.3` |
    | [github/codeql-action/analyze](https://github.com/github/codeql-action)       | `4.36.2` | `4.37.3` |
    | [step-security/harden-runner](https://github.com/step-security/harden-runner) | `2.19.4` | `2.20.0` |
  - Updates `actions/checkout` from 7.0.0 to 7.0.1
- [Release notes](https://github.com/actions/checkout/releases)
- [Changelog](https://github.com/actions/checkout/blob/main/CHANGELOG.md)
- [Commits](https://github.com/actions/checkout/compare/9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0...3d3c42e5aac5ba805825da76410c181273ba90b1)
  - Updates `actions/setup-node` from 6.4.0 to 7.0.0
- [Release notes](https://github.com/actions/setup-node/releases)
- [Commits](https://github.com/actions/setup-node/compare/48b55a011bda9f5d6aeb4c2d9c7362e8dae4041e...820762786026740c76f36085b0efc47a31fe5020)
  - Updates `actions/setup-python` from 6.3.0 to 7.0.0
- [Release notes](https://github.com/actions/setup-python/releases)
- [Commits](https://github.com/actions/setup-python/compare/ece7cb06caefa5fff74198d8649806c4678c61a1...5fda3b95a4ea91299a34e894583c3862153e4b97)
  - Updates `github/codeql-action/init` from 4.36.2 to 4.37.3
- [Release notes](https://github.com/github/codeql-action/releases)
- [Changelog](https://github.com/github/codeql-action/blob/main/CHANGELOG.md)
- [Commits](https://github.com/github/codeql-action/compare/8aad20d150bbac5944a9f9d289da16a4b0d87c1e...e4fba868fa4b1b91e1fdab776edc8cfbe6e9fb81)
  - Updates `github/codeql-action/analyze` from 4.36.2 to 4.37.3
- [Release notes](https://github.com/github/codeql-action/releases)
- [Changelog](https://github.com/github/codeql-action/blob/main/CHANGELOG.md)
- [Commits](https://github.com/github/codeql-action/compare/8aad20d150bbac5944a9f9d289da16a4b0d87c1e...e4fba868fa4b1b91e1fdab776edc8cfbe6e9fb81)
  - Updates `step-security/harden-runner` from 2.19.4 to 2.20.0
- [Release notes](https://github.com/step-security/harden-runner/releases)
- [Commits](https://github.com/step-security/harden-runner/compare/9af89fc71515a100421586dfdb3dc9c984fbf411...bf7454d06d71f1098171f2acdf0cd4708d7b5920)
  [dependabot][dev][all](deps-dev): [dependency] Update dependency group
  - Bumps the dependabot-all group with 9 updates:
  - | Package                                                                                | From      | To        |
    | -------------------------------------------------------------------------------------- | --------- | --------- |
    | [eslint](https://github.com/eslint/eslint)                                             | `10.7.0`  | `10.8.0`  |
    | [eslint-config-nick2bad4u](https://github.com/Nick2bad4u/eslint-config-nick2bad4u)     | `5.0.0`   | `11.0.1`  |
    | [gitcliff-config-nick2bad4u](https://github.com/Nick2bad4u/gitcliff-config-nick2bad4u) | `1.3.0`   | `1.4.0`   |
    | [jscpd](https://github.com/kucherenko/jscpd/tree/HEAD/rust/jscpd)                      | `5.0.12`  | `5.0.14`  |
    | [ncu-config-nick2bad4u](https://github.com/Nick2bad4u/ncu-config-nick2bad4u)           | `0.2.0`   | `0.2.1`   |
    | [npm-check-updates](https://github.com/raineorshine/npm-check-updates)                 | `22.2.9`  | `23.0.0`  |
    | [prettier](https://github.com/prettier/prettier)                                       | `3.9.5`   | `3.9.6`   |
    | [secretlint](https://github.com/secretlint/secretlint)                                 | `13.0.2`  | `13.0.4`  |
    | [stylelint](https://github.com/stylelint/stylelint)                                    | `17.14.0` | `17.14.1` |
  - Updates `eslint` from 10.7.0 to 10.8.0
- [Release notes](https://github.com/eslint/eslint/releases)
- [Commits](https://github.com/eslint/eslint/compare/v10.7.0...v10.8.0)
  - Updates `eslint-config-nick2bad4u` from 5.0.0 to 11.0.1
- [Release notes](https://github.com/Nick2bad4u/eslint-config-nick2bad4u/releases)
- [Changelog](https://github.com/Nick2bad4u/eslint-config-nick2bad4u/blob/main/CHANGELOG.md)
- [Commits](https://github.com/Nick2bad4u/eslint-config-nick2bad4u/compare/v5.0.0...v11.0.1)
  - Updates `gitcliff-config-nick2bad4u` from 1.3.0 to 1.4.0
- [Release notes](https://github.com/Nick2bad4u/gitcliff-config-nick2bad4u/releases)
- [Commits](https://github.com/Nick2bad4u/gitcliff-config-nick2bad4u/compare/v1.3.0...v1.4.0)
  - Updates `jscpd` from 5.0.12 to 5.0.14
- [Release notes](https://github.com/kucherenko/jscpd/releases)
- [Changelog](https://github.com/kucherenko/jscpd/blob/master/CHANGELOG.md)
- [Commits](https://github.com/kucherenko/jscpd/commits/v5.0.14/rust/jscpd)
  - Updates `ncu-config-nick2bad4u` from 0.2.0 to 0.2.1
- [Release notes](https://github.com/Nick2bad4u/ncu-config-nick2bad4u/releases)
- [Changelog](https://github.com/Nick2bad4u/ncu-config-nick2bad4u/blob/main/CHANGELOG.md)
- [Commits](https://github.com/Nick2bad4u/ncu-config-nick2bad4u/compare/v0.2.0...v0.2.1)
  - Updates `npm-check-updates` from 22.2.9 to 23.0.0
- [Release notes](https://github.com/raineorshine/npm-check-updates/releases)
- [Changelog](https://github.com/raineorshine/npm-check-updates/blob/main/CHANGELOG.md)
- [Commits](https://github.com/raineorshine/npm-check-updates/compare/v22.2.9...v23.0.0)
  - Updates `prettier` from 3.9.5 to 3.9.6
- [Release notes](https://github.com/prettier/prettier/releases)
- [Changelog](https://github.com/prettier/prettier/blob/main/CHANGELOG.md)
- [Commits](https://github.com/prettier/prettier/compare/3.9.5...3.9.6)
  - Updates `secretlint` from 13.0.2 to 13.0.4
- [Release notes](https://github.com/secretlint/secretlint/releases)
- [Commits](https://github.com/secretlint/secretlint/compare/v13.0.2...v13.0.4)
  - Updates `stylelint` from 17.14.0 to 17.14.1
- [Release notes](https://github.com/stylelint/stylelint/releases)
- [Changelog](https://github.com/stylelint/stylelint/blob/main/CHANGELOG.md)
- [Commits](https://github.com/stylelint/stylelint/compare/17.14.0...17.14.1)
  ***

updated-dependencies:

- dependency-name: actions/checkout
  dependency-version: 7.0.1
  dependency-type: direct:production
  update-type: version-update:semver-patch
  dependency-group: dependabot-all
- dependency-name: actions/setup-node
  dependency-version: 7.0.0
  dependency-type: direct:production
  update-type: version-update:semver-major
  dependency-group: dependabot-all
- dependency-name: actions/setup-python
  dependency-version: 7.0.0
  dependency-type: direct:production
  update-type: version-update:semver-major
  dependency-group: dependabot-all
- dependency-name: github/codeql-action/init
  dependency-version: 4.37.3
  dependency-type: direct:production
  update-type: version-update:semver-minor
  dependency-group: dependabot-all
- dependency-name: github/codeql-action/analyze
  dependency-version: 4.37.3
  dependency-type: direct:production
  update-type: version-update:semver-minor
  dependency-group: dependabot-all
- dependency-name: step-security/harden-runner
  dependency-version: 2.20.0
  dependency-type: direct:production
  update-type: version-update:semver-minor
  dependency-group: dependabot-all
- dependency-name: eslint
  dependency-version: 10.8.0
  dependency-type: direct:development
  update-type: version-update:semver-minor
  dependency-group: dependabot-all
- dependency-name: eslint-config-nick2bad4u
  dependency-version: 11.0.1
  dependency-type: direct:development
  update-type: version-update:semver-major
  dependency-group: dependabot-all
- dependency-name: gitcliff-config-nick2bad4u
  dependency-version: 1.4.0
  dependency-type: direct:development
  update-type: version-update:semver-minor
  dependency-group: dependabot-all
- dependency-name: jscpd
  dependency-version: 5.0.14
  dependency-type: direct:development
  update-type: version-update:semver-patch
  dependency-group: dependabot-all
- dependency-name: ncu-config-nick2bad4u
  dependency-version: 0.2.1
  dependency-type: direct:development
  update-type: version-update:semver-patch
  dependency-group: dependabot-all
- dependency-name: npm-check-updates
  dependency-version: 23.0.0
  dependency-type: direct:development
  update-type: version-update:semver-major
  dependency-group: dependabot-all
- dependency-name: prettier
  dependency-version: 3.9.6
  dependency-type: direct:development
  update-type: version-update:semver-patch
  dependency-group: dependabot-all
- dependency-name: secretlint
  dependency-version: 13.0.4
  dependency-type: direct:development
  update-type: version-update:semver-patch
  dependency-group: dependabot-all
- dependency-name: stylelint
  dependency-version: 17.14.1
  dependency-type: direct:development
  update-type: version-update:semver-patch
  dependency-group: dependabot-all
  ...

> [!NOTE]
> **Release comparison**: https://github.com/Nick2bad4u/codex-skills/compare/v0.9.1...v0.10.0

## ✨ What's Changed in v0.9.1

- <b>Commit Range: ➡️</b> [`v0.9.0...v0.9.1`](https://github.com/Nick2bad4u/codex-skills/compare/v0.9.0...v0.9.1 "View full commit range on GitHub")

### 📝 Documentation

- [`8b023c7`](https://github.com/Nick2bad4u/codex-skills/commit/8b023c77122e1e4c468bfde97553f2468b179123 "Diff: 4 files, +57 | -7") — 📝 [docs] Define skill workflow contracts&nbsp;<sub><em>(4&nbsp;files,&nbsp;+57,&nbsp;-7)</em></sub>
  - 📝 [docs] Add explicit input and output contracts to instruction review, GitHub Actions, test quality, and workspace continuation workflows.
  - 🧪 [test] Connect heuristic capability graphs so all 20 skills pass Skillcheck without warnings.

> [!NOTE]
> **Release comparison**: https://github.com/Nick2bad4u/codex-skills/compare/v0.9.0...v0.9.1

## ✨ What's Changed in v0.9.0

- <b>Commit Range: ➡️</b> [`v0.8.0...v0.9.0`](https://github.com/Nick2bad4u/codex-skills/compare/v0.8.0...v0.9.0 "View full commit range on GitHub")

### ✨ Features

- [`d80c82a`](https://github.com/Nick2bad4u/codex-skills/commit/d80c82a9f87f82d3471d8267737e2d29f432869c "Diff: 20 files, +54 | -40") — ✨ [feat] Enable automatic invocation for most skills&nbsp;<sub><em>(20&nbsp;files,&nbsp;+54,&nbsp;-40)</em></sub>
  - ✨ [feat] Emit explicit allow_implicit_invocation values for every generated skill metadata file, with only VSIcons association recommendations and workspace continuation disabled.
  - 🧪 [test] Enforce the two-skill implicit-invocation denylist during repository validation.

### 🚜 Refactor

- [`9e890cc`](https://github.com/Nick2bad4u/codex-skills/commit/9e890cc9aee45e755469889cfb826af74b723aa3 "Diff: 1 file, +8 | -16") — 🚜 [refactor] Centralize implicit invocation denylist&nbsp;<sub><em>(1&nbsp;file,&nbsp;+8,&nbsp;-16)</em></sub>
  - 🚜 [refactor] Derive every generated skill policy from the two-skill denylist, removing scattered per-skill overrides and obsolete policy typing.

> [!NOTE]
> **Release comparison**: https://github.com/Nick2bad4u/codex-skills/compare/v0.8.0...v0.9.0

## ✨ What's Changed in v0.8.0

- <b>Commit Range: ➡️</b> [`v0.7.1...v0.8.0`](https://github.com/Nick2bad4u/codex-skills/compare/v0.7.1...v0.8.0 "View full commit range on GitHub")

### ✨ Features

- [`c4b922d`](https://github.com/Nick2bad4u/codex-skills/commit/c4b922d4f198b9f87bcf23f262fb8dfe24b04db7 "Diff: 9 files, +524 | -0") — ✨ [feat] Add npm 12 migration skill&nbsp;<sub><em>(9&nbsp;files,&nbsp;+524,&nbsp;-0)</em></sub>
  - Add an explicitly invoked npm 12 migration workflow covering npm 11 staging, lifecycle-script allowlisting, source-policy defaults, Node alignment, lockfile review, breaking changes, and release validation.
  - Include generated metadata, restored rich SVG assets with backups, authoritative npm references, and the synchronized explicit-invocation policy for SchemaStore maintenance.

### 🛠️ Bug Fixes

- [`2e9e9f2`](https://github.com/Nick2bad4u/codex-skills/commit/2e9e9f297d25d2c6646e65889113b5441983a057 "Diff: 5 files, +5 | -0") — 💚 [fix] Restore Python lint compatibility&nbsp;<sub><em>(5&nbsp;files,&nbsp;+5,&nbsp;-0)</em></sub>
  - Add repository copyright notices to the Python helper scripts and their test module so Ruff's newly enforced CPY001 gate passes after the tooling refresh.

- [`87c5586`](https://github.com/Nick2bad4u/codex-skills/commit/87c5586c26a4346c4b5af047107f7c113f08c482 "Diff: 1 file, +1 | -1") — 💚 [fix] Restore external lint tool boundary&nbsp;<sub><em>(1&nbsp;file,&nbsp;+1,&nbsp;-1)</em></sub>
  - Keep Gitleaks available through lint:gitleaks and lint:external without requiring its standalone binary in release:verify, matching the CI environment.

### 📝 Documentation

- [`3c7e5ca`](https://github.com/Nick2bad4u/codex-skills/commit/3c7e5ca48ab482c334e39f04c677c016f4833994 "Diff: 1 file, +1 | -1") — 📝 [docs] Clarify dependency update validation scope&nbsp;<sub><em>(1&nbsp;file,&nbsp;+1,&nbsp;-1)</em></sub>
  - Use the full installation terminology in the dependency-update maintenance guidance without changing its behavior or trigger.

### 👷 CI/CD

- [`edc0e02`](https://github.com/Nick2bad4u/codex-skills/commit/edc0e02970496d6c77f2a4730c390d583247a7c2 "Diff: 2 files, +55 | -5") — _(release)_ Guard git-cliff note generation&nbsp;<sub><em>(2&nbsp;files,&nbsp;+55,&nbsp;-5)</em></sub>
  - Validate the authoritative release tag at HEAD immediately before git-cliff and export GitHub authentication for enriched notes. Standardize Actionlint configuration and direct package CLI usage where applicable.

### 📦 Dependencies

- [`de5f899`](https://github.com/Nick2bad4u/codex-skills/commit/de5f899ef09a744a0f2e1e64fd1a004b06d0efc7 "Diff: 1 file, +3 | -3") — ⬆️ [build] Update npm_and_yarn dependencies&nbsp;<sub><em>(1&nbsp;file,&nbsp;+3,&nbsp;-3)</em></sub>

- [`2b3fd0b`](https://github.com/Nick2bad4u/codex-skills/commit/2b3fd0bfe0e0f2deba6f610e311e8818f9c8461b "Diff: 1 file, +16 | -32") — ⬆️ [build] Update npm_and_yarn dependencies&nbsp;<sub><em>(1&nbsp;file,&nbsp;+16,&nbsp;-32)</em></sub>

- [`7eb880f`](https://github.com/Nick2bad4u/codex-skills/commit/7eb880f24e24854b655ab0d062df3476a992771c "Diff: 2 files, +1209 | -817") — ⬆️ [build] Refresh shared tooling dependencies&nbsp;<sub><em>(2&nbsp;files,&nbsp;+1209,&nbsp;-817)</em></sub>
  - Adopt the shared NCU package wiring and update the development toolchain, including the ESLint 5 and Lychee 2 presets. Keep heavy JSCPD and Lychee checks available as dedicated scripts while excluding them from lint:all.

### 🛡️ Security

- [`bb88d11`](https://github.com/Nick2bad4u/codex-skills/commit/bb88d1185c934c951ebb0e5c7dd5e77cbbee394d "Diff: 4 files, +508 | -8") — 🔒️ [fix] Harden CI dependency installation&nbsp;<sub><em>(4&nbsp;files,&nbsp;+508,&nbsp;-8)</em></sub>
  - Disable npm lifecycle scripts during CI and release installation, replace unverified pip upgrades with a generated SHA-256-locked Python dependency set, and require hash verification in workflows and local bootstrap scripts.
  - This resolves the six SonarCloud workflow vulnerabilities without weakening the quality gate.

### 🛠️ Other Changes

- [`42ff5bc`](https://github.com/Nick2bad4u/codex-skills/commit/42ff5bce89c62130784fb97824ed0168393f2368 "Diff: 1 file, +7 | -0") — Add SchemaStore adoption evidence guidance (#1)&nbsp;<sub><em>(1&nbsp;file,&nbsp;+7,&nbsp;-0)</em></sub>
  - 📝 [docs] Add SchemaStore adoption evidence guidance
  - fix: use full path src/api/json/catalog.json in adoption evidence guidance
  ***
  - Co-authored-by: copilot-swe-agent[bot] <198982749+Copilot@users.noreply.github.com>

### New Contributors

- @dependabot[bot] made their first contribution in [#3](https://github.com/Nick2bad4u/codex-skills/pull/3)

> [!NOTE]
> **Release comparison**: https://github.com/Nick2bad4u/codex-skills/compare/v0.7.1...v0.8.0

## ✨ What's Changed in v0.7.1

- <b>Commit Range: ➡️</b> [`v0.7.0...v0.7.1`](https://github.com/Nick2bad4u/codex-skills/compare/v0.7.0...v0.7.1 "View full commit range on GitHub")

### 🛠️ Bug Fixes

- [`258ecf5`](https://github.com/Nick2bad4u/codex-skills/commit/258ecf584c394396eb15b40d175c41757fd37288 "Diff: 1 file, +3 | -7") — _(package)_ Include complete skill resources&nbsp;<sub><em>(1&nbsp;file,&nbsp;+3,&nbsp;-7)</em></sub>
  - 📦️ [fix] Package the full skills tree so references, assets, and agent metadata ship with each skill.
  - 🧹 [chore] Exclude generated Python bytecode and **pycache** directories from npm artifacts.

> [!NOTE]
> **Release comparison**: https://github.com/Nick2bad4u/codex-skills/compare/v0.7.0...v0.7.1

## ✨ What's Changed in v0.7.0

- <b>Commit Range: ➡️</b> [`v0.6.0...v0.7.0`](https://github.com/Nick2bad4u/codex-skills/compare/v0.6.0...v0.7.0 "View full commit range on GitHub")

### ✨ Features

- [`169fc67`](https://github.com/Nick2bad4u/codex-skills/commit/169fc675d2a892c80d639c1e409b79c9d00516a0 "Diff: 3 files, +50 | -14") — _(python)_ Support standardized dependency locks&nbsp;<sub><em>(3&nbsp;files,&nbsp;+50,&nbsp;-14)</em></sub>
  - ✨ [feat] Make the strict Python workflow select the repository's authoritative requirements, pylock, or tool-specific lock source.
  - 📝 [docs] Document PEP 751 filenames, pip support checks, platform coverage risks, uv exports, CI cache alignment, and matching npm bootstrap commands.

- [`b5127f3`](https://github.com/Nick2bad4u/codex-skills/commit/b5127f3f1a5fc04bfaa6f91bdf86e13f46f7bd48 "Diff: 4 files, +256 | -251") — ✨ [feat] Update configuration files and dependencies&nbsp;<sub><em>(4&nbsp;files,&nbsp;+256,&nbsp;-251)</em></sub>

### 🛠️ Bug Fixes

- [`82a6c6d`](https://github.com/Nick2bad4u/codex-skills/commit/82a6c6df9692077a1a70bc5247b1385f91e6afac "Diff: 1 file, +174 | -174") — _(config)_ Restore portable TOML formatting&nbsp;<sub><em>(1&nbsp;file,&nbsp;+174,&nbsp;-174)</em></sub>
  - 🎨 [style] Apply the repository Prettier configuration to pyproject.toml so Linux CI and local release checks agree.

> [!NOTE]
> **Release comparison**: https://github.com/Nick2bad4u/codex-skills/compare/v0.6.0...v0.7.0

## ✨ What's Changed in v0.6.0

- <b>Commit Range: ➡️</b> [`v0.5.1...v0.6.0`](https://github.com/Nick2bad4u/codex-skills/compare/v0.5.1...v0.6.0 "View full commit range on GitHub")

### ✨ Features

- [`f37b44c`](https://github.com/Nick2bad4u/codex-skills/commit/f37b44c9d4fdf51972576aa72d06f2807b4490b4 "Diff: 36 files, +1383 | -31") — ✨ [feat] Add SchemaStore and dependency update skills&nbsp;<sub><em>(36&nbsp;files,&nbsp;+1383,&nbsp;-31)</em></sub>
  - ✨ [feat] Add researched SchemaStore PR and dependency update maintenance workflows with metadata, references, icons, and deterministic audit scripts.
  - 🧪 [test] Cover both auditors and extend strict Python coverage sources.
  - 🔧 [chore] Tighten skill descriptions and keep repository linters from traversing generated cache directories.

### 🛠️ Bug Fixes

- [`91a77a6`](https://github.com/Nick2bad4u/codex-skills/commit/91a77a691a5b434db05c15bc125446a43e837313 "Diff: 4 files, +227 | -206") — 🐛 [fix] Restore trusted release workflow identity&nbsp;<sub><em>(4&nbsp;files,&nbsp;+227,&nbsp;-206)</em></sub>
  - Restore release-skill.yml so npm trusted publishing recognizes the workflow's OIDC identity. Add GitHub release-note metadata and exclude generated Python bytecode from npm and ZIP artifacts.

- [`1e87112`](https://github.com/Nick2bad4u/codex-skills/commit/1e8711200962ba341a0abe05cb05b738071c19f9 "Diff: 2 files, +205 | -205") — 🐛 [fix] Use canonical release workflow path&nbsp;<sub><em>(2&nbsp;files,&nbsp;+205,&nbsp;-205)</em></sub>
  - 🐛 [fix] Rename the existing skill release workflow to release.yml so fresh repository-compliance lint recognizes the real release configuration.

- [`c0a91b5`](https://github.com/Nick2bad4u/codex-skills/commit/c0a91b5c3585fb30489576171e8d3c17ac44ebfd "Diff: 4 files, +0 | -0") — 🐛 [fix] Mark Python audit scripts executable&nbsp;<sub><em>(4&nbsp;files,&nbsp;+0,&nbsp;-0)</em></sub>
  - 🐛 [fix] Store every shebang-bearing Python auditor with executable Git mode so Ruff EXE001 passes on Linux runners.

### 🧹 Chores

- [`98f7a54`](https://github.com/Nick2bad4u/codex-skills/commit/98f7a54757b00fbb437c3dba5a4a761b76fa5224 "Diff: 1 file, +1 | -1") — 🔧 [chore] Keep JSCPD and Lychee out of lint all&nbsp;<sub><em>(1&nbsp;file,&nbsp;+1,&nbsp;-1)</em></sub>
  - 🔧 [chore] Leave the dedicated JSCPD and Lychee scripts available while keeping aggregate CI lint runs focused on existing gates.

- [`46f5a24`](https://github.com/Nick2bad4u/codex-skills/commit/46f5a2446c49a5fdeb60fb71dad76e801fbf17ef "Diff: 5 files, +188 | -237") — 🔧 [chore] Adopt shared validation configs&nbsp;<sub><em>(5&nbsp;files,&nbsp;+188,&nbsp;-237)</em></sub>
  - 🔧 [chore] Wire JSCPD, git-cliff, and Lychee through shared config packages.
  - 👷 [ci] Point release-note generation at the shared git-cliff config where workflows invoke git-cliff directly.

### 🛡️ Security

- [`e2fbd48`](https://github.com/Nick2bad4u/codex-skills/commit/e2fbd4858bddba8c7655ecc8108a57ded07cdf84 "Diff: 3 files, +46 | -61") — 🔒️ [fix] Remove custom Git ref inputs&nbsp;<sub><em>(3&nbsp;files,&nbsp;+46,&nbsp;-61)</em></sub>
  - 🔒️ [fix] Resolve changed files from trusted origin/main and origin/master defaults instead of passing CLI-provided revisions to Git.
  - 🧪 [test] Keep repository-path validation covered for both auditors.

- [`58ae708`](https://github.com/Nick2bad4u/codex-skills/commit/58ae708d24b6205402225bcc395cd2725c274470 "Diff: 4 files, +111 | -19") — 🔒️ [fix] Validate auditor Git inputs&nbsp;<sub><em>(4&nbsp;files,&nbsp;+111,&nbsp;-19)</em></sub>
  - 🔒️ [fix] Validate repository paths and simple Git refs, resolve bases to verified commit SHAs, and separate revision arguments before invoking Git.
  - 🐛 [fix] Emit audit JSON as CLI output and replace repeated dependency filenames with constants.
  - 🧪 [test] Prove both auditors reject option-shaped base refs.

> [!NOTE]
> **Release comparison**: https://github.com/Nick2bad4u/codex-skills/compare/v0.5.1...v0.6.0

## ✨ What's Changed in v0.5.1

- <b>Commit Range: ➡️</b> [`v0.5.0...v0.5.1`](https://github.com/Nick2bad4u/codex-skills/compare/v0.5.0...v0.5.1 "View full commit range on GitHub")

### 🧹 Chores

- [`4f9b535`](https://github.com/Nick2bad4u/codex-skills/commit/4f9b535dfb66371277890736a16a9295dfaa8618 "Diff: 10 files, +987 | -619") — 🧹 [chore] Make maintenance skills user-invokable&nbsp;<sub><em>(10&nbsp;files,&nbsp;+987,&nbsp;-619)</em></sub>
  - 🧹 [chore] Add explicit no-implicit-invocation policy metadata for the requested maintenance skills and keep generated OpenAI metadata in sync.
  - ⬆️ [chore] Refresh npm dependency ranges and lockfile versions.
  - ✅ [fix] Harden the Python coverage script against ambient pytest plugins and keep the updated lint stack compatible with the repo's Prettier TOML format.

> [!NOTE]
> **Release comparison**: https://github.com/Nick2bad4u/codex-skills/compare/v0.5.0...v0.5.1

## ✨ What's Changed in v0.5.0

- <b>Commit Range: ➡️</b> [`v0.4.0...v0.5.0`](https://github.com/Nick2bad4u/codex-skills/compare/v0.4.0...v0.5.0 "View full commit range on GitHub")

### ✨ Features

- [`e86be2c`](https://github.com/Nick2bad4u/codex-skills/commit/e86be2c49ad1dce6559accd2b33b5de6fc808727 "Diff: 2 files, +22 | -5") — ✨ [feat] Add Sonar quality gate release guidance&nbsp;<sub><em>(2&nbsp;files,&nbsp;+22,&nbsp;-5)</em></sub>

### 🧹 Chores

- [`b8bf115`](https://github.com/Nick2bad4u/codex-skills/commit/b8bf1151b0217bc87ab111a1622d319f2490e321 "Diff: 1 file, +0 | -1") — 🔧 [chore] Update VSCode extensions by removing unused Pyright extension&nbsp;<sub><em>(1&nbsp;file,&nbsp;+0,&nbsp;-1)</em></sub>

### 👷 CI/CD

- [`a336613`](https://github.com/Nick2bad4u/codex-skills/commit/a336613569d61b3d8fd7cb6166f96027fdb4b771 "Diff: 1 file, +10 | -0") — 👷 [ci] Install Python tooling in skill release workflow&nbsp;<sub><em>(1&nbsp;file,&nbsp;+10,&nbsp;-0)</em></sub>

- [`9ca5e2a`](https://github.com/Nick2bad4u/codex-skills/commit/9ca5e2a49bafdd172e789828879e51a4fa4e4f03 "Diff: 6 files, +133 | -3") — 👷 [ci] Add Python Codecov coverage reporting&nbsp;<sub><em>(6&nbsp;files,&nbsp;+133,&nbsp;-3)</em></sub>

> [!NOTE]
> **Release comparison**: https://github.com/Nick2bad4u/codex-skills/compare/v0.4.0...v0.5.0

## ✨ What's Changed in v0.4.0

- <b>Commit Range: ➡️</b> [`v0.3.0...v0.4.0`](https://github.com/Nick2bad4u/codex-skills/compare/v0.3.0...v0.4.0 "View full commit range on GitHub")

### ✨ Features

- [`b83579f`](https://github.com/Nick2bad4u/codex-skills/commit/b83579ffa50f331c8977b224eb7d27c952ae10fc "Diff: 20 files, +729 | -451") — _(python)_ Add strict Python validation coverage&nbsp;<sub><em>(20&nbsp;files,&nbsp;+729,&nbsp;-451)</em></sub>
  - ✨ [feat] Add Python strict gate coverage for skills and tests, including compile:python, Windows-safe skillcheck execution, pinned-dev tooling references, and focused tests for bundled Python helpers.
  - 🐛 [fix] Repair strict Python helper scripts for Ruff, mypy, and Pyright by replacing dynamic config reads with typed helpers and removing direct print usage.
  - 📝 [docs] Update Python strict-development and skillcheck guidance with venv setup, coverage/cache defaults, semantic graph linting notes, and root-cause suppression policy.
  - 🚨 [fix] Clean release-gate lint failures in Dependabot, stale workflow casing, remark ignores, and audit tool error checks.

- [`02ed7d7`](https://github.com/Nick2bad4u/codex-skills/commit/02ed7d7e3dbde646fb41c96c22beb439bbfe061f "Diff: 1 file, +131 | -130") — _(package)_ Update package.json with new scripts and dependencies&nbsp;<sub><em>(1&nbsp;file,&nbsp;+131,&nbsp;-130)</em></sub>

- [`8e163d2`](https://github.com/Nick2bad4u/codex-skills/commit/8e163d20c9cc9d8561d51b0039baecd7436d75da "Diff: 7 files, +1386 | -962") — _(package)_ Enhance project configuration and add Python support&nbsp;<sub><em>(7&nbsp;files,&nbsp;+1386,&nbsp;-962)</em></sub>

- [`8b45759`](https://github.com/Nick2bad4u/codex-skills/commit/8b45759bb610bf1c61ea745a25a116eb45cbb8b7 "Diff: 17 files, +1123 | -25") — ✨ [feat] Add skill resource audit helpers&nbsp;<sub><em>(17&nbsp;files,&nbsp;+1123,&nbsp;-25)</em></sub>
  - ✨ [feat] Adds read-only helper scripts for strict Python tooling audits and VSIcons icon inventory, giving agents deterministic checks for config drift and local icon availability.
  - 📝 [docs] Adds Python project-shape and strict-fix references, VSIcons source-resolution guidance, and contents sections for long skill references.
  - 🧹 [chore] Adds a repo-local skill surface auditor to validate linked references/scripts and long-reference tables of contents through npm run validate.
  - 🎨 [style] Preserves the updated Python strict development brand color and regenerates the associated OpenAI metadata and SVG assets.

### 🎨 Styling

- [`212ef2e`](https://github.com/Nick2bad4u/codex-skills/commit/212ef2e04456b1a1d2343749eaea296c4b96b0d1 "Diff: 2 files, +15 | -13") — 🎨 [style] Update Python skill documentation for clarity and consistency&nbsp;<sub><em>(2&nbsp;files,&nbsp;+15,&nbsp;-13)</em></sub>

> [!NOTE]
> **Release comparison**: https://github.com/Nick2bad4u/codex-skills/compare/v0.3.0...v0.4.0

## ✨ What's Changed in v0.3.0

- <b>Commit Range: ➡️</b> [`v0.2.0...v0.3.0`](https://github.com/Nick2bad4u/codex-skills/compare/v0.2.0...v0.3.0 "View full commit range on GitHub")

### ✨ Features

- [`c459581`](https://github.com/Nick2bad4u/codex-skills/commit/c459581eac54691c004fc1eb2a74d7eefab8bfe5 "Diff: 10 files, +524 | -2") — ✨ [feat] Add Python strict development skill&nbsp;<sub><em>(10&nbsp;files,&nbsp;+524,&nbsp;-2)</em></sub>
  - ✨ [feat] Adds python-strict-development with strict Ruff, mypy, Pyright, pytest, compileall, VS Code, and npm-script guidance based on the reference Python skill package.
  - 📝 [docs] Adds skillcheck strict configuration references for skill creation and review workflows, including semantic graph-linting guidance for --semantic.
  - 🧹 [chore] Registers the new skill in metadata sync so agents/openai.yaml and SVG assets are generated with the existing repository workflow.

> [!NOTE]
> **Release comparison**: https://github.com/Nick2bad4u/codex-skills/compare/v0.2.0...v0.3.0

## ✨ What's Changed in v0.2.0

- <b>Commit Range: ➡️</b> [`v0.1.2...v0.2.0`](https://github.com/Nick2bad4u/codex-skills/compare/v0.1.2...v0.2.0 "View full commit range on GitHub")

### ✨ Features

- [`02efe00`](https://github.com/Nick2bad4u/codex-skills/commit/02efe00a56c5d37c2951bc7781b26a1024a2f53e "Diff: 53 files, +3134 | -986") — ✨ [feat] Expand skill catalog and metadata sync&nbsp;<sub><em>(53&nbsp;files,&nbsp;+3134,&nbsp;-986)</em></sub>
  - ✨ [feat] Add Mermaid diagram, release publish loop, and Prettier plugin maintenance skills with generated OpenAI metadata and SVG assets.
  - 🚜 [refactor] Rename the icon generator to sync-skill-metadata and make policy/dependencies metadata first-class for generated agents/openai.yaml files.
  - 🎨 [style] Refresh generated skill icons with full titles, emoji badges, color updates, and explicit invocation policy for release, VSIcons, and workspace continuation.
  - 🧪 [test] Verified with npm run release:verify before committing.

- [`c2193bc`](https://github.com/Nick2bad4u/codex-skills/commit/c2193bc48218c05e66a46230aaf75435e3e07415 "Diff: 1 file, +1 | -1") — ✨ [feat] Enhance local custom icon recommendation logic&nbsp;<sub><em>(1&nbsp;file,&nbsp;+1,&nbsp;-1)</em></sub>

### 🛡️ Security

- [`a172d1d`](https://github.com/Nick2bad4u/codex-skills/commit/a172d1dd8b79cb1d887197ed23fb3c9db3f1edc4 "Diff: 6 files, +323 | -7") — 🔒️ [fix] Harden skill audit boundaries&nbsp;<sub><em>(6&nbsp;files,&nbsp;+323,&nbsp;-7)</em></sub>
  - 🔒️ [fix] Treat CI logs and external VSIcons references as untrusted data, limiting them to diagnostics and verifiable facts instead of agent instructions.
  - 🔧 [fix] Disable implicit invocation for ci-release-readiness in generated OpenAI metadata so log-reading workflows require explicit use.
  - 🔨 [chore] Add an audit:skills CLI wrapper for checking every local skill against the skills.sh audit endpoint.
  - 🧪 [test] Verify the release gate with npm run release:verify.

> [!NOTE]
> **Release comparison**: https://github.com/Nick2bad4u/codex-skills/compare/v0.1.2...v0.2.0

## ✨ What's Changed in v0.1.2

- <b>Commit Range: ➡️</b> [`v0.1.1...v0.1.2`](https://github.com/Nick2bad4u/codex-skills/compare/v0.1.1...v0.1.2 "View full commit range on GitHub")

### ✨ Features

- [`9ecde09`](https://github.com/Nick2bad4u/codex-skills/commit/9ecde09354a2a17443c2128ca698f413bdece86e "Diff: 15 files, +1795 | -562") — _(github-actions-workflow-maintenance)_ Introduce GitHub Actions Workflow Maintenance skill&nbsp;<sub><em>(15&nbsp;files,&nbsp;+1795,&nbsp;-562)</em></sub>

- [`11fb710`](https://github.com/Nick2bad4u/codex-skills/commit/11fb7105f6159b6c4da902faa29c43248798f70d "Diff: 5 files, +120 | -0") — ✨ [feat] Add VSIcons association recommender skill&nbsp;<sub><em>(5&nbsp;files,&nbsp;+120,&nbsp;-0)</em></sub>
  - Add a reusable skill for recommending copy-pasteable vscode-icons file and folder association snippets, including optional local custom icon handling.
  - Keep generated Codex metadata and SVG assets synchronized through the icon generator.
  - Validation: npm run release:verify; skillcheck skills/vsicons-association-recommender/SKILL.md

- [`feeb94c`](https://github.com/Nick2bad4u/codex-skills/commit/feeb94c168fa8c6a64452b6dd006aa2d4d053309 "Diff: 13 files, +272 | -0") — ✨ [feat] Add agent skill and remark maintenance skills&nbsp;<sub><em>(13&nbsp;files,&nbsp;+272,&nbsp;-0)</em></sub>
  - Rename the agent instruction workflows to emphasize skill coverage and add a remark/remark-lint plugin maintenance workflow with generated Codex metadata and icons.
  - Validation: npm run release:verify; skillcheck skills/agent-skill-instruction-review/SKILL.md skills/agent-skill-instruction-creation/SKILL.md skills/remark-plugin-maintenance/SKILL.md

### 🛠️ Bug Fixes

- [`da9701c`](https://github.com/Nick2bad4u/codex-skills/commit/da9701c0525d713e308c9bdcd8e243d4ebc99a74 "Diff: 8 files, +27744 | -27744") — 💚 [fix] Restore workflow lint formatting&nbsp;<sub><em>(8&nbsp;files,&nbsp;+27744,&nbsp;-27744)</em></sub>

### 🛡️ Security

- [`3bb7a34`](https://github.com/Nick2bad4u/codex-skills/commit/3bb7a3482d66714507bf8a1dead945def6eb0f27 "Diff: 6 files, +6 | -6") — 🔒 [fix] Pin reusable workflow callers&nbsp;<sub><em>(6&nbsp;files,&nbsp;+6,&nbsp;-6)</em></sub>
  - Pin all workflow-template reusable workflow references to an immutable commit SHA to satisfy Sonar githubactions:S7637 findings.
  - Validation: npm run release:verify

- [`b3d3d90`](https://github.com/Nick2bad4u/codex-skills/commit/b3d3d90aedde441ac659dab06a257eb6dd2241ec "Diff: 13 files, +27811 | -27867") — 👷 [ci] Use shared workflow callers&nbsp;<sub><em>(13&nbsp;files,&nbsp;+27811,&nbsp;-27867)</em></sub>
  - 👷 [ci] Switches the Dependabot auto-merge caller to workflow-templates@main and replaces local security and maintenance workflows with shared reusable callers.
  - ⬆️ [build] Updates eslint-config-nick2bad4u to the published caller override version and records any peer dependency needed for the shared ESLint config to load.

> [!NOTE]
> **Release comparison**: https://github.com/Nick2bad4u/codex-skills/compare/v0.1.1...v0.1.2

## ✨ What's Changed in v0.1.1

- <b>Commit Range: ➡️</b> [`5fdf450...v0.1.1`](https://github.com/Nick2bad4u/codex-skills/compare/5fdf4503794dc2bfda51e2b15d8adf7932a73f00...v0.1.1 "View full commit range on GitHub")

### ✨ Features

- [`d4212a5`](https://github.com/Nick2bad4u/codex-skills/commit/d4212a5470e4d8457b57624315f71d1dbd030654 "Diff: 33 files, +737 | -13") — 🎨 [feat] Add skill icons and release notes&nbsp;<sub><em>(33&nbsp;files,&nbsp;+737,&nbsp;-13)</em></sub>

- [`5fdf450`](https://github.com/Nick2bad4u/codex-skills/commit/5fdf4503794dc2bfda51e2b15d8adf7932a73f00 "Diff: 40 files, +5366 | -0") — ✨ [feat] Add consolidated Codex skills repo&nbsp;<sub><em>(40&nbsp;files,&nbsp;+5366,&nbsp;-0)</em></sub>

### 🔧 Build System

- [`f13cece`](https://github.com/Nick2bad4u/codex-skills/commit/f13cece5a39f1ee902bb36a71ac0fc6b65716add "Diff: 3 files, +4 | -5") — 📦 [build] Use typpi npm package scope&nbsp;<sub><em>(3&nbsp;files,&nbsp;+4,&nbsp;-5)</em></sub>

- [`c369ef6`](https://github.com/Nick2bad4u/codex-skills/commit/c369ef6179930d09c2012030fa2472a64b3deadc "Diff: 46 files, +27362 | -3115") — 🚀 [build] Prepare Codex skills package publishing&nbsp;<sub><em>(46&nbsp;files,&nbsp;+27362,&nbsp;-3115)</em></sub>

### 🛡️ Security

- [`622d9c2`](https://github.com/Nick2bad4u/codex-skills/commit/622d9c2ff57d0f728bca2c3fcbb0d28f19bebbfe "Diff: 1 file, +7 | -3") — 🔒 [fix] Harden release workflow inputs&nbsp;<sub><em>(1&nbsp;file,&nbsp;+7,&nbsp;-3)</em></sub>

### New Contributors

- @Nick2bad4u made their first contribution

## ⭐ Contributors

Thanks to anyone who has 🧑‍💻 [contributed](https://github.com/Nick2bad4u/codex-skills/graphs/contributors).

_This changelog was automatically generated with ⛰️ [git-cliff](https://github.com/orhun/git-cliff)._
