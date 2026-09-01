# Copyright (c) 2026 Nick2bad4u
"""Focused safety regressions for the StepSecurity management helper."""

from __future__ import annotations

import argparse
import http.client
import importlib.util
import json
import math
import sys
import time
from email.message import Message
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, Self, cast, override
from urllib import error, request

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from types import ModuleType, TracebackType

type TransportOutcome = FakeResponse | BaseException

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "skills/stepsecurity-management/scripts/manage_stepsecurity.py"
BASE_URL = "https://agent.api.stepsecurity.io/v1"
API_URL = f"{BASE_URL}/items"
HTTP_OK = 200
HTTP_BAD_REQUEST = 400
HTTP_SERVICE_UNAVAILABLE = 503
EXPECTED_PAGE_COUNT = 2
NATURAL_MAX_PAGES = 3
DEFAULT_MAX_PAGES = 10
MAX_SAFE_ERROR_MESSAGE_LENGTH = 1400
CLI_ERROR_EXIT = 2
REDIRECT_CODES = (301, 302, 303, 307, 308)
WRITE_METHODS = ("POST", "PUT", "PATCH", "DELETE")
RETRYABLE_WRITE_STATUSES = (429, 502, 503, 504)
TRANSPORT_FAILURE_KINDS = ("connection-reset", "os-error", "incomplete-read", "http-exception")


class ApiResultView(Protocol):
    """Structural view of a dynamically loaded API result."""

    payload: object


class RecordingStream(BytesIO):
    """Bytes stream that records every requested read bound."""

    def __init__(self, body: bytes, *, close_failure: BaseException | None = None) -> None:
        """Initialize the stream and its read log."""
        super().__init__(body)
        self._close_failure = close_failure
        self.close_attempts = 0
        self.read_sizes: list[int] = []

    @override
    def close(self) -> None:
        """Record closure and optionally raise before the stream can close."""
        self.close_attempts += 1
        failure = self._close_failure
        self._close_failure = None
        if failure is not None:
            raise failure
        super().close()

    @override
    def read(self, size: int | None = -1) -> bytes:
        """Record and honor the requested byte count."""
        self.read_sizes.append(-1 if size is None else size)
        return super().read(size)


