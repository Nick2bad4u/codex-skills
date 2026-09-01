# Copyright (c) 2026 Nick2bad4u
"""Safety and complete-profile tests for the strict Python auditor."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import cast

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
AUDIT_SCRIPT = REPO_ROOT / "skills" / "python-strict-development" / "scripts" / "audit_python_strict.py"
CHECK_PYTHON_UNSAFE_PREFIX = "npm run lint:python:unsafe && npm run typecheck:python"

STRICT_PYPROJECT = r"""
[tool.ruff]
force-exclude = true
line-length = 120
required-version = ">=0.15.20"
show-fixes = true
target-version = "py314"
src = ["."]
cache-dir = ".cache/.ruff_cache"
respect-gitignore = true
extend-exclude = [
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
]

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
    "ANN401",
    "COM812",
    "D203",
    "D213",
    "EM101",
    "EM102",
    "INP001",
    "ISC001",
    "TRY003",
]
fixable = ["ALL"]
unfixable = ["ERA", "F401"]

[tool.ruff.lint.pydocstyle]
convention = "google"

[tool.ruff.lint.flake8-type-checking]
strict = true

[tool.ruff.lint.per-file-ignores]
"tests/**/*.py" = ["S101"]

[tool.mypy]
python_version = "3.14"
files = ["."]
mypy_path = "."
cache_dir = ".cache/.mypy_cache"
exclude = '''(?x)(
    (^|/)\.bzr/
    | (^|/)\.cache/
    | (^|/)\.git/
    | (^|/)\.hg/
    | (^|/)\.mypy_cache/
    | (^|/)\.nox/
    | (^|/)\.pytest_cache/
    | (^|/)\.ruff_cache/
    | (^|/)\.svn/
    | (^|/)\.tox/
    | (^|/)\.venv/
    | (^|/)__pycache__/
    | (^|/)__pypackages__/
    | (^|/)build/
    | (^|/)coverage/
    | (^|/)dist/
    | (^|/)env/
    | (^|/)htmlcov/
    | (^|/)node_modules/
    | (^|/)site-packages/
    | (^|/)third_party/
    | (^|/)tmp/
    | (^|/)vendor/
    | (^|/)venv/
)'''
strict = true
disallow_any_decorated = true
disallow_any_unimported = true
strict_bytes = true
strict_equality = true
strict_equality_for_none = true
warn_incomplete_stub = true
warn_redundant_casts = true
warn_return_any = true
warn_unused_configs = true
warn_unused_ignores = true
warn_unreachable = true
junit_xml = "coverage/mypy/junit.xml"
cobertura_xml_report = "coverage/mypy/cobertura.xml"
xml_report = "coverage/mypy/mypy.xml"
linecoverage_report = "coverage/mypy/linecoverage.xml"
any_exprs_report = "coverage/mypy/any_exprs.txt"
linecount_report = "coverage/mypy/linecount.txt"
lineprecision_report = "coverage/mypy/lineprecision.txt"
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

[tool.pyright]
include = ["."]
extraPaths = ["."]
exclude = [
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
]
pythonVersion = "3.14"
pythonPlatform = "All"
typeCheckingMode = "strict"
analyzeUnannotatedFunctions = true
strictDictionaryInference = true
strictListInference = true
strictSetInference = true
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
reportUnusedCallResult = true
reportImplicitOverride = true
reportUnnecessaryTypeIgnoreComment = true

[tool.pytest.ini_options]
addopts = ["--strict-config", "--strict-markers", "--import-mode=importlib"]
filterwarnings = ["error"]
pythonpath = ["."]
testpaths = ["."]
norecursedirs = [
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
]
cache_dir = ".cache/.pytest_cache"
junit_duration_report = "call"
junit_family = "xunit2"
junit_logging = "log"
junit_log_passing_tests = true
junit_suite_name = "codex-skills"
strict = true
strict_config = true
strict_markers = true
strict_parametrization_ids = true
strict_xfail = true
"""

STRICT_PACKAGE_SCRIPTS = {
    "check:python": "npm run lint:python && npm run typecheck:python && npm run test:python && npm run compile:python",
    "check:python:unsafe": f"{CHECK_PYTHON_UNSAFE_PREFIX} && npm run test:python && npm run compile:python",
    "compile:python": 'python -m compileall -q -x "[\\/]\\." scripts tests',
    "format:python": "npm run ruff:format && npm run ruff:fix",
    "lint:python": "npm run ruff:check && npm run ruff:format:check",
    "lint:python:unsafe": "npm run ruff:check:unsafe && npm run ruff:fix:unsafe",
    "pyright": "pyright",
    "python:bootstrap": "python -m pip install -r requirements-dev.txt",
    "python:venv": "python -m venv .venv && .venv\\Scripts\\activate && python -m pip install -r requirements-dev.txt",
    "ruff:check": "ruff check scripts tests",
    "ruff:check:unsafe": "ruff check --unsafe-fixes scripts tests",
    "ruff:fix": "ruff check --fix scripts tests",
    "ruff:fix:unsafe": "ruff check --fix --unsafe-fixes scripts tests",
    "ruff:format": "ruff format scripts tests",
    "ruff:format:check": "ruff format --check scripts tests",
    "test:python": "pytest",
    "typecheck:python": "mypy && npm run pyright",
}

PINNED_REQUIREMENTS = """\
mypy==2.1.0
pyright==1.1.411
pytest==9.1.1
ruff==0.15.20
"""
TEST_SHA256 = "a" * 64
STRICT_TOOL_VERSIONS = {
    "mypy": "2.1.0",
    "pyright": "1.1.411",
    "pytest": "9.1.1",
    "ruff": "0.15.20",
}


def pinned_requirements(*, ruff_version: str = "0.15.20") -> str:
    """Return exact direct pins for every invoked strict tool."""
    versions = {**STRICT_TOOL_VERSIONS, "ruff": ruff_version}
    return "".join(f"{name}=={version}\n" for name, version in versions.items())


def hashed_requirements(*, ruff_version: str = "0.15.20") -> str:
    """Return an all-entry sha256 requirements lock for every strict tool."""
    versions = {**STRICT_TOOL_VERSIONS, "ruff": ruff_version}
    return "".join(f"{name}=={version} \\\n    --hash=sha256:{TEST_SHA256}\n" for name, version in versions.items())


def pylock_contents(*, ruff_version: str = "0.15.20") -> str:
    """Return a minimal structurally valid PEP 751-style lock fixture."""
    versions = {**STRICT_TOOL_VERSIONS, "ruff": ruff_version}
    packages = "".join(
        f"""\
[[packages]]
name = "{name}"
version = "{version}"

[[packages.wheels]]
name = "{name}-{version}-py3-none-any.whl"
hashes = {{ sha256 = "{TEST_SHA256}" }}
"""
        for name, version in versions.items()
    )
    return f'lock-version = "1.0"\n{packages}'


def uv_lock_contents(*, ruff_version: str = "0.15.20") -> str:
    """Return a minimal structurally valid frozen uv lock fixture."""
    versions = {**STRICT_TOOL_VERSIONS, "ruff": ruff_version}
    packages = "".join(
        f"""\
