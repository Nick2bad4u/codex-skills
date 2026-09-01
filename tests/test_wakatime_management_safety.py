# Copyright (c) 2026 Nick2bad4u
"""Focused transport and CLI safety regressions for WakaTime management."""

from __future__ import annotations

import argparse
import base64
import gc
import importlib.util
import json
import math
import os
import subprocess
import sys
import time
from email.message import Message
from http import client
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, Self, cast, override
from urllib import error, parse, request

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Mapping
    from types import ModuleType, TracebackType

type JsonValue = bool | int | float | str | list[JsonValue] | dict[str, JsonValue] | None
type TransportOutcome = FakeResponse | ReadFailureResponse | BaseException

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "skills/wakatime-management/scripts/manage_wakatime.py"
API_BASE_URL = "https://api.wakatime.com/api/v1"
API_URL = f"{API_BASE_URL}/users/current"
TEST_OAUTH_TOKEN = "oauth/active+credential-value"  # noqa: S105  # Synthetic credential fixture.
TEST_API_KEY = "basic-" + "active-credential"
MALFORMED_URL_SECRET = "malformed-url-credential"  # noqa: S105  # Synthetic malformed-URL fixture.
HTTP_OK = 200
ARGPARSE_USAGE_ERROR = 2
RETRIED_REQUEST_COUNT = 2
EXPECTED_HEADER_COUNT = 2
MAX_RETRY_DELAY_SECONDS = 60.0
MAX_TIMEOUT_SECONDS = 300.0
EXPECTED_TRANSIENT_STATUSES = (302, 429, 500, 503, 504)
WRITE_METHODS = ("POST", "PUT", "PATCH", "DELETE")
SENSITIVE_QUERY_NAMES = (
    "clientSecret",
    "ClientSecrets",
    "client_secret",
    "client-secret",
    "clientsecret",
    "accessToken",
    "refreshTokens",
    "apiKeys",
    "API_TOKENS",
    "authorizationHeaders",
    "HTTPHeaders",
    "request_headers",
    "cookies",
    "Session",
    "sessionId",
    "signatures",
    "sig",
    "X-Amz-Signature",
    "X_AMZ_CREDENTIAL",
    "xAmzSecurityToken",
)
ORDINARY_NAMES = (
    "clientId",
    "projectKey",
    "tokenCount",
    "refreshInterval",
    "authorizationMode",
    "headerCount",
    "cookiePolicy",
    "sessionDuration",
    "signatureAlgorithm",
    "documentationUrl",
    "secretariat",
)
ERROR_BODY_CASES = (
    ("empty", b"", None),
    ("malformed", b"{", None),
    ("undecodable", b"\xff", None),
    ("oversized", b"123456789", 8),
)
NONFINITE_JSON_CASES = (
    ("nan", '{"value":NaN}'),
    ("positive-infinity", '{"value":Infinity}'),
    ("negative-infinity", '{"value":-Infinity}'),
    ("finite-overflow", '{"nested":[1e400]}'),
)
READ_FAILURE_KINDS = ("incomplete-read", "http-exception")


class ApiResultView(Protocol):
    """Typed view of the dynamically loaded API result."""

    payload: JsonValue
    status: int
    url: str


class RecordingStream(BytesIO):
    """Bytes stream that records each requested read bound."""

    def __init__(self, body: bytes) -> None:
        """Initialize the stream and read-size log."""
        super().__init__(body)
        self.read_sizes: list[int] = []

    @override
    def read(self, size: int | None = -1, /) -> bytes:
        """Record and perform one bounded read."""
        self.read_sizes.append(-1 if size is None else size)
        return super().read(size)


