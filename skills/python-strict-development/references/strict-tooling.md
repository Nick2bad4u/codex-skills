# Strict Python Tooling

Use this reference when a Python repository needs the user's strict local quality setup. Adapt names and paths before writing files.

## Contents

- [Baseline Files](#baseline-files)
- [Ruff](#ruff)
- [mypy](#mypy)
- [Pyright](#pyright)
- [pytest](#pytest)
- [VS Code Settings](#vs-code-settings)
- [npm Scripts For Python Repos](#npm-scripts-for-python-repos)
- [Fix Strategy](#fix-strategy)

## Baseline Files

- `pyproject.toml`: Ruff, mypy, Pyright, and pytest configuration.
- `.vscode/settings.json`: editor integration for Ruff, Pylance/Pyright, pytest, and the preferred interpreter.
- `package.json`: npm scripts only when the repo already uses npm as a command runner or publishes a skill/package through npm.
- `requirements-dev.txt` or equivalent: include `ruff`, `mypy`, `pyright`, `pytest`, and any stubs required by strict type checking.

## Ruff

Start strict and relax only with narrow reasons.

```toml
[tool.ruff]
force-exclude = true
line-length = 120
required-version = ">=0.15.20"
show-fixes = true
target-version = "py314"
src = ["scripts", "tests"]

[tool.ruff.format]
docstring-code-format = true
line-ending = "lf"
quote-style = "double"

[tool.ruff.analyze]
detect-string-imports = true
direction = "dependencies"
type-checking-imports = true

[tool.ruff.lint]
select = ["ALL"]
ignore = [
    "ANN401", # Dynamic JSON or API payloads at a typed boundary.
    "COM812", # Conflicts with the formatter.
    "D203",   # Incompatible with D211.
    "D213",   # Incompatible with D212.
    "EM101",  # CLI errors are clearer inline at the call site.
    "EM102",  # CLI errors are clearer inline at the call site.
    "ISC001", # Conflicts with the formatter.
    "TRY003", # CLI errors are clearer inline at the call site.
]
fixable = ["ALL"]
unfixable = [
    "ERA", # Do not delete commented context automatically.
    "F401", # Keep import removal explicit in review.
]

[tool.ruff.lint.isort]
known-first-party = ["your_package"]

[tool.ruff.lint.pydocstyle]
convention = "google"

[tool.ruff.lint.flake8-type-checking]
strict = true

[tool.ruff.lint.per-file-ignores]
"tests/**/*.py" = [
    "S101", # pytest uses assert rewriting.
]
```

Use `INP001` only for direct-execution helper directories such as `scripts/` that are intentionally not packages. Use `T201` only in CLI or rendering files that own user-facing output. Use `PLR091*` and `C901` only where command handlers or API wrappers are intentionally direct dispatchers.

## mypy

Keep mypy strict and enable high-signal extra error codes.

```toml
[tool.mypy]
python_version = "3.14"
files = ["scripts", "tests"]
mypy_path = "scripts"
strict = true
disallow_any_decorated = true
disallow_any_unimported = true
color_output = true
incremental = true
allow_redefinition = false
local_partial_types = true
no_implicit_optional = true
no_implicit_reexport = true
strict_optional = true
strict_bytes = true
strict_equality = true
strict_equality_for_none = true
warn_incomplete_stub = true
warn_no_return = true
warn_redundant_casts = true
warn_return_any = true
warn_unused_configs = true
warn_unused_ignores = true
warn_unreachable = true
show_error_context = true
pretty = true
show_column_numbers = true
enable_error_code = [
    "deprecated",
    "explicit-override",
    "ignore-without-code",
    "mutable-override",
    "possibly-undefined",
    "redundant-expr",
    "truthy-bool",
    "truthy-iterable",
    "unused-awaitable",
]
```

## Pyright

Use Pyright as a second strict checker. It catches inference, override, reachability, missing stub, and unknown-type problems that mypy may not report.

```toml
[tool.pyright]
include = ["scripts", "tests"]
extraPaths = ["scripts"]
exclude = ["**/.*", "**/__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache", "node_modules"]
pythonVersion = "3.14"
pythonPlatform = "All"
typeCheckingMode = "strict"
analyzeUnannotatedFunctions = true
strictDictionaryInference = true
strictListInference = true
strictSetInference = true
strictParameterNoneValue = true
enableTypeIgnoreComments = true
enableReachabilityAnalysis = true
deprecateTypingAliases = true
disableBytesTypePromotions = true
useLibraryCodeForTypes = true
reportMissingTypeStubs = "error"
reportUnknownArgumentType = "error"
reportUnknownLambdaType = "error"
reportUnknownMemberType = "error"
reportUnknownParameterType = "error"
reportUnknownVariableType = "error"
```

Add explicit `report... = true` diagnostics when a repo wants a fully pinned editor/CLI policy instead of relying on Pyright defaults. Keep `.vscode/settings.json` aligned with `python.analysis.typeCheckingMode = "strict"`.

## pytest

```toml
[tool.pytest.ini_options]
addopts = ["--strict-config", "--strict-markers", "--import-mode=importlib"]
filterwarnings = ["error"]
pythonpath = ["scripts"]
testpaths = ["tests"]
strict = true
strict_config = true
strict_markers = true
strict_parametrization_ids = true
strict_xfail = true
```

## VS Code Settings

```json
{
 "[python]": {
  "editor.codeActionsOnSave": {
   "source.fixAll.ruff": "explicit",
   "source.organizeImports.ruff": "explicit"
  },
  "editor.defaultFormatter": "charliermarsh.ruff",
  "editor.formatOnSave": true
 },
 "mypy-type-checker.reportingScope": "workspace",
 "python.analysis.diagnosticMode": "workspace",
 "python.analysis.extraPaths": ["${workspaceFolder}/scripts"],
 "python.analysis.typeCheckingMode": "strict",
 "python.analysis.typeEvaluation.analyzeUnannotatedFunctions": true,
 "python.analysis.typeEvaluation.deprecateTypingAliases": true,
 "python.analysis.typeEvaluation.disableBytesTypePromotions": true,
 "python.analysis.typeEvaluation.enableReachabilityAnalysis": true,
 "python.analysis.typeEvaluation.enableTypeIgnoreComments": true,
 "python.analysis.typeEvaluation.strictDictionaryInference": true,
 "python.analysis.typeEvaluation.strictListInference": true,
 "python.analysis.typeEvaluation.strictParameterNoneValue": true,
 "python.analysis.typeEvaluation.strictSetInference": true,
 "python.analysis.useLibraryCodeForTypes": true,
 "python.defaultInterpreterPath": "C:\\Python314\\python.exe",
 "python.testing.pytestEnabled": true,
 "python.testing.unittestEnabled": false,
 "ruff.configurationPreference": "filesystemFirst",
 "ruff.fixAll": true,
 "ruff.format.backend": "internal",
 "ruff.importStrategy": "fromEnvironment",
 "ruff.lint.enable": true,
 "ruff.nativeServer": "auto",
 "ruff.organizeImports": true
}
```

Do not hard-code `C:\\Python314\\python.exe` unless the workspace is intentionally tied to that local interpreter. For shared repositories, prefer documentation or environment setup over committing machine-specific paths.

## npm Scripts For Python Repos

Use these only when npm is already the project task runner.

```json
{
 "scripts": {
  "check:python": "npm run lint:python && npm run typecheck:python && npm run test:python && python -m compileall -q -x \"[\\\\/]\\.\" scripts tests",
  "compile:python": "python -m compileall -q -x \"[\\\\/]\\.\" scripts tests",
  "format:python": "ruff format scripts tests && ruff check --fix scripts tests",
  "lint:python": "ruff check scripts tests && ruff format --check scripts tests",
  "mypy": "mypy scripts tests",
  "pyright": "pyright scripts tests",
  "ruff:check": "ruff check scripts tests",
  "ruff:fix": "ruff check --fix scripts tests",
  "ruff:format": "ruff format scripts tests",
  "ruff:format:check": "ruff format --check scripts tests",
  "test:python": "pytest",
  "typecheck:python": "mypy scripts tests && pyright scripts tests"
 }
}
```

## Fix Strategy

- Run format before lint only when formatting drift is expected; otherwise inspect Ruff diagnostics first.
- Fix type errors at the boundary by adding typed models, `TypedDict`, protocols, dataclasses, or small adapters.
- Add stubs or dependency extras when strict type checkers report missing stubs for a real dependency.
- Use `cast` only at narrow trust boundaries and remove it when the surrounding type can be expressed.
- Keep `# noqa`, `# type: ignore[...]`, and per-file ignores specific, justified, and close to the rule they suppress.
