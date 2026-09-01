# Copyright (c) 2026 Nick2bad4u
"""Safety and fail-closed tests for the SchemaStore PR auditor."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import cast

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
AUDIT_SCRIPT = REPO_ROOT / "skills" / "schemastore-pr-maintenance" / "scripts" / "audit_schemastore_pr.py"
OPERATIONAL_ERROR = 2


def as_dict(value: object) -> dict[str, object]:
    """Assert that a dynamic JSON value is a string-keyed object."""
    if not isinstance(value, dict):
        raise TypeError("Expected a JSON object.")
    return cast("dict[str, object]", value)


def as_list(value: object) -> list[object]:
    """Assert that a dynamic JSON value is a list."""
    if not isinstance(value, list):
        raise TypeError("Expected a JSON list.")
    return cast("list[object]", value)


def run_audit(
    repository: Path,
    *arguments: str,
    environment: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run the auditor with deterministic captured text output."""
    return subprocess.run(  # noqa: S603  # Fixed interpreter and repository-local script; no shell.
        [sys.executable, str(AUDIT_SCRIPT), str(repository), *arguments],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        stdin=subprocess.DEVNULL,
        text=True,
        env=environment,
    )


def run_git(repository: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    """Run Git in a temporary test repository and require success."""
    git_executable = shutil.which("git")
    if git_executable is None:
        pytest.skip("Git is required for SchemaStore auditor integration tests.")
    result = subprocess.run(  # noqa: S603  # Resolved Git executable and test-controlled arguments; no shell.
        [git_executable, *arguments],
        cwd=repository,
        check=False,
        capture_output=True,
        stdin=subprocess.DEVNULL,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return result


def initialize_repository(repository: Path) -> None:
    """Initialize a temporary Git repository with a local test identity."""
    _ = run_git(repository, "init")
    _ = run_git(repository, "config", "user.email", "audit@example.invalid")
    _ = run_git(repository, "config", "user.name", "SchemaStore Audit Test")


def commit_all(repository: Path, message: str) -> None:
    """Commit every temporary fixture change."""
    _ = run_git(repository, "add", "--all")
    _ = run_git(repository, "commit", "-m", message)


def write_catalog_entries(repository: Path, entries: list[dict[str, object]]) -> None:
    """Write structurally test-controlled SchemaStore catalog entries."""
    catalog = repository / "src" / "api" / "json" / "catalog.json"
    catalog.parent.mkdir(parents=True, exist_ok=True)
    _ = catalog.write_text(json.dumps({"schemas": entries}), encoding="utf-8")


def write_catalog(repository: Path, schema_names: list[str]) -> None:
    """Write a structurally valid minimal SchemaStore catalog."""
    write_catalog_entries(
        repository,
        [{"url": f"https://www.schemastore.org/{schema_name}"} for schema_name in schema_names],
    )


def write_validation_config(repository: Path, content: str = "{}") -> None:
    """Write a schema-validation.jsonc fixture."""
    path = repository / "src" / "schema-validation.jsonc"
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(content, encoding="utf-8")


def write_schema(repository: Path, schema_name: str) -> None:
    """Write one local schema without adding tests."""
    schema = repository / "src" / "schemas" / "json" / schema_name
    schema.parent.mkdir(parents=True, exist_ok=True)
    _ = schema.write_text("{}", encoding="utf-8")


def write_schema_with_test(repository: Path, schema_name: str) -> None:
    """Write one local schema and one positive test file."""
    write_schema(repository, schema_name)
    test = repository / "src" / "test" / schema_name.removesuffix(".json") / "valid.json"
    test.parent.mkdir(parents=True, exist_ok=True)
    _ = test.write_text("{}", encoding="utf-8")


def diagnostic_code(result: subprocess.CompletedProcess[str]) -> str:
    """Return the first machine-readable diagnostic code."""
    payload = as_dict(json.loads(result.stdout))
    diagnostics = as_list(payload["diagnostics"])
    return str(as_dict(diagnostics[0])["code"])


def test_explicit_changed_file_audits_non_git_fixture_and_emits_structured_argv(tmp_path: Path) -> None:
    """Explicit files bypass Git while preserving structured safe command arguments."""
    write_schema_with_test(tmp_path, "example.json")
    write_catalog(tmp_path, ["example.json"])

    changed_schema = "src/schemas/json/example.json"
    result = run_audit(tmp_path, "--changed-file", changed_schema, "--json")

    assert result.returncode == 0, result.stderr
    audit = as_dict(json.loads(result.stdout))
    assert audit["baseline_ref"] is None
    assert audit["committed_changed_files"] == []
    assert audit["uncommitted_changed_files"] == []
    assert audit["explicit_changed_files"] == [changed_schema]
    assert ["node", "./cli.js", "check", "--schema-name=example.json"] in as_list(audit["suggested_command_argv"])


def test_git_discovery_reports_missing_git_worktree_and_baseline_distinctly(tmp_path: Path) -> None:
    """Git discovery fails with stable diagnostics instead of reporting zero changes."""
    no_git_environment = {**os.environ, "PATH": ""}
    missing_git = run_audit(tmp_path, "--json", environment=no_git_environment)
    not_worktree = run_audit(tmp_path, "--json")

    initialize_repository(tmp_path)
    _ = (tmp_path / "README.md").write_text("fixture\n", encoding="utf-8")
    commit_all(tmp_path, "baseline-less commit")
    missing_baseline = run_audit(tmp_path, "--json")

    assert missing_git.returncode == OPERATIONAL_ERROR
    assert diagnostic_code(missing_git) == "git_not_found"
    assert not_worktree.returncode == OPERATIONAL_ERROR
    assert diagnostic_code(not_worktree) == "not_git_worktree"
    assert missing_baseline.returncode == OPERATIONAL_ERROR
    assert diagnostic_code(missing_baseline) == "git_baseline_missing"


def test_git_command_failure_is_not_collapsed_to_zero_changes(tmp_path: Path) -> None:
    """A failing Git status command produces a controlled command diagnostic."""
    initialize_repository(tmp_path)
    _ = (tmp_path / "README.md").write_text("fixture\n", encoding="utf-8")
    commit_all(tmp_path, "baseline")
    _ = run_git(tmp_path, "update-ref", "refs/remotes/origin/main", "HEAD")
    _ = (tmp_path / ".git" / "index").write_bytes(b"not-a-git-index")

    result = run_audit(tmp_path, "--json")

    assert result.returncode == OPERATIONAL_ERROR
    assert diagnostic_code(result) == "git_command_failed"


def test_git_nul_discovery_keeps_sources_deletions_and_both_rename_paths(tmp_path: Path) -> None:
    """Committed and uncommitted NUL records retain deletes and both sides of renames."""
    initialize_repository(tmp_path)
    for schema_name in ("old.json", "stay.json", "uncommitted.json"):
        write_schema_with_test(tmp_path, schema_name)
    write_catalog(tmp_path, ["old.json", "stay.json", "uncommitted.json", "renamed.json"])
    write_validation_config(tmp_path)
    commit_all(tmp_path, "baseline")
    _ = run_git(tmp_path, "update-ref", "refs/remotes/origin/main", "HEAD")

    _ = run_git(
        tmp_path,
        "mv",
        "src/schemas/json/old.json",
        "src/schemas/json/renamed.json",
    )
    _ = run_git(tmp_path, "rm", "src/test/stay/valid.json")
    commit_all(tmp_path, "committed rename and delete")
    _ = run_git(
        tmp_path,
        "mv",
        "src/test/uncommitted/valid.json",
        "src/test/uncommitted/renamed.json",
    )

    result = run_audit(tmp_path, "--json")

    assert result.returncode == 1, result.stderr
    audit = as_dict(json.loads(result.stdout))
    committed = as_list(audit["committed_changed_files"])
    uncommitted = as_list(audit["uncommitted_changed_files"])
    deleted = as_list(audit["deleted_critical_files"])
    assert audit["baseline_ref"] == "origin/main"
    assert "src/schemas/json/old.json" in committed
    assert "src/schemas/json/renamed.json" in committed
    assert "src/test/stay/valid.json" in committed
    assert "src/test/uncommitted/valid.json" in uncommitted
    assert "src/test/uncommitted/renamed.json" in uncommitted
    assert "src/schemas/json/old.json" in deleted
    assert "src/test/stay/valid.json" in deleted
    assert "src/test/uncommitted/valid.json" in deleted


@pytest.mark.parametrize(
    "schema_filename",
    [
        "bad;command.json",
        "bad name.json",
        'bad"quote.json',
        "bad`command.json",
        "bad$variable.json",
        "bad\nline.json",
        "-leading-option.json",
    ],
)
def test_schema_filename_injection_is_rejected_before_command_rendering(
    tmp_path: Path,
    schema_filename: str,
) -> None:
    """PR-controlled shell and control characters never reach command output."""
    result = run_audit(
        tmp_path,
        "--changed-file",
        f"src/schemas/json/{schema_filename}",
        "--json",
    )

    assert result.returncode == OPERATIONAL_ERROR
    payload = as_dict(json.loads(result.stdout))
    assert diagnostic_code(result) in {"unsafe_changed_path", "unsafe_schema_filename"}
    assert "suggested_commands" not in payload
    assert "suggested_command_argv" not in payload


@pytest.mark.parametrize(
    "accepted_base",
    [
        "https://www.schemastore.org/",
        "https://raw.githubusercontent.com/SchemaStore/schemastore/master/src/schemas/json/",
    ],
)
def test_catalog_versions_register_local_schema_from_authoritative_bases_only(
    tmp_path: Path,
    accepted_base: str,
) -> None:
    """Every string versions URL participates in local catalog registration."""
    write_schema_with_test(tmp_path, "versioned.json")
    write_catalog_entries(
        tmp_path,
        [
            {
                "url": "https://example.invalid/current.json",
                "versions": {"legacy": f"{accepted_base}versioned.json"},
            }
        ],
    )

    result = run_audit(
        tmp_path,
        "--changed-file",
        "src/schemas/json/versioned.json",
        "--json",
    )

    assert result.returncode == 0, result.stderr
    assert as_dict(json.loads(result.stdout))["missing_catalog_entries"] == []


@pytest.mark.parametrize(
    "near_alias",
    [
        "https://json.schemastore.org/primary-near-alias.json",
        "https://raw.githubusercontent.com/SchemaStore/schemastore/main/src/schemas/json/primary-near-alias.json",
        "https://www.schemastore.org.example/primary-near-alias.json",
        (
            "https://raw.githubusercontent.com/SchemaStore/schemastore/master/"
            "src/schemas/jsonish/primary-near-alias.json"
        ),
    ],
)
def test_catalog_primary_url_rejects_near_alias_bases(tmp_path: Path, near_alias: str) -> None:
    """Primary catalog URLs must use one of the two authoritative local bases."""
    write_schema_with_test(tmp_path, "primary-near-alias.json")
    write_catalog_entries(tmp_path, [{"url": near_alias}])

    result = run_audit(
        tmp_path,
        "--changed-file",
        "src/schemas/json/primary-near-alias.json",
        "--json",
    )

    assert result.returncode == 1, result.stderr
    assert as_dict(json.loads(result.stdout))["missing_catalog_entries"] == ["primary-near-alias.json"]


@pytest.mark.parametrize(
    "near_alias",
    [
        "https://json.schemastore.org/near-alias.json",
        "https://raw.githubusercontent.com/SchemaStore/schemastore/main/src/schemas/json/near-alias.json",
        "https://www.schemastore.org.example/near-alias.json",
        "https://raw.githubusercontent.com/SchemaStore/schemastore/master/src/schemas/jsonish/near-alias.json",
        "https://www.schemastore.org/not-near-alias.json",
        "https://www.schemastore.org/near-alias.json.backup",
        "https://raw.githubusercontent.com/SchemaStore/schemastore/master/src/schemas/json/near-alias-v2.json",
    ],
)
def test_catalog_versions_reject_near_alias_url_bases(tmp_path: Path, near_alias: str) -> None:
    """Near aliases in versions do not satisfy authoritative local URL registration."""
    write_schema_with_test(tmp_path, "near-alias.json")
    write_catalog_entries(
        tmp_path,
        [{"url": "https://example.invalid/current.json", "versions": {"legacy": near_alias}}],
    )

    result = run_audit(
        tmp_path,
        "--changed-file",
        "src/schemas/json/near-alias.json",
        "--json",
    )

    assert result.returncode == 1, result.stderr
    assert as_dict(json.loads(result.stdout))["missing_catalog_entries"] == ["near-alias.json"]


@pytest.mark.parametrize(
    "versions",
    [
        None,
        [],
        "https://www.schemastore.org/versioned.json",
        {"legacy": 1},
    ],
)
def test_catalog_rejects_invalid_versions_shapes_and_values(tmp_path: Path, versions: object) -> None:
    """Present versions must be an object containing only string URL values."""
    write_catalog_entries(
        tmp_path,
        [{"url": "https://example.invalid/current.json", "versions": versions}],
    )

    result = run_audit(tmp_path, "--changed-file", "README.md", "--json")

    assert result.returncode == OPERATIONAL_ERROR
    assert diagnostic_code(result) == "catalog_structure_invalid"


def test_jsonc_exact_exemptions_string_awareness_and_coverage_commands(tmp_path: Path) -> None:
    """Only exact exemptions count, while JSONC strings, comments, commas, and coverage stay structural."""
    schema_names = ["cataloged.json", "missing-exempt.json", "skip-exempt.json", "unrelated.json"]
    for schema_name in ("cataloged.json", "missing-exempt.json", "unrelated.json"):
        write_schema_with_test(tmp_path, schema_name)
    write_schema(tmp_path, "skip-exempt.json")
    write_catalog(tmp_path, ["cataloged.json"])
    write_validation_config(
        tmp_path,
        """{
  // unrelated.json in a comment is not an exemption.
  "missingCatalogUrl": ["missing-exempt.json",],
  "skiptest": ["skip-exempt.json",],
  "ajvNotStrictMode": ["unrelated.json"],
  "options": {
    "unrelated.json": {
      "unknownKeywords": ["https://example.invalid//keyword", "/*literal*/",],
    },
  },
  "coverage": [
    {"schema": "unrelated.json", "strict": true,},
  ],
}
""",
    )
    changed_arguments = [
        argument for schema_name in schema_names for argument in ("--changed-file", f"src/schemas/json/{schema_name}")
    ]

    result = run_audit(
        tmp_path,
        *changed_arguments,
        "--changed-file",
        "src/schema-validation.jsonc",
        "--json",
    )

    assert result.returncode == 1, result.stderr
    audit = as_dict(json.loads(result.stdout))
    assert audit["missing_catalog_entries"] == ["unrelated.json"]
    assert audit["missing_positive_tests"] == []
    assert audit["skiptest_test_conflicts"] == []
    assert audit["targeted_coverage_schemas"] == ["unrelated.json"]
    assert audit["release_blocking_coverage_schemas"] == ["unrelated.json"]
    argv = as_list(audit["suggested_command_argv"])
    assert ["node", "./cli.js", "coverage", "--schema-name=unrelated.json"] in argv
    assert ["node", "./cli.js", "coverage"] in argv
    assert "Strict coverage is release-blocking for the listed changed schemas." in as_list(audit["warnings"])


def test_missing_catalog_url_allows_tests_but_skiptest_forbids_all_test_surfaces(tmp_path: Path) -> None:
    """Keep missingCatalogUrl testable while reporting both skiptest test directories."""
    write_schema_with_test(tmp_path, "missing-catalog.json")
    write_schema_with_test(tmp_path, "skipped.json")
    negative_test = tmp_path / "src" / "negative_test" / "skipped" / "invalid.json"
    negative_test.parent.mkdir(parents=True)
    _ = negative_test.write_text("{}", encoding="utf-8")
    write_catalog(tmp_path, [])
    write_validation_config(
        tmp_path,
        """{
  "missingCatalogUrl": ["missing-catalog.json"],
  "skiptest": ["skipped.json"]
}
""",
    )

    result = run_audit(
        tmp_path,
        "--changed-file",
        "src/schemas/json/missing-catalog.json",
        "--changed-file",
        "src/test/missing-catalog/valid.json",
        "--changed-file",
        "src/schemas/json/skipped.json",
        "--changed-file",
        "src/test/skipped/valid.json",
        "--changed-file",
        "src/negative_test/skipped/invalid.json",
        "--json",
    )

    assert result.returncode == 1, result.stderr
    audit = as_dict(json.loads(result.stdout))
    assert audit["missing_catalog_entries"] == []
    assert audit["missing_positive_tests"] == []
    assert audit["skiptest_test_conflicts"] == [
        "src/test/skipped",
        "src/negative_test/skipped",
    ]
    assert ["node", "./cli.js", "check", "--schema-name=missing-catalog.json"] in as_list(
        audit["suggested_command_argv"]
    )
    assert ["node", "./cli.js", "check", "--schema-name=skipped.json"] not in as_list(audit["suggested_command_argv"])


def test_skiptest_without_tests_exempts_catalog_and_positive_test_readiness(tmp_path: Path) -> None:
    """A skiptest schema without test surfaces does not require catalog or positive tests."""
    write_schema(tmp_path, "skipped.json")
    write_catalog(tmp_path, [])
    write_validation_config(tmp_path, '{"skiptest":["skipped.json"]}')

    result = run_audit(
        tmp_path,
        "--changed-file",
        "src/schemas/json/skipped.json",
        "--json",
    )

    assert result.returncode == 0, result.stderr
    audit = as_dict(json.loads(result.stdout))
    assert audit["missing_catalog_entries"] == []
    assert audit["missing_positive_tests"] == []
    assert audit["skiptest_test_conflicts"] == []


def test_missing_catalog_url_does_not_exempt_positive_test_readiness(tmp_path: Path) -> None:
    """A missingCatalogUrl schema remains testable and still needs a positive test."""
    write_schema(tmp_path, "still-testable.json")
    write_catalog(tmp_path, [])
    write_validation_config(tmp_path, '{"missingCatalogUrl":["still-testable.json"]}')

    result = run_audit(
        tmp_path,
        "--changed-file",
        "src/schemas/json/still-testable.json",
        "--json",
    )

    assert result.returncode == 1, result.stderr
    audit = as_dict(json.loads(result.stdout))
    assert audit["missing_catalog_entries"] == []
    assert audit["missing_positive_tests"] == ["still-testable.json"]
    assert audit["skiptest_test_conflicts"] == []


def test_targeted_coverage_is_retained_without_config_change(tmp_path: Path) -> None:
    """A changed opted-in schema receives targeted coverage without forcing full coverage."""
    write_schema_with_test(tmp_path, "covered.json")
    write_catalog(tmp_path, ["covered.json"])
    write_validation_config(
        tmp_path,
        '{"coverage":[{"schema":"covered.json","strict":false}]}',
    )

    result = run_audit(
        tmp_path,
        "--changed-file",
        "src/test/covered/valid.json",
        "--json",
    )

    assert result.returncode == 0, result.stderr
    audit = as_dict(json.loads(result.stdout))
    argv = as_list(audit["suggested_command_argv"])
    assert audit["targeted_coverage_schemas"] == ["covered.json"]
    assert ["node", "./cli.js", "coverage", "--schema-name=covered.json"] in argv
    assert ["node", "./cli.js", "coverage"] not in argv


@pytest.mark.parametrize(
    ("relative_path", "content", "expected_code"),
    [
        ("src/api/json/catalog.json", '{"schemas":[', "catalog_json_invalid"),
        (
            "src/schema-validation.jsonc",
            '{"skiptest":["example.json",], /* unterminated',
            "schema_validation_jsonc_invalid",
        ),
    ],
)
def test_malformed_json_and_jsonc_return_machine_readable_diagnostics(
    tmp_path: Path,
    relative_path: str,
    content: str,
    expected_code: str,
) -> None:
    """Malformed source files fail nonzero without a traceback or partial audit."""
    write_catalog(tmp_path, [])
    write_validation_config(tmp_path)
    target = tmp_path / Path(relative_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    _ = target.write_text(content, encoding="utf-8")

    result = run_audit(tmp_path, "--changed-file", "README.md", "--json")

    assert result.returncode == OPERATIONAL_ERROR
    assert result.stderr == ""
    assert diagnostic_code(result) == expected_code
    assert "Traceback" not in result.stdout


@pytest.mark.parametrize(
    "deleted_path",
    [
        "src/schemas/json/deleted.json",
        "src/api/json/catalog.json",
        "src/test/deleted/valid.json",
        "src/schema-validation.jsonc",
    ],
)
def test_explicit_critical_deletions_cannot_return_false_clean(
    tmp_path: Path,
    deleted_path: str,
) -> None:
    """Every destructive SchemaStore surface produces a readiness finding."""
    if deleted_path != "src/api/json/catalog.json":
        write_catalog(tmp_path, [])
    if deleted_path != "src/schema-validation.jsonc":
        write_validation_config(tmp_path)

    result = run_audit(tmp_path, "--changed-file", deleted_path, "--json")

    assert result.returncode == 1, result.stderr
    audit = as_dict(json.loads(result.stdout))
    assert deleted_path in as_list(audit["deleted_critical_files"])


@pytest.mark.parametrize(
    "replaced_path",
    [
        "src/schemas/json/replaced.json",
        "src/test/replaced/valid.json",
        "src/negative_test/replaced/invalid.json",
        "src/api/json/catalog.json",
        "src/schema-validation.jsonc",
    ],
)
def test_critical_paths_replaced_by_directories_are_invalid(
    tmp_path: Path,
    replaced_path: str,
) -> None:
    """A directory at any changed file-only surface remains a readiness finding."""
    write_schema_with_test(tmp_path, "replaced.json")
    negative_test = tmp_path / "src" / "negative_test" / "replaced" / "invalid.json"
    negative_test.parent.mkdir(parents=True)
    _ = negative_test.write_text("{}", encoding="utf-8")
    write_catalog(tmp_path, ["replaced.json"])
    write_validation_config(tmp_path)

    target = tmp_path / Path(replaced_path)
    target.unlink()
    target.mkdir()

    result = run_audit(tmp_path, "--changed-file", replaced_path, "--json")

    assert result.returncode == 1, result.stderr
    audit = as_dict(json.loads(result.stdout))
    assert replaced_path in as_list(audit["deleted_critical_files"])
    assert (
        "Critical schema, catalog, test, or validation-config paths are missing or are not regular files."
        in as_list(audit["warnings"])
    )
