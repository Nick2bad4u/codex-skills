#!/usr/bin/env python
"""Audit a Python repository for the strict tooling profile."""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

Severity = Literal["fail", "pass", "warn"]


@dataclass(frozen=True)
class Diagnostic:
    """A single audit result."""

    check: str
    message: str
    severity: Severity


def add_check(
    diagnostics: list[Diagnostic],
    condition: bool,
    check: str,
    failure: str,
    success: str,
    severity: Severity = "fail",
) -> None:
    """Append a pass or failing diagnostic."""

    diagnostics.append(
        Diagnostic(
            check=check,
            message=success if condition else failure,
            severity="pass" if condition else severity,
        )
    )


def get_nested(data: dict[str, Any], *keys: str) -> Any:
    """Return a nested dictionary value."""

    value: Any = data
    for key in keys:
        if not isinstance(value, dict) or key not in value:
            return None
        value = value[key]
    return value


def has_all(values: object, expected: set[str]) -> bool:
    """Check whether a list-like value contains all expected strings."""

    return isinstance(values, list) and expected.issubset(
        {item for item in values if isinstance(item, str)}
    )


def load_json(path: Path) -> dict[str, Any] | None:
    """Load a JSON object if the file exists."""

    if not path.exists():
        return None

    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)

    if not isinstance(data, dict):
        raise TypeError(f"{path} must contain a JSON object")

    return data


def load_toml(path: Path) -> dict[str, Any]:
    """Load a TOML object."""

    with path.open("rb") as handle:
        data = tomllib.load(handle)

    if not isinstance(data, dict):
        raise TypeError(f"{path} must contain a TOML object")

    return data


def audit_pyproject(root: Path, diagnostics: list[Diagnostic]) -> None:
    """Audit pyproject.toml strict settings."""

    pyproject_path = root / "pyproject.toml"
    add_check(
        diagnostics,
        pyproject_path.exists(),
        "pyproject.exists",
        "pyproject.toml is missing.",
        "pyproject.toml exists.",
    )
    if not pyproject_path.exists():
        return

    pyproject = load_toml(pyproject_path)
    ruff = get_nested(pyproject, "tool", "ruff")
    ruff_lint = get_nested(pyproject, "tool", "ruff", "lint")
    ruff_format = get_nested(pyproject, "tool", "ruff", "format")
    ruff_analyze = get_nested(pyproject, "tool", "ruff", "analyze")
    mypy = get_nested(pyproject, "tool", "mypy")
    pyright = get_nested(pyproject, "tool", "pyright")
    pytest_options = get_nested(pyproject, "tool", "pytest", "ini_options")

    add_check(
        diagnostics,
        isinstance(ruff, dict) and ruff.get("force-exclude") is True,
        "ruff.force-exclude",
        "Ruff should set force-exclude = true.",
        "Ruff force-exclude is enabled.",
    )
    add_check(
        diagnostics,
        isinstance(ruff, dict) and ruff.get("line-length") == 120,
        "ruff.line-length",
        "Ruff should use line-length = 120.",
        "Ruff line length is 120.",
    )
    add_check(
        diagnostics,
        isinstance(ruff, dict) and isinstance(ruff.get("required-version"), str),
        "ruff.required-version",
        "Ruff should pin a minimum required-version.",
        "Ruff required-version is configured.",
    )
    add_check(
        diagnostics,
        isinstance(ruff_lint, dict) and has_all(ruff_lint.get("select"), {"ALL"}),
        "ruff.lint.select",
        'Ruff lint should select ["ALL"].',
        "Ruff lint selects ALL.",
    )
    add_check(
        diagnostics,
        isinstance(ruff_format, dict)
        and ruff_format.get("docstring-code-format") is True
        and ruff_format.get("line-ending") == "lf"
        and ruff_format.get("quote-style") == "double",
        "ruff.format",
        "Ruff format should enable docstring code formatting, LF endings, and double quotes.",
        "Ruff format settings match the strict profile.",
    )
    add_check(
        diagnostics,
        isinstance(ruff_analyze, dict)
        and ruff_analyze.get("detect-string-imports") is True
        and ruff_analyze.get("type-checking-imports") is True,
        "ruff.analyze",
        "Ruff analyze should detect string imports and type-checking imports.",
        "Ruff analyze settings match the strict profile.",
    )
    add_check(
        diagnostics,
        get_nested(pyproject, "tool", "ruff", "lint", "flake8-type-checking", "strict")
        is True,
        "ruff.flake8-type-checking.strict",
        "Ruff flake8-type-checking strict mode should be enabled.",
        "Ruff flake8-type-checking strict mode is enabled.",
    )

    add_check(
        diagnostics,
        isinstance(mypy, dict) and mypy.get("strict") is True,
        "mypy.strict",
        "mypy strict = true is missing.",
        "mypy strict mode is enabled.",
    )
    add_check(
        diagnostics,
        isinstance(mypy, dict)
        and has_all(
            mypy.get("enable_error_code"),
            {
                "deprecated",
                "explicit-override",
                "ignore-without-code",
                "mutable-override",
                "possibly-undefined",
                "redundant-expr",
                "truthy-bool",
                "truthy-iterable",
                "unused-awaitable",
            },
        ),
        "mypy.error-codes",
        "mypy should enable the strict profile's extra error codes.",
        "mypy extra error codes match the strict profile.",
    )
    add_check(
        diagnostics,
        isinstance(mypy, dict)
        and mypy.get("warn_unused_ignores") is True
        and mypy.get("warn_return_any") is True
        and mypy.get("warn_unreachable") is True,
        "mypy.warnings",
        "mypy should warn on unused ignores, return Any, and unreachable code.",
        "mypy warning settings match the strict profile.",
    )

    add_check(
        diagnostics,
        isinstance(pyright, dict) and pyright.get("typeCheckingMode") == "strict",
        "pyright.strict",
        'Pyright typeCheckingMode should be "strict".',
        "Pyright strict mode is enabled.",
    )
    add_check(
        diagnostics,
        isinstance(pyright, dict)
        and pyright.get("reportUnknownArgumentType") == "error"
        and pyright.get("reportUnknownMemberType") == "error"
        and pyright.get("reportUnknownVariableType") == "error",
        "pyright.unknown-types",
        "Pyright should report unknown argument, member, and variable types as errors.",
        "Pyright unknown-type diagnostics are errors.",
    )
    add_check(
        diagnostics,
        isinstance(pyright, dict)
        and pyright.get("enableReachabilityAnalysis") is True
        and pyright.get("strictDictionaryInference") is True
        and pyright.get("strictListInference") is True,
        "pyright.inference",
        "Pyright should enable reachability analysis and strict collection inference.",
        "Pyright inference settings match the strict profile.",
    )

    add_check(
        diagnostics,
        isinstance(pytest_options, dict)
        and has_all(
            pytest_options.get("addopts"),
            {"--strict-config", "--strict-markers", "--import-mode=importlib"},
        )
        and pytest_options.get("filterwarnings") == ["error"],
        "pytest.strict",
        "pytest should use strict config, strict markers, importlib import mode, and warning errors.",
        "pytest strict options match the strict profile.",
    )


