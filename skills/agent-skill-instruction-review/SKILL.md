---
name: agent-skill-instruction-review
description: Audits and improves agent skill and instruction surfaces including SKILL.md, AGENTS.md, AGENTS.override.md, CLAUDE.md, Copilot instructions, and Cursor rules. Use when asked to lint, score, modernize, de-duplicate, secure, or repair reusable skills or project agent guidance.
---

# Agent Skill Instruction Review

Use this skill to treat agent-facing instructions as maintained project code. Start from the user's requested files or repository scope, then judge the instructions against the actual project, the active agent client, and the intended workflow.

## Source Of Truth

- For Codex behavior, prefer current OpenAI Codex docs/manual when behavior may have changed.
- For open Agent Skills portability, check the current Agent Skills specification and best-practice docs when format details matter.
- For AGENTS.md portability, treat AGENTS.md as plain Markdown with no required fields; nested files can specialize guidance closer to the work area.
- For repo-specific skill packages, obey the repository's own schema, validators, metadata rules, and install paths even when the broader spec allows more fields.
- Do not let linter scores override clear project evidence. Use findings as leads, not authority.

## Review Workflow

1. Inventory relevant instruction files, skill folders, metadata, scripts, references, assets, and nested overrides.
2. Identify the active consumer: Codex, Claude Code, GitHub Copilot, Cursor, Windsurf, OpenClaw, another agent, or a portable mix.
3. Read nearby code, package metadata, test scripts, CI workflows, docs, and existing commands before judging guidance.
4. Check discovery rules and scope: global versus repo guidance, nested override precedence, fallback filenames, skill locations, and duplicate skill names.
5. Check structure, clarity, completeness, security, cross-file consistency, and token/context cost.
6. For SKILL.md, verify name/folder match, frontmatter constraints, trigger description quality, progressive disclosure, relative file references, and whether scripts or references are justified.
7. For AGENTS.md-like files, verify commands are real, precedence is clear, validation expectations are actionable, review guidance is concrete, and security boundaries are explicit.
8. Run applicable validators when practical, then reconcile findings with source evidence before editing or reporting.

## Optional Tools

- Run repo-local validation first, such as `npm run validate`, markdown lint, schema checks, or custom scripts.
- Use `skillcheck <path>` for SKILL.md static analysis when available; it can flag frontmatter, description quality, sizing, references, and cross-agent compatibility.
- Use `npx agentlinter` for AGENTS.md/CLAUDE.md-style workspace checks when available; treat generated reports as advisory and inspect proposed fixes before applying them.
- Use secret scanners already configured by the repo when guidance files include tokens, keys, private URLs, or copied logs.

## Review Criteria

- Instructions must be specific enough to change agent behavior: exact package managers, commands, paths, review priorities, and escalation points beat vague style advice.
- Instructions must not conflict across files. If they do, preserve the narrower or newer project truth and remove stale duplication.
- Durable guidance belongs in AGENTS.md-like files; reusable task workflows belong in skills; local runtime settings belong in config; installable bundles belong in plugins.
- Skill descriptions must front-load trigger intent, include realistic keywords and boundaries, stay concise, and avoid claiming every nearby task.
- Skill bodies should be procedural, imperative, compact, and reusable. Move bulky variant details into focused references only when they materially reduce loaded context.
- Scripts should be self-contained, deterministic, documented by usage, and worth the maintenance cost. Do not hide risky network, eval, install, credential, or deletion behavior inside skill scripts.
- Security guidance must call out sensitive data handling, untrusted external content, prompt-injection boundaries, dangerous shell patterns, and permission expectations where relevant.
- Validation guidance must name commands that exist and explain when to run targeted versus broad checks.

## Fix Workflow

When the user asks for improvements, make focused edits instead of rewriting every instruction file.

1. Preserve user-specific policy and project voice unless it is stale, unsafe, or impossible to follow.
2. Replace vague directives with verifiable procedures, commands, examples, or scope boundaries.
3. Remove outdated commands only after proving their replacement from package metadata, CI, docs, or maintainer notes.
4. Keep Markdown simple. Avoid large persona blocks, motivational text, and restating generic coding-agent behavior.
5. Re-run the relevant validators and lint tools. If a tool is unavailable or would require installing new dependencies, state that in the result.

## Output

For reviews, lead with findings by severity and include file, impact, evidence, confidence, and a concrete fix. For fix work, finish with changed instruction surfaces, validation commands, remaining risks, and any current-doc sources used.
