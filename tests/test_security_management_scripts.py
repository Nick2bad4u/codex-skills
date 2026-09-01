# Copyright (c) 2026 Nick2bad4u
"""Behavioral tests for external security and activity management helpers."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import cast

REPO_ROOT = Path(__file__).resolve().parents[1]
ARGPARSE_USAGE_ERROR = 2
REDACTED = "<redacted>"
TEST_CREDENTIAL = "not-a-real-credential"
SOCKET_SCRIPT = REPO_ROOT / "skills" / "socket-management" / "scripts" / "manage_socket.py"
SNYK_SCRIPT = REPO_ROOT / "skills" / "snyk-management" / "scripts" / "manage_snyk.py"
WAKATIME_SCRIPT = REPO_ROOT / "skills" / "wakatime-management" / "scripts" / "manage_wakatime.py"
STEPSECURITY_SCRIPT = REPO_ROOT / "skills" / "stepsecurity-management" / "scripts" / "manage_stepsecurity.py"


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


def clean_environment(**values: str) -> dict[str, str]:
    """Build deterministic subprocess environment without real service credentials."""
    environment = os.environ.copy()
    for name in (
        "SOCKET_SECURITY_API_TOKEN",
        "SNYK_TOKEN",
        "STEP_SECURITY_API_KEY",
        "STEPSECURITY_API_KEY",
        "STEP_SECURITY_CUSTOMER",
        "WAKATIME_ACCESS_TOKEN",
        "WAKATIME_API_KEY",
    ):
        _ = environment.pop(name, None)
    environment.update(values)
    return environment


def run_script(
    script: Path,
    *arguments: str,
    environment: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run one fixed local helper without a shell."""
    return subprocess.run(  # noqa: S603  # Fixed interpreter and repository-owned script.
        [sys.executable, str(script), *arguments],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        env=environment or clean_environment(),
        stdin=subprocess.DEVNULL,
        text=True,
    )


def write_openapi(path: Path, paths: dict[str, object]) -> None:
    """Write a small OpenAPI 3 JSON fixture."""
    _ = path.write_text(
        json.dumps({"openapi": "3.0.3", "info": {"title": "fixture", "version": "1"}, "paths": paths}),
        encoding="utf-8",
    )


def test_socket_context_and_operation_discovery_redact_credentials(tmp_path: Path) -> None:
    """Resolve Socket context and filter a local OpenAPI operation safely."""
    secret = TEST_CREDENTIAL
    environment = clean_environment(TEST_SOCKET_KEY=secret)
    context_result = run_script(
        SOCKET_SCRIPT,
        "context",
        "--repo",
        str(REPO_ROOT),
        "--org",
        "nick2bad4u",
        "--repository",
        "demo",
        "--token-env",
        "TEST_SOCKET_KEY",
        environment=environment,
    )

    assert context_result.returncode == 0, context_result.stderr
    assert secret not in context_result.stdout
    context = as_dict(json.loads(context_result.stdout))
    assert context["organization"] == "nick2bad4u"
    assert context["repository"] == "demo"
    assert context.get("token") == "configured"

    spec = tmp_path / "socket-openapi.json"
    write_openapi(
        spec,
        {
            "/orgs/{org}/alerts": {
                "get": {
                    "operationId": "listAlerts",
                    "summary": "List organization alerts",
                    "tags": ["Alerts"],
                }
            },
            "/orgs/{org}/policies": {"post": {"operationId": "createPolicy", "summary": "Create policy"}},
        },
    )
    operations_result = run_script(
        SOCKET_SCRIPT,
        "operations",
        "--spec-file",
        str(spec),
        "--search",
        "alert",
        "--method",
        "GET",
    )

    assert operations_result.returncode == 0, operations_result.stderr
    operations = as_list(as_dict(json.loads(operations_result.stdout))["operations"])
    assert len(operations) == 1
    assert as_dict(operations[0])["operation_id"] == "listAlerts"


