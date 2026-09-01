#!/usr/bin/env python
# Copyright (c) 2026 Nick2bad4u
"""Discover UptimeRobot API v3 operations and execute guarded requests."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import sys
import time
from contextlib import suppress
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from http.client import HTTPException, IncompleteRead
from pathlib import Path
from typing import TYPE_CHECKING, Never, Protocol, Self, cast, override
from urllib import error, parse, request

if TYPE_CHECKING:
    from http.client import HTTPMessage
    from types import TracebackType
    from typing import IO

type JsonValue = bool | int | float | str | list[JsonValue] | dict[str, JsonValue] | None
type QueryPairs = tuple[tuple[str, str], ...]

DEFAULT_BASE_URL = "https://api.uptimerobot.com/v3"
DEFAULT_SPEC_URL = "https://cdn.uptimerobot.com/api/openapi.yaml"
DEFAULT_READ_TOKEN_ENVS = ("UPTIMEROBOT_READ_ONLY_API_KEY",)
DEFAULT_MAIN_TOKEN_ENVS = ("UPTIMEROBOT_API_KEY",)
DEFAULT_TIMEOUT = 30.0
DEFAULT_RETRIES = 2
DEFAULT_MAX_PAGES = 25
MAX_TIMEOUT = 300.0
MAX_MAX_PAGES = 500
MAX_RESPONSE_TEXT = 2000
MAX_REQUEST_BODY_BYTES = 2 * 1024 * 1024
MAX_REQUEST_JSON_DEPTH = 64
MAX_REQUEST_JSON_NODES = 100_000
MAX_REQUEST_JSON_STRING_CHARS = 1_000_000
MAX_API_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_RESPONSE_JSON_DEPTH = 64
MAX_RESPONSE_JSON_NODES = 250_000
MAX_RESPONSE_JSON_STRING_CHARS = 4 * 1024 * 1024
MAX_ERROR_RESPONSE_BYTES = 16 * 1024
MAX_OPENAPI_BYTES = 16 * 1024 * 1024
MAX_PAGINATED_RESPONSE_BYTES = 32 * 1024 * 1024
MAX_TRANSPORT_ERROR_TEXT = 1000
MAX_SECRET_DECODE_ROUNDS = 3
MIN_CREDENTIAL_LENGTH = 8
MIN_QUOTED_SCALAR_LENGTH = 2
MAX_RETRY_AFTER_LENGTH = 128
MAX_RETRY_AFTER_DELTA_DIGITS = 2
MAX_RETRY_DELAY = 60.0
ASCII_CONTROL_LIMIT = 32
ASCII_DELETE = 127
JSON_MEDIA_TYPE = "application/json"
REDACTED_VALUE = "<redacted>"
HTTP_SUCCESS_MIN = 200
HTTP_SUCCESS_LIMIT = 300
RETRYABLE_GET_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
INDETERMINATE_MUTATION_STATUS_CODES = frozenset({500, 502, 503, 504})
SAFE_METHODS = frozenset({"GET", "HEAD"})
HTTP_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE")
YAML_HTTP_METHODS = frozenset(item.lower() for item in HTTP_METHODS)
PATH_PARAMETER = re.compile(r"\{([^{}]+)\}")
PERCENT_ESCAPE = re.compile(r"%[0-9A-Fa-f]{2}")
CAMEL_CASE_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
ACRONYM_BOUNDARY = re.compile(r"(?<=[A-Z])(?=[A-Z][a-z])")
KEY_TOKEN = re.compile(r"[A-Za-z0-9]+")
SENSITIVE_KEY_EXACT_NORMALIZED = frozenset({"credentialenvironment"})
SENSITIVE_KEY_SUFFIXES = (
    ("api", "key"),
    ("authorization",),
    ("authorization", "header"),
    ("cookie",),
    ("credential",),
    ("custom", "headers"),
    ("custom", "http", "headers"),
    ("http", "password"),
    ("passphrase",),
    ("password",),
    ("ping", "url"),
    ("post", "value"),
    ("post", "value", "data"),
    ("private", "key"),
    ("request", "headers"),
    ("response", "headers"),
    ("secret",),
    ("set", "cookie"),
    ("token",),
    ("url", "to", "notify"),
    ("webhook", "url"),
)
SENSITIVE_CONTAINER_TOKEN_SEQUENCES = frozenset({("headers",), ("request", "headers"), ("response", "headers")})
SAFE_OUTPUT_METADATA_KEYS = frozenset({"credentialenvironment", "maincredential", "readcredential"})
INTEGRATION_TYPE_MARKERS = (
    "discord",
    "googlechat",
    "mattermost",
    "msteams",
    "slack",
    "teams",
    "webhook",
)
CAPABILITY_URL_PATTERN = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)
ALWAYS_CAPABILITY_HOSTS = frozenset(
    {
        "heartbeat.uptimerobot.com",
        "hooks.slack.com",
        "hooks.zapier.com",
    }
)
CAPABILITY_HOST_PATH_RULES = (
    (frozenset({"discord.com", "discordapp.com"}), "/api/webhooks/"),
    (frozenset({"chat.googleapis.com"}), "/v1/spaces/"),
    (frozenset({"api.telegram.org"}), "/bot"),
    (frozenset({"events.pagerduty.com"}), "/integration/"),
)


class UptimeRobotCliError(RuntimeError):
    """Report a safe, user-facing helper error."""


class ResponseConsumptionError(UptimeRobotCliError):
    """Identify a bounded response-consumption failure after an API attempt."""


class StrictJsonError(ValueError):
    """Identify invalid or structurally unsafe JSON without retaining input text."""


class NoRedirectHandler(request.HTTPRedirectHandler):
    """Reject redirects so bearer credentials never cross a trust boundary."""

    @override
    def redirect_request(
        self,
        req: request.Request,
        fp: IO[bytes],
        code: int,
        msg: str,
        headers: HTTPMessage,
        newurl: str,
    ) -> request.Request | None:
        """Refuse every redirect and surface the original response."""
        del req, fp, code, msg, headers, newurl
        return None


class ReadableBinary(Protocol):
    """Small structural type shared by files and urllib response streams."""

    def read(self, size: int = -1, /) -> bytes:
        """Read at most size bytes."""
        ...


class ApiResponse(ReadableBinary, Protocol):
    """Structural urllib response consumed by the API transport."""

    headers: HTTPMessage
    status: int

    def __enter__(self) -> Self:
        """Enter the response context."""
        ...

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close the response context."""
        ...


@dataclass(frozen=True)
class Credential:
    """One resolved credential without an output-safe representation of its value."""

    environment: str
    value: str


@dataclass(frozen=True)
class UptimeRobotContext:
    """Validated API target and optional account credentials."""

    base_url: str
    main_credential: Credential | None
    read_credential: Credential | None
    spec_url: str


@dataclass(frozen=True)
class OpenApiOperation:
    """Small stable view of one OpenAPI operation."""

    deprecated: bool
    method: str
    operation_id: str
    path: str
    summary: str
    tags: tuple[str, ...]
    array_query_parameters: tuple[str, ...] = ()


@dataclass(frozen=True)
class RequestPlan:
    """Resolved request inputs before authentication or execution."""

    body: JsonValue
    confirmation_value: str | None
    high_risk: bool
    method: str
    operation_id: str | None
    query: QueryPairs
    url: str


@dataclass(frozen=True)
class ResolvedRequestTarget:
    """Endpoint and risk metadata resolved from raw or OpenAPI inputs."""

    array_query_parameters: tuple[str, ...]
    endpoint: str
    high_risk: bool
    method: str
    operation_id: str | None


@dataclass(frozen=True)
class ApiResult:
    """One API response page."""

    payload: JsonValue
    status: int
    url: str
    response_bytes: int = 0


@dataclass(frozen=True)
class ResponseMetadata:
    """Headers and status needed by bounded response consumers."""

    content_length: str | None
    content_type: str
    retry_after: str | None
    status: int


@dataclass(frozen=True)
class RetryState:
    """Current attempt and configured retry budget."""

    attempt: int
    retries: int


@dataclass(frozen=True)
class RetryInstruction:
    """One bounded delay requested by a retryable read response."""

    delay: float


@dataclass(frozen=True)
class PreparedRequest:
    """Fully validated transport inputs prepared before authentication is attached."""

    body: bytes | None
    headers: dict[str, str]
    retries: int
    secrets: tuple[str, ...]
    timeout: float
    url: str


@dataclass
class YamlOperationState:
    """Mutable operation metadata while reading the official YAML document."""

    deprecated: bool = False
    array_query_parameters: list[str] = field(default_factory=list[str])
    method: str | None = None
    operation_id: str = ""
    path: str | None = None
    parameter_is_array: bool = False
    parameter_location: str = ""
    parameter_name: str = ""
    reading_parameters: bool = False
    reading_tags: bool = False
    summary: str = ""
    tags: list[str] = field(default_factory=list[str])

    def operation(self) -> OpenApiOperation | None:
        """Return a completed operation when all required identity fields exist."""
        self.finish_parameter()
        if self.path is None or self.method is None or not self.operation_id:
            return None
        return OpenApiOperation(
            deprecated=self.deprecated,
            method=self.method,
            operation_id=self.operation_id,
            path=self.path,
            summary=self.summary,
            tags=tuple(self.tags),
            array_query_parameters=tuple(self.array_query_parameters),
        )

    def finish_parameter(self) -> None:
        """Retain a completed array-valued query parameter and reset its state."""
        if (
            self.parameter_name
            and self.parameter_location == "query"
            and self.parameter_is_array
            and self.parameter_name not in self.array_query_parameters
        ):
            self.array_query_parameters.append(self.parameter_name)
        self.parameter_is_array = False
        self.parameter_location = ""
        self.parameter_name = ""

    def reset_operation(self, method: str | None = None) -> None:
        """Reset operation-local fields while preserving the current path."""
        self.deprecated = False
        self.array_query_parameters = []
        self.method = method
        self.operation_id = ""
        self.parameter_is_array = False
        self.parameter_location = ""
        self.parameter_name = ""
        self.reading_parameters = False
        self.reading_tags = False
        self.summary = ""
        self.tags = []