[[package]]
name = "{name}"
version = "{version}"
source = {{ registry = "https://pypi.org/simple" }}
sdist = {{ url = "https://files.pythonhosted.org/{name}.tar.gz", hash = "sha256:{TEST_SHA256}" }}
"""
        for name, version in versions.items()
    )
    return f"version = 1\n{packages}"


STRICT_VSCODE_JSONC = r"""
{
    // A line comment before a nested object.
    "[python]": {
        "editor.codeActionsOnSave": {
            "source.fixAll.ruff": "explicit",
            "source.organizeImports.ruff": "explicit",
        },
        "editor.defaultFormatter": "charliermarsh.ruff",
        "editor.formatOnSave": true,
    },
    /* A block comment between ordinary settings. */
    "mypy-type-checker.reportingScope": "workspace",
    "python.analysis.diagnosticMode": "workspace",
    "python.analysis.extraPaths": ["${workspaceFolder}",],
    "python.analysis.typeCheckingMode": "strict",
    "python.defaultInterpreterPath": "${workspaceFolder}\\.venv\\Scripts\\python.exe",
    "python.testing.pytestEnabled": true,
    "python.testing.unittestEnabled": false,
    "ruff.configurationPreference": "filesystemFirst",
    "ruff.fixAll": true,
    "ruff.format.backend": "internal",
    "ruff.importStrategy": "fromEnvironment",
    "ruff.lint.enable": true,
    "ruff.nativeServer": "auto",
    "ruff.organizeImports": true,
    "test.commentMarkers": "https://example.test/path//literal/*marker*/,}",
}
"""


def as_dict(value: object) -> dict[str, object]:
    """Assert that a decoded JSON value is a string-keyed object."""
    if not isinstance(value, dict):
        raise TypeError("Expected a JSON object.")

    result: dict[str, object] = {}
    for key, item in cast("dict[object, object]", value).items():
        if not isinstance(key, str):
            raise TypeError("Expected a string JSON object key.")
        result[key] = item
    return result


def as_list(value: object) -> list[object]:
    """Assert that a decoded JSON value is a list."""
    if not isinstance(value, list):
        raise TypeError("Expected a JSON list.")
    return cast("list[object]", value)


def write_complete_profile(root: Path, *, pyproject: str = STRICT_PYPROJECT) -> None:
    """Write an independent fixture containing every audited strict-profile value."""
    settings_dir = root / ".vscode"
    settings_dir.mkdir()
    _ = (root / "pyproject.toml").write_text(pyproject, encoding="utf-8")
    _ = (root / "package.json").write_text(
        json.dumps({"scripts": STRICT_PACKAGE_SCRIPTS}),
        encoding="utf-8",
    )
    _ = (root / "requirements-dev.txt").write_text(pinned_requirements(), encoding="utf-8")
    _ = (settings_dir / "settings.json").write_text(STRICT_VSCODE_JSONC, encoding="utf-8")


def run_audit(root: Path) -> subprocess.CompletedProcess[str]:
    """Run the local audit in JSON mode."""
    return subprocess.run(  # noqa: S603  # Fixed interpreter and repository-local script; no shell.
        [sys.executable, str(AUDIT_SCRIPT), str(root), "--json"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        stdin=subprocess.DEVNULL,
        text=True,
    )


def run_audit_text(root: Path) -> subprocess.CompletedProcess[str]:
    """Run the local audit in human-readable mode."""
    return subprocess.run(  # noqa: S603  # Fixed interpreter and repository-local script; no shell.
        [sys.executable, str(AUDIT_SCRIPT), str(root)],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        stdin=subprocess.DEVNULL,
        text=True,
    )


def write_package_scripts(root: Path, scripts: dict[str, object]) -> None:
    """Replace the fixture package scripts with a caller-controlled object."""
    _ = (root / "package.json").write_text(json.dumps({"scripts": scripts}), encoding="utf-8")


def chain_commands(*commands: str) -> str:
    """Compose test commands with the one modeled safe shell operator."""
    return " && ".join(commands)


def replace_mypy_exclusion(pyproject: str, replacement: str) -> str:
    """Replace the fixture's complete multiline mypy exclusion value."""
    start = pyproject.index("exclude = '''")
    end = pyproject.index("'''", start + len("exclude = '''")) + len("'''")
    return f"{pyproject[:start]}exclude = {replacement}{pyproject[end:]}"


def package_issues(result: subprocess.CompletedProcess[str]) -> dict[str, object]:
    """Return the sanitized issue map from the package-script diagnostic."""
    package_diagnostic = next(
        item for item in diagnostics_from(result) if item["check"] == "package-json.python-scripts"
    )
    return as_dict(as_dict(package_diagnostic["actual"])["issues"])


def diagnostics_from(result: subprocess.CompletedProcess[str]) -> list[dict[str, object]]:
    """Decode structured diagnostics and prove stdout remained valid JSON."""
    return [as_dict(item) for item in as_list(json.loads(result.stdout))]


def failed_checks(result: subprocess.CompletedProcess[str]) -> set[str]:
    """Return all failing check identifiers from one audit result."""
    return {str(diagnostic["check"]) for diagnostic in diagnostics_from(result) if diagnostic["severity"] == "fail"}


def test_complete_profile_accepts_jsonc_comments_trailing_commas_and_string_markers(tmp_path: Path) -> None:
    """Accept the complete profile without treating comment markers inside strings as syntax."""
    write_complete_profile(tmp_path)

    result = run_audit(tmp_path)

    assert result.returncode == 0, result.stderr
    assert failed_checks(result) == set()
    assert {str(item["check"]) for item in diagnostics_from(result)} >= {
        "mypy.paths",
        "mypy.reports",
        "mypy.essentials",
        "mypy.exclusions",
        "mypy.suppressions",
        "pyright.exclusions",
        "pyright.paths",
        "pyright.essentials",
        "pyright.suppressions",
        "pytest.profile",
        "pytest.suppressions",
        "pytest.strict",
        "ruff.exclusions",
        "ruff.paths",
        "ruff.required-version",
        "ruff.suppressions",
        "vscode.interpreter",
        "vscode.python",
        "vscode.ruff",
        "vscode.workspace",
    }