def test_socket_operation_write_preview_and_raw_guards(tmp_path: Path) -> None:
    """Preview a Socket write and reject unsafe raw request inputs."""
    spec = tmp_path / "socket-openapi.json"
    write_openapi(
        spec,
        {"/orgs/{org}/policies": {"post": {"operationId": "createPolicy", "summary": "Create policy"}}},
    )
    preview_result = run_script(
        SOCKET_SCRIPT,
        "request",
        "--spec-file",
        str(spec),
        "--operation-id",
        "createPolicy",
        "--path",
        "org=nick2bad4u",
        "--body-json",
        '{"enabled":true,"token":"do-not-print"}',
    )

    assert preview_result.returncode == 0, preview_result.stderr
    assert "do-not-print" not in preview_result.stdout
    preview = as_dict(json.loads(preview_result.stdout))
    assert preview["dryRun"] is True
    assert preview["method"] == "POST"
    assert as_dict(preview["body"]).get("token") == REDACTED

    failures = (
        ("https://example.com/v0/alerts", "origin must match"),
        ("/alerts", "token-like query parameter", "--query", "access_token=bad"),
        ("relative", "Relative endpoint must start"),
    )
    for case in failures:
        endpoint, expected, *extra = case
        result = run_script(SOCKET_SCRIPT, "request", endpoint, "--dry-run", *extra)
        assert result.returncode == 1
        assert expected in result.stderr


def test_snyk_context_operations_and_mutation_preview(tmp_path: Path) -> None:
    """Inspect Snyk context and preview a JSON:API mutation from local schema data."""
    secret = TEST_CREDENTIAL
    environment = clean_environment(TEST_SNYK_TOKEN=secret)
    context_result = run_script(
        SNYK_SCRIPT,
        "context",
        "--base-url",
        "https://api.eu.snyk.io/rest",
        "--api-version",
        "2024-10-15",
        "--token-env",
        "TEST_SNYK_TOKEN",
        environment=environment,
    )

    assert context_result.returncode == 0, context_result.stderr
    assert secret not in context_result.stdout
    context = as_dict(json.loads(context_result.stdout))
    assert context["baseUrl"] == "https://api.eu.snyk.io/rest"
    assert context.get("token") == "configured"

    spec = tmp_path / "snyk-openapi.json"
    write_openapi(
        spec,
        {
            "/orgs/{org_id}/projects": {"get": {"operationId": "listOrgProjects", "summary": "List projects"}},
            "/orgs/{org_id}/settings": {"patch": {"operationId": "updateOrgSettings", "summary": "Update settings"}},
        },
    )
    operations_result = run_script(
        SNYK_SCRIPT,
        "operations",
        "--spec-file",
        str(spec),
        "--search",
        "projects",
        "--method",
        "GET",
    )
    assert operations_result.returncode == 0, operations_result.stderr
    operations = as_list(as_dict(json.loads(operations_result.stdout))["operations"])
    assert as_dict(operations[0])["operation_id"] == "listOrgProjects"

    preview_result = run_script(
        SNYK_SCRIPT,
        "request",
        "--spec-file",
        str(spec),
        "--operation-id",
        "updateOrgSettings",
        "--path",
        "org_id=abc-123",
        "--body-json",
        '{"data":{"type":"org_settings","attributes":{"enabled":true}}}',
    )
    assert preview_result.returncode == 0, preview_result.stderr
    preview = as_dict(json.loads(preview_result.stdout))
    assert preview["dryRun"] is True
    assert preview["method"] == "PATCH"
    assert "version=2024-10-15" in str(preview["url"])


def test_snyk_rejects_region_query_and_body_mistakes() -> None:
    """Keep Snyk raw requests in-region and free of credential query data."""
    cases = (
        ("https://api.eu.snyk.io/rest/orgs", "origin must match"),
        ("/orgs", "token-like query parameter", "--query", "api_key=bad"),
        ("/orgs", "conflicts with --api-version", "--query", "version=2023-01-01"),
        ("/orgs", "GET requests must not include", "--body-json", "{}"),
    )
    for case in cases:
        endpoint, expected, *extra = case
        result = run_script(SNYK_SCRIPT, "request", endpoint, "--dry-run", *extra)
        assert result.returncode == 1
        assert expected in result.stderr


