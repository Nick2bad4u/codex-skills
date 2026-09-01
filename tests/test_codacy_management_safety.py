# Copyright (c) 2026 Nick2bad4u
"""Focused safety regression tests for the Codacy management transport."""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from email.message import Message
from email.utils import format_datetime
from http.client import HTTPException
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, cast
from urllib import error, parse, request

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import ModuleType
    from typing import Self

type JsonValue = bool | int | float | str | list[JsonValue] | dict[str, JsonValue] | None

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "skills/codacy-management/scripts/manage_codacy.py"
API_BASE_URL = "https://api.codacy.com/api/v3"
API_URL = f"{API_BASE_URL}/items"
TEST_CREDENTIAL = "codacy-active-" + "credential-value"
TEST_ENVIRONMENT_NAME = "CODACY_API_TOKEN"
TEST_IPV6_HOST = "2001:db8::c0de"
HTTP_SERVICE_UNAVAILABLE = 503
HTTP_OK = 200
EXPECTED_GET_ATTEMPTS = 3
EXPECTED_REDACTIONS = 5
EXPECTED_PAGINATION_CALLS = 2
EXPECTED_TWO_ATTEMPTS = 2
EXPECTED_MAX_DELAY = 60.0
TEST_HTTPS_PORT = 8443
CLI_ERROR = 1


class ApiResultView(Protocol):
    """Typed view of the dynamically loaded result dataclass."""

    payload: JsonValue
    response_bytes: int
    status: int
    url: str


class RequestPlanView(Protocol):
    """Typed view of the dynamically loaded request-plan dataclass."""

    query: dict[str, str]


class FakeResponse:
    """Small urllib-compatible response that records bounded read sizes."""

    def __init__(
        self,
        body: bytes,
        *,
        content_length: str | None = None,
        read_error: BaseException | None = None,
        status: int = HTTP_OK,
    ) -> None:
        """Initialize a response with optional declared length and status."""
        super().__init__()
        self._stream = BytesIO(body)
        self.headers = Message()
        if content_length is not None:
            self.headers["Content-Length"] = content_length
        self._read_error = read_error
        self.closed = False
        self.read_sizes: list[int] = []
        self.status = status

    def __enter__(self) -> Self:
        """Enter a response context."""
        return self

    def __exit__(self, *_arguments: object) -> None:
        """Close the response stream."""
        self.close()

    def close(self) -> None:
        """Close the response exactly as urllib would after context exit."""
        self.closed = True
        self._stream.close()

    def read(self, size: int = -1) -> bytes:
        """Read response bytes while recording the requested bound."""
        self.read_sizes.append(size)
        if self._read_error is not None:
            raise self._read_error
        return self._stream.read(size)


type TransportOutcome = FakeResponse | BaseException


class FakeOpener:
    """Return deterministic responses or raise deterministic transport errors."""

    def __init__(self, outcomes: list[TransportOutcome]) -> None:
        """Initialize the opener with ordered transport outcomes."""
        super().__init__()
        self._outcomes = iter(outcomes)
        self.requests: list[request.Request] = []

    def open(self, api_request: request.Request, *, timeout: float) -> FakeResponse:
        """Record a request and return its configured outcome."""
        del timeout
        self.requests.append(api_request)
        outcome = next(self._outcomes)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def load_script_module() -> ModuleType:
    """Load the Codacy helper without invoking its CLI entry point."""
    specification = importlib.util.spec_from_file_location("codacy_management_safety", SCRIPT_PATH)
    if specification is None or specification.loader is None:
        raise RuntimeError(f"Could not load test module: {SCRIPT_PATH}")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


CODACY = load_script_module()


def member(name: str) -> object:
    """Return one dynamically loaded helper member."""
    return getattr(CODACY, name)


def context(*, base_url: str = API_BASE_URL, token: str | None = TEST_CREDENTIAL) -> object:
    """Create a token-bearing Codacy context."""
    context_factory = cast("Callable[..., object]", member("CodacyContext"))
    return context_factory(
        base_url=base_url,
        repository_root=REPO_ROOT,
        slug=None,
        token=token,
        token_env_name=TEST_ENVIRONMENT_NAME if token else None,
    )


def plan(
    method: str = "GET",
    *,
    body: JsonValue = None,
    endpoint: str = "/items",
    operation_id: str | None = None,
    query: dict[str, str] | None = None,
) -> object:
    """Create a raw request plan."""
    plan_factory = cast("Callable[..., object]", member("RequestPlan"))
    return plan_factory(
        body=body,
        endpoint=endpoint,
        method=method,
        operation_id=operation_id,
        query=query or {},
    )


def runtime(*, retries: int = 3) -> object:
    """Create a no-delay request runtime."""
    runtime_factory = cast("Callable[..., object]", member("RequestRuntime"))
    return runtime_factory(retries=retries, retry_base_delay=0.0, timeout=1.0)


def http_failure(
    body: bytes = b'{"message":"temporary"}',
    *,
    headers: dict[str, str] | None = None,
    status: int = HTTP_SERVICE_UNAVAILABLE,
) -> error.HTTPError:
    """Create a retriable HTTP failure with a closable body."""
    message = Message()
    for name, value in (headers or {}).items():
        message[name] = value
    return error.HTTPError(API_URL, status, "fixture failure", message, BytesIO(body))


def install_opener(monkeypatch: pytest.MonkeyPatch, outcomes: list[TransportOutcome]) -> FakeOpener:
    """Install a deterministic opener for the dynamically loaded module."""
    opener = FakeOpener(outcomes)

    def build_opener(*_handlers: object) -> FakeOpener:
        return opener

    monkeypatch.setattr(request, "build_opener", build_opener)
    return opener


def encoded_text(value: str) -> str:
    """Percent-encode every byte so even normally safe characters are hidden."""
    return "".join(f"%{byte:02X}" for byte in value.encode())


def run_cli(*arguments: str, token: str = TEST_CREDENTIAL) -> subprocess.CompletedProcess[str]:
    """Run the helper with an active credential in an isolated environment."""
    environment = os.environ.copy()
    environment[TEST_ENVIRONMENT_NAME] = token
    return subprocess.run(  # noqa: S603  # Fixed current interpreter and repository-owned script.
        [sys.executable, str(SCRIPT_PATH), *arguments],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )


def nested_json(depth: int, leaf: JsonValue = "safe") -> JsonValue:
    """Build a deterministic JSON object with exactly ``depth`` container levels."""
    value = leaf
    for _level in range(depth):
        value = cast("JsonValue", {"level": value})
    return value


