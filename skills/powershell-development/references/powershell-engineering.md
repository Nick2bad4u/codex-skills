# PowerShell Engineering Reference

Use this reference for implementation and review details that are too specific for the core workflow.

## Contents

- [Runtime and compatibility](#runtime-and-compatibility)
- [Command API design](#command-api-design)
- [Pipeline and output](#pipeline-and-output)
- [Errors and native commands](#errors-and-native-commands)
- [Mutation and confirmation](#mutation-and-confirmation)
- [Filesystem and process safety](#filesystem-and-process-safety)
- [Security, remoting, and host boundaries](#security-remoting-and-host-boundaries)
- [Modules, manifests, profiles, and packaging](#modules-manifests-profiles-and-packaging)
- [Documentation and performance](#documentation-and-performance)
- [Validation matrix](#validation-matrix)
- [Primary references](#primary-references)

## Runtime and Compatibility

Inventory the declared contract before choosing syntax or APIs:

```powershell
$PSVersionTable
Get-Command -Name pwsh, powershell -ErrorAction SilentlyContinue
Get-Module -ListAvailable -Name Pester, PSScriptAnalyzer |
    Sort-Object -Property Name, Version -Descending
```

- Read `#Requires -Version`, `#Requires -Modules`, `PowerShellVersion`, `CompatiblePSEditions`, `RequiredModules`, lock/config files, and the CI matrix together. None proves the full contract alone.
- Windows PowerShell 5.1 runs on .NET Framework and does not support the PowerShell 7 features listed here. Do not use ternary expressions, null-coalescing operators, pipeline-chain operators, newer APIs, or newer encoding names when 5.1 remains supported without an explicit compatibility layer.
- PowerShell 7 is cross-platform, but providers, registry paths, CIM/WMI behavior, Windows-only modules, elevation, path case, executable names, and default encodings remain platform-dependent.
- Guard intentional platform behavior with `$IsWindows`, `$IsLinux`, or `$IsMacOS` only where those variables exist. For 5.1 compatibility, use a small tested platform helper or edition check.
- When launching `powershell.exe` from `pwsh`, inspect the inherited `PSModulePath`. A Core-only value can hide Windows PowerShell's built-in modules; give the child its default or a deliberate merged module path, and restore any parent-process change.
- Prefer invariant, culture-aware, or ordinal comparison explicitly according to the data contract. Do not rely on the current user's culture for machine-readable dates, numbers, sorting, or serialization.
- Use UTF-8 deliberately for repository files and external tools. Verify the consumer when Windows PowerShell 5.1 participates because its default encoding behavior differs from PowerShell 7.
- Run compatibility analysis and real execution. Static compatibility rules can identify unsupported commands or syntax, but they do not prove provider, module, or native-tool behavior.

## Command API Design

- Use an approved verb from `Get-Verb`, a specific singular noun, and a module-specific noun prefix when collision risk exists.
- Preserve an established public name even if a cleaner name exists unless a breaking change is authorized. Add aliases only as an intentional compatibility surface and document their lifecycle.
- Use `[CmdletBinding()]` for reusable public functions. Add `SupportsShouldProcess`, `ConfirmImpact`, `DefaultParameterSetName`, and positional behavior only when the contract requires them.
- Prefer standard parameter names such as `Path`, `LiteralPath`, `Name`, `InputObject`, `Credential`, `ComputerName`, `Force`, and `PassThru` with their conventional meanings.
- Prefer `[switch]` over Boolean flags. Use `[Nullable[bool]]` only when true, false, and unspecified are distinct states.
- Use strong types such as `[uri]`, `[datetime]`, `[version]`, `[cultureinfo]`, `[pscredential]`, enums, and domain types when conversion semantics are safe and predictable.
- Use validation attributes for caller errors that can be decided without I/O. Perform filesystem, network, permission, or cross-parameter validation in executable code so errors identify the real boundary.
- Use parameter sets for genuinely different ways to identify or supply the same operation. Ensure each set is unambiguous and choose the most common safe set as the default.
- Enable `ValueFromPipeline` for direct object input and `ValueFromPipelineByPropertyName` for stable property contracts. Do not enable both reflexively or bind multiple parameters ambiguously.
- Use `begin` for once-per-pipeline initialization, `process` for record-by-record work, `end` for aggregation/finalization, and `clean` only when the minimum PowerShell version and cleanup semantics are explicitly compatible.
- Avoid dynamic parameters unless the parameter truly depends on provider/runtime state; they complicate discovery, help, tests, and remote invocation.
- Preserve repository casing and private-variable conventions. Public commands and parameters remain PascalCase regardless of local variable style.

## Pipeline and Output

- Everything unassigned can reach the success stream: command output, method return values, collection mutations, and helper calls. Assign, cast to `[void]`, or pipe to `Out-Null` only when output is intentionally discarded.
- Prefer implicit output or a bare expression over `Write-Output` when no enumeration control is needed. Use `Write-Output -NoEnumerate` only after testing the caller-visible collection contract.
- Emit objects, not presentation strings. Add a stable `PSTypeName` or real type when downstream consumers need identity; document the properties and `.OUTPUTS` type.
- Keep `Format-Table`, `Format-List`, `Out-String`, ANSI decoration, progress rendering, and host UI at the outermost presentation boundary.
- Stream records when latency and memory matter. Avoid repeated array `+=`; use pipeline streaming, `foreach`, or a typed/list collection when aggregation is required.
- A mutating command normally acts as a sink. Add `-PassThru` to return the created or affected object instead of emitting incidental status text.
- Use `Write-Verbose` for opt-in operational detail, `Write-Debug` for developer diagnostics, `Write-Information` for redirectable informational UI, `Write-Warning` for actionable risk, and the error stream for failures. Use `Write-Host` only for intentionally host-bound UI.
- Keep progress bounded and clear it before permanent output. Do not make progress records part of the data contract or require an interactive terminal.

## Errors and Native Commands

- `try`/`catch` handles terminating errors. Add `-ErrorAction Stop` to the specific cmdlet call whose non-terminating errors must enter `catch`; avoid changing `$ErrorActionPreference` across a caller's session.
- Catch a specific exception only when the implementation can handle it more precisely. Otherwise use one cleanup/enrichment catch and preserve the original exception.
- For an advanced public function, use `$PSCmdlet.WriteError()` for a record-scoped non-terminating error and `$PSCmdlet.ThrowTerminatingError()` when the entire command cannot continue. A simple `throw` is appropriate for private helpers and script-level fatal failures when a custom record adds no value.
- Construct public `ErrorRecord` instances with the original exception, a stable fully qualified error ID, the closest `ErrorCategory`, and the object that actually failed.
- Do not catch merely to rewrite a useful exception as a generic message. Never report success from `finally`; reserve it for cleanup that must run after both success and failure.
- Invoke a known executable directly with an argument array:

  ```powershell
  $arguments = @('status', '--short', '--branch')
  & $gitCommand @arguments
  $gitExitCode = $LASTEXITCODE
  if ($gitExitCode -ne 0) {
      throw "git status failed with exit code $gitExitCode."
  }
  ```

- Capture `$LASTEXITCODE` immediately before another native command can overwrite it. Respect tools that use documented nonzero statuses for nonfatal results.
- `$PSNativeCommandUseErrorActionPreference` changes how nonzero exits integrate with PowerShell's error handling on supported PowerShell versions, but it does not remove the need to understand and test the native command's exit contract.
- Prefer direct invocation over `Start-Process` when output, errors, or exit status are required. When `Start-Process` is necessary, use `-Wait -PassThru`, inspect `ExitCode`, and validate platform-specific argument quoting.
- Never build a command string from untrusted values or use `Invoke-Expression` as an argument parser.

## Mutation and Confirmation

Use `ShouldProcess` for filesystem, registry, service, package, account, permission, cloud, remote, process, certificate, scheduled-task, and configuration changes.

```powershell
function Remove-ProjectArtifact {
    [CmdletBinding(SupportsShouldProcess, ConfirmImpact = 'High')]
    param(
        [Parameter(Mandatory, ValueFromPipelineByPropertyName)]
        [Alias('FullName')]
        [string]$LiteralPath,

        [switch]$Force
    )

    process {
        $target = Resolve-ValidatedProjectPath -LiteralPath $LiteralPath

        if ($Force -and -not $PSBoundParameters.ContainsKey('Confirm')) {
            $ConfirmPreference = 'None'
        }

        if (-not $PSCmdlet.ShouldProcess($target, 'Remove project artifact')) {
            return
        }

        if (-not $Force -and -not $PSCmdlet.ShouldContinue(
                "Remove '$target' permanently?",
                'Irreversible removal'
            )) {
            return
        }

        Remove-Item -LiteralPath $target -Recurse -Force -Confirm:$false
    }
}
```

- `-Force` may suppress automatic confirmation or an extra `ShouldContinue`, but `ShouldProcess` must still execute so `-WhatIf` wins.
- Use `ShouldContinue` only for an extra high-risk confirmation after `ShouldProcess`. Provide `-Force` so unattended callers can suppress it.
- Describe the target and operation accurately. For a multi-target command, call once per independently skippable target; for an atomic transaction, describe and confirm the whole transaction once.
- Keep discovery and validation outside the approved mutation block when safe, but do not perform state changes while calculating a `ShouldProcess` message.
- After handling confirmation at the public boundary, suppress duplicate prompts in the inner cmdlet with `-Confirm:$false`. Do not call the inner mutation at all when `ShouldProcess` returns false.
- Test default execution, `-WhatIf`, `-Confirm:$false`, `-Force`, and `-Force -WhatIf`. The last combination must not mutate.

## Filesystem and Process Safety

- Use `Join-Path`, `[System.IO.Path]`, and `-LiteralPath` instead of manual separators or wildcard interpretation.
- Resolve existing paths before mutation. For new paths, resolve the existing parent, combine the leaf, normalize with `GetFullPath()`, and compare against the intended root using platform-appropriate case semantics.
- Reject an empty path, filesystem root, home directory, workspace root, unresolved environment variable, unintended ancestor, and target outside the authorized root before recursive delete or move.
- Avoid unresolved globs for destructive targets. Inventory concrete candidates, validate each absolute path, and mutate those exact paths.
- On Windows, use PowerShell cmdlets end to end for filesystem mutations. Do not feed PowerShell-discovered paths into `cmd /c`, batch built-ins, or a second shell.
- Never recursively enumerate a cloud-sync root. Set the working directory to the exact repository and search relative paths with the repository's normal ignore configuration.
- Create temporary directories beneath `[System.IO.Path]::GetTempPath()` with a unique leaf. Track what the current operation created and remove only that exact validated target in `finally` or after successful evidence capture.
- Separate external-command dry-run/read modes from mutation modes. Display the resolved executable, target, and effective arguments without exposing secrets.
- Use `Start-Process -WindowStyle Hidden` for noninteractive background helpers on Windows unless the user needs a visible interactive window.

## Security, Remoting, and Host Boundaries

- Treat script text, configuration, remote output, registry values, event logs, API responses, and native-tool output as untrusted data. Never execute text merely because it came from a trusted transport.
- Accept credentials as `[pscredential]`, platform credential-store references, or the repository's established secret mechanism. `SecureString` reduces accidental display but is not a portable encrypted storage format by itself.
- Do not pass secrets in command-line arguments when a tool supports standard input, environment injection scoped to the process, a credential object, or a protected file.
- Scope remoting targets explicitly, use session options intentionally, clean up sessions/jobs in `finally`, and distinguish local from remote paths, modules, preferences, and credentials.
- Do not disable certificate validation, weaken TLS, change execution policy, or enable remoting as a convenience fix. Explain the actual trust or host prerequisite instead.
- Treat elevation as a separate execution context with different profiles, environment, drives, credentials, and module paths. Revalidate targets after elevation.
- Account for constrained language mode, JEA endpoints, noninteractive hosts, redirected output, CI, scheduled tasks, services, and hosts without a full terminal when they are supported scenarios.

## Modules, Manifests, Profiles, and Packaging

- Keep a clear source layout, normally public and private functions under a module root with one `.psm1` entrypoint and one `.psd1` manifest. Follow the existing repository if it already uses a build step or generated module.
- Export public functions intentionally with `Export-ModuleMember` and explicit `FunctionsToExport`, `CmdletsToExport`, `AliasesToExport`, and `VariablesToExport`. Avoid wildcard exports for a stable package.
- Keep the source manifest, built manifest, documentation, and tests aligned on `RootModule`, `ModuleVersion`, GUID, prerequisites, compatible editions, nested/required modules, and file lists.
- Run `Test-ModuleManifest`, import the built artifact in a clean `pwsh -NoProfile` process, inspect `Get-Command -Module`, and execute public smoke tests.
- Test module unloading/reimport when state, classes, type data, format data, argument completers, or event subscriptions are involved.
- Keep profile code fast and idempotent. Guard optional modules and host-specific UI; one missing tool must not prevent the shell from starting.
- Prefer PSResourceGet for new repository/gallery workflows when the project supports it, but preserve PowerShellGet when compatibility or existing automation requires it.
- Inspect package contents and repository metadata before publishing. Do not register repositories, trust publishers, sign code, upload packages, or publish a version without explicit authorization.

## Documentation and Performance

- Add comment-based help to public commands with accurate `.SYNOPSIS`, `.DESCRIPTION`, `.PARAMETER`, `.EXAMPLE`, `.INPUTS`, `.OUTPUTS`, and relevant `.NOTES`/links. Do not document parameters the binder does not expose.
- Make examples executable, non-destructive by default, and representative of pipeline and `-WhatIf` behavior. Verify them against the built module when practical.
- Keep help adjacent to source unless the repository intentionally generates external help with platyPS or another build pipeline. Update the authoritative source, not generated output alone.
- Prefer clarity until measurement proves a hot path. For in-memory loops, `foreach` is often cheaper than `ForEach-Object`; for composability and streaming, a pipeline may be the correct tradeoff.
- Avoid repeated array concatenation, repeated module imports, per-record network setup, unnecessary `Get-ChildItem -Recurse`, and unbounded parallelism.
- Bound concurrency and preserve deterministic output/error handling. Test cancellation, timeout, partial failure, and cleanup for jobs, runspaces, thread jobs, and `ForEach-Object -Parallel`.

## Validation Matrix

Adapt to the repository instead of inventing a parallel toolchain:

```powershell
# Parse every tracked script without executing it.
$parseErrors = $null
[System.Management.Automation.Language.Parser]::ParseFile(
    $scriptPath,
    [ref]$null,
    [ref]$parseErrors
) | Out-Null

# Static analysis.
Invoke-ScriptAnalyzer -Path $sourceRoot -Recurse -Settings $settingsPath

# Tests and module packaging.
Invoke-Pester -Configuration $pesterConfiguration
Test-ModuleManifest -Path $manifestPath
```

For the supported matrix, verify as applicable:

- fresh process with `-NoLogo -NoProfile -NonInteractive`
- Windows PowerShell 5.1 and each supported PowerShell 7 line
- Windows, Linux, and macOS
- ordinary and elevated execution
- interactive and redirected/noninteractive hosts
- clean import, repeated import, and package-layout import
- analyzer findings, Pester tests, help, examples, signatures, and CI artifacts

## Primary References

- [Required Development Guidelines](https://learn.microsoft.com/powershell/scripting/developer/cmdlet/required-development-guidelines)
- [Strongly Encouraged Development Guidelines](https://learn.microsoft.com/powershell/scripting/developer/cmdlet/strongly-encouraged-development-guidelines)
- [Everything about ShouldProcess](https://learn.microsoft.com/powershell/scripting/learn/deep-dives/everything-about-shouldprocess)
- [about_Preference_Variables](https://learn.microsoft.com/powershell/module/microsoft.powershell.core/about/about_preference_variables)
- [PSScriptAnalyzer overview](https://learn.microsoft.com/powershell/utility-modules/psscriptanalyzer/overview)
