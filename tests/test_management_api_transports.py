# Copyright (c) 2026 Nick2bad4u
"""Transport-boundary tests for network-capable management helpers."""

from __future__ import annotations

import argparse
import gc
import importlib.util
import sys
import time
from email.message import Message
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, Self, cast
from urllib import error, request

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Mapping
    from types import ModuleType, TracebackType

REPO_ROOT = Path(__file__).resolve().parents[1]
HTTP_OK = 200
HTTP_TOO_MANY_REQUESTS = 429
EXPECTED_REQUEST_COUNT = 2
TEST_CREDENTIAL = "not-a-real-service-credential"
TEST_ENVIRONMENT_NAME = "TEST_SERVICE_ENV"

type JsonValue = bool | int | float | str | list[JsonValue] | dict[str, JsonValue] | None
type TransportOutcome = FakeResponse | BaseException


class ApiResultView(Protocol):
    """Structural response view shared by the management helpers."""

    payload: JsonValue
    status: int
    url: str


class SnykResultView(ApiResultView, Protocol):
    """Snyk response view with API lifecycle metadata."""

    sunset: str | None


class FakeResponse:
    """Small urllib-compatible response returned by a deterministic opener."""

    def __init__(self, payload: bytes, *, status: int = HTTP_OK, headers: Mapping[str, str] | None = None) -> None:
        """Initialize a response body, status, and HTTP-compatible headers."""
        super().__init__()
        self.payload = payload
        self.status = status
        self.headers = http_headers(headers or {})
        self._closed = False

    @property
    def closed(self) -> bool:
        """Return whether the response has been closed."""
        return self._closed

    def close(self) -> None:
        """Close the response idempotently like a real urllib response."""
        self._closed = True

    def __enter__(self) -> Self:
        """Enter a urllib-style response context."""
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Leave a urllib-style response context without suppressing errors."""
        del exception_type, exception, traceback
        self.close()

    def read(self, amount: int | None = None) -> bytes:
        """Return the configured payload, respecting an optional byte bound."""
        if self.closed:
            raise ValueError("I/O operation on closed response.")
        return self.payload if amount is None else self.payload[:amount]


class FakeOpener:
    """Record requests and return or raise deterministic transport outcomes."""

    def __init__(self, outcomes: list[TransportOutcome]) -> None:
        """Initialize the ordered transport outcomes and request log."""
        super().__init__()
        self.outcomes = outcomes
        self.requests: list[request.Request] = []

    def open(self, api_request: request.Request, timeout: float) -> FakeResponse:
        """Record one request and consume the next configured outcome."""
        del timeout
        self.requests.append(api_request)
        if not self.outcomes:
            raise AssertionError("Fake opener exhausted its configured outcomes.")
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def http_headers(values: Mapping[str, str]) -> Message:
    """Create an HTTPMessage-compatible header mapping."""
    headers = Message()
    for name, value in values.items():
        headers[name] = value
    return headers


def http_failure(
    url: str,
    status: int,
    payload: bytes = b"",
    *,
    headers: Mapping[str, str] | None = None,
) -> error.HTTPError:
    """Create a readable urllib HTTP error with deterministic headers."""
    return error.HTTPError(url, status, "fixture failure", http_headers(headers or {}), BytesIO(payload))


def install_opener(monkeypatch: pytest.MonkeyPatch, outcomes: list[TransportOutcome]) -> FakeOpener:
    """Replace urllib opener construction for one test."""
    opener = FakeOpener(outcomes)

    def build_opener(*_handlers: object) -> FakeOpener:
        return opener

    monkeypatch.setattr(request, "build_opener", build_opener)
    return opener


def record_sleeps(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Replace transport backoff with a deterministic recorder."""
    delays: list[float] = []

    def sleep(delay: float) -> None:
        delays.append(delay)

    monkeypatch.setattr(time, "sleep", sleep)
    return delays


