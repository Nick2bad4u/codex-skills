# Copyright (c) 2026 Nick2bad4u
"""Focused unit tests for management-helper validation and redaction logic."""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, cast

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[1]

type JsonValue = bool | int | float | str | list[JsonValue] | dict[str, JsonValue] | None


class RepositorySlug(Protocol):
    """Structural view of the Socket repository-slug record."""

    organization: str
    repository: str


class RequestPlanView(Protocol):
    """Structural view of a management helper request plan."""

    query: dict[str, str]
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


SOCKET = load_script_module(
    "test_manage_socket",
    "skills/socket-management/scripts/manage_socket.py",
)
SNYK = load_script_module(
    "test_manage_snyk",
    "skills/snyk-management/scripts/manage_snyk.py",
)
WAKATIME = load_script_module(
    "test_manage_wakatime",
    "skills/wakatime-management/scripts/manage_wakatime.py",
)
STEPSECURITY = load_script_module(
    "test_manage_stepsecurity",
    "skills/stepsecurity-management/scripts/manage_stepsecurity.py",
)


def function(module: ModuleType, name: str) -> object:
    """Retrieve a dynamically loaded helper member for an explicit cast."""
    return getattr(module, name)


def error_type(module: ModuleType, name: str) -> type[Exception]:
    """Retrieve one helper's user-facing exception type."""
    return cast("type[Exception]", function(module, name))


def embedded_credentials_url(host_and_path: str) -> str:
    """Build a deliberately invalid URL without a credential-like source literal."""
    return "https://user" + chr(58) + "placeholder@" + host_and_path


