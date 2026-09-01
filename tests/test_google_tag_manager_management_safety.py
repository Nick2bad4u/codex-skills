# Copyright (c) 2026 Nick2bad4u
"""Focused safety regressions for the Google Tag Manager helper."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from email.message import Message
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, Self, cast
from urllib import error, parse, request

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from types import ModuleType, TracebackType

type JsonValue = bool | int | float | str | list[JsonValue] | dict[str, JsonValue] | None

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "skills/google-tag-manager-management/scripts/manage_google_tag_manager.py"
BASE_URL = "https://tagmanager.googleapis.com/tagmanager/v2"
DISCOVERY_URL = "https://tagmanager.googleapis.com/$discovery/rest?version=v2"
TEST_CREDENTIAL = "gtm-review-credential-value"
HTTP_OK = 200
HTTP_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE")
RETRYABLE_STATUSES = (429, 500, 502, 503, 504)
EXPECTED_RETRY_ATTEMPTS = 2
CUMULATIVE_TEST_LIMIT = 10


class RequestPlanView(Protocol):
    """Typed view of a dynamically loaded request plan."""

    body: JsonValue
    confirmation_value: str | None
    url: str


class ApiResultView(Protocol):
    """Typed view of a dynamically loaded API result."""

    payload: JsonValue
    response_bytes: int


class FakeResponse:
    """Close-aware urllib response with observable bounded reads."""

    def __init__(
        self,
        payload: bytes,
        *,
        content_length: str | None = None,
        content_type: str = "application/json",
        status: int = HTTP_OK,
    ) -> None:
        """Initialize response bytes and optional transport metadata."""
        super().__init__()
        self.closed = False
        self.headers = Message()
        if content_length is not None:
            self.headers["Content-Length"] = content_length
        if content_type:
            self.headers["Content-Type"] = content_type
        self.payload = payload
        self.read_amounts: list[int | None] = []
        self.status = status

    def __enter__(self) -> Self:
        """Return the response for a urllib-style context manager."""
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close on successful and exceptional exits."""
        del exception_type, exception, traceback
        self.close()

    def close(self) -> None:
        """Record response closure."""
        self.closed = True

    def read(self, amount: int | None = None) -> bytes:
        """Return at most the requested bytes and record the bound."""
        self.read_amounts.append(amount)
        return self.payload if amount is None else self.payload[:amount]


class FakeOpener:
    """Consume deterministic transport outcomes and record request attempts."""

    def __init__(self, outcomes: list[FakeResponse | BaseException]) -> None:
        """Store ordered responses or failures."""
        super().__init__()
        self.outcomes = outcomes
        self.requests: list[request.Request] = []

    def open(self, api_request: request.Request, timeout: float) -> FakeResponse:
        """Return or raise the next configured outcome."""
        del timeout
        self.requests.append(api_request)
        if not self.outcomes:
            raise AssertionError("Fake opener exhausted its configured outcomes.")
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def load_script_module() -> ModuleType:
    """Load the helper without invoking its CLI entry point."""
    specification = importlib.util.spec_from_file_location("gtm_management_safety", SCRIPT_PATH)
    if specification is None or specification.loader is None:
        raise RuntimeError(f"Could not load test module: {SCRIPT_PATH}")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


GTM = load_script_module()


def member(name: str) -> object:
    """Return a dynamically loaded helper member."""
    return getattr(GTM, name)


def credential() -> object:
    """Build a synthetic OAuth credential."""
    factory = cast("Callable[..., object]", member("Credential"))
    return factory(environment="TEST_GTM_TOKEN", value=TEST_CREDENTIAL)


def context() -> object:
    """Build a production-origin helper context with a synthetic credential."""
    factory = cast("Callable[..., object]", member("GoogleTagManagerContext"))
    return factory(base_url=BASE_URL, credential=credential(), discovery_url=DISCOVERY_URL)


