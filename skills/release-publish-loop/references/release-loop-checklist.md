# Release Loop Checklist

Use this checklist before a remote push or publish workflow dispatch.

## Contents

- [Repository State](#repository-state)
- [Local Gates](#local-gates)
- [GitHub CI](#github-ci)
- [External Quality Gates](#external-quality-gates)
- [Semver Evidence](#semver-evidence)
- [Publish Dispatch](#publish-dispatch)
- [Published Artifact Verification](#published-artifact-verification)

## Repository State

```powershell
git rev-parse --show-toplevel
git branch --show-current
git status --short --branch --untracked-files=all
git remote -v
git log -5 --oneline --decorate
```

- Is the branch the intended release branch?
- Are unrelated local changes absent, already committed, or intentionally excluded?
- Does the upstream remote match the repository the user wants to be released?
- Are tags fetched before semver analysis?

## Local Gates

Prefer repo-specific aggregate commands:

```powershell
npm run release:verify
npm run validate
npm run lint
npm run typecheck
npm test
npm pack --dry-run
```

Use equivalent package-manager or language commands when the repository is not npm-based. Do not publish from a failed or skipped gate unless the user explicitly accepts a documented external blocker.

## GitHub CI

After pushing:

```powershell
$sha = git rev-parse HEAD
git ls-remote origin "refs/heads/$(git branch --show-current)"
gh run list --branch "$(git branch --show-current)" --commit $sha --limit 30
gh run watch <run-id> --exit-status
```

For failures:

```powershell
gh run view <run-id> --log-failed
gh run view <run-id> --json jobs,conclusion,status,url
```

Fix source causes before rerunning. Do not rerun repeatedly without evidence of a transient failure.

## External Quality Gates

Check for configured scanners and quality gates before publishing:

```powershell
Test-Path sonar-project.properties
rg -n "sonar|SonarCloud|SonarQube|quality gate" .github package.json sonar-project.properties
gh run view <run-id> --json jobs,conclusion,status,url
```

- If SonarCloud or SonarQube is configured, inspect the GitHub check, scanner logs, quality gate result, and actionable findings.
- Fix root causes before publishing. Do not waive or ignore maintainability, reliability, security hotspot, vulnerability, coverage, or duplication failures unless the user explicitly accepts a documented false positive or external blocker.
- Revalidate locally where possible, then push and watch the replacement commit until the quality gate passes.

## Semver Evidence

```powershell
git fetch --tags --quiet
git tag --list "v[0-9]*.[0-9]*.[0-9]*" --sort=-v:refname
git describe --tags --abbrev=0 --match "v[0-9]*.[0-9]*.[0-9]*"
git log --oneline <tag>..HEAD
git diff --name-status <tag>..HEAD
git diff --stat <tag>..HEAD
```

Check package metadata when applicable:

```powershell
node -p "require('./package.json').version"
npm pack --dry-run --json
npm view <package>@<version> version
```

## Publish Dispatch

Inspect workflow inputs before dispatch:

```powershell
gh workflow list --all
gh workflow view <workflow.yml>
Get-Content .github/workflows/<workflow.yml>
```

Common dispatch shape:

```powershell
gh workflow run <workflow.yml> --ref <branch> -f release_type=<patch|minor|major>
gh run watch <run-id> --exit-status
```

Use the repository's actual workflow file, input names, and branch. If the workflow publishes on tag push, create or push tags only after CI and semver evidence are complete.

## Published Artifact Verification

Use checks that match the release target:

```powershell
gh release view <tag> --json tagName,targetCommitish,assets,url
git ls-remote --tags origin refs/tags/<tag>
npm view <package>@<version> version dist.tarball time --json
```

If packaging changed, install or inspect the published artifact rather than trusting the workflow summary alone.
