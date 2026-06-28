# Strict Python Fix Patterns

Use this reference when strict Ruff, mypy, Pyright, or pytest diagnostics are valid but the right fix is not obvious.

## Contents

- [Dynamic JSON And API Payloads](#dynamic-json-and-api-payloads)
- [argparse Boundaries](#argparse-boundaries)
- [Subprocess And Shell Rules](#subprocess-and-shell-rules)
- [Missing Stubs And Untyped Dependencies](#missing-stubs-and-untyped-dependencies)
- [Overrides And Inheritance](#overrides-and-inheritance)
- [pytest Patterns](#pytest-patterns)
- [Suppressions](#suppressions)

## Dynamic JSON And API Payloads

- Keep raw external data at the boundary as `object`, `Mapping[str, object]`, or a narrow `TypedDict`.
- Normalize payloads into typed dataclasses, `TypedDict`s, or small domain objects before business logic.
- Prefer helper functions such as `as_str(value, field)` or `require_mapping(value, field)` over repeated casts.
- Use `Any` only at the unavoidable dynamic boundary and keep it from spreading into internal functions.

## argparse Boundaries

- Build parsers in small functions and test parser defaults separately from command execution.
- Convert `argparse.Namespace` into a typed dataclass before calling business logic.
- Avoid reading private parser attributes unless no public API exists; justify `SLF001` locally if required.
- Keep `SystemExit` behavior in CLI tests explicit.

## Subprocess And Shell Rules

- Prefer fixed argument arrays with `subprocess.run([...], check=True)` over shell strings.
- Pass user-controlled values as arguments, not interpolated command text.
- Use `sys.executable` for Python subprocesses when invoking the current environment matters.
- Use PATH tools such as `git` only when the repo intentionally supports normal developer installations; justify `S607` locally.
- Capture output only when needed for behavior, diagnostics, or tests.

## Missing Stubs And Untyped Dependencies

- Install official stubs or package extras when available.
- For a small untyped dependency surface, write a local protocol or adapter rather than turning off missing-stub checks globally.
- Use `py.typed` for first-party typed packages that are distributed to other projects.
- Keep `ignore_missing_imports` scoped to a module only when no stubs or practical adapter exists.

## Overrides And Inheritance

- Use `typing.override` for overridden methods when supported by the configured Python version.
- Fix Pyright `reportImplicitOverride` by adding the marker, not by disabling the diagnostic.
- Keep subclass method signatures compatible with the base class; do not use broader ignores for variance errors.

## pytest Patterns

- Keep Ruff `S101` ignores scoped to tests because pytest rewrites `assert`.
- Use `pytest.raises(..., match=...)` for expected exceptions.
- Prefer `tmp_path`, `monkeypatch`, and `capsys` over shared filesystem state or brittle process-global changes.
- Avoid sleeps; use deterministic synchronization or direct function calls.
- Treat warnings as errors and add targeted warning assertions only when warning behavior is part of the contract.

## Suppressions

- Prefer code changes over `# noqa`, `# type: ignore[...]`, or config ignores.
- Include the exact rule or error code and a reason.
- Keep suppressions close to the line or file that needs them.
- Use per-file ignores for intentional file roles such as CLI output, direct script bootstrap, or pytest asserts.
- Remove stale suppressions when strict tools report them as unused.
