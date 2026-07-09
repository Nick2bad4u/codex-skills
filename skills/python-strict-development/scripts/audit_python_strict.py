#!/usr/bin/env python
"""Audit a Python repository for the strict tooling profile."""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal, cast

Severity = Literal["fail", "pass", "warn"]
STRICT_LINE_LENGTH = 120


@dataclass(frozen=True)
class Diagnostic:
    """A single audit result."""

    check: str
    message: str
    severity: Severity


@dataclass(frozen=True)
class CheckMessages:
    """Pass and fail messages for one audit check."""

    failure: str
    success: str


def add_check(
    diagnostics: list[Diagnostic],
    check: str,
    messages: CheckMessages,
    *,
    passed: bool,
    severity: Severity = "fail",
) -> None:
    """Append a pass or failing diagnostic."""
    diagnostics.append(
        Diagnostic(
            check=check,
            message=messages.success if passed else messages.failure,
            severity="pass" if passed else severity,
        )
    )


def as_str_mapping(value: object) -> dict[str, object] | None:
    """Return a string-keyed mapping when a dynamic value has that shape."""
    if not isinstance(value, dict):
        return None

    mapping: dict[str, object] = {}
    for key, item in cast("dict[object, object]", value).items():
        if not isinstance(key, str):
            return None
        mapping[key] = item

    return mapping


def get_nested(data: object, *keys: str) -> object | None:
    """Return a nested dictionary value."""
    value: object = data
    for key in keys:
        mapping = as_str_mapping(value)
        if mapping is None or key not in mapping:
            return None
        value = mapping[key]
    return value


def has_all(values: object, expected: set[str]) -> bool:
    """Check whether a list-like value contains all expected strings."""
    if not isinstance(values, list):
        return False

    return expected.issubset({item for item in cast("list[object]", values) if isinstance(item, str)})


def has_keys(value: object, expected: tuple[str, ...]) -> bool:
    """Check whether a dynamic mapping contains all expected keys."""
    mapping = as_str_mapping(value)
    return mapping is not None and all(key in mapping for key in expected)


def raw_value(value: object, key: str) -> object | None:
    """Return a key from a dynamic mapping."""
    mapping = as_str_mapping(value)
    if mapping is None:
        return None

    return mapping.get(key)


def load_json(path: Path) -> dict[str, object] | None:
    """Load a JSON object if the file exists."""
    if not path.exists():
        return None

    with path.open(encoding="utf-8") as handle:
        data: object = json.load(handle)

    mapping = as_str_mapping(data)
    if mapping is None:
        raise TypeError(f"{path} must contain a JSON object")

    return mapping


def load_toml(path: Path) -> dict[str, object]:
    """Load a TOML object."""
    with path.open("rb") as handle:
        data: object = tomllib.load(handle)

    mapping = as_str_mapping(data)
    if mapping is None:
        raise TypeError(f"{path} must contain a TOML object")

    return mapping


def write_line(text: str) -> None:
    """Write one line to stdout."""
    _ = sys.stdout.write(f"{text}\n")