def install_opener(
    monkeypatch: pytest.MonkeyPatch,
    outcomes: list[FakeResponse | BaseException],
) -> FakeOpener:
    """Install one deterministic opener and return its request log."""
    opener = FakeOpener(outcomes)

    def build_opener(*_handlers: object) -> FakeOpener:
        return opener

    monkeypatch.setattr(request, "build_opener", build_opener)
    return opener


def http_failure(
    status: int,
    payload: bytes = b"{}",
    *,
    headers: Mapping[str, str] | None = None,
) -> error.HTTPError:
    """Build a readable HTTP error with deterministic headers."""
    message = Message()
    for name, value in (headers or {}).items():
        message[name] = value
    return error.HTTPError(f"{BASE_URL}/accounts", status, "fixture failure", message, BytesIO(payload))


def request_plan(method: str = "GET") -> RequestPlanView:
    """Build one synthetic plan for transport safety tests."""
    factory = cast("Callable[..., RequestPlanView]", member("RequestPlan"))
    return factory(
        body=None,
        confirmation_value=None,
        high_risk=False,
        method=method,
        operation_id="tagmanager.accounts.test",
        query={},
        acceptable_scopes=("readonly",),
        supports_page_token=method == "GET",
        url=f"{BASE_URL}/accounts",
    )


def discovery_document() -> bytes:
    """Return the smallest valid local/live Discovery fixture."""
    return b'{"name":"tagmanager","version":"v2","resources":{}}'


def ignore_sleep(_delay: float) -> None:
    """Replace retry sleeps in deterministic matrix tests."""


def raw_arguments(
    endpoint: str,
    *,
    body_json: str | None = None,
    method: str = "POST",
    query: list[str] | None = None,
) -> argparse.Namespace:
    """Build the arguments needed for a raw request plan."""
    return argparse.Namespace(
        allow_deprecated=False,
        body_file=None,
        body_json=body_json,
        discovery_file=None,
        endpoint=endpoint,
        method=method,
        operation_id=None,
        path_values=[],
        query=query or [],
    )


@pytest.mark.parametrize(
    ("arguments"),
    [
        raw_arguments("/accounts", method="GET", query=[f"quotaUser={TEST_CREDENTIAL}"]),
        raw_arguments(f"/accounts/{TEST_CREDENTIAL}", method="GET"),
        raw_arguments("/accounts", body_json=json.dumps({"value": TEST_CREDENTIAL})),
    ],
)
def test_resolved_oauth_credential_is_rejected_outside_authorization(arguments: argparse.Namespace) -> None:
    """A credential cannot be hidden in a path, query, or body."""
    build_plan = cast("Callable[[argparse.Namespace, object], RequestPlanView]", member("build_plan"))
    helper_error = cast("type[Exception]", member("GoogleTagManagerCliError"))

    with pytest.raises(helper_error) as caught:
        _ = build_plan(arguments, context())

    assert "Authorization header" in str(caught.value)
    assert TEST_CREDENTIAL not in str(caught.value)