def test_wakatime_auth_context_and_wrapped_read_plans() -> None:
    """Resolve WakaTime OAuth context and preview privacy-sensitive read ranges."""
    secret = TEST_CREDENTIAL
    environment = clean_environment(WAKATIME_ACCESS_TOKEN=secret)
    api_key_environment = "WAKATIME_API" + "_KEY"
    environment[api_key_environment] = "fallback-key"
    context_result = run_script(WAKATIME_SCRIPT, "context", environment=environment)

    assert context_result.returncode == 0, context_result.stderr
    assert secret not in context_result.stdout
    context = as_dict(json.loads(context_result.stdout))
    assert context["authentication"] == "oauth"
    assert context["credentialEnvironment"] == "WAKATIME_ACCESS_TOKEN"

    summaries_result = run_script(
        WAKATIME_SCRIPT,
        "summaries",
        "--start",
        "2026-08-01",
        "--end",
        "2026-08-07",
        "--project",
        "codex-skills",
        "--branches",
        "main",
        "--dry-run",
    )
    assert summaries_result.returncode == 0, summaries_result.stderr
    summary = as_dict(json.loads(summaries_result.stdout))
    query = as_dict(summary["query"])
    assert query == {
        "branches": "main",
        "end": "2026-08-07",
        "project": "codex-skills",
        "start": "2026-08-01",
    }

    commands = (
        ("stats", "--range", "last_7_days"),
        ("projects", "--search", "codex"),
        ("goals",),
        ("durations", "--date", "2026-08-01", "--project", "codex-skills"),
        ("heartbeats", "--date", "2026-08-01"),
        ("data-dumps",),
        ("user",),
    )
    for command in commands:
        result = run_script(WAKATIME_SCRIPT, *command, "--dry-run")
        assert result.returncode == 0, result.stderr
        assert as_dict(json.loads(result.stdout))["dryRun"] is True


def test_wakatime_mutation_preview_and_validation_errors(tmp_path: Path) -> None:
    """Redact WakaTime request bodies and reject invalid dates, URLs, and query data."""
    body = tmp_path / "heartbeats.json"
    _ = body.write_text('{"secret":"private","entity":"file.py"}', encoding="utf-8")
    preview_result = run_script(
        WAKATIME_SCRIPT,
        "request",
        "/users/current/heartbeats.bulk",
        "--method",
        "POST",
        "--body-file",
        str(body),
    )
    assert preview_result.returncode == 0, preview_result.stderr
    assert "private" not in preview_result.stdout
    assert as_dict(as_dict(json.loads(preview_result.stdout))["body"]).get("secret") == REDACTED

    cases = (
        (
            "summaries",
            "--start",
            "2026-08-08",
            "--end",
            "2026-08-01",
            "--dry-run",
            "--end must not be earlier",
        ),
        ("stats", "--range", "bad/range", "--dry-run", "unsupported characters"),
        ("request", "https://example.com/api/v1/users/current", "--dry-run", "origin must match"),
        ("request", "/users/current", "--query", "token=bad", "--dry-run", "sensitive query parameter"),
    )
    for case in cases:
        *arguments, expected = case
        result = run_script(WAKATIME_SCRIPT, *arguments)
        assert result.returncode == 1
        assert expected in result.stderr


def stepsecurity_spec(path: Path) -> None:
    """Write an OpenAPI fixture with tenant inference and required inputs."""
    write_openapi(
        path,
        {
            "/organizations/{organization}/detections": {
                "get": {
                    "operationId": "listDetections",
                    "summary": "List runtime detections",
                    "tags": ["Detections"],
                    "parameters": [
                        {"name": "organization", "in": "path", "required": True},
                        {"name": "limit", "in": "query", "required": False},
                    ],
                }
            },
            "/organizations/{organization}/suppressions": {
                "post": {
                    "operationId": "createSuppression",
                    "summary": "Create suppression",
                    "parameters": [{"name": "organization", "in": "path", "required": True}],
                    "requestBody": {"required": True, "content": {"application/json": {}}},
                }
            },
        },
    )