def audit_pyproject(root: Path, diagnostics: list[Diagnostic]) -> None:
    """Audit pyproject.toml strict settings."""
    pyproject_path = root / "pyproject.toml"
    add_check(
        diagnostics,
        "pyproject.exists",
        CheckMessages(
            failure="pyproject.toml is missing.",
            success="pyproject.toml exists.",
        ),
        passed=pyproject_path.exists(),
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
        "ruff.force-exclude",
        CheckMessages(
            failure="Ruff should set force-exclude = true.",
            success="Ruff force-exclude is enabled.",
        ),
        passed=raw_value(ruff, "force-exclude") is True,
    )
    add_check(
        diagnostics,
        "ruff.line-length",
        CheckMessages(
            failure=f"Ruff should use line-length = {STRICT_LINE_LENGTH}.",
            success=f"Ruff line length is {STRICT_LINE_LENGTH}.",
        ),
        passed=raw_value(ruff, "line-length") == STRICT_LINE_LENGTH,
    )
    add_check(
        diagnostics,
        "ruff.required-version",
        CheckMessages(
            failure="Ruff should pin a minimum required-version.",
            success="Ruff required-version is configured.",
        ),
        passed=isinstance(raw_value(ruff, "required-version"), str),
    )
    add_check(
        diagnostics,
        "ruff.lint.select",
        CheckMessages(
            failure='Ruff lint should select ["ALL"].',
            success="Ruff lint selects ALL.",
        ),
        passed=has_all(raw_value(ruff_lint, "select"), {"ALL"}),
    )
    add_check(
        diagnostics,
        "ruff.format",
        CheckMessages(
            failure="Ruff format should enable docstring code formatting, LF endings, and double quotes.",
            success="Ruff format settings match the strict profile.",
        ),
        passed=raw_value(ruff_format, "docstring-code-format") is True
        and raw_value(ruff_format, "line-ending") == "lf"
        and raw_value(ruff_format, "quote-style") == "double",
    )
    add_check(
        diagnostics,
        "ruff.analyze",
        CheckMessages(
            failure="Ruff analyze should detect string imports and type-checking imports.",
            success="Ruff analyze settings match the strict profile.",
        ),
        passed=raw_value(ruff_analyze, "detect-string-imports") is True
        and raw_value(ruff_analyze, "type-checking-imports") is True,
    )
    add_check(
        diagnostics,
        "ruff.flake8-type-checking.strict",
        CheckMessages(
            failure="Ruff flake8-type-checking strict mode should be enabled.",
            success="Ruff flake8-type-checking strict mode is enabled.",
        ),
        passed=get_nested(pyproject, "tool", "ruff", "lint", "flake8-type-checking", "strict") is True,
    )

    add_check(
        diagnostics,
        "mypy.strict",
        CheckMessages(
            failure="mypy strict = true is missing.",
            success="mypy strict mode is enabled.",
        ),
        passed=raw_value(mypy, "strict") is True,
    )
    add_check(
        diagnostics,
        "mypy.error-codes",
        CheckMessages(
            failure="mypy should enable the strict profile's extra error codes.",
            success="mypy extra error codes match the strict profile.",
        ),
        passed=has_all(
            raw_value(mypy, "enable_error_code"),
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
    )
    add_check(
        diagnostics,
        "mypy.warnings",
        CheckMessages(
            failure="mypy should warn on unused ignores, return Any, and unreachable code.",
            success="mypy warning settings match the strict profile.",
        ),
        passed=raw_value(mypy, "warn_unused_ignores") is True
        and raw_value(mypy, "warn_return_any") is True
        and raw_value(mypy, "warn_unreachable") is True,
    )

    add_check(
        diagnostics,
        "pyright.strict",
        CheckMessages(
            failure='Pyright typeCheckingMode should be "strict".',
            success="Pyright strict mode is enabled.",
        ),
        passed=raw_value(pyright, "typeCheckingMode") == "strict",
    )
    add_check(
        diagnostics,
        "pyright.unknown-types",
        CheckMessages(
            failure="Pyright should report unknown argument, member, and variable types as errors.",
            success="Pyright unknown-type diagnostics are errors.",
        ),
        passed=raw_value(pyright, "reportUnknownArgumentType") == "error"
        and raw_value(pyright, "reportUnknownMemberType") == "error"
        and raw_value(pyright, "reportUnknownVariableType") == "error",
    )
    add_check(
        diagnostics,
        "pyright.inference",
        CheckMessages(
            failure="Pyright should enable reachability analysis and strict collection inference.",
            success="Pyright inference settings match the strict profile.",
        ),
        passed=raw_value(pyright, "enableReachabilityAnalysis") is True
        and raw_value(pyright, "strictDictionaryInference") is True
        and raw_value(pyright, "strictListInference") is True,
    )

    add_check(
        diagnostics,
        "pytest.strict",
        CheckMessages(
            failure="pytest should use strict config, strict markers, importlib import mode, and warning errors.",
            success="pytest strict options match the strict profile.",
        ),
        passed=has_all(
            raw_value(pytest_options, "addopts"),
            {"--strict-config", "--strict-markers", "--import-mode=importlib"},
        )
        and raw_value(pytest_options, "filterwarnings") == ["error"],
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

    scripts = raw_value(package_json, "scripts")
    add_check(
        diagnostics,
        "package-json.python-scripts",
        CheckMessages(
            failure="package.json is missing one or more strict Python scripts.",
            success="package.json includes the expected strict Python scripts.",
        ),
        passed=has_keys(
            scripts,
            (
                "check:python",
                "compile:python",
                "format:python",
                "lint:python",
                "python:bootstrap",
                "python:venv",
                "test:python",
                "typecheck:python",
            ),
        ),
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

    python_settings = raw_value(settings, "[python]")
    add_check(
        diagnostics,
        "vscode.python-format",
        CheckMessages(
            failure="VS Code Python formatter should be Ruff with format-on-save enabled.",
            success="VS Code Python formatter uses Ruff.",
        ),
        passed=raw_value(python_settings, "editor.defaultFormatter") == "charliermarsh.ruff"
        and raw_value(python_settings, "editor.formatOnSave") is True,
        severity="warn",
    )
    add_check(
        diagnostics,
        "vscode.ruff",
        CheckMessages(
            failure="VS Code Ruff should prefer filesystem config and enable linting.",
            success="VS Code Ruff settings match the strict profile.",
        ),
        passed=raw_value(settings, "ruff.configurationPreference") == "filesystemFirst"
        and raw_value(settings, "ruff.lint.enable") is True,
        severity="warn",
    )
    add_check(
        diagnostics,
        "vscode.pyright",
        CheckMessages(
            failure="VS Code Python analysis should use strict workspace diagnostics.",
            success="VS Code Python analysis uses strict workspace diagnostics.",
        ),
        passed=raw_value(settings, "python.analysis.typeCheckingMode") == "strict"
        and raw_value(settings, "python.analysis.diagnosticMode") == "workspace",
        severity="warn",
    )


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Audit a Python repository for strict Ruff, mypy, Pyright, pytest, npm, and VS Code settings."
    )
    _ = parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Repository root to audit. Defaults to the current directory.",
    )
    _ = parser.add_argument(
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
        write_line(f"{prefix} {diagnostic.check}: {diagnostic.message}")


def main() -> int:
    """Run the audit."""
    args = parse_args()
    root = Path(args.path).resolve()
    diagnostics: list[Diagnostic] = []

    audit_pyproject(root, diagnostics)
    audit_package_json(root, diagnostics)
    audit_vscode(root, diagnostics)

    if args.json:
        write_line(json.dumps([asdict(diagnostic) for diagnostic in diagnostics], indent=2))
    else:
        print_text(diagnostics)

    return 1 if any(diagnostic.severity == "fail" for diagnostic in diagnostics) else 0


if __name__ == "__main__":
    sys.exit(main())