def optional_text(value: object) -> str | None:
    """Return a stripped optional string."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def decoded_text_forms(value: str) -> tuple[str, ...]:
    """Return deterministic raw and repeatedly percent/form-decoded text forms."""
    forms = [value]
    seen = {value}
    frontier = [value]
    for _ in range(MAX_SECRET_DECODE_ROUNDS):
        decoded: list[str] = []
        for item in frontier:
            for decoder in (parse.unquote, parse.unquote_plus):
                candidate = decoder(item)
                if candidate not in seen:
                    seen.add(candidate)
                    decoded.append(candidate)
        if not decoded:
            break
        forms.extend(decoded)
        frontier = decoded
    return tuple(forms)


def normalized_key(value: str) -> str:
    """Normalize the deepest decoded key across separators and casing styles."""
    return "".join(character for character in decoded_text_forms(value)[-1].casefold() if character.isalnum())


def semantic_key_tokens(value: str) -> tuple[tuple[str, ...], ...]:
    """Tokenize every bounded decoded key form without substring heuristics."""
    tokenized: list[tuple[str, ...]] = []
    for form in decoded_text_forms(value):
        separated = CAMEL_CASE_BOUNDARY.sub(" ", ACRONYM_BOUNDARY.sub(" ", form))
        tokens = tuple(match.group(0).casefold() for match in KEY_TOKEN.finditer(separated))
        if tokens and tokens not in tokenized:
            tokenized.append(tokens)
    return tuple(tokenized)


def key_has_tokens(value: str, expected: tuple[str, ...]) -> bool:
    """Return whether one decoded key form exactly matches a token sequence."""
    return expected in semantic_key_tokens(value)


def is_sensitive_key(value: str) -> bool:
    """Recognize decoded credential fields by semantic token suffixes."""
    for tokens in semantic_key_tokens(value):
        normalized = "".join(tokens)
        if normalized in SENSITIVE_KEY_EXACT_NORMALIZED or tokens in SENSITIVE_CONTAINER_TOKEN_SEQUENCES:
            return True
        if any(len(tokens) >= len(suffix) and tokens[-len(suffix) :] == suffix for suffix in SENSITIVE_KEY_SUFFIXES):
            return True
    return False


def is_capability_url(value: str) -> bool:
    """Recognize callback URLs only on known capability-bearing providers."""
    try:
        parsed = parse.urlsplit(value)
        host = (parsed.hostname or "").casefold()
        _ = parsed.port
    except ValueError:
        return False
    if parsed.scheme.casefold() not in {"http", "https"} or not host:
        return False
    path = parsed.path.casefold()
    is_office_host = host == "office.com" or host.endswith(".office.com")
    is_office_webhook_host = host == "webhook.office.com" or host.endswith(".webhook.office.com")
    matches_host_path_rule = any(
        host in hosts and (path.startswith(marker) if marker == "/bot" else marker in path)
        for hosts, marker in CAPABILITY_HOST_PATH_RULES
    )
    return (
        host in ALWAYS_CAPABILITY_HOSTS
        or matches_host_path_rule
        or is_office_webhook_host
        or (is_office_host and "webhook" in path)
        or (host.endswith(".logic.azure.com") and "/workflows/" in path)
    )


def text_contains_capability_url(value: str) -> bool:
    """Detect raw or repeatedly encoded capability URLs in arbitrary text."""
    for form in decoded_text_forms(value):
        if is_capability_url(form):
            return True
        if any(is_capability_url(match.group(0)) for match in CAPABILITY_URL_PATTERN.finditer(form)):
            return True
    return False


def active_secrets(secrets: tuple[str, ...]) -> tuple[str, ...]:
    """Retain unique configured values that meet the minimum credential length."""
    return tuple(dict.fromkeys(secret for secret in secrets if len(secret) >= MIN_CREDENTIAL_LENGTH))


def is_credential_character(value: str) -> bool:
    """Classify characters that can extend an opaque credential token."""
    return value.isalnum() or value in {"_", "-"}


def bounded_occurrence(value: str, needle: str, start: int) -> bool:
    """Require token boundaries only where the credential endpoint is token-like."""
    end = start + len(needle)
    left_is_joined = start > 0 and is_credential_character(value[start - 1]) and is_credential_character(needle[0])
    right_is_joined = end < len(value) and is_credential_character(value[end]) and is_credential_character(needle[-1])
    return not left_is_joined and not right_is_joined


def text_has_bounded_value(value: str, needle: str) -> bool:
    """Find an exact value without matching it inside a larger credential token."""
    start = value.find(needle)
    while start >= 0:
        if bounded_occurrence(value, needle, start):
            return True
        start = value.find(needle, start + 1)
    return False


def encoded_secret_variants(secret: str) -> tuple[str, ...]:
    """Generate bounded raw, percent, form, and mixed credential encodings."""
    variants = [secret]
    seen = {secret}
    frontier = [secret]
    for _ in range(MAX_SECRET_DECODE_ROUNDS):
        encoded: list[str] = []
        for item in frontier:
            for encoder in (parse.quote, parse.quote_plus):
                candidate = encoder(item, safe="")
                if candidate not in seen:
                    seen.add(candidate)
                    encoded.append(candidate)
        if not encoded:
            break
        variants.extend(encoded)
        frontier = encoded
    return tuple(sorted(variants, key=len, reverse=True))


def text_contains_secret(value: str, secrets: tuple[str, ...]) -> bool:
    """Detect bounded configured credentials through repeated percent/form decoding."""
    return any(
        text_has_bounded_value(form, secret) for secret in active_secrets(secrets) for form in decoded_text_forms(value)
    )


def json_contains_secret(value: JsonValue, secrets: tuple[str, ...]) -> bool:
    """Detect configured credentials recursively in request JSON."""
    if isinstance(value, dict):
        return any(
            text_contains_secret(key, secrets) or json_contains_secret(item, secrets) for key, item in value.items()
        )
    if isinstance(value, list):
        return any(json_contains_secret(item, secrets) for item in value)
    return isinstance(value, str) and text_contains_secret(value, secrets)


def replace_bounded_value(value: str, needle: str) -> str:
    """Replace bounded occurrences while retaining surrounding ordinary text."""
    parts: list[str] = []
    cursor = 0
    while True:
        start = value.find(needle, cursor)
        if start < 0:
            parts.append(value[cursor:])
            break
        if not bounded_occurrence(value, needle, start):
            parts.append(value[cursor : start + 1])
            cursor = start + 1
            continue
        parts.extend((value[cursor:start], REDACTED_VALUE))
        cursor = start + len(needle)
    return "".join(parts)


def redact_configured_secrets(value: str, secrets: tuple[str, ...]) -> str:
    """Replace every direct encoded credential variant at semantic boundaries."""
    redacted = value
    for secret in active_secrets(secrets):
        if not text_contains_secret(redacted, (secret,)):
            continue
        for variant in encoded_secret_variants(secret):
            redacted = replace_bounded_value(redacted, variant)
    if redacted == value and text_contains_secret(value, secrets):
        return REDACTED_VALUE
    return redacted


def redact_known_secrets(value: str, secrets: tuple[str, ...]) -> str:
    """Redact configured credentials and known provider capabilities in one scalar."""
    redacted = redact_configured_secrets(value, secrets)
    return REDACTED_VALUE if text_contains_capability_url(redacted) else redacted


def is_integration_capability_object(value: dict[str, JsonValue]) -> bool:
    """Recognize alert-integration objects whose generic value is a capability."""
    if any(normalized_key(key) in {"webhookurl", "urltonotify"} for key in value):
        return True
    for key, item in value.items():
        if normalized_key(key) not in {"alertcontacttype", "integrationtype", "provider", "type"}:
            continue
        if isinstance(item, str):
            normalized_value = normalized_key(item)
            if any(marker in normalized_value for marker in INTEGRATION_TYPE_MARKERS):
                return True
    return False


def is_integration_container_key(value: str) -> bool:
    """Recognize response containers whose child value fields are capabilities."""
    return any(
        tokens in {("alert", "contact"), ("alert", "contacts")}
        or any(token in {"integration", "integrations"} for token in tokens)
        for tokens in semantic_key_tokens(value)
    )


def as_string_list(value: object) -> list[str]:
    """Narrow parser-controlled repeatable string arguments."""
    return cast("list[str]", value)


def is_environment_name(value: str) -> bool:
    """Return whether a name is a portable ASCII environment identifier."""
    return value.isascii() and value.isidentifier()


def is_safe_output_metadata(key: str, value: JsonValue) -> bool:
    """Recognize the helper's non-secret credential source metadata shapes."""
    normalized = normalized_key(key)
    if normalized not in SAFE_OUTPUT_METADATA_KEYS:
        return False
    if normalized == "credentialenvironment":
        return value is None or (isinstance(value, str) and is_environment_name(value))
    if not isinstance(value, dict) or set(value) != {"configured", "environment"}:
        return False
    configured = value.get("configured")
    environment = value.get("environment")
    return isinstance(configured, bool) and (
        environment is None or (isinstance(environment, str) and is_environment_name(environment))
    )


def existing_file(value: str) -> Path:
    """Resolve an existing regular file for argparse."""
    try:
        path = Path(value).expanduser().resolve(strict=True)
    except OSError as exception:
        raise argparse.ArgumentTypeError(f"File does not exist: {value}") from exception
    if not path.is_file():
        raise argparse.ArgumentTypeError(f"Path is not a regular file: {value}")
    return path


def resolve_credential(names: list[str], defaults: tuple[str, ...]) -> Credential | None:
    """Resolve the first populated credential from validated environment names."""
    candidates = names or list(defaults)
    for name in candidates:
        if not is_environment_name(name):
            raise UptimeRobotCliError(f"Invalid credential environment variable name: {name}")
        value = os.environ.get(name, "").strip()
        if value:
            if len(value) < MIN_CREDENTIAL_LENGTH:
                raise UptimeRobotCliError(
                    f"Credential in {name} must contain at least {MIN_CREDENTIAL_LENGTH} characters."
                )
            return Credential(environment=name, value=value)
    return None


def sanitize_base_url(value: str) -> str:
    """Lock a bearer-authenticated base URL to the production v3 API."""
    candidate = value.strip().rstrip("/")
    if contains_control_character(candidate):
        raise UptimeRobotCliError("API base URL contains control characters.")
    try:
        parsed = parse.urlsplit(candidate)
        port = parsed.port
    except ValueError as exception:
        raise UptimeRobotCliError("API base URL is malformed.") from exception
    if parsed.scheme.lower() != "https" or parsed.hostname != "api.uptimerobot.com":
        raise UptimeRobotCliError("API base URL must use the production https://api.uptimerobot.com origin.")
    if parsed.username is not None or parsed.password is not None or port is not None:
        raise UptimeRobotCliError("API base URL must not contain credentials or an explicit port.")
    if parsed.query or parsed.fragment:
        raise UptimeRobotCliError("API base URL must not contain a query or fragment.")
    if parsed.path.rstrip("/") != "/v3":
        raise UptimeRobotCliError("API base URL must end with /v3.")
    return DEFAULT_BASE_URL


def validate_spec_url(value: str) -> str:
    """Lock live contract discovery to the official OpenAPI document."""
    candidate = value.strip()
    if contains_control_character(candidate):
        raise UptimeRobotCliError("OpenAPI URL contains control characters.")
    try:
        parsed = parse.urlsplit(candidate)
        port = parsed.port
    except ValueError as exception:
        raise UptimeRobotCliError("OpenAPI URL is malformed.") from exception
    if parsed.scheme.lower() != "https" or parsed.hostname != "cdn.uptimerobot.com":
        raise UptimeRobotCliError("OpenAPI URL must use the official UptimeRobot CDN origin.")
    if parsed.username is not None or parsed.password is not None or port is not None:
        raise UptimeRobotCliError("OpenAPI URL must not contain credentials or an explicit port.")
    if parsed.query or parsed.fragment or parsed.path != "/api/openapi.yaml":
        raise UptimeRobotCliError("OpenAPI URL must be the official /api/openapi.yaml document.")
    return DEFAULT_SPEC_URL


