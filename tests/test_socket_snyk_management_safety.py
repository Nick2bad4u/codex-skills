# Copyright (c) 2026 Nick2bad4u
"""Focused safety regressions for the Socket and Snyk management transports."""

from __future__ import annotations

import argparse
import gc
import importlib.util
import json
import math
import os
import re
import subprocess
import sys
import time
from email.message import Message
from http.client import HTTPException
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, Self, cast, override
from urllib import error, parse, request

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Mapping
    from types import ModuleType, TracebackType

type JsonValue = bool | int | float | str | list[JsonValue] | dict[str, JsonValue] | None
type TransportOutcome = FakeResponse | BaseException

REPO_ROOT = Path(__file__).resolve().parents[1]
SOCKET_BASE_URL = "https://api.socket.dev/v0"
SNYK_BASE_URL = "https://api.snyk.io/rest"
SNYK_API_VERSION = "2024-10-15"
TEST_TOKEN = "socket-snyk-active-token-value"  # noqa: S105  # Synthetic credential fixture.
TEST_SOCKET_ENVIRONMENT = "TEST_SOCKET_ENV"
TEST_SNYK_ENVIRONMENT = "TEST_SNYK_ENV"
HTTP_OK = 200
HTTP_NO_CONTENT = 204
RETRIED_REQUEST_COUNT = 2
MIN_EXPECTED_REDACTIONS = 2
GET_RETRYABLE_STATUS_CODES = (408, 429, 500, 502, 503, 504)
AMBIGUOUS_WRITE_STATUS_CODES = (*GET_RETRYABLE_STATUS_CODES, 599)
WRITE_METHODS = ("POST", "PUT", "PATCH", "DELETE")
NONFINITE_JSON_VALUES = ("NaN", "Infinity", "-Infinity", "1e400", "-1e400")
TRANSPORT_FAILURE_KINDS = ("url-error", "os-error", "http-exception")


class ApiResultView(Protocol):
    """Typed view of a dynamically loaded API result."""

    payload: JsonValue
    response_bytes: int
    status: int
    url: str


class RecordingStream(BytesIO):
    """Bytes stream that records every requested read bound."""

    def __init__(self, payload: bytes) -> None:
        """Initialize payload bytes and an empty read-size log."""
        super().__init__(payload)
        self.read_sizes: list[int] = []

    @override
    def read(self, size: int | None = -1, /) -> bytes:
        """Record and perform one bounded read."""
        self.read_sizes.append(-1 if size is None else size)
        return super().read(size)


