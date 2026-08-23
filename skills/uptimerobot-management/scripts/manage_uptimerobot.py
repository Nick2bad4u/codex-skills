#!/usr/bin/env python
# Copyright (c) 2026 Nick2bad4u
"""Discover UptimeRobot API v3 operations and execute guarded requests."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, cast, override
from urllib import error, parse, request

if TYPE_CHECKING:
    from http.client import HTTPMessage
    from typing import IO

type JsonValue = bool | int | float | str | list[JsonValue] | dict[str, JsonValue] | None

DEFAULT_BASE_URL = "https://api.uptimerobot.com/v3"
DEFAULT_SPEC_URL = "https://cdn.uptimerobot.com/api/openapi.yaml"
DEFAULT_READ_TOKEN_ENVS = ("UPTIMEROBOT_READ_ONLY_API_KEY",)
DEFAULT_MAIN_TOKEN_ENVS = ("UPTIMEROBOT_API_KEY",)
DEFAULT_TIMEOUT = 30.0
DEFAULT_RETRIES = 2
DEFAULT_MAX_PAGES = 25
MAX_MAX_PAGES = 500
MAX_RESPONSE_TEXT = 2000
MIN_QUOTED_SCALAR_LENGTH = 2
JSON_MEDIA_TYPE = "application/json"
REDACTED_VALUE = "<redacted>"
HTTP_SUCCESS_MIN = 200
HTTP_SUCCESS_LIMIT = 300
RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
SAFE_METHODS = frozenset({"GET", "HEAD"})
HTTP_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE")
YAML_HTTP_METHODS = frozenset(item.lower() for item in HTTP_METHODS)
PATH_PARAMETER = re.compile(r"\{([^{}]+)\}")
SENSITIVE_KEY_MARKERS = (
    "apikey",
    "authorization",
    "credential",
    "customhttpheaders",
    "httppassword",
    "password",
    "postvaluedata",
    "secret",
    "token",
)


class UptimeRobotCliError(RuntimeError):
    """Report a safe, user-facing helper error."""


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


@dataclass(frozen=True)
class RequestPlan:
    """Resolved request inputs before authentication or execution."""

    body: JsonValue
    confirmation_value: str | None
    high_risk: bool
    method: str
    operation_id: str | None
    query: dict[str, str]
    url: str


@dataclass(frozen=True)
class ResolvedRequestTarget:
    """Endpoint and risk metadata resolved from raw or OpenAPI inputs."""

    confirmation_value: str | None
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


@dataclass
class YamlOperationState:
    """Mutable operation metadata while reading the official YAML document."""

    deprecated: bool = False
    method: str | None = None
    operation_id: str = ""
    path: str | None = None
    reading_tags: bool = False
    summary: str = ""
    tags: list[str] = field(default_factory=list[str])

    def operation(self) -> OpenApiOperation | None:
        """Return a completed operation when all required identity fields exist."""
        if self.path is None or self.method is None or not self.operation_id:
            return None
        return OpenApiOperation(
            deprecated=self.deprecated,
            method=self.method,
            operation_id=self.operation_id,
            path=self.path,
            summary=self.summary,
            tags=tuple(self.tags),
        )

    def reset_operation(self, method: str | None = None) -> None:
        """Reset operation-local fields while preserving the current path."""
        self.deprecated = False
        self.method = method
        self.operation_id = ""
        self.reading_tags = False
        self.summary = ""
        self.tags = []


def optional_text(value: object) -> str | None:
    """Return a stripped optional string."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def is_sensitive_key(value: str) -> bool:
    """Recognize credential-like field names without a backtracking regex."""
    normalized = value.casefold().replace("-", "").replace("_", "")
    return any(marker in normalized for marker in SENSITIVE_KEY_MARKERS)


def as_string_list(value: object) -> list[str]:
    """Narrow parser-controlled repeatable string arguments."""
    return cast("list[str]", value)


def is_environment_name(value: str) -> bool:
    """Return whether a name is a portable ASCII environment identifier."""
    return value.isascii() and value.isidentifier()


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
            return Credential(environment=name, value=value)
    return None