def resolve_context(arguments: argparse.Namespace) -> UptimeRobotContext:
    """Resolve validated URLs and independent read/main credentials."""
    return UptimeRobotContext(
        base_url=sanitize_base_url(str(arguments.base_url)),
        main_credential=resolve_credential(as_string_list(arguments.main_token_envs), DEFAULT_MAIN_TOKEN_ENVS),
        read_credential=resolve_credential(as_string_list(arguments.read_token_envs), DEFAULT_READ_TOKEN_ENVS),
        spec_url=validate_spec_url(str(arguments.spec_url)),
    )


def context_payload(context: UptimeRobotContext) -> dict[str, JsonValue]:
    """Build a credential-safe context report."""
    return {
        "baseUrl": context.base_url,
        "mainCredential": {
            "configured": context.main_credential is not None,
            "environment": context.main_credential.environment if context.main_credential else None,
        },
        "officialCli": {"installed": shutil.which("uptimerobot") is not None},
        "readCredential": {
            "configured": context.read_credential is not None,
            "environment": context.read_credential.environment if context.read_credential else None,
        },
        "specUrl": context.spec_url,
    }


def strip_yaml_scalar(value: str) -> str:
    """Decode the simple scalar forms used by operation metadata."""
    text = value.strip()
    if len(text) >= MIN_QUOTED_SCALAR_LENGTH and text[0] == text[-1] == "'":
        return text[1:-1].replace("''", "'")
    if len(text) >= MIN_QUOTED_SCALAR_LENGTH and text[0] == text[-1] == '"':
        try:
            decoded = json.loads(text)
        except json.JSONDecodeError:
            return text[1:-1]
        return decoded if isinstance(decoded, str) else text
    return text


def array_query_parameter_names(*parameter_groups: JsonValue) -> tuple[str, ...]:
    """Return inline OpenAPI query parameters whose schema type is array."""
    names: list[str] = []
    for parameters in parameter_groups:
        if not isinstance(parameters, list):
            continue
        for parameter in parameters:
            if not isinstance(parameter, dict) or parameter.get("in") != "query":
                continue
            name = parameter.get("name")
            schema = parameter.get("schema")
            if (
                isinstance(name, str)
                and name
                and isinstance(schema, dict)
                and schema.get("type") == "array"
                and name not in names
            ):
                names.append(name)
    return tuple(names)


def openapi_operation(
    path: str,
    method: str,
    value: JsonValue,
    path_parameters: JsonValue = None,
) -> OpenApiOperation | None:
    """Normalize one JSON OpenAPI operation."""
    if not isinstance(value, dict):
        return None
    operation_id = value.get("operationId")
    if not isinstance(operation_id, str) or not operation_id:
        return None
    summary = value.get("summary")
    tags = value.get("tags")
    return OpenApiOperation(
        deprecated=value.get("deprecated") is True,
        method=method.upper(),
        operation_id=operation_id,
        path=path,
        summary=summary if isinstance(summary, str) else "",
        tags=tuple(item for item in tags if isinstance(item, str)) if isinstance(tags, list) else (),
        array_query_parameters=array_query_parameter_names(path_parameters, value.get("parameters")),
    )


def parse_json_operations(payload: JsonValue) -> list[OpenApiOperation]:
    """Extract operations from an OpenAPI JSON object."""
    if not isinstance(payload, dict):
        raise UptimeRobotCliError("OpenAPI JSON root must be an object.")
    paths = payload.get("paths")
    if not isinstance(paths, dict):
        raise UptimeRobotCliError("OpenAPI document does not contain a paths object.")
    operations: list[OpenApiOperation] = []
    for path_name, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue
        for method in (item.lower() for item in HTTP_METHODS):
            operation = openapi_operation(path_name, method, path_item.get(method), path_item.get("parameters"))
            if operation is not None:
                operations.append(operation)
    return operations


def append_yaml_operation(operations: list[OpenApiOperation], state: YamlOperationState) -> None:
    """Append the current YAML operation when complete."""
    operation = state.operation()
    if operation is not None:
        operations.append(operation)


def yaml_mapping_entry(line: str, *, indent: int) -> tuple[str, str] | None:
    """Parse one exactly indented simple YAML mapping entry."""
    prefix = " " * indent
    if not line.startswith(prefix) or line.startswith(f"{prefix} "):
        return None
    field_name, separator, value = line[indent:].partition(":")
    if not separator or not field_name or not field_name[0].isalpha() or not field_name.isalnum():
        return None
    return field_name, value.strip()


def apply_yaml_operation_field(state: YamlOperationState, line: str) -> bool:
    """Apply one operation-level YAML field and report whether it matched."""
    field = yaml_mapping_entry(line, indent=6)
    if field is None:
        return False
    field_name, value = field
    state.finish_parameter()
    state.reading_parameters = field_name == "parameters"
    state.reading_tags = field_name == "tags"
    if field_name == "operationId":
        state.operation_id = strip_yaml_scalar(value)
    elif field_name == "summary":
        state.summary = strip_yaml_scalar(value)
    elif field_name == "deprecated":
        state.deprecated = value.strip().lower() == "true"
    return True


def apply_yaml_parameter_field(state: YamlOperationState, line: str) -> bool:
    """Collect one inline operation-level OpenAPI parameter field."""
    if not state.reading_parameters:
        return False
    parameter_prefix = "        - name:"
    if line.startswith(parameter_prefix):
        state.finish_parameter()
        state.parameter_name = strip_yaml_scalar(line[len(parameter_prefix) :].strip())
        return True
    parameter_field = yaml_mapping_entry(line, indent=10)
    if parameter_field is not None:
        field_name, value = parameter_field
        if field_name == "in":
            state.parameter_location = strip_yaml_scalar(value)
        return True
    schema_field = yaml_mapping_entry(line, indent=12)
    if schema_field is not None:
        field_name, value = schema_field
        if field_name == "type":
            state.parameter_is_array = strip_yaml_scalar(value) == "array"
        return True
    return False


def apply_yaml_tag(state: YamlOperationState, line: str) -> None:
    """Append a simple list-form tag when currently inside the tags field."""
    tag_prefix = "        -"
    if not state.reading_tags or not line.startswith(tag_prefix):
        return
    value = line[len(tag_prefix) :].strip()
    if value:
        state.tags.append(strip_yaml_scalar(value))


def yaml_path_key(line: str) -> str | None:
    """Return an exactly two-space-indented OpenAPI path key."""
    if not line.startswith("  /"):
        return None
    content = line[2:].rstrip()
    return content[:-1] if content.endswith(":") else None


def openapi_path_lines(text: str) -> list[str]:
    """Return lines within the top-level paths mapping."""
    lines: list[str] = []
    in_paths = False
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not in_paths:
            in_paths = line == "paths:"
            continue
        if line and not line.startswith((" ", "#")):
            break
        lines.append(line)
    if not in_paths:
        raise UptimeRobotCliError("OpenAPI YAML document does not contain a paths mapping.")
    return lines


def parse_yaml_operations(text: str) -> list[OpenApiOperation]:
    """Extract operation metadata from the official consistently indented YAML."""
    operations: list[OpenApiOperation] = []
    state = YamlOperationState()
    for line in openapi_path_lines(text):
        path_name = yaml_path_key(line)
        if path_name is not None:
            append_yaml_operation(operations, state)
            state.path = path_name
            state.reset_operation()
            continue
        method_entry = yaml_mapping_entry(line, indent=4)
        method = method_entry[0] if method_entry is not None and not method_entry[1] else None
        if method in YAML_HTTP_METHODS and state.path is not None:
            append_yaml_operation(operations, state)
            state.reset_operation(method.upper())
            continue
        if (
            state.method is not None
            and not apply_yaml_operation_field(state, line)
            and not apply_yaml_parameter_field(state, line)
        ):
            apply_yaml_tag(state, line)
    append_yaml_operation(operations, state)
    if not operations:
        raise UptimeRobotCliError("Could not discover operations in the OpenAPI YAML document.")
    return operations


def read_bounded_stream(
    stream: ReadableBinary,
    *,
    max_bytes: int,
    label: str,
    content_length: str | None = None,
) -> bytes:
    """Enforce declared and actual response sizes with a limit-plus-one read."""
    if content_length is not None:
        try:
            declared_length = int(content_length)
        except ValueError:
            declared_length = None
        if declared_length is not None and declared_length >= 0 and declared_length > max_bytes:
            raise UptimeRobotCliError(f"{label} exceeds the {max_bytes}-byte safety limit.")
    data = stream.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise UptimeRobotCliError(f"{label} exceeds the {max_bytes}-byte safety limit.")
    return data


def reject_json_constant(_value: str) -> Never:
    """Reject NaN and infinity spellings without reflecting source text."""
    raise StrictJsonError("JSON constants must be finite.")


def parse_finite_json_float(value: str) -> float:
    """Parse one JSON number and reject float overflow."""
    try:
        parsed_value = float(value)
    except (OverflowError, ValueError) as exception:
        raise StrictJsonError("JSON numbers must be finite.") from exception
    if not math.isfinite(parsed_value):
        raise StrictJsonError("JSON numbers must be finite.")
    return parsed_value


def reject_duplicate_json_keys(pairs: list[tuple[str, JsonValue]]) -> dict[str, JsonValue]:
    """Reject duplicate object keys instead of silently keeping the last value."""
    result: dict[str, JsonValue] = {}
    for key, value in pairs:
        if key in result:
            raise StrictJsonError("JSON objects must not contain duplicate keys.")
        result[key] = value
    return result


def validate_json_scalar(item: object, *, label: str, max_string_chars: int) -> bool:
    """Validate one scalar and report whether the item was a JSON scalar."""
    if isinstance(item, str):
        if len(item) > max_string_chars:
            raise StrictJsonError(f"{label} exceeds the {max_string_chars}-character JSON string limit.")
        return True
    if item is None or isinstance(item, bool | int):
        return True
    if isinstance(item, float):
        if not math.isfinite(item):
            raise StrictJsonError(f"{label} contains a non-finite JSON number.")
        return True
    return False


def json_container_children(
    item: object,
    *,
    depth: int,
    label: str,
    max_string_chars: int,
) -> tuple[list[tuple[object, int]], int]:
    """Validate one container and return child work plus its object-key node count."""
    if isinstance(item, list):
        sequence = cast("list[object]", item)
        return ([(child, depth) for child in sequence], 0)
    if not isinstance(item, dict):
        raise StrictJsonError(f"{label} contains a value that JSON cannot represent.")
    mapping = cast("dict[object, object]", item)
    children: list[tuple[object, int]] = []
    for key, child in mapping.items():
        if not isinstance(key, str):
            raise StrictJsonError(f"{label} contains a non-string JSON object key.")
        if len(key) > max_string_chars:
            raise StrictJsonError(f"{label} exceeds the {max_string_chars}-character JSON string limit.")
        children.append((child, depth))
    return children, len(mapping)


