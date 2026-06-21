---
name: agent-skill-instruction-creation
description: Creates new agent skill and instruction surfaces including SKILL.md folders, AGENTS.md, AGENTS.override.md, CLAUDE.md, copilot-instructions.md, and Cursor rules. Use when asked to bootstrap, design, scaffold, migrate, or author reusable skills, project guidance, or agent workspace instructions.
---

# Agent Skill Instruction Creation

Use this skill to create agent-facing instructions that are grounded in the target project, not generic prompt prose. Prefer the smallest durable surface that matches the requested scope.

## Choose The Surface

- Use `AGENTS.md` for durable repository conventions, setup commands, validation expectations, review priorities, and local workflow rules.
- Use nested `AGENTS.md` or `AGENTS.override.md` files when a subdirectory needs different commands, constraints, generated-code rules, or ownership boundaries.
- Use fallback names such as `CLAUDE.md`, `.github/copilot-instructions.md`, Cursor rules, or configured project-doc filenames only when the target agent or existing repo convention requires them.
- Use a skill when the user needs a reusable task workflow with procedural knowledge, optional scripts, references, or assets.
- Use a plugin when distribution needs more than a local skill folder, such as bundled skills plus apps, MCP configuration, hooks, or install metadata.
- Do not create an agent instruction file to store secrets, credentials, private tokens, or one-off task notes.

## Discovery Workflow

1. Identify the target agent clients and current discovery rules before creating files.
2. Inspect package metadata, lockfiles, build scripts, CI workflows, test directories, docs, existing style configs, security tooling, deployment notes, and generated-file patterns.
3. Ask only when the repo cannot answer a durable decision, such as team policy, preferred validation gates, publishing intent, or whether guidance should apply globally or to one subtree.
4. Draft from project evidence: exact commands, paths, package manager, module boundaries, review expectations, and failure recovery steps.
5. Keep instructions compact and procedural. Avoid broad persona text, duplicated README content, and generic "be careful" guidance.

## AGENTS.md Creation

Create plain Markdown with headings that fit the project. Common sections:

- Repository purpose and boundaries.
- Setup, build, test, lint, typecheck, format, and release commands.
- Code style, architecture, generated-file, dependency, and migration rules.
- Security, secrets, data handling, network, destructive-command, and permission boundaries.
- Review guidelines with project-specific P0/P1 risks.
- Validation expectations and what to do when commands are slow, unavailable, or flaky.

Make commands copy-pasteable and real. Mention nested precedence only when the repo has or needs nested instruction files.

## Skill Creation

Create skills as small folders with a required `SKILL.md`, plus optional `scripts/`, `references/`, `assets/`, and `agents/openai.yaml` when the target client uses it.

1. Name the skill with lowercase hyphen-case and match the folder name.
2. Put only `name` and `description` in frontmatter unless the target repository explicitly allows broader Agent Skills metadata.
3. Write the description for triggering: front-load user intent, include realistic trigger words, define boundaries, and stay under the current spec limit.
4. Write the body as a reusable workflow using imperative steps, source-of-truth rules, validation loops, gotchas, and output expectations.
5. Add references only for bulky or variant-specific material that should load on demand.
6. Add scripts only for deterministic repeated logic, and make them self-contained with clear dependencies and error messages.
7. Add assets only when the skill needs templates, icons, fonts, sample files, or other output resources.
8. Add trigger eval prompts or forward tests for complex skills when practical, including near-miss prompts that should not trigger.

## Validation

- Run repo-local validation first, such as `npm run validate`, markdown lint, schema checks, or generator scripts.
- Use `skillcheck` when available to check SKILL.md format, references, description quality, sizing, and cross-agent compatibility.
- Use `npx agentlinter` when available to score AGENTS.md/CLAUDE.md-like workspaces for clarity, completeness, security, and consistency.
- For Codex skills, verify `agents/openai.yaml` against the current SchemaStore/OpenAI metadata shape when that file is present.
- If the new instruction surface changes expected behavior materially, sanity-test it with realistic prompts or a fresh Codex run when practical.

## Output

Finish with files created, why each surface belongs at that scope, commands run, and any policy choices the user still needs to decide.
