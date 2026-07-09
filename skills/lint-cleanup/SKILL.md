---
name: lint-cleanup
description: Validates and repairs lint, ESLint, and static-analysis diagnostics at the root cause. Use when running lint, resolving errors/warnings, removing unnecessary disable comments, or replacing suppressions with code, type, config, or test fixes.
---

# Lint Cleanup

Use this skill for lint failures and lint hygiene tasks where the goal is a clean rerun without weakening the gate.

## Workflow

1. Inspect the repo's package manager, lint scripts, lint config, typed-lint project boundaries, and any user-provided diagnostics.
2. Run the relevant lint command unless the user already supplied exact current output.
3. Use autofix commands only as a starting point when the project provides them.
4. Manually review remaining diagnostics and fix root causes.
5. Prefer code, type, config, docs, or test fixes over suppressions.
6. Do not add blanket disables, broad ignores, unsafe casts, mass exceptions, or rule downgrades unless the user explicitly approves.
7. If behavior changes, run targeted tests as well as lint.
8. Rerun lint after each logical batch.

## ESLint Disable Cleanup

Use unused-disable reporting when available. For every remaining disable, identify the exact rule and diagnostic, try to remove it by improving the code locally, keep only narrowly scoped justified disables, and add or improve reason comments when a disable must remain.

## Output

Finish only when lint is clean or every remaining issue has a concrete blocker. Report diagnostics fixed, suppressions removed or retained with rationale, commands run, and validation results.