def validate_json_tree(
    value: JsonValue,
    *,
    label: str,
    max_depth: int,
    max_nodes: int,
    max_string_chars: int,
) -> None:
    """Iteratively enforce JSON depth, node, string, type, and finite-number limits."""
    stack: list[tuple[object, int]] = [(value, 0)]
    node_count = 0
    while stack:
        item, parent_depth = stack.pop()
        node_count += 1
        if node_count > max_nodes:
            raise StrictJsonError(f"{label} exceeds the {max_nodes}-node JSON safety limit.")
        if validate_json_scalar(item, label=label, max_string_chars=max_string_chars):
            continue
        depth = parent_depth + 1
        if depth > max_depth:
            raise StrictJsonError(f"{label} exceeds the {max_depth}-level JSON depth limit.")
        children, key_nodes = json_container_children(
            item,
            depth=depth,
            label=label,
            max_string_chars=max_string_chars,
        )
        node_count += key_nodes
        if node_count > max_nodes:
            raise StrictJsonError(f"{label} exceeds the {max_nodes}-node JSON safety limit.")
        stack.extend(children)


def strict_json_loads(
    text: str,
    *,
    label: str,
    max_depth: int,
    max_nodes: int,
    max_string_chars: int,
) -> JsonValue:
    """Decode strict JSON and enforce iterative structural limits."""
    try:
        value = cast(
            "JsonValue",
            json.loads(
                text,
                object_pairs_hook=reject_duplicate_json_keys,
                parse_constant=reject_json_constant,
                parse_float=parse_finite_json_float,
            ),
        )
    except StrictJsonError:
        raise
    except (json.JSONDecodeError, RecursionError) as exception:
        raise StrictJsonError(f"{label} must be valid JSON within the configured depth limit.") from exception
    validate_json_tree(
        value,
        label=label,
        max_depth=max_depth,
        max_nodes=max_nodes,
        max_string_chars=max_string_chars,
    )
    return value


def encode_request_body(value: JsonValue, *, sort_keys: bool = False) -> bytes:
    """Validate and atomically encode one bounded request JSON document."""
    try:
        validate_json_tree(
            value,
            label="Request body",
            max_depth=MAX_REQUEST_JSON_DEPTH,
            max_nodes=MAX_REQUEST_JSON_NODES,
            max_string_chars=MAX_REQUEST_JSON_STRING_CHARS,
        )
        encoded = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=sort_keys,
        ).encode("utf-8")
    except StrictJsonError as exception:
        raise UptimeRobotCliError(str(exception)) from exception
    except (RecursionError, TypeError, UnicodeEncodeError, ValueError) as exception:
        raise UptimeRobotCliError("Request body could not be encoded as strict JSON.") from exception
    if len(encoded) > MAX_REQUEST_BODY_BYTES:
        raise UptimeRobotCliError(f"Request body exceeds the {MAX_REQUEST_BODY_BYTES}-byte safety limit.")
    return encoded


def read_api_response_bytes(
    stream: ReadableBinary,
    *,
    max_bytes: int,
    label: str,
    content_length: str | None,
) -> bytes:
    """Convert low-level post-attempt stream failures into safe response errors."""
    try:
        return read_bounded_stream(
            stream,
            max_bytes=max_bytes,
            label=label,
            content_length=content_length,
        )
    except UptimeRobotCliError as exception:
        raise ResponseConsumptionError(str(exception)) from exception
    except IncompleteRead as exception:
        raise ResponseConsumptionError(f"{label} ended before its declared body was complete.") from exception
    except (HTTPException, OSError) as exception:
        raise ResponseConsumptionError(f"{label} could not be read safely.") from exception


def bounded_error_detail(
    stream: ReadableBinary,
    *,
    content_length: str | None,
    label: str,
) -> str | None:
    """Consume a bounded error body and return only a size-limit diagnostic."""
    try:
        _ = read_bounded_stream(
            stream,
            max_bytes=MAX_ERROR_RESPONSE_BYTES,
            label=label,
            content_length=content_length,
        )
    except UptimeRobotCliError as response_error:
        return str(response_error)
    else:
        return None


def retryable_status_delay(
    status: int,
    retry_after: str | None,
    *,
    attempt: int,
    retries: int,
) -> float | None:
    """Return a delay only while a retryable GET status remains in budget."""
    if status not in RETRYABLE_GET_STATUS_CODES or attempt >= retries:
        return None
    return retry_delay_header(retry_after, attempt)


def status_error_detail(label: str, status: int, response_detail: str | None) -> str:
    """Build one bounded status diagnostic without reflecting response content."""
    detail = f"{label} failed with HTTP {status}."
    return detail if response_detail is None else f"{detail} {response_detail}"