@pytest.mark.parametrize(
    ("original", "replacement", "expected_check"),
    [
        pytest.param("force-exclude = true", "force-exclude = false", "ruff.force-exclude"),
        pytest.param("line-length = 120", "line-length = 88", "ruff.line-length"),
        pytest.param("show-fixes = true\n", "", "ruff.core", id="delete-ruff-show-fixes"),
        pytest.param('target-version = "py314"', 'target-version = "py313"', "ruff.core"),
        pytest.param("respect-gitignore = true", "respect-gitignore = false", "ruff.core"),
        pytest.param('src = ["."]', 'src = ["src"]', "ruff.paths"),
        pytest.param('cache-dir = ".cache/.ruff_cache"', 'cache-dir = ".ruff_cache"', "ruff.paths"),
        pytest.param('    "vendor",\n', "", "ruff.paths", id="delete-ruff-exclusion"),
        pytest.param('select = ["ALL"]', 'select = ["E", "F"]', "ruff.lint.select"),
        pytest.param('fixable = ["ALL"]', "fixable = []", "ruff.lint"),
        pytest.param("docstring-code-format = true", "docstring-code-format = false", "ruff.format"),
        pytest.param('line-ending = "lf"', 'line-ending = "native"', "ruff.format"),
        pytest.param('quote-style = "double"', 'quote-style = "single"', "ruff.format"),
        pytest.param("detect-string-imports = true", "detect-string-imports = false", "ruff.analyze"),
        pytest.param('direction = "dependencies"', 'direction = "imports"', "ruff.analyze", id="weaken-ruff-analyze"),
        pytest.param("type-checking-imports = true", "type-checking-imports = false", "ruff.analyze"),
        pytest.param('convention = "google"\n', "", "ruff.pydocstyle", id="delete-ruff-pydocstyle"),
        pytest.param(
            "[tool.ruff.lint.flake8-type-checking]\nstrict = true",
            "[tool.ruff.lint.flake8-type-checking]\nstrict = false",
            "ruff.flake8-type-checking.strict",
        ),
        pytest.param('python_version = "3.14"', 'python_version = "3.13"', "mypy.paths"),
        pytest.param('files = ["."]', 'files = ["scripts"]', "mypy.paths"),
        pytest.param('mypy_path = "."', 'mypy_path = "src"', "mypy.paths"),
        pytest.param('cache_dir = ".cache/.mypy_cache"', 'cache_dir = ".mypy_cache"', "mypy.paths"),
        pytest.param("    | (^|/)vendor/\n", "", "mypy.paths", id="delete-mypy-vendor-exclusion"),
        pytest.param(
            "\nstrict = true\ndisallow_any_decorated", "\nstrict = false\ndisallow_any_decorated", "mypy.strict"
        ),
        pytest.param("disallow_any_decorated = true", "disallow_any_decorated = false", "mypy.essentials"),
        pytest.param("disallow_any_unimported = true", "disallow_any_unimported = false", "mypy.essentials"),
        pytest.param("strict_bytes = true", "strict_bytes = false", "mypy.essentials"),
        pytest.param("strict_equality = true", "strict_equality = false", "mypy.essentials"),
        pytest.param("strict_equality_for_none = true", "strict_equality_for_none = false", "mypy.essentials"),
        pytest.param("warn_incomplete_stub = true", "warn_incomplete_stub = false", "mypy.essentials"),
        pytest.param("warn_redundant_casts = true", "warn_redundant_casts = false", "mypy.warnings"),
        pytest.param("warn_return_any = true", "warn_return_any = false", "mypy.warnings"),
        pytest.param("warn_unused_configs = true", "warn_unused_configs = false", "mypy.warnings"),
        pytest.param("warn_unused_ignores = true", "warn_unused_ignores = false", "mypy.warnings"),
        pytest.param("warn_unreachable = true", "warn_unreachable = false", "mypy.warnings"),
        pytest.param('junit_xml = "coverage/mypy/junit.xml"', 'junit_xml = "junit.xml"', "mypy.reports"),
        pytest.param(
            'cobertura_xml_report = "coverage/mypy/cobertura.xml"',
            'cobertura_xml_report = "cobertura.xml"',
            "mypy.reports",
        ),
        pytest.param('xml_report = "coverage/mypy/mypy.xml"', 'xml_report = "mypy.xml"', "mypy.reports"),
        pytest.param(
            'linecoverage_report = "coverage/mypy/linecoverage.xml"',
            'linecoverage_report = "linecoverage.xml"',
            "mypy.reports",
        ),
        pytest.param(
            'any_exprs_report = "coverage/mypy/any_exprs.txt"',
            'any_exprs_report = "any_exprs.txt"',
            "mypy.reports",
        ),
        pytest.param(
            'linecount_report = "coverage/mypy/linecount.txt"',
            'linecount_report = "linecount.txt"',
            "mypy.reports",
        ),
        pytest.param(
            'lineprecision_report = "coverage/mypy/lineprecision.txt"',
            'lineprecision_report = "lineprecision.txt"',
            "mypy.reports",
        ),
        pytest.param('include = ["."]', 'include = ["src"]', "pyright.paths"),
        pytest.param('extraPaths = ["."]', "extraPaths = []", "pyright.paths"),
        pytest.param('    "**/vendor",\n', "", "pyright.paths", id="delete-pyright-exclusion"),
        pytest.param('pythonVersion = "3.14"', 'pythonVersion = "3.13"', "pyright.paths"),
        pytest.param('pythonPlatform = "All"', 'pythonPlatform = "Windows"', "pyright.essentials"),
        pytest.param('typeCheckingMode = "strict"', 'typeCheckingMode = "basic"', "pyright.strict"),
        pytest.param("analyzeUnannotatedFunctions = true", "analyzeUnannotatedFunctions = false", "pyright.inference"),
        pytest.param("strictDictionaryInference = true", "strictDictionaryInference = false", "pyright.inference"),
        pytest.param("strictListInference = true", "strictListInference = false", "pyright.inference"),
        pytest.param("strictSetInference = true\n", "", "pyright.essentials", id="delete-strict-set-inference"),
        pytest.param("enableReachabilityAnalysis = true", "enableReachabilityAnalysis = false", "pyright.inference"),
        pytest.param("deprecateTypingAliases = true", "deprecateTypingAliases = false", "pyright.essentials"),
        pytest.param("disableBytesTypePromotions = true", "disableBytesTypePromotions = false", "pyright.essentials"),
        pytest.param("useLibraryCodeForTypes = true", "useLibraryCodeForTypes = false", "pyright.essentials"),
        pytest.param(
            'reportMissingTypeStubs = "error"',
            'reportMissingTypeStubs = "warning"',
            "pyright.essentials",
        ),
        pytest.param('reportUnknownLambdaType = "error"\n', "", "pyright.essentials"),
        pytest.param(
            'reportUnknownParameterType = "error"',
            'reportUnknownParameterType = "warning"',
            "pyright.essentials",
        ),
        pytest.param("reportUnusedCallResult = true", "reportUnusedCallResult = false", "pyright.essentials"),
        pytest.param("reportImplicitOverride = true", "reportImplicitOverride = false", "pyright.essentials"),
        pytest.param(
            "reportUnnecessaryTypeIgnoreComment = true",
            "reportUnnecessaryTypeIgnoreComment = false",
            "pyright.essentials",
        ),
        pytest.param("--strict-config", "--no-header", "pytest.strict"),
        pytest.param("--strict-markers", "--verbose", "pytest.strict"),
        pytest.param("--import-mode=importlib", "--import-mode=prepend", "pytest.strict"),
        pytest.param('filterwarnings = ["error"]', 'filterwarnings = ["default"]', "pytest.strict"),
        pytest.param('pythonpath = ["."]', 'pythonpath = ["src"]', "pytest.profile"),
        pytest.param('testpaths = ["."]', 'testpaths = ["tests"]', "pytest.profile"),
        pytest.param('cache_dir = ".cache/.pytest_cache"', 'cache_dir = ".pytest_cache"', "pytest.profile"),
        pytest.param('junit_duration_report = "call"', 'junit_duration_report = "total"', "pytest.profile"),
        pytest.param('junit_family = "xunit2"', 'junit_family = "legacy"', "pytest.profile"),
        pytest.param('junit_logging = "log"', 'junit_logging = "no"', "pytest.profile"),
        pytest.param("junit_log_passing_tests = true", "junit_log_passing_tests = false", "pytest.profile"),
        pytest.param('junit_suite_name = "codex-skills"', 'junit_suite_name = "pytest"', "pytest.profile"),
        pytest.param("\nstrict = true\nstrict_config", "\nstrict = false\nstrict_config", "pytest.strict"),
        pytest.param("strict_config = true", "strict_config = false", "pytest.strict"),
        pytest.param("strict_markers = true", "strict_markers = false", "pytest.strict"),
        pytest.param("strict_parametrization_ids = true\n", "", "pytest.strict"),
        pytest.param("strict_xfail = true", "strict_xfail = false", "pytest.strict"),
    ],
)
def test_documented_profile_deletions_and_weakenings_fail(
    tmp_path: Path,
    original: str,
    replacement: str,
    expected_check: str,
) -> None:
    """Reject deletion or weakening of every representative strict-profile group."""
    mutated = STRICT_PYPROJECT.replace(original, replacement, 1)
    assert mutated != STRICT_PYPROJECT
    write_complete_profile(tmp_path, pyproject=mutated)

    result = run_audit(tmp_path)

    assert result.returncode == 1
    assert expected_check in failed_checks(result)
    assert "Traceback" not in result.stderr


@pytest.mark.parametrize(
    "requirement",
    [
        pytest.param(None, id="missing"),
        pytest.param("0.15.20", id="missing-comparator"),
        pytest.param(">=0.15.19", id="weaker"),
        pytest.param(">=0.15", id="missing-component"),
        pytest.param(">=00.15.20", id="leading-zero"),
        pytest.param(">=not-a-version", id="malformed"),
    ],
)
def test_ruff_required_version_rejects_missing_malformed_or_weaker_values(
    tmp_path: Path,
    requirement: str | None,
) -> None:
    """Require a valid semantic lower bound at or above the documented Ruff version."""
    replacement = "" if requirement is None else f'required-version = "{requirement}"\n'
    pyproject = STRICT_PYPROJECT.replace('required-version = ">=0.15.20"\n', replacement, 1)
    write_complete_profile(tmp_path, pyproject=pyproject)

    result = run_audit(tmp_path)

    assert result.returncode == 1
    assert failed_checks(result) == {"ruff.required-version"}


@pytest.mark.parametrize("requirement", [">=0.15.20", ">=0.16.0", ">=1.0.0"])
def test_ruff_required_version_accepts_equal_or_stronger_semantic_minimums(
    tmp_path: Path,
    requirement: str,
) -> None:
    """Accept stable semantic lower bounds equal to or stronger than the minimum."""
    pyproject = STRICT_PYPROJECT.replace(">=0.15.20", requirement, 1)
    write_complete_profile(tmp_path, pyproject=pyproject)
    ruff_version = requirement.removeprefix(">=")
    _ = (tmp_path / "requirements-dev.txt").write_text(
        pinned_requirements(ruff_version=ruff_version),
        encoding="utf-8",
    )

    result = run_audit(tmp_path)

    assert result.returncode == 0, result.stdout


@pytest.mark.parametrize(
    ("relative_path", "contents", "expected_check"),
    [
        pytest.param("pyproject.toml", "[tool.ruff\n", "pyproject.parse", id="malformed-toml"),
        pytest.param("package.json", "{", "package-json.parse", id="malformed-json"),
        pytest.param(
            ".vscode/settings.json",
            "{/* unterminated",
            "vscode.parse",
            id="malformed-jsonc",
        ),
        pytest.param("package.json", "[]", "package-json.parse", id="json-array-root"),
        pytest.param(".vscode/settings.json", "[]", "vscode.parse", id="jsonc-array-root"),
    ],
)
def test_malformed_configs_and_wrong_top_level_shapes_are_structured_failures(
    tmp_path: Path,
    relative_path: str,
    contents: str,
    expected_check: str,
) -> None:
    """Return valid JSON diagnostics instead of tracebacks for invalid configuration files."""
    write_complete_profile(tmp_path)
    _ = (tmp_path / relative_path).write_text(contents, encoding="utf-8")

    result = run_audit(tmp_path)

    assert result.returncode == 1
    assert expected_check in failed_checks(result)
    assert "Traceback" not in result.stderr
    assert "Traceback" not in result.stdout


