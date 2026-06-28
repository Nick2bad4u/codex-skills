# Python Project Shapes

Use this reference when the target repository does not match the simple `scripts` + `tests` layout. Adapt paths before editing config.

## Contents

- [Shape Selection](#shape-selection)
- [Direct Script Repository](#direct-script-repository)
- [src Package Library](#src-package-library)
- [CLI Package](#cli-package)
- [Hybrid npm And Python Skill Package](#hybrid-npm-and-python-skill-package)
- [No npm Task Runner](#no-npm-task-runner)
- [Package Manager Notes](#package-manager-notes)

## Shape Selection

Inventory these before writing config:

- import roots and first-party package names
- whether source files are direct scripts, importable packages, or both
- test root and pytest import mode
- package manager: `pip`, `uv`, `hatch`, `pdm`, Poetry, npm task runner, or a mix
- minimum supported Python version and local interpreter path policy
- CI commands and publish/package surfaces

## Direct Script Repository

Use this for helper-script repositories where files under `scripts/` are executed directly.

- Ruff `src = ["scripts", "tests"]`
- mypy `files = ["scripts", "tests"]`
- mypy `mypy_path = "scripts"` only when tests import script modules directly
- Pyright `include = ["scripts", "tests"]`
- Pyright `extraPaths = ["scripts"]`
- pytest `pythonpath = ["scripts"]`
- Consider Ruff `INP001` for `scripts/**/*.py` only when `scripts/` is intentionally not a package.

## src Package Library

Use this for installable libraries under `src/<package>`.

- Ruff `src = ["src", "tests"]`
- mypy `files = ["src", "tests"]`
- Avoid `mypy_path` unless the package is not installed in the test environment.
- Pyright `include = ["src", "tests"]`
- Pyright `extraPaths = ["src"]`
- pytest usually does not need `pythonpath` when tests install the package.
- Add `py.typed` to the distributed package when public inline types are part of the package contract.
- Check `package_data`, `include-package-data`, build backend config, and `MANIFEST.in` if `py.typed` or fixture files must ship.

## CLI Package

Use this for packages exposing console scripts or module entrypoints.

- Keep CLI parsing thin and testable; put behavior in importable functions.
- Type `argparse.Namespace` boundaries with a small dataclass or adapter when strict typing becomes noisy.
- Add tests for parser defaults, invalid input, exit codes, user-facing output, and environment/credential failures.
- Keep Ruff `T201` ignores limited to the CLI output layer.
- Prefer package entry points over direct `python path/to/script.py` execution for installable CLIs.

## Hybrid npm And Python Skill Package

Use this when npm publishes the package but Python implements runtime helpers.

- Keep npm scripts as orchestration wrappers around Python tools.
- Keep `check:python`, `lint:python`, `typecheck:python`, `test:python`, and `compile:python` separate enough to debug failures quickly.
- Ensure `npm pack --dry-run` or the package manifest includes Python scripts, requirements files, skill resources, and generated metadata that consumers need.
- Do not let npm package validation replace Python typecheck/test gates.

## No npm Task Runner

Use direct Python commands instead of adding npm only for task orchestration.

```powershell
ruff check src tests
ruff format --check src tests
mypy src tests
pyright src tests
pytest
python -m compileall -q -x "[\\/]\\." src tests
```

If the repo uses `uv`, prefer checked-in commands such as:

```powershell
uv run ruff check src tests
uv run mypy src tests
uv run pyright src tests
uv run pytest
```

## Package Manager Notes

- For `uv`, check `pyproject.toml`, `uv.lock`, dependency groups, and `requires-python`.
- For Hatch, check build targets, environments, and scripts before adding direct commands.
- For PDM or Poetry, use their existing task/dependency groups instead of adding parallel dependency declarations.
- Keep editor interpreter paths local unless the repository intentionally commits a fixed interpreter path.
- Keep CI and local commands aligned; when they differ, document why.
