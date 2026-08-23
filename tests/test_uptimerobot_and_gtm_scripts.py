# Copyright (c) 2026 Nick2bad4u
"""Behavioral tests for UptimeRobot and Google Tag Manager helpers."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import cast

REPO_ROOT = Path(__file__).resolve().parents[1]
UPTIMEROBOT_SCRIPT = REPO_ROOT / "skills" / "uptimerobot-management" / "scripts" / "manage_uptimerobot.py"
GTM_SCRIPT = REPO_ROOT / "skills" / "google-tag-manager-management" / "scripts" / "manage_google_tag_manager.py"
TEST_CREDENTIAL = "not-a-real-service-credential"
REDACTED = "<redacted>"


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
    """Build a subprocess environment without real service credentials."""
    environment = os.environ.copy()
    for name in (
        "GOOGLE_TAG_MANAGER_ACCESS_TOKEN",
        "GTM_ACCESS_TOKEN",
        "UPTIMEROBOT_API_KEY",
        "UPTIMEROBOT_READ_ONLY_API_KEY",
    ):
        _ = environment.pop(name, None)
    environment.update(values)
    return environment


def run_script(
    script: Path,
    *arguments: str,
    environment: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run one fixed repository-owned helper without a shell."""
    return subprocess.run(  # noqa: S603  # Fixed interpreter and repository-owned script.
        [sys.executable, str(script), *arguments],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        env=environment or clean_environment(),
        stdin=subprocess.DEVNULL,
        text=True,
    )


def write_uptimerobot_openapi(path: Path) -> None:
    """Write a deterministic UptimeRobot OpenAPI JSON fixture."""
    payload = {
        "openapi": "3.0.0",
        "paths": {
            "/monitors": {
                "get": {
                    "operationId": "MonitorsController_list",
                    "summary": "List monitors",
                    "tags": ["Monitors"],
                }
            },
            "/monitors/{id}": {
                "patch": {
                    "operationId": "MonitorsController_update",
                    "summary": "Update monitor",
                    "tags": ["Monitors"],
                }
            },
            "/monitors/{id}/pause": {
                "post": {
                    "operationId": "MonitorsController_pause",
                    "summary": "Pause monitor",
                    "tags": ["Monitors"],
                }
            },
        },
    }
    _ = path.write_text(json.dumps(payload), encoding="utf-8")


def write_gtm_discovery(path: Path) -> None:
    """Write a nested Tag Manager v2 Discovery fixture."""
    payload = {
        "name": "tagmanager",
        "version": "v2",
        "resources": {
            "accounts": {
                "methods": {
                    "list": {
                        "id": "tagmanager.accounts.list",
                        "path": "tagmanager/v2/accounts",
                        "httpMethod": "GET",
                        "description": "List accounts",
                        "parameters": {"pageToken": {"location": "query"}},
                        "scopes": ["https://www.googleapis.com/auth/tagmanager.readonly"],
                    }
                },
                "resources": {
                    "containers": {
                        "resources": {
                            "workspaces": {
                                "methods": {
                                    "getStatus": {
                                        "id": "tagmanager.accounts.containers.workspaces.getStatus",
                                        "path": "tagmanager/v2/{+path}/status",
                                        "httpMethod": "GET",
                                        "parameters": {"path": {"location": "path", "required": True}},
                                        "scopes": ["https://www.googleapis.com/auth/tagmanager.readonly"],
                                    },
                                    "create_version": {
                                        "id": "tagmanager.accounts.containers.workspaces.create_version",
                                        "path": "tagmanager/v2/{+path}:create_version",
                                        "httpMethod": "POST",
                                        "parameters": {"path": {"location": "path", "required": True}},
                                        "request": {"$ref": "CreateVersionRequest"},
                                        "scopes": ["https://www.googleapis.com/auth/tagmanager.edit.containerversions"],
                                    },
                                },
                                "resources": {
                                    "tags": {
                                        "methods": {
                                            "update": {
                                                "id": "tagmanager.accounts.containers.workspaces.tags.update",
                                                "path": "tagmanager/v2/{+path}",
                                                "httpMethod": "PUT",
                                                "parameters": {
                                                    "path": {"location": "path", "required": True},
                                                    "fingerprint": {"location": "query"},
                                                },
                                                "request": {"$ref": "Tag"},
                                                "scopes": [
                                                    "https://www.googleapis.com/auth/tagmanager.edit.containers"
                                                ],
                                            }
                                        }
                                    }
                                },
                            },
                            "versions": {
                                "methods": {
                                    "publish": {
                                        "id": "tagmanager.accounts.containers.versions.publish",
                                        "path": "tagmanager/v2/{+path}:publish",
                                        "httpMethod": "POST",
                                        "parameters": {
                                            "path": {"location": "path", "required": True},
                                            "fingerprint": {"location": "query"},
                                        },
                                        "scopes": ["https://www.googleapis.com/auth/tagmanager.publish"],
                                    }
                                }
                            },
                        }
                    }
                },
            }
        },
    }
    _ = path.write_text(json.dumps(payload), encoding="utf-8")