def test_package_json_remains_strict_json_while_vscode_settings_accept_jsonc(tmp_path: Path) -> None:
    """Reject JSONC syntax in package.json even when the same syntax is valid for VS Code."""
    write_complete_profile(tmp_path)
    _ = (tmp_path / "package.json").write_text(
        """{
  // package.json does not permit comments.
  "scripts": {},
}
""",
        encoding="utf-8",
    )

    result = run_audit(tmp_path)

    assert result.returncode == 1
    assert failed_checks(result) == {"package-json.parse"}
    diagnostics = diagnostics_from(result)
    assert any(item["check"] == "vscode.python" and item["severity"] == "pass" for item in diagnostics)
    assert all(item["check"] != "vscode.parse" for item in diagnostics)


@pytest.mark.parametrize(
    "error_code",
    [
        "deprecated",
        "explicit-override",
        "ignore-without-code",
        "mutable-override",
        "possibly-undefined",
        "redundant-expr",
        "truthy-bool",
        "truthy-iterable",
        "unused-awaitable",
    ],
)
def test_every_documented_mypy_error_code_is_required(tmp_path: Path, error_code: str) -> None:
    """Reject removal of each documented high-signal mypy error code."""
    pyproject = STRICT_PYPROJECT.replace(f'    "{error_code}",\n', "", 1)
    assert pyproject != STRICT_PYPROJECT
    write_complete_profile(tmp_path, pyproject=pyproject)

    result = run_audit(tmp_path)

    assert result.returncode == 1
    assert "mypy.error-codes" in failed_checks(result)


@pytest.mark.parametrize(
    "diagnostic",
    [
        "reportMissingTypeStubs",
        "reportUnknownArgumentType",
        "reportUnknownLambdaType",
        "reportUnknownMemberType",
        "reportUnknownParameterType",
        "reportUnknownVariableType",
    ],
)
def test_every_documented_pyright_unknown_type_diagnostic_is_required(
    tmp_path: Path,
    diagnostic: str,
) -> None:
    """Reject weakening each documented Pyright unknown-type diagnostic."""
    pyproject = STRICT_PYPROJECT.replace(f'{diagnostic} = "error"', f'{diagnostic} = "warning"', 1)
    assert pyproject != STRICT_PYPROJECT
    write_complete_profile(tmp_path, pyproject=pyproject)

    result = run_audit(tmp_path)

    assert result.returncode == 1
    assert "pyright.unknown-types" in failed_checks(result)


@pytest.mark.parametrize(
    ("original", "replacement", "expected_check"),
    [
        ('"source.fixAll.ruff": "explicit"', '"source.fixAll.ruff": "never"', "vscode.python"),
        (
            '"source.organizeImports.ruff": "explicit"',
            '"source.organizeImports.ruff": "never"',
            "vscode.python",
        ),
        (
            '"editor.defaultFormatter": "charliermarsh.ruff"',
            '"editor.defaultFormatter": "other"',
            "vscode.python-format",
        ),
        ('"editor.formatOnSave": true', '"editor.formatOnSave": false', "vscode.python-format"),
        (
            '"mypy-type-checker.reportingScope": "workspace"',
            '"mypy-type-checker.reportingScope": "file"',
            "vscode.workspace",
        ),
        (
            '"python.analysis.diagnosticMode": "workspace"',
            '"python.analysis.diagnosticMode": "openFilesOnly"',
            "vscode.pyright",
        ),
        (
            '"python.analysis.extraPaths": ["${workspaceFolder}",]',
            '"python.analysis.extraPaths": []',
            "vscode.workspace",
        ),
        (
            '"python.analysis.typeCheckingMode": "strict"',
            '"python.analysis.typeCheckingMode": "basic"',
            "vscode.pyright",
        ),
        (
            '"python.defaultInterpreterPath": "${workspaceFolder}\\\\.venv\\\\Scripts\\\\python.exe"',
            '"python.defaultInterpreterPath": "C:\\\\Python314\\\\python.exe"',
            "vscode.interpreter",
        ),
        ('"python.testing.pytestEnabled": true', '"python.testing.pytestEnabled": false', "vscode.workspace"),
        ('"python.testing.unittestEnabled": false', '"python.testing.unittestEnabled": true', "vscode.workspace"),
        (
            '"ruff.configurationPreference": "filesystemFirst"',
            '"ruff.configurationPreference": "editorFirst"',
            "vscode.ruff",
        ),
        ('"ruff.fixAll": true', '"ruff.fixAll": false', "vscode.ruff"),
        ('"ruff.format.backend": "internal"', '"ruff.format.backend": "external"', "vscode.ruff"),
        ('"ruff.importStrategy": "fromEnvironment"', '"ruff.importStrategy": "useBundled"', "vscode.ruff"),
        ('"ruff.lint.enable": true', '"ruff.lint.enable": false', "vscode.ruff"),
        ('"ruff.nativeServer": "auto"', '"ruff.nativeServer": "off"', "vscode.ruff"),
        ('"ruff.organizeImports": true', '"ruff.organizeImports": false', "vscode.ruff"),
    ],
)
def test_every_documented_vscode_surface_is_required(
    tmp_path: Path,
    original: str,
    replacement: str,
    expected_check: str,
) -> None:
    """Reject deletion or weakening of every documented VS Code profile surface."""
    write_complete_profile(tmp_path)
    mutated = STRICT_VSCODE_JSONC.replace(original, replacement, 1)
    assert mutated != STRICT_VSCODE_JSONC
    _ = (tmp_path / ".vscode" / "settings.json").write_text(mutated, encoding="utf-8")

    result = run_audit(tmp_path)

    assert result.returncode == 1
    assert expected_check in failed_checks(result)


@pytest.mark.parametrize(
    ("script_name", "replacement"),
    [
        ("ruff:check", "fixture"),
        ("ruff:check:unsafe", "ruff check scripts tests"),
        ("ruff:fix", "ruff check scripts tests"),
        ("ruff:fix:unsafe", "ruff check --fix scripts tests"),
        ("ruff:format", "ruff format"),
        ("ruff:format:check", "ruff format scripts tests"),
        ("pyright", "exit 0"),
        ("lint:python", "npm run ruff:check"),
        ("lint:python:unsafe", "npm run ruff:check:unsafe"),
        ("format:python", "npm run ruff:format"),
        ("typecheck:python", "mypy"),
        ("test:python", "echo pytest"),
        ("compile:python", "python -m compileall -q scripts tests"),
        (
            "check:python",
            "npm run lint:python && npm run typecheck:python && npm run compile:python",
        ),
        (
            "check:python:unsafe",
            "npm run lint:python:unsafe && npm run test:python && npm run compile:python",
        ),
        ("python:bootstrap", "python -m pip install -r requirements-dev.in"),
        (
            "python:venv",
            "python -m venv .venv && python -m pip install -r pylock.toml",
        ),
    ],
)
def test_npm_script_leaf_tools_flags_and_gate_composition_are_required(
    tmp_path: Path,
    script_name: str,
    replacement: str,
) -> None:
    """Reject hollow leaves, missing strict flags, and incomplete aggregate gates."""
    write_complete_profile(tmp_path)
    scripts: dict[str, object] = dict(STRICT_PACKAGE_SCRIPTS)
    scripts[script_name] = replacement
    write_package_scripts(tmp_path, scripts)

    result = run_audit(tmp_path)

    assert result.returncode == 1
    assert failed_checks(result) == {"package-json.python-scripts"}
    package_diagnostic = next(
        item for item in diagnostics_from(result) if item["check"] == "package-json.python-scripts"
    )
    issues = as_dict(as_dict(package_diagnostic["actual"])["issues"])
    assert script_name in issues


@pytest.mark.parametrize("invalid_value", [None, 0, False, [], {}])
def test_npm_script_values_must_be_nonempty_strings(tmp_path: Path, invalid_value: object) -> None:
    """Reject JSON-valid but non-command npm script values with structured diagnostics."""
    write_complete_profile(tmp_path)
    scripts: dict[str, object] = dict(STRICT_PACKAGE_SCRIPTS)
    scripts["ruff:check"] = invalid_value
    write_package_scripts(tmp_path, scripts)

    result = run_audit(tmp_path)

    assert result.returncode == 1
    assert failed_checks(result) == {"package-json.python-scripts"}


