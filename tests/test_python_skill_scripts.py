"""Tests for Python helper scripts bundled with skills."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import cast

REPO_ROOT = Path(__file__).resolve().parents[1]
AUDIT_SCRIPT = REPO_ROOT / "skills" / "python-strict-development" / "scripts" / "audit_python_strict.py"
INVENTORY_SCRIPT = REPO_ROOT / "skills" / "vsicons-association-recommender" / "scripts" / "inventory_vsicons.py"


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