def load_script_module(name: str, relative_path: str) -> ModuleType:
    """Load a repository helper without invoking its CLI entry point."""
    path = REPO_ROOT / relative_path
    specification = importlib.util.spec_from_file_location(name, path)
    if specification is None or specification.loader is None:
        raise RuntimeError(f"Could not load test module: {path}")
    module = importlib.util.module_from_spec(specification)
    sys.modules[name] = module
    specification.loader.exec_module(module)
    return module


def function(module: ModuleType, name: str) -> object:
    """Retrieve a dynamically loaded helper member for an explicit cast."""
    return getattr(module, name)


@pytest.fixture(autouse=True)
def collect_transport_exception_cycles() -> Iterator[None]:
    """Collect retained urllib tracebacks while pytest capture files are still open."""
    yield
    _ = gc.collect()


CODACY = load_script_module("transport_manage_codacy", "skills/codacy-management/scripts/manage_codacy.py")
SOCKET = load_script_module("transport_manage_socket", "skills/socket-management/scripts/manage_socket.py")
SNYK = load_script_module("transport_manage_snyk", "skills/snyk-management/scripts/manage_snyk.py")
WAKATIME = load_script_module("transport_manage_wakatime", "skills/wakatime-management/scripts/manage_wakatime.py")
STEPSECURITY = load_script_module(
    "transport_manage_stepsecurity",
    "skills/stepsecurity-management/scripts/manage_stepsecurity.py",
)
UPTIMEROBOT = load_script_module(
    "transport_manage_uptimerobot",
    "skills/uptimerobot-management/scripts/manage_uptimerobot.py",
)
GTM = load_script_module(
    "transport_manage_google_tag_manager",
    "skills/google-tag-manager-management/scripts/manage_google_tag_manager.py",
)


def test_contract_download_http_errors_are_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Close failed OpenAPI and Discovery responses before surfacing safe CLI errors."""
    codacy_context_factory = cast("Callable[..., object]", function(CODACY, "CodacyContext"))
    codacy_load = cast("Callable[..., object]", function(CODACY, "load_openapi_document"))
    codacy_error = cast("type[Exception]", function(CODACY, "CodacyCliError"))
    codacy_context = codacy_context_factory(
        base_url="https://api.codacy.com/api/v3",
        repository_root=REPO_ROOT,
        slug=None,
        token=None,
        token_env_name=None,
    )
    codacy_failure = http_failure("https://api.codacy.com/api/api-docs/swagger.yaml", 503)
    _ = install_opener(monkeypatch, [codacy_failure])
    codacy_spec_arguments = argparse.Namespace(spec_file=None, spec_url=None, timeout=1.0)
    with pytest.raises(codacy_error, match="Unable to load"):
        _ = codacy_load(codacy_spec_arguments, codacy_context)
    assert codacy_failure.fp.closed

    _ = install_opener(monkeypatch, [error.URLError("offline")])
    with pytest.raises(codacy_error, match="Unable to load"):
        _ = codacy_load(codacy_spec_arguments, codacy_context)

    socket_context_factory = cast("Callable[..., object]", function(SOCKET, "SocketContext"))
    socket_load = cast("Callable[..., object]", function(SOCKET, "load_openapi"))
    socket_error = cast("type[Exception]", function(SOCKET, "SocketCliError"))
    socket_context = socket_context_factory(
        base_url="https://api.socket.dev/v0",
        organization=None,
        repository=None,
        repository_root=REPO_ROOT,
        token=None,
        token_env_name=None,
    )
    socket_failure = http_failure("https://api.socket.dev/v0/openapi", 503)
    _ = install_opener(monkeypatch, [socket_failure])
    socket_spec_arguments = argparse.Namespace(spec_file=None, spec_url=None, timeout=1.0)
    with pytest.raises(socket_error, match="OpenAPI request failed"):
        _ = socket_load(socket_spec_arguments, socket_context)
    assert socket_failure.fp.closed

    snyk_get_json = cast("Callable[..., object]", function(SNYK, "get_json"))
    snyk_error = cast("type[Exception]", function(SNYK, "SnykCliError"))
    snyk_failure = http_failure("https://api.snyk.io/rest/openapi/2024-10-15", 503)
    _ = install_opener(monkeypatch, [snyk_failure])
    with pytest.raises(snyk_error, match="request failed"):
        _ = snyk_get_json(
            "https://api.snyk.io/rest/openapi/2024-10-15",
            timeout=1.0,
            source="Snyk OpenAPI",
        )
    assert snyk_failure.fp.closed


def test_yaml_contract_download_http_errors_are_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Close failed YAML OpenAPI and Discovery responses before surfacing CLI errors."""
    uptime_context_factory = cast("Callable[..., object]", function(UPTIMEROBOT, "UptimeRobotContext"))
    uptime_load = cast("Callable[..., object]", function(UPTIMEROBOT, "load_operations"))
    uptime_error = cast("type[Exception]", function(UPTIMEROBOT, "UptimeRobotCliError"))
    uptime_context = uptime_context_factory(
        base_url="https://api.uptimerobot.com/v3",
        main_credential=None,
        read_credential=None,
        spec_url="https://cdn.uptimerobot.com/api/openapi.yaml",
    )
    uptime_failure = http_failure("https://cdn.uptimerobot.com/api/openapi.yaml", 503)
    _ = install_opener(monkeypatch, [uptime_failure])
    uptime_spec_arguments = argparse.Namespace(spec_file=None, timeout=1.0)
    with pytest.raises(uptime_error, match="OpenAPI request failed"):
        _ = uptime_load(uptime_spec_arguments, uptime_context)
    assert uptime_failure.fp.closed

    gtm_context_factory = cast("Callable[..., object]", function(GTM, "GoogleTagManagerContext"))
    gtm_load = cast("Callable[..., object]", function(GTM, "load_discovery"))
    gtm_error = cast("type[Exception]", function(GTM, "GoogleTagManagerCliError"))
    gtm_context = gtm_context_factory(
        base_url="https://tagmanager.googleapis.com/tagmanager/v2",
        credential=None,
        discovery_url="https://tagmanager.googleapis.com/$discovery/rest?version=v2",
    )
    gtm_failure = http_failure("https://tagmanager.googleapis.com/$discovery/rest?version=v2", 503)
    _ = install_opener(monkeypatch, [gtm_failure])
    gtm_discovery_arguments = argparse.Namespace(discovery_file=None, timeout=1.0)
    with pytest.raises(gtm_error, match="Discovery request failed"):
        _ = gtm_load(gtm_discovery_arguments, gtm_context)
    assert gtm_failure.fp.closed


