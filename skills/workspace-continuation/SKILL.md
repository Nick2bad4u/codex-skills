---
name: workspace-continuation
description: Generates compact handoffs and continues active plans from workspace state. Use when resuming work, carrying a plan through implementation and validation, or summarizing work for a fresh session without rediscovery.
---

# Workspace Continuation

Use this skill for continuity tasks that depend on current workspace state and prior progress.

## Continue Work

1. Resume from the actual workspace state rather than restarting from scratch.
2. Inspect changed files, command output, TODOs, tests, and relevant conversation notes to determine what remains.
3. Preserve unrelated user changes and do not redo finished work unless current evidence proves it is wrong.
4. Continue with the next concrete action until the task is complete or a real blocker remains.
5. Verify the requested outcome with changed files, passing commands, reproduced behavior, or a clear blocker explanation.

## Implement A Plan

1. Read the plan and inspect the files, data paths, and tests it affects.
2. Confirm the plan still matches the current code. If stale, adapt it conservatively and explain the adjustment.
3. Check the worktree before editing and preserve unrelated user changes.
4. Make focused changes that follow existing project patterns.
5. Run relevant formatter, lint, typecheck, tests, or equivalent validation for touched areas.

## Write A Handoff

Include objective, current status, working directory, branch, dirty files, files changed or inspected, decisions made, commands run and results, remaining work in priority order, blockers, risks, and assumptions. Keep it compact but specific enough for a fresh session to resume.

## Output

Finish with what changed or what remains, why it matches the plan or current objective, and the verification evidence.