def test_send_rechecks_credential_before_constructing_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    """Direct plans cannot bypass the outbound credential-reuse guard."""
    plan_factory = cast("Callable[..., RequestPlanView]", member("RequestPlan"))
    send = cast("Callable[..., object]", member("send_request"))
    helper_error = cast("type[Exception]", member("GoogleTagManagerCliError"))
    plan = plan_factory(
        body={"value": TEST_CREDENTIAL},
        confirmation_value=None,
        high_risk=False,
        method="POST",
        operation_id=None,
        query={},
        acceptable_scopes=(),
        supports_page_token=False,
        url=f"{BASE_URL}/accounts",
    )
    opener_built = False

    def build_opener(*_handlers: object) -> object:
        nonlocal opener_built
        opener_built = True
        raise AssertionError("Transport must not be constructed for credential reuse.")

    monkeypatch.setattr(request, "build_opener", build_opener)
    with pytest.raises(helper_error, match="Authorization header"):
        _ = send(plan, plan.url, credential(), argparse.Namespace(retries=0, timeout=1.0))
    assert not opener_built


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity", '{"nested":[NaN]}'])
def test_non_standard_json_numbers_are_rejected_without_partial_output(
    value: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Bodies and API payloads accept only standards-compliant JSON numbers."""
    load_body = cast("Callable[[argparse.Namespace], JsonValue]", member("load_body"))
    response_payload = cast("Callable[[bytes, str], JsonValue]", member("response_payload"))
    helper_error = cast("type[Exception]", member("GoogleTagManagerCliError"))

    with pytest.raises(helper_error, match="standards-compliant"):
        _ = load_body(argparse.Namespace(body_file=None, body_json=value))
    with pytest.raises(helper_error, match="standards-compliant"):
        _ = response_payload(value.encode(), "application/json")
    assert capsys.readouterr().out == ""


def test_json_output_rejects_non_finite_values_before_writing(capsys: pytest.CaptureFixture[str]) -> None:
    """Output serialization never emits Python's invalid JSON extensions."""
    write_json = cast("Callable[[JsonValue], None]", member("write_json"))
    helper_error = cast("type[Exception]", member("GoogleTagManagerCliError"))

    with pytest.raises(helper_error, match="non-finite"):
        write_json({"value": float("nan")})
    assert capsys.readouterr().out == ""


def test_preview_result_and_transport_errors_defensively_redact_known_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """All emitted metadata and transport reasons redact a known token."""
    plan_factory = cast("Callable[..., RequestPlanView]", member("RequestPlan"))
    result_factory = cast("Callable[..., object]", member("ApiResult"))
    preview_payload = cast("Callable[..., dict[str, JsonValue]]", member("preview_payload"))
    result_payload = cast("Callable[..., dict[str, JsonValue]]", member("result_payload"))
    send = cast("Callable[..., object]", member("send_request"))
    helper_error = cast("type[Exception]", member("GoogleTagManagerCliError"))
    encoded = parse.quote_plus(TEST_CREDENTIAL)
    url = f"{BASE_URL}/accounts?quotaUser={encoded}"
    plan = plan_factory(
        body=None,
        confirmation_value=f"POST /accounts?quotaUser={encoded}",
        high_risk=True,
        method="POST",
        operation_id=None,
        query={},
        acceptable_scopes=(),
        supports_page_token=False,
        url=f"{BASE_URL}/accounts",
    )
    preview = preview_payload(plan, context(), url)
    result = result_payload(result_factory(payload={}, status=200, url=url), credential())
    assert TEST_CREDENTIAL not in json.dumps(preview)
    assert encoded not in json.dumps(preview)
    assert TEST_CREDENTIAL not in json.dumps(result)
    assert encoded not in json.dumps(result)

    safe_plan = plan_factory(
        body=None,
        confirmation_value=None,
        high_risk=False,
        method="GET",
        operation_id=None,
        query={},
        acceptable_scopes=(),
        supports_page_token=False,
        url=f"{BASE_URL}/accounts",
    )

    class FailingOpener:
        """Raise one credential-bearing transport error."""

        def open(self, *_arguments: object, **_keywords: object) -> object:
            """Raise a deterministic URL error."""
            raise error.URLError(f"offline {TEST_CREDENTIAL}")

    def build_failing_opener(*_handlers: object) -> FailingOpener:
        return FailingOpener()

    monkeypatch.setattr(request, "build_opener", build_failing_opener)
    with pytest.raises(helper_error) as caught:
        _ = send(safe_plan, safe_plan.url, credential(), argparse.Namespace(retries=0, timeout=1.0))
    assert TEST_CREDENTIAL not in str(caught.value)
    assert "<redacted>" in str(caught.value)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("0", 0.0),
        ("NaN", 4.0),
        ("Infinity", 4.0),
        ("-1", 4.0),
        ("invalid", 4.0),
    ],
)
def test_retry_after_is_finite_and_bounded(value: str, expected: float) -> None:
    """Invalid Retry-After values use the bounded exponential fallback."""
    retry_delay = cast("Callable[[error.HTTPError, int], float]", member("retry_delay"))
    headers = Message()
    headers["Retry-After"] = value
    failure = error.HTTPError(f"{BASE_URL}/accounts", 429, "retry", headers, BytesIO())
    try:
        assert retry_delay(failure, 2) == expected
    finally:
        failure.close()


