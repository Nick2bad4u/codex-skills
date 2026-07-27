# npm 12 Migration Reference

This reference captures the npm 12.0.1 baseline released on 2026-07-10. Before a migration, re-check the latest npm 12 release, engine range, command docs, and changelog because npm security policy and bug fixes can change within the major.

## Contents

- [Version Baseline](#version-baseline)
- [Lifecycle Script Policy](#lifecycle-script-policy)
- [Recommended Staging](#recommended-staging)
- [Dependency Source Policy](#dependency-source-policy)
- [Other Breaking Changes](#other-breaking-changes)
- [Validation Checklist](#validation-checklist)
- [Older Sources and Other Package Managers](#older-sources-and-other-package-managers)
- [Official Sources](#official-sources)

## Version Baseline

- npm 12.0.1 requires Node `^22.22.2 || ^24.15.0 || >=26.0.0`.
- npm 11 supports older Node releases, including Node 20. Upgrade Node before installing npm 12.
- npm 12 continues to use [lockfile version 3](https://docs.npmjs.com/cli/v12/configuring-npm/package-lock-json/) by default. A normal npm 11-to-12 migration does not require a wholesale lockfile schema rewrite.
- Pin an exact npm 12 release where the repository already pins package managers. Verify the executable in local shells, CI, containers, release jobs, and docs; `packageManager` alone may not select it.
- Use `npm view npm@12 version engines --json` and the official npm CLI releases to identify the current 12.x target. npm 12 `view --json` returns arrays, so automation must not assume the npm 11 scalar shape.

## Lifecycle Script Policy

### What Changed

[npm 11.16 introduced](https://github.com/npm/cli/pull/9360) `allowScripts`, approval commands, warnings, explicit denials, and strict enforcement. In npm 11, an unreviewed dependency script still runs unless strict mode is enabled. [npm 12 changes the default](https://github.com/npm/cli/pull/9424): unreviewed dependency install scripts are skipped and reported.

The policy covers dependency `preinstall`, `install`, `postinstall`, and `prepare` for non-registry sources. It does not require approvals for the root project or workspaces, which are owner-managed. A child workspace's own `allowScripts` field is ignored; the policy belongs in the workspace root.

### Root Policy

Prefer the management commands over hand editing:

```powershell
npm install-scripts ls --all=false
npm install-scripts approve sharp
npm install-scripts deny telemetry-pkg
npm install-scripts prune --dry-run
```

Approvals are pinned to installed versions by default. The resulting root field resembles:

```json
{
 "allowScripts": {
  "sharp@0.34.3": true,
  "esbuild@0.25.8 || 0.25.9": true,
  "telemetry-pkg": false
 }
}
```

Policy rules:

- Prefer exact pins or exact versions joined by `||`.
- A bare name or `name@*` applies to every version. Treat that as broader future trust.
- Semver ranges such as `^1`, `~1`, `>=1`, and dist-tags such as `@latest` are rejected.
- A denial wins when allow and deny entries overlap.
- Denials are name-only and survive `approve --all`.
- Package aliases must be approved by the underlying registry package name, not the alias.
- Git, remote tarball, `file:`, and directory dependencies use source identities. Let npm generate the key.
- Bundled dependency install scripts cannot be independently allowlisted. The parent package must expose required work through its own lifecycle.
- `prune --dry-run` finds approvals and denials that no longer match an installed package with an install script. Apply `prune` only after reviewing the preview.

`npm install-scripts` is workspace-unaware and always manages the root. Effective `all=true` from user config conflicts with `ls` and `prune`; override it with `--all=false` for those commands.

### Configuration Layers

The effective policy is selected from the highest applicable source:

1. CLI flags and environment variables
2. Non-empty root `package.json#allowScripts`
3. Project, user, and global `.npmrc`

Use the exact spelling and surface for each control:

| Control                                                                             | Configuration surface                                                                                                     | Expected value                                        |
| ----------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------- |
| [`allowScripts`](https://docs.npmjs.com/cli/v12/commands/npm-install-scripts/)      | Root `package.json`; normally managed with `npm install-scripts`                                                          | Object mapping package selectors to `true` or `false` |
| [`allow-scripts`](https://docs.npmjs.com/cli/v12/using-npm/config/)                 | npm config through CLI, environment, or `.npmrc`; principally for `npm exec`, `npx`, global installs, and fallback policy | Comma-separated package identities                    |
| [`strict-allow-scripts`](https://docs.npmjs.com/cli/v12/using-npm/config/)          | npm config, normally committed in project `.npmrc` for CI enforcement                                                     | Boolean; default `false`                              |
| [`dangerously-allow-all-scripts`](https://docs.npmjs.com/cli/v12/using-npm/config/) | npm config or CLI diagnostic override; never committed as project policy                                                  | Boolean; default `false`                              |
| [`allow-git`](https://docs.npmjs.com/cli/v12/using-npm/config/)                     | npm config, normally project `.npmrc` or CLI                                                                              | `none`, `root`, or `all`; default `none`              |
| [`allow-remote`](https://docs.npmjs.com/cli/v12/using-npm/config/)                  | npm config, normally project `.npmrc` or CLI                                                                              | `none`, `root`, or `all`; default `none`              |

Project-scoped `npm install`, `ci`, `update`, and `rebuild` reject a CLI `--allow-scripts` list. Commit team policy in the root package manifest. The CLI/config list is intended for `npm exec`, `npx`, and global installs:

```powershell
npm install -g --allow-scripts=canvas,sharp some-tool
npm config set allow-scripts=canvas,sharp --location=user
```

Audit user/global config because it can make a local install pass without portable repository policy. Do not print auth tokens or copy credential-bearing config into reports.

### Strict and Escape-Hatch Modes

- `strict-allow-scripts=true` fails when an unreviewed dependency script exists. On npm 11 it prevents those scripts from executing; on npm 12 it turns a blocked-script warning into a hard failure. This is a useful committed CI policy after approvals are complete.
- `ignore-scripts=true` suppresses package scripts and `.npm-extension`. Use it to create a safe inventory tree, not as final proof that the application builds.
- `dangerously-allow-all-scripts=true` bypasses approvals and explicit denials. Never commit it. Treat any diagnostic use as execution of untrusted code and require a specific reason.

`npm trust` is unrelated. It manages OIDC trusted-publisher relationships and permissions; it does not approve dependency lifecycle scripts.

## Recommended Staging

When starting from [npm `>=11.18.0 <12`](https://github.com/npm/cli/releases/tag/v11.18.0), which provides the namespaced `npm install-scripts` commands and `prune`:

1. Upgrade to npm 11.18.0 if necessary.
2. Run `npm ci --ignore-scripts` to create the actual dependency tree without lifecycle execution.
3. Run `npm install-scripts ls --all=false`.
4. Inspect each listed package's resolved identity, lifecycle commands, repository, published artifact, and why the project needs its generated output.
5. Approve or deny packages individually. Avoid `approve --all`.
6. Add `strict-allow-scripts=true` in the project `.npmrc` if new unreviewed scripts should fail CI.
7. Run a clean npm 11 install without `ignore-scripts` to prove the policy.
8. Switch Node/npm pins to npm 12 and repeat the clean install and full validation.

If npm 11.17 or older is the source, first introduce npm 11.18.0 only for inventory and policy staging, or use npm 12 with `--ignore-scripts` to build the inventory. npm 11.16 and 11.17 understand the earlier policy commands, but not the complete namespaced workflow above. Do not let the intermediate install run unreviewed scripts.

After a dependency update, re-run `ls`, update exact approval pins only after reviewing the new release, preview `prune`, and validate a clean install.

## Dependency Source Policy

The [npm 12.0.0 release notes](https://github.com/npm/cli/releases/tag/v12.0.0) and [npm configuration documentation](https://docs.npmjs.com/cli/v12/using-npm/config/) define these changed defaults:

- `allow-git=none`
- `allow-remote=none`

Values are `none`, `root`, or `all`:

- `root` permits only dependencies declared by the project root.
- `all` also permits transitive occurrences.
- Prefer `root` unless a reviewed transitive source is required.

Registry tarballs whose hostname matches the configured registry remain permitted. A private registry or mirror that serves tarballs from another host may require a correct `replace-registry-host` configuration or an explicit `allow-remote` decision.

`allow-file` and `allow-directory` remain `all` by default. Still audit them because local sources can execute lifecycle scripts and may behave differently in CI or published packages.

## Other Breaking Changes

The following baseline comes from the [npm 12.0.0 breaking changes](https://github.com/npm/cli/releases/tag/v12.0.0). Check later npm 12.x releases for additions, then migrate only surfaces used by the repository:

- `npm shrinkwrap`, the `shrinkwrap` config alias, and all `npm-shrinkwrap.json` loading are removed. Rename a root file to `package-lock.json`; use `bundleDependencies` when a published artifact must carry a dependency tree.
- Root `preinstall` now runs before dependencies are installed. It must not assume `node_modules` or dependency binaries already exist.
- Unknown CLI flags, abbreviated flags, and single-hyphen multi-character shorthands now error. Unknown `.npmrc` keys warn by default; `strict-npmrc=true` makes them errors.
- `npm adduser` is removed. Create accounts on the website and use `npm login` for CLI authentication.
- `npm star`, `npm stars`, and `npm unstar` are removed.
- Global installs no longer register system man pages. Use `npm help <command>`.
- `npm init` no longer supplies an ISC license by default.
- npm no longer rewrites `process.execPath` through `whichnode`.
- `npm view --json` always returns an array.
- `npm pkg` is no longer forced to JSON output.
- `npm pack --json` and `npm publish --json` share a new consistent shape.
- CycloneDX SBOM names now come from package manifests, which can change root and aliased component `name`, `bom-ref`, and `purl`.
- Git dependencies preserve HTTPS instead of automatically changing protocol.

Additive features such as `install-strategy=linked`, `packageExtensions`, and `npm patch` are not required migrations. Do not adopt them without a repository need.

`min-release-age` remains opt-in rather than a new npm 12 default. If the repository uses it, review `min-release-age-exclude`, `before` precedence, private-scope handling, and the nonzero result when the age window blocks an audit fix.

## Validation Checklist

- Confirm all intended environments report supported Node and the target npm 12 patch.
- Confirm a clean `npm ci` runs every required approved script and reports no unreviewed scripts.
- Confirm `npm install-scripts ls --all=false` is empty under controlled project/CI config.
- Confirm intentional denials do not remove runtime files the application needs.
- Run the repository's test, typecheck, lint, build, docs, package, and release-verification commands.
- Exercise native or platform-specific dependencies on each supported OS and architecture.
- Inspect the lockfile diff for source rewrites, removed packages, and unrelated churn.
- Test automation that parses `view`, `pkg`, `pack`, `publish`, or CycloneDX output.
- Test root `preinstall` from a genuinely clean tree.
- Test private registries, git dependencies, remote tarballs, local sources, proxies, and mirrors when present.
- Test global-install and `npx` workflows separately; they do not use root `package.json#allowScripts`.
- Review CI logs for skipped-script warnings even when the main build happens to pass.

## Older Sources and Other Package Managers

- npm 11.16-11.18 supplies the best staging path because it understands the policy while retaining npm 11 compatibility.
- From npm 10 or older, also review all npm 11 breaking changes that the repository skipped; do not assume the npm 12 delta is the only one.
- pnpm, Yarn, and Bun use different dependency-build trust fields and identity rules. Do not translate names mechanically. Install the npm lockfile tree without scripts, inventory it with npm, and create a new root `allowScripts` policy.
- Fields such as `trustedDependencies`, `onlyBuiltDependencies`, and `ignoredBuiltDependencies` are not npm's `allowScripts` policy. Preserve or remove them only according to the package manager the repository still supports.

## Official Sources

- [npm CLI v12.0.1 release](https://github.com/npm/cli/releases/tag/v12.0.1)
- [npm CLI v12.0.0 breaking changes](https://github.com/npm/cli/releases/tag/v12.0.0)
- [npm CLI v11.18.0 release](https://github.com/npm/cli/releases/tag/v11.18.0)
- [npm install-scripts](https://docs.npmjs.com/cli/v12/commands/npm-install-scripts/)
- [npm install](https://docs.npmjs.com/cli/v12/commands/npm-install/)
- [npm config](https://docs.npmjs.com/cli/v12/using-npm/config/)
- [npm package-lock.json](https://docs.npmjs.com/cli/v12/configuring-npm/package-lock-json/)
- [npm 11 allowScripts introduction](https://github.com/npm/cli/pull/9360)
- [npm 12 default-deny change](https://github.com/npm/cli/pull/9424)
- [Unknown `.npmrc` correction before stable](https://github.com/npm/cli/pull/9729)
