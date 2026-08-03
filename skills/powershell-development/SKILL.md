---
name: powershell-development
description: Develops, audits, repairs, and tests PowerShell. Use whenever the user asks to create, review, debug, harden, or test .ps1, .psm1, or .psd1 files, functions, modules, profiles, PSScriptAnalyzer, Pester, native tools, cross-platform automation, remoting, packaging, or PowerShell CI.
---

# PowerShell Development

Build PowerShell that behaves like a trustworthy command-line API: inspectable, pipeline-friendly, non-interactive by default, safe under `-WhatIf`, and testable without touching live systems.

## Source Priority

1. Read applicable `AGENTS.md` files, module manifests, `#Requires` statements, analyzer settings, build scripts, CI workflows, tests, and help before editing.
2. Treat the repository's declared PowerShell, Pester, and PSScriptAnalyzer versions as authoritative. Inspect the live versions only to confirm that the required matrix can run.
3. Preserve established public command names and output contracts unless the user explicitly authorizes a breaking change.
4. Use current Microsoft PowerShell, PSScriptAnalyzer, and Pester documentation for version-sensitive behavior. Do not generalize from Windows PowerShell 5.1 to PowerShell 7 or vice versa.
5. Read [powershell-engineering.md](references/powershell-engineering.md) when authoring or reviewing command APIs, modules, native-process calls, filesystem mutations, remoting, compatibility, documentation, or packaging.
6. Read [pester-testing.md](references/pester-testing.md) whenever tests, mocks, coverage, Pester configuration, or a Pester 5-to-6 migration is in scope.

## Workflow

1. Classify the request as diagnose, review, implementation, test work, compatibility migration, or release preparation. Do not mutate code for an analysis-only request.
2. Inventory `.ps1`, `.psm1`, `.psd1`, `.pssc`, `.psrc`, analyzer settings, test files, module imports, exported commands, external executables, platform guards, and CI entrypoints in the requested scope.
3. Establish the compatibility contract:
   - Windows PowerShell versus PowerShell Core
   - minimum and tested versions
   - Windows, Linux, and macOS expectations
   - required modules and native tools
   - interactive, unattended, elevated, remote, or constrained-language hosts
4. Reproduce the failing behavior or capture a clean baseline with the narrowest real command. Use `-NoProfile` when profile state is not part of the feature.
5. Design the public contract before implementation: approved `Verb-Noun` name, parameter sets and types, pipeline binding, output objects, error behavior, idempotency, and mutation/confirmation semantics.
6. Make a focused change. Keep environment discovery, validation, planning, mutation, cleanup, and presentation separable enough to test.
7. Add or repair behavior-focused Pester coverage. Test failure paths, cleanup, pipeline input, output shape, platform conditions, native exit codes, and `-WhatIf` for mutating commands.
8. Run the targeted test or analyzer command after each fix, then the repository's aggregate gates and required compatibility matrix.
9. Review the diff for leaked success-stream output, unsafe interpolation, broad path operations, hidden prompts, swallowed exit codes, global preference changes, and unjustified analyzer suppressions.

## Safety Invariants

- Separate read-only discovery from mutation. Resolve and display exact targets before destructive, elevated, remote, package-management, service, registry, certificate, scheduled-task, or cloud changes.
- Implement `[CmdletBinding(SupportsShouldProcess)]` for commands that change state and call `$PSCmdlet.ShouldProcess()` before every independently skippable mutation or once before a described transaction.
- Always execute `ShouldProcess`, even when `-Force` is present. Let `-Force` suppress an additional `ShouldContinue` or other interactive prompt; never let it bypass `-WhatIf`.
- Prefer `-LiteralPath` for user-selected filesystem targets. Resolve absolute paths, reject filesystem roots and unintended ancestors, and prove containment before recursive delete or move operations.
- On Windows, keep discovery and mutation in one PowerShell process. Do not enumerate paths in PowerShell and pass constructed deletion commands to `cmd.exe`, a batch file, or another shell.
- Invoke native tools with a fixed executable and argument array. Capture `$LASTEXITCODE` immediately and treat nonzero status according to that tool's documented contract; PowerShell's error stream is not a substitute for native exit-code handling.
- Keep secrets out of source, arguments, verbose output, transcripts, test fixtures, and error messages. Accept credentials through established secure boundaries and redact diagnostic output.
- Make automation non-interactive. Use parameters, `ShouldProcess`, and explicit opt-in switches instead of `Read-Host`; isolate genuinely interactive UI from reusable command logic.
- Make cleanup success-gated where it protects evidence or recoverability, and put unavoidable temporary-resource cleanup in `finally`/Pester teardown blocks.

## Command and Output Contract

- Use approved verbs, specific singular nouns, PascalCase command and parameter names, full cmdlet names, full parameter names, and splatting for nontrivial calls. Avoid aliases and `Invoke-Expression` in committed code.
- Use standard parameter names and strong types. Add validation that improves the caller's error without rejecting valid pipeline or provider input.
- Bind pipeline input deliberately. Stream one output object per input record from `process`; do not add `begin`/`process`/`end` blocks when the command has no lifecycle need.
- Write only data to the success stream. Return rich objects with stable type names or documented properties; reserve formatting for entrypoint/UI code. Use verbose, information, warning, debug, and error streams for their intended purposes.
- Default state-changing commands to no output when that matches PowerShell conventions, and implement `-PassThru` when callers need the affected object.
- Catch only errors that can be handled, enriched, or cleaned up. Use `-ErrorAction Stop` at the specific boundary that must become terminating; do not silently swallow failures or change caller-wide preferences.
- Preserve the original exception as the `ErrorRecord` exception, choose a stable fully qualified error ID and category for public commands, and identify the real target object.

## Modules, Profiles, and Packaging

- Keep public/private boundaries explicit. Export commands intentionally in both the module and manifest; avoid wildcard exports for a stable public module.
- Validate manifests with `Test-ModuleManifest`, import the built module in a clean process, and verify exported commands and help. Test the packaged layout rather than only dot-sourced source files.
- Keep profile edits fast, idempotent, host-aware, and failure-isolated. Do not assume interactive modules, terminal capabilities, or network availability in every host.
- Treat installation, repository registration, signing, publishing, remoting, and gallery operations as external mutations. Inspect first and require authorization for the actual external change.

## Validation

Prefer repository commands. Otherwise adapt this baseline to the declared versions and paths:

```powershell
Invoke-ScriptAnalyzer -Path . -Recurse -Settings ./PSScriptAnalyzerSettings.psd1
Invoke-Pester -Path ./tests
Test-ModuleManifest -Path ./src/ModuleName/ModuleName.psd1
pwsh -NoLogo -NoProfile -Command "Import-Module ./src/ModuleName/ModuleName.psd1 -Force; Get-Command -Module ModuleName"
```

Run Windows PowerShell 5.1 separately when it is supported; passing under `pwsh` does not prove Desktop-edition compatibility. Exercise each supported operating system in CI when platform-specific paths, providers, native tools, elevation, remoting, or encoding behavior matter.

## Output

Finish with files and public contracts changed, PowerShell/Pester versions exercised, commands run, behavior and failure paths proven, remaining platform or privilege gaps, and any external mutation intentionally not performed.