class FakeResponse:
    """Small urllib-compatible response that records bounded reads."""

    def __init__(
        self,
        body: bytes,
        *,
        content_length: str | None = None,
        content_type: str = "text/plain",
        status: int = HTTP_OK,
    ) -> None:
        """Initialize response bytes, headers, and status."""
        super().__init__()
        self._stream = RecordingStream(body)
        self.headers = http_headers({"Content-Type": content_type})
        if content_length is not None:
            self.headers["Content-Length"] = content_length
        self.status = status

    @property
    def read_sizes(self) -> list[int]:
        """Return recorded read bounds."""
        return self._stream.read_sizes

    @property
    def closed(self) -> bool:
        """Return whether response cleanup closed the body stream."""
        return self._stream.closed

    def __enter__(self) -> Self:
        """Enter a urllib-style response context."""
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close the response stream without suppressing exceptions."""
        del exception_type, exception, traceback
        self._stream.close()

    def read(self, amount: int | None = None) -> bytes:
        """Read response bytes while preserving an optional bound."""
        return self._stream.read(-1 if amount is None else amount)


class ReadFailureResponse(FakeResponse):
    """Successful response whose bounded body read raises a transport exception."""

    def __init__(self, read_exception: client.HTTPException) -> None:
        """Initialize an otherwise successful JSON response."""
        super().__init__(b"", content_type="application/json")
        self._read_exception = read_exception

    @override
    def read(self, amount: int | None = None) -> bytes:
        """Record the read bound and raise the configured transport exception."""
        self._stream.read_sizes.append(-1 if amount is None else amount)
        raise self._read_exception


class ReadFailureStream(BytesIO):
    """HTTP error stream whose bounded read raises a transport exception."""

    def __init__(self, read_exception: client.HTTPException) -> None:
        """Initialize the failure and read-size log."""
        super().__init__()
        self._read_exception = read_exception
        self.read_sizes: list[int] = []

    @override
    def read(self, size: int | None = -1, /) -> bytes:
        """Record the attempted bound and raise the configured exception."""
        self.read_sizes.append(-1 if size is None else size)
        raise self._read_exception


class FakeOpener:
    """Record requests and consume deterministic transport outcomes."""

    def __init__(self, outcomes: list[TransportOutcome]) -> None:
        """Initialize ordered outcomes and an empty request log."""
        super().__init__()
        self.outcomes = outcomes
        self.requests: list[request.Request] = []
        self.timeouts: list[float] = []

    def open(self, api_request: request.Request, timeout: float) -> FakeResponse | ReadFailureResponse:
        """Record one request and return or raise the next outcome."""
        self.requests.append(api_request)
        self.timeouts.append(timeout)
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
    status: int,
    *,
    body: bytes = b'{"message":"temporary"}',
    content_length: str | None = None,
    content_type: str = "application/json",
    retry_after: str | None = "0",
) -> tuple[error.HTTPError, RecordingStream]:
    """Create a readable HTTP error and expose its recording stream."""
    headers = http_headers({"Content-Type": content_type})
    if retry_after is not None:
        headers["Retry-After"] = retry_after
    if content_length is not None:
        headers["Content-Length"] = content_length
    stream = RecordingStream(body)
    return error.HTTPError(API_URL, status, "fixture failure", headers, stream), stream


def http_read_failure(
    status: int,
    read_exception: client.HTTPException,
) -> tuple[error.HTTPError, ReadFailureStream]:
    """Create an HTTP error whose body read fails before yielding bytes."""
    headers = http_headers({"Content-Type": "application/json", "Retry-After": "0"})
    stream = ReadFailureStream(read_exception)
    return error.HTTPError(API_URL, status, "fixture failure", headers, stream), stream


def response_read_exception(kind: str) -> client.HTTPException:
    """Create one deterministic response-read transport failure."""
    if kind == "incomplete-read":
        partial = TEST_OAUTH_TOKEN.encode()
        return client.IncompleteRead(partial=partial, expected=len(partial) + 1)
    if kind == "http-exception":
        return client.HTTPException(f"read interrupted near {TEST_OAUTH_TOKEN}")
    raise AssertionError(f"Unknown response-read exception fixture: {kind}")


def load_script_module() -> ModuleType:
    """Load the WakaTime helper without invoking its CLI entry point."""
    specification = importlib.util.spec_from_file_location("wakatime_management_safety", SCRIPT_PATH)
    if specification is None or specification.loader is None:
        raise RuntimeError(f"Could not load test module: {SCRIPT_PATH}")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


WAKATIME = load_script_module()


def member(name: str) -> object:
    """Return one dynamically loaded helper member."""
    return getattr(WAKATIME, name)


def authentication(*, scheme: str = "oauth", secret: str = TEST_OAUTH_TOKEN) -> object:
    """Create synthetic WakaTime authentication."""
    factory = cast("Callable[..., object]", member("Authentication"))
    return factory(environment_name="WAKATIME_TEST_CREDENTIAL", scheme=scheme, secret=secret)


def context(*, scheme: str = "oauth", secret: str = TEST_OAUTH_TOKEN) -> object:
    """Create an official-origin WakaTime context."""
    factory = cast("Callable[..., object]", member("WakaTimeContext"))
    return factory(authentication=authentication(scheme=scheme, secret=secret), base_url=API_BASE_URL)


def plan(method: str = "GET", *, query: dict[str, str] | None = None, url: str = API_URL) -> object:
    """Create one raw WakaTime request plan."""
    factory = cast("Callable[..., object]", member("RequestPlan"))
    body: JsonValue = None if method == "GET" else {"enabled": True}
    return factory(body=body, method=method, query=query or {}, url=url)


def send(
    request_plan: object,
    *,
    retries: int = 3,
    timeout: float = 1.0,
    request_context: object | None = None,
) -> object:
    """Invoke the WakaTime transport with deterministic runtime options."""
    send_request = cast("Callable[..., object]", member("send_request"))
    return send_request(
        request_context or context(),
        request_plan,
        argparse.Namespace(retries=retries, timeout=timeout),
    )


def install_opener(monkeypatch: pytest.MonkeyPatch, outcomes: list[TransportOutcome]) -> FakeOpener:
    """Replace urllib opener construction with a deterministic recorder."""
    opener = FakeOpener(outcomes)

    def build_opener(*_handlers: object) -> FakeOpener:
        return opener

    monkeypatch.setattr(request, "build_opener", build_opener)
    return opener


def clean_environment(**values: str) -> dict[str, str]:
    """Build a subprocess environment without ambient WakaTime credentials."""
    environment = os.environ.copy()
    _ = environment.pop("WAKATIME_ACCESS_TOKEN", None)
    _ = environment.pop("WAKATIME_API_KEY", None)
    environment.update(values)
    return environment


def run_script(*arguments: str, environment: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    """Run the fixed repository helper without a shell."""
    return subprocess.run(  # noqa: S603  # Fixed interpreter and repository-owned script.
        [sys.executable, str(SCRIPT_PATH), *arguments],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        env=environment or clean_environment(),
        stdin=subprocess.DEVNULL,
        text=True,
    )


def invoke_write_main(
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    outcomes: list[TransportOutcome],
) -> tuple[int, FakeOpener, list[float]]:
    """Invoke one sent write through the real CLI error boundary and fake transport."""
    opener = install_opener(monkeypatch, outcomes)
    sleeps: list[float] = []
    monkeypatch.setattr(time, "sleep", sleeps.append)
    monkeypatch.setenv("WAKATIME_ACCESS_TOKEN", TEST_OAUTH_TOKEN)
    monkeypatch.delenv("WAKATIME_API_KEY", raising=False)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(SCRIPT_PATH),
            "request",
            "/users/current/data_dumps",
            "--method",
            method,
            "--body-json",
            '{"enabled":true}',
            "--send",
            "--retries",
            "10",
            "--json",
        ],
    )
    main = cast("Callable[[], int]", member("main"))
    return main(), opener, sleeps


@pytest.fixture(autouse=True)
def collect_transport_exception_cycles() -> Iterator[None]:
    """Collect retained urllib exception tracebacks while capture is open."""
    yield
    _ = gc.collect()


def test_base_url_accepts_only_the_normalized_official_origin() -> None:
    """Foreign hosts, lookalikes, paths, ports, and empty suffixes are rejected."""
    sanitize = cast("Callable[[str], str]", member("sanitize_base_url"))
    helper_error = cast("type[Exception]", member("WakaTimeCliError"))

    assert sanitize("HTTPS://API.WAKATIME.COM/api/v1/") == API_BASE_URL
    unsafe_urls = (
        "http://api.wakatime.com/api/v1",
        "https://wakatime.com/api/v1",
        "https://api.eu.wakatime.com/api/v1",
        "https://api.wakatime.com:443/api/v1",
        "https://api.wakatime.com.evil.invalid/api/v1",
        "https://api.wakatime.com/foo/api/v1",
        "https://api.wakatime.com/api/v1.evil",
        "https://api.wakatime.com/api/v1?",
        "https://api.wakatime.com/api/v1#",
    )
    for unsafe_url in unsafe_urls:
        with pytest.raises(helper_error, match="WakaTime API base URL"):
            _ = sanitize(unsafe_url)


def test_cli_rejects_foreign_base_urls_without_exposing_credentials() -> None:
    """CLI context resolution never accepts a credential-bearing foreign origin."""
    environment = clean_environment(WAKATIME_ACCESS_TOKEN=TEST_OAUTH_TOKEN)
    for unsafe_url in (
        "https://api.wakatime.com.attacker.invalid/api/v1",
        "https://api.wakatime.com:8443/api/v1",
        "https://attacker.invalid/api/v1",
    ):
        result = run_script("context", "--base-url", unsafe_url, environment=environment)
        assert result.returncode == 1
        assert "must be exactly" in result.stderr
        assert TEST_OAUTH_TOKEN not in result.stdout
        assert TEST_OAUTH_TOKEN not in result.stderr


@pytest.mark.parametrize(
    "base_url",
    [
        "https://[::1",
        "https://api.wakatime.com:not-a-port/api/v1",
        "https://api.wakatime.com\uff0fevil/api/v1",
        f"https://{MALFORMED_URL_SECRET}@[::1",
    ],
)
def test_cli_normalizes_malformed_base_url_value_errors_without_a_traceback(base_url: str) -> None:
    """URL parser, normalization, hostname, and port failures become sanitized CLI errors."""
    environment = clean_environment(**{"WAKATIME_ACCESS_" + "TOKEN": MALFORMED_URL_SECRET})
    result = run_script("context", f"--base-url={base_url}", environment=environment)

    assert result.returncode == 1
    assert result.stdout == ""
    assert "malformed" in result.stderr.casefold()
    assert "Traceback" not in result.stderr
    assert TEST_OAUTH_TOKEN not in result.stderr
    assert MALFORMED_URL_SECRET not in result.stderr


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://[::1/api/v1/users/current",
        "https://api.wakatime.com:not-a-port/api/v1/users/current",
        "https://api.wakatime.com\uff0fevil/api/v1/users/current",
        f"https://{MALFORMED_URL_SECRET}@api.wakatime.com:not-a-port/api/v1/users/current",
    ],
)
def test_cli_normalizes_malformed_request_url_value_errors_without_a_traceback(endpoint: str) -> None:
    """Malformed absolute request URLs fail safely without exposing their input."""
    environment = clean_environment(**{"WAKATIME_ACCESS_" + "TOKEN": MALFORMED_URL_SECRET})
    result = run_script("request", endpoint, "--dry-run", environment=environment)

    assert result.returncode == 1
    assert result.stdout == ""
    assert "malformed" in result.stderr.casefold()
    assert "Traceback" not in result.stderr
    assert TEST_OAUTH_TOKEN not in result.stderr
    assert MALFORMED_URL_SECRET not in result.stderr


def test_endpoint_validation_does_not_swallow_unrelated_programmer_value_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only URL parsing and authority extraction ValueError instances are normalized."""
    validate_endpoint = cast("Callable[[str, str], str]", member("validated_endpoint_url"))

    def fail_decode(*_arguments: object) -> str:
        raise ValueError("programmer-value-error-sentinel")

    monkeypatch.setattr(WAKATIME, "decode_path_strict", fail_decode)

    with pytest.raises(ValueError, match="programmer-value-error-sentinel"):
        _ = validate_endpoint(API_BASE_URL, "/users/current")


