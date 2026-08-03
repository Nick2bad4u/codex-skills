# Pester Testing Reference

Use this reference for PowerShell unit, integration, contract, and migration tests. Preserve the repository's Pester major version unless an upgrade is explicitly in scope.

## Contents

- [Select the test contract](#select-the-test-contract)
- [Structure and execution phases](#structure-and-execution-phases)
- [Behavior-focused test design](#behavior-focused-test-design)
- [Assertions and collections](#assertions-and-collections)
- [Mocks and module scope](#mocks-and-module-scope)
- [PowerShell-specific coverage](#powershell-specific-coverage)
- [Configuration and CI](#configuration-and-ci)
- [Pester 5 to 6 migration](#pester-5-to-6-migration)
- [Validation loop](#validation-loop)
- [Primary references](#primary-references)

## Select the Test Contract

1. Inspect module manifests, dependency declarations, bootstrap/build scripts, existing imports, configuration objects, CI setup, and installed versions.
2. Record the Pester major version and every PowerShell/runtime target. Do not assume the highest installed Pester version is the repository's intended version.
3. Run a clean baseline before changing tests. Distinguish a product defect, stale test expectation, version migration break, environment failure, and test-isolation leak.
4. Keep established assertion syntax during unrelated work. Pester 6 still supports classic `Should -Be`; adopting the new `Should-Be` command family is an optional separate migration.
5. For Pester 6, target supported hosts: Windows PowerShell 5.1 or PowerShell 7.4 and newer. Keep Pester 5 only where the repository contract requires it, and verify that contract rather than guessing from local availability.

## Structure and Execution Phases

- Use `*.Tests.ps1` unless the repository's runner explicitly discovers another convention.
- Keep test execution inside Pester blocks. Use `BeforeDiscovery` for data required to construct `Describe`, `Context`, or `It -ForEach` cases; use `BeforeAll` for module imports and runtime setup.
- Import the built module or public entrypoint in `BeforeAll`. Dot-source source files only when the project intentionally tests scripts without a module boundary.
- Make every test file self-contained. Pester 6 discovers and runs one file before moving to the next, and parallel execution isolates files in separate runspaces.
- Use one setup/teardown block of each kind per containing block. Combine duplicate `BeforeAll`, `BeforeEach`, `AfterEach`, or `AfterAll` blocks.
- Use `BeforeEach` for fresh per-test state and `AfterEach`/`AfterAll` for resources the test created. Cleanup must target only those recorded resources.
- Group behavior under `Describe`; use `Context` for meaningful states or parameter sets. Write `It` names as observable outcomes, optionally with `Because` for non-obvious business rules.
- Do not depend on test order, leaked module/session state, a developer profile, current location, local culture, wall-clock timing, or network availability unless the test is explicitly tagged as integration.

## Behavior-Focused Test Design

- Arrange, act, and assert around one behavior. Multiple assertions are appropriate when they prove one output/error/interaction contract together.
- Cover normal input, empty and boundary input, invalid binding/validation, each parameter set, pipeline input, repeated calls, idempotency, cancellation, cleanup, and partial failure according to risk.
- Use `-ForEach` or `-TestCases` for readable data-driven coverage. In Pester 6, `$null` or an empty case list fails unless `-AllowNullOrEmptyForEach` is explicitly justified; prefer fixing missing discovery data.
- Tag integration, network, filesystem, remoting, elevation, platform, performance, and slow tests. Keep the default unit suite deterministic and offline.
- Use `-Skip:$condition` only for a real unsupported environment, with a reason close to the condition. Do not convert failures into skips to get CI green.
- Prefer state-based assertions for the command's public result and interaction assertions only where the boundary call is itself part of the contract.
- Keep fixtures minimal and representative. Avoid snapshots of unstable formatting, error rendering, object property order, timestamps, GUIDs, or absolute machine paths.

## Assertions and Collections

- Assert values, types, property contracts, error IDs/categories, and side effects rather than implementation details.
- Preserve the distinction between no output, `$null`, an empty collection, one scalar, and a one-element collection. PowerShell pipeline unrolling can collapse those shapes.
- In Pester 6's new assertion commands, use `-Actual` when the concrete collection type or unwrapped value matters; pipeline input can re-collect or unwrap values.
- Assert an exact error identifier or structured `ErrorRecord` property when it is a public contract. Avoid matching the entire localized/rendered error string.
- Use `Should -Throw`/`Should-Throw` for terminating failures. For non-terminating errors, capture the error stream or use `-ErrorVariable` and assert the record while proving processing continues as designed.
- Do not rewrite classic assertions solely for style. If migrating to Pester 6 assertion commands, isolate that change and validate collection, truthiness, null/empty, and exception semantics.

## Mocks and Module Scope

- Mock external boundaries: HTTP, cloud/service APIs, registry, filesystem mutation, remoting, process launch, time, randomness, credentials, and commands outside the unit.
- Do not mock the command under test or every private helper. Prefer real pure logic and observable behavior.
- Provide safe default mocks, then add `-ParameterFilter` variants for specific calls. In Pester 6, unmatched filtered mocks no longer fall through to the real command; an unmatched call fails unless a default mock exists.
- Use `Should -Invoke` and `Should -InvokeVerifiable` for Pester 5-compatible suites. Pester 6-only suites may use `Should-Invoke` and `Should-Invoke -Verifiable`. Do not use removed `Assert-MockCalled` or `Assert-VerifiableMock` in Pester 6.
- Specify `-Times`, `-Exactly`, `-ParameterFilter`, and scope intentionally. Prefer assertions scoped to the current `It` when setup calls should not count.
- Mock in the scope where the command resolves. For script modules, use the repository's established `InModuleScope`/module-name pattern for private boundaries, but avoid white-box tests that freeze internal layout.
- Make mocked return objects faithful enough to exercise real binding, property access, and enumeration behavior. A loose hashtable is not equivalent to every object a real command returns.
- Prove a dangerous boundary was not called for validation failures, `-WhatIf`, and rejected confirmation paths.

## PowerShell-Specific Coverage

### ShouldProcess and Force

For every mutating public command, prove:

- normal invocation performs the intended mutation
- `-WhatIf` reports intent and does not call the mutation boundary
- `-Force` suppresses only the extra interactive confirmation
- `-Force -WhatIf` still does not mutate
- each pipeline target is approved/skipped independently when that is the contract
- downstream commands do not double-prompt after the public boundary approves the mutation

Test behavior instead of trying to replace `$PSCmdlet.ShouldProcess` directly when possible. A real `-WhatIf` call plus a mocked mutation boundary is usually clearer.

### Filesystem and Temporary Data

- Use Pester's `TestDrive:` for isolated provider-backed filesystem tests when its semantics match the code.
- Use a uniquely named directory beneath the OS temporary directory for code that must interact with native tools or real filesystem APIs. Record the exact path and clean it in teardown.
- Cover wildcard-looking literal names, spaces, Unicode, missing parents, symlinks/reparse points when relevant, containment rejection, root rejection, and cleanup after exceptions.

### Pipelines, Streams, and Errors

- Test zero, one, and multiple pipeline records; property-name binding; parameter-set resolution; process-block streaming; and downstream consumption.
- Assert that status messages do not leak to the success stream and that verbose/information/warning/error output uses the intended stream.
- Cover terminating and non-terminating paths separately. Prove the fully qualified error ID, category, target, and continuation/termination behavior expected by callers.
- For native tools, mock the process boundary for unit tests and add a focused integration test where exit status, stdout/stderr, encoding, or argument quoting is the behavior under test.

### Modules and State

- Import the packaged module in a clean session and verify public exports, aliases, type/format data, help, and repeated import/removal when relevant.
- Reset module variables, environment variables, locations, preference variables, jobs, events, runspaces, and mocks in teardown when the test changes them.
- Test profile-dependent behavior only in a dedicated profile/host suite; normal unit tests should run with `-NoProfile`.

## Configuration and CI

Prefer a checked-in configuration object or repository wrapper for nontrivial suites:

```powershell
$configuration = New-PesterConfiguration
$configuration.Run.Path = './tests'
$configuration.Run.Exit = $true
$configuration.Output.Verbosity = 'Detailed'
$configuration.TestResult.Enabled = $true
$configuration.TestResult.OutputPath = './coverage/pester/test-results.xml'
$configuration.TestResult.OutputFormat = 'NUnitXml'
$configuration.CodeCoverage.Enabled = $true
$configuration.CodeCoverage.Path = './src'
$configuration.CodeCoverage.OutputPath = './coverage/pester/coverage.xml'
$configuration.CodeCoverage.OutputFormat = 'Cobertura'

Invoke-Pester -Configuration $configuration
```

- Adapt output formats and paths to the CI consumer. Create artifact directories deterministically and keep them out of source packages.
- Set `Run.Exit = $true` for a standalone CI process, or inspect the returned result and exit explicitly in a larger build orchestrator.
- Keep coverage meaningful: include public behavior and risky branches, exclude generated code only with a documented reason, and never add execution-only assertions to inflate a threshold.
- Run PSScriptAnalyzer independently from Pester. A green test suite does not prove static-analysis or compatibility rules.
- Use an explicit test matrix for supported PowerShell/Pester/OS combinations. Avoid installing an unpinned latest module in CI when the repository claims reproducible compatibility.
- Treat Pester 6 parallel execution as opt-in and experimental until the repository proves isolation. Run the serial suite as the correctness baseline.

## Pester 5 to 6 Migration

Record a clean Pester 5 baseline, change one migration category at a time, and rerun targeted files plus the complete suite. Check these documented breaks:

1. Run Pester 6 only on Windows PowerShell 5.1 or PowerShell 7.4+.
2. Make each file self-contained because v6 discovery/run happens per file rather than as two suite-global phases.
3. Move discovery-time case generation to `BeforeDiscovery`; do runtime imports/setup in `BeforeAll`.
4. Fix empty or `$null` `-ForEach`/`-TestCases`; use `-AllowNullOrEmptyForEach` only when zero cases are an intentional valid result.
5. Combine duplicate setup/teardown blocks in the same container.
6. Replace removed `Assert-MockCalled` and `Assert-VerifiableMock` with `Should -Invoke` and `Should -InvokeVerifiable`.
7. Add a default mock where filtered mocks do not cover every valid call; v6 does not fall through to the real command.
8. Replace removed `Set-ItResult -Pending` with an intentional skipped or inconclusive result.
9. Replace legacy v4-style `Invoke-Pester` parameters with `New-PesterConfiguration` or the supported simple parameter set.
10. Replace removed `CoverageGutters` output with `JaCoCo` or `Cobertura` and verify paths against `Run.RepoRoot`.
11. Rename a literal `None` tag if it must not match v6's reserved untagged-test filter.
12. Review templated `<...>` test names because v6 evaluates their contents as expressions.

Do not combine the required migration with optional `Should-*` assertion conversion or experimental parallel execution unless the user asks. Keeping those diffs separate makes regressions diagnosable.

## Validation Loop

1. Run the smallest failing `*.Tests.ps1` file with detailed output.
2. Run the affected `Describe`/tag subset if the repository supports a stable filter.
3. Run the complete serial suite in a fresh `-NoProfile` process.
4. Run PSScriptAnalyzer and module/package smoke tests.
5. Run every supported PowerShell/Pester/OS job, not just the developer's newest local version.
6. Inspect test-result and coverage artifacts for zero discovered tests, skipped-test drift, missing files, path errors, or parser warnings before trusting a green process exit.

Report the Pester and PowerShell versions exercised, tests discovered/passed/failed/skipped, coverage when configured, mocked versus real boundaries, platform jobs not run, and any remaining migration category.

## Primary References

- [Pester quick start](https://pester.dev/docs/quick-start)
- [Pester installation and compatibility](https://pester.dev/docs/introduction/installation)
- [Pester v5 to v6 migration](https://pester.dev/docs/migrations/v5-to-v6)
- [Pester configuration](https://pester.dev/docs/usage/configuration)
- [Pester mocking](https://pester.dev/docs/usage/mocking)
