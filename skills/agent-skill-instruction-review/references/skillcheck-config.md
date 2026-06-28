# skillcheck Strict Config

Use this reference when reviewing a skill package that uses `skillcheck` or when adding a strict config during remediation.

## Baseline Config

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

## Review Meaning

- `max-tokens` and `max-lines`: identify oversized skills that should move bulky material into `references/`.
- `min-desc-score`: checks whether the trigger description is concrete enough to select the skill reliably.
- `strict-vscode` and `strict-cursor`: tighten checks for metadata and compatibility with those consumers.
- `target-agent = "all"`: expects a portable package and may surface cross-agent compatibility problems.
- `[frontmatter].extension_fields`: allows package formats with extra metadata fields. This conflicts with repositories that require only `name` and `description`; follow the repo-local schema first.
- `semantic = true`: enables deeper semantic and graph-style linting. Review findings can involve relationships across `SKILL.md`, references, scripts, assets, metadata, links, trigger claims, and cross-agent compatibility. Treat them as evidence leads, not automatic fixes.

## Review Procedure

1. Run the repository's validator before external lint tools.
2. Run `skillcheck <path>` and, when semantic checks are not already configured, `skillcheck <path> --semantic`.
3. Inspect graph or semantic findings against actual files: missing references, dead links, unreferenced bundled resources, unsupported metadata, trigger/body mismatches, and cross-agent drift are often real; wording preferences may be advisory.
4. Do not widen frontmatter allowances just to silence `skillcheck` if the repository's own schema intentionally rejects extension fields.