def test_codacy_dynamic_boundaries_and_response_decoding(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cover Codacy argparse validation, fallback decoding, redaction, and JSON request bodies."""
    as_string_list = cast("Callable[[object, str], list[str]]", function(CODACY, "as_string_list"))
    decode_response = cast("Callable[[bytes, str | None], JsonValue]", function(CODACY, "decode_api_response"))
    redact_json = cast("Callable[[JsonValue, str | None], JsonValue]", function(CODACY, "redact_json"))
    helper_error = cast("type[Exception]", function(CODACY, "CodacyCliError"))

    assert as_string_list(["query=value"], "Query values") == ["query=value"]
    with pytest.raises(helper_error, match="list of strings"):
        _ = as_string_list([1], "Query values")
    assert redact_json(f"prefix-{TEST_CREDENTIAL}", TEST_CREDENTIAL) == "prefix-<redacted>"
    assert decode_response(b"", None) is None
    fallback = decode_response(f"not-json-{TEST_CREDENTIAL}".encode(), TEST_CREDENTIAL)
    assert isinstance(fallback, str)
    assert TEST_CREDENTIAL not in fallback
    assert "<redacted>" in fallback

    context_factory = cast("Callable[..., object]", function(CODACY, "CodacyContext"))
    plan_factory = cast("Callable[..., object]", function(CODACY, "RequestPlan"))
    runtime_factory = cast("Callable[..., object]", function(CODACY, "RequestRuntime"))
    send = cast("Callable[..., object]", function(CODACY, "send_request"))
    context = context_factory(
        base_url="https://api.codacy.com/api/v3",
        repository_root=REPO_ROOT,
        slug=None,
        token=TEST_CREDENTIAL,
        token_env_name=TEST_ENVIRONMENT_NAME,
    )
    plan = plan_factory(body={"name": "demo"}, endpoint="/items", method="POST", operation_id=None, query={})
    opener = install_opener(
        monkeypatch,
        [FakeResponse(b'{"id":"1"}', headers={"Content-Type": "application/json"})],
    )
    result = cast(
        "ApiResultView",
        send(
            context,
            plan,
            query={},
            runtime=runtime_factory(retries=0, retry_base_delay=0.0, timeout=1.0),
        ),
    )
    assert result.payload == {"id": "1"}
    assert opener.requests[0].data == b'{"name":"demo"}'
    assert opener.requests[0].get_header("Content-type") == "application/json"


def test_codacy_transport_retries_redacts_errors_and_merges_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    """Exercise Codacy request construction, retry safety, and cursor aggregation."""
    context_factory = cast("Callable[..., object]", function(CODACY, "CodacyContext"))
    plan_factory = cast("Callable[..., object]", function(CODACY, "RequestPlan"))
    runtime_factory = cast("Callable[..., object]", function(CODACY, "RequestRuntime"))
    result_factory = cast("Callable[..., object]", function(CODACY, "ApiResult"))
    send = cast("Callable[..., object]", function(CODACY, "send_request"))
    paginate = cast("Callable[..., object]", function(CODACY, "paginate_request"))
    helper_error = cast("type[Exception]", function(CODACY, "CodacyCliError"))
    url = "https://api.codacy.com/api/v3/user"
    context = context_factory(
        base_url="https://api.codacy.com/api/v3",
        repository_root=REPO_ROOT,
        slug=None,
        token=TEST_CREDENTIAL,
        token_env_name=TEST_ENVIRONMENT_NAME,
    )
    plan = plan_factory(body=None, endpoint="/user", method="GET", operation_id=None, query={})
    runtime = runtime_factory(retries=1, retry_base_delay=0.25, timeout=1.0)
    opener = install_opener(
        monkeypatch,
        [
            http_failure(url, HTTP_TOO_MANY_REQUESTS, headers={"Retry-After": "0"}),
            FakeResponse(b'{"data":{"name":"demo"}}', headers={"Content-Type": "application/json"}),
        ],
    )
    delays = record_sleeps(monkeypatch)

    result = cast("ApiResultView", send(context, plan, query={}, runtime=runtime))
    assert result.status == HTTP_OK
    assert result.payload == {"data": {"name": "demo"}}
    assert delays == [0.0]
    assert len(opener.requests) == EXPECTED_REQUEST_COUNT
    assert opener.requests[0].get_header("Api-token") == TEST_CREDENTIAL

    _ = install_opener(
        monkeypatch,
        [http_failure(url, 400, f'{{"message":"{TEST_CREDENTIAL}"}}'.encode())],
    )
    terminal_runtime = runtime_factory(retries=0, retry_base_delay=0.0, timeout=1.0)
    with pytest.raises(helper_error) as captured:
        _ = send(context, plan, query={}, runtime=terminal_runtime)
    assert TEST_CREDENTIAL not in str(captured.value)
    assert "<redacted>" in str(captured.value)

    responses = iter(
        (
            result_factory(
                payload={"data": [{"id": 1}], "pagination": {"cursor": "next"}},
                status=HTTP_OK,
                url=url,
            ),
            result_factory(payload={"data": [{"id": 2}], "pagination": {}}, status=HTTP_OK, url=url),
        )
    )

    def fake_send(*_arguments: object, **_keywords: object) -> object:
        return next(responses)

    monkeypatch.setattr(CODACY, "send_request", fake_send)
    merged = cast("ApiResultView", paginate(context, plan, max_pages=3, runtime=runtime))
    assert merged.payload == {
        "data": [{"id": 1}, {"id": 2}],
        "pagination": {},
        "paginationFetch": {"fetchedCount": 2, "fetchedPages": 2},
    }


def test_socket_transport_retries_redacts_errors_and_merges_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    """Exercise Socket request construction, retry safety, and cursor aggregation."""
    context_factory = cast("Callable[..., object]", function(SOCKET, "SocketContext"))
    plan_factory = cast("Callable[..., object]", function(SOCKET, "RequestPlan"))
    result_factory = cast("Callable[..., object]", function(SOCKET, "ApiResult"))
    send = cast("Callable[..., object]", function(SOCKET, "send_request"))
    paginate = cast("Callable[..., object]", function(SOCKET, "paginated_request"))
    helper_error = cast("type[Exception]", function(SOCKET, "SocketCliError"))
    url = "https://api.socket.dev/v0/alerts"
    context = context_factory(
        base_url="https://api.socket.dev/v0",
        organization="acme",
        repository="widget",
        repository_root=REPO_ROOT,
        token=TEST_CREDENTIAL,
        token_env_name=TEST_ENVIRONMENT_NAME,
    )
    plan = plan_factory(body=None, method="GET", operation_id="listAlerts", query={}, url=url)
    arguments = argparse.Namespace(retries=1, timeout=1.0, max_pages=3)
    opener = install_opener(
        monkeypatch,
        [
            http_failure(
                url,
                HTTP_TOO_MANY_REQUESTS,
                b'{"message":"retry"}',
                headers={"Content-Type": "application/json", "Retry-After": "0"},
            ),
            FakeResponse(b'{"items":[],"endCursor":null}', headers={"Content-Type": "application/json"}),
        ],
    )
    delays = record_sleeps(monkeypatch)

    result = cast("ApiResultView", send(context, plan, query={}, arguments=arguments))
    assert result.payload == {"items": [], "endCursor": None}
    assert delays == [0.0]
    assert opener.requests[0].get_header("Authorization") == f"Bearer {TEST_CREDENTIAL}"

    _ = install_opener(
        monkeypatch,
        [
            http_failure(
                url,
                400,
                f'{{"message":"{TEST_CREDENTIAL}"}}'.encode(),
                headers={"Content-Type": "application/json"},
            )
        ],
    )
    terminal_arguments = argparse.Namespace(retries=0, timeout=1.0)
    with pytest.raises(helper_error) as captured:
        _ = send(context, plan, query={}, arguments=terminal_arguments)
    assert TEST_CREDENTIAL not in str(captured.value)

    responses = iter(
        (
            result_factory(payload={"items": [{"id": 1}], "endCursor": "next"}, status=HTTP_OK, url=url),
            result_factory(payload={"items": [{"id": 2}], "endCursor": None}, status=HTTP_OK, url=url),
        )
    )

    def fake_send(*_arguments: object, **_keywords: object) -> object:
        return next(responses)

    monkeypatch.setattr(SOCKET, "send_request", fake_send)
    merged = cast("ApiResultView", paginate(context, plan, arguments))
    assert merged.payload == {"items": [{"id": 1}, {"id": 2}], "endCursor": None, "pages": 2}


def test_snyk_transport_retries_redacts_errors_and_merges_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    """Exercise Snyk request construction, lifecycle headers, and JSON:API pagination."""
    context_factory = cast("Callable[..., object]", function(SNYK, "SnykContext"))
    plan_factory = cast("Callable[..., object]", function(SNYK, "RequestPlan"))
    result_factory = cast("Callable[..., object]", function(SNYK, "ApiResult"))
    send = cast("Callable[..., object]", function(SNYK, "send_request"))
    paginate = cast("Callable[..., object]", function(SNYK, "paginated_request"))
    helper_error = cast("type[Exception]", function(SNYK, "SnykCliError"))
    url = "https://api.snyk.io/rest/orgs?version=2024-10-15"
    context = context_factory(
        api_version="2024-10-15",
        auth_scheme="token",
        base_url="https://api.snyk.io/rest",
        token=TEST_CREDENTIAL,
        token_env_name=TEST_ENVIRONMENT_NAME,
    )
    plan = plan_factory(
        body=None,
        method="GET",
        operation_id="listOrgs",
        query={"version": "2024-10-15"},
        url="https://api.snyk.io/rest/orgs",
    )
    arguments = argparse.Namespace(retries=1, timeout=1.0, max_pages=3)
    opener = install_opener(
        monkeypatch,
        [
            http_failure(
                url,
                HTTP_TOO_MANY_REQUESTS,
                b"{}",
                headers={"Content-Type": "application/vnd.api+json", "Retry-After": "0"},
            ),
            FakeResponse(
                b'{"data":[],"links":{"next":null}}',
                headers={"Content-Type": "application/vnd.api+json", "Sunset": "2030-01-01"},
            ),
        ],
    )
    delays = record_sleeps(monkeypatch)

    result = cast("SnykResultView", send(context, plan, arguments))
    assert result.payload == {"data": [], "links": {"next": None}}
    assert result.sunset == "2030-01-01"
    assert delays == [0.0]
    assert opener.requests[0].get_header("Authorization") == f"token {TEST_CREDENTIAL}"

    _ = install_opener(
        monkeypatch,
        [
            http_failure(
                url,
                400,
                f'{{"detail":"{TEST_CREDENTIAL}"}}'.encode(),
                headers={"Content-Type": "application/vnd.api+json"},
            )
        ],
    )
    terminal_arguments = argparse.Namespace(retries=0, timeout=1.0)
    with pytest.raises(helper_error) as captured:
        _ = send(context, plan, terminal_arguments)
    assert TEST_CREDENTIAL not in str(captured.value)

    responses = iter(
        (
            result_factory(
                payload={
                    "data": [{"id": "1"}],
                    "links": {"next": "/rest/orgs?version=2024-10-15&starting_after=next"},
                },
                status=HTTP_OK,
                sunset=None,
                url=url,
            ),
            result_factory(
                payload={"data": [{"id": "2"}], "links": {"next": None}},
                status=HTTP_OK,
                sunset=None,
                url=url,
            ),
        )
    )

    def fake_send(*_arguments: object) -> object:
        return next(responses)

    monkeypatch.setattr(SNYK, "send_request", fake_send)
    merged = cast("SnykResultView", paginate(context, plan, arguments))
    assert merged.payload == {
        "data": [{"id": "1"}, {"id": "2"}],
        "links": {"next": None},
        "meta": {"pages": 2},
    }


def test_wakatime_transport_retries_and_redacts_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """Exercise WakaTime authorization, bounded retries, and safe HTTP errors."""
    authentication_factory = cast("Callable[..., object]", function(WAKATIME, "Authentication"))
    context_factory = cast("Callable[..., object]", function(WAKATIME, "WakaTimeContext"))
    plan_factory = cast("Callable[..., object]", function(WAKATIME, "RequestPlan"))
    send = cast("Callable[..., object]", function(WAKATIME, "send_request"))
    helper_error = cast("type[Exception]", function(WAKATIME, "WakaTimeCliError"))
    url = "https://api.wakatime.com/api/v1/users/current"
    authentication = authentication_factory(
        environment_name="WAKATIME_TEST_TOKEN", scheme="oauth", secret=TEST_CREDENTIAL
    )
    context = context_factory(authentication=authentication, base_url="https://api.wakatime.com/api/v1")
    plan = plan_factory(body=None, method="GET", query={}, url=url)
    opener = install_opener(
        monkeypatch,
        [
            http_failure(url, HTTP_TOO_MANY_REQUESTS, headers={"Retry-After": "0"}),
            FakeResponse(b'{"data":{"id":"current"}}', headers={"Content-Type": "application/json"}),
        ],
    )
    delays = record_sleeps(monkeypatch)

    result = cast("ApiResultView", send(context, plan, argparse.Namespace(retries=1, timeout=1.0)))
    assert result.payload == {"data": {"id": "current"}}
    assert delays == [0.0]
    assert opener.requests[0].get_header("Authorization") == f"Bearer {TEST_CREDENTIAL}"

    _ = install_opener(
        monkeypatch,
        [
            http_failure(
                url,
                400,
                f'{{"message":"{TEST_CREDENTIAL}"}}'.encode(),
                headers={"Content-Type": "application/json"},
            )
        ],
    )
    terminal_arguments = argparse.Namespace(retries=0, timeout=1.0)
    with pytest.raises(helper_error) as captured:
        _ = send(context, plan, terminal_arguments)
    assert TEST_CREDENTIAL not in str(captured.value)


def test_stepsecurity_transport_validates_redirects_retries_and_redacts(monkeypatch: pytest.MonkeyPatch) -> None:
    """Exercise StepSecurity redirects, retry policy, and response redaction."""
    runtime_factory = cast("Callable[..., object]", function(STEPSECURITY, "RequestRuntime"))
    send = cast("Callable[..., object]", function(STEPSECURITY, "send"))
    helper_error = cast("type[Exception]", function(STEPSECURITY, "StepSecurityError"))
    url = "https://agent.api.stepsecurity.io/v1/detections"
    success_response = FakeResponse(
        f'{{"data":[],"token":"{TEST_CREDENTIAL}"}}'.encode(),
        headers={"Content-Type": "application/json", "X-Request-Id": "fixture-request"},
    )
    opener = install_opener(
        monkeypatch,
        [
            http_failure(url, 302, headers={"Location": "/v1/detections?page=2"}),
            http_failure(url, HTTP_TOO_MANY_REQUESTS, headers={"Retry-After": "0"}),
            success_response,
        ],
    )
    delays = record_sleeps(monkeypatch)
    runtime = runtime_factory(retries=1, timeout=1.0)

    status, headers, payload = cast(
        "tuple[int, dict[str, str], object]",
        send("GET", url, {"Authorization": f"Bearer {TEST_CREDENTIAL}"}, None, runtime),
    )
    assert status == HTTP_OK
    assert headers["X-Request-Id"] == "fixture-request"
    assert payload == {"data": [], "token": "<redacted>"}
    assert delays == [0.0]
    assert [item.full_url for item in opener.requests] == [url, f"{url}?page=2", f"{url}?page=2"]
    assert success_response.closed

    _ = install_opener(monkeypatch, [error.URLError("offline")])
    with pytest.raises(helper_error, match="offline"):
        _ = send("GET", url, {}, None, runtime)

    terminal_failure = http_failure(url, 400, f'{{"message":"{TEST_CREDENTIAL}"}}'.encode())
    _ = install_opener(monkeypatch, [terminal_failure])
    with pytest.raises(helper_error) as captured:
        _ = send("GET", url, {"Authorization": f"Bearer {TEST_CREDENTIAL}"}, None, runtime)
    assert TEST_CREDENTIAL not in str(captured.value)
    assert terminal_failure.fp.closed


def test_uptimerobot_transport_retries_and_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Exercise UptimeRobot bearer requests, safe retries, and decoding failures."""
    credential_factory = cast("Callable[..., object]", function(UPTIMEROBOT, "Credential"))
    plan_factory = cast("Callable[..., object]", function(UPTIMEROBOT, "RequestPlan"))
    send = cast("Callable[..., object]", function(UPTIMEROBOT, "send_request"))
    response_payload = cast("Callable[[bytes, str], JsonValue]", function(UPTIMEROBOT, "response_payload"))
    helper_error = cast("type[Exception]", function(UPTIMEROBOT, "UptimeRobotCliError"))
    url = "https://api.uptimerobot.com/v3/monitors"
    credential = credential_factory(environment="UPTIMEROBOT_TEST_TOKEN", value=TEST_CREDENTIAL)
    plan = plan_factory(
        body=None,
        confirmation_value=None,
        high_risk=False,
        method="GET",
        operation_id="MonitorsController_list",
        query=(),
        url=url,
    )
    success_response = FakeResponse(b'{"data":[]}', headers={"Content-Type": "application/json"})
    opener = install_opener(
        monkeypatch,
        [
            http_failure(url, HTTP_TOO_MANY_REQUESTS, headers={"Retry-After": "0"}),
            success_response,
        ],
    )
    delays = record_sleeps(monkeypatch)

    result = cast("ApiResultView", send(plan, url, credential, argparse.Namespace(retries=1, timeout=1.0)))
    assert result.payload == {"data": []}
    assert delays == [0.0]
    assert success_response.closed
    assert opener.requests[0].get_header("Authorization") == f"Bearer {TEST_CREDENTIAL}"
    assert response_payload(b"", "application/json") is None
    with pytest.raises(helper_error, match="Expected JSON"):
        _ = response_payload(b"not-json", "application/json")

    _ = install_opener(monkeypatch, [error.URLError("offline")])
    terminal_arguments = argparse.Namespace(retries=0, timeout=1.0)
    with pytest.raises(helper_error, match="offline"):
        _ = send(plan, url, credential, terminal_arguments)

    terminal_failure = http_failure(url, 400)
    _ = install_opener(monkeypatch, [terminal_failure])
    with pytest.raises(helper_error, match="HTTP 400"):
        _ = send(plan, url, credential, terminal_arguments)
    assert terminal_failure.fp.closed


def test_gtm_transport_retries_sends_json_and_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Exercise GTM OAuth requests, JSON bodies, safe retries, and decoding failures."""
    credential_factory = cast("Callable[..., object]", function(GTM, "Credential"))
    plan_factory = cast("Callable[..., object]", function(GTM, "RequestPlan"))
    send = cast("Callable[..., object]", function(GTM, "send_request"))
    response_payload = cast("Callable[[bytes, str], JsonValue]", function(GTM, "response_payload"))
    helper_error = cast("type[Exception]", function(GTM, "GoogleTagManagerCliError"))
    url = "https://tagmanager.googleapis.com/tagmanager/v2/accounts"
    credential = credential_factory(environment="GTM_TEST_TOKEN", value=TEST_CREDENTIAL)
    plan = plan_factory(
        body=None,
        confirmation_value=None,
        high_risk=False,
        method="GET",
        operation_id="tagmanager.accounts.list",
        query={},
        acceptable_scopes=("readonly",),
        supports_page_token=True,
        url=url,
    )
    opener = install_opener(
        monkeypatch,
        [
            http_failure(url, HTTP_TOO_MANY_REQUESTS, headers={"Retry-After": "0"}),
            FakeResponse(b'{"account":[]}', headers={"Content-Type": "application/json"}),
        ],
    )
    delays = record_sleeps(monkeypatch)

    result = cast("ApiResultView", send(plan, url, credential, argparse.Namespace(retries=1, timeout=1.0)))
    assert result.payload == {"account": []}
    assert delays == [0.0]
    assert opener.requests[0].get_header("Authorization") == f"Bearer {TEST_CREDENTIAL}"
    assert response_payload(b"", "application/json") is None
    with pytest.raises(helper_error, match="Expected JSON"):
        _ = response_payload(b"not-json", "application/json")

    mutation_plan = plan_factory(
        body={"name": "demo"},
        confirmation_value=None,
        high_risk=False,
        method="POST",
        operation_id="tagmanager.accounts.create",
        query={},
        acceptable_scopes=("edit",),
        supports_page_token=False,
        url=url,
    )
    mutation_opener = install_opener(
        monkeypatch,
        [FakeResponse(b'{"accountId":"1"}', headers={"Content-Type": "application/json"})],
    )
    mutation = cast(
        "ApiResultView",
        send(mutation_plan, url, credential, argparse.Namespace(retries=5, timeout=1.0)),
    )
    assert mutation.payload == {"accountId": "1"}
    assert mutation_opener.requests[0].data == b'{"name":"demo"}'
    assert mutation_opener.requests[0].get_header("Content-type") == "application/json"

    terminal_failure = http_failure(url, 400)
    _ = install_opener(monkeypatch, [terminal_failure])
    terminal_arguments = argparse.Namespace(retries=0, timeout=1.0)
    with pytest.raises(helper_error, match="HTTP 400"):
        _ = send(plan, url, credential, terminal_arguments)
    assert terminal_failure.fp.closed