def test_uptimerobot_context_operations_and_credential_selection(tmp_path: Path) -> None:
    """Report credential sources safely and filter a local operation contract."""
    environment = clean_environment(TEST_UPTIME_READ=TEST_CREDENTIAL, TEST_UPTIME_MAIN=f"{TEST_CREDENTIAL}-main")
    context_result = run_script(
        UPTIMEROBOT_SCRIPT,
        "context",
        "--read-token-env",
        "TEST_UPTIME_READ",
        "--main-token-env",
        "TEST_UPTIME_MAIN",
        environment=environment,
    )
    assert context_result.returncode == 0, context_result.stderr
    assert TEST_CREDENTIAL not in context_result.stdout
    context = as_dict(json.loads(context_result.stdout))
    assert as_dict(context["readCredential"])["environment"] == "TEST_UPTIME_READ"
    assert as_dict(context["mainCredential"])["environment"] == "TEST_UPTIME_MAIN"

    spec = tmp_path / "uptimerobot-openapi.json"
    write_uptimerobot_openapi(spec)
    operations_result = run_script(
        UPTIMEROBOT_SCRIPT,
        "operations",
        "--spec-file",
        str(spec),
        "--search",
        "pause",
        "--method",
        "POST",
    )
    assert operations_result.returncode == 0, operations_result.stderr
    operations = as_list(as_dict(json.loads(operations_result.stdout))["operations"])
    assert len(operations) == 1
    assert as_dict(operations[0])["operation_id"] == "MonitorsController_pause"


def test_uptimerobot_write_preview_redaction_and_guards(tmp_path: Path) -> None:
    """Preview a main-key write, redact monitor secrets, and reject unsafe input."""
    spec = tmp_path / "uptimerobot-openapi.json"
    write_uptimerobot_openapi(spec)
    environment = clean_environment(TEST_UPTIME_MAIN=TEST_CREDENTIAL)
    preview_result = run_script(
        UPTIMEROBOT_SCRIPT,
        "request",
        "--spec-file",
        str(spec),
        "--operation-id",
        "MonitorsController_update",
        "--path",
        "id=42",
        "--body-json",
        '{"friendlyName":"demo","apiKey":"do-not-print","customHttpHeaders":{"X-Key":"private"}}',
        "--main-token-env",
        "TEST_UPTIME_MAIN",
        environment=environment,
    )
    assert preview_result.returncode == 0, preview_result.stderr
    assert "do-not-print" not in preview_result.stdout
    assert "private" not in preview_result.stdout
    preview = as_dict(json.loads(preview_result.stdout))
    request = as_dict(preview["request"])
    assert request["method"] == "PATCH"
    assert as_dict(request["body"])["apiKey"] == REDACTED
    assert preview["credentialEnvironment"] == "TEST_UPTIME_MAIN"

    delete_preview_result = run_script(
        UPTIMEROBOT_SCRIPT,
        "request",
        "/monitors/42",
        "--method",
        "DELETE",
        "--main-token-env",
        "TEST_UPTIME_MAIN",
        environment=environment,
    )
    assert delete_preview_result.returncode == 0, delete_preview_result.stderr
    delete_preview = as_dict(json.loads(delete_preview_result.stdout))
    assert delete_preview["confirmationRequired"] is True
    assert delete_preview["confirmationValue"] == "DELETE /monitors/42"

    delete_without_confirmation = run_script(
        UPTIMEROBOT_SCRIPT,
        "request",
        "/monitors/42",
        "--method",
        "DELETE",
        "--send",
        "--main-token-env",
        "TEST_UPTIME_MAIN",
        environment=environment,
    )
    assert delete_without_confirmation.returncode == 1
    assert "requires --confirm" in delete_without_confirmation.stderr

    read_preview = run_script(
        UPTIMEROBOT_SCRIPT,
        "request",
        "/monitors",
        "--dry-run",
        "--read-token-env",
        "TEST_UPTIME_READ",
        environment=clean_environment(TEST_UPTIME_READ=TEST_CREDENTIAL),
    )
    assert read_preview.returncode == 0, read_preview.stderr
    assert as_dict(json.loads(read_preview.stdout))["credentialEnvironment"] == "TEST_UPTIME_READ"

    cases = (
        ("https://example.com/v3/monitors", "origin must match"),
        ("/../monitors", "path traversal"),
        ("/monitors", "credential-like query", "--query", "api_key=bad"),
        ("relative", "Relative endpoint must start"),
    )
    for case in cases:
        endpoint, expected, *extra = case
        result = run_script(UPTIMEROBOT_SCRIPT, "request", endpoint, "--dry-run", *extra)
        assert result.returncode == 1
        assert expected in result.stderr