def test_socket_repository_context_validation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Cover Socket repository, base URL, remote, and token validation."""
    socket_error = error_type(SOCKET, "SocketCliError")
    optional_text = cast("Callable[[object], str | None]", function(SOCKET, "optional_text"))
    resolve_repository = cast("Callable[[str], Path]", function(SOCKET, "resolve_repository"))
    sanitize = cast("Callable[[str], str]", function(SOCKET, "sanitize_base_url"))
    parse_remote = cast("Callable[[str], RepositorySlug | None]", function(SOCKET, "parse_github_remote"))
    resolve_token = cast(
        "Callable[[list[str]], tuple[str | None, str | None]]",
        function(SOCKET, "resolve_token"),
    )
    assert optional_text(None) is None
    assert optional_text("  ") is None
    assert optional_text(42) == "42"
    assert resolve_repository(str(tmp_path)) == tmp_path.resolve()
    file_path = tmp_path / "file.txt"
    _ = file_path.write_text("x", encoding="utf-8")
    with pytest.raises(argparse.ArgumentTypeError, match="not a directory"):
        _ = resolve_repository(str(file_path))
    with pytest.raises(argparse.ArgumentTypeError, match="does not exist"):
        _ = resolve_repository(str(tmp_path / "missing"))

    assert sanitize(" https://api.socket.dev/v0/ ") == "https://api.socket.dev/v0"
    for invalid in (
        "http://api.socket.dev/v0",
        embedded_credentials_url("api.socket.dev/v0"),
        "https://api.socket.dev/v0?token=x",
        "https://api.socket.dev/v1",
    ):
        with pytest.raises(socket_error):
            _ = sanitize(invalid)

    https_slug = parse_remote("https://github.com/Nick2bad4u/codex-skills.git")
    ssh_slug = parse_remote("git@github.com:Nick2bad4u/codex-skills.git")
    assert https_slug is not None
    assert https_slug.repository == "codex-skills"
    assert ssh_slug is not None
    assert ssh_slug.organization == "Nick2bad4u"
    assert parse_remote("https://example.com/org/repo") is None
    assert parse_remote("https://github.com/too/many/parts") is None

    monkeypatch.setenv("SOCKET_UNIT_TOKEN", " value ")
    assert resolve_token(["SOCKET_UNIT_TOKEN"]) == ("value", "SOCKET_UNIT_TOKEN")
    assert resolve_token(["SOCKET_EMPTY_TOKEN"]) == (None, None)
    with pytest.raises(socket_error, match="Invalid token environment"):
        _ = resolve_token(["bad-name!"])


def test_socket_request_input_validation_and_redaction() -> None:
    """Cover Socket JSON, request input, path, URL, and redaction validation."""
    socket_error = error_type(SOCKET, "SocketCliError")
    decode = cast("Callable[..., JsonValue]", function(SOCKET, "decode_json"))
    parse_pairs = cast("Callable[..., dict[str, str]]", function(SOCKET, "parse_pairs"))
    fill_path = cast("Callable[[str, dict[str, str]], str]", function(SOCKET, "fill_path"))
    validate_endpoint = cast("Callable[[str, str], str]", function(SOCKET, "validated_endpoint_url"))
    redact = cast("Callable[[JsonValue, str | None], JsonValue]", function(SOCKET, "redact_json"))

    assert decode(b'{"ok":true}', source="fixture") == {"ok": True}
    with pytest.raises(socket_error, match="Expected JSON"):
        _ = decode(b"not-json", source="fixture")
    assert parse_pairs(["limit=10"], label="query") == {"limit": "10"}
    for values in (["missing"], ["name=value", "name=again"], ["api_token=bad"]):
        with pytest.raises(socket_error):
            _ = parse_pairs(values, label="query")
    assert fill_path("/orgs/{org}", {"org": "Nick 2"}) == "/orgs/Nick%202"
    with pytest.raises(socket_error, match="Missing path"):
        _ = fill_path("/orgs/{org}", {})
    with pytest.raises(socket_error, match="Unused path"):
        _ = fill_path("/orgs", {"org": "Nick"})
    assert validate_endpoint("https://api.socket.dev/v0", "/alerts") == "https://api.socket.dev/v0/alerts"
    for endpoint in ("/../alerts", "/alerts?q=x", "https://api.socket.dev/outside"):
        with pytest.raises(socket_error):
            _ = validate_endpoint("https://api.socket.dev/v0", endpoint)
    assert redact({"token": "x", "nested": ["credential"]}, "credential") == {
        "token": "<redacted>",
        "nested": ["<redacted>"],
    }


def test_snyk_pure_validation_and_pagination_guards(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cover Snyk region, version, token, response, path, and pagination validation."""
    snyk_error = error_type(SNYK, "SnykCliError")
    sanitize = cast("Callable[[str], str]", function(SNYK, "sanitize_base_url"))
    validate_version = cast("Callable[[str], str]", function(SNYK, "validate_api_version"))
    resolve_token = cast(
        "Callable[[list[str]], tuple[str | None, str | None]]",
        function(SNYK, "resolve_token"),
    )
    response_payload = cast("Callable[..., JsonValue]", function(SNYK, "response_payload"))
    validate_endpoint = cast("Callable[[str, str], str]", function(SNYK, "validated_endpoint_url"))
    parse_pairs = cast("Callable[..., dict[str, str]]", function(SNYK, "parse_pairs"))
    fill_path = cast("Callable[[str, dict[str, str]], str]", function(SNYK, "fill_path"))
    redact = cast("Callable[[JsonValue, str | None], JsonValue]", function(SNYK, "redact_json"))

    assert sanitize("https://api.au.snyk.io/rest/") == "https://api.au.snyk.io/rest"
    for invalid in (
        "http://api.snyk.io/rest",
        embedded_credentials_url("api.snyk.io/rest"),
        "https://api.snyk.io/rest?x=1",
        "https://api.snyk.io/v1",
    ):
        with pytest.raises(snyk_error):
            _ = sanitize(invalid)
    assert validate_version("2024-10-15") == "2024-10-15"
    assert validate_version("2026-03-25~beta") == "2026-03-25~beta"
    with pytest.raises(snyk_error, match="API version"):
        _ = validate_version("latest")

    monkeypatch.setenv("SNYK_UNIT_TOKEN", "value")
    assert resolve_token(["SNYK_UNIT_TOKEN"]) == ("value", "SNYK_UNIT_TOKEN")
    with pytest.raises(snyk_error, match="Invalid token environment"):
        _ = resolve_token(["not-valid!"])
    assert response_payload(b'{"data":[]}', "application/json", source="fixture") == {"data": []}
    assert response_payload(b"plain", "text/plain", source="fixture") == "plain"
    with pytest.raises(snyk_error, match="malformed JSON"):
        _ = response_payload(b"bad", "application/json", source="fixture")

    base = "https://api.snyk.io/rest"
    assert validate_endpoint(base, "/orgs") == f"{base}/orgs"
    for endpoint in ("/../orgs", "/orgs?q=x", "https://api.eu.snyk.io/rest/orgs", "https://api.snyk.io/v1"):
        with pytest.raises(snyk_error):
            _ = validate_endpoint(base, endpoint)
    assert parse_pairs(["limit=20"], label="query") == {"limit": "20"}
    with pytest.raises(snyk_error):
        _ = parse_pairs(["token=bad"], label="query")
    assert fill_path("/orgs/{org_id}", {"org_id": "abc/123"}) == "/orgs/abc%2F123"
    assert redact({"api_key": "x", "message": "secret"}, "secret") == {
        "api_key": "<redacted>",
        "message": "<redacted>",
    }