def decode_operations(data: bytes, *, source: str) -> list[OpenApiOperation]:
    """Decode JSON or the official YAML operation metadata."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exception:
        raise UptimeRobotCliError(f"OpenAPI document from {source} is not UTF-8.") from exception
    stripped = text.lstrip()
    if stripped.startswith("{"):
        try:
            payload = cast("JsonValue", json.loads(text))
        except json.JSONDecodeError as exception:
            raise UptimeRobotCliError(f"Could not parse OpenAPI JSON from {source}.") from exception
        operations = parse_json_operations(payload)
    else:
        operations = parse_yaml_operations(text)
    if not operations:
        raise UptimeRobotCliError("OpenAPI document did not expose any operations.")
    return sorted(operations, key=lambda item: (item.path, item.method, item.operation_id))


def load_local_operations(spec_file: Path) -> list[OpenApiOperation]:
    """Load a size-bounded local OpenAPI document."""
    try:
        with spec_file.open("rb") as stream:
            document = read_bounded_stream(
                stream,
                max_bytes=MAX_OPENAPI_BYTES,
                label="OpenAPI document",
            )
    except OSError as exception:
        raise UptimeRobotCliError(f"Could not read OpenAPI file: {spec_file}") from exception
    return decode_operations(document, source=str(spec_file))


def consume_openapi_response(
    stream: ReadableBinary,
    metadata: ResponseMetadata,
    retry_state: RetryState,
) -> bytes | RetryInstruction:
    """Read one OpenAPI response or return its bounded retry delay."""
    if HTTP_SUCCESS_MIN <= metadata.status < HTTP_SUCCESS_LIMIT:
        return read_bounded_stream(
            stream,
            max_bytes=MAX_OPENAPI_BYTES,
            label="OpenAPI document",
            content_length=metadata.content_length,
        )
    response_detail = bounded_error_detail(
        stream,
        content_length=metadata.content_length,
        label="OpenAPI error response",
    )
    delay = retryable_status_delay(
        metadata.status,
        metadata.retry_after,
        attempt=retry_state.attempt,
        retries=retry_state.retries,
    )
    if delay is not None:
        return RetryInstruction(delay)
    raise UptimeRobotCliError(status_error_detail("OpenAPI request", metadata.status, response_detail))


def consume_openapi_http_error(
    http_error: error.HTTPError,
    *,
    attempt: int,
    retries: int,
) -> RetryInstruction:
    """Consume one urllib OpenAPI failure and return a retry delay when allowed."""
    response_detail = bounded_error_detail(
        http_error,
        content_length=http_error.headers.get("Content-Length"),
        label="OpenAPI error response",
    )
    delay = retryable_status_delay(
        http_error.code,
        http_error.headers.get("Retry-After"),
        attempt=attempt,
        retries=retries,
    )
    if delay is not None:
        return RetryInstruction(delay)
    detail = status_error_detail("OpenAPI request", http_error.code, response_detail)
    raise UptimeRobotCliError(detail) from http_error


def load_remote_operations(arguments: argparse.Namespace, context: UptimeRobotContext) -> list[OpenApiOperation]:
    """Load the official OpenAPI document with bounded read retries."""
    retries = validated_retries(arguments, default=0)
    timeout = validated_timeout(arguments)
    opener = request.build_opener(NoRedirectHandler())
    spec_request = request.Request(  # noqa: S310  # validate_spec_url locks the URL.
        context.spec_url,
        headers={"Accept": "application/yaml, application/json", "User-Agent": "codex-uptimerobot-management/1"},
    )
    secrets = request_secrets(context)
    for attempt in range(retries + 1):
        try:
            with opener.open(spec_request, timeout=timeout) as response:
                outcome = consume_openapi_response(
                    response,
                    ResponseMetadata(
                        content_length=response.headers.get("Content-Length"),
                        content_type=response.headers.get("Content-Type", ""),
                        retry_after=response.headers.get("Retry-After"),
                        status=int(response.status),
                    ),
                    RetryState(attempt=attempt, retries=retries),
                )
        except error.HTTPError as exception:
            try:
                delay = consume_openapi_http_error(exception, attempt=attempt, retries=retries)
            finally:
                exception.close()
            time.sleep(delay.delay)
            continue
        except (error.URLError, TimeoutError) as exception:
            if attempt < retries:
                time.sleep(min(2.0**attempt, 30.0))
                continue
            reason = exception.reason if isinstance(exception, error.URLError) else exception
            safe_reason = safe_transport_reason(reason, secrets)
            raise UptimeRobotCliError(f"OpenAPI request failed: {safe_reason}") from exception
        if isinstance(outcome, RetryInstruction):
            time.sleep(outcome.delay)
            continue
        return decode_operations(outcome, source=context.spec_url)
    raise UptimeRobotCliError("OpenAPI request exhausted its retry budget.")


def load_operations(arguments: argparse.Namespace, context: UptimeRobotContext) -> list[OpenApiOperation]:
    """Load operation metadata from a local file or the live official contract."""
    spec_file = cast("Path | None", getattr(arguments, "spec_file", None))
    return load_local_operations(spec_file) if spec_file is not None else load_remote_operations(arguments, context)


def parse_pairs(values: list[str], *, label: str, secrets: tuple[str, ...] = ()) -> dict[str, str]:
    """Parse repeatable name=value values with duplicate and credential guards."""
    result: dict[str, str] = {}
    for value in values:
        name, separator, item_value = value.partition("=")
        name = name.strip()
        if not separator or not name or not item_value:
            raise UptimeRobotCliError(f"{label} values must use non-empty name=value syntax.")
        if text_contains_secret(name, secrets) or text_contains_secret(item_value, secrets):
            raise UptimeRobotCliError(f"Refusing configured credential in {label} value.")
        if name in result:
            raise UptimeRobotCliError(f"Duplicate {label} name: {name}")
        if label == "query" and is_sensitive_key(name):
            raise UptimeRobotCliError("Refusing credential-like query parameter.")
        result[name] = item_value
    return result


def parse_query_pairs(
    values: list[str],
    *,
    array_names: tuple[str, ...] = (),
    allow_repeated: bool = False,
    secrets: tuple[str, ...] = (),
) -> QueryPairs:
    """Parse ordered query pairs, allowing only schema-declared or raw repeats."""
    result: list[tuple[str, str]] = []
    seen: set[str] = set()
    repeatable = frozenset(array_names)
    for value in values:
        name, separator, item_value = value.partition("=")
        name = name.strip()
        if not separator or not name or not item_value:
            raise UptimeRobotCliError("query values must use non-empty name=value syntax.")
        if text_contains_secret(name, secrets) or text_contains_secret(item_value, secrets):
            raise UptimeRobotCliError("Refusing configured credential in query value.")
        if is_sensitive_key(name):
            raise UptimeRobotCliError("Refusing credential-like query parameter.")
        if name in seen and not allow_repeated and name not in repeatable:
            raise UptimeRobotCliError(f"Duplicate query name: {name}")
        seen.add(name)
        result.append((name, item_value))
    return tuple(result)


def load_body(arguments: argparse.Namespace) -> JsonValue:
    """Load one bounded, strict UTF-8 JSON body from a reviewed source."""
    body_json = cast("str | None", getattr(arguments, "body_json", None))
    body_file = cast("Path | None", getattr(arguments, "body_file", None))
    if body_file is not None:
        try:
            with body_file.open("rb") as stream:
                body_bytes = read_bounded_stream(
                    stream,
                    max_bytes=MAX_REQUEST_BODY_BYTES,
                    label="Request body",
                )
        except OSError as exception:
            raise UptimeRobotCliError(f"Could not read request body file: {body_file}") from exception
    elif body_json is not None:
        try:
            body_bytes = body_json.encode("utf-8")
        except UnicodeEncodeError as exception:
            raise UptimeRobotCliError("Request body must be valid UTF-8 JSON.") from exception
        if len(body_bytes) > MAX_REQUEST_BODY_BYTES:
            raise UptimeRobotCliError(f"Request body exceeds the {MAX_REQUEST_BODY_BYTES}-byte safety limit.")
    else:
        return None
    try:
        body_text = body_bytes.decode("utf-8")
    except UnicodeDecodeError as exception:
        raise UptimeRobotCliError("Request body must be valid UTF-8 JSON.") from exception
    try:
        return strict_json_loads(
            body_text,
            label="Request body",
            max_depth=MAX_REQUEST_JSON_DEPTH,
            max_nodes=MAX_REQUEST_JSON_NODES,
            max_string_chars=MAX_REQUEST_JSON_STRING_CHARS,
        )
    except StrictJsonError as exception:
        raise UptimeRobotCliError(str(exception)) from exception


def operation_by_id(operations: list[OpenApiOperation], operation_id: str) -> OpenApiOperation:
    """Resolve exactly one case-sensitive operation ID."""
    matches = [operation for operation in operations if operation.operation_id == operation_id]
    if len(matches) != 1:
        raise UptimeRobotCliError("operationId must resolve exactly once in the OpenAPI document.")
    return matches[0]


def fill_path(path_template: str, values: dict[str, str]) -> str:
    """Fill all documented path parameters and reject unused values."""
    required = PATH_PARAMETER.findall(path_template)
    missing = [name for name in required if name not in values]
    unused = [name for name in values if name not in required]
    if missing:
        raise UptimeRobotCliError(f"Missing path parameter(s): {', '.join(missing)}")
    if unused:
        raise UptimeRobotCliError(f"Unused path parameter(s): {', '.join(unused)}")
    result = path_template
    for name in required:
        result = result.replace(f"{{{name}}}", parse.quote(values[name], safe=""))
    return result


def contains_control_character(value: str) -> bool:
    """Recognize ASCII controls that are unsafe in request targets."""
    return any(ord(character) < ASCII_CONTROL_LIMIT or ord(character) == ASCII_DELETE for character in value)


def has_well_formed_percent_escapes(value: str) -> bool:
    """Require every literal percent sign to start one complete hex escape."""
    cursor = 0
    while True:
        cursor = value.find("%", cursor)
        if cursor < 0:
            return True
        if PERCENT_ESCAPE.fullmatch(value[cursor : cursor + 3]) is None:
            return False
        cursor += 3


def repeatedly_unquote_path(value: str) -> tuple[str, ...]:
    """Decode a URL path to a bounded fixed point and reject residual encodings."""
    if not has_well_formed_percent_escapes(value):
        raise UptimeRobotCliError("Endpoint path contains malformed percent encoding.")
    forms = [value]
    current = value
    for _ in range(MAX_SECRET_DECODE_ROUNDS):
        try:
            decoded = parse.unquote(current, errors="strict")
        except UnicodeDecodeError as exception:
            raise UptimeRobotCliError("Endpoint path contains invalid UTF-8 percent encoding.") from exception
        if decoded == current:
            break
        forms.append(decoded)
        current = decoded
    if PERCENT_ESCAPE.search(current) is not None or "%" in current:
        raise UptimeRobotCliError("Endpoint path contains residual percent encoding.")
    return tuple(forms)


def has_residual_component_encoding(value: str) -> bool:
    """Return whether mixed query decoding still exposes an encoded octet."""
    frontier = [value]
    for _ in range(MAX_SECRET_DECODE_ROUNDS):
        decoded: list[str] = []
        for item in frontier:
            for decoder in (parse.unquote, parse.unquote_plus):
                candidate = decoder(item)
                if candidate != item and candidate not in decoded:
                    decoded.append(candidate)
        if not decoded:
            return False
        frontier = decoded
    return any(PERCENT_ESCAPE.search(item) is not None for item in frontier)


def normalized_endpoint_path(url: str) -> str:
    """Return the fully decoded endpoint path after confinement validation."""
    parsed = parse.urlsplit(url)
    return repeatedly_unquote_path(parsed.path)[-1]


def split_production_api_url(candidate: str) -> parse.SplitResult:
    """Split a URL and enforce the exact bearer-authenticated API origin."""
    try:
        parsed = parse.urlsplit(candidate)
        port = parsed.port
    except ValueError as exception:
        raise UptimeRobotCliError("Endpoint URL is malformed.") from exception
    if parsed.scheme.lower() != "https" or parsed.hostname != "api.uptimerobot.com":
        raise UptimeRobotCliError("Endpoint origin must match the production UptimeRobot API.")
    if parsed.username is not None or parsed.password is not None or port is not None:
        raise UptimeRobotCliError("Endpoint must not contain credentials or an explicit port.")
    return parsed


def validate_api_path(path: str) -> None:
    """Reject traversal and structural changes across every decoded path form."""
    path_forms = repeatedly_unquote_path(path)
    slash_count = path_forms[0].count("/")
    for path_form in path_forms:
        if (
            contains_control_character(path_form)
            or any(character.isspace() for character in path_form)
            or "\\" in path_form
            or "?" in path_form
            or "#" in path_form
            or path_form.count("/") != slash_count
            or any(part in {".", ".."} for part in path_form.split("/"))
        ):
            raise UptimeRobotCliError("Endpoint path traversal or encoded structural characters are not allowed.")
        if path_form != "/v3" and not path_form.startswith("/v3/"):
            raise UptimeRobotCliError("Endpoint must remain under the configured /v3 base path.")


def validate_api_query(query: str) -> None:
    """Reject malformed, residual, controlled, and credential-like query names."""
    if not has_well_formed_percent_escapes(query):
        raise UptimeRobotCliError("Endpoint query contains malformed percent encoding.")
    try:
        query_pairs = parse.parse_qsl(query, keep_blank_values=True)
    except ValueError as exception:
        raise UptimeRobotCliError("Endpoint query is malformed.") from exception
    for name, item_value in query_pairs:
        if any(contains_control_character(form) for form in decoded_text_forms(name)) or any(
            contains_control_character(form) for form in decoded_text_forms(item_value)
        ):
            raise UptimeRobotCliError("Endpoint query contains encoded control characters.")
        if has_residual_component_encoding(name) or has_residual_component_encoding(item_value):
            raise UptimeRobotCliError("Endpoint query contains residual percent encoding.")
        if is_sensitive_key(name):
            raise UptimeRobotCliError("Refusing credential-like query parameter.")


def assert_safe_api_url(base_url: str, candidate: str, *, allow_query: bool) -> str:
    """Validate exact API origin and repeatedly decoded path/query confinement."""
    if candidate != candidate.strip() or contains_control_character(candidate):
        raise UptimeRobotCliError("Endpoint URL contains whitespace or control characters.")
    _ = sanitize_base_url(base_url)
    parsed = split_production_api_url(candidate)
    if parsed.fragment or (parsed.query and not allow_query):
        raise UptimeRobotCliError("Endpoint must not contain a query or fragment; use --query.")
    validate_api_path(parsed.path)
    validate_api_query(parsed.query)
    return candidate


def validated_endpoint_url(base_url: str, endpoint: str) -> str:
    """Resolve a raw/spec endpoint while preserving the API trust boundary."""
    value = endpoint.strip()
    if not value:
        raise UptimeRobotCliError("Endpoint must not be empty.")
    try:
        parsed_value = parse.urlsplit(value)
    except ValueError as exception:
        raise UptimeRobotCliError("Endpoint URL is malformed.") from exception
    if parsed_value.query or parsed_value.fragment:
        raise UptimeRobotCliError("Endpoint must not contain a query or fragment; use --query.")
    if value.startswith("/v3"):
        candidate = f"https://api.uptimerobot.com{value}"
    elif value.startswith("/"):
        candidate = f"{base_url}{value}"
    elif parsed_value.scheme:
        candidate = value
    else:
        raise UptimeRobotCliError("Relative endpoint must start with /.")
    return assert_safe_api_url(base_url, candidate, allow_query=False)


def operation_is_high_risk(operation: OpenApiOperation) -> bool:
    """Identify destructive and broad-scope operations requiring exact confirmation."""
    return operation.method == "DELETE" or operation.operation_id.startswith("BulkMonitorsController_")


def raw_confirmation_value(method: str, url: str) -> str:
    """Build the exact confirmation phrase for a raw high-risk request."""
    path = parse.urlsplit(url).path.removeprefix("/v3") or "/"
    return f"{method} {path}"


def confirmation_value(method: str, url: str, body: JsonValue, operation_id: str | None) -> str:
    """Bind a high-impact confirmation to the exact operation, target, query, and body."""
    parsed = parse.urlsplit(url)
    path = parsed.path.removeprefix("/v3") or "/"
    target = parse.urlunsplit(("", "", path, parsed.query, ""))
    prefix = f"{operation_id} " if operation_id is not None else ""
    value = f"{prefix}{method} {target}"
    if body is None:
        return value
    canonical_body = encode_request_body(body, sort_keys=True)
    return f"{value} body-sha256={hashlib.sha256(canonical_body).hexdigest()}"


def resolve_request_target(arguments: argparse.Namespace, context: UptimeRobotContext) -> ResolvedRequestTarget:
    """Resolve raw or operation-based target inputs before body processing."""
    endpoint = optional_text(arguments.endpoint)
    operation_id = optional_text(arguments.operation_id)
    if endpoint is not None and operation_id is not None:
        raise UptimeRobotCliError("Provide either an endpoint or --operation-id, not both.")
    if endpoint is None and operation_id is None:
        raise UptimeRobotCliError("Provide an endpoint or --operation-id.")

    requested_method = optional_text(arguments.method)
    path_values = as_string_list(arguments.path_values)
    if operation_id is None:
        if path_values:
            raise UptimeRobotCliError("--path requires --operation-id.")
        return ResolvedRequestTarget(
            array_query_parameters=(),
            endpoint=cast("str", endpoint),
            high_risk=False,
            method=(requested_method or "GET").upper(),
            operation_id=None,
        )

    operation = operation_by_id(load_operations(arguments, context), operation_id)
    if requested_method is not None and requested_method.upper() != operation.method:
        raise UptimeRobotCliError("--method conflicts with the OpenAPI operation.")
    high_risk = operation_is_high_risk(operation)
    return ResolvedRequestTarget(
        array_query_parameters=operation.array_query_parameters,
        endpoint=fill_path(operation.path, parse_pairs(path_values, label="path", secrets=request_secrets(context))),
        high_risk=high_risk,
        method=operation.method,
        operation_id=operation_id,
    )


def build_plan(arguments: argparse.Namespace, context: UptimeRobotContext) -> RequestPlan:
    """Build a raw or operation-based request plan."""
    target = resolve_request_target(arguments, context)
    body = load_body(arguments)
    if target.method in SAFE_METHODS and body is not None:
        raise UptimeRobotCliError(f"{target.method} requests must not include a body.")
    secrets = request_secrets(context)
    reject_credential_reuse(target.endpoint, body, secrets)
    url = validated_endpoint_url(context.base_url, target.endpoint)
    high_risk = target.high_risk
    if target.operation_id is None:
        raw_path = parse.urlsplit(url).path.casefold()
        high_risk = target.method == "DELETE" or "/monitors/bulk/" in raw_path
    query = parse_query_pairs(
        as_string_list(arguments.query),
        array_names=target.array_query_parameters,
        allow_repeated=target.operation_id is None,
        secrets=secrets,
    )
    encoded_url = encode_url(url, query)
    reject_credential_reuse(encoded_url, body, secrets)
    return RequestPlan(
        body=body,
        confirmation_value=(
            confirmation_value(target.method, encoded_url, body, target.operation_id) if high_risk else None
        ),
        high_risk=high_risk,
        method=target.method,
        operation_id=target.operation_id,
        query=query,
        url=url,
    )


def reject_credential_reuse(url: str, body: JsonValue, secrets: tuple[str, ...]) -> None:
    """Keep configured API credentials out of paths, queries, and request bodies."""
    if text_contains_secret(url, secrets) or json_contains_secret(body, secrets):
        raise UptimeRobotCliError(
            "Configured UptimeRobot credentials may appear only in the generated Authorization header."
        )


def output_url_parts(value: str) -> tuple[parse.SplitResult, int | None, list[tuple[str, str]]] | None:
    """Parse URL output metadata without allowing malformed values to escape redaction."""
    try:
        parsed = parse.urlsplit(value)
        port = parsed.port
        pairs = parse.parse_qsl(parsed.query, keep_blank_values=True)
    except ValueError:
        return None
    return parsed, port, pairs


def redact_url_secrets(value: str, secrets: tuple[str, ...] = ()) -> str:
    """Redact sensitive fields in absolute API URLs and relative pagination links."""
    output_parts = output_url_parts(value)
    if output_parts is None:
        return redact_configured_secrets(value, secrets)
    parsed, port, pairs = output_parts
    is_absolute = parsed.scheme.lower() in {"http", "https"} and parsed.hostname is not None
    is_relative = not parsed.scheme and not parsed.netloc and value.startswith(("/", "?"))
    if not is_absolute and not is_relative:
        return redact_configured_secrets(value, secrets)
    if is_capability_url(value):
        return REDACTED_VALUE
    has_userinfo = parsed.username is not None or parsed.password is not None
    if parsed.hostname is not None and text_contains_secret(parsed.hostname, secrets):
        return REDACTED_VALUE
    redacted_path = redact_configured_secrets(parsed.path, secrets)
    redacted_fragment = redact_known_secrets(parsed.fragment, secrets)
    redacted_pairs = [
        (
            name,
            (
                REDACTED_VALUE
                if is_sensitive_key(name) or text_contains_capability_url(item_value)
                else redact_configured_secrets(item_value, secrets)
            ),
        )
        for name, item_value in pairs
    ]
    if (
        not has_userinfo
        and redacted_path == parsed.path
        and redacted_fragment == parsed.fragment
        and redacted_pairs == pairs
    ):
        return value
    netloc = parsed.netloc
    if has_userinfo and parsed.hostname is not None:
        host = f"[{parsed.hostname}]" if ":" in parsed.hostname else parsed.hostname
        if port is not None:
            host = f"{host}:{port}"
        netloc = f"{REDACTED_VALUE}@{host}"
    query = parse.urlencode(redacted_pairs, doseq=True, safe="<>")
    return parse.urlunsplit((parsed.scheme, netloc, redacted_path, query, redacted_fragment))


def redact_embedded_urls(value: str, secrets: tuple[str, ...]) -> str:
    """Sanitize absolute URLs embedded inside bounded diagnostic text."""
    return CAPABILITY_URL_PATTERN.sub(lambda match: redact_url_secrets(match.group(0), secrets), value)


def redact_json_value(
    value: JsonValue,
    secrets: tuple[str, ...],
    *,
    integration_context: bool,
) -> JsonValue:
    """Recursively redact one value with its structured integration context."""
    if isinstance(value, dict):
        is_heartbeat = any(
            key_has_tokens(key, ("type",)) and isinstance(item, str) and item.casefold() == "heartbeat"
            for key, item in value.items()
        )
        is_integration = integration_context or is_integration_capability_object(value)
        return {
            redact_known_secrets(key, secrets): (
                REDACTED_VALUE
                if (is_sensitive_key(key) and not is_safe_output_metadata(key, item))
                or (is_heartbeat and key_has_tokens(key, ("url",)))
                or (is_integration and key_has_tokens(key, ("value",)))
                else redact_json_value(
                    item,
                    secrets,
                    integration_context=is_integration or is_integration_container_key(key),
                )
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_json_value(item, secrets, integration_context=integration_context) for item in value]
    if isinstance(value, str):
        url_safe = redact_url_secrets(value, secrets)
        return redact_known_secrets(redact_embedded_urls(url_safe, secrets), secrets)
    return value


def redact_json(value: JsonValue, secrets: tuple[str, ...] = ()) -> JsonValue:
    """Recursively redact credential-like fields and reflected credential values."""
    return redact_json_value(value, secrets, integration_context=False)


def encode_url(url: str, query: QueryPairs | dict[str, str]) -> str:
    """Append encoded query values to a validated URL."""
    parsed = parse.urlsplit(url)
    pairs = tuple(query.items()) if isinstance(query, dict) else query
    return parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parse.urlencode(pairs), ""))


def validated_next_url(base_url: str, current_url: str, next_link: str) -> str:
    """Resolve a cursor link while preserving the exact collection endpoint."""
    value = next_link.strip()
    if not value:
        raise UptimeRobotCliError("Pagination nextLink must not be empty.")
    current_url = assert_safe_api_url(base_url, current_url, allow_query=True)
    current_path = normalized_endpoint_path(current_url)
    if value.startswith("?"):
        current = parse.urlsplit(current_url)
        candidate = parse.urlunsplit((current.scheme, current.netloc, current.path, value[1:], ""))
    elif value.startswith("/v3"):
        candidate = f"https://api.uptimerobot.com{value}"
    elif value.startswith("/"):
        candidate = f"{base_url}{value}"
    else:
        candidate = parse.urljoin(current_url, value)
    candidate = assert_safe_api_url(base_url, candidate, allow_query=True)
    if normalized_endpoint_path(candidate) != current_path:
        raise UptimeRobotCliError("Pagination nextLink must remain on the exact collection endpoint path.")
    current_pairs = parse.parse_qsl(parse.urlsplit(current_url).query, keep_blank_values=True)
    candidate_parsed = parse.urlsplit(candidate)
    candidate_pairs = parse.parse_qsl(candidate_parsed.query, keep_blank_values=True)
    replacement_names = {name for name, _ in candidate_pairs}
    merged_pairs = [pair for pair in current_pairs if pair[0] not in replacement_names]
    merged_pairs.extend(candidate_pairs)
    merged = parse.urlunsplit(
        (
            candidate_parsed.scheme,
            candidate_parsed.netloc,
            candidate_parsed.path,
            parse.urlencode(merged_pairs),
            "",
        )
    )
    merged = assert_safe_api_url(base_url, merged, allow_query=True)
    if normalized_endpoint_path(merged) != current_path:
        raise UptimeRobotCliError("Pagination nextLink must remain on the exact collection endpoint path.")
    return merged


def credential_for(context: UptimeRobotContext, method: str) -> Credential | None:
    """Prefer read-only authentication for reads and require main auth for writes."""
    if method in SAFE_METHODS:
        return context.read_credential or context.main_credential
    return context.main_credential


def response_payload(data: bytes, content_type: str) -> JsonValue:
    """Decode one strict, structurally bounded UTF-8 API response."""
    if not data:
        return None
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exception:
        raise ResponseConsumptionError("UptimeRobot API response is not valid UTF-8.") from exception
    if "json" not in content_type.lower():
        return text[:MAX_RESPONSE_TEXT]
    try:
        return strict_json_loads(
            text,
            label="UptimeRobot API response",
            max_depth=MAX_RESPONSE_JSON_DEPTH,
            max_nodes=MAX_RESPONSE_JSON_NODES,
            max_string_chars=MAX_RESPONSE_JSON_STRING_CHARS,
        )
    except StrictJsonError as exception:
        raise ResponseConsumptionError(
            f"Expected JSON from the UptimeRobot API under strict bounded parsing. {exception}"
        ) from exception


def retry_fallback(attempt: int) -> float:
    """Return overflow-safe exponential fallback bounded to 30 seconds."""
    bounded_attempt = min(max(attempt, 0), 5)
    return min(2.0**bounded_attempt, 30.0)


def delta_seconds_retry(value: str) -> float | None:
    """Parse one standards-compliant integer delta-seconds value."""
    if not value.isascii() or not value.isdecimal():
        return None
    significant_digits = value.lstrip("0") or "0"
    if len(significant_digits) > MAX_RETRY_AFTER_DELTA_DIGITS:
        return MAX_RETRY_DELAY
    return float(min(int(significant_digits), int(MAX_RETRY_DELAY)))


def http_date_retry(value: str, *, now: datetime | None) -> float | None:
    """Parse one HTTP-date relative to an injectable UTC clock."""
    try:
        parsed_date = parsedate_to_datetime(value)
    except OverflowError, TypeError, ValueError:
        return None
    if parsed_date.tzinfo is None:
        return None
    current = datetime.now(UTC) if now is None else now
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    try:
        delay = (parsed_date.astimezone(UTC) - current.astimezone(UTC)).total_seconds()
    except OverflowError, ValueError:
        return None
    if not math.isfinite(delay):
        return None
    return min(max(delay, 0.0), MAX_RETRY_DELAY)


def retry_delay_header(
    retry_after: str | None,
    attempt: int,
    *,
    now: datetime | None = None,
) -> float:
    """Honor HTTP delta-seconds or an HTTP-date, bounded to 60 seconds."""
    value = (retry_after or "").strip()
    fallback = retry_fallback(attempt)
    if not value:
        return fallback
    delta_delay = delta_seconds_retry(value)
    if delta_delay is not None:
        return delta_delay
    if len(value) > MAX_RETRY_AFTER_LENGTH:
        return fallback
    date_delay = http_date_retry(value, now=now)
    return fallback if date_delay is None else date_delay


def retry_delay(http_error: error.HTTPError, attempt: int) -> float:
    """Preserve the direct-call helper contract for one HTTP error."""
    return retry_delay_header(http_error.headers.get("Retry-After"), attempt)


def safe_transport_reason(reason: object, secrets: tuple[str, ...]) -> str:
    """Return bounded transport text without configured credentials or capability URLs."""
    safe = cast("str", redact_json(str(reason), secrets))
    return " ".join(safe.split())[:MAX_TRANSPORT_ERROR_TEXT] or "transport details unavailable"


def indeterminate_mutation_message(method: str, detail: str) -> str:
    """Explain recovery after an attempted mutation whose outcome is unknown."""
    return " ".join(
        (
            detail,
            f"The {method} mutation may have succeeded and was not retried; its outcome is indeterminate.",
            "Re-read the exact UptimeRobot target before retrying manually.",
        )
    )


def response_consumption_detail(
    status: int | None,
    exception: BaseException,
    secrets: tuple[str, ...],
) -> str:
    """Build a bounded, redacted, status-aware post-attempt diagnostic."""
    reason = (
        safe_transport_reason(exception, secrets)
        if isinstance(exception, ResponseConsumptionError)
        else "response stream or metadata could not be consumed safely"
    )
    prefix = "API response" if status is None else f"API response for HTTP {status}"
    return f"{prefix} could not be consumed safely: {reason}."


def raise_response_consumption_error(
    plan: RequestPlan,
    status: int | None,
    exception: BaseException,
    secrets: tuple[str, ...],
) -> Never:
    """Classify an attempted write response failure as indeterminate."""
    detail = response_consumption_detail(status, exception, secrets)
    if plan.method not in SAFE_METHODS:
        raise UptimeRobotCliError(indeterminate_mutation_message(plan.method, detail)) from exception
    raise UptimeRobotCliError(detail) from exception


def raise_status_error(plan: RequestPlan, status: int, detail: str) -> Never:
    """Raise a terminal status error with correct mutation-outcome semantics."""
    if plan.method not in SAFE_METHODS and status in INDETERMINATE_MUTATION_STATUS_CODES:
        raise UptimeRobotCliError(indeterminate_mutation_message(plan.method, detail))
    raise UptimeRobotCliError(detail)


def consume_api_response(
    plan: RequestPlan,
    url: str,
    stream: ReadableBinary,
    metadata: ResponseMetadata,
    retry_state: RetryState,
) -> ApiResult | RetryInstruction:
    """Consume one API response or return a safe-read retry delay."""
    if metadata.status < HTTP_SUCCESS_MIN or metadata.status >= HTTP_SUCCESS_LIMIT:
        delay = (
            retryable_status_delay(
                metadata.status,
                metadata.retry_after,
                attempt=retry_state.attempt,
                retries=retry_state.retries,
            )
            if plan.method == "GET"
            else None
        )
        try:
            _ = read_api_response_bytes(
                stream,
                max_bytes=MAX_ERROR_RESPONSE_BYTES,
                label="UptimeRobot API error response",
                content_length=metadata.content_length,
            )
        except ResponseConsumptionError:
            if delay is not None:
                return RetryInstruction(delay)
            raise
        if delay is not None:
            return RetryInstruction(delay)
        raise_status_error(
            plan,
            metadata.status,
            status_error_detail("API request", metadata.status, None),
        )
    data = read_api_response_bytes(
        stream,
        max_bytes=MAX_API_RESPONSE_BYTES,
        label="UptimeRobot API response",
        content_length=metadata.content_length,
    )
    payload = response_payload(data, metadata.content_type)
    return ApiResult(payload=payload, response_bytes=len(data), status=metadata.status, url=url)


def consume_api_http_error(
    plan: RequestPlan,
    http_error: error.HTTPError,
    *,
    attempt: int,
    retries: int,
) -> RetryInstruction:
    """Consume one urllib API status failure and return a GET retry delay."""
    delay = (
        retryable_status_delay(
            http_error.code,
            http_error.headers.get("Retry-After"),
            attempt=attempt,
            retries=retries,
        )
        if plan.method == "GET"
        else None
    )
    try:
        _ = read_api_response_bytes(
            http_error,
            max_bytes=MAX_ERROR_RESPONSE_BYTES,
            label="UptimeRobot API error response",
            content_length=http_error.headers.get("Content-Length"),
        )
    except ResponseConsumptionError:
        if delay is not None:
            return RetryInstruction(delay)
        raise
    if delay is not None:
        return RetryInstruction(delay)
    detail = status_error_detail("API request", http_error.code, None)
    raise_status_error(plan, http_error.code, detail)


def raise_transport_error(
    plan: RequestPlan,
    exception: error.URLError | TimeoutError,
    secrets: tuple[str, ...],
) -> Never:
    """Raise a bounded transport failure with mutation ambiguity when required."""
    reason = exception.reason if isinstance(exception, error.URLError) else exception
    detail = f"API request failed: {safe_transport_reason(reason, secrets)}"
    if plan.method not in SAFE_METHODS:
        raise UptimeRobotCliError(indeterminate_mutation_message(plan.method, detail)) from exception
    raise UptimeRobotCliError(detail) from exception


def validated_timeout(arguments: argparse.Namespace) -> float:
    """Return a finite positive timeout within the global pre-I/O cap."""
    try:
        timeout = float(getattr(arguments, "timeout", DEFAULT_TIMEOUT))
    except (OverflowError, TypeError, ValueError) as exception:
        raise UptimeRobotCliError(f"--timeout must be greater than zero and at most {MAX_TIMEOUT:g}.") from exception
    if not math.isfinite(timeout) or timeout <= 0 or timeout > MAX_TIMEOUT:
        raise UptimeRobotCliError(f"--timeout must be greater than zero and at most {MAX_TIMEOUT:g}.")
    return timeout


def validated_retries(arguments: argparse.Namespace, *, default: int = 0) -> int:
    """Return an integer GET retry budget within the supported range."""
    try:
        retries = int(getattr(arguments, "retries", default))
    except (TypeError, ValueError, OverflowError) as exception:
        raise UptimeRobotCliError("--retries must be between 0 and 10.") from exception
    if retries < 0 or retries > 10:  # noqa: PLR2004  # Explicit safety cap.
        raise UptimeRobotCliError("--retries must be between 0 and 10.")
    return retries


def close_http_error(http_error: error.HTTPError) -> None:
    """Best-effort close an HTTPError without masking the primary safe failure."""
    with suppress(HTTPException, OSError):
        http_error.close()


def prepare_request(
    plan: RequestPlan,
    url: str,
    credential: Credential,
    arguments: argparse.Namespace,
    secrets: tuple[str, ...],
) -> PreparedRequest:
    """Resolve every safety-sensitive input before constructing auth or an opener."""
    if plan.method not in HTTP_METHODS:
        raise UptimeRobotCliError("Request method is not supported.")
    all_secrets = active_secrets(tuple(dict.fromkeys((*secrets, credential.value))))
    reject_credential_reuse(url, plan.body, all_secrets)
    plan_url = assert_safe_api_url(DEFAULT_BASE_URL, plan.url, allow_query=False)
    url = assert_safe_api_url(DEFAULT_BASE_URL, url, allow_query=True)
    if normalized_endpoint_path(url) != normalized_endpoint_path(plan_url):
        raise UptimeRobotCliError("Request URL must remain on the planned endpoint path.")
    body = None if plan.body is None else encode_request_body(plan.body)
    timeout = validated_timeout(arguments)
    configured_retries = validated_retries(arguments)
    retries = configured_retries if plan.method == "GET" else 0
    if len(credential.value) < MIN_CREDENTIAL_LENGTH or contains_control_character(credential.value):
        raise UptimeRobotCliError("Configured credential is not a valid bearer value.")
    headers = {
        "Accept": JSON_MEDIA_TYPE,
        "Authorization": f"Bearer {credential.value}",
        "User-Agent": "codex-uptimerobot-management/1",
    }
    if body is not None:
        headers["Content-Type"] = JSON_MEDIA_TYPE
    return PreparedRequest(
        body=body,
        headers=headers,
        retries=retries,
        secrets=all_secrets,
        timeout=timeout,
        url=url,
    )


def consume_http_error_response(
    plan: RequestPlan,
    http_error: error.HTTPError,
    *,
    attempt: int,
    retries: int,
    secrets: tuple[str, ...],
) -> RetryInstruction:
    """Consume and close an HTTPError with post-attempt mutation semantics."""
    try:
        try:
            return consume_api_http_error(plan, http_error, attempt=attempt, retries=retries)
        except ResponseConsumptionError as response_error:
            raise_response_consumption_error(plan, int(http_error.code), response_error, secrets)
        except (IncompleteRead, HTTPException, OSError, TypeError, ValueError) as response_error:
            raise_response_consumption_error(plan, int(http_error.code), response_error, secrets)
    finally:
        close_http_error(http_error)


def consume_opened_response(
    plan: RequestPlan,
    response: ApiResponse,
    prepared: PreparedRequest,
    *,
    attempt: int,
) -> ApiResult | RetryInstruction:
    """Consume one returned response and classify every post-attempt failure."""
    response_status: int | None = None
    try:
        with response:
            response_status = int(response.status)
            return consume_api_response(
                plan,
                prepared.url,
                response,
                ResponseMetadata(
                    content_length=response.headers.get("Content-Length"),
                    content_type=response.headers.get("Content-Type", ""),
                    retry_after=response.headers.get("Retry-After"),
                    status=response_status,
                ),
                RetryState(attempt=attempt, retries=prepared.retries),
            )
    except ResponseConsumptionError as response_error:
        raise_response_consumption_error(plan, response_status, response_error, prepared.secrets)
    except (IncompleteRead, HTTPException, OSError, TypeError, ValueError) as response_error:
        raise_response_consumption_error(plan, response_status, response_error, prepared.secrets)


def send_request(
    plan: RequestPlan,
    url: str,
    credential: Credential,
    arguments: argparse.Namespace,
    *,
    secrets: tuple[str, ...] = (),
) -> ApiResult:
    """Send one request, retrying only safe reads within explicit bounds."""
    prepared = prepare_request(plan, url, credential, arguments, secrets)
    opener = request.build_opener(NoRedirectHandler())
    for attempt in range(prepared.retries + 1):
        api_request = request.Request(  # noqa: S310  # URL is origin- and path-locked before this point.
            prepared.url,
            data=prepared.body,
            headers=prepared.headers,
            method=plan.method,
        )
        try:
            response = cast("ApiResponse", opener.open(api_request, timeout=prepared.timeout))
        except error.HTTPError as exception:
            delay = consume_http_error_response(
                plan,
                exception,
                attempt=attempt,
                retries=prepared.retries,
                secrets=prepared.secrets,
            )
            time.sleep(delay.delay)
            continue
        except (error.URLError, TimeoutError) as exception:
            if plan.method == "GET" and attempt < prepared.retries:
                time.sleep(retry_delay_header(None, attempt))
                continue
            raise_transport_error(plan, exception, prepared.secrets)
        outcome = consume_opened_response(
            plan,
            response,
            prepared,
            attempt=attempt,
        )
        if isinstance(outcome, RetryInstruction):
            time.sleep(outcome.delay)
            continue
        return outcome
    raise UptimeRobotCliError("API request exhausted its retry budget.")


def next_link(payload: JsonValue) -> str | None:
    """Read a required nullable v3 nextLink field without hiding malformed pages."""
    if not isinstance(payload, dict) or "nextLink" not in payload:
        raise UptimeRobotCliError("Pagination response must contain a nullable nextLink field.")
    value = payload["nextLink"]
    if value is None:
        return None
    if isinstance(value, str) and value.strip():
        return value
    raise UptimeRobotCliError("Pagination nextLink must be null or a non-empty string.")


def validate_execution_mode(arguments: argparse.Namespace, *, is_safe: bool) -> None:
    """Reject execution switches that conflict with request safety."""
    if bool(arguments.send) and is_safe:
        raise UptimeRobotCliError("--send is only valid for mutating requests; reads execute without it.")
    if bool(arguments.paginate) and not is_safe:
        raise UptimeRobotCliError("--paginate is only valid for safe read requests.")


def request_secrets(context: UptimeRobotContext) -> tuple[str, ...]:
    """Return configured secret values for reflected-response redaction."""
    return tuple(
        dict.fromkeys(item.value for item in (context.read_credential, context.main_credential) if item is not None)
    )


def write_preview(context: UptimeRobotContext, plan: RequestPlan, initial_url: str, secrets: tuple[str, ...]) -> None:
    """Write a deterministic, credential-safe request preview."""
    reject_credential_reuse(initial_url, plan.body, secrets)
    credential = credential_for(context, plan.method)
    write_json(
        {
            "confirmationRequired": plan.high_risk,
            "confirmationValue": plan.confirmation_value,
            "credentialEnvironment": credential.environment if credential else None,
            "dryRun": True,
            "request": {
                "body": plan.body,
                "method": plan.method,
                "operationId": plan.operation_id,
                "url": initial_url,
            },
        },
        secrets=secrets,
    )


def require_credential(context: UptimeRobotContext, plan: RequestPlan, *, is_safe: bool) -> Credential:
    """Resolve the least-privileged credential or fail before network access."""
    credential = credential_for(context, plan.method)
    if credential is None:
        role = "read-only or main" if is_safe else "main"
        raise UptimeRobotCliError(f"No {role} credential is configured for this request.")
    return credential


def result_payload(result: ApiResult) -> dict[str, JsonValue]:
    """Build one API response object for centralized output sanitization."""
    return {
        "data": result.payload,
        "status": result.status,
        "url": result.url,
    }


def write_paginated_results(
    arguments: argparse.Namespace,
    context: UptimeRobotContext,
    plan: RequestPlan,
    credential: Credential,
    initial_url: str,
) -> None:
    """Execute and write bounded cursor pagination for a safe request."""
    pages: list[JsonValue] = []
    current_url = initial_url
    pending_link: str | None = None
    secrets = request_secrets(context)
    response_bytes = 0
    visited_urls = {current_url}
    for _ in range(int(arguments.max_pages)):
        result = send_request(plan, current_url, credential, arguments, secrets=secrets)
        response_bytes += result.response_bytes
        if response_bytes > MAX_PAGINATED_RESPONSE_BYTES:
            raise UptimeRobotCliError(
                f"UptimeRobot pagination exceeds the {MAX_PAGINATED_RESPONSE_BYTES}-byte cumulative safety limit."
            )
        pages.append(result_payload(result))
        raw_next_link = next_link(result.payload)
        if raw_next_link is None:
            pending_link = None
            break
        current_url = validated_next_url(context.base_url, current_url, raw_next_link)
        reject_credential_reuse(current_url, plan.body, secrets)
        if current_url in visited_urls:
            raise UptimeRobotCliError(
                f"UptimeRobot pagination is incomplete after {len(pages)} page(s): repeated nextLink."
            )
        visited_urls.add(current_url)
        pending_link = current_url
    write_json(
        {
            "complete": pending_link is None,
            "nextLink": pending_link,
            "pageCount": len(pages),
            "pages": pages,
        },
        secrets=secrets,
    )


def execute_plan(arguments: argparse.Namespace, context: UptimeRobotContext, plan: RequestPlan) -> None:
    """Preview a write/read or execute a credentialed request."""
    is_safe = plan.method in SAFE_METHODS
    validate_execution_mode(arguments, is_safe=is_safe)
    preview = bool(arguments.dry_run) or (not is_safe and not bool(arguments.send))
    initial_url = encode_url(plan.url, plan.query)
    secrets = request_secrets(context)
    reject_credential_reuse(initial_url, plan.body, secrets)
    if preview:
        write_preview(context, plan, initial_url, secrets)
        return

    credential = require_credential(context, plan, is_safe=is_safe)
    if plan.high_risk and optional_text(arguments.confirm) != plan.confirmation_value:
        safe_confirmation = cast("str", redact_json(plan.confirmation_value, secrets))
        raise UptimeRobotCliError(f"High-impact request requires --confirm {safe_confirmation!r}.")
    if bool(arguments.paginate):
        write_paginated_results(arguments, context, plan, credential, initial_url)
        return
    write_json(
        result_payload(send_request(plan, initial_url, credential, arguments, secrets=secrets)),
        secrets=secrets,
    )


def handle_operations(arguments: argparse.Namespace, context: UptimeRobotContext) -> int:
    """Filter and print current OpenAPI operation metadata."""
    operations = load_operations(arguments, context)
    search = (optional_text(arguments.search) or "").casefold()
    method = (optional_text(arguments.operation_method) or "").upper()
    tag = (optional_text(arguments.tag) or "").casefold()
    selected = [
        operation
        for operation in operations
        if (bool(arguments.include_deprecated) or not operation.deprecated)
        and (not method or operation.method == method)
        and (not tag or any(tag in item.casefold() for item in operation.tags))
        and (
            not search
            or search
            in " ".join(
                (operation.operation_id, operation.path, operation.summary, " ".join(operation.tags))
            ).casefold()
        )
    ]
    write_json(
        {"count": len(selected), "operations": [cast("JsonValue", asdict(item)) for item in selected]},
        secrets=request_secrets(context),
    )
    return 0


def write_json(value: JsonValue, *, secrets: tuple[str, ...] = ()) -> None:
    """Write deterministic JSON through the single output-sanitization boundary."""
    json.dump(redact_json(value, secrets), sys.stdout, indent=2, sort_keys=True)
    _ = sys.stdout.write("\n")


def common_parser() -> argparse.ArgumentParser:
    """Create options shared by all commands."""
    parser = argparse.ArgumentParser(add_help=False)
    _ = parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    _ = parser.add_argument("--spec-url", default=DEFAULT_SPEC_URL)
    _ = parser.add_argument("--read-token-env", action="append", dest="read_token_envs", default=[])
    _ = parser.add_argument("--main-token-env", action="append", dest="main_token_envs", default=[])
    _ = parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    _ = parser.add_argument("--retries", type=int, default=DEFAULT_RETRIES)
    return parser


def add_spec_options(parser: argparse.ArgumentParser) -> None:
    """Add local/live OpenAPI selection."""
    _ = parser.add_argument("--spec-file", type=existing_file)


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line interface."""
    parser = argparse.ArgumentParser(description=__doc__)
    common = common_parser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    _ = subparsers.add_parser("context", parents=[common], help="Report safe API and credential context")

    operations = subparsers.add_parser("operations", parents=[common], help="Discover OpenAPI operations")
    add_spec_options(operations)
    _ = operations.add_argument("--search")
    _ = operations.add_argument("--method", choices=HTTP_METHODS, dest="operation_method")
    _ = operations.add_argument("--tag")
    _ = operations.add_argument("--include-deprecated", action="store_true")

    request_parser = subparsers.add_parser("request", parents=[common], help="Preview or send a guarded v3 request")
    add_spec_options(request_parser)
    _ = request_parser.add_argument("endpoint", nargs="?")
    _ = request_parser.add_argument("--operation-id")
    _ = request_parser.add_argument("--method", choices=HTTP_METHODS)
    _ = request_parser.add_argument("--path", action="append", dest="path_values", default=[])
    _ = request_parser.add_argument("--query", action="append", default=[])
    body = request_parser.add_mutually_exclusive_group()
    _ = body.add_argument("--body-json")
    _ = body.add_argument("--body-file", type=existing_file)
    execution = request_parser.add_mutually_exclusive_group()
    _ = execution.add_argument("--send", action="store_true")
    _ = execution.add_argument("--dry-run", action="store_true")
    _ = request_parser.add_argument("--confirm")
    _ = request_parser.add_argument("--paginate", action="store_true")
    _ = request_parser.add_argument("--max-pages", type=int, default=DEFAULT_MAX_PAGES)
    return parser


