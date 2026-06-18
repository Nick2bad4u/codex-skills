---
name: code-review-maintenance
description: Review and improve repositories, files, configurations, and low-confidence review claims. Use when Codex is asked to review a codebase or file, fix brittle or hacky implementation choices, normalize duplicated logic or consistency drift, or triage AI review comments without accepting speculative claims.
---

# Code Review Maintenance

Use this skill for review-driven work where the main risk is correctness, maintainability, security, release safety, or test coverage. Start from the user's requested scope and do not widen it unless the evidence shows a shared failure pattern.

## Scope Modes

- Whole-repo review: stay read-only unless the user asked for fixes. Report findings first, ordered by severity.
- File review: read the target file plus direct callers, tests, types, and related utilities before changing anything.
- Review loop: fix one focused batch at a time, validate it, then continue only while the next issue is high-confidence.
- Consistency and dedupe: normalize drift only when there is real correctness, maintenance, testing, or public-surface risk.
- Brittle fix cleanup: prefer structured APIs and existing helpers over regex/string parsing, unsafe casts, broad catch/fallback behavior, magic constants, and overfit tests.
- Low-confidence AI review: verify every claim from source evidence before accepting it.

## Workflow

1. Inspect the current worktree and preserve unrelated user changes.
2. Identify the relevant code paths, tests, docs, scripts, generated surfaces, and public API contracts.
3. Prioritize issues that can cause real failures: incorrect behavior, security exposure, data loss, broken releases, API drift, fragile concurrency, dependency risk, CI hazards, or critical missing tests.
4. For review-only requests, do not edit files or run mutating commands.
5. For fix requests, implement only high-confidence changes and keep edits scoped to the affected paths.
6. Validate touched behavior with targeted tests, lint, typecheck, docs, package checks, or an equivalent local command.

## Output

For reviews, report findings first. Include location, impact, evidence, confidence, recommended fix, and suggested validation. If there are no serious findings, say so and list residual risk.

For fix work, finish with issues handled, changed files, validation commands, and follow-up work that needs user judgment.
