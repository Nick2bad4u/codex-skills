# AGENTS.md

## Repository Purpose

This repository stores multiple personal Codex skills under `skills/<skill-name>`. It is local-first and private unless the owner decides a skill should be promoted to a standalone published repository.

## Skill Rules

- Each skill folder must contain `SKILL.md`.
- Each `SKILL.md` frontmatter must include only `name` and `description`.
- Skill names use lowercase hyphen-case and match their folder names.
- Keep skill bodies compact and procedural. Do not paste long prompt text verbatim when a smaller durable workflow is enough.
- Put detailed variant-specific guidance in `references/` only when it materially reduces context or improves reuse.
- Add scripts only when deterministic execution is better than repeated agent reasoning.
- Keep `agents/openai.yaml` aligned with `SKILL.md`.

## Repo Rules

- Validate with `npm run validate` after skill changes.
- Run `npm run format:check` before committing.
- Do not add npm publishing workflows until the owner explicitly decides to publish.
- Do not remove installed skills from `C:\Users\Nick\.agents\skills` unless explicitly requested.
- Prefer focused edits. Avoid turning this repo into a dump of one-off prompts.
