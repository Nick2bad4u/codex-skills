"""Tests for Python helper scripts bundled with skills."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import cast

REPO_ROOT = Path(__file__).resolve().parents[1]
AUDIT_SCRIPT = REPO_ROOT / "skills" / "python-strict-development" / "scripts" / "audit_python_strict.py"
DEPENDENCY_AUDIT_SCRIPT = (
    REPO_ROOT / "skills" / "dependency-update-maintenance" / "scripts" / "audit_dependency_update.py"
)
INVENTORY_SCRIPT = REPO_ROOT / "skills" / "vsicons-association-recommender" / "scripts" / "inventory_vsicons.py"
SCHEMASTORE_AUDIT_SCRIPT = REPO_ROOT / "skills" / "schemastore-pr-maintenance" / "scripts" / "audit_schemastore_pr.py"


def as_dict(value: object) -> dict[str, object]:
    """Assert that a dynamic JSON value is a string-keyed object."""
    if not isinstance(value, dict):
        raise TypeError("Expected JSON object.")

    result: dict[str, object] = {}
    for key, item in cast("dict[object, object]", value).items():
        if not isinstance(key, str):
            raise TypeError("Expected string JSON object key.")
        result[key] = item

    return result


def as_list(value: object) -> list[object]:
    """Assert that a dynamic JSON value is a list."""
    if not isinstance(value, list):
        raise TypeError("Expected JSON list.")

    return cast("list[object]", value)


def run_python(*args: str) -> subprocess.CompletedProcess[str]:
    """Run a Python script from the repository root."""
    return subprocess.run(  # noqa: S603 - Tests invoke local helper scripts with shell=False and fixed interpreter.
        [sys.executable, *args],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_audit_python_strict_accepts_repo_defaults() -> None:
    """Verify the strict Python audit accepts this repository's default configuration."""
    result = run_python(str(AUDIT_SCRIPT), str(REPO_ROOT), "--json")

    assert result.returncode == 0, result.stderr
    diagnostics = [as_dict(item) for item in as_list(json.loads(result.stdout))]
    severities = {str(diagnostic["severity"]) for diagnostic in diagnostics}
    checks = {str(diagnostic["check"]) for diagnostic in diagnostics}

    assert "fail" not in severities
    assert "pyproject.exists" in checks
    assert "package-json.python-scripts" in checks


def test_audit_python_strict_reports_missing_project_files(tmp_path: Path) -> None:
    """Verify the strict Python audit reports missing repository configuration."""
    result = run_python(str(AUDIT_SCRIPT), str(tmp_path))

    assert result.returncode == 1
    assert "FAIL pyproject.exists: pyproject.toml is missing." in result.stdout
    assert "WARN package-json.exists: package.json is absent" in result.stdout
    assert "WARN vscode.exists: .vscode/settings.json is absent" in result.stdout


def test_inventory_vsicons_reports_custom_icons(tmp_path: Path) -> None:
    """Verify the vsicons inventory reports custom file and folder icons."""
    custom_icons = tmp_path / "custom-icons"
    custom_icons.mkdir()
    _ = (custom_icons / "file_type_codex.svg").write_text("<svg />", encoding="utf-8")
    _ = (custom_icons / "folder_type_skills.svg").write_text("<svg />", encoding="utf-8")

    result = run_python(
        str(INVENTORY_SCRIPT),
        "--custom-icons",
        str(custom_icons),
        "--extension-root",
        str(tmp_path / "extensions"),
        "--json",
    )

    assert result.returncode == 0, result.stderr
    inventory = as_dict(json.loads(result.stdout))
    custom = [as_dict(item) for item in as_list(inventory["custom"])]
    custom_source = custom[0]

    assert custom_source["file_icons"] == ["codex"]
    assert custom_source["folder_icons"] == ["skills"]
    assert custom_source["missing_opened_folder_icons"] == ["skills"]


def test_inventory_vsicons_reports_text_summary_for_bundled_icons(tmp_path: Path) -> None:
    """Verify the vsicons inventory reports filtered text summaries for bundled icons."""
    custom_icons = tmp_path / "custom-icons"
    custom_icons.mkdir()
    _ = (custom_icons / "file_type_codex.svg").write_text("<svg />", encoding="utf-8")
    _ = (custom_icons / "file_type_unmatched.svg").write_text("<svg />", encoding="utf-8")

    extension_root = tmp_path / "extensions"
    bundled_icons = extension_root / "vscode-icons-team.vscode-icons-99.0.0" / "icons"
    bundled_icons.mkdir(parents=True)
    _ = (bundled_icons / "folder_type_codex.svg").write_text("<svg />", encoding="utf-8")
    _ = (bundled_icons / "folder_type_codex_opened.svg").write_text("<svg />", encoding="utf-8")

    result = run_python(
        str(INVENTORY_SCRIPT),
        "--custom-icons",
        str(custom_icons),
        "--extension-root",
        str(extension_root),
        "--query",
        "codex",
    )

    assert result.returncode == 0, result.stderr
    assert "custom: 1 source(s)" in result.stdout
    assert "bundled: 1 source(s)" in result.stdout
    assert "sample file icons: codex" in result.stdout
    assert "sample folder icons: codex" in result.stdout
    assert "folders missing _opened pair: 0" in result.stdout