def sanitize_base_url(value: str) -> str:
    """Lock a bearer-authenticated base URL to the production v3 API."""
    parsed = parse.urlsplit(value.strip().rstrip("/"))
    if parsed.scheme.lower() != "https" or parsed.hostname != "api.uptimerobot.com":
        raise UptimeRobotCliError("API base URL must use the production https://api.uptimerobot.com origin.")
    if parsed.username is not None or parsed.password is not None or parsed.port is not None:
        raise UptimeRobotCliError("API base URL must not contain credentials or an explicit port.")
    if parsed.query or parsed.fragment:
        raise UptimeRobotCliError("API base URL must not contain a query or fragment.")
    if parsed.path.rstrip("/") != "/v3":
        raise UptimeRobotCliError("API base URL must end with /v3.")
    return DEFAULT_BASE_URL


def validate_spec_url(value: str) -> str:
    """Lock live contract discovery to the official OpenAPI document."""
    parsed = parse.urlsplit(value.strip())
    if parsed.scheme.lower() != "https" or parsed.hostname != "cdn.uptimerobot.com":
        raise UptimeRobotCliError("OpenAPI URL must use the official UptimeRobot CDN origin.")
    if parsed.username is not None or parsed.password is not None or parsed.port is not None:
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


def openapi_operation(path: str, method: str, value: JsonValue) -> OpenApiOperation | None:
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
            operation = openapi_operation(path_name, method, path_item.get(method))
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
    state.reading_tags = field_name == "tags"
    if field_name == "operationId":
        state.operation_id = strip_yaml_scalar(value)
    elif field_name == "summary":
        state.summary = strip_yaml_scalar(value)
    elif field_name == "deprecated":
        state.deprecated = value.strip().lower() == "true"
    return True


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
        if state.method is not None and not apply_yaml_operation_field(state, line):
            apply_yaml_tag(state, line)
    append_yaml_operation(operations, state)
    if not operations:
        raise UptimeRobotCliError("Could not discover operations in the OpenAPI YAML document.")
    return operations


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


def load_operations(arguments: argparse.Namespace, context: UptimeRobotContext) -> list[OpenApiOperation]:
    """Load operation metadata from a local file or the live official contract."""
    spec_file = cast("Path | None", arguments.spec_file)
    if spec_file is not None:
        try:
            return decode_operations(spec_file.read_bytes(), source=str(spec_file))
        except OSError as exception:
            raise UptimeRobotCliError(f"Could not read OpenAPI file: {spec_file}") from exception
    opener = request.build_opener(NoRedirectHandler())
    spec_request = request.Request(  # noqa: S310  # validate_spec_url locks the URL.
        context.spec_url,
        headers={"Accept": "application/yaml, application/json", "User-Agent": "codex-uptimerobot-management/1"},
    )
    try:
        with opener.open(spec_request, timeout=float(arguments.timeout)) as response:
            return decode_operations(response.read(), source=context.spec_url)
    except error.HTTPError as exception:
        raise UptimeRobotCliError(f"OpenAPI request failed with HTTP {exception.code}.") from exception
    except error.URLError as exception:
        raise UptimeRobotCliError(f"OpenAPI request failed: {exception.reason}") from exception


def parse_pairs(values: list[str], *, label: str) -> dict[str, str]:
    """Parse repeatable name=value values with duplicate and credential guards."""
    result: dict[str, str] = {}
    for value in values:
        name, separator, item_value = value.partition("=")
        name = name.strip()
        if not separator or not name or not item_value:
            raise UptimeRobotCliError(f"{label} values must use non-empty name=value syntax.")
        if name in result:
            raise UptimeRobotCliError(f"Duplicate {label} name: {name}")
        if label == "query" and is_sensitive_key(name):
            raise UptimeRobotCliError(f"Refusing credential-like query parameter: {name}")
        result[name] = item_value
    return result


def load_body(arguments: argparse.Namespace) -> JsonValue:
    """Load an optional JSON body from one reviewed source."""
    body_text = optional_text(arguments.body_json)
    body_file = cast("Path | None", arguments.body_file)
    if body_file is not None:
        try:
            body_text = body_file.read_text(encoding="utf-8")
        except OSError as exception:
            raise UptimeRobotCliError(f"Could not read request body file: {body_file}") from exception
    if body_text is None:
        return None
    try:
        return cast("JsonValue", json.loads(body_text))
    except json.JSONDecodeError as exception:
        raise UptimeRobotCliError("Request body must be valid JSON.") from exception


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