def test_stepsecurity_context_operations_and_tenant_inference(tmp_path: Path) -> None:
    """Inspect StepSecurity context and build a tenant-scoped read request from OpenAPI."""
    secret = TEST_CREDENTIAL
    environment = clean_environment(STEP_SECURITY_API_KEY=secret, STEP_SECURITY_CUSTOMER="customer-slug")
    context_result = run_script(
        STEPSECURITY_SCRIPT,
        "context",
        "--org",
        "Nick2bad4u",
        "--repo",
        "Nick2bad4u/codex-skills",
        environment=environment,
    )
    assert context_result.returncode == 0, context_result.stderr
    assert secret not in context_result.stdout
    context = as_dict(json.loads(context_result.stdout))
    assert context["credential_present"] is True
    assert context["credential_source"] == "STEP_SECURITY_API_KEY"
    assert context["customer"] == "customer-slug"

    spec = tmp_path / "stepsecurity-openapi.json"
    stepsecurity_spec(spec)
    operations_result = run_script(
        STEPSECURITY_SCRIPT,
        "operations",
        "--spec-file",
        str(spec),
        "--match",
        "detection",
    )
    assert operations_result.returncode == 0, operations_result.stderr
    operations = as_list(json.loads(operations_result.stdout))
    assert as_dict(operations[0])["operation_id"] == "listDetections"

    request_result = run_script(
        STEPSECURITY_SCRIPT,
        "request",
        "--spec-file",
        str(spec),
        "--operation-id",
        "listDetections",
        "--org",
        "Nick2bad4u",
        "--query",
        "limit=25",
        "--dry-run",
        environment=environment,
    )
    assert request_result.returncode == 0, request_result.stderr
    preview = as_dict(as_dict(json.loads(request_result.stdout))["request"])
    assert "/organizations/Nick2bad4u/detections" in str(preview["url"])
    assert "limit=25" in str(preview["url"])
    assert as_dict(preview["headers"])["Authorization"] == REDACTED


def test_stepsecurity_write_preview_and_safety_errors(tmp_path: Path) -> None:
    """Preview a redacted suppression and reject unsafe StepSecurity request shapes."""
    environment = clean_environment(STEP_SECURITY_API_KEY=TEST_CREDENTIAL)
    spec = tmp_path / "stepsecurity-openapi.json"
    stepsecurity_spec(spec)
    preview_result = run_script(
        STEPSECURITY_SCRIPT,
        "request",
        "--spec-file",
        str(spec),
        "--operation-id",
        "createSuppression",
        "--org",
        "Nick2bad4u",
        "--body",
        '{"reason":"test","secret":"do-not-print"}',
        environment=environment,
    )
    assert preview_result.returncode == 0, preview_result.stderr
    assert "do-not-print" not in preview_result.stdout
    preview = as_dict(json.loads(preview_result.stdout))
    assert preview["executed"] is False
    request = as_dict(preview["request"])
    assert request["method"] == "POST"
    assert as_dict(request["body"]).get("secret") == REDACTED

    cases = (
        ("--endpoint", "https://example.com/v1/detections", "--dry-run", "production origin"),
        ("--endpoint", "/detections", "--query", "api_key=bad", "--dry-run", "Credential-like query"),
        ("--endpoint", "/../detections", "--dry-run", "path traversal"),
        ("--endpoint", "/detections", "--execute", "--dry-run", "mutually exclusive"),
        ("--endpoint", "/detections", "--max-pages", "0", "--dry-run", "at least 1"),
    )
    for case in cases:
        *arguments, expected = case
        result = run_script(STEPSECURITY_SCRIPT, "request", *arguments, environment=environment)
        assert result.returncode == ARGPARSE_USAGE_ERROR
        assert expected in result.stderr


def test_stepsecurity_openapi_validation_errors(tmp_path: Path) -> None:
    """Reject missing bodies, unknown inputs, unresolved references, and invalid specifications."""
    environment = clean_environment(STEP_SECURITY_API_KEY=TEST_CREDENTIAL)
    spec = tmp_path / "stepsecurity-openapi.json"
    stepsecurity_spec(spec)
    cases = (
        (
            "--spec-file",
            str(spec),
            "--operation-id",
            "createSuppression",
            "--org",
            "Nick2bad4u",
            "requires a request body",
        ),
        (
            "--spec-file",
            str(spec),
            "--operation-id",
            "listDetections",
            "--org",
            "Nick2bad4u",
            "--query",
            "unknown=value",
            "Unknown query parameter",
        ),
        (
            "--spec-file",
            str(spec),
            "--operation-id",
            "missingOperation",
            "OpenAPI operation not found",
        ),
    )
    for case in cases:
        *arguments, expected = case
        result = run_script(STEPSECURITY_SCRIPT, "request", *arguments, environment=environment)
        assert result.returncode == ARGPARSE_USAGE_ERROR
        assert expected in result.stderr

    invalid_spec = tmp_path / "invalid.json"
    _ = invalid_spec.write_text('{"openapi":"2.0","paths":{}}', encoding="utf-8")
    result = run_script(STEPSECURITY_SCRIPT, "operations", "--spec-file", str(invalid_spec))
    assert result.returncode == ARGPARSE_USAGE_ERROR
    assert "must use OpenAPI 3" in result.stderr