def test_audit_schemastore_pr_reports_targeted_commands(tmp_path: Path) -> None:
    """Verify the SchemaStore PR audit reports schema surfaces and targeted commands."""
    schema_root = tmp_path / "src" / "schemas" / "json"
    catalog_root = tmp_path / "src" / "api" / "json"
    test_root = tmp_path / "src" / "test" / "example"
    schema_root.mkdir(parents=True)
    catalog_root.mkdir(parents=True)
    test_root.mkdir(parents=True)
    _ = (schema_root / "example.json").write_text("{}", encoding="utf-8")
    _ = (test_root / "example.json").write_text("{}", encoding="utf-8")
    _ = (catalog_root / "catalog.json").write_text(
        '{"schemas":[{"url":"https://www.schemastore.org/example.json"}]}',
        encoding="utf-8",
    )

    result = run_python(
        str(SCHEMASTORE_AUDIT_SCRIPT),
        str(tmp_path),
        "--changed-file",
        "src/schemas/json/example.json",
        "--changed-file",
        "src/test/example/example.json",
        "--json",
    )

    assert result.returncode == 0, result.stderr
    audit = as_dict(json.loads(result.stdout))
    assert audit["local_schemas"] == ["example.json"]
    assert audit["missing_positive_tests"] == []
    assert audit["missing_catalog_entries"] == []
    assert "node ./cli.js check --schema-name=example.json" in as_list(audit["suggested_commands"])


def test_audit_dependency_update_reports_repo_scripts(tmp_path: Path) -> None:
    """Verify the dependency update audit prefers repo scripts and gated update commands."""
    _ = (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "scripts": {
                    "release:verify": "npm test",
                    "test": "node --test",
                    "update-deps": "ncu -u",
                }
            }
        ),
        encoding="utf-8",
    )
    _ = (tmp_path / "package-lock.json").write_text("{}", encoding="utf-8")

    result = run_python(
        str(DEPENDENCY_AUDIT_SCRIPT),
        str(tmp_path),
        "--changed-file",
        "package.json",
        "--changed-file",
        "package-lock.json",
        "--include-update-commands",
        "--json",
    )

    assert result.returncode == 0, result.stderr
    audit = as_dict(json.loads(result.stdout))
    assert audit["package_managers"] == ["npm"]
    assert audit["install_commands"] == ["npm ci"]
    assert as_list(audit["validation_commands"])[:2] == ["npm run release:verify", "npm run test"]
    assert "npm run update-deps" in as_list(audit["update_commands"])


def test_audit_schemastore_pr_reports_missing_readiness(tmp_path: Path) -> None:
    """Verify the SchemaStore PR audit fails when a local schema lacks PR essentials."""
    schema_root = tmp_path / "src" / "schemas" / "json"
    schema_root.mkdir(parents=True)
    _ = (schema_root / "missing.json").write_text("{}", encoding="utf-8")

    result = run_python(
        str(SCHEMASTORE_AUDIT_SCRIPT),
        str(tmp_path),
        "--changed-file",
        "src/schemas/json/missing.json",
    )

    assert result.returncode == 1
    assert "missing positive tests:" in result.stdout
    assert "missing catalog/config entries:" in result.stdout
    assert "Local schema changes are missing positive tests." in result.stdout


def test_audit_dependency_update_reports_python_and_workflows(tmp_path: Path) -> None:
    """Verify the dependency update audit reports Python and workflow validation hints."""
    workflow_root = tmp_path / ".github" / "workflows"
    workflow_root.mkdir(parents=True)
    _ = (workflow_root / "ci.yml").write_text("name: CI\n", encoding="utf-8")
    _ = (tmp_path / "requirements-dev.txt").write_text("pytest\n", encoding="utf-8")
    _ = (tmp_path / "uv.lock").write_text("", encoding="utf-8")
    _ = (tmp_path / "pyproject.toml").write_text(
        """[tool.ruff]
[tool.mypy]
[tool.pyright]
[tool.pytest.ini_options]
""",
        encoding="utf-8",
    )

    result = run_python(
        str(DEPENDENCY_AUDIT_SCRIPT),
        str(tmp_path),
        "--changed-file",
        "pyproject.toml",
        "--changed-file",
        "uv.lock",
        "--changed-file",
        ".github/workflows/ci.yml",
    )

    assert result.returncode == 0, result.stderr
    assert "  - python" in result.stdout
    assert "  - github-actions" in result.stdout
    assert "  - python -m pip install -r requirements-dev.txt" in result.stdout
    assert "  - ruff check ." in result.stdout
    assert "  - actionlint" in result.stdout
    assert "Mutating update commands omitted" in result.stdout


def test_audit_dependency_update_reports_multiple_ecosystems(tmp_path: Path) -> None:
    """Verify the dependency update audit detects lockfile ecosystems beyond npm."""
    _ = (tmp_path / "pnpm-lock.yaml").write_text("", encoding="utf-8")
    _ = (tmp_path / "yarn.lock").write_text("", encoding="utf-8")
    _ = (tmp_path / "bun.lock").write_text("", encoding="utf-8")
    _ = (tmp_path / "go.mod").write_text("module example\n", encoding="utf-8")
    _ = (tmp_path / "Cargo.toml").write_text("[package]\nname = 'example'\n", encoding="utf-8")
    _ = (tmp_path / "example.csproj").write_text("<Project />\n", encoding="utf-8")

    result = run_python(
        str(DEPENDENCY_AUDIT_SCRIPT),
        str(tmp_path),
        "--changed-file",
        "pnpm-lock.yaml",
        "--changed-file",
        "yarn.lock",
        "--changed-file",
        "bun.lock",
        "--changed-file",
        "go.mod",
        "--changed-file",
        "Cargo.toml",
        "--changed-file",
        "example.csproj",
        "--include-update-commands",
        "--json",
    )

    assert result.returncode == 0, result.stderr
    audit = as_dict(json.loads(result.stdout))
    assert audit["package_managers"] == ["pnpm", "yarn", "bun", "go", "rust", "dotnet"]
    assert "pnpm install --frozen-lockfile" in as_list(audit["install_commands"])
    assert "go test ./..." in as_list(audit["validation_commands"])
    assert "cargo update" in as_list(audit["update_commands"])
