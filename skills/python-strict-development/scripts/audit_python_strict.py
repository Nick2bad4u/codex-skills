#!/usr/bin/env python
# Copyright (c) 2026 Nick2bad4u
"""Audit a Python repository for the strict tooling profile."""

from __future__ import annotations

import argparse
import json
import math
import re
import shlex
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

Severity = Literal["fail", "pass", "warn"]
MatchMode = Literal["equals", "contains", "text-contains"]
SemanticVersion = tuple[int, int, int]
type JsonScalar = bool | float | int | str | None
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]
STRICT_LINE_LENGTH = 120
MINIMUM_RUFF_VERSION: SemanticVersion = (0, 15, 20)
SEMANTIC_VERSION_COMPONENTS = 3
MINIMUM_TOOL_COMMAND_LENGTH = 3
MINIMUM_QUOTED_TOKEN_LENGTH = 2
MISSING_VALUE = "<missing>"
REDACTED_VALUE = "<redacted>"
MAXIMUM_REPORTED_STRING_LENGTH = 240
SENSITIVE_KEY_PARTS = ("auth", "credential", "key", "password", "secret", "token")
MAXIMUM_CONFIG_DEPTH = 64
MAXIMUM_CONFIG_NODES = 20_000
MAXIMUM_CONFIG_COLLECTION_ITEMS = 4_096
MAXIMUM_CONFIG_STRING_LENGTH = 1_000_000
MAXIMUM_CONFIG_FILE_BYTES = 5_000_000
MAXIMUM_DIAGNOSTIC_DEPTH = 32
MAXIMUM_DIAGNOSTIC_NODES = 4_096
MAXIMUM_DIAGNOSTIC_COLLECTION_ITEMS = 256
MAXIMUM_PACKAGE_SCRIPTS = 2_048
MAXIMUM_SCRIPT_LENGTH = 8_192
MAXIMUM_SCRIPT_TOKENS = 256
MAXIMUM_SCRIPT_COMMANDS = 32
MAXIMUM_TOKEN_LENGTH = 1_024
MAXIMUM_GRAPH_NODES = 128
MAXIMUM_GRAPH_EDGES = 512
MAXIMUM_DEPENDENCY_FILE_BYTES = 5_000_000
MAXIMUM_REQUIREMENT_ENTRIES = 5_000
MAXIMUM_REQUIREMENT_LINE_LENGTH = 8_192
SHA256_HEX_LENGTH = 64
SAFE_CHAIN_OPERATOR = "&&"
UNSAFE_CHAIN_OPERATORS = frozenset({"&", ";", "|", "||"})
NO_OP_FLAGS = frozenset({"--help", "--version", "-h", "-V"})
PYTEST_NO_OP_FLAGS = frozenset(
    {
        "--cache-show",
        "--co",
        "--collect-only",
        "--fixtures",
        "--fixtures-per-test",
        "--markers",
        "--setup-only",
        "--setup-plan",
        "--version",
    }
)
PYTEST_CONFIG_OVERRIDE_FLAGS = frozenset(
    {
        "--confcutdir",
        "--disable-warnings",
        "--override-ini",
        "--rootdir",
        "-c",
        "-o",
        "-p",
    }
)
PYTEST_DISCOVERY_BYPASS_FLAGS = frozenset({"--deselect", "--ignore", "--ignore-glob"})
REQUIRED_TOOL_NAMES = frozenset({"mypy", "pyright", "pytest", "ruff"})
SAFE_NODE_HELPERS = frozenset({"tools/run-pytest.mjs", "tools/validate-codecov-report.mjs"})
SAFE_NAMED_LOCK_PATTERN = re.compile(r"pylock(?:\.[a-z0-9][a-z0-9-]{0,31})?\.toml", re.ASCII)
REQUIREMENT_NAME_PATTERN = r"(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)"
REQUIREMENT_EXTRAS_PATTERN = r"(?:\[[A-Za-z0-9._-]+(?:\s*,\s*[A-Za-z0-9._-]+)*\])?"
REQUIREMENT_VERSION_PATTERN = r"\s*==\s*(?P<version>[A-Za-z0-9][A-Za-z0-9._+!-]*)"
REQUIREMENT_MARKER_PATTERN = r"(?:\s*;\s*[A-Za-z0-9_ .'\"<>=!(),-]+)?"
REQUIREMENT_PATTERN_TEXT = (
    f"{REQUIREMENT_NAME_PATTERN}{REQUIREMENT_EXTRAS_PATTERN}{REQUIREMENT_VERSION_PATTERN}{REQUIREMENT_MARKER_PATTERN}"
)
REQUIREMENT_PATTERN = re.compile(REQUIREMENT_PATTERN_TEXT, re.ASCII)
PINNED_RELEASE_PATTERN = r"(?:[0-9]+!)?[0-9]+(?:\.[0-9]+)*"
PINNED_SUFFIX_PATTERN = r"(?:(?:a|b|rc)[0-9]+)?(?:\.post[0-9]+)?(?:\.dev[0-9]+)?"
PINNED_LOCAL_PATTERN = r"(?:\+[a-z0-9]+(?:[._-][a-z0-9]+)*)?"
PINNED_VERSION_PATTERN = re.compile(
    f"{PINNED_RELEASE_PATTERN}{PINNED_SUFFIX_PATTERN}{PINNED_LOCAL_PATTERN}",
    re.ASCII | re.IGNORECASE,
)
VALID_SHA256_PATTERN = re.compile(r"sha256:(?P<digest>[0-9a-fA-F]{64})", re.ASCII)
MYPY_EXCLUSION_PREFIX = "(^|/)"
EMPTY_STRING_SET: frozenset[str] = frozenset()


@dataclass(frozen=True)
class Diagnostic:
    """A single audit result."""

    check: str
    message: str
    severity: Severity
    expected: JsonValue = None
    actual: JsonValue = None


@dataclass(frozen=True)
class CheckMessages:
    """Pass and fail messages for one audit check."""

    failure: str
    success: str


@dataclass(frozen=True)
class DiagnosticContext:
    """Structured expected and actual context for an audit result."""

    expected: JsonValue = None
    actual: JsonValue = None


EMPTY_DIAGNOSTIC_CONTEXT = DiagnosticContext()


@dataclass(frozen=True)
class ExpectedSetting:
    """One expected value within a dynamically loaded configuration object."""

    path: tuple[str, ...]
    value: object
    mode: MatchMode = "equals"


@dataclass(frozen=True)
class SettingsCheck:
    """A named audit check backed by an expected-value table."""

    check: str
    messages: CheckMessages
    expected: tuple[ExpectedSetting, ...]


def expected_true(*path: str) -> ExpectedSetting:
    """Create a true-valued expected setting."""
    return ExpectedSetting(path, value=True)


def expected_false(*path: str) -> ExpectedSetting:
    """Create a false-valued expected setting."""
    return ExpectedSetting(path, value=False)


RUFF_CORE_SETTINGS = (
    expected_true("show-fixes"),
    ExpectedSetting(("target-version",), "py314"),
    expected_true("respect-gitignore"),
)
RUFF_REQUIRED_EXCLUSIONS = frozenset(
    {
        ".cache",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
        "build",
        "coverage",
        "dist",
        "node_modules",
        "site-packages",
        "vendor",
        "venv",
    }
)
RUFF_ALLOWED_EXCLUSIONS = frozenset(
    {
        ".bzr",
        ".cache",
        ".git",
        ".hg",
        ".mypy_cache",
        ".nox",
        ".pytest_cache",
        ".ruff_cache",
        ".svn",
        ".tox",
        ".venv",
        "__pycache__",
        "__pypackages__",
        "build",
        "coverage",
        "dist",
        "env",
        "htmlcov",
        "node_modules",
        "site-packages",
        "third_party",
        "tmp",
        "vendor",
        "venv",
    }
)
RUFF_ALLOWED_IGNORES = frozenset({"ANN401", "COM812", "D203", "D213", "EM101", "EM102", "INP001", "ISC001", "TRY003"})
RUFF_ALLOWED_UNFIXABLE = frozenset({"ERA", "F401"})
RUFF_ALLOWED_PER_FILE_IGNORES = {"tests/**/*.py": frozenset({"S101"})}
RUFF_PATH_SETTINGS = (
    ExpectedSetting(("src",), frozenset({"."}), "contains"),
    ExpectedSetting(("cache-dir",), ".cache/.ruff_cache"),
    ExpectedSetting(("extend-exclude",), RUFF_REQUIRED_EXCLUSIONS, "contains"),
)
RUFF_LINT_SETTINGS = (ExpectedSetting(("fixable",), frozenset({"ALL"}), "contains"),)
RUFF_FORMAT_SETTINGS = (
    expected_true("docstring-code-format"),
    ExpectedSetting(("line-ending",), "lf"),
    ExpectedSetting(("quote-style",), "double"),
)
RUFF_ANALYZE_SETTINGS = (
    expected_true("detect-string-imports"),
    ExpectedSetting(("direction",), "dependencies"),
    expected_true("type-checking-imports"),
)
RUFF_PYDOCSTYLE_SETTINGS = (ExpectedSetting(("convention",), "google"),)
RUFF_TYPE_CHECKING_SETTINGS = (expected_true("strict"),)

MYPY_ESSENTIAL_SETTINGS = (
    expected_true("disallow_any_decorated"),
    expected_true("disallow_any_unimported"),
    expected_true("strict_bytes"),
    expected_true("strict_equality"),
    expected_true("strict_equality_for_none"),
    expected_true("warn_incomplete_stub"),
    expected_true("warn_redundant_casts"),
    expected_true("warn_return_any"),
    expected_true("warn_unused_configs"),
    expected_true("warn_unused_ignores"),
    expected_true("warn_unreachable"),
)
MYPY_REQUIRED_EXCLUSIONS = frozenset(
    {
        ".cache",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
        "build",
        "coverage",
        "dist",
        "node_modules",
        "site-packages",
        "vendor",
        "venv",
    }
)
MYPY_ALLOWED_EXCLUSIONS = frozenset(
    {
        ".bzr",
        ".cache",
        ".git",
        ".hg",
        ".mypy_cache",
        ".nox",
        ".pytest_cache",
        ".ruff_cache",
        ".svn",
        ".tox",
        ".venv",
        "__pycache__",
        "__pypackages__",
        "build",
        "coverage",
        "dist",
        "env",
        "htmlcov",
        "node_modules",
        "site-packages",
        "third_party",
        "tmp",
        "vendor",
        "venv",
    }
)
MYPY_PATH_SETTINGS = (
    ExpectedSetting(("python_version",), "3.14"),
    ExpectedSetting(("files",), frozenset({"."}), "contains"),
    ExpectedSetting(("mypy_path",), "."),
    ExpectedSetting(("cache_dir",), ".cache/.mypy_cache"),
    ExpectedSetting(("exclude",), MYPY_REQUIRED_EXCLUSIONS, "text-contains"),
)
MYPY_REPORT_SETTINGS = (
    ExpectedSetting(("junit_xml",), "coverage/mypy/junit.xml"),
    ExpectedSetting(("cobertura_xml_report",), "coverage/mypy/cobertura.xml"),
    ExpectedSetting(("xml_report",), "coverage/mypy/mypy.xml"),
    ExpectedSetting(("linecoverage_report",), "coverage/mypy/linecoverage.xml"),
    ExpectedSetting(("any_exprs_report",), "coverage/mypy/any_exprs.txt"),
    ExpectedSetting(("linecount_report",), "coverage/mypy/linecount.txt"),
    ExpectedSetting(("lineprecision_report",), "coverage/mypy/lineprecision.txt"),
)
MYPY_EXTRA_ERROR_CODES = frozenset(
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
    }
)
MYPY_STRICT_NEGATING_SETTINGS = frozenset(
    {
        "check_untyped_defs",
        "disallow_any_generics",
        "disallow_incomplete_defs",
        "disallow_subclassing_any",
        "disallow_untyped_calls",
        "disallow_untyped_decorators",
        "disallow_untyped_defs",
        "no_implicit_reexport",
    }
)

