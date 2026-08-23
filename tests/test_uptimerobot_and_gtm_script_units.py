# Copyright (c) 2026 Nick2bad4u
"""Focused unit tests for UptimeRobot and GTM helper boundaries."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, cast

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_PAGE_COUNT = 2
HTTP_OK = 200

type JsonValue = bool | int | float | str | list[JsonValue] | dict[str, JsonValue] | None


class OperationView(Protocol):
    """Structural operation metadata used by pure unit assertions."""

    method: str
    operation_id: str
    path: str


class RequestPlanView(Protocol):
    """Structural request-plan view shared by both helper modules."""

    high_risk: bool
    method: str
    operation_id: str | None
    query: dict[str, str]
    supports_page_token: bool
    url: str


def load_script_module(name: str, relative_path: str) -> ModuleType:
    """Load a repository-owned helper without running its CLI entry point."""
    path = REPO_ROOT / relative_path
    specification = importlib.util.spec_from_file_location(name, path)
    if specification is None or specification.loader is None:
        raise RuntimeError(f"Could not load test module: {path}")
    module = importlib.util.module_from_spec(specification)
    sys.modules[name] = module
    specification.loader.exec_module(module)
    return module


UPTIMEROBOT = load_script_module(
    "test_manage_uptimerobot",
    "skills/uptimerobot-management/scripts/manage_uptimerobot.py",
)
GTM = load_script_module(
    "test_manage_google_tag_manager",
    "skills/google-tag-manager-management/scripts/manage_google_tag_manager.py",
)


def function(module: ModuleType, name: str) -> object:
    """Retrieve one dynamically loaded helper member for an explicit cast."""
    return getattr(module, name)


def error_type(module: ModuleType, name: str) -> type[Exception]:
    """Retrieve one helper's user-facing exception type."""
    return cast("type[Exception]", function(module, name))


def embedded_credentials_url(host_and_path: str) -> str:
    """Build a deliberately invalid URL without a credential literal."""
    return "https://user" + chr(58) + "placeholder@" + host_and_path


def test_uptimerobot_url_environment_and_pair_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Lock UptimeRobot credentials and requests to approved inputs."""
    helper_error = error_type(UPTIMEROBOT, "UptimeRobotCliError")
    sanitize = cast("Callable[[str], str]", function(UPTIMEROBOT, "sanitize_base_url"))
    spec_url = cast("Callable[[str], str]", function(UPTIMEROBOT, "validate_spec_url"))
    resolve = cast(
        "Callable[[list[str], tuple[str, ...]], object | None]",
        function(UPTIMEROBOT, "resolve_credential"),
    )
    parse_pairs = cast(
        "Callable[[list[str]], dict[str, str]]",
        lambda values: function(UPTIMEROBOT, "parse_pairs")(values, label="query"),  # type: ignore[operator]
    )
    operation_type = cast("Callable[..., object]", function(UPTIMEROBOT, "OpenApiOperation"))
    high_risk = cast("Callable[[object], bool]", function(UPTIMEROBOT, "operation_is_high_risk"))
    confirmation = cast("Callable[[str, str], str]", function(UPTIMEROBOT, "raw_confirmation_value"))
    assert sanitize("https://api.uptimerobot.com/v3/") == "https://api.uptimerobot.com/v3"
    assert spec_url("https://cdn.uptimerobot.com/api/openapi.yaml") == ("https://cdn.uptimerobot.com/api/openapi.yaml")
    for value in (
        "http://api.uptimerobot.com/v3",
        embedded_credentials_url("api.uptimerobot.com/v3"),
        "https://api.uptimerobot.com/v2",
        "https://example.com/v3",
    ):
        with pytest.raises(helper_error):
            _ = sanitize(value)
    monkeypatch.setenv("TEST_UPTIME", "credential")
    assert resolve(["TEST_UPTIME"], ()) is not None
    with pytest.raises(helper_error, match="Invalid credential environment"):
        _ = resolve(["bad-name"], ())
    assert parse_pairs(["limit=200"]) == {"limit": "200"}
    for values in (["bad"], ["limit=1", "limit=2"], ["api_key=bad"]):
        with pytest.raises(helper_error):
            _ = parse_pairs(values)
    assert high_risk(
        operation_type(
            deprecated=False,
            method="DELETE",
            operation_id="MonitorsController_delete",
            path="/monitors/{id}",
            summary="Delete a monitor",
            tags=("Monitors",),
        )
    )
    assert high_risk(
        operation_type(
            deprecated=False,
            method="POST",
            operation_id="BulkMonitorsController_bulkPause",
            path="/monitors/bulk/pause",
            summary="Pause monitors",
            tags=("Monitors - Bulk Operations",),
        )
    )
    assert confirmation("DELETE", "https://api.uptimerobot.com/v3/monitors/42") == "DELETE /monitors/42"


def test_uptimerobot_yaml_paths_pagination_and_redaction() -> None:
    """Parse the live YAML shape and guard paths, cursors, and secret fields."""
    helper_error = error_type(UPTIMEROBOT, "UptimeRobotCliError")
    parse_yaml = cast("Callable[[str], list[OperationView]]", function(UPTIMEROBOT, "parse_yaml_operations"))
    fill_path = cast("Callable[[str, dict[str, str]], str]", function(UPTIMEROBOT, "fill_path"))
    endpoint = cast("Callable[[str, str], str]", function(UPTIMEROBOT, "validated_endpoint_url"))
    next_url = cast("Callable[[str, str, str], str]", function(UPTIMEROBOT, "validated_next_url"))
    redact = cast("Callable[[JsonValue, tuple[str, ...]], JsonValue]", function(UPTIMEROBOT, "redact_json"))
    next_link = cast("Callable[[JsonValue], str | None]", function(UPTIMEROBOT, "next_link"))
    yaml_text = """openapi: 3.0.0