def validate_arguments(arguments: argparse.Namespace) -> None:
    """Validate numeric execution bounds before any I/O."""
    _ = validated_timeout(arguments)
    _ = validated_retries(arguments)
    if arguments.command == "request" and (int(arguments.max_pages) < 1 or int(arguments.max_pages) > MAX_MAX_PAGES):
        raise UptimeRobotCliError(f"--max-pages must be between 1 and {MAX_MAX_PAGES}.")


def dispatch_command(arguments: argparse.Namespace, context: UptimeRobotContext) -> int:
    """Dispatch one validated command."""
    if arguments.command == "context":
        write_json(context_payload(context))
        return 0
    if arguments.command == "operations":
        return handle_operations(arguments, context)
    if arguments.command == "request":
        execute_plan(arguments, context, build_plan(arguments, context))
        return 0
    raise UptimeRobotCliError(f"Unsupported command: {arguments.command}")


def main() -> int:
    """Run one helper command."""
    arguments = build_parser().parse_args()
    context: UptimeRobotContext | None = None
    try:
        validate_arguments(arguments)
        context = resolve_context(arguments)
        return dispatch_command(arguments, context)
    except UptimeRobotCliError as exception:
        secrets = request_secrets(context) if context is not None else ()
        message = cast("str", redact_json(str(exception), secrets))
        _ = sys.stderr.write(f"error: {message}\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