@pytest.mark.parametrize(
    ("bootstrap", "venv", "source"),
    [
        (
            "python -m pip install -r requirements-dev.txt",
            "python -m venv .venv && .venv\\Scripts\\python.exe -m pip install -r requirements-dev.txt",
            "requirements-dev.txt",
        ),
        (
            "python -m pip install --require-hashes -r requirements-dev.in",
            chain_commands(
                "python -m venv .venv",
                ".venv\\Scripts\\activate",
                "python -m pip install --require-hashes -r requirements-dev.in",
            ),
            "requirements-dev.in",
        ),
        (
            "python -m pip install -r pylock.windows.toml",
            "python -m venv .venv && .venv\\Scripts\\python.exe -m pip install -r pylock.windows.toml",
            "pylock.windows.toml",
        ),
        ("uv sync --frozen", "uv sync --frozen", "uv.lock"),
    ],
)
def test_documented_dependency_bootstrap_profiles_are_accepted(
    tmp_path: Path,
    bootstrap: str,
    venv: str,
    source: str,
) -> None:
    """Accept only the small documented set of synchronized dependency profiles."""
    write_complete_profile(tmp_path)
    scripts: dict[str, object] = dict(STRICT_PACKAGE_SCRIPTS)
    scripts["python:bootstrap"] = bootstrap
    scripts["python:venv"] = venv
    write_package_scripts(tmp_path, scripts)
    if source == "requirements-dev.in":
        source_contents = hashed_requirements()
    elif source == "requirements-dev.txt":
        source_contents = pinned_requirements()
    elif source == "uv.lock":
        source_contents = uv_lock_contents()
    else:
        source_contents = pylock_contents()
    _ = (tmp_path / source).write_text(source_contents, encoding="utf-8")

    result = run_audit(tmp_path)

    assert result.returncode == 0, result.stdout


def test_npm_script_cycles_and_hostile_command_text_are_not_executed(tmp_path: Path) -> None:
    """Reject a cyclic hostile-looking graph without invoking any configured command."""
    write_complete_profile(tmp_path)
    marker = tmp_path / "must-not-exist.txt"
    scripts: dict[str, object] = dict(STRICT_PACKAGE_SCRIPTS)
    scripts["lint:python"] = "npm run check:python"
    scripts["python:bootstrap"] = f"python -c \"from pathlib import Path; Path(r'{marker}').touch()\""
    write_package_scripts(tmp_path, scripts)

    result = run_audit(tmp_path)

    assert result.returncode == 1
    assert not marker.exists()
    assert str(marker) not in result.stdout
    assert "Traceback" not in result.stderr


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
@pytest.mark.parametrize("relative_path", ["package.json", ".vscode/settings.json"])
def test_non_finite_json_constants_are_structured_parse_failures(
    tmp_path: Path,
    constant: str,
    relative_path: str,
) -> None:
    """Reject Python JSON decoder extensions in strict JSON and normalized JSONC."""
    write_complete_profile(tmp_path)
    _ = (tmp_path / relative_path).write_text(f'{{"notFinite": {constant}}}', encoding="utf-8")

    result = run_audit(tmp_path)

    expected_check = "package-json.parse" if relative_path == "package.json" else "vscode.parse"
    assert result.returncode == 1
    assert failed_checks(result) == {expected_check}
    assert "Traceback" not in result.stdout
    assert "Traceback" not in result.stderr


def test_legacy_check_ids_json_shape_exit_semantics_and_text_prefixes_are_stable(tmp_path: Path) -> None:
    """Keep HEAD-era machine and text contracts while extending diagnostic detail."""
    write_complete_profile(tmp_path)

    json_result = run_audit(tmp_path)
    text_result = run_audit_text(tmp_path)

    assert json_result.returncode == 0
    assert text_result.returncode == 0
    diagnostics = diagnostics_from(json_result)
    legacy_ids = {
        "mypy.error-codes",
        "mypy.strict",
        "mypy.warnings",
        "package-json.python-scripts",
        "pyproject.exists",
        "pyright.inference",
        "pyright.strict",
        "pyright.unknown-types",
        "pytest.strict",
        "ruff.analyze",
        "ruff.flake8-type-checking.strict",
        "ruff.force-exclude",
        "ruff.format",
        "ruff.line-length",
        "ruff.lint.select",
        "ruff.required-version",
        "vscode.pyright",
        "vscode.python-format",
        "vscode.ruff",
    }
    assert {str(item["check"]) for item in diagnostics} >= legacy_ids
    for diagnostic in diagnostics:
        assert set(diagnostic) == {"actual", "check", "expected", "message", "severity"}
        assert isinstance(diagnostic["check"], str)
        assert isinstance(diagnostic["message"], str)
        assert diagnostic["severity"] in {"fail", "pass", "warn"}
    assert all(line.startswith("PASS ") for line in text_result.stdout.splitlines())
    assert "PASS ruff.force-exclude: Ruff force-exclude is enabled." in text_result.stdout


def test_failure_diagnostics_name_mismatched_fields_without_echoing_script_secrets(tmp_path: Path) -> None:
    """Expose actionable expected/actual data while redacting or omitting command secrets."""
    write_complete_profile(tmp_path)
    scripts: dict[str, object] = dict(STRICT_PACKAGE_SCRIPTS)
    scripts["ruff:check"] = "fixture --token do-not-print-this"
    write_package_scripts(tmp_path, scripts)

    result = run_audit(tmp_path)

    package_diagnostic = next(
        item for item in diagnostics_from(result) if item["check"] == "package-json.python-scripts"
    )
    assert package_diagnostic["severity"] == "fail"
    issues = as_dict(as_dict(package_diagnostic["actual"])["issues"])
    assert "ruff:check" in issues
    assert "do-not-print-this" not in result.stdout


@pytest.mark.parametrize(
    ("original", "replacement", "expected_check"),
    [
        pytest.param(
            '    "venv",\n]\n\n[tool.ruff.format]',
            '    "venv",\n    "**/*",\n]\n\n[tool.ruff.format]',
            "ruff.exclusions",
            id="ruff-root-wide-extend-exclude",
        ),
        pytest.param(
            "[tool.ruff.format]",
            'exclude = ["."]\n\n[tool.ruff.format]',
            "ruff.exclusions",
            id="ruff-base-exclude",
        ),
        pytest.param(
            '    "TRY003",\n]',
            '    "TRY003",\n    "ALL",\n]',
            "ruff.suppressions",
            id="ruff-ignore-all",
        ),
        pytest.param(
            'unfixable = ["ERA", "F401"]',
            'unfixable = ["ERA", "F401", "ALL"]',
            "ruff.suppressions",
            id="ruff-unfixable-all",
        ),
        pytest.param(
            '"tests/**/*.py" = ["S101"]',
            '"tests/**/*.py" = ["S101"]\n"**/*.py" = ["ALL"]',
            "ruff.suppressions",
            id="ruff-catch-all-per-file",
        ),
        pytest.param(
            "[tool.ruff.format]",
            'extend-ignore = ["ALL"]\n\n[tool.ruff.format]',
            "ruff.suppressions",
            id="ruff-hidden-extend-ignore",
        ),
        pytest.param(
            "strict = true\ndisallow_any_decorated",
            "strict = true\nignore_errors = true\ndisallow_any_decorated",
            "mypy.suppressions",
            id="mypy-global-ignore-errors",
        ),
        pytest.param(
            "strict = true\ndisallow_any_decorated",
            'strict = true\ndisable_error_code = ["assignment"]\ndisallow_any_decorated',
            "mypy.suppressions",
            id="mypy-disable-code",
        ),
        pytest.param(
            "strict = true\ndisallow_any_decorated",
            "strict = true\ndisallow_untyped_defs = false\ndisallow_any_decorated",
            "mypy.suppressions",
            id="mypy-negate-strict",
        ),
        pytest.param(
            "strict = true\ndisallow_any_decorated",
            "strict = true\nallow_untyped_globals = true\ndisallow_any_decorated",
            "mypy.suppressions",
            id="mypy-dynamic-allow",
        ),
        pytest.param(
            "strict = true\ndisallow_any_decorated",
            "strict = true\nexclude_gitignore = true\ndisallow_any_decorated",
            "mypy.suppressions",
            id="mypy-gitignore-exclusions",
        ),
        pytest.param(
            '    "**/venv",\n]\npythonVersion',
            '    "**/venv",\n    "**/*",\n]\npythonVersion',
            "pyright.exclusions",
            id="pyright-root-wide-exclude",
        ),
        pytest.param(
            'pythonVersion = "3.14"',
            'ignore = ["**/*"]\npythonVersion = "3.14"',
            "pyright.suppressions",
            id="pyright-ignore-all",
        ),
        pytest.param(
            'pythonVersion = "3.14"',
            'executionEnvironments = [{ root = ".", typeCheckingMode = "off" }]\npythonVersion = "3.14"',
            "pyright.suppressions",
            id="pyright-execution-environment",
        ),
        pytest.param(
            "reportUnnecessaryTypeIgnoreComment = true",
            "reportUnnecessaryTypeIgnoreComment = true\nreportOptionalCall = false",
            "pyright.suppressions",
            id="pyright-added-report-downgrade",
        ),
    ],
)
def test_analysis_nullifying_config_additions_fail(
    tmp_path: Path,
    original: str,
    replacement: str,
    expected_check: str,
) -> None:
    """Reject additive suppressions and root-wide exclusions, not only deleted settings."""
    pyproject = STRICT_PYPROJECT.replace(original, replacement, 1)
    assert pyproject != STRICT_PYPROJECT
    write_complete_profile(tmp_path, pyproject=pyproject)

    result = run_audit(tmp_path)

    assert result.returncode == 1
    assert expected_check in failed_checks(result)
    assert "Traceback" not in result.stdout
    assert "Traceback" not in result.stderr


