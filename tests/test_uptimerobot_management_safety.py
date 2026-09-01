# Copyright (c) 2026 Nick2bad4u
"""Deterministic safety regressions for the UptimeRobot management helper."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from email.message import Message
from email.utils import format_datetime
from http.client import HTTPException, IncompleteRead
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Self, cast, override
from urllib import error, parse, request

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import ModuleType, TracebackType

type JsonValue = bool | int | float | str | list[JsonValue] | dict[str, JsonValue] | None

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "skills" / "uptimerobot-management" / "scripts" / "manage_uptimerobot.py"
API_BASE_URL = "https://api.uptimerobot.com/v3"
SPEC_URL = "https://cdn.uptimerobot.com/api/openapi.yaml"
TEST_CREDENTIAL_VALUE = "configured-uptimerobot-value"
RESERVED_READ_CREDENTIAL = "read/oauth+synthetic value%"
RESERVED_MAIN_CREDENTIAL = "main/oauth+synthetic value%"
HEARTBEAT_CALLBACK_SEGMENT = "heartbeat-callback-segment"
PATH_WEBHOOK_SEGMENT = "private-path-webhook-segment"
REDACTED = "<redacted>"
EXPECTED_RETRY_FALLBACK = 8.0
EXPECTED_GET_ATTEMPT_COUNT = 3
EXPECTED_PAGE_COUNT = 2
EXPECTED_RETRIED_REQUEST_COUNT = 2
EXPECTED_HTTP_DATE_DELAY = 30.0
MAX_EXPECTED_RETRY_DELAY = 60.0
HTTP_OK = 200
TRANSIENT_STATUSES = [429, 500, 502, 503, 504]
INDETERMINATE_STATUSES = [500, 502, 503, 504]
DEFINITIVE_CLIENT_STATUSES = [400, 401, 403, 404, 409, 422, 429]
WRITE_METHODS = ["POST", "PUT", "PATCH", "DELETE"]


class RecordingStream(BytesIO):
    """Byte stream that records bounded read sizes."""

    def __init__(self, body: bytes) -> None:
        """Initialize the recorded byte stream."""
        super().__init__(body)
        self.read_sizes: list[int] = []

    @override
    def read(self, size: int | None = -1) -> bytes:
        self.read_sizes.append(-1 if size is None else size)
        return super().read(size)


class FailingStream(RecordingStream):
    """Closable stream that raises one configured response-consumption failure."""

    def __init__(self, exception: BaseException) -> None:
        """Initialize the failing read."""
        super().__init__(b"")
        self.exception = exception

    @override
    def read(self, size: int | None = -1) -> bytes:
        self.read_sizes.append(-1 if size is None else size)
        raise self.exception


class FakeResponse:
    """Urllib-compatible success response with closure evidence."""

    def __init__(
        self,
        body: bytes,
        *,
        content_length: str | None = None,
        content_type: str = "application/json",
        retry_after: str | None = None,
        status: int = HTTP_OK,
    ) -> None:
        """Initialize one deterministic response."""
        super().__init__()
        self._stream = RecordingStream(body)
        self.headers = Message()
        self.headers["Content-Type"] = content_type
        if content_length is not None:
            self.headers["Content-Length"] = content_length
        if retry_after is not None:
            self.headers["Retry-After"] = retry_after
        self.status = status

    @property
    def closed(self) -> bool:
        """Return whether the response stream was closed."""
        return self._stream.closed

    @property
    def read_sizes(self) -> list[int]:
        """Return every requested read size."""
        return self._stream.read_sizes

    def __enter__(self) -> Self:
        """Enter the response context."""
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close the response stream when leaving its context."""
        del exception_type, exception, traceback
        self._stream.close()

    def read(self, size: int | None = -1) -> bytes:
        """Read bytes from the response stream."""
        return self._stream.read(size)


class StreamResponse(FakeResponse):
    """Response backed by a caller-supplied instrumented stream."""

    def __init__(self, stream: RecordingStream, *, status: int) -> None:
        """Install the supplied stream after initializing response metadata."""
        super().__init__(b"", status=status)
        self._stream = stream


type TransportOutcome = FakeResponse | BaseException


class FakeOpener:
    """Consume deterministic transport outcomes."""

    def __init__(self, outcomes: list[TransportOutcome]) -> None:
        """Initialize deterministic transport outcomes."""
        super().__init__()
        self._outcomes = iter(outcomes)
        self.requests: list[request.Request] = []

    def open(self, api_request: request.Request, *, timeout: float) -> FakeResponse:
        """Record one request and return or raise its next outcome."""
        del timeout
        self.requests.append(api_request)
        outcome = next(self._outcomes)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class FakeSpecFile:
    """Path-like local OpenAPI source with closure evidence."""

    def __init__(self, stream: RecordingStream) -> None:
        """Initialize the one-use local stream."""
        super().__init__()
        self.stream = stream

    def open(self, mode: str) -> RecordingStream:
        """Return the fixture stream for a binary read."""
        assert mode == "rb"
        return self.stream

    @override
    def __str__(self) -> str:
        """Return a stable diagnostic source name."""
        return "fixture-openapi.json"


def load_script_module() -> ModuleType:
    """Load the repository helper without invoking its CLI entry point."""
    specification = importlib.util.spec_from_file_location("test_uptimerobot_management_safety", SCRIPT)
    if specification is None or specification.loader is None:
        raise RuntimeError(f"Could not load helper module: {SCRIPT}")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


UPTIMEROBOT = load_script_module()


def member(name: str) -> object:
    """Return one dynamically loaded helper member."""
    return getattr(UPTIMEROBOT, name)


def install_opener(monkeypatch: pytest.MonkeyPatch, outcomes: list[TransportOutcome]) -> FakeOpener:
    """Install a deterministic opener for the dynamically loaded helper."""
    opener = FakeOpener(outcomes)

    def build_opener(*_handlers: object) -> FakeOpener:
        return opener

    monkeypatch.setattr(request, "build_opener", build_opener)
    return opener


def credential(value: str = TEST_CREDENTIAL_VALUE) -> object:
    """Create one synthetic configured credential."""
    credential_type = cast("Callable[..., object]", member("Credential"))
    return credential_type(environment="TEST_UPTIME_TOKEN", value=value)


def uptime_context(
    *,
    read_value: str | None = TEST_CREDENTIAL_VALUE,
    main_value: str | None = None,
) -> object:
    """Create one synthetic UptimeRobot context."""
    context_type = cast("Callable[..., object]", member("UptimeRobotContext"))
    return context_type(
        base_url=API_BASE_URL,
        main_credential=None if main_value is None else credential(main_value),
        read_credential=None if read_value is None else credential(read_value),
        spec_url=SPEC_URL,
    )


def request_plan(method: str = "GET", *, body: JsonValue = None) -> object:
    """Create one direct transport plan."""
    plan_type = cast("Callable[..., object]", member("RequestPlan"))
    return plan_type(
        body=body,
        confirmation_value=None,
        high_risk=False,
        method=method,
        operation_id=None,
        query=(),
        url=f"{API_BASE_URL}/monitors",
    )


def request_arguments(*, retries: int = 0) -> argparse.Namespace:
    """Create direct transport controls."""
    return argparse.Namespace(retries=retries, timeout=1.0)


def http_failure(
    status: int,
    body: bytes = b"",
    *,
    content_length: str | None = None,
    retry_after: str | None = None,
) -> tuple[error.HTTPError, RecordingStream]:
    """Create a closable HTTP failure."""
    stream = RecordingStream(body)
    headers = Message()
    headers["Content-Type"] = "application/json"
    if content_length is not None:
        headers["Content-Length"] = content_length
    if retry_after is not None:
        headers["Retry-After"] = retry_after
    failure = error.HTTPError(f"{API_BASE_URL}/monitors", status, "fixture failure", headers, stream)
    return failure, stream


def http_failure_with_stream(
    status: int,
    stream: RecordingStream,
    *,
    content_length: str | None = None,
) -> error.HTTPError:
    """Create an HTTP failure backed by one instrumented stream."""
    headers = Message()
    headers["Content-Type"] = "application/json"
    if content_length is not None:
        headers["Content-Length"] = content_length
    return error.HTTPError(f"{API_BASE_URL}/monitors", status, "fixture failure", headers, stream)


def openapi_document() -> bytes:
    """Return one minimal valid OpenAPI contract."""
    return json.dumps(
        {
            "openapi": "3.0.0",
            "paths": {
                "/monitors": {
                    "get": {
                        "operationId": "MonitorsController_list",
                        "summary": "List monitors",
                    }
                }
            },
        },
        separators=(",", ":"),
    ).encode()


def encoded_variants(secret: str) -> tuple[str, ...]:
    """Return raw and mixed repeatedly encoded credential forms."""
    quoted = parse.quote(secret, safe="")
    form_encoded = parse.quote_plus(secret, safe="")
    return tuple(
        dict.fromkeys(
            (
                secret,
                quoted,
                form_encoded,
                parse.quote(quoted, safe=""),
                parse.quote_plus(form_encoded, safe=""),
                parse.quote_plus(parse.quote(form_encoded, safe=""), safe=""),
            )
        )
    )


def as_dict(value: object) -> dict[str, object]:
    """Narrow one decoded JSON object."""
    if not isinstance(value, dict):
        raise TypeError("Expected a JSON object.")
    return cast("dict[str, object]", value)


def clean_environment(**values: str) -> dict[str, str]:
    """Build a subprocess environment without real UptimeRobot credentials."""
    environment = os.environ.copy()
    for name in ("UPTIMEROBOT_API_KEY", "UPTIMEROBOT_READ_ONLY_API_KEY"):
        _ = environment.pop(name, None)
    environment.update(values)
    return environment