def test_gtm_context_discovery_and_workspace_path(tmp_path: Path) -> None:
    """Discover nested GTM operations and expand a reserved workspace path safely."""
    environment = clean_environment(TEST_GTM_TOKEN=TEST_CREDENTIAL)
    context_result = run_script(
        GTM_SCRIPT,
        "context",
        "--token-env",
        "TEST_GTM_TOKEN",
        environment=environment,
    )
    assert context_result.returncode == 0, context_result.stderr
    assert TEST_CREDENTIAL not in context_result.stdout
    context = as_dict(json.loads(context_result.stdout))
    assert as_dict(context["accessToken"])["environment"] == "TEST_GTM_TOKEN"

    discovery = tmp_path / "tagmanager-v2.json"
    write_gtm_discovery(discovery)
    operations_result = run_script(
        GTM_SCRIPT,
        "operations",
        "--discovery-file",
        str(discovery),
        "--search",
        "getStatus",
    )
    assert operations_result.returncode == 0, operations_result.stderr
    operations = as_list(as_dict(json.loads(operations_result.stdout))["operations"])
    assert as_dict(operations[0])["operation_id"] == "tagmanager.accounts.containers.workspaces.getStatus"

    preview_result = run_script(
        GTM_SCRIPT,
        "request",
        "--discovery-file",
        str(discovery),
        "--operation-id",
        "tagmanager.accounts.containers.workspaces.getStatus",
        "--path",
        "path=accounts/1/containers/2/workspaces/3",
        "--dry-run",
    )
    assert preview_result.returncode == 0, preview_result.stderr
    request = as_dict(as_dict(json.loads(preview_result.stdout))["request"])
    assert str(request["url"]).endswith("/accounts/1/containers/2/workspaces/3/status")
    assert "tagmanager.readonly" in str(request["requiredScopes"])


def test_gtm_mutation_preview_confirmation_and_guards(tmp_path: Path) -> None:
    """Redact GTM writes and require exact confirmation for publication."""
    discovery = tmp_path / "tagmanager-v2.json"
    write_gtm_discovery(discovery)
    tag_body = tmp_path / "tag.json"
    _ = tag_body.write_text('{"name":"demo","clientSecret":"do-not-print"}', encoding="utf-8")
    preview_result = run_script(
        GTM_SCRIPT,
        "request",
        "--discovery-file",
        str(discovery),
        "--operation-id",
        "tagmanager.accounts.containers.workspaces.tags.update",
        "--path",
        "path=accounts/1/containers/2/workspaces/3/tags/4",
        "--query",
        "fingerprint=abc123",
        "--body-file",
        str(tag_body),
    )
    assert preview_result.returncode == 0, preview_result.stderr
    assert "do-not-print" not in preview_result.stdout
    request = as_dict(as_dict(json.loads(preview_result.stdout))["request"])
    assert as_dict(request["body"])["clientSecret"] == REDACTED

    publish_arguments = (
        "request",
        "--discovery-file",
        str(discovery),
        "--operation-id",
        "tagmanager.accounts.containers.versions.publish",
        "--path",
        "path=accounts/1/containers/2/versions/9",
        "--query",
        "fingerprint=abc123",
    )
    publish_preview = run_script(GTM_SCRIPT, *publish_arguments)
    assert publish_preview.returncode == 0, publish_preview.stderr
    publish = as_dict(json.loads(publish_preview.stdout))
    assert publish["confirmationRequired"] is True
    assert publish["confirmationValue"] == "tagmanager.accounts.containers.versions.publish"

    blocked_send = run_script(
        GTM_SCRIPT,
        *publish_arguments,
        "--send",
        "--token-env",
        "TEST_GTM_TOKEN",
        environment=clean_environment(TEST_GTM_TOKEN=TEST_CREDENTIAL),
    )
    assert blocked_send.returncode == 1
    assert "requires --confirm" in blocked_send.stderr
    assert TEST_CREDENTIAL not in blocked_send.stderr

    cases = (
        ("https://example.com/tagmanager/v2/accounts", "origin must match"),
        ("/../accounts", "path traversal"),
        ("/accounts", "credential-like query", "--query", "oauth_token=bad"),
        ("relative", "Relative endpoint must start"),
    )
    for case in cases:
        endpoint, expected, *extra = case
        result = run_script(GTM_SCRIPT, "request", endpoint, "--dry-run", *extra)
        assert result.returncode == 1
        assert expected in result.stderr