@pytest.mark.parametrize(
    "replacement",
    [
        '".*"',
        '"^.*$"',
        '"(?s:.*)"',
        '"(?x)((^|/).*/)"',
        '"(?x)((^|/)vendor/|.*)"',
    ],
)
def test_mypy_catch_all_exclusion_regexes_fail(tmp_path: Path, replacement: str) -> None:
    """Reject regex variants that can exclude the complete repository."""
    write_complete_profile(tmp_path, pyproject=replace_mypy_exclusion(STRICT_PYPROJECT, replacement))

    result = run_audit(tmp_path)

    assert result.returncode == 1
    assert "mypy.exclusions" in failed_checks(result)


def test_mypy_catch_all_override_fails(tmp_path: Path) -> None:
    """Reject a module-star override even when the root strict flag remains true."""
    pyproject = f"""{STRICT_PYPROJECT}
[[tool.mypy.overrides]]
module = "*"
ignore_errors = true
"""
    write_complete_profile(tmp_path, pyproject=pyproject)

    result = run_audit(tmp_path)

    assert result.returncode == 1
    assert "mypy.suppressions" in failed_checks(result)


def test_omitting_optional_narrow_ruff_suppressions_remains_stricter_and_passes(tmp_path: Path) -> None:
    """Allow removal of documented exceptions because fewer suppressions are stricter."""
    pyproject = STRICT_PYPROJECT.replace(
        """ignore = [
    "ANN401",
    "COM812",
    "D203",
    "D213",
    "EM101",
    "EM102",
    "INP001",
    "ISC001",
    "TRY003",
]
""",
        "",
        1,
    ).replace('unfixable = ["ERA", "F401"]\n', "", 1)
    pyproject = pyproject.replace('\n[tool.ruff.lint.per-file-ignores]\n"tests/**/*.py" = ["S101"]\n', "", 1)
    write_complete_profile(tmp_path, pyproject=pyproject)

    result = run_audit(tmp_path)

    assert result.returncode == 0, result.stdout


@pytest.mark.parametrize(
    "operator",
    ["||", "|", "&", ";"],
)
def test_required_npm_chains_reject_every_non_conjunction_operator(tmp_path: Path, operator: str) -> None:
    """Reject fallback, pipeline, background, and sequence operators in strict gates."""
    write_complete_profile(tmp_path)
    scripts: dict[str, object] = dict(STRICT_PACKAGE_SCRIPTS)
    scripts["lint:python"] = f"npm run ruff:check {operator} npm run ruff:format:check"
    write_package_scripts(tmp_path, scripts)

    result = run_audit(tmp_path)

    assert result.returncode == 1
    assert "lint:python" in package_issues(result)
    assert "Traceback" not in result.stderr


@pytest.mark.parametrize(
    ("script_name", "command"),
    [
        ("ruff:check", "ruff check --help skills tests"),
        ("ruff:format:check", "ruff format --version --check skills tests"),
        ("pyright", "pyright --version"),
        ("typecheck:python", "mypy --help && npm run pyright"),
        ("test:python", "pytest --collect-only"),
        ("test:python", "pytest --fixtures"),
        ("test:python", "node tools/run-pytest.mjs --collect-only"),
        ("test:python", "node tools/run-pytest.mjs -p no:warnings"),
        ("compile:python", "python -m compileall --help -q -x pattern skills tests"),
    ],
)
def test_required_tool_commands_reject_no_op_and_discovery_only_flags(
    tmp_path: Path,
    script_name: str,
    command: str,
) -> None:
    """Reject commands that name the right executable without enforcing analysis."""
    write_complete_profile(tmp_path)
    scripts: dict[str, object] = dict(STRICT_PACKAGE_SCRIPTS)
    scripts[script_name] = command
    write_package_scripts(tmp_path, scripts)

    result = run_audit(tmp_path)

    assert result.returncode == 1
    assert script_name in package_issues(result)


@pytest.mark.parametrize(
    "command",
    [
        "node tools/not-run-pytest.mjs",
        "node tools/run-pytest.mjs.evil",
        "node other/run-pytest.mjs",
        "echo tools/run-pytest.mjs",
        "node tools/run-pytest.mjs && exit 0",
        "node tools/run-pytest.mjs||exit 0",
    ],
)
def test_pytest_helper_requires_an_exact_modeled_command_without_appends(tmp_path: Path, command: str) -> None:
    """Reject helper substring spoofs and commands appended to the real helper."""
    write_complete_profile(tmp_path)
    scripts: dict[str, object] = dict(STRICT_PACKAGE_SCRIPTS)
    scripts["test:python"] = command
    write_package_scripts(tmp_path, scripts)

    result = run_audit(tmp_path)

    assert result.returncode == 1
    assert "test:python" in package_issues(result)


@pytest.mark.parametrize(
    ("script_name", "command"),
    [
        ("ruff:check", "ruff check skills tests && exit 0"),
        ("ruff:fix", "ruff check --fix skills tests && echo fixture"),
        ("pyright", "pyright && true"),
        ("typecheck:python", "mypy && npm run pyright && echo done"),
        ("compile:python", 'python -m compileall -q -x "[\\/]\\." skills tests && exit 0'),
    ],
)
def test_modeled_tool_commands_reject_unmodeled_appended_commands(
    tmp_path: Path,
    script_name: str,
    command: str,
) -> None:
    """Reject a valid strict command followed by any unmodeled command."""
    write_complete_profile(tmp_path)
    scripts: dict[str, object] = dict(STRICT_PACKAGE_SCRIPTS)
    scripts[script_name] = command
    write_package_scripts(tmp_path, scripts)

    result = run_audit(tmp_path)

    assert result.returncode == 1
    assert script_name in package_issues(result)


def test_operator_tokenization_accepts_safe_conjunctions_without_surrounding_spaces(tmp_path: Path) -> None:
    """Recognize an exact conjunction even when shell whitespace is omitted."""
    write_complete_profile(tmp_path)
    scripts: dict[str, object] = dict(STRICT_PACKAGE_SCRIPTS)
    scripts["lint:python"] = "npm run ruff:check&&npm run ruff:format:check"
    write_package_scripts(tmp_path, scripts)

    result = run_audit(tmp_path)

    assert result.returncode == 0, result.stdout


@pytest.mark.parametrize(
    "command",
    [
        "ruff check " + "x" * 8_300,
        "ruff check " + " ".join(f"target-{index}" for index in range(260)),
        " && ".join("ruff check skills tests" for _index in range(34)),
    ],
)
def test_script_command_token_and_chain_limits_are_structured_failures(tmp_path: Path, command: str) -> None:
    """Bound command length, token count, and conjunction count before graph analysis."""
    write_complete_profile(tmp_path)
    scripts: dict[str, object] = dict(STRICT_PACKAGE_SCRIPTS)
    scripts["ruff:check"] = command
    write_package_scripts(tmp_path, scripts)

    result = run_audit(tmp_path)

    assert result.returncode == 1
    assert "ruff:check" in package_issues(result)
    assert "Traceback" not in result.stdout
    assert "Traceback" not in result.stderr


def test_package_script_collection_limit_is_a_structured_failure(tmp_path: Path) -> None:
    """Bound package-script collection size before parsing every command graph."""
    write_complete_profile(tmp_path)
    scripts: dict[str, object] = dict(STRICT_PACKAGE_SCRIPTS)
    scripts.update({f"filler-{index}": "pytest" for index in range(2_050)})
    write_package_scripts(tmp_path, scripts)

    result = run_audit(tmp_path)

    assert result.returncode == 1
    assert "scripts" in package_issues(result)
    assert "Traceback" not in result.stderr


def test_alias_chain_beyond_python_recursion_limit_fails_without_recursion(tmp_path: Path) -> None:
    """Traverse an adversarially deep alias graph iteratively and stop at the graph bound."""
    write_complete_profile(tmp_path)
    scripts: dict[str, object] = dict(STRICT_PACKAGE_SCRIPTS)
    chain_length = 1_100
    scripts["test:python"] = "npm run alias-0"
    scripts.update({f"alias-{index}": f"npm run alias-{index + 1}" for index in range(chain_length - 1)})
    scripts[f"alias-{chain_length - 1}"] = "pytest"
    write_package_scripts(tmp_path, scripts)

    result = run_audit(tmp_path)

    assert result.returncode == 1
    assert "test:python" in package_issues(result)
    assert "RecursionError" not in result.stdout
    assert "Traceback" not in result.stderr