def run_script(
    *arguments: str,
    environment: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run the fixed repository helper without a shell."""
    return subprocess.run(  # noqa: S603  # Fixed interpreter and repository-owned script.
        [sys.executable, str(SCRIPT), *arguments],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        env=environment or clean_environment(),
        stdin=subprocess.DEVNULL,
        text=True,
    )


def write_openapi_fixture(path: Path) -> None:
    """Write the operation and query shapes needed by subprocess tests."""
    payload = {
        "openapi": "3.0.0",
        "paths": {
            "/monitors": {
                "get": {
                    "operationId": "MonitorsController_list",
                    "parameters": [
                        {
                            "name": "customField",
                            "in": "query",
                            "schema": {"type": "array", "items": {"type": "string"}},
                        },
                        {"name": "limit", "in": "query", "schema": {"type": "integer"}},
                    ],
                    "summary": "List monitors",
                    "tags": ["Monitors"],
                }
            },
            "/monitors/bulk/update": {
                "post": {
                    "operationId": "BulkMonitorsController_bulkUpdate",
                    "parameters": [
                        {"name": "scope", "in": "query", "schema": {"type": "string"}},
                    ],
                    "summary": "Update monitors in bulk",
                    "tags": ["Monitors - Bulk Operations"],
                }
            },
        },
    }
    _ = path.write_text(json.dumps(payload), encoding="utf-8")


def test_central_output_sanitization_covers_uptime_fields_and_encoded_secrets() -> None:
    """Redact capability URLs, headers, sensitive fields, and encoded secrets."""
    redact = cast("Callable[[JsonValue, tuple[str, ...]], JsonValue]", member("redact_json"))
    sanitized = redact(
        {
            "data": {
                "type": "HEARTBEAT",
                "url": f"https://heartbeat.uptimerobot.com/{HEARTBEAT_CALLBACK_SEGMENT}",
                "pingUrl": f"https://heartbeat.uptimerobot.com/{HEARTBEAT_CALLBACK_SEGMENT}",
                "Cookie": "session-cookie",
                "Set-Cookie": "response-cookie",
                "passphrase": "phrase",
                "private-key": "key-material",
                "request": {"headers": {"X-Ordinary": "must-not-print"}},
                "response": {"headers": [{"name": "Server", "value": "must-not-print"}]},
                "ordinary": "visible",
            },
            "integrations": [
                {"webhookURL": "https://discord.com/api/webhooks/path-capability"},
                {"urlToNotify": "https://hooks.slack.com/services/path-capability"},
                {"customHeaders": {"X-Capability": "must-not-print"}},
                {"postValue": "must-not-print"},
                {"type": "Slack", "value": "path-capability", "ordinary": "visible"},
                {"name": "opaque-integration", "value": "opaque-capability", "ordinary": "visible"},
            ],
            "alertContacts": [{"name": "opaque-contact", "value": "contact-capability"}],
            TEST_CREDENTIAL_VALUE: "visible-under-redacted-key",
            "ordinaryUrl": "https://example.com/health?region=us-east",
        },
        (TEST_CREDENTIAL_VALUE,),
    )
    sanitized_object = as_dict(sanitized)
    data = as_dict(sanitized_object["data"])
    assert data["url"] == REDACTED
    assert data["pingUrl"] == REDACTED
    assert data["Cookie"] == REDACTED
    assert data["Set-Cookie"] == REDACTED
    assert data["passphrase"] == REDACTED
    assert data["private-key"] == REDACTED
    assert data["ordinary"] == "visible"
    assert sanitized_object["ordinaryUrl"] == "https://example.com/health?region=us-east"
    sanitized_text = json.dumps(sanitized_object)
    assert "path-capability" not in sanitized_text
    assert "opaque-capability" not in sanitized_text
    assert "contact-capability" not in sanitized_text
    assert "must-not-print" not in sanitized_text
    assert TEST_CREDENTIAL_VALUE not in sanitized_text
    assert "visible-under-redacted-key" in sanitized_text

    reserved_credential = "oauth/active+synthetic value%"
    encoded_credential = parse.quote_plus(reserved_credential, safe="")
    encoded_output = redact(
        {
            "nextLink": f"?cursor={encoded_credential}&ordinary=visible",
            "url": f"{API_BASE_URL}/monitors?cursor={encoded_credential}&ordinary=visible",
        },
        (reserved_credential,),
    )
    encoded_output_text = json.dumps(encoded_output)
    assert reserved_credential not in encoded_output_text
    assert encoded_credential not in encoded_output_text
    assert "ordinary=visible" in encoded_output_text


def test_central_output_sanitization_covers_results_and_pagination(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Redact reflected result URLs, heartbeat capabilities, and cursors."""
    credential_type = cast("Callable[..., object]", member("Credential"))
    context_type = cast("Callable[..., object]", member("UptimeRobotContext"))
    plan_type = cast("Callable[..., object]", member("RequestPlan"))
    result_type = cast("Callable[..., object]", member("ApiResult"))
    execute = cast("Callable[[argparse.Namespace, object, object], None]", member("execute_plan"))
    credential = credential_type(environment="TEST_UPTIME_READ", value=TEST_CREDENTIAL_VALUE)
    context = context_type(
        base_url=API_BASE_URL,
        main_credential=None,
        read_credential=credential,
        spec_url=SPEC_URL,
    )
    plan = plan_type(
        body=None,
        confirmation_value=None,
        high_risk=False,
        method="GET",
        operation_id="MonitorsController_list",
        query=(("customField", "environment:production"),),
        url=f"{API_BASE_URL}/monitors",
    )
    path_webhook = f"https://discord.com/api/webhooks/{PATH_WEBHOOK_SEGMENT}"
    ordinary_hooks_url = "https://status.example.test/hooks/status"
    encoded_path_webhook = parse.quote_plus(path_webhook, safe="")

    def fake_send(*_arguments: object, **_keyword_arguments: object) -> object:
        return result_type(
            payload={
                "data": [
                    {
                        "type": "HEARTBEAT",
                        "url": f"https://heartbeat.uptimerobot.com/{HEARTBEAT_CALLBACK_SEGMENT}",
                        "pingUrl": f"https://heartbeat.uptimerobot.com/{HEARTBEAT_CALLBACK_SEGMENT}",
                        "request": {"headers": {"Authorization": TEST_CREDENTIAL_VALUE}},
                        "ordinary": "visible",
                    }
                ],
                "cursor": TEST_CREDENTIAL_VALUE,
                "nextLink": f"?cursor={encoded_path_webhook}&ordinary=visible",
                "ordinaryHooksUrl": ordinary_hooks_url,
            },
            status=200,
            url=f"{API_BASE_URL}/monitors?cursor={encoded_path_webhook}&ordinary=visible",
        )

    monkeypatch.setattr(UPTIMEROBOT, "send_request", fake_send)
    execute(
        argparse.Namespace(send=False, dry_run=False, paginate=True, max_pages=1, confirm=None),
        context,
        plan,
    )
    output_text = capsys.readouterr().out
    assert TEST_CREDENTIAL_VALUE not in output_text
    assert HEARTBEAT_CALLBACK_SEGMENT not in output_text
    assert PATH_WEBHOOK_SEGMENT not in output_text
    output = as_dict(json.loads(output_text))
    assert output["complete"] is False
    assert REDACTED in cast("str", output["nextLink"])
    assert "ordinary=visible" in cast("str", output["nextLink"])
    assert "environment%3Aproduction" in cast("str", output["nextLink"])
    assert ordinary_hooks_url in output_text
    assert "visible" in output_text

    rejected_preview = run_script(
        "request",
        "/monitors",
        "--dry-run",
        "--query",
        f"cursor={TEST_CREDENTIAL_VALUE}",
        "--query",
        "ordinary=visible",
        "--read-token-env",
        "TEST_UPTIME_READ",
        environment=clean_environment(TEST_UPTIME_READ=TEST_CREDENTIAL_VALUE),
    )
    assert rejected_preview.returncode == 1
    assert TEST_CREDENTIAL_VALUE not in rejected_preview.stdout
    assert "configured credential in query value" in rejected_preview.stderr


def test_confirmations_bind_operation_method_target_query_and_canonical_body(tmp_path: Path) -> None:
    """Bind both operation and raw bulk confirmations to every resolved input."""
    spec = tmp_path / "uptimerobot-openapi.json"
    write_openapi_fixture(spec)
    body = {"customFields": {"team": "platform"}, "monitorIds": [2, 1]}
    body_text = json.dumps(body, indent=2)
    canonical_body = json.dumps(body, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    body_hash = hashlib.sha256(canonical_body).hexdigest()
    operation_preview = run_script(
        "request",
        "--spec-file",
        str(spec),
        "--operation-id",
        "BulkMonitorsController_bulkUpdate",
        "--query",
        "scope=production group",
        "--body-json",
        body_text,
    )
    assert operation_preview.returncode == 0, operation_preview.stderr
    operation_confirmation = cast("str", as_dict(json.loads(operation_preview.stdout))["confirmationValue"])
    assert operation_confirmation == (
        f"BulkMonitorsController_bulkUpdate POST /monitors/bulk/update?scope=production+group body-sha256={body_hash}"
    )

    raw_preview = run_script(
        "request",
        "/monitors/bulk/update",
        "--method",
        "POST",
        "--query",
        "scope=production group",
        "--body-json",
        body_text,
    )
    assert raw_preview.returncode == 0, raw_preview.stderr
    raw_confirmation = cast("str", as_dict(json.loads(raw_preview.stdout))["confirmationValue"])
    assert raw_confirmation == (f"POST /monitors/bulk/update?scope=production+group body-sha256={body_hash}")
    assert raw_confirmation != operation_confirmation

    changed_body = run_script(
        "request",
        "/monitors/bulk/update",
        "--method",
        "POST",
        "--query",
        "scope=production group",
        "--body-json",
        '{"customFields":{"team":"security"},"monitorIds":[2,1]}',
    )
    assert changed_body.returncode == 0, changed_body.stderr
    assert as_dict(json.loads(changed_body.stdout))["confirmationValue"] != raw_confirmation

    unbound_confirmation = run_script(
        "request",
        "--spec-file",
        str(spec),
        "--operation-id",
        "BulkMonitorsController_bulkUpdate",
        "--query",
        "scope=production group",
        "--body-json",
        body_text,
        "--send",
        "--confirm",
        "BulkMonitorsController_bulkUpdate",
        "--main-token-env",
        "TEST_UPTIME_MAIN",
        environment=clean_environment(TEST_UPTIME_MAIN=TEST_CREDENTIAL_VALUE),
    )
    assert unbound_confirmation.returncode == 1
    assert "requires --confirm" in unbound_confirmation.stderr
    assert TEST_CREDENTIAL_VALUE not in unbound_confirmation.stderr


def test_array_query_serialization_and_pagination_preserve_pairs(tmp_path: Path) -> None:
    """Allow OpenAPI arrays, reject scalar repeats, and retain raw/paginated pairs."""
    spec = tmp_path / "uptimerobot-openapi.json"
    write_openapi_fixture(spec)
    array_preview = run_script(
        "request",
        "--spec-file",
        str(spec),
        "--operation-id",
        "MonitorsController_list",
        "--query",
        "customField=environment:production",
        "--query",
        "customField=team:platform",
        "--dry-run",
    )
    assert array_preview.returncode == 0, array_preview.stderr
    array_url = cast("str", as_dict(as_dict(json.loads(array_preview.stdout))["request"])["url"])
    assert array_url.endswith("?customField=environment%3Aproduction&customField=team%3Aplatform")

    scalar_duplicate = run_script(
        "request",
        "--spec-file",
        str(spec),
        "--operation-id",
        "MonitorsController_list",
        "--query",
        "limit=10",
        "--query",
        "limit=20",
        "--dry-run",
    )
    assert scalar_duplicate.returncode == 1
    assert "Duplicate query name: limit" in scalar_duplicate.stderr

    raw_preview = run_script(
        "request",
        "/monitors",
        "--query",
        "filter=first",
        "--query",
        "filter=second",
        "--dry-run",
    )
    assert raw_preview.returncode == 0, raw_preview.stderr
    raw_url = cast("str", as_dict(as_dict(json.loads(raw_preview.stdout))["request"])["url"])
    assert raw_url.endswith("?filter=first&filter=second")

    credential_metadata_query = run_script(
        "request",
        "/monitors",
        "--query",
        "credentialEnvironment=visible",
        "--dry-run",
    )
    assert credential_metadata_query.returncode == 1
    assert "credential-like query parameter" in credential_metadata_query.stderr

    parse_yaml = cast("Callable[[str], list[object]]", member("parse_yaml_operations"))
    yaml_operations = parse_yaml(
        """openapi: 3.0.0
paths:
  /monitors:
    get:
      operationId: MonitorsController_list
      parameters:
        - name: customField
          in: query
          schema:
            type: array
            items:
              type: string
        - name: limit
          in: query
          schema:
            type: integer
      summary: List monitors
      tags:
        - Monitors
components:
  schemas: {}
"""
    )
    assert vars(yaml_operations[0])["array_query_parameters"] == ("customField",)

    next_url = cast("Callable[[str, str, str], str]", member("validated_next_url"))
    current = f"{API_BASE_URL}/monitors?customField=environment%3Aproduction&customField=team%3Aplatform&cursor=old"
    merged = next_url(API_BASE_URL, current, "?cursor=new")
    assert parse.parse_qsl(parse.urlsplit(merged).query) == [
        ("customField", "environment:production"),
        ("customField", "team:platform"),
        ("cursor", "new"),
    ]


@pytest.mark.parametrize("retry_after", ["garbage", "NaN", "Infinity", "-Infinity", "-1"])
def test_invalid_retry_after_uses_bounded_fallback_without_traceback(retry_after: str) -> None:
    """Use capped exponential fallback for malformed, non-finite, or negative values."""
    retry_delay = cast("Callable[[error.HTTPError, int], float]", member("retry_delay"))
    failure, _stream = http_failure(429, retry_after=retry_after)
    try:
        assert retry_delay(failure, 3) == EXPECTED_RETRY_FALLBACK
    finally:
        failure.close()


@pytest.mark.parametrize("timeout", ["NaN", "Infinity", "-Infinity"])
def test_non_finite_timeout_is_a_safe_subprocess_error(timeout: str) -> None:
    """Reject non-finite timeout values before I/O and without a traceback."""
    result = run_script("context", f"--timeout={timeout}")
    assert result.returncode == 1
    assert "--timeout must be greater than zero and at most 300" in result.stderr
    assert "Traceback" not in result.stderr


@pytest.mark.parametrize("secret", [RESERVED_READ_CREDENTIAL, RESERVED_MAIN_CREDENTIAL])
def test_all_credential_encodings_are_rejected_in_paths_queries_and_bodies(secret: str) -> None:
    """Reject raw, percent, form, and repeatedly encoded configured credentials."""
    reject = cast(
        "Callable[[str, JsonValue, tuple[str, ...]], None]",
        member("reject_credential_reuse"),
    )
    helper_error = cast("type[Exception]", member("UptimeRobotCliError"))
    parse_query = cast("Callable[..., tuple[tuple[str, str], ...]]", member("parse_query_pairs"))
    for variant in encoded_variants(secret):
        candidates: tuple[tuple[str, JsonValue], ...] = (
            (f"{API_BASE_URL}/monitors/{variant}", None),
            (f"{API_BASE_URL}/monitors?cursor={variant}&ordinary=visible", None),
            (f"{API_BASE_URL}/monitors", {"ordinary": "visible", "value": variant}),
            (f"{API_BASE_URL}/monitors", {variant: "visible"}),
        )
        for url, body in candidates:
            with pytest.raises(helper_error, match="Authorization header") as caught:
                reject(url, body, (RESERVED_READ_CREDENTIAL, RESERVED_MAIN_CREDENTIAL))
            assert secret not in str(caught.value)
            assert variant not in str(caught.value)
        with pytest.raises(helper_error) as query_error:
            _ = parse_query(
                [f"{variant}=visible", f"{variant}=duplicate"],
                allow_repeated=True,
                secrets=(RESERVED_READ_CREDENTIAL, RESERVED_MAIN_CREDENTIAL),
            )
        assert secret not in str(query_error.value)
        assert variant not in str(query_error.value)


@pytest.mark.parametrize(
    ("location", "secret"),
    [
        ("path", RESERVED_MAIN_CREDENTIAL),
        ("query", RESERVED_MAIN_CREDENTIAL),
        ("body", RESERVED_READ_CREDENTIAL),
    ],
)
def test_cli_rejects_either_configured_credential_without_reflection(location: str, secret: str) -> None:
    """Reject unselected credentials too, without leaking any encoded form."""
    variant = parse.quote_plus(parse.quote_plus(secret, safe=""), safe="")
    arguments = ["request", "/monitors", "--dry-run"]
    if location == "path":
        arguments[1] = f"/monitors/{variant}"
    elif location == "query":
        arguments.extend(("--query", f"cursor={variant}", "--query", "ordinary=visible"))
    else:
        arguments.extend(("--method", "POST", "--body-json", json.dumps({"value": variant})))
    arguments.extend(
        (
            "--read-token-env",
            "TEST_UPTIME_READ",
            "--main-token-env",
            "TEST_UPTIME_MAIN",
        )
    )
    result = run_script(
        *arguments,
        environment=clean_environment(
            TEST_UPTIME_MAIN=RESERVED_MAIN_CREDENTIAL,
            TEST_UPTIME_READ=RESERVED_READ_CREDENTIAL,
        ),
    )
    output = f"{result.stdout}\n{result.stderr}"
    assert result.returncode == 1
    assert "configured" in result.stderr.casefold()
    assert "credential" in result.stderr.casefold()
    assert "Traceback" not in result.stderr
    for configured_secret in (RESERVED_READ_CREDENTIAL, RESERVED_MAIN_CREDENTIAL):
        for configured_variant in encoded_variants(configured_secret):
            assert configured_variant not in output


def test_preview_and_transport_recheck_both_context_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """Recheck bypassed plans immediately before preview and network transport."""
    write_preview = cast("Callable[..., None]", member("write_preview"))
    send = cast("Callable[..., object]", member("send_request"))
    request_secrets = cast("Callable[[object], tuple[str, ...]]", member("request_secrets"))
    helper_error = cast("type[Exception]", member("UptimeRobotCliError"))
    context = uptime_context(read_value=RESERVED_READ_CREDENTIAL, main_value=RESERVED_MAIN_CREDENTIAL)
    secrets = request_secrets(context)
    plan = request_plan()
    encoded_main = parse.quote_plus(parse.quote_plus(RESERVED_MAIN_CREDENTIAL, safe=""), safe="")
    unsafe_url = f"{API_BASE_URL}/monitors/{encoded_main}"

    with pytest.raises(helper_error, match="Authorization header"):
        write_preview(context, plan, unsafe_url, secrets)

    opener = install_opener(monkeypatch, [FakeResponse(b"{}")])
    read_credential = credential(RESERVED_READ_CREDENTIAL)
    retry_arguments = request_arguments(retries=10)
    with pytest.raises(helper_error, match="Authorization header"):
        _ = send(
            plan,
            unsafe_url,
            read_credential,
            retry_arguments,
            secrets=secrets,
        )
    assert opener.requests == []

    encoded_read = parse.quote(parse.quote(RESERVED_READ_CREDENTIAL, safe=""), safe="")
    write_plan = request_plan("POST", body={"postValueData": encoded_read})
    main_credential = credential(RESERVED_MAIN_CREDENTIAL)
    write_arguments = request_arguments(retries=10)
    with pytest.raises(helper_error, match="Authorization header"):
        _ = send(
            write_plan,
            f"{API_BASE_URL}/monitors",
            main_credential,
            write_arguments,
            secrets=secrets,
        )
    assert opener.requests == []


def test_previews_and_confirmations_redact_path_webhook_capabilities(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Redact path-token webhooks while retaining ordinary preview fields."""
    plan_type = cast("Callable[..., object]", member("RequestPlan"))
    confirmation = cast("Callable[[str, str, JsonValue, str | None], str]", member("confirmation_value"))
    encode_url = cast("Callable[..., str]", member("encode_url"))
    execute = cast("Callable[[argparse.Namespace, object, object], None]", member("execute_plan"))
    webhook = f"https://discord.com/api/webhooks/{PATH_WEBHOOK_SEGMENT}"
    query = (("callback", webhook), ("ordinary", "visible"))
    url = f"{API_BASE_URL}/monitors/bulk/update"
    body: JsonValue = {
        "monitorUrl": "https://status.example.test/hooks/status",
        "ordinary": "visible",
        "webhookURL": webhook,
    }
    encoded_url = encode_url(url, query)
    plan = plan_type(
        body=body,
        confirmation_value=confirmation("POST", encoded_url, body, None),
        high_risk=True,
        method="POST",
        operation_id=None,
        query=query,
        url=url,
    )
    execute(
        argparse.Namespace(send=False, dry_run=False, paginate=False, confirm=None),
        uptime_context(read_value=None, main_value=None),
        plan,
    )
    output_text = capsys.readouterr().out
    output = as_dict(json.loads(output_text))
    preview_request = as_dict(output["request"])
    preview_body = as_dict(preview_request["body"])
    assert PATH_WEBHOOK_SEGMENT not in output_text
    assert output["confirmationValue"] == REDACTED
    assert preview_body["webhookURL"] == REDACTED
    assert preview_body["monitorUrl"] == "https://status.example.test/hooks/status"
    assert preview_body["ordinary"] == "visible"
    assert "ordinary=visible" in cast("str", preview_request["url"])


@pytest.mark.parametrize(
    ("content_length", "body", "expected_error", "expected_reads"),
    [
        ("4", b"1234", None, [5]),
        ("5", b"12345", "4-byte safety limit", []),
        (None, b"12345", "4-byte safety limit", [5]),
        ("malformed", b"12345", "4-byte safety limit", [5]),
        ("1", b"12345", "4-byte safety limit", [5]),
        ("-1", b"12345", "4-byte safety limit", [5]),
    ],
)
def test_bounded_stream_uses_content_length_only_for_early_rejection(
    content_length: str | None,
    body: bytes,
    expected_error: str | None,
    expected_reads: list[int],
) -> None:
    """Enforce actual bytes with one limit-plus-one read despite untrusted headers."""
    read_bounded = cast("Callable[..., bytes]", member("read_bounded_stream"))
    helper_error = cast("type[Exception]", member("UptimeRobotCliError"))
    stream = RecordingStream(body)
    if expected_error is not None:
        with pytest.raises(helper_error, match=expected_error):
            _ = read_bounded(stream, max_bytes=4, label="fixture", content_length=content_length)
    else:
        assert read_bounded(stream, max_bytes=4, label="fixture", content_length=content_length) == body
    assert stream.read_sizes == expected_reads


def test_local_and_remote_openapi_reads_are_actual_byte_bounded_and_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Close exact and one-over local and remote OpenAPI streams."""
    load_local = cast("Callable[[Path], list[object]]", member("load_local_operations"))
    load_remote = cast("Callable[[argparse.Namespace, object], list[object]]", member("load_remote_operations"))
    helper_error = cast("type[Exception]", member("UptimeRobotCliError"))
    document = openapi_document()
    limit = len(document)
    monkeypatch.setattr(UPTIMEROBOT, "MAX_OPENAPI_BYTES", limit)

    local_exact = RecordingStream(document)
    operations = load_local(cast("Path", FakeSpecFile(local_exact)))
    assert len(operations) == 1
    assert local_exact.closed
    assert local_exact.read_sizes == [limit + 1]

    local_over = RecordingStream(document + b" ")
    local_over_file = cast("Path", FakeSpecFile(local_over))
    with pytest.raises(helper_error, match=f"{limit}-byte safety limit"):
        _ = load_local(local_over_file)
    assert local_over.closed
    assert local_over.read_sizes == [limit + 1]

    remote_exact = FakeResponse(document, content_length="malformed", content_type="application/json")
    _ = install_opener(monkeypatch, [remote_exact])
    operations = load_remote(argparse.Namespace(timeout=1.0, retries=0), uptime_context())
    assert len(operations) == 1
    assert remote_exact.closed
    assert remote_exact.read_sizes == [limit + 1]

    remote_over = FakeResponse(document + b" ", content_length="1", content_type="application/json")
    _ = install_opener(monkeypatch, [remote_over])
    remote_arguments = argparse.Namespace(timeout=1.0, retries=0)
    context = uptime_context()
    with pytest.raises(helper_error, match=f"{limit}-byte safety limit"):
        _ = load_remote(remote_arguments, context)
    assert remote_over.closed
    assert remote_over.read_sizes == [limit + 1]


def test_remote_openapi_minimal_namespace_consumes_and_closes_http_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Default omitted retry controls before consuming a direct-call HTTP error."""
    load = cast("Callable[[argparse.Namespace, object], list[object]]", member("load_operations"))
    helper_error = cast("type[Exception]", member("UptimeRobotCliError"))
    failure, stream = http_failure(503, b"temporary")
    opener = install_opener(monkeypatch, [failure])
    arguments = argparse.Namespace(spec_file=None, timeout=1.0)
    context = uptime_context()
    with pytest.raises(helper_error, match="OpenAPI request failed with HTTP 503"):
        _ = load(arguments, context)
    assert len(opener.requests) == 1
    assert stream.closed
    assert stream.read_sizes == [cast("int", member("MAX_ERROR_RESPONSE_BYTES")) + 1]


def test_success_and_error_api_reads_are_actual_byte_bounded_and_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Enforce actual success and error bytes and close every response stream."""
    send = cast("Callable[..., object]", member("send_request"))
    helper_error = cast("type[Exception]", member("UptimeRobotCliError"))
    success_body = b'{"ok":true}'
    success_limit = len(success_body)
    monkeypatch.setattr(UPTIMEROBOT, "MAX_API_RESPONSE_BYTES", success_limit)

    exact = FakeResponse(success_body, content_length=str(success_limit))
    _ = install_opener(monkeypatch, [exact])
    result = send(request_plan(), f"{API_BASE_URL}/monitors", credential(), request_arguments())
    assert vars(result)["response_bytes"] == success_limit
    assert exact.closed
    assert exact.read_sizes == [success_limit + 1]

    over = FakeResponse(success_body + b" ", content_length="1")
    _ = install_opener(monkeypatch, [over])
    over_plan = request_plan()
    over_credential = credential()
    over_arguments = request_arguments()
    with pytest.raises(helper_error, match=f"{success_limit}-byte safety limit"):
        _ = send(over_plan, f"{API_BASE_URL}/monitors", over_credential, over_arguments)
    assert over.closed
    assert over.read_sizes == [success_limit + 1]

    monkeypatch.setattr(UPTIMEROBOT, "MAX_ERROR_RESPONSE_BYTES", 4)
    exact_failure, exact_error_stream = http_failure(400, b"1234", content_length="malformed")
    _ = install_opener(monkeypatch, [exact_failure])
    exact_failure_plan = request_plan()
    exact_failure_credential = credential()
    exact_failure_arguments = request_arguments()
    with pytest.raises(helper_error, match="HTTP 400"):
        _ = send(
            exact_failure_plan,
            f"{API_BASE_URL}/monitors",
            exact_failure_credential,
            exact_failure_arguments,
        )
    assert exact_error_stream.closed
    assert exact_error_stream.read_sizes == [5]

    oversized_failure, oversized_error_stream = http_failure(400, b"12345", content_length="1")
    _ = install_opener(monkeypatch, [oversized_failure])
    oversized_failure_plan = request_plan()
    oversized_failure_credential = credential()
    oversized_failure_arguments = request_arguments()
    with pytest.raises(helper_error, match="4-byte safety limit"):
        _ = send(
            oversized_failure_plan,
            f"{API_BASE_URL}/monitors",
            oversized_failure_credential,
            oversized_failure_arguments,
        )
    assert oversized_error_stream.closed
    assert oversized_error_stream.read_sizes == [5]


@pytest.mark.parametrize("transport_kind", ["url-error", "timeout"])
def test_get_transport_failures_consume_exact_retry_budget(
    monkeypatch: pytest.MonkeyPatch,
    transport_kind: str,
) -> None:
    """Retry GET URL and direct timeout losses within the configured budget."""
    send = cast("Callable[..., object]", member("send_request"))
    failures: list[BaseException]
    if transport_kind == "url-error":
        failures = [error.URLError("temporary one"), error.URLError("temporary two")]
    else:
        failures = [TimeoutError("temporary one"), TimeoutError("temporary two")]
    success = FakeResponse(b'{"ok":true}')
    opener = install_opener(monkeypatch, [*failures, success])
    delays: list[float] = []
    monkeypatch.setattr(UPTIMEROBOT.time, "sleep", delays.append)
    result = send(
        request_plan(),
        f"{API_BASE_URL}/monitors",
        credential(),
        request_arguments(retries=2),
    )
    assert vars(result)["status"] == HTTP_OK
    assert len(opener.requests) == EXPECTED_GET_ATTEMPT_COUNT
    assert delays == [1.0, 2.0]
    assert success.closed


@pytest.mark.parametrize("status", TRANSIENT_STATUSES)
@pytest.mark.parametrize("transport_kind", ["response", "http-error"])
def test_get_retries_every_retryable_status_shape(
    monkeypatch: pytest.MonkeyPatch,
    status: int,
    transport_kind: str,
) -> None:
    """Retry all configured transient GET statuses from both urllib shapes."""
    send = cast("Callable[..., object]", member("send_request"))
    failure_stream: RecordingStream | None = None
    direct_response: FakeResponse | None = None
    first_outcome: TransportOutcome
    if transport_kind == "http-error":
        first_outcome, failure_stream = http_failure(status, b"temporary", retry_after="0")
    else:
        direct_response = FakeResponse(b"temporary", retry_after="0", status=status)
        first_outcome = direct_response
    success = FakeResponse(b'{"ok":true}')
    opener = install_opener(monkeypatch, [first_outcome, success])
    delays: list[float] = []
    monkeypatch.setattr(UPTIMEROBOT.time, "sleep", delays.append)
    result = send(
        request_plan(),
        f"{API_BASE_URL}/monitors",
        credential(),
        request_arguments(retries=1),
    )
    assert vars(result)["status"] == HTTP_OK
    assert len(opener.requests) == EXPECTED_RETRIED_REQUEST_COUNT
    assert delays == [0.0]
    assert success.closed
    assert failure_stream is None or failure_stream.closed
    assert direct_response is None or direct_response.closed


@pytest.mark.parametrize("method", WRITE_METHODS)
@pytest.mark.parametrize("status", INDETERMINATE_STATUSES)
@pytest.mark.parametrize("transport_kind", ["response", "http-error"])
def test_transient_write_statuses_are_one_shot_and_indeterminate(
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    status: int,
    transport_kind: str,
) -> None:
    """Classify every transient write status as a one-shot ambiguous mutation."""
    send = cast("Callable[..., object]", member("send_request"))
    helper_error = cast("type[Exception]", member("UptimeRobotCliError"))
    failure_stream: RecordingStream | None = None
    direct_response: FakeResponse | None = None
    outcome: TransportOutcome
    if transport_kind == "http-error":
        outcome, failure_stream = http_failure(status, b"temporary", retry_after="0")
    else:
        direct_response = FakeResponse(b"temporary", retry_after="0", status=status)
        outcome = direct_response
    opener = install_opener(monkeypatch, [outcome])
    plan = request_plan(method, body={"ordinary": "visible"})
    request_credential = credential()
    arguments = request_arguments(retries=10)
    with pytest.raises(helper_error) as caught:
        _ = send(
            plan,
            f"{API_BASE_URL}/monitors",
            request_credential,
            arguments,
        )
    message = str(caught.value)
    assert f"HTTP {status}" in message
    assert f"The {method} mutation may have succeeded" in message
    assert "outcome is indeterminate" in message
    assert "Re-read the exact UptimeRobot target" in message
    assert len(opener.requests) == 1
    assert failure_stream is None or failure_stream.closed
    assert direct_response is None or direct_response.closed


@pytest.mark.parametrize("method", WRITE_METHODS)
@pytest.mark.parametrize("status", DEFINITIVE_CLIENT_STATUSES)
@pytest.mark.parametrize("transport_kind", ["response", "http-error"])
def test_write_client_errors_are_definitive_and_never_retried(
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    status: int,
    transport_kind: str,
) -> None:
    """Keep all tested 4xx write outcomes definitive, including HTTP 429."""
    send = cast("Callable[..., object]", member("send_request"))
    helper_error = cast("type[Exception]", member("UptimeRobotCliError"))
    failure_stream: RecordingStream | None = None
    direct_response: FakeResponse | None = None
    outcome: TransportOutcome
    if transport_kind == "http-error":
        outcome, failure_stream = http_failure(status, b"client error", retry_after="0")
    else:
        direct_response = FakeResponse(b"client error", retry_after="0", status=status)
        outcome = direct_response
    opener = install_opener(monkeypatch, [outcome])
    plan = request_plan(method, body={"ordinary": "visible"})
    request_credential = credential()
    arguments = request_arguments(retries=10)
    with pytest.raises(helper_error) as caught:
        _ = send(
            plan,
            f"{API_BASE_URL}/monitors",
            request_credential,
            arguments,
        )
    message = str(caught.value)
    assert f"HTTP {status}" in message
    assert "may have succeeded" not in message
    assert "indeterminate" not in message
    assert len(opener.requests) == 1
    assert failure_stream is None or failure_stream.closed
    assert direct_response is None or direct_response.closed


@pytest.mark.parametrize("method", WRITE_METHODS)
@pytest.mark.parametrize("transport_kind", ["url-error", "timeout"])
def test_write_transport_losses_are_one_shot_bounded_redacted_and_indeterminate(
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    transport_kind: str,
) -> None:
    """Bound and redact write transport losses while requiring an exact reread."""
    send = cast("Callable[..., object]", member("send_request"))
    safe_reason = cast("Callable[[object, tuple[str, ...]], str]", member("safe_transport_reason"))
    helper_error = cast("type[Exception]", member("UptimeRobotCliError"))
    webhook = f"https://alerts.example.test/hooks/{PATH_WEBHOOK_SEGMENT}"
    encoded_secret = parse.quote_plus(RESERVED_READ_CREDENTIAL, safe="")
    reason = f"transport {encoded_secret} {webhook} " + ("x" * 5000)
    outcome: BaseException = error.URLError(reason) if transport_kind == "url-error" else TimeoutError(reason)
    opener = install_opener(monkeypatch, [outcome])
    plan = request_plan(method, body={"ordinary": "visible"})
    main_credential = credential(RESERVED_MAIN_CREDENTIAL)
    arguments = request_arguments(retries=10)
    with pytest.raises(helper_error) as caught:
        _ = send(
            plan,
            f"{API_BASE_URL}/monitors",
            main_credential,
            arguments,
            secrets=(RESERVED_READ_CREDENTIAL, RESERVED_MAIN_CREDENTIAL),
        )
    message = str(caught.value)
    assert RESERVED_READ_CREDENTIAL not in message
    assert encoded_secret not in message
    assert PATH_WEBHOOK_SEGMENT in message
    assert f"The {method} mutation may have succeeded" in message
    assert "Re-read the exact UptimeRobot target" in message
    assert len(opener.requests) == 1
    max_reason = cast("int", member("MAX_TRANSPORT_ERROR_TEXT"))
    assert len(safe_reason("x" * (max_reason + 100), ())) == max_reason
    sanitized_reason = safe_reason(reason, (RESERVED_READ_CREDENTIAL,))
    assert RESERVED_READ_CREDENTIAL not in sanitized_reason
    assert PATH_WEBHOOK_SEGMENT in sanitized_reason


@pytest.mark.parametrize(
    ("retry_after", "expected"),
    [("0", 0.0), ("59", 59.0), ("59.5", 1.0), ("999", 60.0), ("1e309", 1.0)],
)
def test_retry_after_controls_are_finite_and_capped(retry_after: str, expected: float) -> None:
    """Accept integer delta-seconds, cap large values, and reject extensions."""
    retry_delay = cast("Callable[[str | None, int], float]", member("retry_delay_header"))
    assert retry_delay(retry_after, 0) == expected


def test_cumulative_pagination_limit_is_checked_before_retaining_page(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Allow an exact cumulative limit and reject overflow before page retention."""
    result_type = cast("Callable[..., object]", member("ApiResult"))
    paginate = cast("Callable[..., None]", member("write_paginated_results"))
    result_payload = cast("Callable[[object], dict[str, JsonValue]]", member("result_payload"))
    helper_error = cast("type[Exception]", member("UptimeRobotCliError"))
    context = uptime_context()
    plan = request_plan()
    arguments = argparse.Namespace(max_pages=3, retries=0, timeout=1.0)
    monkeypatch.setattr(UPTIMEROBOT, "MAX_PAGINATED_RESPONSE_BYTES", 10)

    exact_results = iter(
        (
            result_type(payload={"data": [1], "nextLink": "?cursor=2"}, response_bytes=5, status=200, url="one"),
            result_type(payload={"data": [2], "nextLink": None}, response_bytes=5, status=200, url="two"),
        )
    )

    def exact_send(*_arguments: object, **_keyword_arguments: object) -> object:
        return next(exact_results)

    monkeypatch.setattr(UPTIMEROBOT, "send_request", exact_send)
    paginate(arguments, context, plan, credential(), f"{API_BASE_URL}/monitors")
    exact_output = as_dict(json.loads(capsys.readouterr().out))
    assert exact_output["complete"] is True
    assert exact_output["pageCount"] == EXPECTED_PAGE_COUNT

    overflow_results = iter(
        (
            result_type(payload={"data": [1], "nextLink": "?cursor=2"}, response_bytes=5, status=200, url="one"),
            result_type(payload={"data": [2], "nextLink": None}, response_bytes=6, status=200, url="two"),
        )
    )
    retained: list[str] = []

    def overflow_send(*_arguments: object, **_keyword_arguments: object) -> object:
        return next(overflow_results)

    def tracking_payload(result: object) -> dict[str, JsonValue]:
        retained.append(cast("str", vars(result)["url"]))
        return result_payload(result)

    monkeypatch.setattr(UPTIMEROBOT, "send_request", overflow_send)
    monkeypatch.setattr(UPTIMEROBOT, "result_payload", tracking_payload)
    pagination_credential = credential()
    with pytest.raises(helper_error, match="10-byte cumulative safety limit"):
        paginate(arguments, context, plan, pagination_credential, f"{API_BASE_URL}/monitors")
    assert retained == ["one"]
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize(
    "payload",
    [[], {}, {"nextLink": ""}, {"nextLink": []}, {"nextLink": 0}],
)
def test_pagination_rejects_malformed_next_link_shapes(payload: JsonValue) -> None:
    """Do not silently treat missing or malformed cursor metadata as complete."""
    next_link = cast("Callable[[JsonValue], str | None]", member("next_link"))
    helper_error = cast("type[Exception]", member("UptimeRobotCliError"))
    with pytest.raises(helper_error, match="nextLink"):
        _ = next_link(payload)


def test_pagination_rejects_malformed_cycles_and_encoded_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fail closed on malformed, repeated, and credential-bearing next links."""
    next_url = cast("Callable[[str, str, str], str]", member("validated_next_url"))
    result_type = cast("Callable[..., object]", member("ApiResult"))
    paginate = cast("Callable[..., None]", member("write_paginated_results"))
    helper_error = cast("type[Exception]", member("UptimeRobotCliError"))
    with pytest.raises(helper_error, match="malformed"):
        _ = next_url(
            API_BASE_URL,
            f"{API_BASE_URL}/monitors",
            "https://api.uptimerobot.com:not-a-port/v3/monitors",
        )

    context = uptime_context(read_value=RESERVED_READ_CREDENTIAL)
    plan_type = cast("Callable[..., object]", member("RequestPlan"))
    repeated_plan = plan_type(
        body=None,
        confirmation_value=None,
        high_risk=False,
        method="GET",
        operation_id=None,
        query=(("limit", "1"),),
        url=f"{API_BASE_URL}/monitors",
    )
    repeated_result = result_type(
        payload={"data": [], "nextLink": "?limit=1"},
        response_bytes=1,
        status=200,
        url=f"{API_BASE_URL}/monitors?limit=1",
    )

    def repeated_send(*_arguments: object, **_keyword_arguments: object) -> object:
        return repeated_result

    monkeypatch.setattr(UPTIMEROBOT, "send_request", repeated_send)
    pagination_arguments = argparse.Namespace(max_pages=3, retries=0, timeout=1.0)
    read_credential = credential(RESERVED_READ_CREDENTIAL)
    with pytest.raises(helper_error, match="repeated nextLink"):
        paginate(
            pagination_arguments,
            context,
            repeated_plan,
            read_credential,
            f"{API_BASE_URL}/monitors?limit=1",
        )

    encoded_secret = parse.quote_plus(parse.quote_plus(RESERVED_READ_CREDENTIAL, safe=""), safe="")
    secret_result = result_type(
        payload={"data": [], "nextLink": f"?cursor={encoded_secret}"},
        response_bytes=1,
        status=200,
        url=f"{API_BASE_URL}/monitors",
    )

    def secret_send(*_arguments: object, **_keyword_arguments: object) -> object:
        return secret_result

    monkeypatch.setattr(UPTIMEROBOT, "send_request", secret_send)
    secret_arguments = argparse.Namespace(max_pages=3, retries=0, timeout=1.0)
    secret_plan = request_plan()
    secret_credential = credential(RESERVED_READ_CREDENTIAL)
    with pytest.raises(helper_error, match="Authorization header") as caught:
        paginate(
            secret_arguments,
            context,
            secret_plan,
            secret_credential,
            f"{API_BASE_URL}/monitors",
        )
    assert RESERVED_READ_CREDENTIAL not in str(caught.value)
    assert encoded_secret not in str(caught.value)


def encoded_key_variants(key: str) -> tuple[str, ...]:
    """Encode the first key character through raw, percent, form, and mixed rounds."""
    single = f"%{ord(key[0]):02X}{key[1:]}"
    double = parse.quote(single, safe="")
    triple = parse.quote_plus(double, safe="")
    mixed = parse.quote(parse.quote_plus(single, safe=""), safe="")
    return tuple(dict.fromkeys((key, single, double, triple, mixed)))


@pytest.mark.parametrize(
    "key",
    ["apiKey", "Set-Cookie", "privateKey", "customHTTPHeaders", "accessToken", "webhookURL"],
)
def test_repeatedly_decoded_sensitive_keys_are_rejected_and_redacted(key: str) -> None:
    """Classify encoded key names consistently in query, URL, JSON, and diagnostics."""
    is_sensitive = cast("Callable[[str], bool]", member("is_sensitive_key"))
    parse_query = cast("Callable[..., tuple[tuple[str, str], ...]]", member("parse_query_pairs"))
    redact = cast("Callable[[JsonValue, tuple[str, ...]], JsonValue]", member("redact_json"))
    safe_reason = cast("Callable[[object, tuple[str, ...]], str]", member("safe_transport_reason"))
    helper_error = cast("type[Exception]", member("UptimeRobotCliError"))
    for variant in encoded_key_variants(key):
        assert is_sensitive(variant)
        with pytest.raises(helper_error) as caught:
            _ = parse_query([f"{variant}=must-not-print"])
        assert variant not in str(caught.value)

        sanitized = as_dict(redact({variant: "must-not-print", "ordinary": "visible"}, ()))
        assert sanitized[variant] == REDACTED
        assert sanitized["ordinary"] == "visible"

        encoded_name = parse.quote(variant, safe="")
        diagnostic = safe_reason(
            f"failed https://example.test/path?{encoded_name}=must-not-print&ordinary=visible",
            (),
        )
        assert "must-not-print" not in diagnostic
        assert "ordinary=visible" in diagnostic


@pytest.mark.parametrize(
    "key",
    ["tokenizationMode", "tokenizerVersion", "cookieCount", "secretaryName", "privateKeyboard", "postValueCount"],
)
def test_ordinary_semantic_keys_and_generic_hook_urls_remain_visible(key: str) -> None:
    """Avoid substring and ordinary-host webhook false positives."""
    is_sensitive = cast("Callable[[str], bool]", member("is_sensitive_key"))
    redact = cast("Callable[[JsonValue, tuple[str, ...]], JsonValue]", member("redact_json"))
    ordinary_url = "https://status.example.test/hooks/status"
    assert not is_sensitive(key)
    sanitized = as_dict(
        redact(
            {
                key: "visible",
                "monitorUrl": ordinary_url,
                "webhookURL": ordinary_url,
                "knownProvider": "https://discord.com/api/webhooks/private-capability",
            },
            (),
        )
    )
    assert sanitized[key] == "visible"
    assert sanitized["monitorUrl"] == ordinary_url
    assert sanitized["webhookURL"] == REDACTED
    assert sanitized["knownProvider"] == REDACTED


def test_active_credential_replacement_is_boundary_aware_and_requires_valid_length(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Replace active values at boundaries without treating short or embedded text as a secret."""
    redact = cast("Callable[[JsonValue, tuple[str, ...]], JsonValue]", member("redact_json"))
    resolve = cast("Callable[[list[str], tuple[str, ...]], object]", member("resolve_credential"))
    helper_error = cast("type[Exception]", member("UptimeRobotCliError"))
    active = "active-credential"
    reserved = "reserved/credential+value"
    encoded_reserved = parse.quote_plus(reserved, safe="")
    sanitized = as_dict(
        redact(
            {
                "exact": active,
                "encoded": encoded_reserved,
                "encodedJoined": f"prefix{encoded_reserved}",
                "sentence": f"before {active} after",
                "leftJoined": f"prefix{active}",
                "rightJoined": f"{active}suffix",
                "shortText": "a appears ordinarily",
            },
            (active, reserved, "a"),
        )
    )
    assert sanitized["exact"] == REDACTED
    assert sanitized["encoded"] == REDACTED
    assert sanitized["encodedJoined"] == f"prefix{encoded_reserved}"
    assert sanitized["sentence"] == f"before {REDACTED} after"
    assert sanitized["leftJoined"] == f"prefix{active}"
    assert sanitized["rightJoined"] == f"{active}suffix"
    assert sanitized["shortText"] == "a appears ordinarily"

    monkeypatch.setenv("TEST_SHORT_UPTIME_CREDENTIAL", "short")
    with pytest.raises(helper_error, match="at least 8 characters"):
        _ = resolve(["TEST_SHORT_UPTIME_CREDENTIAL"], ())
    monkeypatch.setenv("TEST_SHORT_UPTIME_CREDENTIAL", "12345678")
    assert vars(resolve(["TEST_SHORT_UPTIME_CREDENTIAL"], ()))["value"] == "12345678"


def test_operations_output_uses_configured_secret_sanitization(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Route OpenAPI operation output through the configured-secret sanitizer."""
    operation_type = cast("Callable[..., object]", member("OpenApiOperation"))
    handle = cast("Callable[[argparse.Namespace, object], int]", member("handle_operations"))
    reflected = parse.quote_plus(TEST_CREDENTIAL_VALUE, safe="")
    operation = operation_type(
        array_query_parameters=(),
        deprecated=False,
        method="GET",
        operation_id="MonitorsController_list",
        path=f"/monitors/{reflected}",
        summary=f"ordinary before {TEST_CREDENTIAL_VALUE} after",
        tags=("Monitors",),
    )

    def fake_load_operations(*_arguments: object) -> list[object]:
        return [operation]

    monkeypatch.setattr(UPTIMEROBOT, "load_operations", fake_load_operations)
    arguments = argparse.Namespace(
        include_deprecated=False,
        operation_method=None,
        search=None,
        tag=None,
    )
    assert handle(arguments, uptime_context()) == 0
    output = capsys.readouterr().out
    assert TEST_CREDENTIAL_VALUE not in output
    assert reflected not in output
    assert "ordinary before" in output
    assert "after" in output


@pytest.mark.parametrize(
    "unsafe_url",
    [
        "https://user@api.uptimerobot.com/v3/monitors",
        "https://api.uptimerobot.com:443/v3/monitors",
        "https://api.uptimerobot.com/v3/monitors#fragment",
        "https://example.test/v3/monitors",
        "https://api.uptimerobot.com/v2/monitors",
        "https://api.uptimerobot.com/v3/monitors/%2e%2e/incidents",
        "https://api.uptimerobot.com/v3/monitors/%252e%252e/incidents",
        "https://api.uptimerobot.com/v3/monitors/%25252e%25252e/incidents",
        "https://api.uptimerobot.com/v3/monitors/%2525252e%2525252e/incidents",
        "https://api.uptimerobot.com/v3/monitors%2Fother",
        "https://api.uptimerobot.com/v3/monitors/%5cother",
        "https://api.uptimerobot.com/v3/monitors/%250aother",
        "https://api.uptimerobot.com/v3/incidents",
    ],
)
def test_send_revalidates_url_confinement_before_auth_or_opener(
    monkeypatch: pytest.MonkeyPatch,
    unsafe_url: str,
) -> None:
    """Reject unsafe synthetic targets before constructing any opener."""
    send = cast("Callable[..., object]", member("send_request"))
    helper_error = cast("type[Exception]", member("UptimeRobotCliError"))
    build_calls: list[tuple[object, ...]] = []

    def build_opener(*handlers: object) -> FakeOpener:
        build_calls.append(handlers)
        return FakeOpener([])

    monkeypatch.setattr(request, "build_opener", build_opener)
    plan = request_plan()
    request_credential = credential()
    arguments = request_arguments(retries=10)
    with pytest.raises(helper_error):
        _ = send(plan, unsafe_url, request_credential, arguments)
    assert build_calls == []


def test_send_revalidates_an_unsafe_synthetic_plan_before_opener(monkeypatch: pytest.MonkeyPatch) -> None:
    """Do not trust a direct caller's preconstructed RequestPlan URL."""
    plan_type = cast("Callable[..., object]", member("RequestPlan"))
    send = cast("Callable[..., object]", member("send_request"))
    helper_error = cast("type[Exception]", member("UptimeRobotCliError"))
    build_calls: list[tuple[object, ...]] = []

    def build_opener(*handlers: object) -> FakeOpener:
        build_calls.append(handlers)
        return FakeOpener([])

    monkeypatch.setattr(request, "build_opener", build_opener)
    unsafe_plan = plan_type(
        body=None,
        confirmation_value=None,
        high_risk=False,
        method="GET",
        operation_id=None,
        query=(),
        url="https://api.uptimerobot.com/v3/monitors/%25252e%25252e/incidents",
    )
    request_credential = credential()
    arguments = request_arguments()
    with pytest.raises(helper_error):
        _ = send(unsafe_plan, f"{API_BASE_URL}/monitors", request_credential, arguments)
    assert build_calls == []


def test_request_body_file_is_binary_bounded_utf8_strict_and_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Enforce exact/one-over bytes and UTF-8 while closing every body file."""
    load = cast("Callable[[argparse.Namespace], JsonValue]", member("load_body"))
    helper_error = cast("type[Exception]", member("UptimeRobotCliError"))
    document = b'{"a":1}'
    monkeypatch.setattr(UPTIMEROBOT, "MAX_REQUEST_BODY_BYTES", len(document))

    exact = RecordingStream(document)
    assert load(argparse.Namespace(body_json=None, body_file=FakeSpecFile(exact))) == {"a": 1}
    assert exact.closed
    assert exact.read_sizes == [len(document) + 1]

    over = RecordingStream(document + b" ")
    over_arguments = argparse.Namespace(body_json=None, body_file=FakeSpecFile(over))
    with pytest.raises(helper_error, match="Request body exceeds"):
        _ = load(over_arguments)
    assert over.closed
    assert over.read_sizes == [len(document) + 1]

    invalid_utf8 = RecordingStream(b"\xff")
    invalid_utf8_arguments = argparse.Namespace(body_json=None, body_file=FakeSpecFile(invalid_utf8))
    with pytest.raises(helper_error, match="valid UTF-8 JSON"):
        _ = load(invalid_utf8_arguments)
    assert invalid_utf8.closed


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ('{"value":NaN}', "finite"),
        ('{"value":Infinity}', "finite"),
        ('{"value":-Infinity}', "finite"),
        ('{"value":1e9999}', "finite"),
        ('{"duplicate":1,"duplicate":2}', "duplicate keys"),
    ],
)
def test_request_json_rejects_constants_overflow_and_duplicate_keys_without_echo(
    body: str,
    expected: str,
) -> None:
    """Apply the documented strict duplicate-key and finite-number policy."""
    result = run_script("request", "/monitors", "--method", "POST", "--body-json", body)
    assert result.returncode == 1
    assert expected in result.stderr
    assert body not in result.stderr
    assert "Traceback" not in result.stderr


def test_request_json_depth_node_and_string_boundaries(monkeypatch: pytest.MonkeyPatch) -> None:
    """Allow each exact structural boundary and reject one-over inputs iteratively."""
    load = cast("Callable[[argparse.Namespace], JsonValue]", member("load_body"))
    helper_error = cast("type[Exception]", member("UptimeRobotCliError"))

    monkeypatch.setattr(UPTIMEROBOT, "MAX_REQUEST_JSON_DEPTH", 2)
    assert load(argparse.Namespace(body_json="[[0]]", body_file=None)) == [[0]]
    too_deep_arguments = argparse.Namespace(body_json="[[[0]]]", body_file=None)
    with pytest.raises(helper_error, match="2-level JSON depth limit"):
        _ = load(too_deep_arguments)

    monkeypatch.setattr(UPTIMEROBOT, "MAX_REQUEST_JSON_DEPTH", 64)
    monkeypatch.setattr(UPTIMEROBOT, "MAX_REQUEST_JSON_NODES", 3)
    assert load(argparse.Namespace(body_json="[0,1]", body_file=None)) == [0, 1]
    too_many_nodes_arguments = argparse.Namespace(body_json="[0,1,2]", body_file=None)
    with pytest.raises(helper_error, match="3-node JSON safety limit"):
        _ = load(too_many_nodes_arguments)

    monkeypatch.setattr(UPTIMEROBOT, "MAX_REQUEST_JSON_NODES", 100)
    monkeypatch.setattr(UPTIMEROBOT, "MAX_REQUEST_JSON_STRING_CHARS", 3)
    assert load(argparse.Namespace(body_json='{"abc":"xyz"}', body_file=None)) == {"abc": "xyz"}
    long_key_arguments = argparse.Namespace(body_json='{"abcd":"xyz"}', body_file=None)
    with pytest.raises(helper_error, match="3-character JSON string limit"):
        _ = load(long_key_arguments)
    long_value_arguments = argparse.Namespace(body_json='{"abc":"xyzz"}', body_file=None)
    with pytest.raises(helper_error, match="3-character JSON string limit"):
        _ = load(long_value_arguments)


@pytest.mark.parametrize("invalid_body", [{"value": float("nan")}, {"value": float("inf")}])
def test_atomic_request_encoding_rejects_invalid_synthetic_bodies_before_opener(
    monkeypatch: pytest.MonkeyPatch,
    invalid_body: JsonValue,
) -> None:
    """Apply strict encoding to direct callers before any mutation attempt."""
    send = cast("Callable[..., object]", member("send_request"))
    helper_error = cast("type[Exception]", member("UptimeRobotCliError"))
    build_calls: list[tuple[object, ...]] = []

    def build_opener(*handlers: object) -> FakeOpener:
        build_calls.append(handlers)
        return FakeOpener([])

    monkeypatch.setattr(request, "build_opener", build_opener)
    plan = request_plan("POST", body=invalid_body)
    request_credential = credential()
    arguments = request_arguments()
    with pytest.raises(helper_error, match="non-finite JSON number"):
        _ = send(plan, f"{API_BASE_URL}/monitors", request_credential, arguments)
    assert build_calls == []


def test_atomic_request_encoding_honors_exact_and_one_over_byte_limits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Finish strict JSON encoding and size validation before opening a write."""
    send = cast("Callable[..., object]", member("send_request"))
    helper_error = cast("type[Exception]", member("UptimeRobotCliError"))
    body: JsonValue = {"ordinary": "visible"}
    encoded = b'{"ordinary":"visible"}'
    monkeypatch.setattr(UPTIMEROBOT, "MAX_REQUEST_BODY_BYTES", len(encoded))
    response = FakeResponse(b"{}")
    opener = install_opener(monkeypatch, [response])
    _ = send(request_plan("POST", body=body), f"{API_BASE_URL}/monitors", credential(), request_arguments())
    assert len(opener.requests) == 1
    assert opener.requests[0].data == encoded
    assert response.closed

    build_calls: list[tuple[object, ...]] = []

    def build_opener(*handlers: object) -> FakeOpener:
        build_calls.append(handlers)
        return FakeOpener([])

    monkeypatch.setattr(request, "build_opener", build_opener)
    monkeypatch.setattr(UPTIMEROBOT, "MAX_REQUEST_BODY_BYTES", len(encoded) - 1)
    oversized_plan = request_plan("POST", body=body)
    request_credential = credential()
    arguments = request_arguments()
    with pytest.raises(helper_error, match="Request body exceeds"):
        _ = send(oversized_plan, f"{API_BASE_URL}/monitors", request_credential, arguments)
    assert build_calls == []


@pytest.mark.parametrize("method", WRITE_METHODS)
@pytest.mark.parametrize("transport_kind", ["response", "http-error"])
@pytest.mark.parametrize("failure_kind", ["size", "oserror", "http-exception", "incomplete-read"])
def test_write_response_consumption_failures_are_one_shot_and_indeterminate(
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    transport_kind: str,
    failure_kind: str,
) -> None:
    """Classify bounded direct and HTTPError body-consumption failures for every write."""
    send = cast("Callable[..., object]", member("send_request"))
    helper_error = cast("type[Exception]", member("UptimeRobotCliError"))
    monkeypatch.setattr(UPTIMEROBOT, "MAX_API_RESPONSE_BYTES", 4)
    monkeypatch.setattr(UPTIMEROBOT, "MAX_ERROR_RESPONSE_BYTES", 4)
    if failure_kind == "size":
        stream: RecordingStream = RecordingStream(b"12345")
    elif failure_kind == "oserror":
        stream = FailingStream(OSError(f"read failed {RESERVED_READ_CREDENTIAL}"))
    elif failure_kind == "http-exception":
        stream = FailingStream(HTTPException(f"protocol failed {RESERVED_READ_CREDENTIAL}"))
    else:
        stream = FailingStream(IncompleteRead(b"", 1))
    status = HTTP_OK if transport_kind == "response" else 400
    outcome: TransportOutcome
    if transport_kind == "response":
        outcome = StreamResponse(stream, status=status)
    else:
        outcome = http_failure_with_stream(status, stream)
    opener = install_opener(monkeypatch, [outcome])
    plan = request_plan(method, body={"ordinary": "visible"})
    main_credential = credential(RESERVED_MAIN_CREDENTIAL)
    arguments = request_arguments(retries=10)
    with pytest.raises(helper_error) as caught:
        _ = send(
            plan,
            f"{API_BASE_URL}/monitors",
            main_credential,
            arguments,
            secrets=(RESERVED_READ_CREDENTIAL, RESERVED_MAIN_CREDENTIAL),
        )
    message = str(caught.value)
    assert f"HTTP {status}" in message
    assert f"The {method} mutation may have succeeded" in message
    assert "Re-read the exact UptimeRobot target" in message
    assert RESERVED_READ_CREDENTIAL not in message
    assert len(opener.requests) == 1
    assert stream.closed


@pytest.mark.parametrize("method", WRITE_METHODS)
@pytest.mark.parametrize("failure_kind", ["utf8", "malformed-json", "strict-constant", "duplicate-key", "depth"])
def test_successful_write_response_parse_failures_are_indeterminate(
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    failure_kind: str,
) -> None:
    """Treat UTF-8, strict-JSON, and depth failures after HTTP 2xx as ambiguous writes."""
    send = cast("Callable[..., object]", member("send_request"))
    helper_error = cast("type[Exception]", member("UptimeRobotCliError"))
    if failure_kind == "utf8":
        body = b"\xff"
    elif failure_kind == "malformed-json":
        body = b"{"
    elif failure_kind == "strict-constant":
        body = b'{"value":NaN}'
    elif failure_kind == "duplicate-key":
        body = b'{"value":1,"value":2}'
    else:
        monkeypatch.setattr(UPTIMEROBOT, "MAX_RESPONSE_JSON_DEPTH", 2)
        body = b"[[[0]]]"
    response = FakeResponse(body)
    opener = install_opener(monkeypatch, [response])
    plan = request_plan(method, body={"ordinary": "visible"})
    request_credential = credential()
    arguments = request_arguments(retries=10)
    with pytest.raises(helper_error) as caught:
        _ = send(
            plan,
            f"{API_BASE_URL}/monitors",
            request_credential,
            arguments,
        )
    message = str(caught.value)
    assert "HTTP 200" in message
    assert f"The {method} mutation may have succeeded" in message
    assert "Re-read the exact UptimeRobot target" in message
    assert len(opener.requests) == 1
    assert response.closed


def test_get_response_consumption_rules_remain_separate(monkeypatch: pytest.MonkeyPatch) -> None:
    """Retry retryable GET status reads but never label a 2xx parse failure as a mutation."""
    send = cast("Callable[..., object]", member("send_request"))
    helper_error = cast("type[Exception]", member("UptimeRobotCliError"))
    failed_stream = FailingStream(OSError("temporary read failure"))
    retryable = StreamResponse(failed_stream, status=503)
    retryable.headers["Retry-After"] = "0"
    success = FakeResponse(b'{"ok":true}')
    opener = install_opener(monkeypatch, [retryable, success])

    def no_sleep(_delay: float) -> None:
        del _delay

    monkeypatch.setattr(UPTIMEROBOT.time, "sleep", no_sleep)
    result = send(request_plan(), f"{API_BASE_URL}/monitors", credential(), request_arguments(retries=1))
    assert vars(result)["payload"] == {"ok": True}
    assert len(opener.requests) == EXPECTED_RETRIED_REQUEST_COUNT
    assert failed_stream.closed

    malformed = FakeResponse(b"{")
    opener = install_opener(monkeypatch, [malformed])
    malformed_plan = request_plan()
    malformed_credential = credential()
    malformed_arguments = request_arguments(retries=10)
    with pytest.raises(helper_error) as caught:
        _ = send(
            malformed_plan,
            f"{API_BASE_URL}/monitors",
            malformed_credential,
            malformed_arguments,
        )
    assert "may have succeeded" not in str(caught.value)
    assert "indeterminate" not in str(caught.value)
    assert len(opener.requests) == 1
    assert malformed.closed


@pytest.mark.parametrize(
    "next_link_value",
    [
        "https://api.uptimerobot.com/v3/incidents?cursor=2",
        "/v3/incidents?cursor=2",
        "/incidents?cursor=2",
        "incidents?cursor=2",
        "../incidents?cursor=2",
    ],
)
def test_pagination_rejects_cross_collection_links_before_a_second_request(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    next_link_value: str,
) -> None:
    """Never request or report a page whose nextLink changes endpoint path."""
    result_type = cast("Callable[..., object]", member("ApiResult"))
    paginate = cast("Callable[..., None]", member("write_paginated_results"))
    helper_error = cast("type[Exception]", member("UptimeRobotCliError"))
    calls: list[str] = []

    def fake_send(_plan: object, url: str, *_arguments: object, **_keywords: object) -> object:
        calls.append(url)
        return result_type(
            payload={"data": [], "nextLink": next_link_value},
            response_bytes=1,
            status=200,
            url=url,
        )

    monkeypatch.setattr(UPTIMEROBOT, "send_request", fake_send)
    pagination_arguments = argparse.Namespace(max_pages=3, retries=0, timeout=1.0)
    context = uptime_context()
    plan = request_plan()
    pagination_credential = credential()
    with pytest.raises(helper_error, match=r"exact collection endpoint path|configured /v3 base path"):
        paginate(
            pagination_arguments,
            context,
            plan,
            pagination_credential,
            f"{API_BASE_URL}/monitors",
        )
    assert calls == [f"{API_BASE_URL}/monitors"]
    assert capsys.readouterr().out == ""


def test_retry_after_http_dates_and_extreme_controls_are_deterministic() -> None:
    """Support HTTP dates with an injectable clock and bound extreme fallback inputs."""
    retry_delay = cast("Callable[..., float]", member("retry_delay_header"))
    now = datetime(2026, 9, 1, 2, 30, tzinfo=UTC)
    assert (
        retry_delay(format_datetime(now + timedelta(seconds=30), usegmt=True), 0, now=now) == EXPECTED_HTTP_DATE_DELAY
    )
    assert (
        retry_delay(format_datetime(now + timedelta(seconds=120), usegmt=True), 0, now=now) == MAX_EXPECTED_RETRY_DELAY
    )
    assert retry_delay(format_datetime(now - timedelta(seconds=1), usegmt=True), 0, now=now) == 0.0
    assert retry_delay("9" * 10_000, 10**100) == MAX_EXPECTED_RETRY_DELAY
    assert retry_delay("not-a-date", 10**100) == EXPECTED_HTTP_DATE_DELAY


@pytest.mark.parametrize(("timeout", "expected_code"), [("300", 0), ("300.0001", 1), ("1e309", 1)])
def test_timeout_has_an_exact_300_second_prework_cap(timeout: str, expected_code: int) -> None:
    """Accept the exact timeout cap and reject over-cap or overflowing controls."""
    result = run_script("context", f"--timeout={timeout}")
    assert result.returncode == expected_code
    if expected_code != 0:
        assert "at most 300" in result.stderr
        assert "Traceback" not in result.stderr


def test_direct_extreme_integer_timeout_uses_the_bounded_validation_error() -> None:
    """Keep direct-call namespaces from leaking float conversion overflows."""
    validate_timeout = cast("Callable[[argparse.Namespace], float]", member("validated_timeout"))
    helper_error = cast("type[Exception]", member("UptimeRobotCliError"))
    arguments = argparse.Namespace(timeout=10**10_000)

    with pytest.raises(helper_error, match="at most 300"):
        _ = validate_timeout(arguments)