def test_forged_foreign_plan_is_rejected_before_authentication_is_attached(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Transport validation blocks a forged plan before building a request."""
    helper_error = cast("type[Exception]", member("WakaTimeCliError"))
    opener = install_opener(monkeypatch, [FakeResponse(b"unexpected")])
    request_plan = plan(url="https://attacker.invalid/api/v1/users/current")

    with pytest.raises(helper_error, match="origin must match"):
        _ = send(request_plan, retries=0)

    assert opener.requests == []


def test_endpoint_validation_rejects_encoded_traversal_and_separators_at_every_layer() -> None:
    """Single, double, mixed-case, backslash, and absolute traversal encodings fail closed."""
    validate_endpoint = cast("Callable[[str, str], str]", member("validated_endpoint_url"))
    helper_error = cast("type[Exception]", member("WakaTimeCliError"))
    deep_dot_segment = "%2e%2e"
    for _iteration in range(5):
        deep_dot_segment = deep_dot_segment.replace("%", "%25")
    unsafe_paths = (
        "/users/%2e%2e/current",
        "/users/%252e%252e/current",
        "/users/%2E%2e/current",
        "/users%2fcurrent",
        "/users%252Fcurrent",
        "/users%5ccurrent",
        "/users%255Ccurrent",
        "/users%3fadmin=true",
        f"/users/{deep_dot_segment}/current",
        "/%2e%2e/users/current",
    )

    for unsafe_path in unsafe_paths:
        for endpoint in (unsafe_path, f"{API_BASE_URL}{unsafe_path}"):
            with pytest.raises(helper_error):
                _ = validate_endpoint(API_BASE_URL, endpoint)

    encoded_space = "/users/current/projects/codex%20skills/commits"
    assert validate_endpoint(API_BASE_URL, encoded_space) == f"{API_BASE_URL}{encoded_space}"


@pytest.mark.parametrize("status", EXPECTED_TRANSIENT_STATUSES)
def test_get_retries_every_retryable_http_status(monkeypatch: pytest.MonkeyPatch, status: int) -> None:
    """GET retries each explicitly retryable WakaTime status."""
    failure, _stream = http_failure(status, body=b"not-json")
    opener = install_opener(monkeypatch, [failure, FakeResponse(b"ok")])
    sleeps: list[float] = []
    monkeypatch.setattr(time, "sleep", sleeps.append)

    result = cast("ApiResultView", send(plan(), retries=1))

    assert result.payload == "ok"
    assert len(opener.requests) == RETRIED_REQUEST_COUNT
    assert sleeps == [0.0]


def test_get_retries_url_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """GET retains bounded automatic retries for transport failures."""
    opener = install_opener(monkeypatch, [error.URLError(TimeoutError("timed out")), FakeResponse(b"ok")])
    sleeps: list[float] = []
    monkeypatch.setattr(time, "sleep", sleeps.append)

    result = cast("ApiResultView", send(plan(), retries=1))

    assert result.payload == "ok"
    assert len(opener.requests) == RETRIED_REQUEST_COUNT
    assert sleeps == [1.0]


@pytest.mark.parametrize("failure_kind", READ_FAILURE_KINDS)
def test_get_retries_normalized_success_response_read_failures_and_closes_stream(
    monkeypatch: pytest.MonkeyPatch,
    failure_kind: str,
) -> None:
    """Safe GET retries include HTTPException failures raised while reading a response."""
    failed_response = ReadFailureResponse(response_read_exception(failure_kind))
    opener = install_opener(monkeypatch, [failed_response, FakeResponse(b"ok")])
    sleeps: list[float] = []
    monkeypatch.setattr(time, "sleep", sleeps.append)

    result = cast("ApiResultView", send(plan(), retries=1))

    assert result.payload == "ok"
    assert len(opener.requests) == RETRIED_REQUEST_COUNT
    assert sleeps == [1.0]
    assert failed_response.closed
    assert len(failed_response.read_sizes) == 1


@pytest.mark.parametrize(
    "timeout",
    ["nan", "+inf", "-inf", "0", "-1", "300.0001", "1e308", "1e309"],
)
def test_cli_rejects_nonfinite_nonpositive_over_cap_or_extreme_timeouts(timeout: str) -> None:
    """Runtime timeouts must remain finite, positive, and Windows-socket safe."""
    result = run_script("context", f"--timeout={timeout}")

    assert result.returncode == 1
    assert "--timeout must be finite, greater than zero, and at most 300 seconds" in result.stderr
    assert "Traceback" not in result.stderr


def test_cli_rejects_malformed_timeout_before_runtime_validation() -> None:
    """Argparse retains a clear usage error for a malformed timeout."""
    result = run_script("context", "--timeout=not-a-number")

    assert result.returncode == ARGPARSE_USAGE_ERROR
    assert "--timeout" in result.stderr


@pytest.mark.parametrize("timeout", ["1e-300", "300"])
def test_cli_accepts_positive_finite_timeout_boundaries(timeout: str) -> None:
    """A tiny positive timeout and the documented maximum are accepted."""
    result = run_script("context", f"--timeout={timeout}")

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "timeout",
    [1e-300, MAX_TIMEOUT_SECONDS],
    ids=("tiny-positive", "maximum"),
)
def test_transport_receives_accepted_timeout_boundaries(
    monkeypatch: pytest.MonkeyPatch,
    timeout: float,
) -> None:
    """Validated timeout boundaries reach the transport unchanged."""
    response = FakeResponse(b"ok")
    opener = install_opener(monkeypatch, [response])

    result = cast("ApiResultView", send(plan(), retries=0, timeout=timeout))

    assert result.payload == "ok"
    assert opener.timeouts == [timeout]
    assert len(opener.requests) == 1
    assert response.closed


def test_transport_rejects_timeout_over_cap_before_opening_a_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Direct callers cannot bypass the timeout cap and reach Windows sockets."""
    helper_error = cast("type[Exception]", member("WakaTimeCliError"))
    opener = install_opener(monkeypatch, [FakeResponse(b"unexpected")])
    request_plan = plan()

    with pytest.raises(helper_error, match="at most 300 seconds"):
        _ = send(request_plan, retries=0, timeout=MAX_TIMEOUT_SECONDS + 0.001)

    assert opener.requests == []
    assert opener.timeouts == []


@pytest.mark.parametrize("retries", ["-1", "11", "999999999999999999999999"])
def test_cli_rejects_retry_counts_outside_the_explicit_cap(retries: str) -> None:
    """Retry counts are nonnegative integers capped at ten."""
    result = run_script("context", f"--retries={retries}")

    assert result.returncode == 1
    assert "--retries must be between zero and 10" in result.stderr


@pytest.mark.parametrize("retries", ["malformed", "1.5", "+inf"])
def test_cli_rejects_noninteger_retry_counts(retries: str) -> None:
    """Malformed and noninteger retry controls remain argparse usage errors."""
    result = run_script("context", f"--retries={retries}")

    assert result.returncode == ARGPARSE_USAGE_ERROR
    assert "--retries" in result.stderr


@pytest.mark.parametrize("retries", ["0", "10"])
def test_cli_accepts_retry_count_boundaries(retries: str) -> None:
    """Both ends of the documented retry-count range are accepted."""
    result = run_script("context", f"--retries={retries}")

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    ("retry_after", "expected"),
    [
        (None, 8.0),
        ("malformed", 8.0),
        ("nan", 8.0),
        ("+inf", 8.0),
        ("-inf", 8.0),
        ("-1", 8.0),
        ("0", 0.0),
        ("59.5", 59.5),
        ("1e308", MAX_RETRY_DELAY_SECONDS),
        ("1e309", 8.0),
    ],
)
def test_retry_after_requires_a_finite_nonnegative_delay_and_caps_large_values(
    retry_after: str | None,
    expected: float,
) -> None:
    """Invalid Retry-After values use fallback while finite values are capped."""
    retry_delay = cast("Callable[[error.HTTPError, int], float]", member("retry_delay"))
    failure, _stream = http_failure(503, retry_after=retry_after)

    try:
        assert retry_delay(failure, 3) == expected
    finally:
        failure.close()