@pytest.mark.parametrize("relative_path", ["package.json", ".vscode/settings.json"])
def test_deep_json_and_jsonc_config_is_a_bounded_structured_failure(tmp_path: Path, relative_path: str) -> None:
    """Reject a parsed structure deeper than the audit limit without recursive serialization."""
    write_complete_profile(tmp_path)
    nested_value = "[" * 80 + "0" + "]" * 80
    if relative_path == "package.json":
        package_prefix = json.dumps({"scripts": STRICT_PACKAGE_SCRIPTS})[:-1]
        contents = f'{package_prefix},"deep":{nested_value}}}'
        expected_check = "package-json.parse"
    else:
        contents = f'{{"deep":{nested_value}}}'
        expected_check = "vscode.parse"
    _ = (tmp_path / relative_path).write_text(contents, encoding="utf-8")

    result = run_audit(tmp_path)

    assert result.returncode == 1
    assert failed_checks(result) == {expected_check}
    assert "Traceback" not in result.stdout
    assert "Traceback" not in result.stderr


@pytest.mark.parametrize(
    "bootstrap",
    [
        "python -m pip install -r requirements-dev.txt requests",
        "python -m pip install -r requirements-dev.txt -r another.txt",
        "python -m pip install --index-url https://example.invalid/simple -r requirements-dev.txt",
        "python -m pip install --trusted-host example.invalid -r requirements-dev.txt",
        "python -m pip install https://example.invalid/tool.whl",
        "pip install -r requirements-dev.txt",
        "python -m pip install --require-hashes -r requirements-dev.txt",
        "python -m pip install --require-hashes -r requirements-dev.in --no-deps",
        "python -m pip install --requirement requirements-dev.txt",
        "py -m pip install -r requirements-dev.txt",
    ],
)
def test_bootstrap_rejects_every_unmodeled_pip_token(tmp_path: Path, bootstrap: str) -> None:
    """Allow one exact requirement target and no package, URL, index, or extra option."""
    write_complete_profile(tmp_path)
    scripts: dict[str, object] = dict(STRICT_PACKAGE_SCRIPTS)
    scripts["python:bootstrap"] = bootstrap
    write_package_scripts(tmp_path, scripts)

    result = run_audit(tmp_path)

    assert result.returncode == 1
    assert "python:bootstrap" in package_issues(result)


@pytest.mark.parametrize(
    "contents",
    [
        "",
        "mypy==2.1.0\npyright==1.1.411\npytest==9.1.1\n",
        "mypy==2.1.0\npyright==1.1.411\npytest==9.1.1\nruff>=0.15.20\n",
        "mypy\npyright==1.1.411\npytest==9.1.1\nruff==0.15.20\n",
        "mypy==not-a-version\npyright==1.1.411\npytest==9.1.1\nruff==0.15.20\n",
        "-r nested-requirements.txt\n" + PINNED_REQUIREMENTS,
        "--index-url https://example.invalid/simple\n" + PINNED_REQUIREMENTS,
        "--trusted-host example.invalid\n" + PINNED_REQUIREMENTS,
        "ruff @ https://example.invalid/ruff.whl\nmypy==2.1.0\npyright==1.1.411\npytest==9.1.1\n",
        "mypy==2.1.0\npyright==1.1.411\npytest==9.1.1\nruff==0.15.19\n",
    ],
)
def test_plain_requirements_profile_rejects_unlocked_or_incomplete_sources(tmp_path: Path, contents: str) -> None:
    """Require exact direct pins and every invoked strict tool in plain requirements."""
    write_complete_profile(tmp_path)
    _ = (tmp_path / "requirements-dev.txt").write_text(contents, encoding="utf-8")

    result = run_audit(tmp_path)

    assert result.returncode == 1
    assert "python:bootstrap" in package_issues(result)


def test_plain_requirements_accepts_extras_markers_comments_and_pin_whitespace(tmp_path: Path) -> None:
    """Parse a conservative PEP 508-like exact-pin profile without a packaging dependency."""
    write_complete_profile(tmp_path)
    contents = """\
# Strict tools for Python 3.14.
mypy[reports] == 2.1.0 ; python_version >= "3.14"
pyright==1.1.411
pytest==9.1.1  # inline rationale
ruff == 0.15.20
"""
    _ = (tmp_path / "requirements-dev.txt").write_text(contents, encoding="utf-8")

    result = run_audit(tmp_path)

    assert result.returncode == 0, result.stdout


@pytest.mark.parametrize(
    "contents",
    [
        hashed_requirements().replace(f"mypy==2.1.0 \\\n    --hash=sha256:{TEST_SHA256}\n", "mypy==2.1.0\n", 1),
        hashed_requirements().replace(TEST_SHA256, "z" * 64, 1),
        hashed_requirements().replace("ruff==0.15.20", "ruff>=0.15.20", 1),
        hashed_requirements().replace("pyright==1.1.411", "-r nested.txt", 1),
        "--index-url https://example.invalid/simple\n" + hashed_requirements(),
        "--trusted-host example.invalid\n" + hashed_requirements(),
        hashed_requirements().replace("pytest==9.1.1", "pytest @ https://example.invalid/pytest.whl", 1),
    ],
)
def test_hash_profile_requires_exact_pins_and_valid_sha256_for_every_entry(tmp_path: Path, contents: str) -> None:
    """Reject missing hashes, invalid hashes, directives, URLs, and nested requirements."""
    write_complete_profile(tmp_path)
    scripts: dict[str, object] = dict(STRICT_PACKAGE_SCRIPTS)
    scripts["python:bootstrap"] = "python -m pip install --require-hashes -r requirements-dev.in"
    scripts["python:venv"] = chain_commands(
        "python -m venv .venv",
        ".venv\\Scripts\\python.exe -m pip install --require-hashes -r requirements-dev.in",
    )
    write_package_scripts(tmp_path, scripts)
    _ = (tmp_path / "requirements-dev.in").write_text(contents, encoding="utf-8")

    result = run_audit(tmp_path)

    assert result.returncode == 1
    assert "python:bootstrap" in package_issues(result)


@pytest.mark.parametrize(
    ("source", "contents"),
    [
        ("pylock.windows.toml", "locked = true\n"),
        ("pylock.windows.toml", 'lock-version = "1.0"\npackages = []\n'),
        ("pylock.windows.toml", pylock_contents().replace('lock-version = "1.0"', 'lock-version = "bogus"', 1)),
        ("pylock.windows.toml", pylock_contents().replace('version = "2.1.0"', 'version = "bogus"', 1)),
        ("pylock.windows.toml", pylock_contents().replace(TEST_SHA256, "not-a-digest", 1)),
        ("pylock.windows.toml", pylock_contents().replace("[[packages.wheels]]", "[[packages.invalid]]", 1)),
        ("uv.lock", "version = 1\npackage = []\n"),
        ("uv.lock", uv_lock_contents().replace(TEST_SHA256, "not-a-digest", 1)),
        ("uv.lock", uv_lock_contents().replace("sdist =", "artifact =", 1)),
    ],
)
def test_nonempty_bogus_or_corrupt_lockfiles_fail_structural_integrity(
    tmp_path: Path,
    source: str,
    contents: str,
) -> None:
    """Require package, version, artifact, and sha256 structure in pylock and uv locks."""
    write_complete_profile(tmp_path)
    scripts: dict[str, object] = dict(STRICT_PACKAGE_SCRIPTS)
    if source == "uv.lock":
        scripts["python:bootstrap"] = "uv sync --frozen"
        scripts["python:venv"] = "uv sync --frozen"
    else:
        scripts["python:bootstrap"] = f"python -m pip install -r {source}"
        scripts["python:venv"] = f"python -m venv .venv && .venv/bin/python -m pip install -r {source}"
    write_package_scripts(tmp_path, scripts)
    _ = (tmp_path / source).write_text(contents, encoding="utf-8")

    result = run_audit(tmp_path)

    assert result.returncode == 1
    assert "python:bootstrap" in package_issues(result)


@pytest.mark.parametrize(
    "venv",
    [
        "python -m venv .venv && python -m pip install -r requirements-dev.txt",
        "python -m venv .venv && echo .venv\\Scripts\\activate && python -m pip install -r requirements-dev.txt",
        "python -m venv env && env\\Scripts\\python.exe -m pip install -r requirements-dev.txt",
        "python -m venv .venv && .venv\\Scripts\\activate-evil && python -m pip install -r requirements-dev.txt",
        chain_commands(
            "python -m venv .venv",
            ".venv\\Scripts\\activate",
            "python -m pip install --upgrade pip",
            "python -m pip install -r requirements-dev.txt",
        ),
        "python -m venv .venv && C:\\Python314\\python.exe -m pip install -r requirements-dev.txt",
    ],
)
def test_venv_profile_requires_activation_or_the_local_interpreter(tmp_path: Path, venv: str) -> None:
    """Reject global installers, spoofed activation, wrong environments, and extra setup commands."""
    write_complete_profile(tmp_path)
    scripts: dict[str, object] = dict(STRICT_PACKAGE_SCRIPTS)
    scripts["python:venv"] = venv
    write_package_scripts(tmp_path, scripts)

    result = run_audit(tmp_path)

    assert result.returncode == 1
    assert "python:venv" in package_issues(result)