class FakeResponse:
    """Small urllib-compatible success response with closure evidence."""

    def __init__(
        self,
        body: bytes,
        *,
        content_length: str | None = None,
        content_type: str = "application/json",
        close_failure: BaseException | None = None,
        read_failure: BaseException | None = None,
    ) -> None:
        """Initialize a bounded response fixture."""
        super().__init__()
        self._stream = RecordingStream(body, close_failure=close_failure)
        self.headers = Message()
        self.headers["Content-Type"] = content_type
        if content_length is not None:
            self.headers["Content-Length"] = content_length
        self._read_failure = read_failure
        self.status = HTTP_OK

    @property
    def closed(self) -> bool:
        """Report whether the response stream was closed."""
        return self._stream.closed

    @property
    def read_sizes(self) -> list[int]:
        """Expose recorded read bounds."""
        return self._stream.read_sizes

    @property
    def close_attempts(self) -> int:
        """Expose the number of response closure attempts."""
        return self._stream.close_attempts

    def __enter__(self) -> Self:
        """Enter a urllib-style response context."""
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close the response even when bounded decoding raises."""
        del exception_type, exception, traceback
        self.close()

    def close(self) -> None:
        """Close the underlying response stream."""
        self._stream.close()

    def read(self, size: int | None = -1) -> bytes:
        """Read through the recording stream."""
        if self._read_failure is not None:
            self._stream.read_sizes.append(-1 if size is None else size)
            raise self._read_failure
        return self._stream.read(size)


class FailingStream(RecordingStream):
    """Closable HTTP-error body that raises a deterministic read failure."""

    def __init__(self, failure: BaseException) -> None:
        """Initialize the stream with one read failure."""
        super().__init__(b"")
        self._failure = failure

    @override
    def read(self, size: int | None = -1) -> bytes:
        """Record the bound and raise the configured failure."""
        self.read_sizes.append(-1 if size is None else size)
        raise self._failure


class FakeOpener:
    """Consume deterministic responses and transport errors."""

    def __init__(self, outcomes: list[TransportOutcome]) -> None:
        """Initialize ordered outcomes and an empty request log."""
        super().__init__()
        self._outcomes = iter(outcomes)
        self.requests: list[request.Request] = []

    def open(self, api_request: request.Request, *, timeout: float) -> FakeResponse:
        """Record the request and return or raise the next outcome."""
        del timeout
        self.requests.append(api_request)
        outcome = next(self._outcomes)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def load_script_module() -> ModuleType:
    """Load the StepSecurity helper without invoking its CLI."""
    specification = importlib.util.spec_from_file_location("stepsecurity_management_safety", SCRIPT_PATH)
    if specification is None or specification.loader is None:
        raise RuntimeError(f"Could not load test module: {SCRIPT_PATH}")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


STEPSECURITY = load_script_module()


def member(name: str) -> object:
    """Return one dynamically loaded helper member."""
    return getattr(STEPSECURITY, name)


def runtime(
    *,
    max_response_bytes: int | None = None,
    retries: int = 0,
    timeout: float = 1.0,
) -> object:
    """Create a bounded request runtime."""
    runtime_factory = cast("Callable[..., object]", member("RequestRuntime"))
    if max_response_bytes is None:
        return runtime_factory(retries=retries, timeout=timeout)
    return runtime_factory(max_response_bytes=max_response_bytes, retries=retries, timeout=timeout)


def http_headers(values: Mapping[str, str] | None = None) -> Message:
    """Create HTTPMessage-compatible fixture headers."""
    headers = Message()
    for name, value in (values or {}).items():
        headers[name] = value
    return headers


def http_failure(
    status: int,
    body: bytes = b"",
    *,
    close_failure: BaseException | None = None,
    headers: Mapping[str, str] | None = None,
    url: str = API_URL,
) -> tuple[error.HTTPError, RecordingStream]:
    """Create an HTTP failure and retain its closable body stream."""
    stream = RecordingStream(body, close_failure=close_failure)
    failure = error.HTTPError(url, status, "fixture failure", http_headers(headers), stream)
    return failure, stream


def transport_failure(kind: str, credential_value: str) -> BaseException:
    """Create one long credential-bearing transport failure."""
    detail = f"Bearer {credential_value} " + ("x" * 5000)
    match kind:
        case "connection-reset":
            return ConnectionResetError(detail)
        case "os-error":
            return OSError(detail)
        case "incomplete-read":
            return http.client.IncompleteRead(detail.encode(), 1)
        case "http-exception":
            return http.client.HTTPException(detail)
        case _:
            raise AssertionError(f"Unknown transport failure fixture: {kind}")


def body_failure_outcome(
    response_kind: str,
    failure: BaseException,
) -> tuple[TransportOutcome, FakeResponse | FailingStream]:
    """Create a success or HTTP-error response whose body read fails."""
    if response_kind == "success-body":
        response = FakeResponse(b"", read_failure=failure)
        return response, response
    if response_kind == "http-error-body":
        stream = FailingStream(failure)
        http_error = error.HTTPError(
            API_URL,
            HTTP_BAD_REQUEST,
            "fixture failure",
            http_headers({"Content-Type": "application/json"}),
            stream,
        )
        return http_error, stream
    raise AssertionError(f"Unknown response fixture: {response_kind}")


def response_outcome(
    response_kind: str,
    body: bytes,
    *,
    close_failure: BaseException | None = None,
    content_type: str = "application/json",
) -> tuple[TransportOutcome, FakeResponse | RecordingStream]:
    """Create one closable success or HTTP-error response."""
    if response_kind == "success-body":
        response = FakeResponse(body, close_failure=close_failure, content_type=content_type)
        return response, response
    if response_kind == "http-error-body":
        return http_failure(
            HTTP_BAD_REQUEST,
            body,
            close_failure=close_failure,
            headers={"Content-Type": content_type},
        )
    raise AssertionError(f"Unknown response fixture: {response_kind}")


def nested_json(depth: int, leaf: str) -> bytes:
    """Build deterministic nested valid JSON without recursive Python objects."""
    return (("[" * depth) + json.dumps(leaf) + ("]" * depth)).encode()


def nested_value(depth: int, leaf: object) -> object:
    """Build an in-memory nested JSON value iteratively."""
    value = leaf
    for _index in range(depth):
        value = [value]
    return value


def nested_leaf(value: object) -> object:
    """Unwrap a single-child nested list iteratively."""
    current = value
    while isinstance(current, list):
        items = cast("list[object]", current)
        assert len(items) == 1
        current = items[0]
    return current


def install_opener(monkeypatch: pytest.MonkeyPatch, outcomes: list[TransportOutcome]) -> FakeOpener:
    """Install a deterministic opener for the dynamically loaded helper."""
    opener = FakeOpener(outcomes)

    def build_opener(*_handlers: object) -> FakeOpener:
        return opener

    monkeypatch.setattr(request, "build_opener", build_opener)
    return opener


def send_result(
    method: str,
    *,
    max_response_bytes: int | None = None,
    request_runtime: object | None = None,
) -> object:
    """Invoke the sized StepSecurity transport boundary."""
    send = cast("Callable[..., object]", member("send_result"))
    selected_runtime = request_runtime or runtime(max_response_bytes=max_response_bytes)
    return send(method, API_URL, {"Authorization": "Bearer fixture"}, None, selected_runtime)


@pytest.mark.parametrize("status", REDIRECT_CODES)
def test_get_follows_each_redirect_code_once_and_closes_every_response(
    monkeypatch: pytest.MonkeyPatch,
    status: int,
) -> None:
    """Every supported read redirect is validated, followed, and closed."""
    redirect, stream = http_failure(status, headers={"Location": "/v1/items?page=2"})
    success = FakeResponse(b'{"data":[]}')
    opener = install_opener(monkeypatch, [redirect, success])

    result = cast("ApiResultView", send_result("GET"))

    assert result.payload == {"data": []}
    assert [item.full_url for item in opener.requests] == [API_URL, f"{API_URL}?page=2"]
    assert stream.closed
    assert success.closed


@pytest.mark.parametrize("method", WRITE_METHODS)
@pytest.mark.parametrize("status", REDIRECT_CODES)
def test_write_redirects_are_rejected_before_a_second_request(
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    status: int,
) -> None:
    """Mutation credentials and bodies never cross even an in-origin redirect."""
    helper_error = cast("type[Exception]", member("StepSecurityError"))
    redirect, stream = http_failure(status, headers={"Location": "/v1/items/redirected"})
    opener = install_opener(monkeypatch, [redirect, FakeResponse(b'{"unexpected":true}')])

    with pytest.raises(helper_error, match=rf"HTTP {status} redirect for {method}") as caught:
        _ = send_result(method)

    assert "indeterminate" in str(caught.value)
    assert "audit log" in str(caught.value)
    assert len(opener.requests) == 1
    assert stream.closed


def test_get_redirect_cycle_is_rejected_and_all_errors_are_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """A redirect target already visited cannot cause an infinite request loop."""
    helper_error = cast("type[Exception]", member("StepSecurityError"))
    first, first_stream = http_failure(302, headers={"Location": "?page=2"})
    second, second_stream = http_failure(302, headers={"Location": API_URL}, url=f"{API_URL}?page=2")
    opener = install_opener(monkeypatch, [first, second])

    with pytest.raises(helper_error, match="redirect cycle"):
        _ = send_result("GET")

    assert len(opener.requests) == EXPECTED_PAGE_COUNT
    assert first_stream.closed
    assert second_stream.closed


def test_get_redirect_budget_allows_its_boundary_and_rejects_the_next_hop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Redirect traversal has a small budget independent of retries."""
    helper_error = cast("type[Exception]", member("StepSecurityError"))
    redirect_limit = cast("int", member("MAX_REDIRECTS"))
    allowed_failures: list[error.HTTPError] = []
    allowed_streams: list[RecordingStream] = []
    for hop in range(1, redirect_limit + 1):
        failure, stream = http_failure(302, headers={"Location": f"?hop={hop}"})
        allowed_failures.append(failure)
        allowed_streams.append(stream)
    success = FakeResponse(b'{"ok":true}')
    allowed_opener = install_opener(monkeypatch, [*allowed_failures, success])

    result = cast("ApiResultView", send_result("GET", request_runtime=runtime(retries=10)))

    assert result.payload == {"ok": True}
    assert len(allowed_opener.requests) == redirect_limit + 1
    assert all(stream.closed for stream in allowed_streams)
    assert success.closed

    rejected_failures: list[TransportOutcome] = []
    rejected_streams: list[RecordingStream] = []
    for hop in range(1, redirect_limit + 2):
        failure, stream = http_failure(302, headers={"Location": f"?overflow={hop}"})
        rejected_failures.append(failure)
        rejected_streams.append(stream)
    rejected_opener = install_opener(monkeypatch, rejected_failures)

    with pytest.raises(helper_error, match=rf"redirect limit of {redirect_limit}"):
        _ = send_result("GET", request_runtime=runtime(retries=0))

    assert len(rejected_opener.requests) == redirect_limit + 1
    assert all(stream.closed for stream in rejected_streams)