def test_snyk_openapi_and_pagination_link_validation() -> None:
    """Keep Snyk specifications and cursor links on the selected regional API contract."""
    snyk_error = error_type(SNYK, "SnykCliError")
    context_factory = cast("Callable[..., object]", function(SNYK, "SnykContext"))
    plan_factory = cast("Callable[..., object]", function(SNYK, "RequestPlan"))
    validate_spec = cast("Callable[[str, object], str]", function(SNYK, "validate_spec_url"))
    pagination_plan = cast(
        "Callable[[object, object, str], object]",
        function(SNYK, "pagination_plan"),
    )
    context = context_factory(
        api_version="2024-10-15",
        auth_scheme="token",
        base_url="https://api.snyk.io/rest",
        token=None,
        token_env_name=None,
    )
    plan = plan_factory(
        body=None,
        method="GET",
        operation_id="listOrgs",
        query={"version": "2024-10-15"},
        url="https://api.snyk.io/rest/orgs",
    )
    spec_url = "https://api.snyk.io/rest/openapi/2024-10-15"
    assert validate_spec(spec_url, context) == spec_url
    for invalid in (
        "http://api.snyk.io/rest/openapi/2024-10-15",
        embedded_credentials_url("api.snyk.io/rest/openapi/2024-10-15"),
        "https://api.snyk.io/rest/openapi/2024-10-15?x=1",
        "https://api.eu.snyk.io/rest/openapi/2024-10-15",
        "https://api.snyk.io/rest/orgs",
    ):
        with pytest.raises(snyk_error):
            _ = validate_spec(invalid, context)

    absolute = cast(
        "RequestPlanView",
        pagination_plan(
            context,
            plan,
            "https://api.snyk.io/rest/orgs?version=2024-10-15&starting_after=cursor",
        ),
    )
    relative = cast(
        "RequestPlanView",
        pagination_plan(context, plan, "/rest/orgs?version=2024-10-15&starting_after=cursor"),
    )
    assert absolute.url == "https://api.snyk.io/rest/orgs"
    assert absolute.query["starting_after"] == "cursor"
    assert relative.url == "https://api.snyk.io/rest/orgs"
    for invalid in (
        "orgs?version=2024-10-15",
        "/rest/orgs?version=2023-01-01",
        "/rest/orgs?version=2024-10-15&token=bad",
        "https://api.eu.snyk.io/rest/orgs?version=2024-10-15",
    ):
        with pytest.raises(snyk_error):
            _ = pagination_plan(context, plan, invalid)