def test_retry_fallback_is_overflow_safe_for_an_extreme_attempt() -> None:
    """An attacker-sized attempt counter cannot overflow exponential backoff."""
    retry_delay = cast("Callable[[error.HTTPError, int], float]", member("retry_delay"))
    failure, _stream = http_failure(503, retry_after="malformed")

    try:
        assert retry_delay(failure, 10**100) == MAX_RETRY_DELAY_SECONDS
    finally:
        failure.close()


@pytest.mark.parametrize(
    ("attempt", "expected"),
    [(0, 1.0), (1, 2.0), (3, 8.0), (4, 10.0), (10**100, 10.0)],
)
def test_transport_backoff_is_exponential_and_capped(attempt: int, expected: float) -> None:
    """Transport fallback is capped without constructing an enormous integer power."""
    delay = cast("Callable[[int, float], float]", member("capped_exponential_delay"))

    assert delay(attempt, 10.0) == expected


@pytest.mark.parametrize("status", EXPECTED_TRANSIENT_STATUSES)
@pytest.mark.parametrize("method", WRITE_METHODS)
def test_writes_are_single_attempt_with_indeterminate_http_outcome(
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    status: int,
) -> None:
    """Every write method is single-attempt after every retryable HTTP status."""
    helper_error = cast("type[Exception]", member("WakaTimeCliError"))
    failure, _stream = http_failure(status)
    opener = install_opener(monkeypatch, [failure, FakeResponse(b"unexpected")])
    sleeps: list[float] = []
    monkeypatch.setattr(time, "sleep", sleeps.append)
    request_plan = plan(method)

    with pytest.raises(helper_error, match=r"(?i)indeterminate"):
        _ = send(request_plan, retries=5)

    assert len(opener.requests) == 1
    assert sleeps == []