def test_invalid_read_redirect_is_rejected_and_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Read redirects retain the production-origin and base-path lock."""
    helper_error = cast("type[Exception]", member("StepSecurityError"))
    redirect, stream = http_failure(302, headers={"Location": "https://example.com/v1/items"})
    opener = install_opener(monkeypatch, [redirect])

    with pytest.raises(helper_error, match="production origin"):
        _ = send_result("GET")

    assert len(opener.requests) == 1
    assert stream.closed


def test_get_retry_behavior_is_preserved_and_failures_are_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Transient GET retries remain independent from the redirect budget."""
    retry, retry_stream = http_failure(
        HTTP_SERVICE_UNAVAILABLE,
        b'{"message":"temporary"}',
        headers={"Content-Type": "application/json", "Retry-After": "0"},
    )
    success = FakeResponse(b'{"ok":true}')
    opener = install_opener(monkeypatch, [retry, success])
    sleeps: list[float] = []
    monkeypatch.setattr(time, "sleep", sleeps.append)

    result = cast("ApiResultView", send_result("GET", request_runtime=runtime(retries=1)))

    assert result.payload == {"ok": True}
    assert len(opener.requests) == EXPECTED_PAGE_COUNT
    assert sleeps == [0.0]
    assert retry_stream.closed
    assert success.closed


@pytest.mark.parametrize("method", WRITE_METHODS)
@pytest.mark.parametrize("status", RETRYABLE_WRITE_STATUSES)
def test_write_http_failures_are_single_attempt_redacted_and_indeterminate(
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    status: int,
) -> None:
    """Every ambiguous write status requires remote-state verification before retry."""
    helper_error = cast("type[Exception]", member("StepSecurityError"))
    credential_value = "transport-secret"
    failure, stream = http_failure(
        status,
        f'{{"authorization":"Bearer {credential_value}"}}'.encode(),
        headers={"Content-Type": "application/json", "Retry-After": "0"},
    )
    opener = install_opener(monkeypatch, [failure, FakeResponse(b'{"unexpected":true}')])
    sleeps: list[float] = []
    monkeypatch.setattr(time, "sleep", sleeps.append)
    send = cast("Callable[..., object]", member("send_result"))

    with pytest.raises(helper_error, match=r"(?i)indeterminate.*audit log") as caught:
        _ = send(
            method,
            API_URL,
            {"Authorization": f"Bearer {credential_value}"},
            None,
            runtime(retries=10),
        )

    assert credential_value not in str(caught.value)
    assert "<redacted>" in str(caught.value)
    assert len(opener.requests) == 1
    assert sleeps == []
    assert stream.closed


@pytest.mark.parametrize("method", ["GET", *WRITE_METHODS])
@pytest.mark.parametrize(
    "failure_kind",
    ["url-error", "timeout", *TRANSPORT_FAILURE_KINDS],
)
def test_transport_failures_are_bounded_redacted_and_writes_are_indeterminate(
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    failure_kind: str,
) -> None:
    """Transport exception text cannot bypass redaction or write-recovery guidance."""
    helper_error = cast("type[Exception]", member("StepSecurityError"))
    credential_value = "transport-secret"
    reason = f"Bearer {credential_value} " + ("x" * 5000)
    if failure_kind == "url-error":
        failure: BaseException = error.URLError(reason)
    elif failure_kind == "timeout":
        failure = TimeoutError(reason)
    else:
        failure = transport_failure(failure_kind, credential_value)
    opener = install_opener(monkeypatch, [failure, FakeResponse(b'{"unexpected":true}')])
    send = cast("Callable[..., object]", member("send_result"))

    with pytest.raises(helper_error) as caught:
        _ = send(
            method,
            API_URL,
            {"Authorization": f"Bearer {credential_value}"},
            None,
            runtime(retries=10),
        )

    message = str(caught.value)
    assert credential_value not in message
    if failure_kind != "incomplete-read":
        assert "<redacted>" in message
    assert len(message) < MAX_SAFE_ERROR_MESSAGE_LENGTH
    assert ("indeterminate" in message) is (method != "GET")
    assert len(opener.requests) == 1