def test_wakatime_pure_validation_auth_and_redaction() -> None:
    """Cover WakaTime credential names, ranges, endpoints, response parsing, and redaction."""
    wakatime_error = error_type(WAKATIME, "WakaTimeCliError")
    validate_environment = cast("Callable[[str], str]", function(WAKATIME, "validate_environment_name"))
    sanitize = cast("Callable[[str], str]", function(WAKATIME, "sanitize_base_url"))
    parse_date = cast("Callable[[str], object]", function(WAKATIME, "parse_date"))
    parse_pairs = cast("Callable[[list[str]], dict[str, str]]", function(WAKATIME, "parse_pairs"))
    validate_endpoint = cast("Callable[[str, str], str]", function(WAKATIME, "validated_endpoint_url"))
    response_payload = cast("Callable[[bytes, str], JsonValue]", function(WAKATIME, "response_payload"))
    redact = cast("Callable[[JsonValue, str | None], JsonValue]", function(WAKATIME, "redact_json"))

    assert validate_environment("WAKATIME_UNIT_KEY") == "WAKATIME_UNIT_KEY"
    with pytest.raises(wakatime_error, match="Invalid credential environment"):
        _ = validate_environment("bad-name!")
    assert sanitize("https://api.wakatime.com/api/v1/") == "https://api.wakatime.com/api/v1"
    for invalid in (
        "http://api.wakatime.com/api/v1",
        embedded_credentials_url("api.wakatime.com/api/v1"),
        "https://api.wakatime.com/api/v1?q=x",
        "https://api.wakatime.com/v2",
    ):
        with pytest.raises(wakatime_error):
            _ = sanitize(invalid)
    assert str(parse_date("2026-08-22")) == "2026-08-22"
    with pytest.raises(argparse.ArgumentTypeError, match="YYYY-MM-DD"):
        _ = parse_date("yesterday")
    assert parse_pairs(["project=codex", "branch=main"]) == {"project": "codex", "branch": "main"}
    for values in (["missing"], ["x=1", "x=2"], ["access_token=bad"]):
        with pytest.raises(wakatime_error):
            _ = parse_pairs(values)
    base = "https://api.wakatime.com/api/v1"
    assert validate_endpoint(base, "/users/current") == f"{base}/users/current"
    for endpoint in ("/../users", "/users?q=x", "relative", "https://example.com/api/v1/users"):
        with pytest.raises(wakatime_error):
            _ = validate_endpoint(base, endpoint)
    assert response_payload(b'{"data":{}}', "application/json") == {"data": {}}
    assert response_payload(b"text", "text/plain") == "text"
    with pytest.raises(wakatime_error, match="malformed JSON"):
        _ = response_payload(b"bad", "application/json")
    assert redact({"secret": "x", "text": "key-value"}, "key") == {
        "secret": "<redacted>",
        "text": "<redacted>-value",
    }


def test_stepsecurity_json_and_openapi_validation(tmp_path: Path) -> None:
    """Cover StepSecurity pair, repository, JSON, and OpenAPI validation."""
    step_error = error_type(STEPSECURITY, "StepSecurityError")
    parse_pairs = cast("Callable[[list[str] | None, str], dict[str, str]]", function(STEPSECURITY, "parse_pairs"))
    normalize_repo = cast("Callable[[str | None], str | None]", function(STEPSECURITY, "normalize_repo"))
    load_spec = cast("Callable[[str], dict[str, object]]", function(STEPSECURITY, "load_spec"))
    parameter_list = cast(
        "Callable[[object], list[dict[str, object]]]",
        function(STEPSECURITY, "parameter_list"),
    )
    request_body_required = cast("Callable[[object], bool]", function(STEPSECURITY, "request_body_is_required"))
    assert parse_pairs(None, "query") == {}
    assert parse_pairs(["limit=10"], "query") == {"limit": "10"}
    for values in (["bad"], ["=x"], ["x=1", "x=2"]):
        with pytest.raises(step_error):
            _ = parse_pairs(values, "query")
    assert normalize_repo(None) is None
    assert normalize_repo(" Nick/repo/ ") == "Nick/repo"
    with pytest.raises(step_error, match="owner/repository"):
        _ = normalize_repo("invalid")

    valid_spec = tmp_path / "valid.json"
    _ = valid_spec.write_text('{"openapi":"3.1.0","paths":{}}', encoding="utf-8")
    assert load_spec(str(valid_spec))["openapi"] == "3.1.0"
    malformed = tmp_path / "malformed.json"
    _ = malformed.write_text("not-json", encoding="utf-8")
    with pytest.raises(step_error, match="Invalid JSON"):
        _ = load_spec(str(malformed))
    with pytest.raises(step_error, match="Could not read"):
        _ = load_spec(str(tmp_path / "missing.json"))
    assert parameter_list(None) == []
    assert parameter_list([{"name": "org", "in": "path"}])[0]["name"] == "org"
    with pytest.raises(step_error, match="must be a list"):
        _ = parameter_list({})
    with pytest.raises(step_error, match="Referenced OpenAPI parameters"):
        _ = parameter_list([{"$ref": "#/components/parameters/x"}])
    assert request_body_required({"required": True}) is True
    assert request_body_required(None) is False
    with pytest.raises(step_error, match="Referenced OpenAPI request bodies"):
        _ = request_body_required({"$ref": "#/components/requestBodies/x"})


