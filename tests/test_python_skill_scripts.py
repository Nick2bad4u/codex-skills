# Copyright (c) 2026 Nick2bad4u
"""Tests for Python helper scripts bundled with skills."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import cast

ARGPARSE_USAGE_ERROR = 2
REPO_ROOT = Path(__file__).resolve().parents[1]
AUDIT_SCRIPT = REPO_ROOT / "skills" / "python-strict-development" / "scripts" / "audit_python_strict.py"
DEPENDENCY_AUDIT_SCRIPT = (
    REPO_ROOT / "skills" / "dependency-update-maintenance" / "scripts" / "audit_dependency_update.py"
)
INVENTORY_SCRIPT = REPO_ROOT / "skills" / "vsicons-association-recommender" / "scripts" / "inventory_vsicons.py"
SCHEMASTORE_AUDIT_SCRIPT = REPO_ROOT / "skills" / "schemastore-pr-maintenance" / "scripts" / "audit_schemastore_pr.py"
CODACY_SCRIPT = REPO_ROOT / "skills" / "codacy-management" / "scripts" / "manage_codacy.py"


def write_codacy_spec(path: Path) -> None:
    """Write a small Codacy-shaped OpenAPI fixture."""
    _ = path.write_text(
        """openapi: 3.0.1
paths:
  /analysis/organizations/{provider}/{remoteOrganizationName}/repositories/{repositoryName}:
    get:
      summary: Get repository analysis
      operationId: getRepositoryWithAnalysis
  /analysis/organizations/{provider}/{remoteOrganizationName}/repositories/{repositoryName}/issues/search:
    post:
      summary: Search repository issues
      operationId: searchRepositoryIssues