@pytest.mark.parametrize("method", ["GET", *WRITE_METHODS])
@pytest.mark.parametrize("response_kind", ["success-body", "http-error-body"])
@pytest.mark.parametrize("failure_kind", TRANSPORT_FAILURE_KINDS)
def test_body_transport_failures_are_safe_closed_single_attempt_and_cli_clean(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    method: str,
    response_kind: str,
    failure_kind: str,
) -> None:
    """Every body-read transport class has the same safe API and CLI boundary."""
    helper_error = cast("type[Exception]", member("StepSecurityError"))
    credential_value = "body-read-secret"
    failure = transport_failure(failure_kind, credential_value)
    outcome, close_evidence = body_failure_outcome(response_kind, failure)
    opener = install_opener(monkeypatch, [outcome, FakeResponse(b'{"unexpected":true}')])
    send = cast("Callable[..., object]", member("send_result"))

    with pytest.raises(helper_error) as caught:
        _ = send(
            method,
            API_URL,
            {"Authorization": f"Bearer {credential_value}"},
            None,
            runtime(retries=10),
        )

    message = str(caught.value)
    assert credential_value not in message
    if failure_kind != "incomplete-read":
        assert "<redacted>" in message
    assert len(message) < MAX_SAFE_ERROR_MESSAGE_LENGTH
    assert ("indeterminate" in message) is (method in WRITE_METHODS)
    assert ("audit log" in message) is (method in WRITE_METHODS)
    assert ("Verify the exact resource" in message) is (method in WRITE_METHODS)
    assert len(opener.requests) == 1
    assert close_evidence.closed

    cli_failure = transport_failure(failure_kind, credential_value)
    cli_outcome, cli_close_evidence = body_failure_outcome(response_kind, cli_failure)
    cli_opener = install_opener(monkeypatch, [cli_outcome, FakeResponse(b'{"unexpected":true}')])
    monkeypatch.setenv("STEP_SECURITY_API_KEY", credential_value)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(SCRIPT_PATH),
            "request",
            "--method",
            method,
            "--endpoint",
            "/items",
            "--execute",
            "--retries",
            "10",
        ],
    )
    main = cast("Callable[[], int]", member("main"))

    assert main() == CLI_ERROR_EXIT
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("error: Request failed:")
    assert "Traceback" not in captured.err
    assert credential_value not in captured.err
    if failure_kind != "incomplete-read":
        assert "<redacted>" in captured.err
    assert len(captured.err) < MAX_SAFE_ERROR_MESSAGE_LENGTH
    assert ("indeterminate" in captured.err) is (method in WRITE_METHODS)
    assert ("audit log" in captured.err) is (method in WRITE_METHODS)
    assert ("Verify the exact resource" in captured.err) is (method in WRITE_METHODS)
    assert len(cli_opener.requests) == 1
    assert cli_close_evidence.closed


@pytest.mark.parametrize("method", ["HEAD", "OPTIONS"])
def test_non_get_read_methods_do_not_retry_http_failures(
    monkeypatch: pytest.MonkeyPatch,
    method: str,
) -> None:
    """GET is the transport's only automatically retryable method."""
    helper_error = cast("type[Exception]", member("StepSecurityError"))
    failure, stream = http_failure(HTTP_SERVICE_UNAVAILABLE, b'{"message":"temporary"}')
    opener = install_opener(monkeypatch, [failure, FakeResponse(b'{"unexpected":true}')])
    sleeps: list[float] = []
    monkeypatch.setattr(time, "sleep", sleeps.append)

    with pytest.raises(helper_error, match="HTTP 503"):
        _ = send_result(method, request_runtime=runtime(retries=10))

    assert len(opener.requests) == 1
    assert sleeps == []
    assert stream.closed


@pytest.mark.parametrize("response_kind", ["success-body", "http-error-body"])
@pytest.mark.parametrize(
    ("failure", "expected_type"),
    [
        (KeyboardInterrupt("fixture control"), KeyboardInterrupt),
        (SystemExit("fixture control"), SystemExit),
        (ValueError("fixture programmer error"), ValueError),
    ],
)
def test_non_transport_body_exceptions_remain_outside_boundary_and_close(
    monkeypatch: pytest.MonkeyPatch,
    response_kind: str,
    failure: BaseException,
    expected_type: type[BaseException],
) -> None:
    """Control-flow and programmer exceptions propagate after response closure."""
    outcome, close_evidence = body_failure_outcome(response_kind, failure)
    opener = install_opener(monkeypatch, [outcome])

    with pytest.raises(expected_type, match="fixture"):
        _ = send_result("POST")

    assert len(opener.requests) == 1
    assert close_evidence.closed


@pytest.mark.parametrize("method", ["GET", *WRITE_METHODS])
@pytest.mark.parametrize("response_kind", ["success-body", "http-error-body"])
@pytest.mark.parametrize(
    "depth_case",
    [(-1, True), (0, True), (1, False)],
    ids=("below-cap", "at-cap", "above-cap"),
)
def test_response_json_depth_is_bounded_redacted_closed_and_write_safe(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    method: str,
    response_kind: str,
    depth_case: tuple[int, bool],
) -> None:
    """Success and HTTP-error JSON enforce one explicit depth contract."""
    depth_offset, accepted = depth_case
    helper_error = cast("type[Exception]", member("StepSecurityError"))
    max_depth = cast("int", member("MAX_JSON_DEPTH"))
    credential_value = "json-depth-secret"
    body = nested_json(max_depth + depth_offset, credential_value)
    outcome, close_evidence = response_outcome(response_kind, body)
    opener = install_opener(monkeypatch, [outcome, FakeResponse(b'{"unexpected":true}')])
    send = cast("Callable[..., object]", member("send_result"))
    must_fail = response_kind == "http-error-body" or not accepted

    if must_fail:
        with pytest.raises(helper_error) as caught:
            _ = send(
                method,
                API_URL,
                {"Authorization": f"Bearer {credential_value}"},
                None,
                runtime(retries=10),
            )
        message = str(caught.value)
        assert credential_value not in message
        assert len(message) < MAX_SAFE_ERROR_MESSAGE_LENGTH
        if accepted:
            assert "HTTP 400" in message
            assert "<redacted>" in message
        else:
            assert f"maximum JSON nesting depth of {max_depth}" in message
        assert ("indeterminate" in message) is (method in WRITE_METHODS)
        assert ("audit log" in message) is (method in WRITE_METHODS)
        assert ("Verify the exact resource" in message) is (method in WRITE_METHODS)
    else:
        result = cast(
            "ApiResultView",
            send(method, API_URL, {"Authorization": f"Bearer {credential_value}"}, None, runtime()),
        )
        assert nested_leaf(result.payload) == "<redacted>"

    assert len(opener.requests) == 1
    assert close_evidence.close_attempts == 1
    assert close_evidence.closed

    if accepted or method not in WRITE_METHODS:
        return

    cli_outcome, cli_close_evidence = response_outcome(response_kind, body)
    cli_opener = install_opener(monkeypatch, [cli_outcome, FakeResponse(b'{"unexpected":true}')])
    monkeypatch.setenv("STEP_SECURITY_API_KEY", credential_value)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(SCRIPT_PATH),
            "request",
            "--method",
            method,
            "--endpoint",
            "/items",
            "--execute",
            "--retries",
            "10",
        ],
    )
    main = cast("Callable[[], int]", member("main"))

    assert main() == CLI_ERROR_EXIT
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Traceback" not in captured.err
    assert credential_value not in captured.err
    assert f"maximum JSON nesting depth of {max_depth}" in captured.err
    assert "indeterminate" in captured.err
    assert "Verify the exact resource" in captured.err
    assert "audit log" in captured.err
    assert len(captured.err) < MAX_SAFE_ERROR_MESSAGE_LENGTH
    assert len(cli_opener.requests) == 1
    assert cli_close_evidence.close_attempts == 1
    assert cli_close_evidence.closed