def assert_safe_api_url(base_url: str, candidate: str, *, allow_query: bool) -> str:
    """Validate exact API origin, base path, traversal, and query safety."""
    parsed = parse.urlsplit(candidate)
    if parsed.scheme.lower() != "https" or parsed.hostname != "api.uptimerobot.com":
        raise UptimeRobotCliError("Endpoint origin must match the production UptimeRobot API.")
    if parsed.username is not None or parsed.password is not None or parsed.port is not None:
        raise UptimeRobotCliError("Endpoint must not contain credentials or an explicit port.")
    decoded_path = parse.unquote(parsed.path)
    if "\\" in decoded_path or any(part == ".." for part in decoded_path.split("/")):
        raise UptimeRobotCliError("Endpoint must not contain path traversal.")
    base_path = parse.urlsplit(base_url).path.rstrip("/")
    if parsed.path != base_path and not parsed.path.startswith(f"{base_path}/"):
        raise UptimeRobotCliError("Endpoint must remain under the configured /v3 base path.")
    if parsed.fragment or (parsed.query and not allow_query):
        raise UptimeRobotCliError("Endpoint must not contain a query or fragment; use --query.")
    for name, _ in parse.parse_qsl(parsed.query, keep_blank_values=True):
        if is_sensitive_key(name):
            raise UptimeRobotCliError(f"Refusing credential-like query parameter: {name}")
    return candidate


def validated_endpoint_url(base_url: str, endpoint: str) -> str:
    """Resolve a raw/spec endpoint while preserving the API trust boundary."""
    value = endpoint.strip()
    if not value:
        raise UptimeRobotCliError("Endpoint must not be empty.")
    if parse.urlsplit(value).query or parse.urlsplit(value).fragment:
        raise UptimeRobotCliError("Endpoint must not contain a query or fragment; use --query.")
    if value.startswith("/v3"):
        candidate = f"https://api.uptimerobot.com{value}"
    elif value.startswith("/"):
        candidate = f"{base_url}{value}"
    elif parse.urlsplit(value).scheme:
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
            confirmation_value=None,
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
        confirmation_value=operation.operation_id if high_risk else None,
        endpoint=fill_path(operation.path, parse_pairs(path_values, label="path")),
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
    url = validated_endpoint_url(context.base_url, target.endpoint)
    high_risk = target.high_risk
    confirmation_value = target.confirmation_value
    if target.operation_id is None:
        raw_path = parse.urlsplit(url).path.casefold()
        high_risk = target.method == "DELETE" or "/monitors/bulk/" in raw_path
        confirmation_value = raw_confirmation_value(target.method, url) if high_risk else None
    return RequestPlan(
        body=body,
        confirmation_value=confirmation_value,
        high_risk=high_risk,
        method=target.method,
        operation_id=target.operation_id,
        query=parse_pairs(as_string_list(arguments.query), label="query"),
        url=url,
    )


def redact_url_secrets(value: str) -> str:
    """Redact URL userinfo and credential-like query values in an exact URL string."""
    try:
        parsed = parse.urlsplit(value)
        port = parsed.port
    except ValueError:
        return value
    if parsed.scheme.lower() not in {"http", "https"} or parsed.hostname is None:
        return value
    pairs = parse.parse_qsl(parsed.query, keep_blank_values=True)
    has_sensitive_query = any(is_sensitive_key(name) for name, _ in pairs)
    has_userinfo = parsed.username is not None or parsed.password is not None
    if not has_sensitive_query and not has_userinfo:
        return value
    host = f"[{parsed.hostname}]" if ":" in parsed.hostname else parsed.hostname
    if port is not None:
        host = f"{host}:{port}"
    netloc = f"{REDACTED_VALUE}@{host}" if has_userinfo else parsed.netloc
    redacted_pairs = [(name, REDACTED_VALUE if is_sensitive_key(name) else item_value) for name, item_value in pairs]
    query = parse.urlencode(redacted_pairs, doseq=True, safe="<>")
    return parse.urlunsplit((parsed.scheme, netloc, parsed.path, query, parsed.fragment))