""",
        encoding="utf-8",
    )


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
    return subprocess.run(  # noqa: S603  # Fixed interpreter and local helper arguments; no shell.
        [sys.executable, *args],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        stdin=subprocess.DEVNULL,
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


def test_audit_scripts_reject_missing_repositories(tmp_path: Path) -> None:
    """Verify repository arguments are resolved and validated before use."""
    missing_repository = tmp_path / "missing"
    for script in (DEPENDENCY_AUDIT_SCRIPT, SCHEMASTORE_AUDIT_SCRIPT):
        result = run_python(str(script), str(missing_repository))

        assert result.returncode == ARGPARSE_USAGE_ERROR
        assert "Repository path does not exist" in result.stderr


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


def test_codacy_context_detects_github_origin_without_exposing_token(tmp_path: Path) -> None:
    """Verify Codacy context derives the slug and reports only the token environment name."""
    initialized = run_python(
        "-c",
        "import subprocess,sys; subprocess.run(['git','init',sys.argv[1]],check=True)",
        str(tmp_path),
    )
    remote_added = run_python(
        "-c",
        (
            "import subprocess,sys; "
            "subprocess.run(['git','-C',sys.argv[1],'remote','add','origin',"
            "'git@github.com:acme/widget.git'],check=True)"
        ),
        str(tmp_path),
    )
    assert initialized.returncode == 0, initialized.stderr
    assert remote_added.returncode == 0, remote_added.stderr

    result = subprocess.run(  # noqa: S603  # Fixed interpreter and local helper arguments; no shell.
        [sys.executable, str(CODACY_SCRIPT), "context", "--repo", str(tmp_path), "--json"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        stdin=subprocess.DEVNULL,
        text=True,
        env={**os.environ, "CODACY_API_TOKEN": "top-secret-token"},
    )

    assert result.returncode == 0, result.stderr
    payload = as_dict(json.loads(result.stdout))
    slug = as_dict(payload["slug"])
    assert slug == {"organization": "acme", "provider": "gh", "repository": "widget"}
    assert payload["token"] == "configured"  # noqa: S105  # Status label, not a credential.
    assert payload["tokenEnvironment"] == "CODACY_API_TOKEN"
    assert "top-secret-token" not in result.stdout


def test_codacy_operations_filters_local_openapi_fixture(tmp_path: Path) -> None:
    """Verify operation discovery parses a local OpenAPI document without a YAML dependency."""
    spec = tmp_path / "codacy.yaml"
    write_codacy_spec(spec)
    result = run_python(
        str(CODACY_SCRIPT),
        "operations",
        "--spec-file",
        str(spec),
        "--search",
        "issues",
        "--method",
        "POST",
        "--json",
    )

    assert result.returncode == 0, result.stderr
    payload = as_dict(json.loads(result.stdout))
    operations = [as_dict(item) for item in as_list(payload["operations"])]
    assert operations == [
        {
            "method": "POST",
            "operation_id": "searchRepositoryIssues",
            "path": (
                "/analysis/organizations/{provider}/{remoteOrganizationName}"
                "/repositories/{repositoryName}/issues/search"
            ),
            "summary": "Search repository issues",
        }
    ]


def test_codacy_request_resolves_operation_and_previews_non_get(tmp_path: Path) -> None:
    """Verify operation-based POST requests auto-fill repository parameters and remain previews."""
    spec = tmp_path / "codacy.yaml"
    write_codacy_spec(spec)
    result = run_python(
        str(CODACY_SCRIPT),
        "request",
        "--spec-file",
        str(spec),
        "--operation-id",
        "searchRepositoryIssues",
        "--provider",
        "gh",
        "--organization",
        "acme",
        "--repository",
        "widget",
        "--body-json",
        '{"levels":["Error"],"api_token":"must-redact"}',
        "--json",
    )

    assert result.returncode == 0, result.stderr
    preview = as_dict(json.loads(result.stdout))
    body = as_dict(preview["body"])
    assert preview["dryRun"] is True
    assert preview["method"] == "POST"
    assert str(preview["url"]).endswith("/analysis/organizations/gh/acme/repositories/widget/issues/search")
    assert body["api_token"] == "<redacted>"  # noqa: S105  # Expected redaction marker.
    assert "must-redact" not in result.stdout


def test_codacy_request_rejects_sensitive_query_and_foreign_origin() -> None:
    """Verify raw requests reject query secrets and absolute origin escapes."""
    credentialed_api_url = f"https://{'user'}:{'password'}@api.codacy.com/api/v3/user"
    sensitive = run_python(
        str(CODACY_SCRIPT),
        "request",
        "/user",
        "--query",
        "api-token=secret",
        "--dry-run",
    )
    foreign = run_python(
        str(CODACY_SCRIPT),
        "request",
        "https://example.com/api/v3/user",
        "--dry-run",
    )
    embedded_secret = run_python(
        str(CODACY_SCRIPT),
        "request",
        "/user?api-token=secret",
        "--dry-run",
    )
    url_credentials = run_python(
        str(CODACY_SCRIPT),
        "request",
        credentialed_api_url,
        "--dry-run",
    )
    traversal = run_python(
        str(CODACY_SCRIPT),
        "request",
        "/analysis/../user",
        "--dry-run",
    )

    assert sensitive.returncode == 1
    assert "Refusing token-like query parameter" in sensitive.stderr
    assert foreign.returncode == 1
    assert "must match the configured HTTPS origin and API base path" in foreign.stderr
    assert embedded_secret.returncode == 1
    assert "Refusing token-like endpoint query parameter" in embedded_secret.stderr
    assert url_credentials.returncode == 1
    assert "must not contain URL credentials" in url_credentials.stderr
    assert "password" not in url_credentials.stderr
    assert traversal.returncode == 1
    assert "must not contain traversal path segments" in traversal.stderr


def test_codacy_request_requires_explicit_public_get_or_token() -> None:
    """Verify tokenless GET execution fails while dry-run remains available."""
    environment = {key: value for key, value in os.environ.items() if key != "CODACY_API_TOKEN"}
    result = subprocess.run(  # noqa: S603  # Fixed interpreter and local helper arguments; no shell.
        [sys.executable, str(CODACY_SCRIPT), "request", "/user"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        stdin=subprocess.DEVNULL,
        text=True,
        env=environment,
    )
    dry_run = subprocess.run(  # noqa: S603  # Fixed interpreter and local helper arguments; no shell.
        [sys.executable, str(CODACY_SCRIPT), "request", "/user", "--dry-run", "--json"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        stdin=subprocess.DEVNULL,
        text=True,
        env=environment,
    )

    assert result.returncode == 1
    assert "No account token found" in result.stderr
    assert dry_run.returncode == 0, dry_run.stderr
    assert as_dict(json.loads(dry_run.stdout))["dryRun"] is True


def test_codacy_context_rejects_unsafe_or_ambiguous_inputs(tmp_path: Path) -> None:
    """Verify repository, API-origin, identity, and token-environment safety checks."""
    credentialed_base_url = f"https://{'user'}:{'pass'}@api.codacy.test/api/v3"
    initialized = run_python(
        "-c",
        "import subprocess,sys; subprocess.run(['git','init',sys.argv[1]],check=True)",
        str(tmp_path),
    )
    assert initialized.returncode == 0, initialized.stderr
    regular_file = tmp_path / "not-a-repository.txt"
    _ = regular_file.write_text("fixture", encoding="utf-8")
    missing_path = tmp_path / "missing"
    cases = [
        (["context", "--repo", str(missing_path)], ARGPARSE_USAGE_ERROR, "Repository path does not exist"),
        (["context", "--repo", str(regular_file)], ARGPARSE_USAGE_ERROR, "Repository path is not a directory"),
        (["context", "--base-url", "http://api.codacy.test/api/v3"], 1, "must be an absolute HTTPS URL"),
        (["context", "--base-url", credentialed_base_url], 1, "must not contain credentials"),
        (["context", "--base-url", "https://api.codacy.test/api/v3?token=no"], 1, "query or fragment"),
        (["context", "--token-env", "NOT-AN-ENV"], 1, "Invalid token environment variable name"),
        (["context", "--repo", str(tmp_path), "--provider", "gh"], 1, "Repository identity is incomplete"),
    ]

    for arguments, expected_code, expected_message in cases:
        result = run_python(str(CODACY_SCRIPT), *arguments)
        assert result.returncode == expected_code
        assert expected_message in result.stderr

    no_slug = run_python(str(CODACY_SCRIPT), "context", "--repo", str(tmp_path), "--json")
    assert no_slug.returncode == 0, no_slug.stderr
    assert as_dict(json.loads(no_slug.stdout))["slug"] is None


def test_codacy_request_rejects_malformed_and_conflicting_options(tmp_path: Path) -> None:
    """Verify raw and OpenAPI requests fail closed on malformed or conflicting input."""
    credentialed_spec_url = f"https://{'user'}:{'pass'}@api.codacy.test/api/api-docs/swagger.yaml"
    spec = tmp_path / "codacy.yaml"
    write_codacy_spec(spec)
    cases = [
        (["request", "relative", "--dry-run"], "Relative endpoint must start with"),
        (["request", "--dry-run"], "Provide an endpoint or --operation-id"),
        (
            ["request", "/user", "--operation-id", "getRepositoryWithAnalysis", "--dry-run"],
            "Provide either an endpoint or --operation-id",
        ),
        (["request", "/user", "--query", "broken", "--dry-run"], "non-empty name=value syntax"),
        (
            ["request", "/user", "--query", "limit=10", "--query", "limit=20", "--dry-run"],
            "Duplicate query name",
        ),
        (["request", "/user", "--query", "limit=many", "--dry-run"], "limit must be an integer"),
        (["request", "/user", "--query", "limit=1001", "--dry-run"], "limit must be between"),
        (["request", "/user", "--body-json", "{", "--dry-run"], "Invalid JSON in --body-json"),
        (["request", "/user", "--body-json", "{}", "--dry-run"], "GET requests must not include"),
        (
            ["request", "--spec-file", str(spec), "--operation-id", "missingOperation", "--dry-run"],
            "operationId must resolve exactly once",
        ),
        (
            [
                "request",
                "--spec-url",
                credentialed_spec_url,
                "--operation-id",
                "missingOperation",
                "--dry-run",
            ],
            "OpenAPI specification URL must not contain credentials",
        ),
        (
            [
                "request",
                "--spec-file",
                str(spec),
                "--operation-id",
                "searchRepositoryIssues",
                "--method",
                "GET",
                "--dry-run",
            ],
            "conflicts with OpenAPI operation",
        ),
        (["request", "/user", "--timeout", "0", "--dry-run"], "--timeout must be greater than zero"),
        (["request", "/user", "--max-pages", "0", "--dry-run"], "--max-pages must be at least one"),
        (["request", "/user", "--retries", "-1", "--dry-run"], "--retries must be zero or greater"),
        (["request", "/user", "--retry-delay", "-1", "--dry-run"], "--retry-delay must be zero or greater"),
        (["request", "/user", "--send", "--dry-run"], "--send and --dry-run are mutually exclusive"),
    ]

    for arguments, expected_message in cases:
        result = run_python(str(CODACY_SCRIPT), *arguments)
        assert result.returncode == 1
        assert expected_message in result.stderr