@pytest.mark.parametrize("source", ["inline", "file"])
@pytest.mark.parametrize(
    ("depth_offset", "accepted"),
    [(-1, True), (0, True), (1, False)],
    ids=("below-cap", "at-cap", "above-cap"),
)
def test_request_json_depth_is_explicit_and_non_echoing(
    tmp_path: Path,
    source: str,
    depth_offset: int,
    *,
    accepted: bool,
) -> None:
    """Inline and file request bodies use the same finite nesting cap."""
    helper_error = cast("type[Exception]", member("StepSecurityError"))
    body_bytes_function = cast("Callable[[argparse.Namespace], bytes | None]", member("body_bytes"))
    max_depth = cast("int", member("MAX_JSON_DEPTH"))
    credential_value = "request-depth-secret"
    body = nested_json(max_depth + depth_offset, credential_value)
    body_text = body.decode()
    body_path = tmp_path / "request-body.json"
    if source == "file":
        _ = body_path.write_text(body_text, encoding="utf-8")
    arguments = argparse.Namespace(
        body=body_text if source == "inline" else None,
        body_file=str(body_path) if source == "file" else None,
    )

    if accepted:
        assert body_bytes_function(arguments) == body
    else:
        with pytest.raises(helper_error, match=rf"maximum JSON nesting depth of {max_depth}") as caught:
            _ = body_bytes_function(arguments)
        assert credential_value not in str(caught.value)


@pytest.mark.parametrize(
    ("depth_offset", "accepted"),
    [(-1, True), (0, True), (1, False)],
    ids=("below-cap", "at-cap", "above-cap"),
)
def test_redaction_is_iterative_and_depth_bounded(depth_offset: int, *, accepted: bool) -> None:
    """Redaction does not recurse and cannot bypass the JSON depth cap."""
    helper_error = cast("type[Exception]", member("StepSecurityError"))
    redact_function = cast("Callable[..., object]", member("redact"))
    max_depth = cast("int", member("MAX_JSON_DEPTH"))
    credential_value = "redaction-depth-secret"
    value = nested_value(max_depth + depth_offset, credential_value)

    if accepted:
        assert nested_leaf(redact_function(value, (credential_value,))) == "<redacted>"
    else:
        with pytest.raises(helper_error, match=rf"maximum JSON nesting depth of {max_depth}") as caught:
            _ = redact_function(value, (credential_value,))
        assert credential_value not in str(caught.value)


@pytest.mark.parametrize(
    ("depth_offset", "accepted"),
    [(-1, True), (0, True), (1, False)],
    ids=("below-cap", "at-cap", "above-cap"),
)
def test_output_serialization_is_depth_safe_and_non_echoing(
    capsys: pytest.CaptureFixture[str],
    depth_offset: int,
    *,
    accepted: bool,
) -> None:
    """Command output validates its envelope depth before recursive serialization."""
    helper_error = cast("type[Exception]", member("StepSecurityError"))
    emit_function = cast("Callable[[object], None]", member("emit"))
    max_depth = cast("int", member("MAX_OUTPUT_JSON_DEPTH"))
    credential_value = "output-depth-secret"
    value = nested_value(max_depth + depth_offset, credential_value)

    if accepted:
        emit_function(value)
        assert nested_leaf(json.loads(capsys.readouterr().out)) == credential_value
    else:
        with pytest.raises(helper_error, match=rf"maximum JSON nesting depth of {max_depth}") as caught:
            emit_function(value)
        assert credential_value not in str(caught.value)
        assert capsys.readouterr().out == ""


@pytest.mark.parametrize("body_kind", ["text", "malformed-json"])
@pytest.mark.parametrize("length_kind", ["100000", "100001", "transport-boundary"])
def test_bounded_text_evidence_is_complete_without_pagination_shape_churn(
    monkeypatch: pytest.MonkeyPatch,
    body_kind: str,
    length_kind: str,
) -> None:
    """Every accepted text byte survives parsing, pagination metadata, and output serialization."""
    max_response_bytes = cast("int", member("MAX_API_RESPONSE_BYTES"))
    length = max_response_bytes if length_kind == "transport-boundary" else int(length_kind)
    if body_kind == "text":
        text = "t" * length
        content_type = "text/plain"
    else:
        prefix = '{"malformed":'
        text = prefix + ("m" * (length - len(prefix)))
        content_type = "application/json"
    response = FakeResponse(text.encode(), content_type=content_type)
    opener = install_opener(monkeypatch, [response])
    execute_pages_function = cast("Callable[..., dict[str, object]]", member("execute_pages"))
    safe_dumps = cast("Callable[..., str]", member("safe_json_dumps"))

    output = execute_pages_function(
        execute_arguments(max_pages=1, paginate=False),
        {"method": "GET", "url": API_URL},
        None,
        {"Authorization": "Bearer fixture"},
    )
    pages = cast("list[dict[str, object]]", output["pages"])

    assert output["complete"] is True
    assert output["pageCount"] == 1
    assert output["nextLink"] is None
    page_body = pages[0]["body"]
    assert isinstance(page_body, str)
    assert page_body == text
    assert len(page_body) == length
    serialized = safe_dumps(output, label="test command output")
    serialized_output = cast("dict[str, object]", json.loads(serialized))
    serialized_pages = cast("list[dict[str, object]]", serialized_output["pages"])
    assert serialized_output["complete"] is True
    assert serialized_pages[0]["body"] == text
    assert len(opener.requests) == 1
    assert response.read_sizes == [max_response_bytes + 1]
    assert response.close_attempts == 1
    assert response.closed