paths:
  /monitors/{id}:
    get:
      operationId: MonitorsController_get
      summary: "Get monitor"
      tags:
        - Monitors
components:
  schemas: {}
"""
    operations = parse_yaml(yaml_text)
    assert operations[0].operation_id == "MonitorsController_get"
    assert fill_path("/monitors/{id}", {"id": "a/b"}) == "/monitors/a%2Fb"
    with pytest.raises(helper_error, match="Missing path"):
        _ = fill_path("/monitors/{id}", {})
    with pytest.raises(helper_error, match="Unused path"):
        _ = fill_path("/monitors", {"id": "1"})
    base = "https://api.uptimerobot.com/v3"
    assert endpoint(base, "/monitors") == f"{base}/monitors"
    assert next_url(base, f"{base}/monitors?limit=1", "?cursor=2").endswith("/monitors?cursor=2")
    assert next_url(base, f"{base}/monitors", "/v3/monitors?cursor=3").endswith("cursor=3")
    for value in ("/v3/../monitors", "https://example.com/v3/monitors", "/v3/monitors?token=bad"):
        with pytest.raises(helper_error):
            _ = next_url(base, f"{base}/monitors", value)
    credential_url = "https://" + "user:pass@example.com/health?token=private&ok=1"
    assert redact(
        {
            "apiKey": "x",
            "items": [{"ok": True}],
            "echo": "credential",
            "url": credential_url,
        },
        ("credential",),
    ) == {
        "apiKey": "<redacted>",
        "items": [{"ok": True}],
        "echo": "<redacted>",
        "url": "https://<redacted>@example.com/health?token=<redacted>&ok=1",
    }
    assert next_link({"nextLink": "/v3/monitors?cursor=4"}) == "/v3/monitors?cursor=4"
    assert next_link({"nextLink": None}) is None


def test_uptimerobot_body_response_and_argument_bounds(tmp_path: Path) -> None:
    """Cover UptimeRobot JSON input, response decoding, and numeric caps."""
    helper_error = error_type(UPTIMEROBOT, "UptimeRobotCliError")
    load_body = cast("Callable[[argparse.Namespace], JsonValue]", function(UPTIMEROBOT, "load_body"))
    response_payload = cast("Callable[[bytes, str], JsonValue]", function(UPTIMEROBOT, "response_payload"))
    validate = cast("Callable[[argparse.Namespace], None]", function(UPTIMEROBOT, "validate_arguments"))
    body_file = tmp_path / "body.json"
    _ = body_file.write_text('{"ok":true}', encoding="utf-8")
    assert load_body(argparse.Namespace(body_json=None, body_file=body_file)) == {"ok": True}
    assert load_body(argparse.Namespace(body_json="[1,2]", body_file=None)) == [1, 2]
    invalid_body_arguments = argparse.Namespace(body_json="bad", body_file=None)
    with pytest.raises(helper_error, match="valid JSON"):
        _ = load_body(invalid_body_arguments)
    assert response_payload(b'{"ok":true}', "application/json") == {"ok": True}
    assert response_payload(b"plain", "text/plain") == "plain"
    assert response_payload(b"", "application/json") is None
    validate(argparse.Namespace(timeout=1, retries=0, command="request", max_pages=1))
    for arguments in (
        argparse.Namespace(timeout=0, retries=0, command="context"),
        argparse.Namespace(timeout=1, retries=-1, command="context"),
        argparse.Namespace(timeout=1, retries=0, command="request", max_pages=0),
    ):
        with pytest.raises(helper_error):
            validate(arguments)


def test_gtm_discovery_path_query_and_high_risk_validation() -> None:
    """Parse GTM Discovery methods and enforce reserved paths and confirmation classes."""
    helper_error = error_type(GTM, "GoogleTagManagerCliError")
    sanitize = cast("Callable[[str], str]", function(GTM, "sanitize_base_url"))
    discovery_url = cast("Callable[[str], str]", function(GTM, "validate_discovery_url"))
    parse_operations = cast(
        "Callable[[dict[str, JsonValue]], list[OperationView]]",
        function(GTM, "parse_operations"),
    )
    fill_path = cast("Callable[[str, dict[str, str]], str]", function(GTM, "fill_path"))
    endpoint = cast("Callable[[str, str], str]", function(GTM, "validated_endpoint_url"))
    high_risk = cast("Callable[[object], bool]", function(GTM, "operation_is_high_risk"))
    parse_method = cast("Callable[[JsonValue], object | None]", function(GTM, "parse_method"))
    assert sanitize("https://tagmanager.googleapis.com/tagmanager/v2/") == (
        "https://tagmanager.googleapis.com/tagmanager/v2"
    )
    assert discovery_url("https://tagmanager.googleapis.com/$discovery/rest?version=v2").endswith("version=v2")
    for value in (
        "http://tagmanager.googleapis.com/tagmanager/v2",
        embedded_credentials_url("tagmanager.googleapis.com/tagmanager/v2"),
        "https://tagmanager.googleapis.com/tagmanager/v1",
    ):
        with pytest.raises(helper_error):
            _ = sanitize(value)
    method: dict[str, JsonValue] = {
        "id": "tagmanager.accounts.containers.versions.publish",
        "path": "tagmanager/v2/{+path}:publish",
        "httpMethod": "POST",
        "parameters": {"path": {"location": "path", "required": True}},
        "scopes": ["publish"],
    }
    payload: dict[str, JsonValue] = {"resources": {"accounts": {"methods": {"publish": method}}}}
    operations = parse_operations(payload)
    assert operations[0].operation_id.endswith("publish")
    operation = parse_method(method)
    assert operation is not None
    assert high_risk(operation)
    assert fill_path("tagmanager/v2/{+path}:publish", {"path": "accounts/1/containers/2/versions/3"}) == (
        "tagmanager/v2/accounts/1/containers/2/versions/3:publish"
    )
    base = "https://tagmanager.googleapis.com/tagmanager/v2"
    assert endpoint(base, "tagmanager/v2/accounts") == f"{base}/accounts"
    assert endpoint(base, "/accounts") == f"{base}/accounts"
    for value in ("https://example.com/tagmanager/v2/accounts", "/../accounts", "relative"):
        with pytest.raises(helper_error):
            _ = endpoint(base, value)


def test_gtm_json_redaction_pagination_and_bounds(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cover GTM token resolution, page tokens, JSON redaction, and safety bounds."""
    helper_error = error_type(GTM, "GoogleTagManagerCliError")
    resolve = cast("Callable[[list[str]], object | None]", function(GTM, "resolve_credential"))
    redact = cast("Callable[[JsonValue, str | None], JsonValue]", function(GTM, "redact_json"))
    next_token = cast("Callable[[JsonValue], str | None]", function(GTM, "next_page_token"))
    response_payload = cast("Callable[[bytes, str], JsonValue]", function(GTM, "response_payload"))
    validate = cast("Callable[[argparse.Namespace], None]", function(GTM, "validate_arguments"))
    monkeypatch.setenv("TEST_GTM", "credential")
    assert resolve(["TEST_GTM"]) is not None
    with pytest.raises(helper_error, match="Invalid token environment"):
        _ = resolve(["bad-name"])
    assert redact(
        {
            "clientSecret": "x",
            "echo": "credential",
            "endpoint": "https://example.com/collect?access_token=private&event=view",
        },
        "credential",
    ) == {
        "clientSecret": "<redacted>",
        "echo": "<redacted>",
        "endpoint": "https://example.com/collect?access_token=<redacted>&event=view",
    }
    assert next_token({"nextPageToken": "page-2"}) == "page-2"
    assert next_token({"nextPageToken": None}) is None
    assert response_payload(b'{"nextPageToken":"x"}', "application/json") == {"nextPageToken": "x"}
    assert response_payload(b"plain", "text/plain") == "plain"
    validate(argparse.Namespace(timeout=1, retries=0, command="request", max_pages=500))
    for arguments in (
        argparse.Namespace(timeout=0, retries=0, command="context"),
        argparse.Namespace(timeout=1, retries=11, command="context"),
        argparse.Namespace(timeout=1, retries=0, command="request", max_pages=501),
    ):
        with pytest.raises(helper_error):
            validate(arguments)


