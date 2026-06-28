---
name: python-strict-development
description: Maintain Python projects with strict Ruff, mypy, Pyright, pytest, editor, and package-script quality gates. Use when Codex needs to create, audit, repair, or apply strict Python lint, format, typecheck, test, compile, or VS Code tooling practices.
---

# Python Strict Development

Use this skill when Python code should meet the user's strict local quality bar rather than a minimal lint setup. Start from the current repository and adapt paths, package names, Python version, and CI commands before editing.

## Source Priority

1. Read `pyproject.toml`, `package.json`, `.vscode/settings.json`, requirements files, lockfiles, CI workflows, and existing tests before changing tools.
2. Prefer existing repo conventions when they are already strict and working.
3. Use [strict-tooling.md](references/strict-tooling.md) when adding or repairing Ruff, mypy, Pyright, pytest, VS Code, or npm-script configuration.
4. Use [project-shapes.md](references/project-shapes.md) when the repository is not a simple `scripts` + `tests` project.
5. Use [strict-fix-patterns.md](references/strict-fix-patterns.md) when strict diagnostics are valid but the right code fix is not obvious.
6. Use `scripts/audit_python_strict.py` for a read-only strict profile audit before or after manual config edits.
7. Do not weaken strict diagnostics, broad Ruff rule selection, or typecheck gates just to get a quick pass. Fix code or add narrow, justified ignores.

## Workflow

1. Inventory Python entrypoints, import roots, test roots, minimum supported Python version, direct script execution requirements, and first-party module names.
2. Confirm the active environment can run the expected tools: `ruff`, `mypy`, `pyright`, `pytest`, and `python -m compileall`.
3. Configure or repair the project around one strict gate:
   - `ruff check` plus `ruff format --check`
   - `mypy` with `strict = true` and extra error codes
   - `pyright` in strict mode with explicit diagnostics
   - `pytest` strict config, strict markers, strict config, and warning errors
   - `python -m compileall` over source and tests
4. Add npm package scripts only when the repository already uses npm as the task runner or the user asks for cross-language scripts.
5. Keep ignores local and documented. Prefer `per-file-ignores` for CLI entrypoints, direct-execution bootstrap code, dynamic API boundaries, and pytest asserts.
6. Keep editor settings in `.vscode/settings.json` aligned with repo config: Ruff uses filesystem config first, Pyright/Pylance runs workspace diagnostics, and tests use pytest.
7. Run `python <skill>/scripts/audit_python_strict.py <repo>` when auditing strict-tooling drift, then inspect every failure before editing.
8. Run the narrow failing command after each fix, then run the aggregate gate.

## Python Code Standards

- Use explicit types at public and internal boundaries; avoid `Any` unless the boundary is genuinely dynamic.
- Prefer typed adapters for untyped third-party responses instead of spreading casts through business logic.
- Use `typing.override` where supported and let Pyright catch missing override markers.
- Use `pathlib`, `subprocess.run(..., check=True)` with fixed argument arrays, and structured exceptions.
- Keep CLI output and API/client logic separated enough that tests can assert behavior without scraping terminal output.
- Treat `# type: ignore[...]`, `# noqa: ...`, and Ruff per-file ignores as review surfaces that require a reason.

## Validation Commands

Prefer repo-local scripts when present. Otherwise run the equivalent direct commands:

```powershell
ruff check scripts tests
ruff format --check scripts tests
mypy scripts tests
pyright scripts tests
pytest
python -m compileall -q -x "[\\/]\\." scripts tests
```

For npm-backed Python repositories, prefer:

```powershell
npm run check:python
npm run lint:python
npm run typecheck:python
npm run test:python
```

## Output

Finish with the strict configuration surfaces changed, the commands run, any remaining justified ignores, and any tool or interpreter prerequisite that blocked validation.