def audit_package_json(root: Path, diagnostics: list[Diagnostic]) -> None:
    """Audit npm task-runner scripts when package.json exists."""

    package_json = load_json(root / "package.json")
    if package_json is None:
        diagnostics.append(
            Diagnostic(
                check="package-json.exists",
                message="package.json is absent; npm Python scripts are not required.",
                severity="warn",
            )
        )
        return

    scripts = package_json.get("scripts")
    add_check(
        diagnostics,
        isinstance(scripts, dict)
        and all(
            script in scripts
            for script in (
                "check:python",
                "compile:python",
                "format:python",
                "lint:python",
                "test:python",
                "typecheck:python",
            )
        ),
        "package-json.python-scripts",
        "package.json is missing one or more strict Python scripts.",
        "package.json includes the expected strict Python scripts.",
        severity="warn",
    )


def audit_vscode(root: Path, diagnostics: list[Diagnostic]) -> None:
    """Audit VS Code settings when present."""

    settings = load_json(root / ".vscode" / "settings.json")
    if settings is None:
        diagnostics.append(
            Diagnostic(
                check="vscode.exists",
                message=".vscode/settings.json is absent; editor integration was not audited.",
                severity="warn",
            )
        )
        return

    python_settings = settings.get("[python]")
    add_check(
        diagnostics,
        isinstance(python_settings, dict)
        and python_settings.get("editor.defaultFormatter") == "charliermarsh.ruff"
        and python_settings.get("editor.formatOnSave") is True,
        "vscode.python-format",
        "VS Code Python formatter should be Ruff with format-on-save enabled.",
        "VS Code Python formatter uses Ruff.",
        severity="warn",
    )
    add_check(
        diagnostics,
        settings.get("ruff.configurationPreference") == "filesystemFirst"
        and settings.get("ruff.lint.enable") is True,
        "vscode.ruff",
        "VS Code Ruff should prefer filesystem config and enable linting.",
        "VS Code Ruff settings match the strict profile.",
        severity="warn",
    )
    add_check(
        diagnostics,
        settings.get("python.analysis.typeCheckingMode") == "strict"
        and settings.get("python.analysis.diagnosticMode") == "workspace",
        "vscode.pyright",
        "VS Code Python analysis should use strict workspace diagnostics.",
        "VS Code Python analysis uses strict workspace diagnostics.",
        severity="warn",
    )


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(
        description="Audit a Python repository for strict Ruff, mypy, Pyright, pytest, npm, and VS Code settings."
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Repository root to audit. Defaults to the current directory.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print diagnostics as JSON.",
    )
    return parser.parse_args()


def print_text(diagnostics: list[Diagnostic]) -> None:
    """Print human-readable diagnostics."""

    for diagnostic in diagnostics:
        prefix = {
            "fail": "FAIL",
            "pass": "PASS",
            "warn": "WARN",
        }[diagnostic.severity]
        print(f"{prefix} {diagnostic.check}: {diagnostic.message}")


def main() -> int:
    """Run the audit."""

    args = parse_args()
    root = Path(args.path).resolve()
    diagnostics: list[Diagnostic] = []

    audit_pyproject(root, diagnostics)
    audit_package_json(root, diagnostics)
    audit_vscode(root, diagnostics)

    if args.json:
        print(json.dumps([asdict(diagnostic) for diagnostic in diagnostics], indent=2))
    else:
        print_text(diagnostics)

    return 1 if any(diagnostic.severity == "fail" for diagnostic in diagnostics) else 0


if __name__ == "__main__":
    sys.exit(main())