@pytest.mark.parametrize("method", ["GET", *WRITE_METHODS])
@pytest.mark.parametrize("response_kind", ["success-body", "http-error-body"])
@pytest.mark.parametrize("failure_kind", ["os-error", "http-exception"])
def test_close_failures_are_attempted_bounded_redacted_and_cli_clean(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    method: str,
    response_kind: str,
    failure_kind: str,
) -> None:
    """A failed close is a safe transport error, not a closure guarantee or replay signal."""
    helper_error = cast("type[Exception]", member("StepSecurityError"))
    credential_value = "close-failure-secret"
    close_failure = transport_failure(failure_kind, credential_value)
    outcome, close_evidence = response_outcome(
        response_kind,
        b'{"ok":true}',
        close_failure=close_failure,
    )
    opener = install_opener(monkeypatch, [outcome, FakeResponse(b'{"unexpected":true}')])
    send = cast("Callable[..., object]", member("send_result"))

    with pytest.raises(helper_error) as caught:
        _ = send(
            method,
            API_URL,
            {"Authorization": f"Bearer {credential_value}"},
            None,
            runtime(retries=10),
        )

    message = str(caught.value)
    assert message.startswith("Request failed:")
    assert credential_value not in message
    assert "<redacted>" in message
    assert len(message) < MAX_SAFE_ERROR_MESSAGE_LENGTH
    assert ("indeterminate" in message) is (method in WRITE_METHODS)
    assert ("Verify the exact resource" in message) is (method in WRITE_METHODS)
    assert ("audit log" in message) is (method in WRITE_METHODS)
    assert len(opener.requests) == 1
    assert close_evidence.close_attempts == 1
    assert not close_evidence.closed

    cli_close_failure = transport_failure(failure_kind, credential_value)
    cli_outcome, cli_close_evidence = response_outcome(
        response_kind,
        b'{"ok":true}',
        close_failure=cli_close_failure,
    )
    cli_opener = install_opener(monkeypatch, [cli_outcome, FakeResponse(b'{"unexpected":true}')])
    monkeypatch.setenv("STEP_SECURITY_API_KEY", credential_value)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(SCRIPT_PATH),
            "request",
            "--method",
            method,
            "--endpoint",
            "/items",
            "--execute",
            "--retries",
            "10",
        ],
    )
    main = cast("Callable[[], int]", member("main"))

    assert main() == CLI_ERROR_EXIT
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("error: Request failed:")
    assert "Traceback" not in captured.err
    assert credential_value not in captured.err
    assert "<redacted>" in captured.err
    assert len(captured.err) < MAX_SAFE_ERROR_MESSAGE_LENGTH
    assert ("indeterminate" in captured.err) is (method in WRITE_METHODS)
    assert ("Verify the exact resource" in captured.err) is (method in WRITE_METHODS)
    assert ("audit log" in captured.err) is (method in WRITE_METHODS)
    assert len(cli_opener.requests) == 1
    assert cli_close_evidence.close_attempts == 1
    assert not cli_close_evidence.closed


