---
name: test-quality-maintenance
description: Add, repair, and improve tests and coverage. Use when Codex needs to generate unit tests, fix failing tests, improve meaningful coverage, test error handling, add Playwright end-to-end tests, or create focused performance benchmarks.
---

# Test Quality Maintenance

Use this skill for test work where the goal is behavior confidence, not line-count padding.

## Shared Workflow

1. Inspect the implementation, public API, existing tests, fixtures, mocks, helpers, and project conventions.
2. Reproduce failing output when available.
3. Fix root causes rather than updating assertions to match broken behavior.
4. Add tests for real behavior: normal cases, edge cases, invalid input, async paths, failure paths, cleanup/rollback, integration boundaries, fixers, public API contracts, and user-facing messages.
5. Keep mocks faithful to real behavior and avoid brittle sleeps or snapshots unless the project intentionally uses them.
6. Run targeted tests first, then broader test, coverage, lint, typecheck, or build commands when warranted.

## Coverage Work

Use coverage reports to prioritize high-risk and under-tested files. Aim for configured thresholds, but do not add empty assertions or tests that only execute lines. Document any intentional untested paths with a clear reason.

## Playwright E2E

Inspect app structure, existing Playwright config, fixtures, selectors, auth helpers, and CI constraints. Cover the user journey end to end with stable selectors and deterministic setup. Include meaningful failure, loading, permission, and responsive states when they are part of the workflow.

## Error Handling

Cover validation errors, external service failures, filesystem or network failures, auth failures, cleanup/rollback, retry behavior, logging, UI error boundaries, and user-facing messages. Assert that sensitive data is not logged or exposed.

## Performance

Only add benchmarks when the project already supports them or the user explicitly wants a benchmark harness. Reuse existing thresholds and CI patterns. Measure latency, allocation, scaling, render time, I/O count, or query count as appropriate. Avoid noisy CI blockers unless the project already has stable budgets.

## Output

Finish with scenarios covered, bugs fixed, files changed, commands run, coverage result when relevant, and any remaining test gaps.