@pytest.mark.parametrize("status", EXPECTED_TRANSIENT_STATUSES)
@pytest.mark.parametrize("method", WRITE_METHODS)
@pytest.mark.parametrize(
    ("_body_case", "body", "error_limit"),
    ERROR_BODY_CASES,
    ids=[case[0] for case in ERROR_BODY_CASES],
)
def test_transient_write_guidance_survives_every_error_body_failure_shape(
    monkeypatch: pytest.MonkeyPatch,
    _body_case: str,
    body: bytes,
    error_limit: int | None,
    method: str,
    status: int,
) -> None:
    """Body read/parse failures cannot erase indeterminate guidance for any transient write."""
    helper_error = cast("type[Exception]", member("WakaTimeCliError"))
    if error_limit is not None:
        monkeypatch.setattr(WAKATIME, "MAX_ERROR_RESPONSE_BYTES", error_limit)
    failure, stream = http_failure(status, body=body)
    opener = install_opener(monkeypatch, [failure, FakeResponse(b"unexpected")])
    sleeps: list[float] = []
    monkeypatch.setattr(time, "sleep", sleeps.append)
    request_plan = plan(method)

    with pytest.raises(helper_error) as captured:
        _ = send(request_plan, retries=10)

    message = str(captured.value)
    assert f"HTTP {status}" in message
    assert method in message
    assert "indeterminate" in message.casefold()
    assert "Verify current WakaTime state" in message
    assert len(opener.requests) == 1
    assert sleeps == []
    expected_read_limit = (error_limit if error_limit is not None else 16 * 1024) + 1
    assert stream.read_sizes == [expected_read_limit]


@pytest.mark.parametrize("method", WRITE_METHODS)
def test_writes_are_single_attempt_with_indeterminate_transport_outcome(
    monkeypatch: pytest.MonkeyPatch,
    method: str,
) -> None:
    """Every write method is single-attempt after a URL transport failure."""
    helper_error = cast("type[Exception]", member("WakaTimeCliError"))
    opener = install_opener(
        monkeypatch,
        [error.URLError(TimeoutError("timed out")), FakeResponse(b"unexpected")],
    )
    sleeps: list[float] = []
    monkeypatch.setattr(time, "sleep", sleeps.append)
    request_plan = plan(method)

    with pytest.raises(helper_error, match=r"(?i)indeterminate"):
        _ = send(request_plan, retries=5)

    assert len(opener.requests) == 1
    assert sleeps == []


@pytest.mark.parametrize("failure_kind", READ_FAILURE_KINDS)
@pytest.mark.parametrize("method", WRITE_METHODS)
def test_every_write_normalizes_success_response_read_failures_without_retry_or_traceback(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    method: str,
    failure_kind: str,
) -> None:
    """IncompleteRead and HTTPException on successful write responses retain safe guidance."""
    failed_response = ReadFailureResponse(response_read_exception(failure_kind))

    return_code, opener, sleeps = invoke_write_main(
        monkeypatch,
        method,
        [failed_response, FakeResponse(b"unexpected")],
    )
    captured = capsys.readouterr()

    assert return_code == 1
    assert captured.out == ""
    assert "Traceback" not in captured.err
    assert TEST_OAUTH_TOKEN not in captured.err
    assert "could not be read safely" in captured.err
    assert "indeterminate" in captured.err.casefold()
    assert "Verify current WakaTime state" in captured.err
    if failure_kind == "http-exception":
        assert "<redacted>" in captured.err
    assert len(opener.requests) == 1
    assert sleeps == []
    assert failed_response.closed
    assert len(failed_response.read_sizes) == 1


@pytest.mark.parametrize("failure_kind", READ_FAILURE_KINDS)
@pytest.mark.parametrize("method", WRITE_METHODS)
def test_every_write_normalizes_http_error_body_read_failures_without_retry_or_traceback(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    method: str,
    failure_kind: str,
) -> None:
    """HTTP error-body read failures cannot escape, replay a write, leak, or erase guidance."""
    failure, stream = http_read_failure(400, response_read_exception(failure_kind))

    return_code, opener, sleeps = invoke_write_main(
        monkeypatch,
        method,
        [failure, FakeResponse(b"unexpected")],
    )
    captured = capsys.readouterr()

    assert return_code == 1
    assert captured.out == ""
    assert "Traceback" not in captured.err
    assert TEST_OAUTH_TOKEN not in captured.err
    assert "HTTP 400" in captured.err
    assert "could not be read safely" in captured.err
    assert "indeterminate" in captured.err.casefold()
    assert "Verify current WakaTime state" in captured.err
    if failure_kind == "http-exception":
        assert "<redacted>" in captured.err
    assert len(opener.requests) == 1
    assert sleeps == []
    assert stream.closed
    assert len(stream.read_sizes) == 1


def secret_query_cases() -> tuple[tuple[str, str, str, str], ...]:
    """Build raw, encoded, prefixed, OAuth, and Basic query credential cases."""
    basic = base64.b64encode(TEST_API_KEY.encode()).decode("ascii")
    return (
        ("oauth-raw-value", "WAKATIME_ACCESS_TOKEN", TEST_OAUTH_TOKEN, f"q={TEST_OAUTH_TOKEN}"),
        ("oauth-prefixed-value", "WAKATIME_ACCESS_TOKEN", TEST_OAUTH_TOKEN, f"q=before-{TEST_OAUTH_TOKEN}-after"),
        (
            "oauth-encoded-value",
            "WAKATIME_ACCESS_TOKEN",
            TEST_OAUTH_TOKEN,
            f"q={parse.quote(TEST_OAUTH_TOKEN, safe='')}",
        ),
        (
            "oauth-bearer-value",
            "WAKATIME_ACCESS_TOKEN",
            TEST_OAUTH_TOKEN,
            f"q={parse.quote_plus(f'Bearer {TEST_OAUTH_TOKEN}')}",
        ),
        ("oauth-raw-name", "WAKATIME_ACCESS_TOKEN", TEST_OAUTH_TOKEN, f"before-{TEST_OAUTH_TOKEN}-after=value"),
        (
            "oauth-encoded-name",
            "WAKATIME_ACCESS_TOKEN",
            TEST_OAUTH_TOKEN,
            f"before-{parse.quote(TEST_OAUTH_TOKEN, safe='')}-after=value",
        ),
        ("basic-raw-value", "WAKATIME_API_KEY", TEST_API_KEY, f"q={TEST_API_KEY}"),
        ("basic-prefixed-value", "WAKATIME_API_KEY", TEST_API_KEY, f"q=before-{TEST_API_KEY}-after"),
        ("basic-encoded-value", "WAKATIME_API_KEY", TEST_API_KEY, f"q={parse.quote(TEST_API_KEY, safe='')}"),
        ("basic-header-value", "WAKATIME_API_KEY", TEST_API_KEY, f"q={parse.quote_plus(f'Basic {basic}')}"),
        ("basic-base64-value", "WAKATIME_API_KEY", TEST_API_KEY, f"q=before-{basic}-after"),
        ("basic-encoded-name", "WAKATIME_API_KEY", TEST_API_KEY, f"before-{parse.quote(TEST_API_KEY, safe='')}=value"),
    )