def write_openapi_fixture(path: Path, operation_id: str) -> Path:
    """Write one minimal operation fixture for CLI lookup ordering tests."""
    _ = path.write_text(
        "\n".join(
            (
                "paths:",
                "  /items:",
                "    post:",
                "      summary: fixture operation",
                f"      operationId: {operation_id}",
                "",
            )
        ),
        encoding="utf-8",
    )
    return path


def test_get_retries_transient_http_and_transport_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    """GET retries remain enabled for retriable HTTP and transport failures."""
    send = cast("Callable[..., object]", member("send_request"))
    success = FakeResponse(b'{"data":"ok"}')
    opener = install_opener(
        monkeypatch,
        [http_failure(), error.URLError(TimeoutError("timed out")), success],
    )
    sleeps: list[float] = []
    monkeypatch.setattr(time, "sleep", sleeps.append)

    result = cast("ApiResultView", send(context(), plan(), query={}, runtime=runtime(retries=2)))

    assert result.payload == {"data": "ok"}
    assert result.response_bytes == len(b'{"data":"ok"}')
    assert len(opener.requests) == EXPECTED_GET_ATTEMPTS
    assert sleeps == [0.0, 0.0]


def test_non_get_is_single_attempt_after_http_or_transport_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """Non-GET requests are never replayed after ambiguous failures."""
    send = cast("Callable[..., object]", member("send_request"))
    helper_error = cast("type[Exception]", member("CodacyCliError"))
    sleeps: list[float] = []
    monkeypatch.setattr(time, "sleep", sleeps.append)

    http_opener = install_opener(monkeypatch, [http_failure(), FakeResponse(b'{"unexpected":true}')])
    with pytest.raises(helper_error, match=r"(?is)HTTP 503.*indeterminate"):
        _ = send(
            context(),
            plan("POST", operation_id="searchRepositoryIssues"),
            query={},
            runtime=runtime(),
        )
    assert len(http_opener.requests) == 1

    timeout_opener = install_opener(
        monkeypatch,
        [error.URLError(TimeoutError("timed out")), FakeResponse(b'{"unexpected":true}')],
    )
    with pytest.raises(helper_error, match=r"(?is)Unable to reach Codacy.*indeterminate"):
        _ = send(context(), plan("DELETE"), query={}, runtime=runtime())
    assert len(timeout_opener.requests) == 1
    assert sleeps == []


@pytest.mark.parametrize(
    ("method", "status"),
    [
        ("POST", 408),
        ("PATCH", 429),
        ("DELETE", 500),
        ("POST", 502),
        ("PATCH", 503),
        ("DELETE", 599),
    ],
)
def test_ambiguous_write_http_statuses_never_replay_and_close(
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    status: int,
) -> None:
    """Timeout, throttling, and every server-error class preserve single-attempt write semantics."""
    send = cast("Callable[..., object]", member("send_request"))
    helper_error = cast("type[Exception]", member("CodacyCliError"))
    failure = http_failure(status=status)
    failure_stream = cast("BytesIO", failure.fp)
    opener = install_opener(monkeypatch, [failure, FakeResponse(b'{"unexpected":true}')])
    sleeps: list[float] = []
    monkeypatch.setattr(time, "sleep", sleeps.append)

    with pytest.raises(helper_error, match=rf"(?is)HTTP {status}.*indeterminate.*Verify current Codacy state"):
        _ = send(context(), plan(method), query={}, runtime=runtime())

    assert len(opener.requests) == 1
    assert failure_stream.closed
    assert sleeps == []


@pytest.mark.parametrize(
    ("method", "read_error"),
    [
        ("PATCH", OSError("sensitive read details")),
        ("DELETE", HTTPException("sensitive protocol details")),
    ],
)
def test_non_get_read_exceptions_are_closed_and_never_replayed(
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    read_error: BaseException,
) -> None:
    """A response read failure after a write receives safe indeterminate guidance without replay."""
    send = cast("Callable[..., object]", member("send_request"))
    helper_error = cast("type[Exception]", member("CodacyCliError"))
    response = FakeResponse(b"{}", read_error=read_error)
    opener = install_opener(monkeypatch, [response, FakeResponse(b'{"unexpected":true}')])

    with pytest.raises(helper_error, match=r"(?is)Unable to read or process.*indeterminate.*Verify") as caught:
        _ = send(context(), plan(method), query={}, runtime=runtime())

    assert "sensitive" not in str(caught.value)
    assert len(opener.requests) == 1
    assert response.closed


def test_non_get_oversize_and_nonfinite_responses_are_single_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bounded-read and strict-decode failures after writes do not replay the mutation."""
    send = cast("Callable[..., object]", member("send_request"))
    helper_error = cast("type[Exception]", member("CodacyCliError"))
    monkeypatch.setattr(CODACY, "MAX_API_RESPONSE_BYTES", 8)

    oversized = FakeResponse(b"x" * 9)
    oversized_opener = install_opener(monkeypatch, [oversized, FakeResponse(b'{"unexpected":true}')])
    with pytest.raises(helper_error, match=r"(?is)8-byte safety limit.*indeterminate.*Verify"):
        _ = send(context(), plan("POST"), query={}, runtime=runtime())
    assert len(oversized_opener.requests) == 1
    assert oversized.closed

    monkeypatch.setattr(CODACY, "MAX_API_RESPONSE_BYTES", 1024)
    nonfinite = FakeResponse(b'{"value":NaN}')
    nonfinite_opener = install_opener(monkeypatch, [nonfinite, FakeResponse(b'{"unexpected":true}')])
    with pytest.raises(helper_error, match=r"(?is)non-finite.*indeterminate.*Verify"):
        _ = send(context(), plan("PATCH"), query={}, runtime=runtime())
    assert len(nonfinite_opener.requests) == 1
    assert nonfinite.closed


def test_get_may_retry_post_send_read_failure_and_closes_each_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET remains the only method eligible for replay after a response read failure."""
    send = cast("Callable[..., object]", member("send_request"))
    failed = FakeResponse(b"{}", read_error=OSError("read failed"))
    success = FakeResponse(b'{"data":"ok"}')
    opener = install_opener(monkeypatch, [failed, success])
    sleeps: list[float] = []
    monkeypatch.setattr(time, "sleep", sleeps.append)

    result = cast("ApiResultView", send(context(), plan(), query={}, runtime=runtime(retries=1)))

    assert result.payload == {"data": "ok"}
    assert len(opener.requests) == EXPECTED_TWO_ATTEMPTS
    assert failed.closed
    assert success.closed
    assert sleeps == [0.0]


