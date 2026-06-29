---
name: release-publish-loop
description: "Execute authorized release publishing: validate and commit changes, push to GitHub, watch CI and SonarCloud/SonarQube quality gates, fix failed checks, choose semver, dispatch publish or release workflows, and verify artifacts. Use when the user explicitly asks Codex to push and release."
---

# Release Publish Loop

Use this skill when the user authorizes an end-to-end release process that can mutate the remote repository and publish artifacts. For read-only readiness checks, use `ci-release-readiness` instead.

## Boundaries

1. Do not push, tag, publish, or dispatch release workflows unless the user explicitly asked for that full loop.
2. Do not skip failing checks, weaken gates, bypass branch protection, or publish from a dirty or unverified state.
3. Do not infer the release type from commit labels alone. Use actual changes since the last reachable release tag.
4. Stop before publishing if secrets, npm auth, signing, protected environment approval, or workflow permissions are missing and cannot be verified.
5. Preserve unrelated user changes. If unrelated local work exists, commit only the intended release changes or stop and ask.

## Initial Inspection

1. Confirm repository, branch, upstream, default branch, and dirty state.
2. Read repo instructions, release docs, package metadata, changelog config, publish workflow, CI workflows, and commit-message rules.
3. Identify release commands and gates from the repo, such as `release:verify`, `release:check`, `pack:dry-run`, docs build, or package validation.
4. Identify publish mechanism: GitHub Actions `workflow_dispatch`, tag push, npm publish script, GitHub release workflow, Pages deployment, or another registry.
5. Identify external quality gates when configured, including SonarCloud or SonarQube project keys, `sonar-project.properties`, scanner workflow steps, and GitHub checks.
6. Read `references/release-loop-checklist.md` when the repo release path is unfamiliar or multiple workflows could publish.

## Local Validation And Commit

1. Run the closest local gate before pushing. Prefer the repo's aggregate release gate when practical.
2. Fix root-cause failures in code, tests, config, docs, generated outputs, workflows, or dependencies.
3. Rerun the failed command and then the broader release gate.
4. If changes need committing, follow the repository commit-message instructions. Stage explicit paths, verify `git diff --cached --check`, and commit coherent groups.
5. Confirm the final local tree is clean or contains only unrelated changes that the user intentionally left out.

## Push And Watch CI

1. Push the intended branch to its upstream.
2. Confirm local `HEAD` matches the remote branch SHA.
3. List GitHub Actions runs for that exact commit and branch. Watch all required CI/security/release-readiness runs tied to the pushed commit.
4. If SonarCloud or SonarQube is configured, treat its quality gate and GitHub check as required. Inspect check details, annotations, scanner logs, and actionable findings; fix root causes in code, tests, docs, or configuration before publishing.
5. If CI or Sonar fails, inspect annotations and logs before changing files. Fix the root cause, validate locally, commit, push, and watch the new commit.
6. Repeat until required CI and configured quality gates pass or a precise external blocker remains.

## Semver Decision

1. Use the semver-release-recommender workflow when available.
2. Determine the latest reachable SemVer tag and analyze actual diffs from that tag to `HEAD`.
3. Inspect public package surfaces: exports, CLI names, config keys, schemas, generated types, docs, package files, engines, peers, and runtime dependencies.
4. Recommend `patch`, `minor`, or `major` with confidence and evidence.
5. If the publish workflow accepts both explicit version and bump type, prefer the repo's established release path. Do not invent a versioning scheme.

## Publish Workflow

1. Confirm all required CI and configured SonarCloud/SonarQube quality gates for the target commit passed.
2. Confirm the target version or bump does not already exist in the registry or release system.
3. Dispatch the publish workflow using the repo's documented inputs, or push the release tag only when that is the documented trigger.
4. Watch the publish workflow to completion.
5. If publishing fails, inspect logs. Fix workflow/package issues only when safe, then rerun the release loop from validation. If the failure is credentials, approval, OTP, protected environment, registry outage, or already-published version, report the blocker instead of retrying blindly.

## Final Verification

Verify the published artifact from the consumer side:

- GitHub release or tag points to the intended commit.
- Registry version exists and metadata is correct.
- Release asset, package tarball, docs site, or container image is present.
- Installed package or downloaded artifact contains expected files when packaging changed.
- Local tree and branch status are clean and understandable.

## Output

Finish with the pushed commit, CI runs watched, semver recommendation, publish workflow run, published version/artifacts, verification commands, and any remaining manual actions.