def test_gtm_discovery_validation_and_operation_query() -> None:
    """Reject unrelated Discovery documents and undocumented operation query names."""
    helper_error = error_type(GTM, "GoogleTagManagerCliError")
    validate_document = cast(
        "Callable[[dict[str, JsonValue]], None]",
        function(GTM, "validate_discovery_document"),
    )
    parse_method = cast("Callable[[JsonValue], object | None]", function(GTM, "parse_method"))
    validate_query = cast("Callable[[object, dict[str, str]], None]", function(GTM, "validate_operation_query"))
    validate_document({"name": "tagmanager", "version": "v2", "resources": {}})
    invalid_documents: tuple[dict[str, JsonValue], ...] = (
        {"name": "other", "version": "v2", "resources": {}},
        {"name": "tagmanager", "version": "v1", "resources": {}},
        {"name": "tagmanager", "version": "v2"},
    )
    for payload in invalid_documents:
        with pytest.raises(helper_error):
            validate_document(payload)
    operation = parse_method(
        {
            "id": "tagmanager.accounts.list",
            "path": "tagmanager/v2/accounts",
            "httpMethod": "GET",
            "parameters": {"pageToken": {"location": "query"}},
        }
    )
    assert operation is not None
    validate_query(operation, {"pageToken": "x", "fields": "account"})
    with pytest.raises(helper_error, match="Unknown query"):
        validate_query(operation, {"unknown": "x"})