def test_json_surfaces_reject_non_finite_values_and_output_cycles(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Requests, responses, redaction, and output retain strict finite acyclic JSON."""
    helper_error = cast("type[Exception]", member("StepSecurityError"))
    body_bytes_function = cast("Callable[[argparse.Namespace], bytes | None]", member("body_bytes"))
    parse_response_function = cast("Callable[[bytes, str], object]", member("parse_response"))
    redact_function = cast("Callable[[object], object]", member("redact"))
    emit_function = cast("Callable[[object], None]", member("emit"))

    with pytest.raises(helper_error, match="finite JSON numbers"):
        _ = body_bytes_function(argparse.Namespace(body='{"value":NaN}', body_file=None))
    with pytest.raises(helper_error, match="finite JSON numbers"):
        _ = parse_response_function(b'{"value":Infinity}', "application/json")
    with pytest.raises(helper_error, match="finite JSON numbers"):
        _ = redact_function({"value": -math.inf})
    with pytest.raises(helper_error, match="finite JSON numbers"):
        emit_function({"value": math.nan})

    cyclic: list[object] = []
    cyclic.append(cyclic)
    with pytest.raises(helper_error, match="container cycle"):
        emit_function(cyclic)
    assert capsys.readouterr().out == ""


def test_oversized_write_error_retains_indeterminate_guidance(monkeypatch: pytest.MonkeyPatch) -> None:
    """Response-size rejection cannot erase the attempted-write recovery warning."""
    helper_error = cast("type[Exception]", member("StepSecurityError"))
    monkeypatch.setattr(STEPSECURITY, "MAX_ERROR_RESPONSE_BYTES", 8)
    failure, stream = http_failure(HTTP_SERVICE_UNAVAILABLE, b"x" * 9)
    opener = install_opener(monkeypatch, [failure])

    with pytest.raises(helper_error, match=r"(?i)indeterminate.*audit log"):
        _ = send_result("POST")

    assert len(opener.requests) == 1
    assert stream.read_sizes == [9]
    assert stream.closed


@pytest.mark.parametrize("method", WRITE_METHODS)
def test_oversized_write_success_retains_indeterminate_guidance(
    monkeypatch: pytest.MonkeyPatch,
    method: str,
) -> None:
    """A bounded success-body read failure preserves write recovery guidance."""
    helper_error = cast("type[Exception]", member("StepSecurityError"))
    response = FakeResponse(b"x" * 9, content_type="text/plain")
    opener = install_opener(monkeypatch, [response])

    with pytest.raises(helper_error, match=r"(?i)indeterminate.*audit log"):
        _ = send_result(method, max_response_bytes=8)

    assert len(opener.requests) == 1
    assert response.read_sizes == [9]
    assert response.closed


@pytest.mark.parametrize("content_length", [None, "1"], ids=("absent", "dishonest"))
@pytest.mark.parametrize("overflow", [False, True], ids=("exact", "over"))
def test_success_bodies_use_limit_plus_one_reads_and_close(
    monkeypatch: pytest.MonkeyPatch,
    content_length: str | None,
    *,
    overflow: bool,
) -> None:
    """Actual success bytes enforce the limit despite missing or understated lengths."""
    helper_error = cast("type[Exception]", member("StepSecurityError"))
    response = FakeResponse(b"x" * (9 if overflow else 8), content_length=content_length, content_type="text/plain")
    _ = install_opener(monkeypatch, [response])

    if overflow:
        with pytest.raises(helper_error, match="8-byte safety limit"):
            _ = send_result("GET", max_response_bytes=8)
    else:
        result = cast("ApiResultView", send_result("GET", max_response_bytes=8))
        assert result.payload == "x" * 8

    assert response.read_sizes == [9]
    assert response.closed


@pytest.mark.parametrize("content_length", [None, "1"], ids=("absent", "dishonest"))
@pytest.mark.parametrize("overflow", [False, True], ids=("exact", "over"))
def test_error_bodies_use_limit_plus_one_reads_and_close(
    monkeypatch: pytest.MonkeyPatch,
    content_length: str | None,
    *,
    overflow: bool,
) -> None:
    """Actual error bytes enforce the limit despite missing or understated lengths."""
    helper_error = cast("type[Exception]", member("StepSecurityError"))
    monkeypatch.setattr(STEPSECURITY, "MAX_ERROR_RESPONSE_BYTES", 8)
    headers = {"Content-Length": content_length} if content_length is not None else None
    failure, stream = http_failure(HTTP_BAD_REQUEST, b"x" * (9 if overflow else 8), headers=headers)
    _ = install_opener(monkeypatch, [failure])

    expected = "8-byte safety limit" if overflow else "HTTP 400"
    with pytest.raises(helper_error, match=expected):
        _ = send_result("GET")

    assert stream.read_sizes == [9]
    assert stream.closed


def execute_arguments(*, max_pages: int, paginate: bool = True) -> argparse.Namespace:
    """Create the request arguments needed by execute_request."""
    return argparse.Namespace(
        dry_run=False,
        execute=False,
        header=None,
        max_pages=max_pages,
        paginate=paginate,
        retries=0,
        timeout=1.0,
    )


def install_request_plan(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bypass unrelated OpenAPI planning while retaining execution behavior."""

    def fake_request_plan(_arguments: argparse.Namespace) -> tuple[dict[str, object], None]:
        return {"method": "GET", "url": API_URL}, None

    monkeypatch.setattr(STEPSECURITY, "request_plan", fake_request_plan)
    monkeypatch.setattr(STEPSECURITY, "credential", lambda: "fixture")


def execute_with_payloads(
    monkeypatch: pytest.MonkeyPatch,
    payloads: list[object],
    *,
    max_pages: int,
    paginate: bool = True,
) -> tuple[dict[str, object], list[str]]:
    """Execute deterministic page payloads and return emitted metadata and URLs."""
    install_request_plan(monkeypatch)
    emitted: list[object] = []
    urls: list[str] = []
    payload_iterator = iter(payloads)
    result_factory = cast("Callable[..., object]", member("ApiResult"))

    def fake_send_result(
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
        request_runtime: object,
    ) -> object:
        del method, headers, body, request_runtime
        urls.append(url)
        return result_factory(headers={}, payload=next(payload_iterator), response_bytes=1, status=HTTP_OK)

    monkeypatch.setattr(STEPSECURITY, "send_result", fake_send_result)
    monkeypatch.setattr(STEPSECURITY, "emit", emitted.append)
    execute = cast("Callable[[argparse.Namespace], None]", member("execute_request"))
    execute(execute_arguments(max_pages=max_pages, paginate=paginate))
    return cast("dict[str, object]", emitted[0]), urls


def test_natural_pagination_reports_complete_page_count_and_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Natural pagination exhaustion is explicitly distinguished from truncation."""
    output, urls = execute_with_payloads(
        monkeypatch,
        [
            {"data": [1], "links": {"next": "?page=2"}},
            {"data": [2], "links": {"next": None}},
        ],
        max_pages=NATURAL_MAX_PAGES,
    )

    assert output["complete"] is True
    assert output["pageCount"] == EXPECTED_PAGE_COUNT
    assert output["maxPages"] == NATURAL_MAX_PAGES
    assert output["nextLink"] is None
    assert urls == [API_URL, f"{API_URL}?page=2"]


@pytest.mark.parametrize(
    "malformed_next",
    ["", 0, False, [], {}, {"href": ""}, {"href": 1}],
    ids=("empty", "zero", "false", "list", "object", "empty-href", "non-string-href"),
)
def test_malformed_next_link_fails_with_partial_page_context(
    monkeypatch: pytest.MonkeyPatch,
    malformed_next: object,
) -> None:
    """Malformed pagination metadata cannot masquerade as natural exhaustion."""
    helper_error = cast("type[Exception]", member("StepSecurityError"))

    with pytest.raises(helper_error, match=r"incomplete after 1 page\(s\).*malformed links.next"):
        _ = execute_with_payloads(
            monkeypatch,
            [{"data": [1], "links": {"next": malformed_next}}],
            max_pages=NATURAL_MAX_PAGES,
        )


@pytest.mark.parametrize("malformed_links", [False, [], "not-an-object"])
def test_non_object_links_metadata_fails_incomplete(
    monkeypatch: pytest.MonkeyPatch,
    malformed_links: object,
) -> None:
    """A present non-object links value is malformed rather than terminal."""
    helper_error = cast("type[Exception]", member("StepSecurityError"))

    with pytest.raises(helper_error, match=r"incomplete after 1 page\(s\).*non-object links"):
        _ = execute_with_payloads(
            monkeypatch,
            [{"data": [1], "links": malformed_links}],
            max_pages=NATURAL_MAX_PAGES,
        )


def test_exhausted_pagination_reports_validated_next_link(monkeypatch: pytest.MonkeyPatch) -> None:
    """A max-pages stop remains visibly partial and exposes only a validated next URL."""
    output, urls = execute_with_payloads(
        monkeypatch,
        [{"data": [1], "links": {"next": "/v1/items?page=2"}}],
        max_pages=1,
    )

    assert output["complete"] is False
    assert output["pageCount"] == 1
    assert output["maxPages"] == 1
    assert output["nextLink"] == f"{API_URL}?page=2"
    assert urls == [API_URL]


def test_unpaginated_partial_inventory_never_reports_complete(monkeypatch: pytest.MonkeyPatch) -> None:
    """A single-page request with a next link cannot masquerade as a complete inventory."""
    output, urls = execute_with_payloads(
        monkeypatch,
        [{"data": [1], "links": {"next": "?page=2"}}],
        max_pages=DEFAULT_MAX_PAGES,
        paginate=False,
    )

    assert output["complete"] is False
    assert output["pageCount"] == 1
    assert output["maxPages"] == DEFAULT_MAX_PAGES
    assert output["nextLink"] == f"{API_URL}?page=2"
    assert urls == [API_URL]


def test_repeated_pagination_link_is_detected_before_another_request(monkeypatch: pytest.MonkeyPatch) -> None:
    """Repeated next links fail with explicit partial-inventory context."""
    helper_error = cast("type[Exception]", member("StepSecurityError"))
    install_request_plan(monkeypatch)
    result_factory = cast("Callable[..., object]", member("ApiResult"))
    payloads = iter(
        [
            {"data": [1], "links": {"next": "?page=2"}},
            {"data": [2], "links": {"next": "?page=2"}},
        ]
    )
    urls: list[str] = []

    def fake_send_result(
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
        request_runtime: object,
    ) -> object:
        del method, headers, body, request_runtime
        urls.append(url)
        return result_factory(headers={}, payload=next(payloads), response_bytes=1, status=HTTP_OK)

    monkeypatch.setattr(STEPSECURITY, "send_result", fake_send_result)
    execute = cast("Callable[[argparse.Namespace], None]", member("execute_request"))

    with pytest.raises(helper_error, match=r"incomplete after 2 page\(s\).*repeated next link"):
        execute(execute_arguments(max_pages=NATURAL_MAX_PAGES))

    assert urls == [API_URL, f"{API_URL}?page=2"]


@pytest.mark.parametrize("case", ["exact", "over"])
def test_pagination_enforces_exact_cumulative_response_budget(
    monkeypatch: pytest.MonkeyPatch,
    case: str,
) -> None:
    """Individually valid pages cannot exceed the cumulative byte budget."""
    overflow = case == "over"
    helper_error = cast("type[Exception]", member("StepSecurityError"))
    first_body = b'{"data":[1],"links":{"next":"?page=2"}}'
    second_body = b'{"data":[2],"links":{"next":null}}'
    cumulative_limit = len(first_body) + len(second_body) - int(overflow)
    monkeypatch.setattr(STEPSECURITY, "MAX_API_RESPONSE_BYTES", 1024)
    monkeypatch.setattr(STEPSECURITY, "MAX_PAGINATED_RESPONSE_BYTES", cumulative_limit)
    install_request_plan(monkeypatch)
    emitted: list[object] = []
    monkeypatch.setattr(STEPSECURITY, "emit", emitted.append)
    first = FakeResponse(first_body)
    second = FakeResponse(second_body)
    opener = install_opener(monkeypatch, [first, second])
    execute = cast("Callable[[argparse.Namespace], None]", member("execute_request"))

    if overflow:
        with pytest.raises(helper_error, match=rf"{cumulative_limit}-byte cumulative safety limit"):
            execute(execute_arguments(max_pages=NATURAL_MAX_PAGES))
        assert emitted == []
    else:
        execute(execute_arguments(max_pages=NATURAL_MAX_PAGES))
        output = cast("dict[str, object]", emitted[0])
        assert output["complete"] is True
        assert output["pageCount"] == EXPECTED_PAGE_COUNT

    assert len(opener.requests) == EXPECTED_PAGE_COUNT
    assert first.closed
    assert second.closed
    expected_second_read = len(second_body) + (0 if overflow else 1)
    assert second.read_sizes == [expected_second_read]


@pytest.mark.parametrize("timeout", [0.0, -1.0, math.nan, math.inf, -math.inf])
def test_non_positive_or_non_finite_timeouts_are_rejected(timeout: float) -> None:
    """NaN and infinity cannot bypass timeout validation."""
    helper_error = cast("type[Exception]", member("StepSecurityError"))
    validate = cast("Callable[[argparse.Namespace], None]", member("validate_arguments"))

    with pytest.raises(helper_error, match="finite value greater than zero"):
        validate(argparse.Namespace(max_pages=1, retries=0, timeout=timeout))


@pytest.mark.parametrize(
    ("name", "value", "message"),
    [
        ("max_pages", 0, "--max-pages must be at least 1"),
        ("max_pages", 1001, "--max-pages cannot exceed"),
        ("retries", -1, "--retries must be between"),
        ("retries", 11, "--retries must be between"),
    ],
)
def test_page_and_retry_caps_reject_unbounded_values(name: str, value: int, message: str) -> None:
    """Page and retry controls have explicit lower and upper bounds."""
    helper_error = cast("type[Exception]", member("StepSecurityError"))
    validate = cast("Callable[[argparse.Namespace], None]", member("validate_arguments"))
    values = {"max_pages": 1, "retries": 0, "timeout": 1.0, name: value}

    with pytest.raises(helper_error, match=message):
        validate(argparse.Namespace(**values))


def test_numeric_upper_boundaries_are_accepted() -> None:
    """Documented finite limits remain usable at their exact boundaries."""
    validate = cast("Callable[[argparse.Namespace], None]", member("validate_arguments"))
    validate(argparse.Namespace(max_pages=1000, retries=10, timeout=1.0))