def redact_json(value: JsonValue, secrets: tuple[str, ...] = ()) -> JsonValue:
    """Recursively redact credential-like fields and reflected credential values."""
    if isinstance(value, dict):
        return {
            key: REDACTED_VALUE if is_sensitive_key(key) else redact_json(item, secrets) for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_json(item, secrets) for item in value]
    if isinstance(value, str):
        result = redact_url_secrets(value)
        for secret in secrets:
            if secret:
                result = result.replace(secret, REDACTED_VALUE)
        return result
    return value


def encode_url(url: str, query: dict[str, str]) -> str:
    """Append encoded query values to a validated URL."""
    parsed = parse.urlsplit(url)
    return parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parse.urlencode(query), ""))


def validated_next_url(base_url: str, current_url: str, next_link: str) -> str:
    """Resolve a cursor link without allowing credential forwarding or traversal."""
    value = next_link.strip()
    if not value:
        raise UptimeRobotCliError("Pagination nextLink must not be empty.")
    if value.startswith("?"):
        current = parse.urlsplit(current_url)
        candidate = parse.urlunsplit((current.scheme, current.netloc, current.path, value[1:], ""))
    elif value.startswith("/v3"):
        candidate = f"https://api.uptimerobot.com{value}"
    elif value.startswith("/"):
        candidate = f"{base_url}{value}"
    else:
        candidate = parse.urljoin(current_url, value)
    return assert_safe_api_url(base_url, candidate, allow_query=True)


def credential_for(context: UptimeRobotContext, method: str) -> Credential | None:
    """Prefer read-only authentication for reads and require main auth for writes."""
    if method in SAFE_METHODS:
        return context.read_credential or context.main_credential
    return context.main_credential


def response_payload(data: bytes, content_type: str) -> JsonValue:
    """Decode JSON or retain bounded external text."""
    if not data:
        return None
    if "json" in content_type.lower():
        try:
            return cast("JsonValue", json.loads(data.decode("utf-8")))
        except (UnicodeDecodeError, json.JSONDecodeError) as exception:
            raise UptimeRobotCliError("Expected JSON from the UptimeRobot API.") from exception
    return data.decode("utf-8", errors="replace")[:MAX_RESPONSE_TEXT]


def retry_delay(http_error: error.HTTPError, attempt: int) -> float:
    """Return a bounded Retry-After or exponential fallback delay."""
    value = http_error.headers.get("Retry-After", "").strip()
    try:
        return min(max(float(value), 0.0), 60.0) if value else min(2.0**attempt, 30.0)
    except ValueError:
        return min(2.0**attempt, 30.0)


def send_request(
    plan: RequestPlan,
    url: str,
    credential: Credential,
    arguments: argparse.Namespace,
) -> ApiResult:
    """Send one request, retrying only safe reads within explicit bounds."""
    headers = {
        "Accept": JSON_MEDIA_TYPE,
        "Authorization": f"Bearer {credential.value}",
        "User-Agent": "codex-uptimerobot-management/1",
    }
    body = None if plan.body is None else json.dumps(plan.body, separators=(",", ":")).encode()
    if body is not None:
        headers["Content-Type"] = JSON_MEDIA_TYPE
    opener = request.build_opener(NoRedirectHandler())
    retries = int(arguments.retries) if plan.method in SAFE_METHODS else 0
    for attempt in range(retries + 1):
        api_request = request.Request(  # noqa: S310  # URL is origin- and path-locked before this point.
            url,
            data=body,
            headers=headers,
            method=plan.method,
        )
        try:
            with opener.open(api_request, timeout=float(arguments.timeout)) as response:
                status = int(response.status)
                payload = response_payload(response.read(), response.headers.get("Content-Type", ""))
                if status < HTTP_SUCCESS_MIN or status >= HTTP_SUCCESS_LIMIT:
                    raise UptimeRobotCliError(f"API request returned unexpected HTTP {status}.")
                return ApiResult(payload=payload, status=status, url=url)
        except error.HTTPError as exception:
            if plan.method in SAFE_METHODS and exception.code in RETRYABLE_STATUS_CODES and attempt < retries:
                time.sleep(retry_delay(exception, attempt))
                continue
            raise UptimeRobotCliError(f"API request failed with HTTP {exception.code}.") from exception
        except error.URLError as exception:
            raise UptimeRobotCliError(f"API request failed: {exception.reason}") from exception
    raise UptimeRobotCliError("API request exhausted its retry budget.")