def test_non_get_output_processing_failure_is_indeterminate_and_atomic(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A failure while redacting a sent write response emits no partial stdout and is not replayed."""
    handle_request = cast("Callable[[argparse.Namespace], int]", member("handle_request"))
    build_parser = cast("Callable[[], argparse.ArgumentParser]", member("build_parser"))
    helper_error = cast("type[Exception]", member("CodacyCliError"))
    response = FakeResponse(b'{"data":"ok"}')
    opener = install_opener(monkeypatch, [response, FakeResponse(b'{"unexpected":true}')])
    monkeypatch.setenv(TEST_ENVIRONMENT_NAME, TEST_CREDENTIAL)
    arguments = build_parser().parse_args(
        ["request", "/items", "--method", "DELETE", "--send", "--json", "--retries", "3"]
    )

    def fail_redaction(_value: JsonValue, _token: str | None = None) -> JsonValue:
        raise helper_error("response redaction failed safely")

    monkeypatch.setattr(CODACY, "redact_json", fail_redaction)
    with pytest.raises(helper_error, match=r"(?is)redaction failed safely.*indeterminate.*Verify"):
        _ = handle_request(arguments)

    assert capsys.readouterr().out == ""
    assert len(opener.requests) == 1
    assert response.closed


def test_non_get_stdout_failure_is_indeterminate_without_replay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An output-device failure after a sent write retains the same verify-before-retry contract."""
    handle_request = cast("Callable[[argparse.Namespace], int]", member("handle_request"))
    build_parser = cast("Callable[[], argparse.ArgumentParser]", member("build_parser"))
    helper_error = cast("type[Exception]", member("CodacyCliError"))
    response = FakeResponse(b'{"data":"ok"}')
    opener = install_opener(monkeypatch, [response, FakeResponse(b'{"unexpected":true}')])
    monkeypatch.setenv(TEST_ENVIRONMENT_NAME, TEST_CREDENTIAL)
    arguments = build_parser().parse_args(
        ["request", "/items", "--method", "POST", "--send", "--json", "--retries", "3"]
    )

    class FailingWriter:
        """Reject the first and only atomic output write."""

        def write(self, _value: str) -> int:
            """Raise a deterministic output error."""
            raise OSError("sensitive output-device details")

    class OutputModule:
        """Provide only the stdout attribute used by the request handler."""

        stdout = FailingWriter()

    monkeypatch.setattr(CODACY, "sys", OutputModule())
    with pytest.raises(helper_error, match=r"(?is)Unable to write.*indeterminate.*Verify") as caught:
        _ = handle_request(arguments)

    assert "sensitive" not in str(caught.value)
    assert len(opener.requests) == 1
    assert response.closed


def test_cli_rejects_active_token_from_every_request_location() -> None:
    """CLI planning rejects plain and repeatedly encoded credentials before preview output."""
    encoded = encoded_text(TEST_CREDENTIAL)
    twice_encoded = parse.quote(encoded, safe="")
    cases = [
        ("request", f"/items/{TEST_CREDENTIAL}", "--dry-run", "--json"),
        ("request", "/items", "--query", f"value={TEST_CREDENTIAL}", "--dry-run", "--json"),
        (
            "request",
            "/items",
            "--method",
            "POST",
            "--body-json",
            json.dumps(TEST_CREDENTIAL),
            "--json",
        ),
        (
            "request",
            "/items",
            "--method",
            "POST",
            "--body-json",
            json.dumps([TEST_CREDENTIAL]),
            "--json",
        ),
        (
            "request",
            "/items",
            "--method",
            "POST",
            "--body-json",
            json.dumps({"nested": [{"value": TEST_CREDENTIAL}]}),
            "--json",
        ),
        ("request", f"/items/{encoded}", "--dry-run", "--json"),
        ("request", "/items", "--query", f"value={twice_encoded}", "--dry-run", "--json"),
    ]

    for arguments in cases:
        result = run_cli(*arguments)
        assert result.returncode == CLI_ERROR
        assert result.stdout == ""
        assert TEST_CREDENTIAL not in result.stderr
        assert "active Codacy credential" in result.stderr


@pytest.mark.parametrize(
    "hostname",
    [TEST_CREDENTIAL, encoded_text(TEST_CREDENTIAL), parse.quote(encoded_text(TEST_CREDENTIAL), safe="")],
)
def test_cli_rejects_active_token_in_url_hostname_without_output(hostname: str) -> None:
    """An active token cannot be reused as a plain or repeatedly encoded hostname."""
    result = run_cli(
        "request",
        "/items",
        "--base-url",
        f"https://{hostname}/api/v3",
        "--dry-run",
        "--json",
    )

    assert result.returncode == CLI_ERROR
    assert result.stdout == ""
    assert TEST_CREDENTIAL not in result.stderr
    assert encoded_text(TEST_CREDENTIAL) not in result.stderr
    assert "active Codacy credential" in result.stderr


def test_operation_id_token_check_precedes_lookup_and_conflict_is_compatible(
    tmp_path: Path,
) -> None:
    """Operation IDs are screened before I/O, while the established conflict wording remains."""
    missing_spec = tmp_path / "missing-openapi.yaml"
    encoded = encoded_text(TEST_CREDENTIAL)
    unsafe_lookup = run_cli(
        "request",
        "--operation-id",
        encoded,
        "--method",
        "GET",
        "--spec-file",
        str(missing_spec),
        "--json",
    )

    assert unsafe_lookup.returncode == CLI_ERROR
    assert unsafe_lookup.stdout == ""
    assert TEST_CREDENTIAL not in unsafe_lookup.stderr
    assert encoded not in unsafe_lookup.stderr
    assert "active Codacy credential" in unsafe_lookup.stderr
    assert "OpenAPI document" not in unsafe_lookup.stderr

    fixture = write_openapi_fixture(tmp_path / "openapi.yaml", "safeOperation")
    conflict = run_cli(
        "request",
        "--operation-id",
        "safeOperation",
        "--method",
        "GET",
        "--spec-file",
        str(fixture),
        "--json",
    )

    assert conflict.returncode == CLI_ERROR
    assert conflict.stdout == ""
    assert TEST_CREDENTIAL not in conflict.stderr
    assert "conflicts with OpenAPI operation" in conflict.stderr


@pytest.mark.parametrize(
    "unsafe_plan",
    [
        plan(endpoint=f"/items/{TEST_CREDENTIAL}"),
        plan(query={"value": TEST_CREDENTIAL}),
        plan(method="POST", body=TEST_CREDENTIAL),
        plan(method="POST", body=[TEST_CREDENTIAL]),
        plan(method="POST", body={"items": ["safe", {"nested": TEST_CREDENTIAL}]}),
        plan(endpoint=f"/items/{parse.quote(encoded_text(TEST_CREDENTIAL), safe='')}"),
    ],
)
def test_direct_transport_rejects_active_token_before_open(
    monkeypatch: pytest.MonkeyPatch,
    unsafe_plan: object,
) -> None:
    """Direct callers cannot bypass the credential boundary at transport time."""
    send = cast("Callable[..., object]", member("send_request"))
    helper_error = cast("type[Exception]", member("CodacyCliError"))
    opener = install_opener(monkeypatch, [FakeResponse(b'{"unexpected":true}')])
    unsafe_plan_view = cast("RequestPlanView", unsafe_plan)

    with pytest.raises(helper_error, match="active Codacy credential"):
        _ = send(context(), unsafe_plan, query=unsafe_plan_view.query, runtime=runtime(retries=0))

    assert opener.requests == []


@pytest.mark.parametrize(
    "hostname",
    [TEST_CREDENTIAL, encoded_text(TEST_CREDENTIAL), parse.quote(encoded_text(TEST_CREDENTIAL), safe="")],
)
def test_direct_transport_rejects_active_token_hostname_before_open(
    monkeypatch: pytest.MonkeyPatch,
    hostname: str,
) -> None:
    """Raw contexts cannot move the account credential into the authenticated authority."""
    send = cast("Callable[..., object]", member("send_request"))
    helper_error = cast("type[Exception]", member("CodacyCliError"))
    opener = install_opener(monkeypatch, [FakeResponse(b'{"unexpected":true}')])

    with pytest.raises(helper_error, match="active Codacy credential"):
        _ = send(
            context(base_url=f"https://{hostname}/api/v3"),
            plan(),
            query={},
            runtime=runtime(retries=0),
        )

    assert opener.requests == []


def test_transport_revalidates_query_added_after_planning(monkeypatch: pytest.MonkeyPatch) -> None:
    """The immediate transport check covers query values not present during planning."""
    send = cast("Callable[..., object]", member("send_request"))
    helper_error = cast("type[Exception]", member("CodacyCliError"))
    opener = install_opener(monkeypatch, [FakeResponse(b'{"unexpected":true}')])

    with pytest.raises(helper_error, match="active Codacy credential"):
        _ = send(
            context(),
            plan(),
            query={"ordinary": encoded_text(TEST_CREDENTIAL)},
            runtime=runtime(retries=0),
        )

    assert opener.requests == []


def test_recursive_output_redacts_active_and_unknown_url_credentials() -> None:
    """Returned URL strings cannot expose encoded active tokens or unknown signatures."""
    redact = cast("Callable[[JsonValue, str | None], JsonValue]", member("redact_json"))
    encoded = encoded_text(TEST_CREDENTIAL)
    unknown_query_key = "access_" + "token"
    unknown_query_credential = "unknown-access-" + "credential-value"
    unknown_signature = "unknown-signature-value"
    payload: JsonValue = {
        "plain": f"https://example.test/path/{encoded}?view=summary",
        "nested": [
            {
                "url": "https://example.test/callback?"
                + parse.urlencode(
                    {
                        unknown_query_key: unknown_query_credential,
                        "safe": "kept",
                        "X-Amz-Signature": unknown_signature,
                    }
                )
            }
        ],
        "resultUrl": f"https://example.test/api/v3/items?value={parse.quote(encoded, safe='')}",
    }

    redacted = redact(payload, TEST_CREDENTIAL)
    serialized = json.dumps(redacted, allow_nan=False)

    assert TEST_CREDENTIAL not in serialized
    assert encoded not in serialized
    assert unknown_query_credential not in serialized
    assert unknown_signature not in serialized
    assert "kept" in serialized
    assert "redacted" in serialized


@pytest.mark.parametrize("credential", ["<redacted>", "redacted"])
def test_redaction_marker_cannot_reproduce_active_credential(credential: str) -> None:
    """The fail-safe marker collapses when its own text would contain the active token."""
    redact = cast("Callable[[JsonValue, str | None], JsonValue]", member("redact_json"))
    payload: JsonValue = {
        "token": "unknown-value",
        "value": credential,
        "url": f"https://example.test/items?access_token={credential}",
    }

    serialized = json.dumps(redact(payload, credential), allow_nan=False)

    assert credential not in serialized


def test_url_redaction_sanitizes_token_hosts_and_preserves_ipv6_ports() -> None:
    """Authority redaction cannot leak a host token or corrupt valid bracketed IPv6 URLs."""
    redact_url = cast("Callable[[str, str | None], str]", member("redact_url"))
    unknown_signature = "unknown-signature-value"

    for hostname in (TEST_CREDENTIAL, encoded_text(TEST_CREDENTIAL)):
        redacted = redact_url(f"https://{hostname}:8443/items?view=summary", TEST_CREDENTIAL)
        parsed = parse.urlsplit(redacted)
        assert parsed.hostname == "redacted.invalid"
        assert parsed.port == TEST_HTTPS_PORT
        assert TEST_CREDENTIAL not in redacted
        assert encoded_text(TEST_CREDENTIAL) not in redacted

    for userinfo in (TEST_CREDENTIAL, encoded_text(TEST_CREDENTIAL)):
        redacted_userinfo = redact_url(f"https://{userinfo}@codacy.example.test:8443/items", TEST_CREDENTIAL)
        assert parse.urlsplit(redacted_userinfo).username == "redacted"
        assert TEST_CREDENTIAL not in redacted_userinfo
        assert encoded_text(TEST_CREDENTIAL) not in redacted_userinfo

    ipv6 = redact_url(
        f"https://[2001:db8::1]:8443/items?X-Amz-Signature={unknown_signature}&view=summary",
        TEST_CREDENTIAL,
    )
    parsed_ipv6 = parse.urlsplit(ipv6)
    assert parsed_ipv6.hostname == "2001:db8::1"
    assert parsed_ipv6.port == TEST_HTTPS_PORT
    assert unknown_signature not in ipv6
    assert parse.parse_qs(parsed_ipv6.query) == {"X-Amz-Signature": ["<redacted>"], "view": ["summary"]}

    redacted_active_ipv6 = redact_url(
        f"https://[{TEST_IPV6_HOST}]:8443/items",
        TEST_IPV6_HOST,
    )
    parsed_active_ipv6 = parse.urlsplit(redacted_active_ipv6)
    assert parsed_active_ipv6.hostname == "redacted.invalid"
    assert parsed_active_ipv6.port == TEST_HTTPS_PORT
    assert TEST_IPV6_HOST not in redacted_active_ipv6


def test_cli_rejects_active_ipv6_token_authority_without_echo() -> None:
    """A token that is itself an IPv6 literal is rejected and absent from diagnostics."""
    result = run_cli(
        "request",
        "/items",
        "--base-url",
        f"https://[{TEST_IPV6_HOST}]:8443/api/v3",
        "--dry-run",
        "--json",
        token=TEST_IPV6_HOST,
    )

    assert result.returncode == CLI_ERROR
    assert result.stdout == ""
    assert TEST_IPV6_HOST not in result.stderr
    assert "active Codacy credential" in result.stderr


def test_success_output_redacts_url_strings_with_token_authorities(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Recursive API-result output redacts active-token authorities before stdout."""
    handle_request = cast("Callable[[argparse.Namespace], int]", member("handle_request"))
    build_parser = cast("Callable[[], argparse.ArgumentParser]", member("build_parser"))
    returned_url = f"https://{encoded_text(TEST_CREDENTIAL)}:8443/callback?view=summary"
    response = FakeResponse(json.dumps({"data": [{"returnedUrl": returned_url}]}).encode())
    opener = install_opener(monkeypatch, [response])
    monkeypatch.setenv(TEST_ENVIRONMENT_NAME, TEST_CREDENTIAL)
    arguments = build_parser().parse_args(["request", "/items", "--json", "--retries", "0"])

    assert handle_request(arguments) == 0
    output = capsys.readouterr().out
    payload = cast("dict[str, JsonValue]", json.loads(output))
    serialized = json.dumps(payload, allow_nan=False)

    assert len(opener.requests) == 1
    assert response.closed
    assert TEST_CREDENTIAL not in serialized
    assert encoded_text(TEST_CREDENTIAL) not in serialized
    assert "redacted.invalid:8443" in serialized


def test_http_error_json_is_recursively_redacted_with_bounded_text_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Structured error secrets are redacted and malformed fallback text stays bounded."""
    read_error_body = cast("Callable[[error.HTTPError, str | None], str]", member("read_error_body"))
    unknown_access_token_key = "access" + "Token"
    unknown_access_token = "unknown-access-" + "token"
    structured = {
        "error": {
            "authorization": "Bearer unknown-secret",
            "details": [
                {
                    unknown_access_token_key: unknown_access_token,
                    "apiKey": "unknown-api-key",
                    "password": "unknown-password",
                    "safe": "kept",
                }
            ],
            "message": f"active={TEST_CREDENTIAL}",
        }
    }
    structured_error = http_failure(json.dumps(structured).encode())
    output = read_error_body(structured_error, TEST_CREDENTIAL)
    structured_error.close()

    assert "unknown-secret" not in output
    assert unknown_access_token not in output
    assert "unknown-api-key" not in output
    assert "unknown-password" not in output
    assert TEST_CREDENTIAL not in output
    assert output.count("<redacted>") == EXPECTED_REDACTIONS
    assert "kept" in output

    monkeypatch.setattr(CODACY, "MAX_UNTRUSTED_TEXT", 40)
    unknown_payload_marker = "unknown-plain-text-secret"
    malformed_error = http_failure((f"not-json {TEST_CREDENTIAL} {unknown_payload_marker} " + ("x" * 200)).encode())
    fallback = read_error_body(malformed_error, TEST_CREDENTIAL)
    malformed_error.close()

    assert TEST_CREDENTIAL not in fallback
    assert unknown_payload_marker not in fallback
    assert fallback.startswith("[untrusted-codacy-text] ")
    assert len(fallback) <= len("[untrusted-codacy-text] ") + 40


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity", "1e9999"])
def test_cli_rejects_non_finite_json_before_stdout(constant: str) -> None:
    """CLI request bodies reject all representations that decode to non-finite floats."""
    result = run_cli(
        "request",
        "/items",
        "--method",
        "POST",
        "--body-json",
        f'{{"value":{constant}}}',
        "--json",
    )

    assert result.returncode == CLI_ERROR
    assert result.stdout == ""
    assert "non-finite" in result.stderr


@pytest.mark.parametrize("constant", [b"NaN", b"Infinity", b"-Infinity", b"1e9999"])
def test_api_responses_reject_non_finite_json(constant: bytes) -> None:
    """API decoding rejects non-finite JSON instead of emitting Python extensions."""
    decode = cast("Callable[[bytes, str | None], JsonValue]", member("decode_api_response"))
    helper_error = cast("type[Exception]", member("CodacyCliError"))

    with pytest.raises(helper_error, match="non-finite JSON number"):
        _ = decode(b'{"value":' + constant + b"}", TEST_CREDENTIAL)


def test_non_finite_error_json_is_omitted_and_output_serialization_is_atomic(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Non-standard error JSON is omitted and output failures write no partial stdout."""
    read_error_body = cast("Callable[[error.HTTPError, str | None], str]", member("read_error_body"))
    write_json = cast("Callable[[JsonValue], None]", member("write_json"))
    helper_error = cast("type[Exception]", member("CodacyCliError"))
    response_error = http_failure(b'{"value":NaN,"token":"unknown"}')

    details = read_error_body(response_error, TEST_CREDENTIAL)
    response_error.close()
    assert "NaN" not in details
    assert "unknown" not in details
    assert "omitted" in details

    with pytest.raises(helper_error, match="strict JSON"):
        write_json({"value": math.nan})
    assert capsys.readouterr().out == ""


def test_direct_request_rejects_non_finite_body_before_open(monkeypatch: pytest.MonkeyPatch) -> None:
    """Direct transport calls enforce allow_nan=False before allocating a request."""
    send = cast("Callable[..., object]", member("send_request"))
    helper_error = cast("type[Exception]", member("CodacyCliError"))
    opener = install_opener(monkeypatch, [FakeResponse(b'{"unexpected":true}')])

    with pytest.raises(helper_error, match="strict JSON"):
        _ = send(
            context(),
            plan(method="POST", body={"nested": [math.inf]}),
            query={},
            runtime=runtime(retries=0),
        )
    assert opener.requests == []


def test_json_depth_boundary_for_request_redaction_and_final_serialization(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Request parsing, redaction, and output share one explicit container-depth limit."""
    load_json = cast("Callable[[str, str], JsonValue]", member("load_json_value"))
    redact = cast("Callable[[JsonValue, str | None], JsonValue]", member("redact_json"))
    serialize = cast("Callable[..., str]", member("strict_json_dumps"))
    write_json = cast("Callable[[JsonValue], None]", member("write_json"))
    helper_error = cast("type[Exception]", member("CodacyCliError"))
    depth_limit = cast("int", member("MAX_JSON_NESTING_DEPTH"))
    marker = "depth-secret-marker"
    within_limit = nested_json(depth_limit, marker)
    above_limit = nested_json(depth_limit + 1, marker)
    within_text = json.dumps(within_limit, allow_nan=False)
    above_text = json.dumps(above_limit, allow_nan=False)

    assert load_json(within_text, "--body-json") == within_limit
    assert redact(within_limit, TEST_CREDENTIAL) == within_limit
    assert json.loads(serialize(within_limit, "test output")) == within_limit
    write_json(within_limit)
    assert json.loads(capsys.readouterr().out) == within_limit

    with pytest.raises(helper_error, match=rf"{depth_limit}-level") as request_failure:
        _ = load_json(above_text, "--body-json")
    with pytest.raises(helper_error, match=rf"{depth_limit}-level") as redaction_failure:
        _ = redact(above_limit, TEST_CREDENTIAL)
    with pytest.raises(helper_error, match=rf"{depth_limit}-level") as serialization_failure:
        _ = serialize(above_limit, "test output")
    with pytest.raises(helper_error, match=rf"{depth_limit}-level") as output_failure:
        write_json(above_limit)

    assert capsys.readouterr().out == ""
    for failure in (request_failure, redaction_failure, serialization_failure, output_failure):
        assert marker not in str(failure.value)


def test_cli_json_depth_failure_is_non_echoing_and_atomic() -> None:
    """An over-depth CLI body fails before preview stdout without echoing its leaf data."""
    depth_limit = cast("int", member("MAX_JSON_NESTING_DEPTH"))
    marker = "cli-depth-secret-marker"
    result = run_cli(
        "request",
        "/items",
        "--method",
        "POST",
        "--body-json",
        json.dumps(nested_json(depth_limit + 1, marker), allow_nan=False),
        "--json",
    )

    assert result.returncode == CLI_ERROR
    assert result.stdout == ""
    assert f"{depth_limit}-level" in result.stderr
    assert marker not in result.stderr
    assert "Traceback" not in result.stderr


def test_json_depth_boundary_for_success_and_error_responses() -> None:
    """Successful and error response decoders enforce depth without leaking deep leaf text."""
    decode = cast("Callable[[bytes, str | None], JsonValue]", member("decode_api_response"))
    read_error_body = cast("Callable[[error.HTTPError, str | None], str]", member("read_error_body"))
    helper_error = cast("type[Exception]", member("CodacyCliError"))
    depth_limit = cast("int", member("MAX_JSON_NESTING_DEPTH"))
    marker = "response-depth-secret-marker"
    within_limit = nested_json(depth_limit, TEST_CREDENTIAL)
    above_limit = nested_json(depth_limit + 1, marker)
    within_raw = json.dumps(within_limit, allow_nan=False).encode()
    above_raw = json.dumps(above_limit, allow_nan=False).encode()

    assert decode(within_raw, TEST_CREDENTIAL) == within_limit
    with pytest.raises(helper_error, match=rf"{depth_limit}-level") as success_failure:
        _ = decode(above_raw, TEST_CREDENTIAL)
    assert marker not in str(success_failure.value)

    within_error = http_failure(within_raw)
    above_error = http_failure(above_raw)
    try:
        within_details = read_error_body(within_error, TEST_CREDENTIAL)
        above_details = read_error_body(above_error, TEST_CREDENTIAL)
    finally:
        within_error.close()
        above_error.close()
    assert TEST_CREDENTIAL not in within_details
    assert "redacted" in within_details
    assert marker not in above_details
    assert "omitted" in above_details


def test_extreme_json_depth_never_surfaces_recursion_or_leaf_text() -> None:
    """Decoder recursion limits are translated to non-echoing helper failures on every input surface."""
    load_json = cast("Callable[[str, str], JsonValue]", member("load_json_value"))
    decode = cast("Callable[[bytes, str | None], JsonValue]", member("decode_api_response"))
    read_error_body = cast("Callable[[error.HTTPError, str | None], str]", member("read_error_body"))
    helper_error = cast("type[Exception]", member("CodacyCliError"))
    marker = "extreme-depth-secret-marker"
    extreme_text = ("[" * 2000) + json.dumps(marker) + ("]" * 2000)

    with pytest.raises(helper_error) as request_failure:
        _ = load_json(extreme_text, "--body-json")
    with pytest.raises(helper_error) as response_failure:
        _ = decode(extreme_text.encode(), TEST_CREDENTIAL)

    response_error = http_failure(extreme_text.encode())
    try:
        error_details = read_error_body(response_error, TEST_CREDENTIAL)
    finally:
        response_error.close()

    assert marker not in str(request_failure.value)
    assert marker not in str(response_failure.value)
    assert marker not in error_details
    assert "Traceback" not in str(request_failure.value)
    assert "Traceback" not in str(response_failure.value)


def test_openapi_download_rejects_oversize_without_content_length(monkeypatch: pytest.MonkeyPatch) -> None:
    """OpenAPI downloads enforce actual bytes when Content-Length is missing."""
    load_openapi = cast("Callable[..., object]", member("load_openapi_document"))
    helper_error = cast("type[Exception]", member("CodacyCliError"))
    monkeypatch.setattr(CODACY, "MAX_OPENAPI_BYTES", 8)
    response = FakeResponse(b"x" * 9)
    _ = install_opener(monkeypatch, [response])
    arguments = argparse.Namespace(spec_file=None, spec_url=None, timeout=1.0)

    with pytest.raises(helper_error, match="8-byte safety limit"):
        _ = load_openapi(arguments, context())

    assert response.read_sizes == [9]


@pytest.mark.parametrize("content_length", [None, "1"])
def test_api_response_rejects_oversize_with_missing_or_dishonest_length(
    monkeypatch: pytest.MonkeyPatch,
    content_length: str | None,
) -> None:
    """API reads enforce actual bytes despite absent or understated lengths."""
    send = cast("Callable[..., object]", member("send_request"))
    helper_error = cast("type[Exception]", member("CodacyCliError"))
    monkeypatch.setattr(CODACY, "MAX_API_RESPONSE_BYTES", 8)
    response = FakeResponse(b"x" * 9, content_length=content_length)
    opener = install_opener(monkeypatch, [response])

    with pytest.raises(helper_error, match="8-byte safety limit"):
        _ = send(context(), plan(), query={}, runtime=runtime(retries=0))

    assert len(opener.requests) == 1
    assert response.read_sizes == [9]


def test_api_response_rejects_oversize_declared_length_before_read(monkeypatch: pytest.MonkeyPatch) -> None:
    """An oversized declared length fails before response body allocation."""
    send = cast("Callable[..., object]", member("send_request"))
    helper_error = cast("type[Exception]", member("CodacyCliError"))
    monkeypatch.setattr(CODACY, "MAX_API_RESPONSE_BYTES", 8)
    response = FakeResponse(b"{}", content_length="9")
    _ = install_opener(monkeypatch, [response])

    with pytest.raises(helper_error, match="8-byte safety limit"):
        _ = send(context(), plan(), query={}, runtime=runtime(retries=0))

    assert response.read_sizes == []


@pytest.mark.parametrize(
    ("option", "value"),
    [
        ("--timeout", "NaN"),
        ("--timeout", "Infinity"),
        ("--timeout", "-Infinity"),
        ("--timeout", "0"),
        ("--timeout", "301"),
        ("--retry-delay", "NaN"),
        ("--retry-delay", "Infinity"),
        ("--retry-delay", "-Infinity"),
        ("--retry-delay", "-1"),
        ("--retry-delay", "61"),
        ("--retries", "-1"),
        ("--retries", "11"),
        ("--max-pages", "0"),
        ("--max-pages", "501"),
    ],
)
def test_cli_rejects_non_finite_negative_and_over_cap_numeric_controls(option: str, value: str) -> None:
    """All network and pagination numeric controls are finite and explicitly capped."""
    result = run_cli("request", "/items", "--dry-run", "--json", f"{option}={value}")

    assert result.returncode == CLI_ERROR
    assert result.stdout == ""
    assert option in result.stderr


@pytest.mark.parametrize(
    "retry_after",
    [
        "malformed",
        "NaN",
        "Infinity",
        "-Infinity",
        "-1",
        "+1",
        "1.5",
        "1e2",
        " 10 ",
        "\uff11\uff12",
        "Wed, 21 Oct 2015 07:28:00",
        "Wed, 21 Oct 2015 07:28:00 XYZ",
    ],
)
def test_retry_after_rejects_malformed_non_finite_and_negative_values(retry_after: str) -> None:
    """Invalid Retry-After values fall back to overflow-safe configured backoff."""
    delay = cast("Callable[[error.HTTPError, int, float], float]", member("retry_delay"))
    response_error = http_failure(headers={"Retry-After": retry_after})
    try:
        assert delay(response_error, 1, 0.5) == 1.0
    finally:
        response_error.close()


def test_backoff_is_overflow_safe_and_retry_after_is_capped() -> None:
    """Huge attempts and Retry-After values saturate without exponentiation overflow."""
    backoff = cast("Callable[[int, float], float]", member("backoff_delay"))
    delay = cast("Callable[[error.HTTPError, int, float], float]", member("retry_delay"))
    response_error = http_failure(headers={"Retry-After": "999999999999"})
    try:
        assert delay(response_error, 1, 0.5) == EXPECTED_MAX_DELAY
    finally:
        response_error.close()
    assert backoff(10**9, 1.0) == EXPECTED_MAX_DELAY


def test_retry_after_accepts_ascii_delay_seconds_and_http_dates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Retry-After accepts only ASCII integers or aware HTTP dates, using a deterministic clock."""
    delay = cast("Callable[[error.HTTPError, int, float], float]", member("retry_delay"))
    fixed_now = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
    monkeypatch.setattr(CODACY, "current_utc_time", lambda: fixed_now)
    cases = [
        ("0", 0.0),
        ("0005", 5.0),
        ("60", EXPECTED_MAX_DELAY),
        ("999999999999999999999999999999", EXPECTED_MAX_DELAY),
        (format_datetime(fixed_now + timedelta(seconds=30), usegmt=True), 30.0),
        (format_datetime(fixed_now + timedelta(seconds=120), usegmt=True), EXPECTED_MAX_DELAY),
        (format_datetime(fixed_now - timedelta(seconds=30), usegmt=True), 0.0),
    ]

    for retry_after, expected in cases:
        response_error = http_failure(headers={"Retry-After": retry_after})
        try:
            assert delay(response_error, 1, 0.5) == expected
        finally:
            response_error.close()


def test_direct_transport_rejects_invalid_runtime_before_open(monkeypatch: pytest.MonkeyPatch) -> None:
    """Direct callers cannot bypass finite runtime controls enforced by the CLI."""
    send = cast("Callable[..., object]", member("send_request"))
    runtime_factory = cast("Callable[..., object]", member("RequestRuntime"))
    helper_error = cast("type[Exception]", member("CodacyCliError"))
    opener = install_opener(monkeypatch, [FakeResponse(b'{"unexpected":true}')])
    invalid_runtime = runtime_factory(retries=11, retry_base_delay=math.nan, timeout=math.inf)

    with pytest.raises(helper_error):
        _ = send(context(), plan(), query={}, runtime=invalid_runtime)
    assert opener.requests == []


def test_self_hosted_base_is_canonical_and_gitlab_subgroups_remain_supported() -> None:
    """Custom hosts retain canonical v3 routing and one encoded subgroup separator."""
    sanitize = cast("Callable[[str], str]", member("sanitize_base_url"))
    build_url = cast("Callable[[str, str, dict[str, str]], str]", member("build_url"))
    base_url = "https://codacy.example.test/api/v3"

    assert sanitize(f"{base_url}/") == base_url
    subgroup_url = build_url(
        base_url,
        "/analysis/organizations/gl/group%2Fsubgroup/repositories/project",
        {},
    )
    assert parse.unquote(parse.urlsplit(subgroup_url).path).startswith(
        "/api/v3/analysis/organizations/gl/group/subgroup"
    )


@pytest.mark.parametrize(
    "base_url",
    [
        "https://codacy.example.test:not-a-port/api/v3",
        "https://codacy.example.test:0/api/v3",
        "https://codacy.example.test:65536/api/v3",
        "https://codacy.example.test:/api/v3",
        "https:///api/v3",
        "https://:443/api/v3",
        "https://[2001:db8::1/api/v3",
        "https://2001:db8::1/api/v3",
    ],
)
def test_self_hosted_base_rejects_malformed_or_invalid_authorities(base_url: str) -> None:
    """Malformed hosts and explicit ports never escape as urllib ValueError exceptions."""
    sanitize = cast("Callable[[str], str]", member("sanitize_base_url"))
    helper_error = cast("type[Exception]", member("CodacyCliError"))

    with pytest.raises(helper_error):
        _ = sanitize(base_url)


def test_ipv6_and_default_https_ports_preserve_same_origin_contract() -> None:
    """Bracketed IPv6 remains valid, and implicit HTTPS equals an explicit port 443."""
    sanitize = cast("Callable[[str], str]", member("sanitize_base_url"))
    same_origin = cast("Callable[[str, str], bool]", member("same_origin_and_base_path"))

    assert sanitize("https://[2001:db8::1]/api/v3/") == "https://[2001:db8::1]/api/v3"
    assert sanitize("https://[2001:db8::1]:8443/api/v3") == "https://[2001:db8::1]:8443/api/v3"
    assert same_origin(
        "https://codacy.example.test/api/v3",
        "https://codacy.example.test:443/api/v3/items",
    )
    assert same_origin(
        "https://codacy.example.test:443/api/v3",
        "https://codacy.example.test/api/v3/items",
    )
    assert same_origin(
        "https://[2001:db8::1]/api/v3",
        "https://[2001:db8::1]:443/api/v3/items",
    )
    assert not same_origin(
        "https://codacy.example.test:not-a-port/api/v3",
        "https://codacy.example.test:not-a-port/api/v3/items",
    )


@pytest.mark.parametrize(
    "base_url",
    [
        "https://codacy.example.test/API/v3",
        "https://codacy.example.test/api/V3",
        "https://codacy.example.test/api%2Fv3",
        "https://codacy.example.test/api/v3//",
        "https://codacy.example.test/api/v3/extra",
    ],
)
def test_base_url_rejects_mixed_case_encoded_or_noncanonical_paths(base_url: str) -> None:
    """Self-hosted origin flexibility does not weaken the exact /api/v3 base contract."""
    sanitize = cast("Callable[[str], str]", member("sanitize_base_url"))
    helper_error = cast("type[Exception]", member("CodacyCliError"))

    with pytest.raises(helper_error, match="exactly /api/v3"):
        _ = sanitize(base_url)


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://codacy.example.test/API/v3/items",
        "https://codacy.example.test/api%2Fv3/items",
        "https://codacy.example.test/api/v3/%2e%2e/admin",
        "https://codacy.example.test/api/v3/%252e%252e/admin",
        "https://codacy.example.test/api/v3/group%252Fsubgroup/items",
        "https://codacy.example.test/api/v3/%5cadmin",
        "https://codacy.example.test/api/v3/%255cadmin",
        "https://codacy.example.test/api/v3/item%3Fadmin=true",
        "/%2e%2e/admin",
    ],
)
def test_endpoint_rejects_encoded_separators_nested_encoding_and_base_escapes(endpoint: str) -> None:
    """Repeated decoding cannot introduce traversal, backslashes, delimiters, or base escapes."""
    build_url = cast("Callable[[str, str, dict[str, str]], str]", member("build_url"))
    helper_error = cast("type[Exception]", member("CodacyCliError"))

    with pytest.raises(helper_error):
        _ = build_url("https://codacy.example.test/api/v3", endpoint, {})


@pytest.mark.parametrize(
    "payload",
    [
        {"data": [], "pagination": None},
        {"data": [], "pagination": []},
        {"data": [], "pagination": {"cursor": None}},
        {"data": [], "pagination": {"cursor": 1}},
        {"data": [], "pagination": {"cursor": ""}},
        {"data": [], "pagination": {"cursor": "   "}},
        {"data": [], "pagination": {"cursor": " next"}},
    ],
)
def test_pagination_rejects_present_malformed_metadata(
    monkeypatch: pytest.MonkeyPatch,
    payload: dict[str, JsonValue],
) -> None:
    """Present pagination metadata is strict; only absent pagination or cursor completes."""
    paginate = cast("Callable[..., object]", member("paginate_request"))
    result_factory = cast("Callable[..., object]", member("ApiResult"))
    helper_error = cast("type[Exception]", member("CodacyCliError"))

    def fake_send(*_arguments: object, **_keywords: object) -> object:
        return result_factory(
            payload=payload,
            status=HTTP_OK,
            url=API_URL,
            response_bytes=2,
        )

    monkeypatch.setattr(CODACY, "send_request", fake_send)

    with pytest.raises(helper_error, match=r"pagination|cursor"):
        _ = paginate(context(), plan(), max_pages=2, runtime=runtime())


@pytest.mark.parametrize("payload", [{"data": []}, {"data": [], "pagination": {}}])
def test_pagination_absent_metadata_completes_with_truthful_page_count(
    monkeypatch: pytest.MonkeyPatch,
    payload: dict[str, JsonValue],
) -> None:
    """An absent pagination object or absent cursor completes on the current page."""
    paginate = cast("Callable[..., object]", member("paginate_request"))
    result_factory = cast("Callable[..., object]", member("ApiResult"))

    def fake_send(*_arguments: object, **_keywords: object) -> object:
        return result_factory(
            payload=payload,
            status=HTTP_OK,
            url=API_URL,
            response_bytes=2,
        )

    monkeypatch.setattr(CODACY, "send_request", fake_send)

    result = cast("ApiResultView", paginate(context(), plan(), max_pages=1, runtime=runtime()))
    assert result.payload == {**payload, "data": [], "paginationFetch": {"fetchedCount": 0, "fetchedPages": 1}}


def test_pagination_exact_max_page_fails_when_cursor_proves_incomplete(monkeypatch: pytest.MonkeyPatch) -> None:
    """A cursor on the exact page cap fails instead of returning silently truncated data."""
    paginate = cast("Callable[..., object]", member("paginate_request"))
    result_factory = cast("Callable[..., object]", member("ApiResult"))
    helper_error = cast("type[Exception]", member("CodacyCliError"))
    calls = 0

    def fake_send(*_arguments: object, **_keywords: object) -> object:
        nonlocal calls
        calls += 1
        return result_factory(
            payload={"data": [{"id": 1}], "pagination": {"cursor": "next"}},
            status=HTTP_OK,
            url=API_URL,
            response_bytes=2,
        )

    monkeypatch.setattr(CODACY, "send_request", fake_send)
    with pytest.raises(helper_error, match="output is incomplete"):
        _ = paginate(context(), plan(), max_pages=1, runtime=runtime())
    assert calls == 1


def test_pagination_enforces_cumulative_response_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Many individually valid pages cannot exceed the cumulative byte limit."""
    paginate = cast("Callable[..., object]", member("paginate_request"))
    result_factory = cast("Callable[..., object]", member("ApiResult"))
    helper_error = cast("type[Exception]", member("CodacyCliError"))
    monkeypatch.setattr(CODACY, "MAX_PAGINATED_RESPONSE_BYTES", 10)
    responses = iter(
        [
            result_factory(
                payload={"data": [{"id": 1}], "pagination": {"cursor": "next"}},
                status=HTTP_OK,
                url=API_URL,
                response_bytes=6,
            ),
            result_factory(
                payload={"data": [{"id": 2}], "pagination": {}},
                status=HTTP_OK,
                url=API_URL,
                response_bytes=5,
            ),
        ]
    )
    calls = 0

    def fake_send(*_arguments: object, **_keywords: object) -> object:
        nonlocal calls
        calls += 1
        return next(responses)

    monkeypatch.setattr(CODACY, "send_request", fake_send)

    with pytest.raises(helper_error, match="10-byte cumulative safety limit"):
        _ = paginate(context(), plan(), max_pages=3, runtime=runtime())

    assert calls == EXPECTED_PAGINATION_CALLS
