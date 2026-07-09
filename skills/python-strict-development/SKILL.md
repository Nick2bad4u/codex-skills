---
name: python-strict-development
description: Maintains strict Python projects with Ruff, mypy, Pyright, pytest, editor, and package-script gates. Use when creating, auditing, or repairing strict lint, format, typecheck, test, compile, or VS Code tooling practices.
---

# Python Strict Development

Use this skill when Python code should meet the user's strict local quality bar rather than a minimal lint setup. Start from the current repository and adapt paths, package names, Python version, and CI commands before editing.

## Source Priority

1. Read `pyproject.toml`, `package.json`, `.vscode/settings.json`, `requirements-dev.txt`, lockfiles, CI workflows, and existing tests before changing tools.
2. Prefer existing repo conventions when they are already strict and working.
3. Use [strict-tooling.md](references/strict-tooling.md) when adding or repairing Ruff, mypy, Pyright, pytest, VS Code, or npm-script configuration.
4. Use [project-shapes.md](references/project-shapes.md) when the repository is not a simple `scripts` + `tests` project.
5. Use [strict-fix-patterns.md](references/strict-fix-patterns.md) when strict diagnostics are valid but the right code fix is not obvious.
6. Use `scripts/audit_python_strict.py` for a read-only strict profile audit before or after manual config edits.
7. Do not weaken strict diagnostics, broad Ruff rule selection, or typecheck gates just to get a quick pass. Fix code first; use only narrow, justified ignores after proving the tool finding is intentionally tolerated.

## Workflow

1. Inventory Python entrypoints, import roots, test roots, minimum supported Python version, direct script execution requirements, and first-party module names.
2. Confirm the active environment can run the expected tools: `ruff==0.15.20`, `mypy==2.1.0`, `pyright==1.1.411`, `pytest==9.1.1`, and `python -m compileall` when those pinned tools are available in `requirements-dev.txt`.
3. Set up or refresh the local venv when needed:
   - `python -m venv .venv`
   - `.\.venv\Scripts\python.exe -m pip install --upgrade pip`
   - `.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt`
   - Put `.\.venv\Scripts` first on `PATH` before running npm-backed Python scripts.
4. Configure or repair the project around one strict gate:
   - `ruff check` plus `ruff format --check`
   - `mypy` with `strict = true` and extra error codes
   - `pyright` in strict mode with explicit diagnostics
   - `pytest` strict config, strict markers, strict config, and warning errors
   - `python -m compileall` over source and tests
5. Add npm package scripts only when the repository already uses npm as the task runner or the user asks for cross-language scripts; prefer `check:python`, `format:python`, `lint:python`, `typecheck:python`, `test:python`, and `compile:python`.
6. Keep ignores local and documented. Prefer `per-file-ignores` for CLI entrypoints, direct-execution bootstrap code, dynamic API boundaries, and pytest asserts.
7. Do not mass-disable rules, add broad `ignore` lists, or downgrade warnings because a diagnostic batch fails. Fix the repeated pattern, add typed adapters, split helpers, or narrow the one intentional exception.
8. Keep editor settings in `.vscode/settings.json` aligned with repo config: Ruff uses filesystem config first, Pyright/Pylance runs workspace diagnostics, and tests use pytest.
9. Run `python <skill>/scripts/audit_python_strict.py <repo>` when auditing strict-tooling drift, then inspect every failure before editing.
10. Run the narrow failing command after each fix, then run the aggregate gate.

## Python Code Standards

- Use explicit types at public and internal boundaries; avoid `Any` unless the boundary is genuinely dynamic.
- Prefer typed adapters for untyped third-party responses instead of spreading casts through business logic.
- Use `typing.override` where supported and let Pyright catch missing override markers.
- Use `pathlib`, `subprocess.run(..., check=True)` with fixed argument arrays, and structured exceptions.
- Keep CLI output and API/client logic separated enough that tests can assert behavior without scraping terminal output.
- Treat `# type: ignore[...]`, `# noqa: ...`, and Ruff per-file ignores as review surfaces that require a reason.
- Treat generated coverage and checker output as validation artifacts. The default profile writes mypy reports under `coverage/mypy`, uses `.cache/.ruff_cache`, `.cache/.mypy_cache`, `.cache/.pytest_cache`, and lets pytest emit strict JUnit-compatible metadata when configured.

## Validation Commands

Prefer repo-local scripts when present. Otherwise, run the equivalent direct commands:

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
npm run compile:python
```

## Output

Finish with the strict configuration surfaces changed, the commands run, any remaining justified ignores, and any tool or interpreter prerequisite that blocked validation.