SECRET_QUERY_CASES = secret_query_cases()


@pytest.mark.parametrize(
    ("_case_name", "environment_name", "secret", "query"),
    SECRET_QUERY_CASES,
    ids=[case[0] for case in SECRET_QUERY_CASES],
)
def test_cli_rejects_loaded_credentials_in_query_names_and_values(
    _case_name: str,
    environment_name: str,
    secret: str,
    query: str,
) -> None:
    """CLI query parsing rejects active OAuth and Basic credentials in every representation."""
    environment = clean_environment(**{environment_name: secret})

    result = run_script("request", "/users/current", "--query", query, "--dry-run", environment=environment)

    assert result.returncode == 1
    assert "loaded WakaTime credential" in result.stderr
    assert secret not in result.stdout
    assert secret not in result.stderr


def test_sensitive_query_classifier_normalizes_forms_and_preserves_ordinary_names() -> None:
    """One classifier covers casing, separators, concatenation, plurals, and repeated encoding."""
    classify = cast("Callable[[str], bool]", member("is_sensitive_query_name"))

    for name in SENSITIVE_QUERY_NAMES:
        encoded = parse.quote(name, safe="")
        double_encoded = parse.quote(encoded, safe="")
        assert classify(name), name
        assert classify(encoded), encoded
        assert classify(double_encoded), double_encoded
    for name in ORDINARY_NAMES:
        assert not classify(name), name


@pytest.mark.parametrize("name", SENSITIVE_QUERY_NAMES)
def test_cli_rejects_every_normalized_sensitive_query_name(name: str) -> None:
    """Sensitive URL-query names are rejected without echoing their values."""
    value = "must-not-appear"

    result = run_script("request", "/users/current", "--query", f"{name}={value}", "--dry-run")

    assert result.returncode == 1
    assert "sensitive query parameter name" in result.stderr
    assert value not in result.stdout
    assert value not in result.stderr


def test_query_preview_and_rendered_url_share_sensitive_name_classification() -> None:
    """Structured and URL query renderers redact the same sensitive fields and retain ordinary filters."""
    redact_query = cast("Callable[[dict[str, str], str | None], dict[str, str]]", member("redact_query"))
    redact_url = cast("Callable[[str, str | None], str]", member("redact_url"))
    query = {
        "clientSecret": "client-value",
        "X-Amz-Signature": "signature-value",
        "sessions": "session-value",
        "returnUrl": "https://download.example.invalid/export?X-Amz-Credential=credential-value",
        "page": "2",
        "projectKey": "ordinary-project-key",
    }

    structured = redact_query(query, None)
    rendered = redact_url(f"{API_URL}?{parse.urlencode(query)}", None)
    rendered_query = dict(parse.parse_qsl(parse.urlsplit(rendered).query, keep_blank_values=True))

    for sensitive_name in ("clientSecret", "X-Amz-Signature", "sessions"):
        assert structured[sensitive_name] == "<redacted>"
        assert rendered_query[sensitive_name] == "<redacted>"
    assert structured["returnUrl"] == "<redacted>"
    assert rendered_query["returnUrl"] == "<redacted>"
    assert structured["page"] == "2"
    assert structured["projectKey"] == "ordinary-project-key"
    assert rendered_query["page"] == "2"
    assert rendered_query["projectKey"] == "ordinary-project-key"


def test_body_preview_redacts_nested_sensitive_maps_and_lists() -> None:
    """Mutation previews redact normalized sensitive body fields while retaining ordinary settings."""
    body: JsonValue = {
        "clientSecret": "body-client-secret",
        "nested": [
            {
                "accessTokens": ["body-access-token"],
                "cookies": {"session": "body-cookie"},
                "projectKey": "SEC",
            }
        ],
        "headerCount": 2,
        "enabled": True,
    }

    result = run_script(
        "request",
        "/users/current/data_dumps",
        "--method",
        "POST",
        "--body-json",
        json.dumps(body),
        "--query",
        "page=1",
    )

    assert result.returncode == 0, result.stderr
    output = cast("dict[str, object]", json.loads(result.stdout))
    rendered_body = cast("dict[str, object]", output["body"])
    nested = cast("list[object]", rendered_body["nested"])
    nested_item = cast("dict[str, object]", nested[0])
    assert rendered_body["clientSecret"] == "<redacted>"
    assert nested_item["accessTokens"] == "<redacted>"
    assert nested_item["cookies"] == "<redacted>"
    assert nested_item["projectKey"] == "SEC"
    assert rendered_body["headerCount"] == EXPECTED_HEADER_COUNT
    assert rendered_body["enabled"] is True
    assert output["query"] == {"page": "1"}