def test_local_discovery_enforces_exact_actual_byte_boundary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Local Discovery reads accept the exact limit and reject one additional byte."""
    load_discovery = cast("Callable[..., object]", member("load_discovery"))
    helper_error = cast("type[Exception]", member("GoogleTagManagerCliError"))
    document = discovery_document()
    path = tmp_path / "tagmanager-v2.json"
    _ = path.write_bytes(document)
    arguments = argparse.Namespace(discovery_file=path, timeout=1.0)

    monkeypatch.setattr(GTM, "MAX_DISCOVERY_DOCUMENT_BYTES", len(document))
    assert load_discovery(arguments, context()) == json.loads(document)

    monkeypatch.setattr(GTM, "MAX_DISCOVERY_DOCUMENT_BYTES", len(document) - 1)
    with pytest.raises(helper_error, match=r"Discovery document.*safety limit"):
        _ = load_discovery(arguments, context())


@pytest.mark.parametrize("content_length", [None, str(len(discovery_document()))])
def test_remote_discovery_accepts_exact_boundary_and_closes(
    monkeypatch: pytest.MonkeyPatch,
    content_length: str | None,
) -> None:
    """Remote Discovery accepts exact bytes with honest or missing length metadata."""
    load_discovery = cast("Callable[..., object]", member("load_discovery"))
    document = discovery_document()
    response = FakeResponse(document, content_length=content_length)
    _ = install_opener(monkeypatch, [response])
    monkeypatch.setattr(GTM, "MAX_DISCOVERY_DOCUMENT_BYTES", len(document))

    assert load_discovery(argparse.Namespace(discovery_file=None, timeout=1.0), context()) == json.loads(document)
    assert response.read_amounts == [len(document) + 1]
    assert response.closed


def test_remote_discovery_rejects_dishonest_or_oversized_content_length(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Actual bytes defeat an understated length and numeric overage fails before reading."""
    load_discovery = cast("Callable[..., object]", member("load_discovery"))
    helper_error = cast("type[Exception]", member("GoogleTagManagerCliError"))
    document = discovery_document()
    limit = len(document) - 1
    dishonest = FakeResponse(document, content_length="1")
    _ = install_opener(monkeypatch, [dishonest])
    monkeypatch.setattr(GTM, "MAX_DISCOVERY_DOCUMENT_BYTES", limit)

    with pytest.raises(helper_error, match=r"Discovery response.*safety limit"):
        _ = load_discovery(argparse.Namespace(discovery_file=None, timeout=1.0), context())
    assert dishonest.read_amounts == [limit + 1]
    assert dishonest.closed

    declared_over = FakeResponse(document[:limit], content_length=str(limit + 1))
    _ = install_opener(monkeypatch, [declared_over])
    with pytest.raises(helper_error, match=r"Discovery response.*safety limit"):
        _ = load_discovery(argparse.Namespace(discovery_file=None, timeout=1.0), context())
    assert declared_over.read_amounts == []
    assert declared_over.closed


@pytest.mark.parametrize("content_length", [None, str(len(b'{"ok":true}'))])
def test_success_body_accepts_exact_boundary_and_tracks_bytes(
    monkeypatch: pytest.MonkeyPatch,
    content_length: str | None,
) -> None:
    """Successful API bodies accept exact actual bytes without trusting a required header."""
    send = cast("Callable[..., ApiResultView]", member("send_request"))
    payload = b'{"ok":true}'
    response = FakeResponse(payload, content_length=content_length)
    _ = install_opener(monkeypatch, [response])
    monkeypatch.setattr(GTM, "MAX_API_RESPONSE_BYTES", len(payload))

    result = send(request_plan(), f"{BASE_URL}/accounts", credential(), argparse.Namespace(retries=0, timeout=1.0))
    assert result.payload == {"ok": True}
    assert result.response_bytes == len(payload)
    assert response.read_amounts == [len(payload) + 1]
    assert response.closed