PYRIGHT_ESSENTIAL_SETTINGS = (
    ExpectedSetting(("pythonPlatform",), "All"),
    ExpectedSetting(("typeCheckingMode",), "strict"),
    expected_true("analyzeUnannotatedFunctions"),
    expected_true("strictDictionaryInference"),
    expected_true("strictListInference"),
    expected_true("strictSetInference"),
    expected_true("enableReachabilityAnalysis"),
    expected_true("deprecateTypingAliases"),
    expected_true("disableBytesTypePromotions"),
    expected_true("useLibraryCodeForTypes"),
    ExpectedSetting(("reportMissingTypeStubs",), "error"),
    ExpectedSetting(("reportUnknownArgumentType",), "error"),
    ExpectedSetting(("reportUnknownLambdaType",), "error"),
    ExpectedSetting(("reportUnknownMemberType",), "error"),
    ExpectedSetting(("reportUnknownParameterType",), "error"),
    ExpectedSetting(("reportUnknownVariableType",), "error"),
    expected_true("reportUnusedCallResult"),
    expected_true("reportImplicitOverride"),
    expected_true("reportUnnecessaryTypeIgnoreComment"),
)
PYRIGHT_REQUIRED_EXCLUSIONS = frozenset(
    {
        "**/.*",
        "**/.cache",
        "**/.mypy_cache",
        "**/.pytest_cache",
        "**/.ruff_cache",
        "**/.venv",
        "**/__pycache__",
        "**/build",
        "**/coverage",
        "**/dist",
        "**/node_modules",
        "**/site-packages",
        "**/vendor",
        "**/venv",
    }
)
PYRIGHT_ALLOWED_EXCLUSIONS = frozenset(f"**/{name}" for name in RUFF_ALLOWED_EXCLUSIONS) | frozenset({"**/.*"})
PYRIGHT_PATH_SETTINGS = (
    ExpectedSetting(("include",), frozenset({"."}), "contains"),
    ExpectedSetting(("extraPaths",), frozenset({"."}), "contains"),
    ExpectedSetting(("exclude",), PYRIGHT_REQUIRED_EXCLUSIONS, "contains"),
    ExpectedSetting(("pythonVersion",), "3.14"),
)

PYTEST_STRICT_SETTINGS = (
    ExpectedSetting(
        ("addopts",),
        frozenset({"--strict-config", "--strict-markers", "--import-mode=importlib"}),
        "contains",
    ),
    ExpectedSetting(("filterwarnings",), ["error"]),
    expected_true("strict"),
    expected_true("strict_config"),
    expected_true("strict_markers"),
    expected_true("strict_parametrization_ids"),
    expected_true("strict_xfail"),
)
PYTEST_ALLOWED_NORECURSEDIRS = frozenset(
    {
        ".*",
        "__pycache__",
        "__pypackages__",
        "build",
        "coverage",
        "dist",
        "env",
        "htmlcov",
        "node_modules",
        "site-packages",
        "third_party",
        "tmp",
        "vendor",
        "venv",
    }
)
PYTEST_PROFILE_SETTINGS = (
    ExpectedSetting(("pythonpath",), frozenset({"."}), "contains"),
    ExpectedSetting(("testpaths",), frozenset({"."}), "contains"),
    ExpectedSetting(("norecursedirs",), PYTEST_ALLOWED_NORECURSEDIRS, "contains"),
    ExpectedSetting(("cache_dir",), ".cache/.pytest_cache"),
    ExpectedSetting(("junit_duration_report",), "call"),
    ExpectedSetting(("junit_family",), "xunit2"),
    ExpectedSetting(("junit_logging",), "log"),
    expected_true("junit_log_passing_tests"),
    ExpectedSetting(("junit_suite_name",), "codex-skills"),
)
PYTEST_DEFAULT_DISCOVERY = {
    "python_classes": frozenset({"Test"}),
    "python_files": frozenset({"*_test.py", "test_*.py"}),
    "python_functions": frozenset({"test"}),
}

VSCODE_PYTHON_SETTINGS = (
    ExpectedSetting(("editor.codeActionsOnSave", "source.fixAll.ruff"), "explicit"),
    ExpectedSetting(("editor.codeActionsOnSave", "source.organizeImports.ruff"), "explicit"),
    ExpectedSetting(("editor.defaultFormatter",), "charliermarsh.ruff"),
    expected_true("editor.formatOnSave"),
)
VSCODE_WORKSPACE_SETTINGS = (
    ExpectedSetting(("mypy-type-checker.reportingScope",), "workspace"),
    ExpectedSetting(("python.analysis.diagnosticMode",), "workspace"),
    ExpectedSetting(("python.analysis.extraPaths",), frozenset({"${workspaceFolder}"}), "contains"),
    ExpectedSetting(("python.analysis.typeCheckingMode",), "strict"),
    expected_true("python.testing.pytestEnabled"),
    expected_false("python.testing.unittestEnabled"),
)
VSCODE_INTERPRETER_SETTINGS = (
    ExpectedSetting(("python.defaultInterpreterPath",), "${workspaceFolder}\\.venv\\Scripts\\python.exe"),
)
VSCODE_RUFF_SETTINGS = (
    ExpectedSetting(("ruff.configurationPreference",), "filesystemFirst"),
    expected_true("ruff.fixAll"),
    ExpectedSetting(("ruff.format.backend",), "internal"),
    ExpectedSetting(("ruff.importStrategy",), "fromEnvironment"),
    expected_true("ruff.lint.enable"),
    ExpectedSetting(("ruff.nativeServer",), "auto"),
    expected_true("ruff.organizeImports"),
)

PACKAGE_SCRIPT_NAMES = (
    "check:python",
    "check:python:unsafe",
    "compile:python",
    "format:python",
    "lint:python",
    "lint:python:unsafe",
    "pyright",
    "python:bootstrap",
    "python:venv",
    "ruff:check",
    "ruff:check:unsafe",
    "ruff:fix",
    "ruff:fix:unsafe",
    "ruff:format",
    "ruff:format:check",
    "test:python",
    "typecheck:python",
)
REQUIRED_CHECK_SCRIPTS = frozenset({"compile:python", "lint:python", "test:python", "typecheck:python"})
PLACEHOLDER_WORDS = frozenset({"fixture", "noop", "placeholder"})
CAPABILITY_CONTRACTS = {
    "ruff:check": frozenset({"ruff-check"}),
    "ruff:check:unsafe": frozenset({"ruff-check-unsafe"}),
    "ruff:fix": frozenset({"ruff-fix"}),
    "ruff:fix:unsafe": frozenset({"ruff-fix-unsafe"}),
    "ruff:format": frozenset({"ruff-format"}),
    "ruff:format:check": frozenset({"ruff-format-check"}),
    "pyright": frozenset({"pyright"}),
    "lint:python": frozenset({"ruff-check", "ruff-format-check"}),
    "lint:python:unsafe": frozenset({"ruff-check-unsafe", "ruff-fix-unsafe"}),
    "format:python": frozenset({"ruff-fix", "ruff-format"}),
    "typecheck:python": frozenset({"mypy", "pyright"}),
    "test:python": frozenset({"pytest"}),
    "compile:python": frozenset({"compileall"}),
    "check:python": frozenset({"compileall", "mypy", "pyright", "pytest", "ruff-check", "ruff-format-check"}),
    "check:python:unsafe": frozenset(
        {"compileall", "mypy", "pyright", "pytest", "ruff-check-unsafe", "ruff-fix-unsafe"}
    ),
}
AGGREGATE_SCRIPT_CONTRACTS = {
    "check:python": REQUIRED_CHECK_SCRIPTS,
    "check:python:unsafe": frozenset({"compile:python", "lint:python:unsafe", "test:python", "typecheck:python"}),
}


class JsoncDecodeError(ValueError):
    """Indicate malformed JSONC syntax before strict JSON decoding."""


class StrictJsonConstantError(ValueError):
    """Indicate a non-finite extension rejected by strict JSON parsing."""


class StructureLimitError(ValueError):
    """Indicate that untrusted structured input exceeded a bounded audit limit."""


def reject_json_constant(value: str) -> object:
    """Reject NaN and infinity spellings accepted by Python's JSON decoder."""
    raise StrictJsonConstantError(f"non-standard JSON constant {value!r}")