@pytest.mark.parametrize(
    ("_case_name", "body_json"),
    NONFINITE_JSON_CASES,
    ids=[case[0] for case in NONFINITE_JSON_CASES],
)
def test_cli_rejects_nonfinite_request_json_without_partial_output_or_traceback(
    _case_name: str,
    body_json: str,
) -> None:
    """NaN, infinities, and finite-syntax overflow are not valid request JSON."""
    result = run_script(
        "request",
        "/users/current/data_dumps",
        "--method",
        "POST",
        "--body-json",
        body_json,
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert "strict JSON with finite numbers" in result.stderr
    assert "Traceback" not in result.stderr


@pytest.mark.parametrize("nonfinite", [math.nan, math.inf, -math.inf], ids=("nan", "inf", "negative-inf"))
def test_synthetic_request_body_is_rejected_before_transport(
    monkeypatch: pytest.MonkeyPatch,
    nonfinite: float,
) -> None:
    """A forged RequestPlan cannot bypass strict request serialization."""
    helper_error = cast("type[Exception]", member("WakaTimeCliError"))
    factory = cast("Callable[..., object]", member("RequestPlan"))
    request_plan = factory(body={"nested": [nonfinite]}, method="POST", query={}, url=API_URL)
    opener = install_opener(monkeypatch, [FakeResponse(b"unexpected")])

    with pytest.raises(helper_error, match="strict JSON with finite numbers"):
        _ = send(request_plan, retries=10)

    assert opener.requests == []
    assert opener.timeouts == []


@pytest.mark.parametrize("nonfinite", [math.nan, math.inf, -math.inf], ids=("nan", "inf", "negative-inf"))
def test_strict_stdout_encoding_rejects_synthetic_nonfinite_values_atomically(
    capsys: pytest.CaptureFixture[str],
    nonfinite: float,
) -> None:
    """Synthetic values cannot make write_json emit JavaScript constants or partial output."""
    helper_error = cast("type[Exception]", member("WakaTimeCliError"))
    write = cast("Callable[..., None]", member("write_json"))

    with pytest.raises(helper_error, match="strict JSON with finite numbers"):
        write({"nested": [nonfinite]}, prefix="partial-prefix-must-not-appear\n")

    assert capsys.readouterr().out == ""


def test_non_json_success_marker_is_not_emitted_before_synthetic_payload_validation(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The untrusted-data marker and JSON payload are encoded before one stdout write."""
    helper_error = cast("type[Exception]", member("WakaTimeCliError"))
    result_factory = cast("Callable[..., object]", member("ApiResult"))
    execute = cast("Callable[..., int]", member("execute_plan"))

    def fake_send(*_arguments: object) -> object:
        return result_factory(payload={"value": math.nan}, status=HTTP_OK, url=API_URL)

    monkeypatch.setattr(WAKATIME, "send_request", fake_send)
    arguments = argparse.Namespace(
        allow_unauthenticated=False,
        dry_run=False,
        json=False,
        send=True,
    )
    execution_context = context()
    request_plan = plan()

    with pytest.raises(helper_error, match="strict JSON with finite numbers"):
        _ = execute(arguments, execution_context, request_plan)

    assert capsys.readouterr().out == ""


def test_query_and_response_output_redact_credentials_and_export_urls(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Defense-in-depth output strips credentials from URL metadata and payloads."""
    result_factory = cast("Callable[..., object]", member("ApiResult"))
    execute = cast("Callable[..., int]", member("execute_plan"))
    basic = base64.b64encode(TEST_API_KEY.encode()).decode("ascii")
    encoded = parse.quote(TEST_API_KEY, safe="")
    metadata_signature = "metadata-signature-value"
    signed_download = "https://download.example.invalid/export.zip?X-Amz-Signature=signature-value"
    api_result = result_factory(
        payload={
            "message": f"raw={TEST_API_KEY}; encoded={encoded}; basic={basic}",
            "download_url": signed_download,
            "data": [
                {
                    "clientSecret": "success-client-secret",
                    "nested": {"refreshTokens": ["success-refresh-token"]},
                    "projectKey": "ordinary-project-key",
                }
            ],
            "Headers": {"Authorization": "Bearer unknown-success-token"},
        },
        status=HTTP_OK,
        url=f"{API_URL}?q={parse.quote(TEST_API_KEY, safe='')}&signature={metadata_signature}",
    )

    def fake_send(*_arguments: object) -> object:
        return api_result

    monkeypatch.setattr(WAKATIME, "send_request", fake_send)
    arguments = argparse.Namespace(
        allow_unauthenticated=False,
        dry_run=False,
        json=True,
        send=True,
    )
    request_context = context(scheme="api-key", secret=TEST_API_KEY)

    assert execute(arguments, request_context, plan()) == 0
    output = capsys.readouterr().out
    parsed_output = cast("dict[str, object]", json.loads(output))

    assert TEST_API_KEY not in output
    assert encoded not in output
    assert basic not in output
    assert metadata_signature not in output
    assert signed_download not in output
    assert "success-client-secret" not in output
    assert "success-refresh-token" not in output
    assert "unknown-success-token" not in output
    assert "ordinary-project-key" in output
    assert "<redacted>" in json.dumps(parsed_output)


def test_error_json_redacts_nested_sensitive_maps_and_lists_but_keeps_ordinary_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Structured HTTP error output uses the same recursive classifier as success output."""
    helper_error = cast("type[Exception]", member("WakaTimeCliError"))
    payload = {
        "errors": [
            {
                "clientSecrets": ["error-client-secret"],
                "nested": {"X-Amz-Credential": "error-amz-credential"},
                "projectKey": "ordinary-error-project",
            }
        ],
        "authorizationHeaders": {"Cookie": "error-cookie"},
    }
    failure, _stream = http_failure(400, body=json.dumps(payload).encode())
    _ = install_opener(monkeypatch, [failure])
    request_plan = plan()

    with pytest.raises(helper_error) as captured:
        _ = send(request_plan, retries=0)

    message = str(captured.value)
    assert "error-client-secret" not in message
    assert "error-amz-credential" not in message
    assert "error-cookie" not in message
    assert "ordinary-error-project" in message
    assert "<redacted>" in message


def test_recursive_redaction_preserves_negative_ordinary_fields() -> None:
    """Ordinary names containing nearby security vocabulary are not over-redacted."""
    redact = cast("Callable[[JsonValue, str | None], JsonValue]", member("redact_json"))
    payload: JsonValue = {name: f"ordinary-{index}" for index, name in enumerate(ORDINARY_NAMES)}

    assert redact(payload, None) == payload


def test_data_dump_states_preserve_status_but_redact_every_bearer_like_url() -> None:
    """Pending and completed dump states remain useful without exposing download capability URLs."""
    redact = cast("Callable[[JsonValue, str | None], JsonValue]", member("redact_json"))
    payload: JsonValue = {
        "data": [
            {"status": "Pending", "download_url": None},
            {"status": "Completed", "downloadUrl": "https://download.example.invalid/opaque-capability"},
            {"state": "ready", "url": "https://download.example.invalid/another-capability"},
            {
                "status": "Queued",
                "url": "https://download.example.invalid/export.zip?X-Amz-Credential=credential-value",
            },
        ],
        "documentation_url": "https://wakatime.com/developers",
    }

    redacted = cast("dict[str, JsonValue]", redact(payload, None))
    output = json.dumps(redacted)

    assert "Pending" in output
    assert "Completed" in output
    assert "ready" in output
    assert "Queued" in output
    assert "opaque-capability" not in output
    assert "another-capability" not in output
    assert "credential-value" not in output
    assert redacted["documentation_url"] == "https://wakatime.com/developers"


def test_summaries_cli_emits_the_exact_supported_query_contract() -> None:
    """Summaries expose only dates, project, and branches without category relabeling."""
    result = run_script(
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

    assert result.returncode == 0, result.stderr
    output = cast("dict[str, object]", json.loads(result.stdout))
    assert output["query"] == {
        "branches": "main",
        "end": "2026-08-07",
        "project": "codex-skills",
        "start": "2026-08-01",
    }

    unsupported = run_script(
        "summaries",
        "--start",
        "2026-08-01",
        "--end",
        "2026-08-07",
        "--category",
        "Coding",
        "--dry-run",
    )
    assert unsupported.returncode == ARGPARSE_USAGE_ERROR
    assert "unrecognized arguments: --category Coding" in unsupported.stderr


@pytest.mark.parametrize(
    ("_case_name", "response_json"),
    NONFINITE_JSON_CASES,
    ids=[case[0] for case in NONFINITE_JSON_CASES],
)
def test_success_json_rejects_nonfinite_numbers_and_closes_response(
    monkeypatch: pytest.MonkeyPatch,
    _case_name: str,
    response_json: str,
) -> None:
    """Success JSON must be standards-compliant and finite at every nesting level."""
    helper_error = cast("type[Exception]", member("WakaTimeCliError"))
    response = FakeResponse(response_json.encode(), content_type="application/json")
    opener = install_opener(monkeypatch, [response])
    request_plan = plan()

    with pytest.raises(helper_error, match="malformed JSON or a non-finite JSON number"):
        _ = send(request_plan, retries=0)

    assert len(opener.requests) == 1
    assert response.closed


@pytest.mark.parametrize(
    ("_case_name", "error_json"),
    NONFINITE_JSON_CASES,
    ids=[case[0] for case in NONFINITE_JSON_CASES],
)
def test_transient_write_error_json_rejects_nonfinite_numbers_without_losing_guidance(
    monkeypatch: pytest.MonkeyPatch,
    _case_name: str,
    error_json: str,
) -> None:
    """Strict error parsing omits non-finite JSON while preserving write ambiguity guidance."""
    helper_error = cast("type[Exception]", member("WakaTimeCliError"))
    failure, stream = http_failure(503, body=error_json.encode())
    opener = install_opener(monkeypatch, [failure, FakeResponse(b"unexpected")])
    sleeps: list[float] = []
    monkeypatch.setattr(time, "sleep", sleeps.append)
    request_plan = plan("POST")

    with pytest.raises(helper_error) as captured:
        _ = send(request_plan, retries=10)

    message = str(captured.value)
    assert "malformed, undecodable, or non-finite error response body omitted" in message
    assert "indeterminate" in message.casefold()
    assert "Verify current WakaTime state" in message
    assert len(opener.requests) == 1
    assert sleeps == []
    assert stream.closed


def test_success_response_reads_exact_boundary_with_limit_plus_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A boundary-sized success is accepted through an explicit limit-plus-one read."""
    monkeypatch.setattr(WAKATIME, "MAX_API_RESPONSE_BYTES", 8)
    response = FakeResponse(b"12345678")
    _ = install_opener(monkeypatch, [response])

    result = cast("ApiResultView", send(plan(), retries=0))

    assert result.payload == "12345678"
    assert response.read_sizes == [9]


@pytest.mark.parametrize("content_length", [None, "1"], ids=("missing", "dishonest"))
def test_success_response_rejects_overflow_with_missing_or_dishonest_length(
    monkeypatch: pytest.MonkeyPatch,
    content_length: str | None,
) -> None:
    """Actual success bytes enforce the limit despite absent or understated declarations."""
    helper_error = cast("type[Exception]", member("WakaTimeCliError"))
    monkeypatch.setattr(WAKATIME, "MAX_API_RESPONSE_BYTES", 8)
    response = FakeResponse(b"123456789", content_length=content_length)
    _ = install_opener(monkeypatch, [response])
    request_plan = plan()

    with pytest.raises(helper_error, match="8-byte safety limit"):
        _ = send(request_plan, retries=0)

    assert response.read_sizes == [9]


def test_success_response_rejects_oversized_declared_length_before_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A declared oversized success is rejected before body allocation."""
    helper_error = cast("type[Exception]", member("WakaTimeCliError"))
    monkeypatch.setattr(WAKATIME, "MAX_API_RESPONSE_BYTES", 8)
    response = FakeResponse(b"{}", content_length="9")
    _ = install_opener(monkeypatch, [response])
    request_plan = plan()

    with pytest.raises(helper_error, match="8-byte safety limit"):
        _ = send(request_plan, retries=0)

    assert response.read_sizes == []


def test_http_error_reads_exact_boundary_with_limit_plus_one(monkeypatch: pytest.MonkeyPatch) -> None:
    """A boundary-sized HTTP error body is read with the configured limit plus one."""
    helper_error = cast("type[Exception]", member("WakaTimeCliError"))
    monkeypatch.setattr(WAKATIME, "MAX_ERROR_RESPONSE_BYTES", 8)
    failure, stream = http_failure(400, body=b"12345678")
    _ = install_opener(monkeypatch, [failure])
    request_plan = plan()

    with pytest.raises(helper_error, match="HTTP 400"):
        _ = send(request_plan, retries=0)

    assert stream.read_sizes == [9]


@pytest.mark.parametrize("content_length", [None, "1"], ids=("missing", "dishonest"))
def test_http_error_rejects_overflow_with_missing_or_dishonest_length(
    monkeypatch: pytest.MonkeyPatch,
    content_length: str | None,
) -> None:
    """Actual error bytes enforce the limit despite absent or understated declarations."""
    helper_error = cast("type[Exception]", member("WakaTimeCliError"))
    monkeypatch.setattr(WAKATIME, "MAX_ERROR_RESPONSE_BYTES", 8)
    failure, stream = http_failure(400, body=b"123456789", content_length=content_length)
    _ = install_opener(monkeypatch, [failure])
    request_plan = plan()

    with pytest.raises(helper_error, match="8-byte safety limit"):
        _ = send(request_plan, retries=0)

    assert stream.read_sizes == [9]