@pytest.mark.parametrize(
    "venv",
    [
        "python -m venv .venv && .venv/bin/python -m pip install -r requirements-dev.txt",
        "python -m venv .venv && . .venv/bin/activate && python -m pip install -r requirements-dev.txt",
    ],
)
def test_posix_local_interpreter_and_exact_activation_profiles_are_accepted(tmp_path: Path, venv: str) -> None:
    """Keep the accepted local-environment profiles realistic across Windows and POSIX."""
    write_complete_profile(tmp_path)
    scripts: dict[str, object] = dict(STRICT_PACKAGE_SCRIPTS)
    scripts["python:venv"] = venv
    write_package_scripts(tmp_path, scripts)

    result = run_audit(tmp_path)

    assert result.returncode == 0, result.stdout


def test_requirement_ruff_pin_must_satisfy_the_configured_minimum(tmp_path: Path) -> None:
    """Tie the selected dependency resolution to Ruff's configured required-version."""
    pyproject = STRICT_PYPROJECT.replace(">=0.15.20", ">=0.16.0", 1)
    write_complete_profile(tmp_path, pyproject=pyproject)

    result = run_audit(tmp_path)

    assert result.returncode == 1
    assert "package-json.python-scripts" in failed_checks(result)


@pytest.mark.parametrize(
    "target",
    [
        "pylock.Token.toml",
        "pylock.token-secret.toml",
        "pylock.password.toml",
        "pylock.windows.prod.toml",
        "pylock_unsafe.toml",
        "../pylock.windows.toml",
        "requirements-private-key.txt",
    ],
)
def test_dependency_target_grammar_is_conservative_and_never_echoed(tmp_path: Path, target: str) -> None:
    """Reject unsafe target spellings without returning command-derived source names."""
    write_complete_profile(tmp_path)
    scripts: dict[str, object] = dict(STRICT_PACKAGE_SCRIPTS)
    scripts["python:bootstrap"] = f"python -m pip install -r {target}"
    write_package_scripts(tmp_path, scripts)

    result = run_audit(tmp_path)

    assert result.returncode == 1
    assert target not in result.stdout
    assert "python:bootstrap" in package_issues(result)


def test_named_lock_profile_mismatch_reports_only_sanitized_profile_identifiers(tmp_path: Path) -> None:
    """Do not expose either selected named-lock source when synchronized scripts disagree."""
    write_complete_profile(tmp_path)
    scripts: dict[str, object] = dict(STRICT_PACKAGE_SCRIPTS)
    scripts["python:bootstrap"] = "python -m pip install -r pylock.windows.toml"
    scripts["python:venv"] = "python -m venv .venv && .venv/bin/python -m pip install -r pylock.linux.toml"
    write_package_scripts(tmp_path, scripts)
    _ = (tmp_path / "pylock.windows.toml").write_text(pylock_contents(), encoding="utf-8")

    result = run_audit(tmp_path)

    assert result.returncode == 1
    assert "pylock.windows.toml" not in result.stdout
    assert "pylock.linux.toml" not in result.stdout
    issue = as_dict(package_issues(result)["python:venv"])
    assert set(issue) == {"actual", "expected", "issue", "same_selected_source"}
    assert issue["same_selected_source"] is False
    assert "source_id" in as_dict(issue["expected"])
    assert "source_id" in as_dict(issue["actual"])


@pytest.mark.parametrize(
    ("script_name", "command", "secret"),
    [
        ("python:bootstrap", 'python -m pip install -r "requirements-ULTRA-SECRET.txt', "ULTRA-SECRET"),
        ("python:bootstrap", "python -m pip install -r pylock.api-token.toml", "api-token"),
        ("test:python", "npm run alias-super-secret", "alias-super-secret"),
        ("ruff:check", "ruff check skills tests && echo command-secret", "command-secret"),
    ],
)
def test_command_and_alias_secrets_are_redacted_across_parser_and_graph_failures(
    tmp_path: Path,
    script_name: str,
    command: str,
    secret: str,
) -> None:
    """Keep raw command tokens out of malformed, graph, and unsupported-command issues."""
    write_complete_profile(tmp_path)
    scripts: dict[str, object] = dict(STRICT_PACKAGE_SCRIPTS)
    scripts[script_name] = command
    if script_name == "test:python":
        scripts["alias-super-secret"] = "echo hidden-secret"
    write_package_scripts(tmp_path, scripts)

    result = run_audit(tmp_path)

    assert result.returncode == 1
    assert secret not in result.stdout
    assert "Traceback" not in result.stderr


def test_dependency_file_content_is_never_reflected_in_diagnostics(tmp_path: Path) -> None:
    """Return only profile kind and existence when a source contains sensitive invalid text."""
    write_complete_profile(tmp_path)
    sensitive_value = "dependency-source-password-do-not-print"
    _ = (tmp_path / "requirements-dev.txt").write_text(
        f"--index-url https://user:{sensitive_value}@example.invalid/simple\n{PINNED_REQUIREMENTS}",
        encoding="utf-8",
    )

    result = run_audit(tmp_path)

    assert result.returncode == 1
    assert sensitive_value not in result.stdout
    issue = as_dict(package_issues(result)["python:bootstrap"])
    assert set(issue) == {"exists", "issue", "profile_kind", "source_id"}


def test_dense_alias_graph_stops_at_the_edge_bound_without_echoing_aliases(tmp_path: Path) -> None:
    """Bound dense composition graphs independently of node and command limits."""
    write_complete_profile(tmp_path)
    scripts: dict[str, object] = dict(STRICT_PACKAGE_SCRIPTS)
    leaf_names = [f"leaf-{index}" for index in range(32)]
    hub_names = [f"hub-{index}" for index in range(20)]
    scripts["test:python"] = " && ".join(f"npm run {name}" for name in hub_names)
    shared_references = " && ".join(f"npm run {name}" for name in leaf_names)
    scripts.update(dict.fromkeys(hub_names, shared_references))
    scripts.update(dict.fromkeys(leaf_names, "pytest"))
    write_package_scripts(tmp_path, scripts)

    result = run_audit(tmp_path)

    assert result.returncode == 1
    assert "test:python" in package_issues(result)
    assert all(name not in result.stdout for name in hub_names)
    assert "Traceback" not in result.stderr


@pytest.mark.parametrize(
    ("original", "replacement"),
    [
        (
            'addopts = ["--strict-config", "--strict-markers", "--import-mode=importlib"]',
            'addopts = ["--strict-config", "--strict-markers", "--import-mode=importlib", "--collect-only"]',
        ),
        (
            '    ".*",\n    "__pycache__",',
            '    "*",\n    "__pycache__",',
        ),
        (
            'filterwarnings = ["error"]',
            'python_files = ["never-match-anything"]\nfilterwarnings = ["error"]',
        ),
        (
            'filterwarnings = ["error"]',
            'collect_ignore_glob = ["**/*.py"]\nfilterwarnings = ["error"]',
        ),
    ],
)
def test_pytest_additive_discovery_and_execution_bypasses_fail(
    tmp_path: Path,
    original: str,
    replacement: str,
) -> None:
    """Reject pytest additions that make a complete-looking profile collect or execute nothing."""
    pyproject = STRICT_PYPROJECT.replace(original, replacement, 1)
    write_complete_profile(tmp_path, pyproject=pyproject)

    result = run_audit(tmp_path)

    assert result.returncode == 1
    assert "pytest.suppressions" in failed_checks(result)


@pytest.mark.parametrize(
    ("script_name", "command"),
    [
        ("pyright", "pyright fixtures"),
        ("typecheck:python", "mypy fixtures && npm run pyright"),
    ],
)
def test_typechecker_leaves_reject_command_line_scope_replacement(
    tmp_path: Path,
    script_name: str,
    command: str,
) -> None:
    """Use the audited root config instead of replacing checker scope with a fixture target."""
    write_complete_profile(tmp_path)
    scripts: dict[str, object] = dict(STRICT_PACKAGE_SCRIPTS)
    scripts[script_name] = command
    write_package_scripts(tmp_path, scripts)

    result = run_audit(tmp_path)

    assert result.returncode == 1
    assert script_name in package_issues(result)