def next_link(payload: JsonValue) -> str | None:
    """Read the nullable v3 nextLink field."""
    if not isinstance(payload, dict):
        return None
    value = payload.get("nextLink")
    return value if isinstance(value, str) and value.strip() else None


def validate_execution_mode(arguments: argparse.Namespace, *, is_safe: bool) -> None:
    """Reject execution switches that conflict with request safety."""
    if bool(arguments.send) and is_safe:
        raise UptimeRobotCliError("--send is only valid for mutating requests; reads execute without it.")
    if bool(arguments.paginate) and not is_safe:
        raise UptimeRobotCliError("--paginate is only valid for safe read requests.")


def request_secrets(context: UptimeRobotContext) -> tuple[str, ...]:
    """Return configured secret values for reflected-response redaction."""
    return tuple(item.value for item in (context.read_credential, context.main_credential) if item is not None)


def write_preview(context: UptimeRobotContext, plan: RequestPlan, initial_url: str, secrets: tuple[str, ...]) -> None:
    """Write a deterministic, credential-safe request preview."""
    credential = credential_for(context, plan.method)
    write_json(
        {
            "confirmationRequired": plan.high_risk,
            "confirmationValue": plan.confirmation_value,
            "credentialEnvironment": credential.environment if credential else None,
            "dryRun": True,
            "request": {
                "body": redact_json(plan.body, secrets),
                "method": plan.method,
                "operationId": plan.operation_id,
                "url": initial_url,
            },
        }
    )


def require_credential(context: UptimeRobotContext, plan: RequestPlan, *, is_safe: bool) -> Credential:
    """Resolve the least-privileged credential or fail before network access."""
    credential = credential_for(context, plan.method)
    if credential is None:
        role = "read-only or main" if is_safe else "main"
        raise UptimeRobotCliError(f"No {role} credential is configured for this request.")
    return credential


def result_payload(result: ApiResult, secrets: tuple[str, ...]) -> dict[str, JsonValue]:
    """Build one redacted API response object."""
    return {
        "data": redact_json(result.payload, secrets),
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
    for _ in range(int(arguments.max_pages)):
        result = send_request(plan, current_url, credential, arguments)
        pages.append(result_payload(result, secrets))
        pending_link = next_link(result.payload)
        if pending_link is None:
            break
        current_url = validated_next_url(context.base_url, current_url, pending_link)
    write_json(
        {
            "complete": pending_link is None,
            "nextLink": pending_link,
            "pageCount": len(pages),
            "pages": pages,
        }
    )


def execute_plan(arguments: argparse.Namespace, context: UptimeRobotContext, plan: RequestPlan) -> None:
    """Preview a write/read or execute a credentialed request."""
    is_safe = plan.method in SAFE_METHODS
    validate_execution_mode(arguments, is_safe=is_safe)
    preview = bool(arguments.dry_run) or (not is_safe and not bool(arguments.send))
    initial_url = encode_url(plan.url, plan.query)
    secrets = request_secrets(context)
    if preview:
        write_preview(context, plan, initial_url, secrets)
        return

    credential = require_credential(context, plan, is_safe=is_safe)
    if plan.high_risk and optional_text(arguments.confirm) != plan.confirmation_value:
        raise UptimeRobotCliError(f"High-impact request requires --confirm {plan.confirmation_value!r}.")
    if bool(arguments.paginate):
        write_paginated_results(arguments, context, plan, credential, initial_url)
        return
    write_json(
        result_payload(
            send_request(plan, initial_url, credential, arguments),
            secrets,
        )
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
    write_json({"count": len(selected), "operations": [cast("JsonValue", asdict(item)) for item in selected]})
    return 0


def write_json(value: JsonValue) -> None:
    """Write deterministic human-readable JSON."""
    json.dump(value, sys.stdout, indent=2, sort_keys=True)
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
    if float(arguments.timeout) <= 0:
        raise UptimeRobotCliError("--timeout must be greater than zero.")
    if int(arguments.retries) < 0 or int(arguments.retries) > 10:  # noqa: PLR2004  # Explicit safety cap.
        raise UptimeRobotCliError("--retries must be between 0 and 10.")
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
    try:
        validate_arguments(arguments)
        return dispatch_command(arguments, resolve_context(arguments))
    except UptimeRobotCliError as exception:
        _ = sys.stderr.write(f"error: {exception}\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
