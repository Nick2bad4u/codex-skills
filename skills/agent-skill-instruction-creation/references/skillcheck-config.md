# skillcheck Strict Config

Use this reference when creating or updating a skill package that should be checked with `skillcheck`.

## Baseline Config

Place this in `skillcheck.toml` at the skill package root and adapt limits only when the repository has a documented reason.

```toml
max-tokens = 8000
max-lines = 750
min-desc-score = 25
strict-vscode = true
strict-cursor = true
target-agent = "all"
semantic = true

[frontmatter]
extension_fields = ["license", "metadata"]
```

## What The Options Mean

- `max-tokens` and `max-lines`: keep `SKILL.md` within a bounded context budget; move bulky details into `references/`.
- `min-desc-score`: require trigger descriptions to be specific enough for discovery rather than broad category labels.
- `strict-vscode` and `strict-cursor`: check editor/agent metadata and compatibility surfaces more strictly when those surfaces exist.
- `target-agent = "all"`: evaluate for portable multi-agent skill packages instead of only one consumer.
- `[frontmatter].extension_fields`: allow package formats that intentionally include fields such as `license` and `metadata`; omit this in repos that require only `name` and `description`.
- `semantic = true`: enable deeper semantic and graph-style linting. Expect checks that reason about relationships across `SKILL.md`, references, scripts, assets, agent metadata, links, trigger claims, and cross-agent compatibility. Treat findings as leads and inspect source files before applying fixes.

## Usage

Run the repo validator first, then `skillcheck`:

```powershell
npm run validate
skillcheck .
skillcheck . --semantic
```

If `skillcheck.toml` already sets `semantic = true`, the plain `skillcheck .` run should include the semantic checks. Use `--semantic` explicitly when testing a package that has no config file or when confirming graph linting behavior.

Do not copy this config into a repository whose validator rejects frontmatter extension fields. In those repos, keep `SKILL.md` frontmatter to the local schema and use `skillcheck` as advisory only.