def test_stepsecurity_url_body_redaction_and_links(tmp_path: Path) -> None:
    """Cover StepSecurity URL, body, redaction, response, and pagination helpers."""
    step_error = error_type(STEPSECURITY, "StepSecurityError")
    validated_url = cast("Callable[[str], str]", function(STEPSECURITY, "validated_url"))
    apply_query = cast("Callable[[str, dict[str, str]], str]", function(STEPSECURITY, "apply_query"))
    body_bytes = cast("Callable[[argparse.Namespace], bytes | None]", function(STEPSECURITY, "body_bytes"))
    redact = cast("Callable[[object], object]", function(STEPSECURITY, "redact"))
    sensitive_header_values = cast(
        "Callable[[dict[str, str]], tuple[str, ...]]",
        function(STEPSECURITY, "sensitive_header_values"),
    )
    parse_response = cast("Callable[[bytes, str], object]", function(STEPSECURITY, "parse_response"))
    next_link = cast("Callable[[object], str | None]", function(STEPSECURITY, "next_link"))

    assert validated_url("/detections") == "https://agent.api.stepsecurity.io/v1/detections"
    for endpoint in (
        "",
        "http://agent.api.stepsecurity.io/v1/detections",
        "https://agent.api.stepsecurity.io/outside",
        embedded_credentials_url("agent.api.stepsecurity.io/v1/detections"),
        "/detections?token=bad",
    ):
        with pytest.raises(step_error):
            _ = validated_url(endpoint)
    detections_url = validated_url("/detections")
    assert apply_query(detections_url, {"limit": "10"}).endswith("?limit=10")
    with pytest.raises(step_error, match="Credential-like query"):
        _ = apply_query(detections_url, {"api_key": "bad"})

    assert body_bytes(argparse.Namespace(body=None, body_file=None)) is None
    assert body_bytes(argparse.Namespace(body='{"ok":true}', body_file=None)) == b'{"ok":true}'
    body_file = tmp_path / "body.json"
    _ = body_file.write_text("{}", encoding="utf-8")
    conflicting_body = argparse.Namespace(body="{}", body_file=str(body_file))
    with pytest.raises(step_error, match="either --body"):
        _ = body_bytes(conflicting_body)
    invalid_body = argparse.Namespace(body="bad", body_file=None)
    with pytest.raises(step_error, match="Invalid inline JSON"):
        _ = body_bytes(invalid_body)
    assert redact({"token": "x", "items": [{"ok": True}]}) == {
        "token": "<redacted>",
        "items": [{"ok": True}],
    }
    assert sensitive_header_values({"Authorization": "Bearer secret", "Accept": "application/json"}) == (
        "Bearer secret",
        "secret",
    )
    assert parse_response(b'{"secret":"x"}', "application/json") == {"secret": "<redacted>"}
    assert parse_response(b"plain", "text/plain") == "plain"
    assert next_link({"links": {"next": "/page/2"}}) == "/page/2"
    assert next_link({"links": {"next": {"href": "/page/3"}}}) == "/page/3"
    assert next_link({"links": {"next": None}}) is None
    assert next_link([]) is None