def test_uptimerobot_execute_pagination_and_missing_credentials(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Traverse safe UptimeRobot pages and refuse uncredentialed execution."""
    helper_error = error_type(UPTIMEROBOT, "UptimeRobotCliError")
    context_type = cast("Callable[..., object]", function(UPTIMEROBOT, "UptimeRobotContext"))
    credential_type = cast("Callable[..., object]", function(UPTIMEROBOT, "Credential"))
    plan_type = cast("Callable[..., RequestPlanView]", function(UPTIMEROBOT, "RequestPlan"))
    result_type = cast("Callable[..., object]", function(UPTIMEROBOT, "ApiResult"))
    execute = cast(
        "Callable[[argparse.Namespace, object, RequestPlanView], None]",
        function(UPTIMEROBOT, "execute_plan"),
    )
    credential = credential_type(environment="TEST_READ", value="credential")
    context = context_type(
        base_url="https://api.uptimerobot.com/v3",
        main_credential=None,
        read_credential=credential,
        spec_url="https://cdn.uptimerobot.com/api/openapi.yaml",
    )
    plan = plan_type(
        body=None,
        confirmation_value=None,
        high_risk=False,
        method="GET",
        operation_id="MonitorsController_list",
        query={"limit": "1"},
        url="https://api.uptimerobot.com/v3/monitors",
    )
    responses = iter(
        (
            result_type(
                payload={"data": [{"id": 1}], "nextLink": "?cursor=2"},
                status=200,
                url="https://api.uptimerobot.com/v3/monitors?limit=1",
            ),
            result_type(
                payload={"data": [{"id": 2}], "nextLink": None},
                status=200,
                url="https://api.uptimerobot.com/v3/monitors?cursor=2",
            ),
        )
    )

    def fake_send(*_arguments: object) -> object:
        return next(responses)

    monkeypatch.setattr(UPTIMEROBOT, "send_request", fake_send)
    arguments = argparse.Namespace(send=False, dry_run=False, paginate=True, max_pages=5, confirm=None)
    assert execute(arguments, context, plan) is None
    output = json_from_capture(capsys)
    assert output["complete"] is True
    assert output["pageCount"] == EXPECTED_PAGE_COUNT

    no_auth = context_type(
        base_url="https://api.uptimerobot.com/v3",
        main_credential=None,
        read_credential=None,
        spec_url="https://cdn.uptimerobot.com/api/openapi.yaml",
    )
    read_arguments = argparse.Namespace(send=False, dry_run=False, paginate=False, confirm=None)
    with pytest.raises(helper_error, match="No read-only or main credential"):
        _ = execute(read_arguments, no_auth, plan)

    delete_plan = plan_type(
        body=None,
        confirmation_value="DELETE /monitors/42",
        high_risk=True,
        method="DELETE",
        operation_id=None,
        query={},
        url="https://api.uptimerobot.com/v3/monitors/42",
    )
    delete_arguments = argparse.Namespace(send=True, dry_run=False, paginate=False, confirm=None)
    delete_context = context_type(
        base_url="https://api.uptimerobot.com/v3",
        main_credential=credential,
        read_credential=None,
        spec_url="https://cdn.uptimerobot.com/api/openapi.yaml",
    )
    with pytest.raises(helper_error, match="requires --confirm"):
        _ = execute(delete_arguments, delete_context, delete_plan)
    main_context = context_type(
        base_url="https://api.uptimerobot.com/v3",
        main_credential=credential,
        read_credential=None,
        spec_url="https://cdn.uptimerobot.com/api/openapi.yaml",
    )

    def fake_delete_send(*_arguments: object) -> object:
        return result_type(
            payload={"deleted": True},
            status=200,
            url="https://api.uptimerobot.com/v3/monitors/42",
        )

    monkeypatch.setattr(UPTIMEROBOT, "send_request", fake_delete_send)
    assert (
        execute(
            argparse.Namespace(send=True, dry_run=False, paginate=False, confirm="DELETE /monitors/42"),
            main_context,
            delete_plan,
        )
        is None
    )
    assert json_from_capture(capsys)["status"] == HTTP_OK


def json_from_capture(capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    """Decode one helper JSON document emitted during a direct unit call."""
    value = json.loads(capsys.readouterr().out)
    if not isinstance(value, dict):
        raise TypeError("Expected captured JSON object.")
    return cast("dict[str, object]", value)


def test_gtm_execute_pagination_and_confirmation(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Traverse GTM page tokens and block a high-risk mutation without confirmation."""
    helper_error = error_type(GTM, "GoogleTagManagerCliError")
    context_type = cast("Callable[..., object]", function(GTM, "GoogleTagManagerContext"))
    credential_type = cast("Callable[..., object]", function(GTM, "Credential"))
    plan_type = cast("Callable[..., RequestPlanView]", function(GTM, "RequestPlan"))
    result_type = cast("Callable[..., object]", function(GTM, "ApiResult"))
    execute = cast(
        "Callable[[argparse.Namespace, object, RequestPlanView], None]",
        function(GTM, "execute_plan"),
    )
    credential = credential_type(environment="TEST_GTM", value="credential")
    context = context_type(
        base_url="https://tagmanager.googleapis.com/tagmanager/v2",
        credential=credential,
        discovery_url="https://tagmanager.googleapis.com/$discovery/rest?version=v2",
    )
    read_plan = plan_type(
        body=None,
        confirmation_value=None,
        high_risk=False,
        method="GET",
        operation_id="tagmanager.accounts.list",
        query={},
        required_scopes=("readonly",),
        supports_page_token=True,
        url="https://tagmanager.googleapis.com/tagmanager/v2/accounts",
    )
    responses = iter(
        (
            result_type(payload={"account": [{"id": "1"}], "nextPageToken": "two"}, status=200, url="page1"),
            result_type(payload={"account": [{"id": "2"}]}, status=200, url="page2"),
        )
    )

    def fake_send(*_arguments: object) -> object:
        return next(responses)

    monkeypatch.setattr(GTM, "send_request", fake_send)
    assert (
        execute(
            argparse.Namespace(send=False, dry_run=False, paginate=True, max_pages=5, confirm=None),
            context,
            read_plan,
        )
        is None
    )
    output = json_from_capture(capsys)
    assert output["complete"] is True
    assert output["pageCount"] == EXPECTED_PAGE_COUNT

    publish_plan = plan_type(
        body=None,
        confirmation_value="tagmanager.accounts.containers.versions.publish",
        high_risk=True,
        method="POST",
        operation_id="tagmanager.accounts.containers.versions.publish",
        query={},
        required_scopes=("publish",),
        supports_page_token=False,
        url="https://tagmanager.googleapis.com/tagmanager/v2/accounts/1/containers/2/versions/3:publish",
    )
    publish_arguments = argparse.Namespace(send=True, dry_run=False, paginate=False, confirm=None)
    with pytest.raises(helper_error, match="requires --confirm"):
        _ = execute(publish_arguments, context, publish_plan)