def add_check(
    diagnostics: list[Diagnostic],
    check: str,
    messages: CheckMessages,
    *,
    passed: bool,
    context: DiagnosticContext = EMPTY_DIAGNOSTIC_CONTEXT,
) -> None:
    """Append a pass or failing diagnostic."""
    diagnostics.append(
        Diagnostic(
            check=check,
            message=messages.success if passed else messages.failure,
            severity="pass" if passed else "fail",
            expected=context.expected,
            actual=context.actual,
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


def string_items(value: object) -> frozenset[str] | None:
    """Return all items when a dynamic value is a list containing only strings."""
    if not isinstance(value, list):
        return None

    items = cast("list[object]", value)
    if not all(isinstance(item, str) for item in items):
        return None

    return frozenset(cast("list[str]", items))


def setting_matches(data: object, setting: ExpectedSetting) -> bool:
    """Check one typed expected setting against dynamic configuration data."""
    actual = get_nested(data, *setting.path)
    if setting.mode == "equals":
        return actual == setting.value

    expected_items = cast("frozenset[str]", setting.value)
    if setting.mode == "text-contains":
        return isinstance(actual, str) and all(item in actual for item in expected_items)

    actual_items = string_items(actual)
    return actual_items is not None and expected_items.issubset(actual_items)


def settings_match(data: object, expected: tuple[ExpectedSetting, ...]) -> bool:
    """Check a complete expected-value table against dynamic configuration data."""
    return all(setting_matches(data, setting) for setting in expected)


def is_sensitive_key(key: str) -> bool:
    """Return whether a key name commonly carries secret material."""
    lowered = key.casefold()
    return any(part in lowered for part in SENSITIVE_KEY_PARTS)


def collection_items(value: object) -> list[object] | None:
    """Return dynamic collection items with their element type made explicit."""
    if isinstance(value, list):
        return list(cast("list[object]", value))
    if isinstance(value, tuple):
        return list(cast("tuple[object, ...]", value))
    if isinstance(value, set):
        return sorted(cast("set[object]", value), key=lambda item: (type(item).__name__, str(item)[:80]))
    if isinstance(value, frozenset):
        return sorted(cast("frozenset[object]", value), key=lambda item: (type(item).__name__, str(item)[:80]))
    return None


def structure_limit_error(value: object) -> str | None:
    """Return the first bounded-structure violation using iterative traversal."""
    stack: list[tuple[object, int]] = [(value, 0)]
    visited = 0
    while stack:
        current, depth = stack.pop()
        visited += 1
        if visited > MAXIMUM_CONFIG_NODES:
            return "configuration exceeds the maximum node count"
        if depth > MAXIMUM_CONFIG_DEPTH:
            return "configuration exceeds the maximum nesting depth"
        if isinstance(current, str):
            if len(current) > MAXIMUM_CONFIG_STRING_LENGTH:
                return "configuration contains an oversized string"
            continue
        if (mapping := as_str_mapping(current)) is not None:
            if len(mapping) > MAXIMUM_CONFIG_COLLECTION_ITEMS:
                return "configuration contains an oversized object"
            stack.extend((item, depth + 1) for item in mapping.values())
            continue
        if (items := collection_items(current)) is not None:
            if len(items) > MAXIMUM_CONFIG_COLLECTION_ITEMS:
                return "configuration contains an oversized collection"
            stack.extend((item, depth + 1) for item in items)
    return None


def assign_json_value(
    parent: list[JsonValue] | dict[str, JsonValue],
    slot: int | str,
    value: JsonValue,
) -> None:
    """Assign one converted JSON value to a typed parent container."""
    if isinstance(parent, list):
        if isinstance(slot, int):
            parent[slot] = value
        return
    if isinstance(slot, str):
        parent[slot] = value


def scalar_json_value(value: object, key: str) -> tuple[bool, JsonValue]:
    """Return whether a value is scalar and its bounded conversion."""
    if key and is_sensitive_key(key):
        return True, REDACTED_VALUE
    if value is None or isinstance(value, bool | int):
        return True, value
    if isinstance(value, float):
        return True, value if math.isfinite(value) else f"<non-finite:{value}>"
    if isinstance(value, str):
        if len(value) <= MAXIMUM_REPORTED_STRING_LENGTH:
            return True, value
        return True, f"{value[:MAXIMUM_REPORTED_STRING_LENGTH]}<truncated>"
    return False, None


def json_safe(value: object, *, key: str = "") -> JsonValue:
    """Convert values with iterative depth, size, and redaction bounds."""
    holder: list[JsonValue] = [None]
    stack: list[tuple[object, str, int, list[JsonValue] | dict[str, JsonValue], int | str]] = [
        (value, key, 0, holder, 0)
    ]
    visited = 0
    while stack:
        current, current_key, depth, parent, slot = stack.pop()
        visited += 1
        if visited > MAXIMUM_DIAGNOSTIC_NODES or depth > MAXIMUM_DIAGNOSTIC_DEPTH:
            assign_json_value(parent, slot, "<diagnostic-limit>")
            continue
        is_scalar, scalar = scalar_json_value(current, current_key)
        mapping = as_str_mapping(current)
        items = collection_items(current)
        if is_scalar:
            assign_json_value(parent, slot, scalar)
        elif mapping is not None:
            selected = sorted(mapping.items())[:MAXIMUM_DIAGNOSTIC_COLLECTION_ITEMS]
            converted_mapping: dict[str, JsonValue] = {item_key: None for item_key, _item in selected}
            if len(mapping) > len(selected):
                converted_mapping["<truncated>"] = len(mapping) - len(selected)
            assign_json_value(parent, slot, converted_mapping)
            stack.extend(
                (item, item_key, depth + 1, converted_mapping, item_key) for item_key, item in reversed(selected)
            )
        elif items is not None:
            selected_items = items[:MAXIMUM_DIAGNOSTIC_COLLECTION_ITEMS]
            converted_items: list[JsonValue] = [None] * len(selected_items)
            if len(items) > len(selected_items):
                converted_items.append(f"<truncated:{len(items) - len(selected_items)}>")
            assign_json_value(parent, slot, converted_items)
            stack.extend(
                (item, "", depth + 1, converted_items, index)
                for index, item in reversed(tuple(enumerate(selected_items)))
            )
        else:
            assign_json_value(parent, slot, f"<{type(current).__name__}>")
    return holder[0]


def setting_report(data: object, expected: tuple[ExpectedSetting, ...]) -> tuple[JsonValue, JsonValue]:
    """Build field-actionable expected and mismatch payloads for settings."""
    expected_items: list[JsonValue] = []
    mismatches: list[JsonValue] = []
    for setting in expected:
        path = ".".join(setting.path)
        expected_items.append(
            {
                "path": path,
                "mode": setting.mode,
                "value": json_safe(setting.value, key=setting.path[-1]),
            }
        )
        if not setting_matches(data, setting):
            actual = get_nested(data, *setting.path)
            mismatches.append(
                {
                    "path": path,
                    "value": MISSING_VALUE if actual is None else json_safe(actual, key=setting.path[-1]),
                }
            )
    return {"settings": expected_items}, {"mismatches": mismatches}


def add_settings_check(
    diagnostics: list[Diagnostic],
    data: object,
    settings_check: SettingsCheck,
) -> None:
    """Append one diagnostic for an expected-value table."""
    expected, actual = setting_report(data, settings_check.expected)
    add_check(
        diagnostics,
        settings_check.check,
        settings_check.messages,
        passed=settings_match(data, settings_check.expected),
        context=DiagnosticContext(expected, actual),
    )


def parse_semantic_version(value: str) -> SemanticVersion | None:
    """Parse a stable three-component semantic version without dependencies."""
    parts = value.split(".")
    if len(parts) != SEMANTIC_VERSION_COMPONENTS:
        return None
    if any(not part or not part.isascii() or not part.isdecimal() for part in parts):
        return None
    if any(len(part) > 1 and part.startswith("0") for part in parts):
        return None

    major, minor, patch = (int(part) for part in parts)
    return major, minor, patch


def valid_minimum_version(value: object, minimum: SemanticVersion) -> bool:
    """Check for a valid ``>=x.y.z`` requirement meeting a semantic minimum."""
    version = minimum_requirement_version(value)
    return version is not None and version >= minimum


def minimum_requirement_version(value: object) -> SemanticVersion | None:
    """Parse one stable ``>=x.y.z`` lower-bound requirement."""
    if not isinstance(value, str):
        return None

    requirement = value.strip()
    if not requirement.startswith(">="):
        return None

    return parse_semantic_version(requirement[2:].strip())


def collection_is_empty(value: object) -> bool:
    """Return whether an optional suppression surface is absent or empty."""
    if value is None:
        return True
    return isinstance(value, list | dict) and not value


def string_list_policy(
    value: object,
    *,
    allowed: frozenset[str],
    required: frozenset[str] = EMPTY_STRING_SET,
    allow_missing: bool = False,
) -> tuple[bool, JsonValue]:
    """Validate a bounded string list against required and allowed sets."""
    items: frozenset[str]
    if value is None and allow_missing:
        items = EMPTY_STRING_SET
    else:
        parsed_items = string_items(value)
        if parsed_items is None:
            return False, {"status": "wrong-type"}
        items = parsed_items
    missing_count = len(required - items)
    unapproved_count = len(items - allowed)
    passed = missing_count == 0 and unapproved_count == 0
    status = "accepted" if passed else "missing-required" if missing_count else "unapproved-addition"
    return passed, {
        "status": status,
        "entry_count": len(items),
        "missing_count": missing_count,
        "unapproved_count": unapproved_count,
    }


def ruff_suppressions_status(ruff: object, lint: object) -> tuple[bool, JsonValue]:
    """Validate Ruff suppressions against the documented narrow allowlist."""
    ignore_ok, ignore_status = string_list_policy(
        raw_value(lint, "ignore"),
        allowed=RUFF_ALLOWED_IGNORES,
        allow_missing=True,
    )
    unfixable_ok, unfixable_status = string_list_policy(
        raw_value(lint, "unfixable"),
        allowed=RUFF_ALLOWED_UNFIXABLE,
        allow_missing=True,
    )
    per_file_value = raw_value(lint, "per-file-ignores")
    per_file = as_str_mapping(per_file_value)
    per_file_ok = per_file_value is None or per_file is not None
    per_file_count = 0
    if per_file is not None:
        per_file_count = len(per_file)
        per_file_ok = set(per_file).issubset(RUFF_ALLOWED_PER_FILE_IGNORES)
        for pattern, codes in per_file.items():
            allowed_codes = RUFF_ALLOWED_PER_FILE_IGNORES.get(pattern)
            code_items = string_items(codes)
            per_file_ok = (
                per_file_ok
                and allowed_codes is not None
                and code_items is not None
                and code_items.issubset(allowed_codes)
            )
    forbidden_values = (
        raw_value(ruff, "ignore"),
        raw_value(ruff, "extend-ignore"),
        raw_value(ruff, "unfixable"),
        raw_value(ruff, "extend-unfixable"),
        raw_value(ruff, "per-file-ignores"),
        raw_value(ruff, "extend-per-file-ignores"),
        raw_value(lint, "extend-ignore"),
        raw_value(lint, "extend-unfixable"),
        raw_value(lint, "extend-per-file-ignores"),
    )
    no_hidden_extensions = all(collection_is_empty(value) for value in forbidden_values)
    passed = ignore_ok and unfixable_ok and per_file_ok and no_hidden_extensions
    return passed, {
        "ignore": ignore_status,
        "unfixable": unfixable_status,
        "per_file": {
            "status": "accepted" if per_file_ok else "unapproved-pattern-or-code",
            "entry_count": per_file_count,
        },
        "hidden_extension_status": "absent" if no_hidden_extensions else "present",
    }


def ruff_exclusions_status(ruff: object) -> tuple[bool, JsonValue]:
    """Require documented Ruff exclusions and reject every unapproved addition."""
    exclusions_ok, status = string_list_policy(
        raw_value(ruff, "extend-exclude"),
        allowed=RUFF_ALLOWED_EXCLUSIONS,
        required=RUFF_REQUIRED_EXCLUSIONS,
    )
    base_exclude_empty = collection_is_empty(raw_value(ruff, "exclude"))
    passed = exclusions_ok and base_exclude_empty
    return passed, {
        "extend_exclude": status,
        "base_exclude_status": "empty" if base_exclude_empty else "unapproved",
    }


def parse_mypy_exclusions(value: object) -> frozenset[str] | None:
    """Parse only the canonical path-segment mypy exclusion regex grammar."""
    compact = re.sub(r"\s+", "", value) if isinstance(value, str) else ""
    valid = compact.startswith("(?x)(") and compact.endswith(")")
    body = compact[5:-1] if valid else ""
    names: set[str] = set()
    index = 0
    while valid and index < len(body):
        if not body.startswith(MYPY_EXCLUSION_PREFIX, index):
            valid = False
            break
        index += len(MYPY_EXCLUSION_PREFIX)
        separator = body.find("/", index)
        if separator < 0:
            valid = False
            break
        escaped_name = body[index:separator]
        name = next(
            (candidate for candidate in MYPY_ALLOWED_EXCLUSIONS if candidate.replace(".", r"\.") == escaped_name),
            None,
        )
        if name is None or name in names:
            valid = False
            break
        names.add(name)
        index = separator + 1
        if index < len(body):
            if body[index] != "|":
                valid = False
                break
            index += 1
    return frozenset(names) if valid and names else None


def mypy_exclusions_status(mypy: object) -> tuple[bool, JsonValue]:
    """Reject catch-all regexes while allowing only known directory segments."""
    names = parse_mypy_exclusions(raw_value(mypy, "exclude"))
    missing_count = len(MYPY_REQUIRED_EXCLUSIONS - (names or frozenset()))
    passed = names is not None and missing_count == 0 and names.issubset(MYPY_ALLOWED_EXCLUSIONS)
    return passed, {
        "status": "accepted" if passed else "invalid-or-catch-all",
        "entry_count": len(names or ()),
        "missing_count": missing_count,
    }


def mypy_setting_weakens_strictness(key: str, value: object) -> bool:
    """Identify dynamic global settings that negate or bypass strict analysis."""
    if key.startswith("allow_") and value is True:
        return True
    if key.startswith("disallow_") and value is False:
        return True
    if key == "strict_optional" and value is False:
        return True
    return key in {"exclude_gitignore", "implicit_optional"} and value is True


def mypy_suppressions_status(mypy: object) -> tuple[bool, JsonValue]:
    """Reject global and override-based ways to nullify mypy analysis."""
    mapping = as_str_mapping(mypy) or {}
    overrides_empty = collection_is_empty(raw_value(mypy, "overrides"))
    disabled_codes_empty = collection_is_empty(raw_value(mypy, "disable_error_code"))
    booleans_safe = (
        raw_value(mypy, "ignore_errors") is not True and raw_value(mypy, "ignore_missing_imports") is not True
    )
    strict_settings_safe = all(raw_value(mypy, setting) is not False for setting in MYPY_STRICT_NEGATING_SETTINGS)
    follow_imports = raw_value(mypy, "follow_imports")
    imports_safe = follow_imports not in {"skip", "silent"}
    collection_suppressions_empty = all(
        collection_is_empty(raw_value(mypy, setting))
        for setting in ("always_false", "always_true", "untyped_calls_exclude")
    )
    dynamic_weakening_count = sum(mypy_setting_weakens_strictness(key, value) for key, value in mapping.items())
    passed = all(
        (
            overrides_empty,
            disabled_codes_empty,
            booleans_safe,
            strict_settings_safe,
            imports_safe,
            collection_suppressions_empty,
            dynamic_weakening_count == 0,
        )
    )
    return passed, {
        "overrides": "empty" if overrides_empty else "present",
        "disabled_error_codes": "empty" if disabled_codes_empty else "present",
        "global_ignore_status": "absent" if booleans_safe else "enabled",
        "strict_negation_status": "absent" if strict_settings_safe else "present",
        "import_suppression_status": "absent" if imports_safe else "present",
        "collection_suppression_status": "absent" if collection_suppressions_empty else "present",
        "dynamic_weakening_count": dynamic_weakening_count,
    }


def pyright_exclusions_status(pyright: object) -> tuple[bool, JsonValue]:
    """Require documented Pyright exclusions and reject root-wide additions."""
    return string_list_policy(
        raw_value(pyright, "exclude"),
        allowed=PYRIGHT_ALLOWED_EXCLUSIONS,
        required=PYRIGHT_REQUIRED_EXCLUSIONS,
    )


def pyright_suppressions_status(pyright: object) -> tuple[bool, JsonValue]:
    """Reject Pyright ignore surfaces and downgraded report diagnostics."""
    mapping = as_str_mapping(pyright)
    if mapping is None:
        return False, {"status": "missing-table"}
    ignored_empty = collection_is_empty(mapping.get("ignore"))
    environments_empty = collection_is_empty(mapping.get("executionEnvironments"))
    severity_overrides_empty = collection_is_empty(mapping.get("diagnosticSeverityOverrides"))
    downgraded_reports = sum(
        1 for key, value in mapping.items() if key.startswith("report") and value is not True and value != "error"
    )
    passed = ignored_empty and environments_empty and severity_overrides_empty and downgraded_reports == 0
    return passed, {
        "ignore": "empty" if ignored_empty else "present",
        "execution_environments": "empty" if environments_empty else "present",
        "severity_overrides": "empty" if severity_overrides_empty else "present",
        "downgraded_report_count": downgraded_reports,
    }


def pytest_suppressions_status(options: object) -> tuple[bool, JsonValue]:
    """Reject additive pytest options that disable execution or discovery."""
    addopts = string_items(raw_value(options, "addopts"))
    prohibited = NO_OP_FLAGS | PYTEST_NO_OP_FLAGS | PYTEST_CONFIG_OVERRIDE_FLAGS | PYTEST_DISCOVERY_BYPASS_FLAGS
    unsafe_addopts_count = sum(
        option.casefold().split("=", maxsplit=1)[0] in prohibited for option in addopts or EMPTY_STRING_SET
    )
    collection_ignores_empty = all(
        collection_is_empty(raw_value(options, setting)) for setting in ("collect_ignore", "collect_ignore_glob")
    )
    norecursedirs = string_items(raw_value(options, "norecursedirs"))
    norecursedirs_safe = norecursedirs == PYTEST_ALLOWED_NORECURSEDIRS
    discovery_overrides_safe = all(
        raw_value(options, setting) is None or string_items(raw_value(options, setting)) == defaults
        for setting, defaults in PYTEST_DEFAULT_DISCOVERY.items()
    )
    passed = (
        addopts is not None
        and unsafe_addopts_count == 0
        and collection_ignores_empty
        and norecursedirs_safe
        and discovery_overrides_safe
    )
    return passed, {
        "unsafe_addopts_count": unsafe_addopts_count,
        "collection_ignore_status": "absent" if collection_ignores_empty else "present",
        "norecursedirs_status": "allowlisted" if norecursedirs_safe else "unapproved",
        "discovery_override_status": "default-or-absent" if discovery_overrides_safe else "unapproved",
    }


def copy_json_string(source: str, start: int, output: list[str]) -> int:
    """Copy one quoted JSON string without interpreting comment markers."""
    index = start
    escaped = False
    while index < len(source):
        character = source[index]
        output.append(character)
        index += 1
        if escaped:
            escaped = False
        elif character == "\\":
            escaped = True
        elif character == '"' and index > start + 1:
            return index

    return index


def replace_line_comment(source: str, start: int, output: list[str]) -> int:
    """Replace a line comment with whitespace and preserve its newline."""
    index = start
    while index < len(source) and source[index] not in "\r\n":
        output.append(" ")
        index += 1
    return index


def replace_block_comment(source: str, start: int, output: list[str]) -> int:
    """Replace a block comment with whitespace and preserve its newlines."""
    index = start
    while index < len(source):
        character = source[index]
        following = source[index + 1] if index + 1 < len(source) else ""
        if character == "*" and following == "/":
            output.extend((" ", " "))
            return index + 2
        output.append(character if character in "\r\n" else " ")
        index += 1

    raise JsoncDecodeError("unterminated block comment")


def strip_jsonc_comments(source: str) -> str:
    """Replace JSONC comments with whitespace while preserving strings and lines."""
    output: list[str] = []
    index = 0
    while index < len(source):
        character = source[index]
        following = source[index + 1] if index + 1 < len(source) else ""
        if character == '"':
            index = copy_json_string(source, index, output)
        elif character == "/" and following == "/":
            index = replace_line_comment(source, index, output)
        elif character == "/" and following == "*":
            index = replace_block_comment(source, index, output)
        else:
            output.append(character)
            index += 1

    return "".join(output)


def strip_jsonc_trailing_commas(source: str) -> str:
    """Remove commas before object or array endings without changing strings."""
    output: list[str] = []
    index = 0
    in_string = False
    escaped = False

    while index < len(source):
        character = source[index]
        if in_string:
            output.append(character)
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            index += 1
            continue

        if character == '"':
            output.append(character)
            in_string = True
            index += 1
            continue

        if character == ",":
            lookahead = index + 1
            while lookahead < len(source) and source[lookahead].isspace():
                lookahead += 1
            if lookahead < len(source) and source[lookahead] in "}]":
                index += 1
                continue

        output.append(character)
        index += 1

    return "".join(output)


def parse_jsonc(source: str) -> object:
    """Parse the JSONC subset used by VS Code settings."""
    without_comments = strip_jsonc_comments(source)
    without_trailing_commas = strip_jsonc_trailing_commas(without_comments)
    return json.loads(without_trailing_commas, parse_constant=reject_json_constant)


def add_load_failure(diagnostics: list[Diagnostic], check: str, path: Path, error: Exception) -> None:
    """Convert a configuration loading exception into a failing diagnostic."""
    diagnostics.append(
        Diagnostic(
            check=check,
            message=f"{path.name} could not be parsed: {error}",
            severity="fail",
            expected={"top_level": "object", "syntax": "strict-json" if path.name == "package.json" else "valid"},
            actual={"error_type": type(error).__name__},
        )
    )


def enforce_file_size(path: Path, maximum_bytes: int) -> None:
    """Raise a structured limit error for an oversized untrusted file."""
    if path.stat().st_size > maximum_bytes:
        raise StructureLimitError("configuration file exceeds the maximum byte size")


def enforce_structure_limits(data: object) -> None:
    """Raise a structured limit error for oversized or deeply nested data."""
    if (limit_error := structure_limit_error(data)) is not None:
        raise StructureLimitError(limit_error)


def load_json_object(
    path: Path,
    diagnostics: list[Diagnostic],
    check: str,
    *,
    allow_jsonc: bool,
) -> dict[str, object] | None:
    """Load a strict JSON or JSONC object and report malformed input."""
    try:
        enforce_file_size(path, MAXIMUM_CONFIG_FILE_BYTES)
        source = path.read_text(encoding="utf-8")
        data = parse_jsonc(source) if allow_jsonc else json.loads(source, parse_constant=reject_json_constant)
        enforce_structure_limits(data)
    except (
        JsoncDecodeError,
        StrictJsonConstantError,
        StructureLimitError,
        json.JSONDecodeError,
        OSError,
        RecursionError,
        UnicodeError,
    ) as error:
        add_load_failure(diagnostics, check, path, error)
        return None

    mapping = as_str_mapping(data)
    if mapping is None:
        diagnostics.append(
            Diagnostic(
                check=check,
                message=f"{path.name} must contain a JSON object at the top level.",
                severity="fail",
                expected={"top_level": "object"},
                actual={"top_level": type(data).__name__},
            )
        )
        return None

    return mapping


def load_toml_object(path: Path, diagnostics: list[Diagnostic], check: str) -> dict[str, object] | None:
    """Load a TOML object and report malformed input."""
    try:
        enforce_file_size(path, MAXIMUM_CONFIG_FILE_BYTES)
        with path.open("rb") as handle:
            data: object = tomllib.load(handle)
        enforce_structure_limits(data)
    except (OSError, RecursionError, StructureLimitError, tomllib.TOMLDecodeError) as error:
        add_load_failure(diagnostics, check, path, error)
        return None

    mapping = as_str_mapping(data)
    if mapping is None:
        diagnostics.append(
            Diagnostic(
                check=check,
                message=f"{path.name} must contain a TOML table at the top level.",
                severity="fail",
                expected={"top_level": "table"},
                actual={"top_level": type(data).__name__},
            )
        )
        return None

    return mapping


def raw_value(value: object, key: str) -> object | None:
    """Return a key from a dynamic mapping."""
    mapping = as_str_mapping(value)
    if mapping is None:
        return None

    return mapping.get(key)


@dataclass(frozen=True)
class ParsedScript:
    """A statically parsed npm script; no command is ever executed."""

    commands: tuple[tuple[str, ...], ...]
    operators: tuple[str, ...]
    error: str | None = None


@dataclass(frozen=True)
class GraphResult:
    """Bounded npm-script reachability result."""

    reached: frozenset[str]
    issue: str | None = None


@dataclass(frozen=True)
class DependencyProfile:
    """One accepted dependency bootstrap profile with a private source path."""

    kind: str
    target: str
    source_id: str


@dataclass(frozen=True)
class SourceValidation:
    """Sanitized dependency-source validation result."""

    passed: bool
    exists: bool


def tokenize_script(value: str) -> tuple[list[str], str | None]:
    """Tokenize the shell subset needed for npm scripts without evaluating it."""
    if len(value) > MAXIMUM_SCRIPT_LENGTH:
        return [], "command-length-limit"
    if "\n" in value or "\r" in value:
        return [], "multiline-command"
    lexer = shlex.shlex(value, posix=False, punctuation_chars="&|;<>()")
    lexer.commenters = ""
    lexer.whitespace_split = True
    raw_tokens: list[str] = []
    try:
        for token in lexer:
            raw_tokens.append(token)
            if len(raw_tokens) > MAXIMUM_SCRIPT_TOKENS:
                return [], "token-count-limit"
            if len(token) > MAXIMUM_TOKEN_LENGTH:
                return [], "token-length-limit"
    except ValueError:
        return [], "invalid-quoting"
    tokens = [
        token[1:-1]
        if len(token) >= MINIMUM_QUOTED_TOKEN_LENGTH and token[0] == token[-1] and token[0] in {'"', "'"}
        else token
        for token in raw_tokens
    ]
    return tokens, None


def parse_script(value: str) -> ParsedScript:
    """Split a script into commands and operators for static graph analysis."""
    tokens, error = tokenize_script(value)
    if error is not None:
        return ParsedScript((), (), error)
    commands: list[tuple[str, ...]] = []
    operators: list[str] = []
    current: list[str] = []
    for token in tokens:
        if token and all(character in "&|;<>()" for character in token):
            if not current:
                return ParsedScript((), (), "empty command around an operator")
            if token != SAFE_CHAIN_OPERATOR:
                return ParsedScript((), (), "unsafe-or-unsupported-operator")
            commands.append(tuple(current))
            current = []
            operators.append(token)
            if len(commands) >= MAXIMUM_SCRIPT_COMMANDS:
                return ParsedScript((), (), "command-count-limit")
        else:
            current.append(token)
    if not current:
        return ParsedScript((), (), "empty command")
    commands.append(tuple(current))
    return ParsedScript(tuple(commands), tuple(operators))


def command_name(token: str) -> str:
    """Normalize an executable token without resolving or running it."""
    return token.replace("/", "\\").rsplit("\\", maxsplit=1)[-1].casefold()


def normalized_path_token(token: str) -> str:
    """Normalize a command path lexically without touching the file system."""
    normalized = token.replace("\\", "/").casefold()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def command_has_shell_expansion(command: tuple[str, ...]) -> bool:
    """Reject shell substitutions that static token analysis cannot safely model."""
    return any("$(" in token or "${" in token or "`" in token for token in command)


def tool_arguments(command: tuple[str, ...], tool: str) -> tuple[str, ...] | None:
    """Return arguments for a direct tool or ``python -m`` invocation."""
    if not command:
        return None
    executable = command_name(command[0])
    if executable in {tool, f"{tool}.exe", f"{tool}.cmd"}:
        return command[1:]
    if (
        executable in {"python", "python.exe", "py", "py.exe"}
        and len(command) >= MINIMUM_TOOL_COMMAND_LENGTH
        and command[1:MINIMUM_TOOL_COMMAND_LENGTH] == ("-m", tool)
    ):
        return command[MINIMUM_TOOL_COMMAND_LENGTH:]
    return None


def npm_reference(command: tuple[str, ...]) -> str | None:
    """Return the statically referenced npm script name, when present."""
    if len(command) != MINIMUM_TOOL_COMMAND_LENGTH or command_name(command[0]) not in {"npm", "npm.cmd"}:
        return None
    if command[1] not in {"run", "run-script"}:
        return None
    return command[2] or None


def is_npm_command(command: tuple[str, ...]) -> bool:
    """Return whether a command starts with npm, even when its grammar is invalid."""
    return bool(command) and command_name(command[0]) in {"npm", "npm.cmd"}


def arguments_have_flags(arguments: tuple[str, ...], prohibited: frozenset[str]) -> bool:
    """Return whether arguments contain a prohibited exact or value-taking flag."""
    return any(argument.casefold().split("=", maxsplit=1)[0] in prohibited for argument in arguments)


def positional_arguments(arguments: tuple[str, ...], *, value_options: frozenset[str]) -> tuple[str, ...]:
    """Return apparent positional arguments after known option values are removed."""
    positional: list[str] = []
    skip_next = False
    for argument in arguments:
        if skip_next:
            skip_next = False
        elif argument in value_options:
            skip_next = True
        elif not argument.startswith("-"):
            positional.append(argument)
    return tuple(positional)


def ruff_capability(command: tuple[str, ...]) -> str | None:
    """Return the strict Ruff capability represented by one command."""
    arguments = tool_arguments(command, "ruff")
    if not arguments or arguments_have_flags(arguments, NO_OP_FLAGS):
        return None
    operation = arguments[0]
    allowed_options = {"format": frozenset({"--check"}), "check": frozenset({"--fix", "--unsafe-fixes"})}
    capability: str | None = None
    if operation in allowed_options:
        options = frozenset(argument for argument in arguments[1:] if argument.startswith("-"))
        targets = tuple(argument for argument in arguments[1:] if not argument.startswith("-"))
        if options.issubset(allowed_options[operation]) and targets:
            if operation == "format":
                capability = "ruff-format-check" if "--check" in options else "ruff-format"
            elif "--fix" in options:
                capability = "ruff-fix-unsafe" if "--unsafe-fixes" in options else "ruff-fix"
            else:
                capability = "ruff-check-unsafe" if "--unsafe-fixes" in options else "ruff-check"
    return capability


def compileall_capability(command: tuple[str, ...]) -> str | None:
    """Return compileall only when quiet, exclusions, and targets are present."""
    arguments = tool_arguments(command, "compileall")
    if arguments is None or arguments_have_flags(arguments, NO_OP_FLAGS):
        return None
    targets: list[str] = []
    has_quiet = False
    has_exclusion = False
    index = 0
    while index < len(arguments):
        argument = arguments[index]
        if argument == "-q":
            has_quiet = True
        elif argument in {"-x", "--exclude"}:
            if has_exclusion or index + 1 >= len(arguments):
                return None
            has_exclusion = True
            index += 1
        elif argument.startswith("-"):
            return None
        else:
            targets.append(argument)
        index += 1
    return "compileall" if has_quiet and has_exclusion and targets else None


def pytest_arguments_are_enforcing(arguments: tuple[str, ...]) -> bool:
    """Reject pytest discovery-only and configuration-override invocations."""
    prohibited = NO_OP_FLAGS | PYTEST_NO_OP_FLAGS | PYTEST_CONFIG_OVERRIDE_FLAGS
    return not arguments_have_flags(arguments, prohibited)


def node_helper_capabilities(command: tuple[str, ...]) -> frozenset[str] | None:
    """Recognize only the two documented repository-local Node helpers."""
    if len(command) < MINIMUM_QUOTED_TOKEN_LENGTH or command_name(command[0]) not in {"node", "node.exe"}:
        return None
    helper = normalized_path_token(command[1])
    if helper not in SAFE_NODE_HELPERS:
        return None
    arguments = command[2:]
    if helper == "tools/run-pytest.mjs":
        return frozenset({"pytest"}) if pytest_arguments_are_enforcing(arguments) else None
    return frozenset() if not arguments else None


def command_capabilities(command: tuple[str, ...]) -> frozenset[str] | None:
    """Return strict capabilities for one fully modeled non-alias command."""
    if not command or command_has_shell_expansion(command):
        return None
    capabilities: frozenset[str] | None = None
    if (ruff := ruff_capability(command)) is not None:
        capabilities = frozenset({ruff})
    elif (compileall := compileall_capability(command)) is not None:
        capabilities = frozenset({compileall})
    else:
        for tool in ("mypy", "pyright"):
            arguments = tool_arguments(command, tool)
            if arguments is not None:
                if not arguments:
                    capabilities = frozenset({tool})
                break
        pytest_arguments = tool_arguments(command, "pytest")
        if pytest_arguments is not None and pytest_arguments_are_enforcing(pytest_arguments):
            capabilities = frozenset({"pytest"})
        if capabilities is None:
            capabilities = node_helper_capabilities(command)
    return capabilities


def direct_capabilities(parsed: ParsedScript) -> frozenset[str]:
    """Identify strict-tool capabilities directly invoked by one parsed script."""
    capabilities: set[str] = set()
    for command in parsed.commands:
        if npm_reference(command) is not None:
            continue
        modeled = command_capabilities(command)
        if modeled is not None:
            capabilities.update(modeled)
    return frozenset(capabilities)


def script_is_placeholder(parsed: ParsedScript) -> bool:
    """Reject fixture/no-op bodies that can make a hollow profile look complete."""
    for command in parsed.commands:
        lowered = tuple(token.casefold() for token in command)
        if any(token in PLACEHOLDER_WORDS for token in lowered):
            return True
        if lowered[:2] in {("exit", "0"), ("return", "0")}:
            return True
        if lowered and command_name(lowered[0]) in {"true", "true.exe"}:
            return True
    return False


def graph_has_cycle(adjacency: dict[str, frozenset[str]]) -> bool:
    """Detect a cycle iteratively with Kahn's algorithm."""
    indegree = dict.fromkeys(adjacency, 0)
    for references in adjacency.values():
        for reference in references:
            if reference in indegree:
                indegree[reference] += 1
    queue = [name for name, degree in indegree.items() if degree == 0]
    processed = 0
    while queue:
        current = queue.pop()
        processed += 1
        for reference in adjacency[current]:
            if reference not in indegree:
                continue
            indegree[reference] -= 1
            if indegree[reference] == 0:
                queue.append(reference)
    return processed != len(adjacency)


def parsed_script_references(parsed: ParsedScript | None) -> tuple[frozenset[str], str | None]:
    """Validate one graph node and return only exact npm-run references."""
    issue: str | None = None
    references: set[str] = set()
    if parsed is None:
        issue = "missing-referenced-script"
    elif parsed.error is not None:
        issue = "invalid-referenced-script"
    elif script_is_placeholder(parsed):
        issue = "placeholder-or-no-op"
    elif any(operator != SAFE_CHAIN_OPERATOR for operator in parsed.operators):
        issue = "unsafe-chain-operator"
    else:
        for command in parsed.commands:
            if command_has_shell_expansion(command):
                issue = "shell-expansion"
                break
            reference = npm_reference(command)
            if reference is not None:
                references.add(reference)
            elif is_npm_command(command):
                issue = "invalid-npm-run"
                break
    return frozenset(references), issue


def reachable_scripts(name: str, parsed_scripts: dict[str, ParsedScript]) -> GraphResult:
    """Return bounded npm-script graph reachability without recursive traversal."""
    pending = [name]
    reached: set[str] = set()
    adjacency: dict[str, frozenset[str]] = {}
    edge_count = 0
    issue: str | None = None
    while pending and issue is None:
        current = pending.pop()
        if current in reached:
            continue
        reached.add(current)
        if len(reached) > MAXIMUM_GRAPH_NODES:
            issue = "graph-node-limit"
            break
        references, issue = parsed_script_references(parsed_scripts.get(current))
        if issue is not None:
            break
        edge_count += len(references)
        if edge_count > MAXIMUM_GRAPH_EDGES:
            issue = "graph-edge-limit"
            break
        adjacency[current] = references
        pending.extend(reference for reference in references if reference not in reached)
    if issue is None and graph_has_cycle(adjacency):
        issue = "npm-run-cycle"
    if issue is not None:
        return GraphResult(frozenset(), issue)
    reached.discard(name)
    return GraphResult(frozenset(reached))


def reachable_capabilities(name: str, parsed_scripts: dict[str, ParsedScript]) -> tuple[frozenset[str], str | None]:
    """Return capabilities from a bounded graph whose commands are all modeled."""
    graph = reachable_scripts(name, parsed_scripts)
    if graph.issue is not None:
        return frozenset(), graph.issue
    capabilities: set[str] = set()
    for script_name in (name, *sorted(graph.reached)):
        parsed = parsed_scripts[script_name]
        for command in parsed.commands:
            if npm_reference(command) is not None:
                continue
            modeled = command_capabilities(command)
            if modeled is None:
                return frozenset(), "unsupported-or-no-op-command"
            capabilities.update(modeled)
    return frozenset(capabilities), None


def interpreter_kind(command: tuple[str, ...]) -> str | None:
    """Classify only bare or repository-local Python interpreter tokens."""
    if not command:
        return None
    normalized = normalized_path_token(command[0])
    if "/" not in normalized and normalized in {"python", "python.exe"}:
        return "global"
    if normalized in {".venv/bin/python", ".venv/bin/python3", ".venv/scripts/python.exe"}:
        return "local"
    return None


def safe_named_lock(candidate: str) -> bool:
    """Validate a conservative named-pylock identifier without exposing it."""
    lowered = candidate.casefold()
    if candidate != lowered or SAFE_NAMED_LOCK_PATTERN.fullmatch(lowered) is None:
        return False
    identifier = lowered.removeprefix("pylock.").removesuffix(".toml")
    return identifier == "pylock" or not any(part in identifier for part in SENSITIVE_KEY_PARTS)


def pip_install_profile(command: tuple[str, ...], *, allowed_interpreters: frozenset[str]) -> DependencyProfile | None:
    """Recognize the exact safe pip grammar for one authoritative source."""
    if interpreter_kind(command) not in allowed_interpreters:
        return None
    arguments = tool_arguments(command, "pip")
    if arguments == ("install", "-r", "requirements-dev.txt"):
        return DependencyProfile("pip-requirements", "requirements-dev.txt", "requirements-pinned")
    if arguments == ("install", "--require-hashes", "-r", "requirements-dev.in"):
        return DependencyProfile("pip-requirements-hashed", "requirements-dev.in", "requirements-hashed")
    if arguments is None or len(arguments) != MINIMUM_TOOL_COMMAND_LENGTH or arguments[0:2] != ("install", "-r"):
        return None
    candidate = arguments[2]
    if not safe_named_lock(candidate):
        return None
    source_id = "pylock-default" if candidate == "pylock.toml" else "pylock-named"
    return DependencyProfile("pip-pylock", candidate, source_id)


def uv_profile(command: tuple[str, ...]) -> DependencyProfile | None:
    """Recognize an exact frozen uv synchronization command."""
    if command and command_name(command[0]) in {"uv", "uv.exe"} and command[1:] == ("sync", "--frozen"):
        return DependencyProfile("uv-frozen", "uv.lock", "uv-lock")
    return None


def bootstrap_profile(parsed: ParsedScript) -> DependencyProfile | None:
    """Recognize the documented requirements, pylock, or frozen-uv bootstrap profile."""
    if (
        parsed.error is not None
        or script_is_placeholder(parsed)
        or len(parsed.commands) != 1
        or parsed.operators
        or command_has_shell_expansion(parsed.commands[0])
    ):
        return None
    command = parsed.commands[0]
    return uv_profile(command) or pip_install_profile(command, allowed_interpreters=frozenset({"global"}))


def is_venv_command(command: tuple[str, ...]) -> bool:
    """Recognize creation of the documented repository-local virtual environment."""
    arguments = tool_arguments(command, "venv")
    return interpreter_kind(command) == "global" and arguments == (".venv",)


def is_activation_command(command: tuple[str, ...]) -> bool:
    """Recognize Windows or POSIX activation of the local environment."""
    activation_paths = frozenset({".venv/bin/activate", ".venv/scripts/activate", ".venv/scripts/activate.ps1"})
    if len(command) == 1:
        return normalized_path_token(command[0]) in activation_paths
    return (
        len(command) == MINIMUM_QUOTED_TOKEN_LENGTH
        and command[0] == "."
        and normalized_path_token(command[1]) in activation_paths
    )


def venv_profile(parsed: ParsedScript) -> DependencyProfile | None:
    """Recognize a documented local-venv bootstrap without evaluating it."""
    direct_profile = bootstrap_profile(parsed)
    if direct_profile is not None and direct_profile.kind == "uv-frozen":
        return direct_profile
    if parsed.error is not None or not parsed.commands or not is_venv_command(parsed.commands[0]):
        return None
    if any(operator != SAFE_CHAIN_OPERATOR for operator in parsed.operators):
        return None
    remaining = list(parsed.commands[1:])
    activated = bool(remaining and is_activation_command(remaining[0]))
    if activated:
        _ = remaining.pop(0)
    if len(remaining) != 1:
        return None
    allowed_interpreters = frozenset({"global", "local"}) if activated else frozenset({"local"})
    return pip_install_profile(remaining[0], allowed_interpreters=allowed_interpreters)


def strip_requirement_comment(line: str) -> str:
    """Strip a requirements comment marker outside quoted marker values."""
    quote = ""
    for index, character in enumerate(line):
        if character in {'"', "'"}:
            quote = "" if quote == character else quote or character
        elif character == "#" and not quote and (index == 0 or line[index - 1].isspace()):
            return line[:index].rstrip()
    return line


def logical_requirement_lines(contents: str) -> tuple[str, ...] | None:
    """Join bounded pip continuation lines without interpreting directives."""
    entries: list[str] = []
    current = ""
    for raw_line in contents.splitlines():
        if len(raw_line) > MAXIMUM_REQUIREMENT_LINE_LENGTH:
            return None
        stripped = strip_requirement_comment(raw_line.strip())
        if not stripped:
            continue
        continued = stripped.endswith("\\")
        piece = stripped[:-1].rstrip() if continued else stripped
        current = f"{current} {piece}".strip()
        if len(current) > MAXIMUM_CONFIG_STRING_LENGTH:
            return None
        if not continued:
            entries.append(current)
            current = ""
            if len(entries) > MAXIMUM_REQUIREMENT_ENTRIES:
                return None
    return None if current else tuple(entries)


def normalized_package_name(name: str) -> str:
    """Apply the standard case-insensitive Python package-name normalization."""
    return re.sub(r"[-_.]+", "-", name).casefold()


def parse_requirement_entry(entry: str, *, require_hashes: bool) -> tuple[str, str] | None:
    """Parse one exact-pinned PEP 508-like requirement and its hashes."""
    try:
        tokens = tuple(shlex.split(entry, posix=True))
    except ValueError:
        return None
    if not tokens:
        return None
    hash_index = next((index for index, token in enumerate(tokens) if token.startswith("--hash")), len(tokens))
    requirement = " ".join(tokens[:hash_index])
    hash_tokens = tokens[hash_index:]
    if any(VALID_SHA256_PATTERN.fullmatch(token.removeprefix("--hash=")) is None for token in hash_tokens):
        return None
    if require_hashes != bool(hash_tokens):
        return None
    match = REQUIREMENT_PATTERN.fullmatch(requirement)
    if (
        match is None
        or "@" in requirement
        or "\\" in requirement
        or PINNED_VERSION_PATTERN.fullmatch(match.group("version")) is None
    ):
        return None
    return normalized_package_name(match.group("name")), match.group("version")


def requirements_are_secure(contents: str, *, require_hashes: bool, ruff_minimum: SemanticVersion) -> bool:
    """Validate exact pins, optional all-entry hashes, and required strict tools."""
    entries = logical_requirement_lines(contents)
    if not entries:
        return False
    versions: dict[str, str] = {}
    for entry in entries:
        parsed = parse_requirement_entry(entry, require_hashes=require_hashes)
        if parsed is None:
            return False
        name, version = parsed
        if name in versions and versions[name] != version:
            return False
        versions[name] = version
    if not REQUIRED_TOOL_NAMES.issubset(versions):
        return False
    ruff_version = parse_semantic_version(versions["ruff"])
    return ruff_version is not None and ruff_version >= ruff_minimum


def valid_sha256(value: object) -> bool:
    """Validate a sha256 digest with or without its algorithm prefix."""
    if not isinstance(value, str):
        return False
    candidate = value.removeprefix("sha256:")
    return len(candidate) == SHA256_HEX_LENGTH and all(character in "0123456789abcdefABCDEF" for character in candidate)


def artifact_is_secure(value: object) -> bool:
    """Validate one lock artifact identity and sha256 hash table."""
    artifact = as_str_mapping(value)
    if artifact is None:
        return False
    identity = raw_value(artifact, "name") or raw_value(artifact, "url")
    if not isinstance(identity, str) or not identity:
        return False
    direct_hash = raw_value(artifact, "hash")
    if direct_hash is not None:
        return valid_sha256(direct_hash)
    hashes = as_str_mapping(raw_value(artifact, "hashes"))
    return hashes is not None and set(hashes) == {"sha256"} and valid_sha256(hashes["sha256"])


def package_artifacts_are_secure(package: dict[str, object]) -> bool:
    """Validate every wheel and optional source distribution in a lock package."""
    artifacts: list[object] = []
    wheels = raw_value(package, "wheels")
    if wheels is not None:
        if not isinstance(wheels, list):
            return False
        artifacts.extend(cast("list[object]", wheels))
    source_distribution = raw_value(package, "sdist")
    if source_distribution is not None:
        artifacts.append(source_distribution)
    return bool(artifacts) and all(artifact_is_secure(artifact) for artifact in artifacts)


def lock_package_versions(packages_value: object, *, require_all_artifacts: bool) -> dict[str, str] | None:
    """Validate bounded lock package records and return normalized versions."""
    if not isinstance(packages_value, list) or not packages_value:
        return None
    versions: dict[str, str] = {}
    for package_value in cast("list[object]", packages_value):
        package = as_str_mapping(package_value)
        if package is None:
            return None
        name = raw_value(package, "name")
        version = raw_value(package, "version")
        if (
            not isinstance(name, str)
            or not name
            or not isinstance(version, str)
            or PINNED_VERSION_PATTERN.fullmatch(version) is None
        ):
            return None
        normalized_name = normalized_package_name(name)
        if normalized_name in versions and versions[normalized_name] != version:
            return None
        source = as_str_mapping(raw_value(package, "source"))
        is_registry_package = source is None or "registry" in source
        artifacts_secure = package_artifacts_are_secure(package)
        if (
            require_all_artifacts or is_registry_package or normalized_name in REQUIRED_TOOL_NAMES
        ) and not artifacts_secure:
            return None
        versions[normalized_name] = version
    return versions


def required_lock_tools_are_secure(versions: dict[str, str] | None, ruff_minimum: SemanticVersion) -> bool:
    """Require all invoked strict tools and a Ruff pin satisfying configuration."""
    if versions is None or not REQUIRED_TOOL_NAMES.issubset(versions):
        return False
    ruff_version = parse_semantic_version(versions["ruff"])
    return ruff_version is not None and ruff_version >= ruff_minimum


def pylock_is_secure(data: dict[str, object], ruff_minimum: SemanticVersion) -> bool:
    """Validate structural package, version, artifact, and hash integrity for pylock."""
    lock_version = raw_value(data, "lock-version")
    versions = lock_package_versions(raw_value(data, "packages"), require_all_artifacts=True)
    return lock_version == "1.0" and required_lock_tools_are_secure(versions, ruff_minimum)


def uv_lock_is_secure(data: dict[str, object], ruff_minimum: SemanticVersion) -> bool:
    """Validate structural package, version, artifact, and hash integrity for uv.lock."""
    lock_version = raw_value(data, "version")
    versions = lock_package_versions(raw_value(data, "package"), require_all_artifacts=False)
    return (
        isinstance(lock_version, int) and lock_version >= 1 and required_lock_tools_are_secure(versions, ruff_minimum)
    )


def read_dependency_text(root: Path, profile: DependencyProfile) -> tuple[str | None, bool]:
    """Read one flat allowlisted dependency source without following it outside the root."""
    source_path = root / profile.target
    exists = source_path.exists()
    try:
        if not exists or source_path.resolve().parent != root.resolve():
            return None, exists
        if source_path.stat().st_size > MAXIMUM_DEPENDENCY_FILE_BYTES:
            return None, True
        return source_path.read_text(encoding="utf-8"), True
    except OSError, RuntimeError, UnicodeError:
        return None, exists


def parse_bounded_toml(contents: str) -> dict[str, object] | None:
    """Parse one dependency lock and enforce the shared structure bounds."""
    data: object = tomllib.loads(contents)
    enforce_structure_limits(data)
    return as_str_mapping(data)


def dependency_source_is_secure(
    root: Path,
    profile: DependencyProfile,
    ruff_minimum: SemanticVersion,
) -> SourceValidation:
    """Validate the selected source while returning only sanitized status."""
    contents, exists = read_dependency_text(root, profile)
    if contents is None or not contents.strip():
        return SourceValidation(passed=False, exists=exists)
    passed = False
    if profile.source_id == "requirements-pinned":
        passed = requirements_are_secure(contents, require_hashes=False, ruff_minimum=ruff_minimum)
    elif profile.source_id == "requirements-hashed":
        passed = requirements_are_secure(contents, require_hashes=True, ruff_minimum=ruff_minimum)
    else:
        try:
            lock = parse_bounded_toml(contents)
        except RecursionError, StructureLimitError, tomllib.TOMLDecodeError:
            lock = None
        if lock is not None:
            if profile.source_id == "uv-lock":
                passed = uv_lock_is_secure(lock, ruff_minimum)
            else:
                passed = pylock_is_secure(lock, ruff_minimum)
    return SourceValidation(passed=passed, exists=True)


def parse_package_scripts(scripts: dict[str, object]) -> tuple[dict[str, ParsedScript], dict[str, JsonValue]]:
    """Parse string-valued scripts and report missing, malformed, or hollow requirements."""
    issues: dict[str, JsonValue] = {}
    parsed_scripts = {
        name: parse_script(value) for name, value in scripts.items() if isinstance(value, str) and value.strip()
    }
    for name in PACKAGE_SCRIPT_NAMES:
        value = scripts.get(name)
        if isinstance(value, str) and value.strip():
            parsed = parsed_scripts[name]
            if parsed.error is not None:
                issues[name] = {"issue": "unparseable", "detail": parsed.error}
            elif script_is_placeholder(parsed):
                issues[name] = {"issue": "placeholder-or-no-op"}
        else:
            issues[name] = {"issue": "missing-or-non-string", "actual_type": type(value).__name__}
    return parsed_scripts, issues


def apply_capability_contracts(parsed_scripts: dict[str, ParsedScript], issues: dict[str, JsonValue]) -> None:
    """Add issues for script graphs that do not reach their intended strict tools."""
    for name, required in CAPABILITY_CONTRACTS.items():
        if name not in parsed_scripts or name in issues:
            continue
        actual, graph_issue = reachable_capabilities(name, parsed_scripts)
        missing = sorted(required - actual)
        if graph_issue is not None:
            issues[name] = {"issue": graph_issue}
        elif missing:
            issues[name] = {"issue": "missing-capabilities", "missing": json_safe(missing)}


def apply_aggregate_contracts(parsed_scripts: dict[str, ParsedScript], issues: dict[str, JsonValue]) -> None:
    """Add issues when aggregate gates omit a required named gate script."""
    for aggregate, required_scripts in AGGREGATE_SCRIPT_CONTRACTS.items():
        if aggregate not in parsed_scripts or aggregate in issues:
            continue
        graph = reachable_scripts(aggregate, parsed_scripts)
        missing_scripts = sorted(required_scripts - graph.reached)
        if graph.issue is not None:
            issues[aggregate] = {"issue": graph.issue}
        elif missing_scripts:
            issues[aggregate] = {"issue": "missing-gate-scripts", "missing": json_safe(missing_scripts)}


def profile_report(profile: DependencyProfile | None) -> dict[str, JsonValue]:
    """Return only fixed profile identifiers suitable for diagnostics."""
    if profile is None:
        return {"profile_kind": "unaccepted", "source_id": "unaccepted"}
    return {"profile_kind": profile.kind, "source_id": profile.source_id}


def apply_bootstrap_contracts(
    root: Path,
    parsed_scripts: dict[str, ParsedScript],
    issues: dict[str, JsonValue],
    ruff_minimum: SemanticVersion,
) -> None:
    """Add issues when dependency setup is absent, unlocked, or internally inconsistent."""
    bootstrap = parsed_scripts.get("python:bootstrap")
    venv = parsed_scripts.get("python:venv")
    bootstrap_selected = bootstrap_profile(bootstrap or ParsedScript((), (), "missing"))
    venv_selected = venv_profile(venv or ParsedScript((), (), "missing"))
    if bootstrap_selected is None:
        issues["python:bootstrap"] = {"issue": "unaccepted-dependency-profile"}
    else:
        validation = dependency_source_is_secure(root, bootstrap_selected, ruff_minimum)
        if not validation.passed:
            issues["python:bootstrap"] = {
                "issue": "dependency-source-missing-or-invalid",
                "exists": validation.exists,
                **profile_report(bootstrap_selected),
            }
    if venv_selected is None or bootstrap_selected != venv_selected:
        issues["python:venv"] = {
            "issue": "profile-mismatch",
            "expected": profile_report(bootstrap_selected),
            "actual": profile_report(venv_selected),
            "same_selected_source": (
                bootstrap_selected is not None
                and venv_selected is not None
                and bootstrap_selected.target == venv_selected.target
            ),
        }


def validate_package_scripts(
    root: Path,
    scripts: dict[str, object],
    ruff_minimum: SemanticVersion,
) -> tuple[bool, JsonValue]:
    """Validate script types, graph composition, leaf tools, and bootstrap profiles."""
    if len(scripts) > MAXIMUM_PACKAGE_SCRIPTS:
        return False, {"issues": {"scripts": {"issue": "script-count-limit"}}}
    parsed_scripts, issues = parse_package_scripts(scripts)
    apply_capability_contracts(parsed_scripts, issues)
    apply_aggregate_contracts(parsed_scripts, issues)
    apply_bootstrap_contracts(root, parsed_scripts, issues, ruff_minimum)
    return not issues, {"issues": issues}


def audit_ruff_policy_surfaces(diagnostics: list[Diagnostic], ruff: object, ruff_lint: object) -> None:
    """Audit bounded Ruff exclusions and suppressions."""
    exclusions_ok, exclusions_actual = ruff_exclusions_status(ruff)
    add_check(
        diagnostics,
        "ruff.exclusions",
        CheckMessages(
            failure="Ruff exclusions contain a root-wide or unapproved path, or omit a required generated directory.",
            success="Ruff exclusions use only the documented generated-directory allowlist.",
        ),
        passed=exclusions_ok,
        context=DiagnosticContext(
            expected=json_safe(
                {
                    "required": sorted(RUFF_REQUIRED_EXCLUSIONS),
                    "allowed": sorted(RUFF_ALLOWED_EXCLUSIONS),
                    "base_exclude": "empty",
                }
            ),
            actual=exclusions_actual,
        ),
    )
    suppressions_ok, suppressions_actual = ruff_suppressions_status(ruff, ruff_lint)
    add_check(
        diagnostics,
        "ruff.suppressions",
        CheckMessages(
            failure="Ruff ignores, unfixable rules, or per-file ignores exceed the narrow documented allowlist.",
            success="Ruff suppressions stay within the narrow documented allowlist.",
        ),
        passed=suppressions_ok,
        context=DiagnosticContext(
            expected=json_safe(
                {
                    "ignore_allowed": sorted(RUFF_ALLOWED_IGNORES),
                    "unfixable_allowed": sorted(RUFF_ALLOWED_UNFIXABLE),
                    "per_file_allowed": {key: sorted(value) for key, value in RUFF_ALLOWED_PER_FILE_IGNORES.items()},
                    "extension_surfaces": "empty",
                }
            ),
            actual=suppressions_actual,
        ),
    )


def audit_mypy_policy_surfaces(diagnostics: list[Diagnostic], mypy: object) -> None:
    """Audit bounded mypy exclusions and suppression surfaces."""
    exclusions_ok, exclusions_actual = mypy_exclusions_status(mypy)
    add_check(
        diagnostics,
        "mypy.exclusions",
        CheckMessages(
            failure="mypy exclusions must use only anchored documented directory-segment branches.",
            success="mypy exclusions use the bounded documented directory-segment grammar.",
        ),
        passed=exclusions_ok,
        context=DiagnosticContext(
            expected=json_safe(
                {
                    "required": sorted(MYPY_REQUIRED_EXCLUSIONS),
                    "allowed": sorted(MYPY_ALLOWED_EXCLUSIONS),
                    "branch_shape": "(^|/)<escaped-directory>/",
                }
            ),
            actual=exclusions_actual,
        ),
    )
    suppressions_ok, suppressions_actual = mypy_suppressions_status(mypy)
    add_check(
        diagnostics,
        "mypy.suppressions",
        CheckMessages(
            failure="mypy contains an override, global ignore, disabled code, or strictness-negating setting.",
            success="mypy has no analysis-nullifying override or suppression setting.",
        ),
        passed=suppressions_ok,
        context=DiagnosticContext(
            expected={
                "overrides": "empty",
                "disable_error_code": "empty",
                "global_ignores": "absent",
                "strict_negations": "absent",
            },
            actual=suppressions_actual,
        ),
    )


def audit_pyright_policy_surfaces(diagnostics: list[Diagnostic], pyright: object) -> None:
    """Audit bounded Pyright exclusions and suppression surfaces."""
    exclusions_ok, exclusions_actual = pyright_exclusions_status(pyright)
    add_check(
        diagnostics,
        "pyright.exclusions",
        CheckMessages(
            failure=(
                "Pyright exclusions contain a root-wide or unapproved path, or omit a required generated directory."
            ),
            success="Pyright exclusions use only the documented generated-directory allowlist.",
        ),
        passed=exclusions_ok,
        context=DiagnosticContext(
            expected=json_safe(
                {
                    "required": sorted(PYRIGHT_REQUIRED_EXCLUSIONS),
                    "allowed": sorted(PYRIGHT_ALLOWED_EXCLUSIONS),
                }
            ),
            actual=exclusions_actual,
        ),
    )
    suppressions_ok, suppressions_actual = pyright_suppressions_status(pyright)
    add_check(
        diagnostics,
        "pyright.suppressions",
        CheckMessages(
            failure="Pyright contains ignores, execution overrides, or downgraded report diagnostics.",
            success="Pyright has no analysis-nullifying ignore or diagnostic downgrade.",
        ),
        passed=suppressions_ok,
        context=DiagnosticContext(
            expected={
                "ignore": "empty",
                "execution_environments": "empty",
                "severity_overrides": "empty",
                "report_values": [True, "error"],
            },
            actual=suppressions_actual,
        ),
    )


def audit_pytest_policy_surfaces(diagnostics: list[Diagnostic], pytest_options: object) -> None:
    """Audit additive pytest execution and discovery suppression surfaces."""
    suppressions_ok, suppressions_actual = pytest_suppressions_status(pytest_options)
    add_check(
        diagnostics,
        "pytest.suppressions",
        CheckMessages(
            failure="pytest contains a no-op, discovery bypass, config override, or collection ignore.",
            success="pytest has no additive execution or discovery bypass.",
        ),
        passed=suppressions_ok,
        context=DiagnosticContext(
            expected=json_safe(
                {
                    "addopts": "enforcing",
                    "collection_ignores": "absent",
                    "norecursedirs": sorted(PYTEST_ALLOWED_NORECURSEDIRS),
                    "discovery_overrides": "default-or-absent",
                }
            ),
            actual=suppressions_actual,
        ),
    )


def audit_pyproject(root: Path, diagnostics: list[Diagnostic]) -> SemanticVersion | None:
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
        return None

    pyproject = load_toml_object(pyproject_path, diagnostics, "pyproject.parse")
    if pyproject is None:
        return None

    ruff = get_nested(pyproject, "tool", "ruff")
    ruff_lint = get_nested(pyproject, "tool", "ruff", "lint")
    ruff_format = get_nested(pyproject, "tool", "ruff", "format")
    ruff_analyze = get_nested(pyproject, "tool", "ruff", "analyze")
    ruff_pydocstyle = get_nested(pyproject, "tool", "ruff", "lint", "pydocstyle")
    ruff_type_checking = get_nested(pyproject, "tool", "ruff", "lint", "flake8-type-checking")
    mypy = get_nested(pyproject, "tool", "mypy")
    pyright = get_nested(pyproject, "tool", "pyright")
    pytest_options = get_nested(pyproject, "tool", "pytest", "ini_options")

    add_settings_check(
        diagnostics,
        ruff,
        SettingsCheck(
            check="ruff.force-exclude",
            messages=CheckMessages(
                failure="Ruff should set force-exclude = true.",
                success="Ruff force-exclude is enabled.",
            ),
            expected=(expected_true("force-exclude"),),
        ),
    )
    add_settings_check(
        diagnostics,
        ruff,
        SettingsCheck(
            check="ruff.line-length",
            messages=CheckMessages(
                failure=f"Ruff should use line-length = {STRICT_LINE_LENGTH}.",
                success=f"Ruff line length is {STRICT_LINE_LENGTH}.",
            ),
            expected=(ExpectedSetting(("line-length",), STRICT_LINE_LENGTH),),
        ),
    )
    configured_ruff_minimum = minimum_requirement_version(raw_value(ruff, "required-version"))
    ruff_minimum_valid = configured_ruff_minimum is not None and configured_ruff_minimum >= MINIMUM_RUFF_VERSION
    add_check(
        diagnostics,
        "ruff.required-version",
        CheckMessages(
            failure="Ruff required-version must be a valid >=0.15.20 semantic minimum.",
            success="Ruff required-version meets the >=0.15.20 semantic minimum.",
        ),
        passed=ruff_minimum_valid,
        context=DiagnosticContext(
            expected={"required-version": ">=0.15.20"},
            actual={"required-version": json_safe(raw_value(ruff, "required-version"))},
        ),
    )
    add_settings_check(
        diagnostics,
        ruff_lint,
        SettingsCheck(
            check="ruff.lint.select",
            messages=CheckMessages(
                failure='Ruff lint should select ["ALL"].',
                success="Ruff lint selects ALL.",
            ),
            expected=(ExpectedSetting(("select",), frozenset({"ALL"}), "contains"),),
        ),
    )
    add_settings_check(
        diagnostics,
        ruff,
        SettingsCheck(
            check="ruff.core",
            messages=CheckMessages(
                failure="Ruff target, fix display, or gitignore settings differ from the documented profile.",
                success="Ruff core settings match the strict profile.",
            ),
            expected=RUFF_CORE_SETTINGS,
        ),
    )
    add_settings_check(
        diagnostics,
        ruff,
        SettingsCheck(
            check="ruff.paths",
            messages=CheckMessages(
                failure="Ruff source, cache, or exclusion settings differ from the documented profile.",
                success="Ruff source, cache, and exclusion settings match the strict profile.",
            ),
            expected=RUFF_PATH_SETTINGS,
        ),
    )
    audit_ruff_policy_surfaces(diagnostics, ruff, ruff_lint)
    add_settings_check(
        diagnostics,
        ruff_lint,
        SettingsCheck(
            check="ruff.lint",
            messages=CheckMessages(
                failure='Ruff lint should make ["ALL"] rules fixable.',
                success="Ruff lint makes ALL rules fixable.",
            ),
            expected=RUFF_LINT_SETTINGS,
        ),
    )
    add_settings_check(
        diagnostics,
        ruff_format,
        SettingsCheck(
            check="ruff.format",
            messages=CheckMessages(
                failure="Ruff format should enable docstring code formatting, LF endings, and double quotes.",
                success="Ruff format settings match the strict profile.",
            ),
            expected=RUFF_FORMAT_SETTINGS,
        ),
    )
    add_settings_check(
        diagnostics,
        ruff_analyze,
        SettingsCheck(
            check="ruff.analyze",
            messages=CheckMessages(
                failure="Ruff analyze settings do not match the documented strict profile.",
                success="Ruff analyze settings match the strict profile.",
            ),
            expected=RUFF_ANALYZE_SETTINGS,
        ),
    )
    add_settings_check(
        diagnostics,
        ruff_pydocstyle,
        SettingsCheck(
            check="ruff.pydocstyle",
            messages=CheckMessages(
                failure="Ruff pydocstyle should use the documented Google convention.",
                success="Ruff pydocstyle uses the documented Google convention.",
            ),
            expected=RUFF_PYDOCSTYLE_SETTINGS,
        ),
    )
    add_settings_check(
        diagnostics,
        ruff_type_checking,
        SettingsCheck(
            check="ruff.flake8-type-checking.strict",
            messages=CheckMessages(
                failure="Ruff flake8-type-checking strict mode should be enabled.",
                success="Ruff flake8-type-checking strict mode is enabled.",
            ),
            expected=RUFF_TYPE_CHECKING_SETTINGS,
        ),
    )

    add_settings_check(
        diagnostics,
        mypy,
        SettingsCheck(
            check="mypy.strict",
            messages=CheckMessages(
                failure="mypy strict = true is missing.",
                success="mypy strict mode is enabled.",
            ),
            expected=(expected_true("strict"),),
        ),
    )
    add_check(
        diagnostics,
        "mypy.error-codes",
        CheckMessages(
            failure="mypy should enable the strict profile's extra error codes.",
            success="mypy extra error codes match the strict profile.",
        ),
        passed=(
            (enabled_codes := string_items(raw_value(mypy, "enable_error_code"))) is not None
            and MYPY_EXTRA_ERROR_CODES.issubset(enabled_codes)
        ),
        context=DiagnosticContext(
            expected=json_safe({"enable_error_code": sorted(MYPY_EXTRA_ERROR_CODES)}),
            actual={"enable_error_code": json_safe(raw_value(mypy, "enable_error_code"))},
        ),
    )
    add_settings_check(
        diagnostics,
        mypy,
        SettingsCheck(
            check="mypy.warnings",
            messages=CheckMessages(
                failure="mypy warning settings do not match the documented strict profile.",
                success="mypy warning settings match the strict profile.",
            ),
            expected=tuple(setting for setting in MYPY_ESSENTIAL_SETTINGS if setting.path[0].startswith("warn_")),
        ),
    )
    add_settings_check(
        diagnostics,
        mypy,
        SettingsCheck(
            check="mypy.essentials",
            messages=CheckMessages(
                failure="mypy strict supplemental settings do not match the documented profile.",
                success="mypy strict supplemental settings match the profile.",
            ),
            expected=MYPY_ESSENTIAL_SETTINGS,
        ),
    )
    add_settings_check(
        diagnostics,
        mypy,
        SettingsCheck(
            check="mypy.paths",
            messages=CheckMessages(
                failure="mypy Python version, files, import path, cache, or exclusions differ from the profile.",
                success="mypy path and cache settings match the strict profile.",
            ),
            expected=MYPY_PATH_SETTINGS,
        ),
    )
    audit_mypy_policy_surfaces(diagnostics, mypy)
    add_settings_check(
        diagnostics,
        mypy,
        SettingsCheck(
            check="mypy.reports",
            messages=CheckMessages(
                failure="mypy report outputs differ from the documented coverage/mypy profile.",
                success="mypy report outputs match the strict profile.",
            ),
            expected=MYPY_REPORT_SETTINGS,
        ),
    )

    add_settings_check(
        diagnostics,
        pyright,
        SettingsCheck(
            check="pyright.strict",
            messages=CheckMessages(
                failure='Pyright typeCheckingMode should be "strict".',
                success="Pyright strict mode is enabled.",
            ),
            expected=(ExpectedSetting(("typeCheckingMode",), "strict"),),
        ),
    )
    add_settings_check(
        diagnostics,
        pyright,
        SettingsCheck(
            check="pyright.unknown-types",
            messages=CheckMessages(
                failure="Pyright unknown-type and missing-stub diagnostics should be errors.",
                success="Pyright unknown-type and missing-stub diagnostics are errors.",
            ),
            expected=tuple(
                setting
                for setting in PYRIGHT_ESSENTIAL_SETTINGS
                if setting.path[0].startswith("reportUnknown") or setting.path[0] == "reportMissingTypeStubs"
            ),
        ),
    )
    add_settings_check(
        diagnostics,
        pyright,
        SettingsCheck(
            check="pyright.inference",
            messages=CheckMessages(
                failure="Pyright reachability and strict collection inference settings differ from the profile.",
                success="Pyright inference settings match the strict profile.",
            ),
            expected=tuple(
                setting
                for setting in PYRIGHT_ESSENTIAL_SETTINGS
                if setting.path[0]
                in {
                    "analyzeUnannotatedFunctions",
                    "enableReachabilityAnalysis",
                    "strictDictionaryInference",
                    "strictListInference",
                    "strictSetInference",
                }
            ),
        ),
    )
    add_settings_check(
        diagnostics,
        pyright,
        SettingsCheck(
            check="pyright.essentials",
            messages=CheckMessages(
                failure="Pyright settings do not match the documented strict profile.",
                success="Pyright settings match the strict profile.",
            ),
            expected=PYRIGHT_ESSENTIAL_SETTINGS,
        ),
    )
    add_settings_check(
        diagnostics,
        pyright,
        SettingsCheck(
            check="pyright.paths",
            messages=CheckMessages(
                failure="Pyright include, extra path, exclusions, or Python version differ from the profile.",
                success="Pyright path and Python-version settings match the strict profile.",
            ),
            expected=PYRIGHT_PATH_SETTINGS,
        ),
    )
    audit_pyright_policy_surfaces(diagnostics, pyright)

    add_settings_check(
        diagnostics,
        pytest_options,
        SettingsCheck(
            check="pytest.strict",
            messages=CheckMessages(
                failure="pytest settings do not match the documented strict profile.",
                success="pytest settings match the strict profile.",
            ),
            expected=PYTEST_STRICT_SETTINGS,
        ),
    )
    add_settings_check(
        diagnostics,
        pytest_options,
        SettingsCheck(
            check="pytest.profile",
            messages=CheckMessages(
                failure="pytest discovery, cache, or JUnit settings differ from the documented profile.",
                success="pytest discovery, cache, and JUnit settings match the strict profile.",
            ),
            expected=PYTEST_PROFILE_SETTINGS,
        ),
    )
    audit_pytest_policy_surfaces(diagnostics, pytest_options)
    return configured_ruff_minimum if ruff_minimum_valid else None


def audit_package_json(
    root: Path,
    diagnostics: list[Diagnostic],
    ruff_minimum: SemanticVersion,
) -> None:
    """Audit npm task-runner scripts when package.json exists."""
    package_path = root / "package.json"
    if not package_path.exists():
        diagnostics.append(
            Diagnostic(
                check="package-json.exists",
                message="package.json is absent; npm Python scripts are not required.",
                severity="warn",
            )
        )
        return

    package_json = load_json_object(
        package_path,
        diagnostics,
        "package-json.parse",
        allow_jsonc=False,
    )
    if package_json is None:
        return

    scripts = as_str_mapping(raw_value(package_json, "scripts"))
    passed = False
    actual: JsonValue = {
        "issues": {
            "scripts": {
                "issue": "missing-or-non-object",
                "actual_type": type(raw_value(package_json, "scripts")).__name__,
            }
        }
    }
    if scripts is not None:
        passed, actual = validate_package_scripts(root, scripts, ruff_minimum)
    add_check(
        diagnostics,
        "package-json.python-scripts",
        CheckMessages(
            failure="package.json Python scripts are missing, hollow, unsafe, or do not compose the strict gate.",
            success="package.json Python scripts invoke and compose the documented strict tool gates.",
        ),
        passed=passed,
        context=DiagnosticContext(
            expected=json_safe(
                {
                    "required_scripts": list(PACKAGE_SCRIPT_NAMES),
                    "check_gate_scripts": sorted(REQUIRED_CHECK_SCRIPTS),
                    "bootstrap_profiles": [
                        "pip-requirements",
                        "pip-requirements-hashed",
                        "pip-pylock",
                        "uv-frozen",
                    ],
                }
            ),
            actual=actual,
        ),
    )


def audit_vscode(root: Path, diagnostics: list[Diagnostic]) -> None:
    """Audit VS Code settings when present."""
    settings_path = root / ".vscode" / "settings.json"
    if not settings_path.exists():
        diagnostics.append(
            Diagnostic(
                check="vscode.exists",
                message=".vscode/settings.json is absent; editor integration was not audited.",
                severity="warn",
            )
        )
        return

    settings = load_json_object(
        settings_path,
        diagnostics,
        "vscode.parse",
        allow_jsonc=True,
    )
    if settings is None:
        return

    add_settings_check(
        diagnostics,
        raw_value(settings, "[python]"),
        SettingsCheck(
            check="vscode.python-format",
            messages=CheckMessages(
                failure="VS Code Python formatter should be Ruff with format-on-save enabled.",
                success="VS Code Python formatter uses Ruff.",
            ),
            expected=(
                ExpectedSetting(("editor.defaultFormatter",), "charliermarsh.ruff"),
                expected_true("editor.formatOnSave"),
            ),
        ),
    )
    add_settings_check(
        diagnostics,
        raw_value(settings, "[python]"),
        SettingsCheck(
            check="vscode.python",
            messages=CheckMessages(
                failure="VS Code Python editor settings do not match the documented profile.",
                success="VS Code Python editor settings match the strict profile.",
            ),
            expected=VSCODE_PYTHON_SETTINGS,
        ),
    )
    add_settings_check(
        diagnostics,
        settings,
        SettingsCheck(
            check="vscode.pyright",
            messages=CheckMessages(
                failure="VS Code Python analysis should use strict workspace diagnostics.",
                success="VS Code Python analysis uses strict workspace diagnostics.",
            ),
            expected=(
                ExpectedSetting(("python.analysis.typeCheckingMode",), "strict"),
                ExpectedSetting(("python.analysis.diagnosticMode",), "workspace"),
            ),
        ),
    )
    add_settings_check(
        diagnostics,
        settings,
        SettingsCheck(
            check="vscode.workspace",
            messages=CheckMessages(
                failure="VS Code Python workspace settings do not match the documented profile.",
                success="VS Code Python workspace settings match the strict profile.",
            ),
            expected=VSCODE_WORKSPACE_SETTINGS,
        ),
    )
    add_settings_check(
        diagnostics,
        settings,
        SettingsCheck(
            check="vscode.interpreter",
            messages=CheckMessages(
                failure="VS Code should use the workspace-local Windows Python interpreter.",
                success="VS Code uses the workspace-local Windows Python interpreter.",
            ),
            expected=VSCODE_INTERPRETER_SETTINGS,
        ),
    )
    add_settings_check(
        diagnostics,
        settings,
        SettingsCheck(
            check="vscode.ruff",
            messages=CheckMessages(
                failure="VS Code Ruff settings do not match the documented profile.",
                success="VS Code Ruff settings match the strict profile.",
            ),
            expected=VSCODE_RUFF_SETTINGS,
        ),
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


def write_line(text: str) -> None:
    """Write one line to stdout."""
    _ = sys.stdout.write(f"{text}\n")


def diagnostic_records(diagnostics: list[Diagnostic]) -> list[dict[str, JsonValue]]:
    """Build the stable JSON schema without recursive dataclass conversion."""
    return [
        {
            "check": diagnostic.check,
            "message": diagnostic.message,
            "severity": diagnostic.severity,
            "expected": json_safe(diagnostic.expected),
            "actual": json_safe(diagnostic.actual),
        }
        for diagnostic in diagnostics
    ]


def main() -> int:
    """Run the audit."""
    args = parse_args()
    root = Path(args.path).resolve()
    diagnostics: list[Diagnostic] = []

    configured_ruff_minimum = audit_pyproject(root, diagnostics)
    audit_package_json(root, diagnostics, configured_ruff_minimum or MINIMUM_RUFF_VERSION)
    audit_vscode(root, diagnostics)

    if args.json:
        write_line(json.dumps(diagnostic_records(diagnostics), allow_nan=False, indent=2))
    else:
        print_text(diagnostics)

    return 1 if any(diagnostic.severity == "fail" for diagnostic in diagnostics) else 0


if __name__ == "__main__":
    sys.exit(main())