class FakeResponse:
    """Small urllib-compatible response for deterministic transport tests."""

    def __init__(
        self,
        payload: bytes,
        *,
        status: int = HTTP_OK,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        """Initialize a response payload, status, and headers."""
        super().__init__()
        self._stream = RecordingStream(payload)
        self.status = status
        self.headers = http_headers(headers or {})

    @property
    def closed(self) -> bool:
        """Return whether the response stream was closed."""
        return self._stream.closed

    @property
    def read_sizes(self) -> list[int]:
        """Return the bounds used for each response read."""
        return self._stream.read_sizes

    def __enter__(self) -> Self:
        """Enter a urllib-style response context."""
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Leave the response context without suppressing an exception."""
        del exception_type, exception, traceback
        self._stream.close()

    def read(self, amount: int | None = None) -> bytes:
        """Return the configured payload, respecting an optional bound."""
        return self._stream.read(-1 if amount is None else amount)


class ReadFailureResponse(FakeResponse):
    """Response whose body read fails after a successful HTTP status is known."""

    @override
    def read(self, amount: int | None = None) -> bytes:
        """Raise a deterministic transport read failure."""
        self._stream.read_sizes.append(-1 if amount is None else amount)
        raise OSError("synthetic response read failure")


class ReadFailureStream(RecordingStream):
    """HTTP error stream whose body cannot be read."""

    def __init__(self, reason: str) -> None:
        """Store the reason that the failed body read will expose."""
        super().__init__(b"")
        self.reason = reason

    @override
    def read(self, size: int | None = -1, /) -> bytes:
        """Record the attempted bound and raise the configured failure."""
        self.read_sizes.append(-1 if size is None else size)
        raise OSError(self.reason)


class FakeOpener:
    """Record requests and consume deterministic responses or errors."""

    def __init__(self, outcomes: list[TransportOutcome]) -> None:
        """Initialize ordered outcomes and an empty request log."""
        super().__init__()
        self.outcomes = outcomes
        self.requests: list[request.Request] = []

    def open(self, api_request: request.Request, timeout: float) -> FakeResponse:
        """Record a request and return or raise its configured outcome."""
        del timeout
        self.requests.append(api_request)
        if not self.outcomes:
            raise AssertionError("Fake opener exhausted its configured outcomes.")
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class FailOnIterationList(list[JsonValue]):
    """List sentinel proving an overflow page was not retained."""

    @override
    def __iter__(self) -> Iterator[JsonValue]:
        """Fail if pagination tries to merge this page's items."""
        raise AssertionError("Overflow page items must not be retained.")


def http_headers(values: Mapping[str, str]) -> Message:
    """Create an HTTPMessage-compatible header mapping."""
    headers = Message()
    for name, value in values.items():
        headers[name] = value
    return headers


def recording_http_failure(
    url: str,
    status: int,
    payload: bytes = b'{"message":"temporary"}',
    *,
    content_length: str | None = None,
    content_type: str = "application/json",
) -> tuple[error.HTTPError, RecordingStream]:
    """Create a readable HTTP failure and expose its recording stream."""
    headers = http_headers({"Content-Type": content_type, "Retry-After": "0"})
    if content_length is not None:
        headers["Content-Length"] = content_length
    stream = RecordingStream(payload)
    return error.HTTPError(url, status, "fixture failure", headers, stream), stream


def http_failure(url: str, status: int, payload: bytes = b'{"message":"temporary"}') -> error.HTTPError:
    """Create a readable retryable HTTP failure."""
    failure, _stream = recording_http_failure(url, status, payload)
    return failure


def transport_failure(kind: str, reason: str) -> BaseException:
    """Create one direct transport failure carrying untrusted reason text."""
    if kind == "url-error":
        return error.URLError(reason)
    if kind == "os-error":
        return OSError(reason)
    if kind == "http-exception":
        return HTTPException(reason)
    raise AssertionError(f"Unknown transport failure kind: {kind}")


def load_script_module(name: str, relative_path: str) -> ModuleType:
    """Load a helper without invoking its CLI entry point."""
    path = REPO_ROOT / relative_path
    specification = importlib.util.spec_from_file_location(name, path)
    if specification is None or specification.loader is None:
        raise RuntimeError(f"Could not load test module: {path}")
    module = importlib.util.module_from_spec(specification)
    sys.modules[name] = module
    specification.loader.exec_module(module)
    return module


SOCKET = load_script_module(
    "socket_management_safety",
    "skills/socket-management/scripts/manage_socket.py",
)
SNYK = load_script_module(
    "snyk_management_safety",
    "skills/snyk-management/scripts/manage_snyk.py",
)
PROVIDERS = (SOCKET, SNYK)


def member(module: ModuleType, name: str) -> object:
    """Return one dynamically loaded helper member."""
    return getattr(module, name)


def integer_constant(module: ModuleType, name: str) -> int:
    """Return a dynamically loaded integer constant with runtime narrowing."""
    value = member(module, name)
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{name} must be an integer constant.")
    return value


def float_constant(module: ModuleType, name: str) -> float:
    """Return a dynamically loaded numeric constant with runtime narrowing."""
    value = member(module, name)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise TypeError(f"{name} must be a numeric constant.")
    return float(value)


def provider_name(module: ModuleType) -> str:
    """Return a stable provider name for assertion IDs."""
    return "socket" if module is SOCKET else "snyk"


def provider_error(module: ModuleType) -> type[Exception]:
    """Return one provider's safe CLI exception type."""
    name = "SocketCliError" if module is SOCKET else "SnykCliError"
    return cast("type[Exception]", member(module, name))


def provider_base_url(module: ModuleType) -> str:
    """Return one provider's default trusted API base."""
    return SOCKET_BASE_URL if module is SOCKET else SNYK_BASE_URL


def provider_content_type(module: ModuleType) -> str:
    """Return one provider's normal JSON response media type."""
    return "application/json" if module is SOCKET else "application/vnd.api+json"


def provider_context(module: ModuleType) -> object:
    """Create a token-bearing context for one provider."""
    if module is SOCKET:
        context_factory = cast("Callable[..., object]", member(module, "SocketContext"))
        return context_factory(
            base_url=SOCKET_BASE_URL,
            organization="acme",
            repository="widget",
            repository_root=REPO_ROOT,
            token=TEST_TOKEN,
            token_env_name=TEST_SOCKET_ENVIRONMENT,
        )
    context_factory = cast("Callable[..., object]", member(module, "SnykContext"))
    return context_factory(
        api_version=SNYK_API_VERSION,
        auth_scheme="token",
        base_url=SNYK_BASE_URL,
        token=TEST_TOKEN,
        token_env_name=TEST_SNYK_ENVIRONMENT,
    )


def provider_plan(module: ModuleType, method: str, *, url: str | None = None) -> object:
    """Create a request plan for one provider and HTTP method."""
    plan_factory = cast("Callable[..., object]", member(module, "RequestPlan"))
    base_url = SOCKET_BASE_URL if module is SOCKET else SNYK_BASE_URL
    return plan_factory(
        body={"enabled": True} if method != "GET" else None,
        method=method,
        operation_id=None,
        query={} if module is SOCKET else {"version": SNYK_API_VERSION},
        url=url or f"{base_url}/items",
    )


def provider_plan_with_body(module: ModuleType, method: str, body: JsonValue) -> object:
    """Create one request plan with an explicitly supplied body value."""
    plan_factory = cast("Callable[..., object]", member(module, "RequestPlan"))
    return plan_factory(
        body=body,
        method=method,
        operation_id=None,
        query={} if module is SOCKET else {"version": SNYK_API_VERSION},
        url=f"{provider_base_url(module)}/items",
    )


def provider_result(
    module: ModuleType,
    payload: JsonValue,
    *,
    response_bytes: int,
    url: str | None = None,
) -> object:
    """Create one provider's internal bounded result value."""
    result_factory = cast("Callable[..., object]", member(module, "ApiResult"))
    keywords: dict[str, object] = {
        "payload": payload,
        "response_bytes": response_bytes,
        "status": HTTP_OK,
        "url": url or f"{provider_base_url(module)}/items",
    }
    if module is SNYK:
        keywords["sunset"] = None
    return result_factory(**keywords)


def percent_triplets_with_case(value: str, *, mixed: bool) -> str:
    """Change only percent-triplet hex casing while preserving literal token casing."""
    triplet_index = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal triplet_index
        hex_pair = match.group(0)[1:]
        if mixed:
            converted = "".join(
                character.lower() if (triplet_index + index) % 2 == 0 else character.upper()
                for index, character in enumerate(hex_pair)
            )
        else:
            converted = hex_pair.lower()
        triplet_index += 1
        return f"%{converted}"

    return re.sub(r"%[0-9A-Fa-f]{2}", replace, value)


def send(module: ModuleType, plan: object, *, retries: int = 3) -> object:
    """Invoke one provider's transport through its public helper boundary."""
    send_request = cast("Callable[..., object]", member(module, "send_request"))
    arguments = argparse.Namespace(retries=retries, timeout=1.0)
    context = provider_context(module)
    if module is SOCKET:
        return send_request(context, plan, query={}, arguments=arguments)
    return send_request(context, plan, arguments)


def install_opener(monkeypatch: pytest.MonkeyPatch, outcomes: list[TransportOutcome]) -> FakeOpener:
    """Replace urllib opener construction with a deterministic recorder."""
    opener = FakeOpener(outcomes)

    def build_opener(*_handlers: object) -> FakeOpener:
        return opener

    monkeypatch.setattr(request, "build_opener", build_opener)
    return opener


def run_script(module: ModuleType, *arguments: str) -> subprocess.CompletedProcess[str]:
    """Run one helper with real ambient service credentials removed."""
    relative_path = (
        "skills/socket-management/scripts/manage_socket.py"
        if module is SOCKET
        else "skills/snyk-management/scripts/manage_snyk.py"
    )
    environment = {
        key: value
        for key, value in os.environ.items()
        if key not in {"SNYK_API_TOKEN", "SNYK_TOKEN", "SOCKET_API_TOKEN", "SOCKET_SECURITY_API_TOKEN"}
    }
    return subprocess.run(  # noqa: S603  # Current interpreter and reviewed repository script.
        [sys.executable, str(REPO_ROOT / relative_path), *arguments],
        cwd=REPO_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )


@pytest.fixture(autouse=True)
def collect_transport_exception_cycles() -> Iterator[None]:
    """Collect retained urllib exception tracebacks while capture is open."""
    yield
    _ = gc.collect()


def test_socket_redacts_normalized_integration_credentials_and_preserves_settings() -> None:
    """Camel, Pascal, and plural integration credentials are recursively redacted."""
    redact = cast("Callable[[JsonValue, str | None], JsonValue]", member(SOCKET, "redact_json"))
    credential_fields: dict[str, JsonValue] = {
        "githubToken": "github-secret",
        "GitHubTokens": ["github-secret-1", "github-secret-2"],
        "jiraApiToken": "jira-secret",
        "JiraApiTokens": ["jira-secret-1"],
        "s3AccessKey": "s3-access-secret",
        "S3AccessKeys": ["s3-access-secret-1"],
        "s3SecretKey": "s3-secret",
        "S3SecretKeys": ["s3-secret-1"],
        "msSentinelKey": "sentinel-secret",
        "MsSentinelKeys": ["sentinel-secret-1"],
        "webhook": "https://hooks.example.invalid/one",
        "webhooks": ["https://hooks.example.invalid/two"],
        "webhookUrl": "https://hooks.example.invalid/three",
        "WebhookURLs": ["https://hooks.example.invalid/four"],
        "accessToken": "access-secret",
        "refreshTokens": ["refresh-secret"],
        "clientSecret": "client-secret",
        "apiKeys": ["api-secret"],
        "passwords": ["password-secret"],
        "authorization": "Bearer unknown-secret",
        "credentials": {"value": "unknown-secret"},
    }
    ordinary_settings: dict[str, JsonValue] = {
        "enabled": True,
        "integrationName": "production notifications",
        "jiraProjectKey": "SEC",
        "repositoryNames": ["widget"],
        "retryCount": 3,
        "documentationUrl": "https://docs.example.invalid/integration",
    }
    payload: dict[str, JsonValue] = dict(credential_fields)
    payload.update(ordinary_settings)
    payload["nested"] = [{"GitHubToken": "nested-secret", "enabled": False}]

    redacted = cast("dict[str, JsonValue]", redact(payload, TEST_TOKEN))

    for field in credential_fields:
        assert redacted[field] == "<redacted>"
    for field, value in ordinary_settings.items():
        assert redacted[field] == value
    assert redacted["nested"] == [{"GitHubToken": "<redacted>", "enabled": False}]


def test_snyk_redacts_normalized_nested_credentials_and_preserves_settings() -> None:
    """Snyk redaction handles integration secrets independent of the active token."""
    redact = cast("Callable[[JsonValue, str | None], JsonValue]", member(SNYK, "redact_json"))
    credential_fields: dict[str, JsonValue] = {
        "accessToken": "access-secret",
        "ApiTokens": ["api-token-secret"],
        "apiKey": "api-key-secret",
        "Authorization": "Bearer unknown-secret",
        "cookies": ["cookie-secret"],
        "sessionId": "session-secret",
        "Sessions": [{"value": "nested-session-secret"}],
        "credentials": {"value": "credential-secret"},
        "passwords": ["password-secret"],
        "clientSecret": "client-secret",
        "webhookUrl": "https://hooks.example.invalid/secret",
        "WebhookURLs": ["https://hooks.example.invalid/acronym-plural"],
        "slackWebhooks": ["https://hooks.example.invalid/slack"],
        "providerApiKey": "provider-key-secret",
        "integrationTokens": ["integration-token-secret"],
        "s3AccessKeys": ["s3-access-secret"],
        "MsSentinelKey": "sentinel-secret",
    }
    ordinary_settings: dict[str, JsonValue] = {
        "documentationUrl": "https://docs.example.invalid/snyk",
        "integrationName": "production",
        "jiraProjectKey": "SEC",
        "providerName": "github",
        "secretScanningEnabled": True,
        "sessionTimeoutMinutes": 30,
        "tokenExpirationDays": 90,
        "webhookEnabled": True,
    }
    payload: dict[str, JsonValue] = dict(credential_fields)
    payload.update(ordinary_settings)
    payload["nested"] = [
        {
            "ProviderToken": "nested-provider-secret",
            "message": f"active={TEST_TOKEN}",
            "providerName": "gitlab",
        }
    ]

    redacted = cast("dict[str, JsonValue]", redact(payload, TEST_TOKEN))

    for field in credential_fields:
        assert redacted[field] == "<redacted>"
    for field, value in ordinary_settings.items():
        assert redacted[field] == value
    assert redacted["nested"] == [
        {
            "ProviderToken": "<redacted>",
            "message": "active=<redacted>",
            "providerName": "gitlab",
        }
    ]


@pytest.mark.parametrize("module", PROVIDERS, ids=provider_name)
def test_sensitive_key_tokenization_has_positive_and_negative_semantic_tables(module: ModuleType) -> None:
    """Credential field tokens are recognized without suffix collisions in ordinary evidence."""
    is_sensitive = cast("Callable[[str], bool]", member(module, "is_sensitive_key"))
    sensitive = (
        "apiToken",
        "ApiTokens",
        "providerSession",
        "ProviderSessions",
        "authorization",
        "S3AccessKey",
        "s3SecretKeys",
        "integrationCredential",
        "clientSecret",
        "cookies",
        "passwords",
        "webhookUrl",
        "webhookUrls",
        "WebhookURLs",
        "XMLWebhookURLs",
        "MsSentinelKey",
        "APIKeys",
        "api%54oken",
    )
    ordinary = (
        "possessions",
        "tokenExpirationDays",
        "sessionTimeoutMinutes",
        "webhookEnabled",
        "jiraProjectKey",
        "providerName",
        "secretScanningEnabled",
        "basicConfiguration",
        "authorizationMode",
        "accessKeyRotationDays",
    )

    for key in sensitive:
        assert is_sensitive(key), key
    for key in ordinary:
        assert not is_sensitive(key), key


def test_socket_acronym_boundary_keeps_authorization_header_sensitive() -> None:
    """An all-caps acronym cannot hide a following AuthorizationHeader pair."""
    is_sensitive = cast("Callable[[str], bool]", member(SOCKET, "is_sensitive_key"))

    assert is_sensitive("HTTPAuthorizationHeader")


@pytest.mark.parametrize("module", PROVIDERS, ids=provider_name)
def test_sensitive_key_tokenization_is_linear_safe_for_long_acronym_prefixes(module: ModuleType) -> None:
    """Long acronym segments cannot trigger regex backtracking or hide a following API key."""
    is_sensitive = cast("Callable[[str], bool]", member(module, "is_sensitive_key"))
    long_acronym = "A" * 100_000

    assert is_sensitive(f"{long_acronym}_APIKeys")
    assert not is_sensitive(f"{long_acronym}_Configuration")


@pytest.mark.parametrize("module", PROVIDERS, ids=provider_name)
def test_scalar_redaction_distinguishes_credentials_from_security_prose(module: ModuleType) -> None:
    """Untrusted scalar credentials are removed while ordinary explanatory prose remains intact."""
    redact = cast("Callable[[JsonValue, str | None], JsonValue]", member(module, "redact_json"))
    jwt_header_placeholder = "eyJ" + "hbGciOiJIUzI1NiJ9"
    jwt_placeholder = jwt_header_placeholder + ".payload.signature"
    stripe_token_placeholder = "sk_live_" + "1234567890abcdef"
    credential_evidence = (
        (f"Authorization: Bearer {jwt_placeholder}", jwt_header_placeholder),
        ("Authorization=Basic dXNlcjpwYXNz", "dXNlcjpwYXNz"),
        ("Basic dXNlcjpwYXNz.", "dXNlcjpwYXNz"),
        (f"token {stripe_token_placeholder}", stripe_token_placeholder),
        ("providerSession=provider-session-secret", "provider-session-secret"),
        ("callback=https://user-name:password-value@example.invalid/hook", "password-value"),
    )
    ordinary_evidence = (
        "token expiration is thirty days",
        "token rotation is enabled",
        "basic configuration remains enabled",
        "Bearer is the auth scheme",
        "Bearer authentication is configured.",
        "The possessions field is ordinary evidence",
    )

    for value, secret in credential_evidence:
        redacted = cast("str", redact(value, None))
        assert secret not in redacted
        assert "<redacted>" in redacted
    for value in ordinary_evidence:
        assert redact(value, None) == value


@pytest.mark.parametrize("module", PROVIDERS, ids=provider_name)
def test_plain_scalar_response_is_redacted_before_display_truncation(module: ModuleType) -> None:
    """A credential crossing the display boundary cannot leak a leading token fragment."""
    response_payload = cast("Callable[..., JsonValue]", member(module, "response_payload"))
    limit = integer_constant(module, "MAX_RESPONSE_TEXT")
    authorization_prefix = " Authorization: Bearer "
    exposed_fragment = TEST_TOKEN[:8]
    padding = "x" * (limit - len(authorization_prefix) - len(exposed_fragment))
    data = f"{padding}{authorization_prefix}{TEST_TOKEN}".encode()
    if module is SOCKET:
        rendered = response_payload(data, "text/plain", TEST_TOKEN)
    else:
        rendered = response_payload(data, "text/plain", source="fixture", token=TEST_TOKEN)

    assert isinstance(rendered, str)
    assert exposed_fragment not in rendered
    assert "<redacted>" in rendered
    assert len(rendered) <= limit


@pytest.mark.parametrize("module", PROVIDERS, ids=provider_name)
def test_active_credential_redaction_handles_complex_and_percent_case_variants(module: ModuleType) -> None:
    """Raw, quoted, form, URL, and mixed-case percent encodings of one active credential are removed."""
    redact = cast("Callable[[JsonValue, str | None], JsonValue]", member(module, "redact_json"))
    active = "Tök/+/= space"
    quoted = parse.quote(active, safe="")
    form_encoded = parse.quote_plus(active, safe="")
    lower_quoted = percent_triplets_with_case(quoted, mixed=False)
    mixed_form = percent_triplets_with_case(form_encoded, mixed=True)
    values: list[JsonValue] = [
        active,
        f'"{active}"',
        f"Bearer {active}",
        lower_quoted,
        mixed_form,
        f"https://{lower_quoted}@example.invalid/resource",
        f"https://example.invalid/?active={mixed_form}",
    ]

    redacted = cast("list[JsonValue]", redact(values, active))
    rendered = json.dumps(redacted, ensure_ascii=False)

    assert active not in rendered
    assert lower_quoted not in rendered
    assert mixed_form not in rendered
    assert "<redacted>" in rendered


@pytest.mark.parametrize("module", PROVIDERS, ids=provider_name)
def test_active_credential_redaction_handles_arbitrary_partial_percent_encoding(module: ModuleType) -> None:
    """Each credential character may independently remain raw or use mixed-case URL/form encoding."""
    redact = cast("Callable[[JsonValue, str | None], JsonValue]", member(module, "redact_json"))
    active = "Tök/+/= space"
    partially_encoded = "T%c3%B6k%2f+%2F%3d+space"

    redacted = cast("str", redact(f"active={partially_encoded}", active))

    assert partially_encoded not in redacted
    assert "<redacted>" in redacted


@pytest.mark.parametrize("module", PROVIDERS, ids=provider_name)
def test_scheme_wrapped_active_credential_redacts_its_bare_encoded_value(module: ModuleType) -> None:
    """An active credential carrying its scheme protects the stripped raw and encoded forms."""
    redact = cast("Callable[[JsonValue, str | None], JsonValue]", member(module, "redact_json"))
    bare = "Tök/+/= space"
    encoded = percent_triplets_with_case(parse.quote_plus(bare, safe=""), mixed=True)

    redacted = cast("list[JsonValue]", redact([bare, encoded], f"Bearer {bare}"))
    rendered = json.dumps(redacted, ensure_ascii=False)

    assert bare not in rendered
    assert encoded not in rendered
    assert rendered.count("<redacted>") >= MIN_EXPECTED_REDACTIONS


@pytest.mark.parametrize("module", PROVIDERS, ids=provider_name)
def test_raw_active_credential_matching_remains_case_sensitive(module: ModuleType) -> None:
    """Percent hex is case-insensitive without broad case-insensitive matching of raw evidence."""
    redact = cast("Callable[[JsonValue, str | None], JsonValue]", member(module, "redact_json"))
    active = "MiXeD/Ä+="
    ordinary = "mixed/Ä+="

    assert redact(ordinary, active) == ordinary


def test_socket_accepts_only_the_official_v0_origin() -> None:
    """Socket's base URL is fixed to the official v0 API origin."""
    sanitize = cast("Callable[[str], str]", member(SOCKET, "sanitize_base_url"))
    helper_error = cast("type[Exception]", member(SOCKET, "SocketCliError"))

    assert sanitize(f"{SOCKET_BASE_URL}/") == SOCKET_BASE_URL
    for unsafe in (
        "https://api.socket.dev.evil.invalid/v0",
        "https://socket.example.invalid/v0",
        "https://api.socket.dev/v1",
        "http://api.socket.dev/v0",
    ):
        with pytest.raises(helper_error):
            _ = sanitize(unsafe)


def test_snyk_accepts_all_and_only_official_regional_rest_origins() -> None:
    """Snyk accepts every current official region and rejects lookalike hosts."""
    sanitize = cast("Callable[[str], str]", member(SNYK, "sanitize_base_url"))
    helper_error = cast("type[Exception]", member(SNYK, "SnykCliError"))
    official = (
        "https://api.snyk.io/rest",
        "https://api.us.snyk.io/rest",
        "https://api.eu.snyk.io/rest",
        "https://api.au.snyk.io/rest",
    )

    for base_url in official:
        assert sanitize(f"{base_url}/") == base_url
    for unsafe in (
        "https://api.ca.snyk.io/rest",
        "https://api.snyk.io.evil.invalid/rest",
        "https://tenant.example.invalid/rest",
        "https://api.snyk.io/v1",
        "http://api.snyk.io/rest",
    ):
        with pytest.raises(helper_error):
            _ = sanitize(unsafe)


@pytest.mark.parametrize("module", PROVIDERS, ids=provider_name)
def test_context_validates_origin_before_reading_token_environment(
    monkeypatch: pytest.MonkeyPatch,
    module: ModuleType,
) -> None:
    """Invalid origins fail before ambient or explicit token lookup."""
    resolve_context = cast("Callable[[argparse.Namespace], object]", member(module, "resolve_context"))
    helper_error_name = "SocketCliError" if module is SOCKET else "SnykCliError"
    helper_error = cast("type[Exception]", member(module, helper_error_name))
    token_lookups = 0

    def unexpected_token_lookup(_token_envs: list[str]) -> tuple[str | None, str | None]:
        nonlocal token_lookups
        token_lookups += 1
        return TEST_TOKEN, "UNEXPECTED_TOKEN_ENV"

    monkeypatch.setattr(module, "resolve_token", unexpected_token_lookup)
    if module is SOCKET:
        arguments = argparse.Namespace(
            base_url="https://attacker.example.invalid/v0",
            org=None,
            repo=REPO_ROOT,
            repository=None,
            token_envs=[],
        )
    else:
        arguments = argparse.Namespace(
            api_version=SNYK_API_VERSION,
            auth_scheme="token",
            base_url="https://attacker.example.invalid/rest",
            token_envs=[],
        )

    with pytest.raises(helper_error):
        _ = resolve_context(arguments)

    assert token_lookups == 0


@pytest.mark.parametrize("module", PROVIDERS, ids=provider_name)
def test_authentication_is_not_attached_before_request_origin_validation(
    monkeypatch: pytest.MonkeyPatch,
    module: ModuleType,
) -> None:
    """Even a forged plan cannot attach authentication to an untrusted origin."""
    helper_error_name = "SocketCliError" if module is SOCKET else "SnykCliError"
    helper_error = cast("type[Exception]", member(module, helper_error_name))
    opener = install_opener(monkeypatch, [FakeResponse(b"{}")])
    forged_plan = provider_plan(module, "GET", url="https://attacker.example.invalid/items")

    with pytest.raises(helper_error):
        _ = send(module, forged_plan, retries=0)

    assert opener.requests == []


@pytest.mark.parametrize(
    "unsafe_path",
    [
        "/items/%2e%2e/admin",
        "/items/%252E%252e/admin",
        "/items%2Fadmin",
        "/items%252fadmin",
        "/items%5Cadmin",
        "/items%255cadmin",
        "/items%3Fadmin=value",
        "/items%2523fragment",
        "/items%00control",
        "/items%250Acontrol",
        "/items/%2",
        "/items/%GG",
    ],
)
@pytest.mark.parametrize("absolute", [False, True], ids=("relative", "absolute"))
@pytest.mark.parametrize("module", PROVIDERS, ids=provider_name)
def test_repeated_decoding_confines_relative_and_absolute_endpoint_paths(
    module: ModuleType,
    *,
    absolute: bool,
    unsafe_path: str,
) -> None:
    """Encoded structural delimiters, traversal, controls, and malformed escapes fail closed."""
    validate = cast("Callable[[str, str], str]", member(module, "validated_endpoint_url"))
    base_url = provider_base_url(module)
    endpoint = f"{base_url}{unsafe_path}" if absolute else unsafe_path

    with pytest.raises(provider_error(module), match=r"(?i)(path|encoded|escape|control|travers)"):
        _ = validate(base_url, endpoint)


@pytest.mark.parametrize("module", PROVIDERS, ids=provider_name)
def test_safe_encoded_path_parameters_survive_repeated_decoding_checks(module: ModuleType) -> None:
    """Spaces, plus, equals, Unicode, and a nonstructural literal percent remain usable parameters."""
    fill_path = cast("Callable[[str, dict[str, str]], str]", member(module, "fill_path"))
    validate = cast("Callable[[str, str], str]", member(module, "validated_endpoint_url"))
    path = fill_path("/items/{identifier}", {"identifier": "café + 100%=x"})

    validated = validate(provider_base_url(module), path)

    assert validated.endswith(path)
    assert "%C3%A9" in path
    assert "%2B" in path
    assert "%25" in path
    assert "%3D" in path


@pytest.mark.parametrize("module", PROVIDERS, ids=provider_name)
def test_encoded_spec_traversal_is_rejected(module: ModuleType) -> None:
    """OpenAPI paths cannot traverse their trusted base after repeated decoding."""
    validate = cast("Callable[[str, object], str]", member(module, "validate_spec_url"))
    if module is SOCKET:
        spec_url = f"{SOCKET_BASE_URL}/openapi/%252E%252e/private"
    else:
        spec_url = f"{SNYK_BASE_URL}/openapi/{SNYK_API_VERSION}/%252E%252e/private"
    context = provider_context(module)

    with pytest.raises(provider_error(module), match=r"(?i)(path|encoded|escape|travers)"):
        _ = validate(spec_url, context)


def test_snyk_pagination_link_repeated_decoding_cannot_escape_rest() -> None:
    """A same-origin next link is still rejected when its path decodes into traversal."""
    pagination_plan = cast("Callable[[object, object, str], object]", member(SNYK, "pagination_plan"))
    next_link = f"/rest/items/%252e%252e/admin?version={SNYK_API_VERSION}"
    context = provider_context(SNYK)
    plan = provider_plan(SNYK, "GET")

    with pytest.raises(provider_error(SNYK), match=r"(?i)(path|encoded|escape|travers)"):
        _ = pagination_plan(context, plan, next_link)


@pytest.mark.parametrize("module", PROVIDERS, ids=provider_name)
def test_encoded_path_rejection_occurs_before_any_authenticated_request(
    monkeypatch: pytest.MonkeyPatch,
    module: ModuleType,
) -> None:
    """A double-encoded traversal plan is rejected before an opener sees authentication."""
    opener = install_opener(monkeypatch, [FakeResponse(b"{}")])
    plan = provider_plan(module, "GET", url=f"{provider_base_url(module)}/items/%252e%252e/admin")

    with pytest.raises(provider_error(module)):
        _ = send(module, plan, retries=0)

    assert opener.requests == []


@pytest.mark.parametrize("status", GET_RETRYABLE_STATUS_CODES)
@pytest.mark.parametrize("module", PROVIDERS, ids=provider_name)
def test_get_retries_every_retryable_http_status(
    monkeypatch: pytest.MonkeyPatch,
    module: ModuleType,
    status: int,
) -> None:
    """GET requests retry every explicitly retryable HTTP status."""
    base_url = SOCKET_BASE_URL if module is SOCKET else SNYK_BASE_URL
    success_headers = {
        "Content-Type": "application/json" if module is SOCKET else "application/vnd.api+json",
    }
    opener = install_opener(
        monkeypatch,
        [
            http_failure(f"{base_url}/items", status),
            FakeResponse(b'{"ok":true}', headers=success_headers),
        ],
    )
    sleeps: list[float] = []
    monkeypatch.setattr(time, "sleep", sleeps.append)

    result = cast("ApiResultView", send(module, provider_plan(module, "GET"), retries=1))

    assert result.payload == {"ok": True}
    assert len(opener.requests) == RETRIED_REQUEST_COUNT
    assert sleeps == [0.0]


@pytest.mark.parametrize("module", PROVIDERS, ids=provider_name)
def test_get_retryable_status_does_not_depend_on_reading_the_error_body(
    monkeypatch: pytest.MonkeyPatch,
    module: ModuleType,
) -> None:
    """A failed error-body read cannot suppress an otherwise authorized GET retry."""
    stream = ReadFailureStream("unreadable retryable body")
    retryable = error.HTTPError(
        f"{provider_base_url(module)}/items",
        503,
        "retryable",
        http_headers({"Retry-After": "0"}),
        stream,
    )
    opener = install_opener(
        monkeypatch,
        [retryable, FakeResponse(b'{"ok":true}', headers={"Content-Type": provider_content_type(module)})],
    )
    sleeps: list[float] = []
    monkeypatch.setattr(time, "sleep", sleeps.append)

    result = cast("ApiResultView", send(module, provider_plan(module, "GET"), retries=1))

    assert result.payload == {"ok": True}
    assert len(opener.requests) == RETRIED_REQUEST_COUNT
    assert stream.read_sizes == []
    assert stream.closed
    assert sleeps == [0.0]


@pytest.mark.parametrize("module", PROVIDERS, ids=provider_name)
def test_get_does_not_inherit_every_ambiguous_write_status(
    monkeypatch: pytest.MonkeyPatch,
    module: ModuleType,
) -> None:
    """The broad write-ambiguity range does not silently broaden automatic GET retries."""
    failure, stream = recording_http_failure(f"{provider_base_url(module)}/items", 599)
    opener = install_opener(monkeypatch, [failure, FakeResponse(b'{"unexpected":true}')])
    sleeps: list[float] = []
    monkeypatch.setattr(time, "sleep", sleeps.append)
    plan = provider_plan(module, "GET")

    with pytest.raises(provider_error(module), match="599"):
        _ = send(module, plan, retries=5)

    assert len(opener.requests) == 1
    assert sleeps == []
    assert stream.closed


@pytest.mark.parametrize("module", PROVIDERS, ids=provider_name)
def test_get_retries_url_errors(monkeypatch: pytest.MonkeyPatch, module: ModuleType) -> None:
    """GET requests retain bounded retry behavior for transport failures."""
    content_type = "application/json" if module is SOCKET else "application/vnd.api+json"
    opener = install_opener(
        monkeypatch,
        [
            error.URLError(TimeoutError("timed out")),
            FakeResponse(b'{"ok":true}', headers={"Content-Type": content_type}),
        ],
    )
    sleeps: list[float] = []
    monkeypatch.setattr(time, "sleep", sleeps.append)

    result = cast("ApiResultView", send(module, provider_plan(module, "GET"), retries=1))

    assert result.payload == {"ok": True}
    assert len(opener.requests) == RETRIED_REQUEST_COUNT
    assert sleeps == [1.0]


@pytest.mark.parametrize("status", AMBIGUOUS_WRITE_STATUS_CODES)
@pytest.mark.parametrize("method", WRITE_METHODS)
@pytest.mark.parametrize("module", PROVIDERS, ids=provider_name)
def test_writes_are_single_attempt_with_indeterminate_http_outcome(
    monkeypatch: pytest.MonkeyPatch,
    module: ModuleType,
    method: str,
    status: int,
) -> None:
    """Retryable HTTP failures never replay a potentially applied write."""
    base_url = SOCKET_BASE_URL if module is SOCKET else SNYK_BASE_URL
    failure, stream = recording_http_failure(f"{base_url}/items", status)
    opener = install_opener(
        monkeypatch,
        [failure, FakeResponse(b'{"unexpected":true}')],
    )
    sleeps: list[float] = []
    monkeypatch.setattr(time, "sleep", sleeps.append)
    plan = provider_plan(module, method)

    with pytest.raises(provider_error(module), match=r"(?i)indeterminate") as captured:
        _ = send(module, plan, retries=5)

    message = str(captured.value)
    assert str(status) in message
    assert "verify" in message.casefold()
    assert len(opener.requests) == 1
    assert sleeps == []
    assert stream.closed


@pytest.mark.parametrize("method", WRITE_METHODS)
@pytest.mark.parametrize("module", PROVIDERS, ids=provider_name)
def test_writes_are_single_attempt_with_indeterminate_transport_outcome(
    monkeypatch: pytest.MonkeyPatch,
    module: ModuleType,
    method: str,
) -> None:
    """Transport failures never replay a write whose server outcome is unknown."""
    helper_error_name = "SocketCliError" if module is SOCKET else "SnykCliError"
    helper_error = cast("type[Exception]", member(module, helper_error_name))
    opener = install_opener(
        monkeypatch,
        [error.URLError(TimeoutError("timed out")), FakeResponse(b'{"unexpected":true}')],
    )
    sleeps: list[float] = []
    monkeypatch.setattr(time, "sleep", sleeps.append)
    plan = provider_plan(module, method)

    with pytest.raises(helper_error, match=r"(?i)indeterminate"):
        _ = send(module, plan, retries=5)

    assert len(opener.requests) == 1
    assert sleeps == []


@pytest.mark.parametrize("method", WRITE_METHODS)
@pytest.mark.parametrize("module", PROVIDERS, ids=provider_name)
def test_retryable_write_with_malformed_json_is_still_indeterminate(
    monkeypatch: pytest.MonkeyPatch,
    module: ModuleType,
    method: str,
) -> None:
    """Malformed error JSON cannot hide an indeterminate retryable write outcome."""
    base_url = SOCKET_BASE_URL if module is SOCKET else SNYK_BASE_URL
    helper_error_name = "SocketCliError" if module is SOCKET else "SnykCliError"
    helper_error = cast("type[Exception]", member(module, helper_error_name))
    opener = install_opener(
        monkeypatch,
        [http_failure(f"{base_url}/items", 503, b"{"), FakeResponse(b'{"unexpected":true}')],
    )
    plan = provider_plan(module, method)

    with pytest.raises(helper_error, match=r"(?i)indeterminate"):
        _ = send(module, plan, retries=5)

    assert len(opener.requests) == 1


def test_snyk_delete_204_returns_none_payload_and_status(monkeypatch: pytest.MonkeyPatch) -> None:
    """A successful no-content DELETE is represented without JSON decoding failure."""
    opener = install_opener(
        monkeypatch,
        [FakeResponse(b"", status=HTTP_NO_CONTENT, headers={"Content-Type": "application/vnd.api+json"})],
    )

    result = cast("ApiResultView", send(SNYK, provider_plan(SNYK, "DELETE"), retries=3))

    assert result.payload is None
    assert result.status == HTTP_NO_CONTENT
    assert len(opener.requests) == 1


def test_snyk_rejects_malformed_nonempty_json(monkeypatch: pytest.MonkeyPatch) -> None:
    """No-content support does not make malformed nonempty JSON silently acceptable."""
    helper_error = cast("type[Exception]", member(SNYK, "SnykCliError"))
    opener = install_opener(
        monkeypatch,
        [FakeResponse(b"{", headers={"Content-Type": "application/vnd.api+json"})],
    )
    plan = provider_plan(SNYK, "GET")

    with pytest.raises(helper_error, match="malformed JSON"):
        _ = send(SNYK, plan, retries=0)

    assert len(opener.requests) == 1


@pytest.mark.parametrize("nonfinite", NONFINITE_JSON_VALUES)
@pytest.mark.parametrize("module", PROVIDERS, ids=provider_name)
def test_request_body_parsing_rejects_nonfinite_and_overflow_numbers(module: ModuleType, nonfinite: str) -> None:
    """Every request-body JSON parser rejects constants and exponents that become nonfinite."""
    load_body = cast("Callable[[argparse.Namespace], JsonValue]", member(module, "load_body"))
    arguments = argparse.Namespace(body_file=None, body_json=f'{{"value":{nonfinite}}}')

    with pytest.raises(provider_error(module), match=r"(?i)(json|finite)"):
        _ = load_body(arguments)


@pytest.mark.parametrize("nonfinite", NONFINITE_JSON_VALUES)
@pytest.mark.parametrize("module", PROVIDERS, ids=provider_name)
def test_local_openapi_parsing_rejects_nonfinite_and_overflow_numbers(
    tmp_path: Path,
    module: ModuleType,
    nonfinite: str,
) -> None:
    """Local specifications use the same strict numeric JSON contract."""
    spec_file = tmp_path / f"{provider_name(module)}-nonfinite-openapi.json"
    _ = spec_file.write_text(f'{{"paths":{{}},"value":{nonfinite}}}', encoding="utf-8")
    load_openapi = cast("Callable[..., tuple[dict[str, JsonValue], str]]", member(module, "load_openapi"))
    arguments = argparse.Namespace(spec_file=spec_file, spec_url=None, timeout=1.0)
    context = provider_context(module)

    with pytest.raises(provider_error(module), match=r"(?i)(json|finite|parse)"):
        _ = load_openapi(arguments, context)


@pytest.mark.parametrize("nonfinite", NONFINITE_JSON_VALUES)
@pytest.mark.parametrize("module", PROVIDERS, ids=provider_name)
def test_success_json_responses_reject_nonfinite_and_overflow_numbers(
    monkeypatch: pytest.MonkeyPatch,
    module: ModuleType,
    nonfinite: str,
) -> None:
    """Successful JSON responses cannot construct nonfinite Python floats."""
    response = FakeResponse(
        f'{{"value":{nonfinite}}}'.encode(),
        headers={"Content-Type": provider_content_type(module)},
    )
    _ = install_opener(monkeypatch, [response])
    plan = provider_plan(module, "GET")

    with pytest.raises(provider_error(module), match=r"(?i)(json|finite)"):
        _ = send(module, plan, retries=0)

    assert response.closed


@pytest.mark.parametrize("module", PROVIDERS, ids=provider_name)
def test_request_serialization_rejects_nonfinite_values_before_network(
    monkeypatch: pytest.MonkeyPatch,
    module: ModuleType,
) -> None:
    """A programmatically forged nonfinite body fails strict encoding before any request."""
    opener = install_opener(monkeypatch, [FakeResponse(b'{"unexpected":true}')])
    plan = provider_plan_with_body(module, "POST", {"value": math.nan})

    with pytest.raises(provider_error(module), match=r"(?i)(json|finite)"):
        _ = send(module, plan, retries=0)

    assert opener.requests == []


@pytest.mark.parametrize("module", PROVIDERS, ids=provider_name)
def test_json_output_serialization_is_strict_and_atomic(
    capsys: pytest.CaptureFixture[str],
    module: ModuleType,
) -> None:
    """Output serialization fails before writing any prefix when a value is nonfinite."""
    write_json = cast("Callable[..., None]", member(module, "write_json"))
    keywords = {"prefix": "[untrusted-socket-data]\n"} if module is SOCKET else {}

    with pytest.raises(provider_error(module), match=r"(?i)(json|finite)"):
        write_json({"value": math.inf}, **keywords)

    captured = capsys.readouterr()
    assert captured.out == ""


@pytest.mark.parametrize(
    ("payload", "content_type"),
    [(b"", "application/vnd.api+json"), (b"plain", "text/plain")],
    ids=("empty", "plain-text"),
)
def test_snyk_200_requires_nonempty_strict_json(
    monkeypatch: pytest.MonkeyPatch,
    payload: bytes,
    content_type: str,
) -> None:
    """A successful ordinary REST response cannot be empty or fall back to plain text."""
    response = FakeResponse(payload, headers={"Content-Type": content_type})
    _ = install_opener(monkeypatch, [response])
    plan = provider_plan(SNYK, "GET")

    with pytest.raises(provider_error(SNYK), match=r"(?i)(HTTP 200|JSON|empty)"):
        _ = send(SNYK, plan, retries=0)

    assert response.closed


def test_snyk_nonempty_success_parses_json_regardless_of_content_type(monkeypatch: pytest.MonkeyPatch) -> None:
    """Snyk does not use a text fallback when valid JSON arrives with an incorrect media type."""
    response = FakeResponse(b'{"data":[]}', headers={"Content-Type": "text/plain"})
    _ = install_opener(monkeypatch, [response])

    result = cast("ApiResultView", send(SNYK, provider_plan(SNYK, "GET"), retries=0))

    assert result.payload == {"data": []}
    assert result.status == HTTP_OK
    assert response.closed


def test_snyk_204_nonempty_valid_json_is_parsed(monkeypatch: pytest.MonkeyPatch) -> None:
    """The 204 empty-body exception does not bypass parsing of a body that is actually present."""
    response = FakeResponse(
        b'{"meta":{"acknowledged":true}}',
        status=HTTP_NO_CONTENT,
        headers={"Content-Type": "text/plain"},
    )
    _ = install_opener(monkeypatch, [response])

    result = cast("ApiResultView", send(SNYK, provider_plan(SNYK, "DELETE"), retries=0))

    assert result.payload == {"meta": {"acknowledged": True}}
    assert result.status == HTTP_NO_CONTENT
    assert response.closed


def test_snyk_204_nonempty_malformed_json_is_indeterminate(monkeypatch: pytest.MonkeyPatch) -> None:
    """Malformed bytes after a successful DELETE retain status and write-ambiguity guidance."""
    response = FakeResponse(b"plain", status=HTTP_NO_CONTENT, headers={"Content-Type": "text/plain"})
    opener = install_opener(monkeypatch, [response, FakeResponse(b'{"unexpected":true}')])
    plan = provider_plan(SNYK, "DELETE")

    with pytest.raises(provider_error(SNYK), match=r"(?i)indeterminate") as captured:
        _ = send(SNYK, plan, retries=5)

    message = str(captured.value)
    assert "204" in message
    assert "verify" in message.casefold()
    assert len(opener.requests) == 1
    assert response.closed


@pytest.mark.parametrize("failure_kind", ["read", "oversized", "malformed", "empty"])
@pytest.mark.parametrize("method", WRITE_METHODS)
@pytest.mark.parametrize("module", PROVIDERS, ids=provider_name)
def test_post_success_write_response_failures_are_indeterminate_with_known_status(
    monkeypatch: pytest.MonkeyPatch,
    module: ModuleType,
    method: str,
    failure_kind: str,
) -> None:
    """Read, size, decode, and invalid-empty failures after 2xx never invite blind write replay."""
    status = 201
    headers = {"Content-Type": provider_content_type(module)}
    if failure_kind == "read":
        response: FakeResponse = ReadFailureResponse(b"", status=status, headers=headers)
    elif failure_kind == "oversized":
        monkeypatch.setattr(module, "MAX_API_RESPONSE_BYTES", 8)
        response = FakeResponse(b"123456789", status=status, headers=headers)
    elif failure_kind == "malformed":
        response = FakeResponse(b"{", status=status, headers=headers)
    else:
        response = FakeResponse(b"", status=status, headers=headers)
    opener = install_opener(monkeypatch, [response, FakeResponse(b'{"unexpected":true}')])
    plan = provider_plan(module, method)

    with pytest.raises(provider_error(module), match=r"(?i)indeterminate") as captured:
        _ = send(module, plan, retries=5)

    message = str(captured.value)
    assert str(status) in message
    assert "verify" in message.casefold()
    assert len(opener.requests) == 1
    assert response.closed


@pytest.mark.parametrize("module", PROVIDERS, ids=provider_name)
def test_success_body_accepts_exact_boundary_and_tracks_bytes(
    monkeypatch: pytest.MonkeyPatch,
    module: ModuleType,
) -> None:
    """A boundary-sized success uses a limit-plus-one read and records actual bytes."""
    limit = 8
    monkeypatch.setattr(module, "MAX_API_RESPONSE_BYTES", limit)
    response = FakeResponse(
        b'{"a":1} ',
        headers={"Content-Type": provider_content_type(module), "Content-Length": str(limit)},
    )
    _ = install_opener(monkeypatch, [response])

    result = cast("ApiResultView", send(module, provider_plan(module, "GET"), retries=0))

    assert result.payload == {"a": 1}
    assert result.response_bytes == limit
    assert response.read_sizes == [limit + 1]
    assert response.closed


@pytest.mark.parametrize(
    "content_length",
    [None, "malformed", "1"],
    ids=("absent", "malformed", "understated"),
)
@pytest.mark.parametrize("module", PROVIDERS, ids=provider_name)
def test_success_body_rejects_actual_one_over_regardless_of_content_length(
    monkeypatch: pytest.MonkeyPatch,
    module: ModuleType,
    content_length: str | None,
) -> None:
    """Absent, malformed, or dishonest lengths cannot bypass actual-byte bounds."""
    limit = 8
    monkeypatch.setattr(module, "MAX_API_RESPONSE_BYTES", limit)
    headers = {"Content-Type": "text/plain"}
    if content_length is not None:
        headers["Content-Length"] = content_length
    response = FakeResponse(b"123456789", headers=headers)
    _ = install_opener(monkeypatch, [response])
    plan = provider_plan(module, "GET")

    with pytest.raises(provider_error(module), match=rf"{limit}-byte safety limit"):
        _ = send(module, plan, retries=0)

    assert response.read_sizes == [limit + 1]
    assert response.closed


@pytest.mark.parametrize("module", PROVIDERS, ids=provider_name)
def test_success_body_rejects_oversized_numeric_content_length_before_read(
    monkeypatch: pytest.MonkeyPatch,
    module: ModuleType,
) -> None:
    """A trustworthy oversized declaration rejects before reading the body."""
    limit = 8
    monkeypatch.setattr(module, "MAX_API_RESPONSE_BYTES", limit)
    response = FakeResponse(b"{}", headers={"Content-Type": "application/json", "Content-Length": "9"})
    _ = install_opener(monkeypatch, [response])
    plan = provider_plan(module, "GET")

    with pytest.raises(provider_error(module), match=rf"{limit}-byte safety limit"):
        _ = send(module, plan, retries=0)

    assert response.read_sizes == []
    assert response.closed


@pytest.mark.parametrize("module", PROVIDERS, ids=provider_name)
def test_duplicate_content_lengths_are_not_trusted_for_early_rejection(
    monkeypatch: pytest.MonkeyPatch,
    module: ModuleType,
) -> None:
    """Conflicting duplicate lengths cannot reject a body that meets the actual-byte limit."""
    limit = 8
    monkeypatch.setattr(module, "MAX_API_RESPONSE_BYTES", limit)
    response = FakeResponse(b'{"a":1} ', headers={"Content-Type": provider_content_type(module)})
    response.headers["Content-Length"] = str(limit + 1)
    response.headers["Content-Length"] = str(limit)
    _ = install_opener(monkeypatch, [response])

    result = cast("ApiResultView", send(module, provider_plan(module, "GET"), retries=0))

    assert result.payload == {"a": 1}
    assert result.response_bytes == limit
    assert response.read_sizes == [limit + 1]
    assert response.closed


@pytest.mark.parametrize("module", PROVIDERS, ids=provider_name)
def test_error_body_accepts_exact_boundary_read_and_closes(
    monkeypatch: pytest.MonkeyPatch,
    module: ModuleType,
) -> None:
    """A boundary-sized HTTP error is bounded, reported, and always closed."""
    limit = 8
    monkeypatch.setattr(module, "MAX_ERROR_RESPONSE_BYTES", limit)
    failure, stream = recording_http_failure(
        f"{provider_base_url(module)}/items",
        400,
        b"12345678",
        content_length=str(limit),
        content_type="text/plain",
    )
    _ = install_opener(monkeypatch, [failure])
    plan = provider_plan(module, "GET")

    with pytest.raises(provider_error(module), match="HTTP 400"):
        _ = send(module, plan, retries=0)

    assert stream.read_sizes == [limit + 1]
    assert stream.closed


@pytest.mark.parametrize(
    "content_length",
    [None, "malformed", "1"],
    ids=("absent", "malformed", "understated"),
)
@pytest.mark.parametrize("module", PROVIDERS, ids=provider_name)
def test_error_body_rejects_actual_one_over_regardless_of_content_length(
    monkeypatch: pytest.MonkeyPatch,
    module: ModuleType,
    content_length: str | None,
) -> None:
    """Actual error bytes enforce the cap despite absent or dishonest declarations."""
    limit = 8
    monkeypatch.setattr(module, "MAX_ERROR_RESPONSE_BYTES", limit)
    failure, stream = recording_http_failure(
        f"{provider_base_url(module)}/items",
        400,
        b"123456789",
        content_length=content_length,
        content_type="text/plain",
    )
    _ = install_opener(monkeypatch, [failure])
    plan = provider_plan(module, "GET")

    with pytest.raises(provider_error(module), match=rf"{limit}-byte safety limit"):
        _ = send(module, plan, retries=0)

    assert stream.read_sizes == [limit + 1]
    assert stream.closed


@pytest.mark.parametrize("module", PROVIDERS, ids=provider_name)
def test_error_body_rejects_oversized_numeric_content_length_before_read(
    monkeypatch: pytest.MonkeyPatch,
    module: ModuleType,
) -> None:
    """A trustworthy oversized error declaration rejects before body allocation."""
    limit = 8
    monkeypatch.setattr(module, "MAX_ERROR_RESPONSE_BYTES", limit)
    failure, stream = recording_http_failure(
        f"{provider_base_url(module)}/items",
        400,
        b"{}",
        content_length="9",
    )
    _ = install_opener(monkeypatch, [failure])
    plan = provider_plan(module, "GET")

    with pytest.raises(provider_error(module), match=rf"{limit}-byte safety limit"):
        _ = send(module, plan, retries=0)

    assert stream.read_sizes == []
    assert stream.closed


@pytest.mark.parametrize("method", WRITE_METHODS)
@pytest.mark.parametrize("module", PROVIDERS, ids=provider_name)
def test_retryable_write_error_body_overflow_remains_indeterminate(
    monkeypatch: pytest.MonkeyPatch,
    module: ModuleType,
    method: str,
) -> None:
    """A bounded oversized write error still reports the remote outcome as unknown."""
    limit = 8
    monkeypatch.setattr(module, "MAX_ERROR_RESPONSE_BYTES", limit)
    failure, stream = recording_http_failure(
        f"{provider_base_url(module)}/items",
        503,
        b"123456789",
        content_type="text/plain",
    )
    opener = install_opener(monkeypatch, [failure, FakeResponse(b'{"unexpected":true}')])
    plan = provider_plan(module, method)

    with pytest.raises(provider_error(module), match=r"(?i)indeterminate") as captured:
        _ = send(module, plan, retries=5)

    assert "123456789" not in str(captured.value)
    assert len(opener.requests) == 1
    assert stream.read_sizes == [limit + 1]
    assert stream.closed


@pytest.mark.parametrize("module", PROVIDERS, ids=provider_name)
def test_local_openapi_accepts_exact_boundary_and_rejects_one_over(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    module: ModuleType,
) -> None:
    """Local OpenAPI files are read through an actual-byte limit-plus-one boundary."""
    body = b'{"paths":{}}'
    limit = len(body)
    monkeypatch.setattr(module, "MAX_LOCAL_SPEC_BYTES", limit)
    load_openapi = cast("Callable[..., tuple[dict[str, JsonValue], str]]", member(module, "load_openapi"))
    spec_file = tmp_path / f"{provider_name(module)}-openapi.json"
    _ = spec_file.write_bytes(body)
    arguments = argparse.Namespace(spec_file=spec_file, spec_url=None, timeout=1.0)
    context = provider_context(module)

    payload, source = load_openapi(arguments, context)

    assert payload == {"paths": {}}
    assert source == str(spec_file)

    _ = spec_file.write_bytes(body + b" ")
    with pytest.raises(provider_error(module), match=rf"{limit}-byte safety limit"):
        _ = load_openapi(arguments, context)


@pytest.mark.parametrize("module", PROVIDERS, ids=provider_name)
def test_remote_openapi_accepts_exact_boundary_and_closes(
    monkeypatch: pytest.MonkeyPatch,
    module: ModuleType,
) -> None:
    """A boundary-sized remote specification is read with limit plus one and closed."""
    body = b'{"paths":{}}'
    limit = len(body)
    monkeypatch.setattr(module, "MAX_REMOTE_SPEC_BYTES", limit)
    response = FakeResponse(body, headers={"Content-Type": "application/json", "Content-Length": str(limit)})
    _ = install_opener(monkeypatch, [response])
    load_openapi = cast("Callable[..., tuple[dict[str, JsonValue], str]]", member(module, "load_openapi"))
    arguments = argparse.Namespace(spec_file=None, spec_url=None, timeout=1.0)

    payload, _source = load_openapi(arguments, provider_context(module))

    assert payload == {"paths": {}}
    assert response.read_sizes == [limit + 1]
    assert response.closed


@pytest.mark.parametrize(
    "content_length",
    [None, "malformed", "1"],
    ids=("absent", "malformed", "understated"),
)
@pytest.mark.parametrize("module", PROVIDERS, ids=provider_name)
def test_remote_openapi_rejects_actual_one_over_regardless_of_content_length(
    monkeypatch: pytest.MonkeyPatch,
    module: ModuleType,
    content_length: str | None,
) -> None:
    """Remote spec actual bytes enforce the cap for untrustworthy declarations."""
    body = b'{"paths":{}}'
    limit = len(body)
    monkeypatch.setattr(module, "MAX_REMOTE_SPEC_BYTES", limit)
    headers = {"Content-Type": "application/json"}
    if content_length is not None:
        headers["Content-Length"] = content_length
    response = FakeResponse(body + b" ", headers=headers)
    _ = install_opener(monkeypatch, [response])
    load_openapi = cast("Callable[..., tuple[dict[str, JsonValue], str]]", member(module, "load_openapi"))
    arguments = argparse.Namespace(spec_file=None, spec_url=None, timeout=1.0)
    context = provider_context(module)

    with pytest.raises(provider_error(module), match=rf"{limit}-byte safety limit"):
        _ = load_openapi(arguments, context)

    assert response.read_sizes == [limit + 1]
    assert response.closed


@pytest.mark.parametrize("module", PROVIDERS, ids=provider_name)
def test_remote_openapi_rejects_oversized_numeric_content_length_before_read(
    monkeypatch: pytest.MonkeyPatch,
    module: ModuleType,
) -> None:
    """A trustworthy oversized remote spec declaration rejects before reading."""
    body = b'{"paths":{}}'
    limit = len(body)
    monkeypatch.setattr(module, "MAX_REMOTE_SPEC_BYTES", limit)
    response = FakeResponse(b"{}", headers={"Content-Type": "application/json", "Content-Length": str(limit + 1)})
    _ = install_opener(monkeypatch, [response])
    load_openapi = cast("Callable[..., tuple[dict[str, JsonValue], str]]", member(module, "load_openapi"))
    arguments = argparse.Namespace(spec_file=None, spec_url=None, timeout=1.0)
    context = provider_context(module)

    with pytest.raises(provider_error(module), match=rf"{limit}-byte safety limit"):
        _ = load_openapi(arguments, context)

    assert response.read_sizes == []
    assert response.closed


def snyk_versions_arguments() -> argparse.Namespace:
    """Build arguments for a deterministic Snyk version-catalog read."""
    return argparse.Namespace(
        api_version=SNYK_API_VERSION,
        auth_scheme="token",
        base_url=SNYK_BASE_URL,
        json=True,
        timeout=1.0,
        token_envs=[],
    )


def test_snyk_version_catalog_accepts_exact_boundary_and_closes(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The version catalog has its own exact actual-byte boundary."""
    body = b'["v"]'
    limit = len(body)
    monkeypatch.delenv("SNYK_TOKEN", raising=False)
    monkeypatch.delenv("SNYK_API_TOKEN", raising=False)
    monkeypatch.setattr(SNYK, "MAX_VERSION_RESPONSE_BYTES", limit)
    response = FakeResponse(body, headers={"Content-Type": "application/json", "Content-Length": str(limit)})
    _ = install_opener(monkeypatch, [response])
    handle_versions = cast("Callable[[argparse.Namespace], int]", member(SNYK, "handle_versions"))

    assert handle_versions(snyk_versions_arguments()) == 0
    assert '"versions": [' in capsys.readouterr().out
    assert response.read_sizes == [limit + 1]
    assert response.closed


@pytest.mark.parametrize(
    "content_length",
    [None, "malformed", "1"],
    ids=("absent", "malformed", "understated"),
)
def test_snyk_version_catalog_rejects_actual_one_over_regardless_of_content_length(
    monkeypatch: pytest.MonkeyPatch,
    content_length: str | None,
) -> None:
    """Version-catalog actual bytes defeat missing and dishonest declarations."""
    body = b'["v"]'
    limit = len(body)
    monkeypatch.delenv("SNYK_TOKEN", raising=False)
    monkeypatch.delenv("SNYK_API_TOKEN", raising=False)
    monkeypatch.setattr(SNYK, "MAX_VERSION_RESPONSE_BYTES", limit)
    headers = {"Content-Type": "application/json"}
    if content_length is not None:
        headers["Content-Length"] = content_length
    response = FakeResponse(body + b" ", headers=headers)
    _ = install_opener(monkeypatch, [response])
    handle_versions = cast("Callable[[argparse.Namespace], int]", member(SNYK, "handle_versions"))
    arguments = snyk_versions_arguments()

    with pytest.raises(provider_error(SNYK), match=rf"{limit}-byte safety limit"):
        _ = handle_versions(arguments)

    assert response.read_sizes == [limit + 1]
    assert response.closed


def test_snyk_version_catalog_rejects_oversized_numeric_content_length_before_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A trustworthy oversized version declaration rejects before reading."""
    body = b'["v"]'
    limit = len(body)
    monkeypatch.delenv("SNYK_TOKEN", raising=False)
    monkeypatch.delenv("SNYK_API_TOKEN", raising=False)
    monkeypatch.setattr(SNYK, "MAX_VERSION_RESPONSE_BYTES", limit)
    response = FakeResponse(b"[]", headers={"Content-Type": "application/json", "Content-Length": str(limit + 1)})
    _ = install_opener(monkeypatch, [response])
    handle_versions = cast("Callable[[argparse.Namespace], int]", member(SNYK, "handle_versions"))
    arguments = snyk_versions_arguments()

    with pytest.raises(provider_error(SNYK), match=rf"{limit}-byte safety limit"):
        _ = handle_versions(arguments)

    assert response.read_sizes == []
    assert response.closed


@pytest.mark.parametrize("nonfinite", NONFINITE_JSON_VALUES)
def test_snyk_version_catalog_rejects_nonfinite_and_overflow_numbers(
    monkeypatch: pytest.MonkeyPatch,
    nonfinite: str,
) -> None:
    """The public version document uses strict JSON before validating its array shape."""
    monkeypatch.delenv("SNYK_TOKEN", raising=False)
    monkeypatch.delenv("SNYK_API_TOKEN", raising=False)
    response = FakeResponse(f"[{nonfinite}]".encode(), headers={"Content-Type": "text/plain"})
    _ = install_opener(monkeypatch, [response])
    handle_versions = cast("Callable[[argparse.Namespace], int]", member(SNYK, "handle_versions"))
    arguments = snyk_versions_arguments()

    with pytest.raises(provider_error(SNYK), match=r"(?i)(json|finite)"):
        _ = handle_versions(arguments)

    assert response.closed


@pytest.mark.parametrize(
    "payload",
    [
        {"data": [1]},
        {"data": [1], "links": None},
        {"data": [1], "links": {}},
        {"data": [1], "links": {"next": None}},
    ],
    ids=("links-missing", "links-null", "next-missing", "next-null"),
)
def test_snyk_pagination_accepts_only_documented_terminal_shapes(
    monkeypatch: pytest.MonkeyPatch,
    payload: JsonValue,
) -> None:
    """Missing or null links/next values complete one page without a synthetic extra request."""
    calls = 0

    def fake_send(*_arguments: object, **_keywords: object) -> object:
        nonlocal calls
        calls += 1
        return provider_result(SNYK, payload, response_bytes=1)

    monkeypatch.setattr(SNYK, "send_request", fake_send)
    paginate = cast("Callable[..., object]", member(SNYK, "paginated_request"))
    result = cast(
        "ApiResultView",
        paginate(
            provider_context(SNYK),
            provider_plan(SNYK, "GET"),
            argparse.Namespace(max_pages=3, retries=0, timeout=1.0),
        ),
    )

    assert cast("dict[str, JsonValue]", result.payload)["data"] == [1]
    assert cast("dict[str, JsonValue]", result.payload)["links"] == {"next": None}
    assert calls == 1


@pytest.mark.parametrize("links", [False, 0, "next", []], ids=("false", "number", "string", "list"))
def test_snyk_pagination_rejects_present_nonmapping_links(
    monkeypatch: pytest.MonkeyPatch,
    links: JsonValue,
) -> None:
    """A present non-null links value is malformed, not an implicit terminal page."""
    calls = 0

    def fake_send(*_arguments: object, **_keywords: object) -> object:
        nonlocal calls
        calls += 1
        return provider_result(SNYK, {"data": [1], "links": links}, response_bytes=1)

    monkeypatch.setattr(SNYK, "send_request", fake_send)
    paginate = cast("Callable[..., object]", member(SNYK, "paginated_request"))
    context = provider_context(SNYK)
    plan = provider_plan(SNYK, "GET")
    arguments = argparse.Namespace(max_pages=3, retries=0, timeout=1.0)

    with pytest.raises(provider_error(SNYK), match=r"(?i)links.*(object|mapping|malformed)"):
        _ = paginate(context, plan, arguments)

    assert calls == 1


@pytest.mark.parametrize(
    "next_value",
    [False, 0, "", [], {}],
    ids=("false", "number", "empty-string", "list", "mapping"),
)
def test_snyk_pagination_rejects_malformed_nonnull_next(
    monkeypatch: pytest.MonkeyPatch,
    next_value: JsonValue,
) -> None:
    """Only a nonempty string or null is accepted when links.next is present."""
    calls = 0

    def fake_send(*_arguments: object, **_keywords: object) -> object:
        nonlocal calls
        calls += 1
        return provider_result(SNYK, {"data": [1], "links": {"next": next_value}}, response_bytes=1)

    monkeypatch.setattr(SNYK, "send_request", fake_send)
    paginate = cast("Callable[..., object]", member(SNYK, "paginated_request"))
    context = provider_context(SNYK)
    plan = provider_plan(SNYK, "GET")
    arguments = argparse.Namespace(max_pages=3, retries=0, timeout=1.0)

    with pytest.raises(provider_error(SNYK), match=r"(?i)links\.next.*non-empty string or null"):
        _ = paginate(context, plan, arguments)

    assert calls == 1


@pytest.mark.parametrize("overflow", [False, True], ids=("exact", "one-over"))
@pytest.mark.parametrize("module", PROVIDERS, ids=provider_name)
def test_pagination_enforces_cumulative_bytes_before_retaining_overflow_items(
    monkeypatch: pytest.MonkeyPatch,
    module: ModuleType,
    *,
    overflow: bool,
) -> None:
    """Cumulative overflow is rejected before merging the offending page's items."""
    cumulative_limit = 10
    monkeypatch.setattr(module, "MAX_PAGINATED_RESPONSE_BYTES", cumulative_limit)
    first_payload: JsonValue
    second_payload: JsonValue
    if module is SOCKET:
        first_payload = {"items": [1], "endCursor": "next"}
        second_payload = {
            "items": FailOnIterationList([2]) if overflow else [2],
            "endCursor": None,
        }
    else:
        first_payload = {
            "data": [1],
            "links": {"next": f"/rest/items?version={SNYK_API_VERSION}&starting_after=next"},
        }
        second_payload = {
            "data": FailOnIterationList([2]) if overflow else [2],
            "links": {"next": None},
        }
    responses = iter(
        (
            provider_result(module, first_payload, response_bytes=6 if overflow else 5),
            provider_result(module, second_payload, response_bytes=5),
        )
    )
    calls = 0

    def fake_send(*_arguments: object, **_keywords: object) -> object:
        nonlocal calls
        calls += 1
        return next(responses)

    monkeypatch.setattr(module, "send_request", fake_send)
    paginate = cast("Callable[..., object]", member(module, "paginated_request"))
    arguments = argparse.Namespace(max_pages=3, retries=0, timeout=1.0)
    context = provider_context(module)
    plan = provider_plan(module, "GET")

    if overflow:
        with pytest.raises(provider_error(module), match=rf"{cumulative_limit}-byte cumulative safety limit"):
            _ = paginate(context, plan, arguments)
    else:
        result = cast("ApiResultView", paginate(context, plan, arguments))
        assert result.response_bytes == cumulative_limit
        expected_key = "items" if module is SOCKET else "data"
        assert cast("dict[str, JsonValue]", result.payload)[expected_key] == [1, 2]

    assert calls == RETRIED_REQUEST_COUNT


def test_socket_repeated_cursor_fails_before_third_request_with_partial_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Socket detects a repeated opaque cursor before issuing another request."""
    responses = iter(
        (
            provider_result(SOCKET, {"items": [1], "endCursor": "repeat"}, response_bytes=1),
            provider_result(SOCKET, {"items": [2], "endCursor": "repeat"}, response_bytes=1),
        )
    )
    calls = 0

    def fake_send(*_arguments: object, **_keywords: object) -> object:
        nonlocal calls
        calls += 1
        return next(responses)

    monkeypatch.setattr(SOCKET, "send_request", fake_send)
    paginate = cast("Callable[..., object]", member(SOCKET, "paginated_request"))
    context = provider_context(SOCKET)
    plan = provider_plan(SOCKET, "GET")
    arguments = argparse.Namespace(max_pages=3, retries=0, timeout=1.0)

    with pytest.raises(provider_error(SOCKET), match=r"(?i)incomplete after 2 page\(s\).*repeated.*cursor"):
        _ = paginate(context, plan, arguments)

    assert calls == RETRIED_REQUEST_COUNT


def test_snyk_repeated_canonical_next_url_fails_before_third_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Snyk detects an equivalent reordered next URL before another request."""
    repeated_path = f"/rest/items?starting_after=repeat&version={SNYK_API_VERSION}"
    reordered_absolute = f"{SNYK_BASE_URL}/items?version={SNYK_API_VERSION}&starting_after=repeat"
    responses = iter(
        (
            provider_result(SNYK, {"data": [1], "links": {"next": repeated_path}}, response_bytes=1),
            provider_result(SNYK, {"data": [2], "links": {"next": reordered_absolute}}, response_bytes=1),
        )
    )
    calls = 0

    def fake_send(*_arguments: object, **_keywords: object) -> object:
        nonlocal calls
        calls += 1
        return next(responses)

    monkeypatch.setattr(SNYK, "send_request", fake_send)
    paginate = cast("Callable[..., object]", member(SNYK, "paginated_request"))
    context = provider_context(SNYK)
    plan = provider_plan(SNYK, "GET")
    arguments = argparse.Namespace(max_pages=3, retries=0, timeout=1.0)

    with pytest.raises(provider_error(SNYK), match=r"(?i)incomplete after 2 page\(s\).*repeated.*next"):
        _ = paginate(context, plan, arguments)

    assert calls == RETRIED_REQUEST_COUNT


def credential_bearing_reason(module: ModuleType) -> str:
    """Build a long synthetic transport reason containing several credential forms."""
    scheme = "Bearer" if module is SOCKET else "token"
    return " ".join(
        (
            f"Authorization: {scheme} {TEST_TOKEN}",
            f"active={TEST_TOKEN}",
            "url=https://reason-user:reason-password@example.invalid/callback?",
            "apiToken=external-query-secret&sessionId=external-session-secret&ok=1",
            "x" * 5000,
        )
    )


@pytest.mark.parametrize("module", PROVIDERS, ids=provider_name)
def test_transport_reason_redacts_scheme_wrapped_active_and_encoded_query_credentials(module: ModuleType) -> None:
    """A scheme-bearing active token also protects its bare credential and encoded query keys."""
    formatter_name = "safe_untrusted_reason" if module is SOCKET else "safe_reason"
    formatter = cast("Callable[[object, str | None], str]", member(module, formatter_name))
    bare_credential = "Tök/+/= scheme stripped"
    encoded_active = percent_triplets_with_case(parse.quote_plus(bare_credential, safe=""), mixed=True)
    query_credential = "percent-encoded-query-credential"

    formatted = formatter(
        " ".join(
            (
                f"bare={bare_credential}",
                f"active={encoded_active}",
                f"https://{encoded_active}@example.invalid/?api%54oken={query_credential}",
            )
        ),
        f"Bearer {bare_credential}",
    )

    assert bare_credential not in formatted
    assert encoded_active not in formatted
    assert query_credential not in formatted
    assert "<redacted>" in formatted


@pytest.mark.parametrize("method", ["GET", *WRITE_METHODS])
@pytest.mark.parametrize("failure_kind", TRANSPORT_FAILURE_KINDS)
@pytest.mark.parametrize("module", PROVIDERS, ids=provider_name)
def test_transport_reasons_are_bounded_redacted_and_keep_write_indeterminacy(
    monkeypatch: pytest.MonkeyPatch,
    module: ModuleType,
    failure_kind: str,
    method: str,
) -> None:
    """Long GET/write transport reasons cannot leak known or URL credentials."""
    reason = credential_bearing_reason(module)
    opener = install_opener(
        monkeypatch,
        [transport_failure(failure_kind, reason), FakeResponse(b'{"unexpected":true}')],
    )
    plan = provider_plan(module, method)
    retries = 5 if method != "GET" else 0

    with pytest.raises(provider_error(module)) as captured:
        _ = send(module, plan, retries=retries)

    message = str(captured.value)
    scheme = "Bearer" if module is SOCKET else "token"
    assert TEST_TOKEN not in message
    assert f"{scheme} {TEST_TOKEN}" not in message
    assert "reason-user" not in message
    assert "reason-password" not in message
    assert "external-query-secret" not in message
    assert "external-session-secret" not in message
    assert len(message) <= integer_constant(module, "MAX_UNTRUSTED_REASON_TEXT") + 500
    assert ("indeterminate" in message.casefold()) is (method != "GET")
    assert len(opener.requests) == 1


@pytest.mark.parametrize("module", PROVIDERS, ids=provider_name)
def test_openapi_transport_reasons_are_bounded_and_redacted(
    monkeypatch: pytest.MonkeyPatch,
    module: ModuleType,
) -> None:
    """OpenAPI fetch failures use the same safe transport-reason formatter."""
    _ = install_opener(monkeypatch, [error.URLError(credential_bearing_reason(module))])
    load_openapi = cast("Callable[..., tuple[dict[str, JsonValue], str]]", member(module, "load_openapi"))
    arguments = argparse.Namespace(spec_file=None, spec_url=None, timeout=1.0)
    context = provider_context(module)

    with pytest.raises(provider_error(module)) as captured:
        _ = load_openapi(arguments, context)

    message = str(captured.value)
    assert TEST_TOKEN not in message
    assert "reason-user" not in message
    assert "reason-password" not in message
    assert "external-query-secret" not in message
    assert "external-session-secret" not in message
    assert len(message) <= integer_constant(module, "MAX_UNTRUSTED_REASON_TEXT") + 300


@pytest.mark.parametrize("module", PROVIDERS, ids=provider_name)
def test_openapi_http_error_read_reasons_are_closed_bounded_and_redacted(
    monkeypatch: pytest.MonkeyPatch,
    module: ModuleType,
) -> None:
    """An unreadable OpenAPI HTTP error body cannot bypass safe formatting or closure."""
    reason = credential_bearing_reason(module)
    stream = ReadFailureStream(reason)
    spec_url = f"{SOCKET_BASE_URL}/openapi" if module is SOCKET else f"{SNYK_BASE_URL}/openapi/{SNYK_API_VERSION}"
    failure = error.HTTPError(
        spec_url,
        500,
        "fixture failure",
        http_headers({"Content-Type": "text/plain"}),
        stream,
    )
    _ = install_opener(monkeypatch, [failure])
    load_openapi = cast("Callable[..., tuple[dict[str, JsonValue], str]]", member(module, "load_openapi"))
    arguments = argparse.Namespace(spec_file=None, spec_url=None, timeout=1.0)
    context = provider_context(module)

    with pytest.raises(provider_error(module)) as captured:
        _ = load_openapi(arguments, context)

    message = str(captured.value)
    assert TEST_TOKEN not in message
    assert "reason-user" not in message
    assert "reason-password" not in message
    assert "external-query-secret" not in message
    assert "external-session-secret" not in message
    assert len(message) <= integer_constant(module, "MAX_UNTRUSTED_REASON_TEXT") + 300
    assert stream.closed


def test_snyk_version_transport_reason_is_bounded_and_redacted(monkeypatch: pytest.MonkeyPatch) -> None:
    """The public Snyk version catalog cannot echo ambient credential material."""
    monkeypatch.setenv("SNYK_TOKEN", TEST_TOKEN)
    _ = install_opener(monkeypatch, [error.URLError(credential_bearing_reason(SNYK))])
    handle_versions = cast("Callable[[argparse.Namespace], int]", member(SNYK, "handle_versions"))
    arguments = snyk_versions_arguments()

    with pytest.raises(provider_error(SNYK)) as captured:
        _ = handle_versions(arguments)

    message = str(captured.value)
    assert TEST_TOKEN not in message
    assert "reason-user" not in message
    assert "reason-password" not in message
    assert "external-query-secret" not in message
    assert "external-session-secret" not in message
    assert len(message) <= integer_constant(SNYK, "MAX_UNTRUSTED_REASON_TEXT") + 300


@pytest.mark.parametrize("retry_after", ["", "invalid", "NaN", "Infinity", "-Infinity", "-1", "1e309"])
@pytest.mark.parametrize("module", PROVIDERS, ids=provider_name)
def test_retry_delay_is_finite_capped_and_overflow_safe(module: ModuleType, retry_after: str) -> None:
    """Invalid Retry-After and huge attempts use finite capped fallback delays."""
    function_name = "parse_retry_after" if module is SOCKET else "retry_delay"
    retry_delay = cast("Callable[[error.HTTPError, int], float]", member(module, function_name))
    headers = Message()
    if retry_after:
        headers["Retry-After"] = retry_after
    failure = error.HTTPError(
        f"{provider_base_url(module)}/items",
        429,
        "retry",
        headers,
        BytesIO(),
    )
    try:
        delay = retry_delay(failure, 100_000)
    finally:
        failure.close()

    assert math.isfinite(delay)
    assert 0.0 <= delay <= float_constant(module, "MAX_RETRY_DELAY_SECONDS")


@pytest.mark.parametrize("module", PROVIDERS, ids=provider_name)
def test_retry_after_above_cap_is_bounded(module: ModuleType) -> None:
    """A valid finite Retry-After cannot exceed the documented delay cap."""
    function_name = "parse_retry_after" if module is SOCKET else "retry_delay"
    retry_delay = cast("Callable[[error.HTTPError, int], float]", member(module, function_name))
    headers = Message()
    headers["Retry-After"] = "3600"
    failure = error.HTTPError(f"{provider_base_url(module)}/items", 429, "retry", headers, BytesIO())
    try:
        delay = retry_delay(failure, 0)
    finally:
        failure.close()

    assert delay == float_constant(module, "MAX_RETRY_DELAY_SECONDS")


def validation_arguments(*, max_pages: int = 1, retries: int = 0, timeout: float = 1.0) -> argparse.Namespace:
    """Build the shared numeric-control validation shape."""
    return argparse.Namespace(
        command="request",
        dry_run=False,
        max_pages=max_pages,
        retries=retries,
        send=False,
        timeout=timeout,
    )


@pytest.mark.parametrize("timeout", [0.0, -1.0, math.nan, math.inf, -math.inf])
@pytest.mark.parametrize("module", PROVIDERS, ids=provider_name)
def test_nonpositive_and_nonfinite_timeouts_are_rejected_directly(module: ModuleType, timeout: float) -> None:
    """NaN and infinities cannot bypass direct timeout validation."""
    validate = cast("Callable[[argparse.Namespace], None]", member(module, "validate_arguments"))
    arguments = validation_arguments(timeout=timeout)

    with pytest.raises(provider_error(module), match=r"(?i)finite.*greater than zero"):
        validate(arguments)


@pytest.mark.parametrize(
    ("name", "value"),
    [("retries", -1), ("retries", 11), ("max_pages", 0), ("max_pages", 1001)],
)
@pytest.mark.parametrize("module", PROVIDERS, ids=provider_name)
def test_retry_and_page_caps_reject_out_of_range_values_directly(
    module: ModuleType,
    name: str,
    value: int,
) -> None:
    """Direct validation enforces both lower and documented upper bounds."""
    validate = cast("Callable[[argparse.Namespace], None]", member(module, "validate_arguments"))
    max_pages = value if name == "max_pages" else 1
    retries = value if name == "retries" else 0
    arguments = validation_arguments(max_pages=max_pages, retries=retries)
    match = rf"--{name.replace('_', '-')}.*between"

    with pytest.raises(provider_error(module), match=match):
        validate(arguments)


@pytest.mark.parametrize("module", PROVIDERS, ids=provider_name)
def test_numeric_control_upper_boundaries_are_accepted_directly(module: ModuleType) -> None:
    """The exact documented retry and page caps remain usable."""
    validate = cast("Callable[[argparse.Namespace], None]", member(module, "validate_arguments"))
    validate(validation_arguments(max_pages=1000, retries=10, timeout=1.0))


@pytest.mark.parametrize("timeout", ["NaN", "Infinity", "-Infinity"])
@pytest.mark.parametrize("module", PROVIDERS, ids=provider_name)
def test_nonfinite_timeouts_are_safe_subprocess_errors(module: ModuleType, timeout: str) -> None:
    """CLI timeout validation rejects nonfinite values before any network I/O."""
    result = run_script(module, "request", "/items", "--dry-run", f"--timeout={timeout}")

    assert result.returncode == 1
    assert "finite" in result.stderr.casefold()
    assert "Traceback" not in result.stderr


@pytest.mark.parametrize(
    ("option", "value"),
    [("--retries", "11"), ("--max-pages", "1001")],
)
@pytest.mark.parametrize("module", PROVIDERS, ids=provider_name)
def test_overcap_controls_are_safe_subprocess_errors(module: ModuleType, option: str, value: str) -> None:
    """CLI retry and page overcaps fail cleanly without executing a request."""
    result = run_script(module, "request", "/items", "--dry-run", option, value)

    assert result.returncode == 1
    assert "between" in result.stderr
    assert "Traceback" not in result.stderr


@pytest.mark.parametrize("module", PROVIDERS, ids=provider_name)
def test_control_caps_are_accepted_in_subprocess_preview(module: ModuleType) -> None:
    """Exact retry/page caps remain valid in a real CLI preview."""
    result = run_script(
        module,
        "request",
        "/items",
        "--dry-run",
        "--timeout",
        "1",
        "--retries",
        "10",
        "--max-pages",
        "1000",
    )

    assert result.returncode == 0, result.stderr
    assert "Traceback" not in result.stderr