def test_success_body_rejects_one_byte_over_with_dishonest_length(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An understated success Content-Length cannot bypass the actual-byte limit."""
    send = cast("Callable[..., ApiResultView]", member("send_request"))
    helper_error = cast("type[Exception]", member("GoogleTagManagerCliError"))
    payload = b'{"ok":true}'
    limit = len(payload) - 1
    response = FakeResponse(payload, content_length="1")
    _ = install_opener(monkeypatch, [response])
    monkeypatch.setattr(GTM, "MAX_API_RESPONSE_BYTES", limit)

    with pytest.raises(helper_error, match=r"API response.*safety limit"):
        _ = send(request_plan(), f"{BASE_URL}/accounts", credential(), argparse.Namespace(retries=0, timeout=1.0))
    assert response.read_amounts == [limit + 1]
    assert response.closed


@pytest.mark.parametrize("content_length", [None, str(len(b'{"error":"denied"}'))])
def test_error_body_accepts_exact_boundary_and_always_closes(
    monkeypatch: pytest.MonkeyPatch,
    content_length: str | None,
) -> None:
    """HTTP error bodies are bounded even with absent length metadata."""
    send = cast("Callable[..., object]", member("send_request"))
    helper_error = cast("type[Exception]", member("GoogleTagManagerCliError"))
    payload = b'{"error":"denied"}'
    headers = {"Content-Type": "application/json"}
    if content_length is not None:
        headers["Content-Length"] = content_length
    failure = http_failure(400, payload, headers=headers)
    _ = install_opener(monkeypatch, [failure])
    monkeypatch.setattr(GTM, "MAX_ERROR_RESPONSE_BYTES", len(payload))

    with pytest.raises(helper_error, match="HTTP 400"):
        _ = send(request_plan(), f"{BASE_URL}/accounts", credential(), argparse.Namespace(retries=0, timeout=1.0))
    assert failure.fp.closed


def test_error_body_rejects_one_byte_over_with_dishonest_length(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An understated error Content-Length cannot bypass the actual-byte limit."""
    send = cast("Callable[..., object]", member("send_request"))
    helper_error = cast("type[Exception]", member("GoogleTagManagerCliError"))
    payload = b'{"error":"denied"}'
    limit = len(payload) - 1
    failure = http_failure(
        400,
        payload,
        headers={"Content-Length": "1", "Content-Type": "application/json"},
    )
    _ = install_opener(monkeypatch, [failure])
    monkeypatch.setattr(GTM, "MAX_ERROR_RESPONSE_BYTES", limit)

    with pytest.raises(helper_error, match=r"error response.*safety limit"):
        _ = send(request_plan(), f"{BASE_URL}/accounts", credential(), argparse.Namespace(retries=0, timeout=1.0))
    assert failure.fp.closed


def test_discovery_error_body_is_bounded_and_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remote Discovery failures apply the error-body limit and close their response."""
    load_discovery = cast("Callable[..., object]", member("load_discovery"))
    helper_error = cast("type[Exception]", member("GoogleTagManagerCliError"))
    payload = b"oversized"
    failure = http_failure(503, payload, headers={"Content-Length": "1"})
    _ = install_opener(monkeypatch, [failure])
    monkeypatch.setattr(GTM, "MAX_ERROR_RESPONSE_BYTES", len(payload) - 1)

    with pytest.raises(helper_error, match=r"error response.*safety limit"):
        _ = load_discovery(argparse.Namespace(discovery_file=None, timeout=1.0), context())
    assert failure.fp.closed


@pytest.mark.parametrize("method", HTTP_METHODS)
@pytest.mark.parametrize("status", [400, *RETRYABLE_STATUSES])
def test_method_and_http_status_retry_matrix(
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    status: int,
) -> None:
    """Only GET replays retryable HTTP statuses; writes remain single-attempt and explicit."""
    send = cast("Callable[..., ApiResultView]", member("send_request"))
    helper_error = cast("type[Exception]", member("GoogleTagManagerCliError"))
    failure = http_failure(status, headers={"Content-Type": "application/json", "Retry-After": "0"})
    success = FakeResponse(b'{"ok":true}')
    opener = install_opener(monkeypatch, [failure, success])
    monkeypatch.setattr(time, "sleep", ignore_sleep)

    if method == "GET" and status in RETRYABLE_STATUSES:
        assert send(
            request_plan(method),
            f"{BASE_URL}/accounts",
            credential(),
            argparse.Namespace(retries=1, timeout=1.0),
        ).payload == {"ok": True}
        assert len(opener.requests) == EXPECTED_RETRY_ATTEMPTS
    else:
        with pytest.raises(helper_error) as caught:
            _ = send(
                request_plan(method),
                f"{BASE_URL}/accounts",
                credential(),
                argparse.Namespace(retries=1, timeout=1.0),
            )
        assert len(opener.requests) == 1
        message = str(caught.value)
        if method != "GET" and status in RETRYABLE_STATUSES:
            assert "attempted exactly once" in message
            assert "may have taken effect" in message
            assert "outcome is indeterminate" in message
            assert "Verify current Google Tag Manager state before retrying manually" in message
        else:
            assert "indeterminate" not in message
    assert failure.fp.closed


@pytest.mark.parametrize("method", HTTP_METHODS)
@pytest.mark.parametrize("transport_failure", [error.URLError("offline"), TimeoutError("timed out")])
def test_method_and_transport_failure_retry_matrix(
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    transport_failure: BaseException,
) -> None:
    """GET alone replays URL/timeout failures; every write reports an indeterminate outcome."""
    send = cast("Callable[..., ApiResultView]", member("send_request"))
    helper_error = cast("type[Exception]", member("GoogleTagManagerCliError"))
    opener = install_opener(monkeypatch, [transport_failure, FakeResponse(b'{"ok":true}')])
    monkeypatch.setattr(time, "sleep", ignore_sleep)

    if method == "GET":
        assert send(
            request_plan(method),
            f"{BASE_URL}/accounts",
            credential(),
            argparse.Namespace(retries=1, timeout=1.0),
        ).payload == {"ok": True}
        assert len(opener.requests) == EXPECTED_RETRY_ATTEMPTS
        return

    with pytest.raises(helper_error) as caught:
        _ = send(
            request_plan(method),
            f"{BASE_URL}/accounts",
            credential(),
            argparse.Namespace(retries=5, timeout=1.0),
        )
    assert len(opener.requests) == 1
    message = str(caught.value)
    assert "attempted exactly once" in message
    assert "may have taken effect" in message
    assert "outcome is indeterminate" in message
    assert "Verify current Google Tag Manager state before retrying manually" in message


@pytest.mark.parametrize("method", ["HEAD", "OPTIONS", "TRACE"])
def test_unsupported_discovery_and_raw_methods_are_rejected(method: str) -> None:
    """Discovery metadata and direct plan building accept only the five CLI methods."""
    parse_method = cast("Callable[[JsonValue], object | None]", member("parse_method"))
    build_plan = cast("Callable[[argparse.Namespace, object], object]", member("build_plan"))
    helper_error = cast("type[Exception]", member("GoogleTagManagerCliError"))
    with pytest.raises(helper_error, match="Unsupported Discovery HTTP method"):
        _ = parse_method(
            {
                "id": "tagmanager.accounts.unsupported",
                "path": "tagmanager/v2/accounts",
                "httpMethod": method,
            }
        )
    with pytest.raises(helper_error, match="Unsupported HTTP method"):
        _ = build_plan(raw_arguments("/accounts", method=method), context())


@pytest.mark.parametrize(
    "payload",
    [
        b"unknownCredentialType=secret-value",
        b"payload=https%3A%2F%2Fexample.test%2Fcollect%3Fmystery%3Dsecret-value",
        f"form=active-{TEST_CREDENTIAL}".encode(),
        b"invalid-utf8-\xff\xfe",
    ],
)
def test_unexpected_non_json_success_body_is_always_omitted(payload: bytes) -> None:
    """Arbitrary text, nested form/URL data, active tokens, and invalid UTF-8 are never emitted."""
    response_payload = cast("Callable[[bytes, str], JsonValue]", member("response_payload"))
    marker = "[untrusted-gtm-text] non-JSON response body omitted"
    result = response_payload(payload, "text/plain")
    assert result == marker
    rendered = json.dumps(result)
    assert TEST_CREDENTIAL not in rendered
    assert "secret-value" not in rendered
    assert "example.test" not in rendered
    assert "unknownCredentialType" not in rendered


def test_cumulative_pagination_accepts_exact_limit_and_reports_bytes(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Pages totaling the cumulative byte boundary are retained and accounted for."""
    write_pages = cast("Callable[..., None]", member("write_paginated_results"))
    result_factory = cast("Callable[..., object]", member("ApiResult"))
    results = iter(
        [
            result_factory(payload={"nextPageToken": "two"}, status=200, url=f"{BASE_URL}/accounts", response_bytes=5),
            result_factory(payload={"account": []}, status=200, url=f"{BASE_URL}/accounts", response_bytes=5),
        ]
    )

    def fake_send(*_args: object, **_kwargs: object) -> object:
        return next(results)

    monkeypatch.setattr(GTM, "send_request", fake_send)
    monkeypatch.setattr(GTM, "MAX_PAGINATED_RESPONSE_BYTES", CUMULATIVE_TEST_LIMIT)

    write_pages(argparse.Namespace(max_pages=2), request_plan(), credential())
    output = json.loads(capsys.readouterr().out)
    assert output["pageCount"] == EXPECTED_RETRY_ATTEMPTS
    assert output["responseBytes"] == CUMULATIVE_TEST_LIMIT


def test_cumulative_pagination_rejects_before_retaining_overflow_page(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A one-byte cumulative overflow fails before the second page enters retained output."""
    write_pages = cast("Callable[..., None]", member("write_paginated_results"))
    result_factory = cast("Callable[..., object]", member("ApiResult"))
    original_result_payload = cast("Callable[..., dict[str, JsonValue]]", member("result_payload"))
    helper_error = cast("type[Exception]", member("GoogleTagManagerCliError"))
    retained: list[int] = []
    results = iter(
        [
            result_factory(payload={"nextPageToken": "two"}, status=200, url=f"{BASE_URL}/accounts", response_bytes=5),
            result_factory(payload={"account": []}, status=200, url=f"{BASE_URL}/accounts", response_bytes=6),
        ]
    )

    def track_result(result: ApiResultView, active_credential: object) -> dict[str, JsonValue]:
        retained.append(result.response_bytes)
        return original_result_payload(result, active_credential)

    def fake_send(*_args: object, **_kwargs: object) -> object:
        return next(results)

    monkeypatch.setattr(GTM, "send_request", fake_send)
    monkeypatch.setattr(GTM, "result_payload", track_result)
    monkeypatch.setattr(GTM, "MAX_PAGINATED_RESPONSE_BYTES", CUMULATIVE_TEST_LIMIT)

    with pytest.raises(helper_error, match="cumulative safety limit"):
        write_pages(argparse.Namespace(max_pages=2), request_plan(), credential())
    assert retained == [5]
    assert capsys.readouterr().out == ""
