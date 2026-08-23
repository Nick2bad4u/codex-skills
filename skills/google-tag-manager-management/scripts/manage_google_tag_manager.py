#!/usr/bin/env python
# Copyright (c) 2026 Nick2bad4u
"""Discover Google Tag Manager API v2 operations and execute guarded requests."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, cast, override
from urllib import error, parse, request

if TYPE_CHECKING:
    from http.client import HTTPMessage
    from typing import IO

type JsonValue = bool | int | float | str | list[JsonValue] | dict[str, JsonValue] | None

DEFAULT_BASE_URL = "https://tagmanager.googleapis.com/tagmanager/v2"
DEFAULT_DISCOVERY_URL = "https://tagmanager.googleapis.com/$discovery/rest?version=v2"
DEFAULT_TOKEN_ENVS = ("GOOGLE_TAG_MANAGER_ACCESS_TOKEN", "GTM_ACCESS_TOKEN")
DEFAULT_TIMEOUT = 30.0
DEFAULT_RETRIES = 2
DEFAULT_MAX_PAGES = 25
MAX_MAX_PAGES = 500
MAX_RESPONSE_TEXT = 2000
JSON_MEDIA_TYPE = "application/json"
HTTP_SUCCESS_MIN = 200
HTTP_SUCCESS_LIMIT = 300
RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
SAFE_METHODS = frozenset({"GET", "HEAD"})
HTTP_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE")
GLOBAL_QUERY_PARAMETERS = frozenset({"alt", "fields", "prettyPrint", "quotaUser"})
PATH_PARAMETER = re.compile(r"\{(\+?)([^{}]+)\}")
SENSITIVE_KEY = re.compile(
    r"""
    access[-_]?token
    | api[-_]?key
    | authorization
    | client[-_]?secret
    | credential
    | oauth[-_]?token
    | password
    | private[-_]?key
    | refresh[-_]?token
    | secret
    | token
    """,
    re.IGNORECASE | re.VERBOSE,
)


class GoogleTagManagerCliError(RuntimeError):
    """Report a safe, user-facing helper error."""


class NoRedirectHandler(request.HTTPRedirectHandler):
    """Reject redirects so OAuth credentials never cross a trust boundary."""

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
    """One resolved short-lived OAuth credential."""

    environment: str
    value: str


@dataclass(frozen=True)
class GoogleTagManagerContext:
    """Validated API/Discovery targets and optional OAuth context."""

    base_url: str
    credential: Credential | None
    discovery_url: str


@dataclass(frozen=True)
class OperationParameter:
    """One documented Discovery method parameter."""

    location: str
    name: str
    required: bool


@dataclass(frozen=True)
class DiscoveryOperation:
    """Small stable view of one Discovery API method."""

    description: str
    has_request_body: bool
    method: str
    operation_id: str
    parameters: tuple[OperationParameter, ...]
    path: str
    scopes: tuple[str, ...]


@dataclass(frozen=True)
class RequestPlan:
    """Resolved request details and safety metadata."""

    body: JsonValue
    confirmation_value: str | None
    high_risk: bool
    method: str
    operation_id: str | None
    query: dict[str, str]
    required_scopes: tuple[str, ...]
    supports_page_token: bool
    url: str


@dataclass(frozen=True)
class ApiResult:
    """One Tag Manager API response page."""

    payload: JsonValue
    status: int
    url: str


def optional_text(value: object) -> str | None:
    """Return a stripped optional string."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


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


def resolve_credential(names: list[str]) -> Credential | None:
    """Resolve the first populated token from validated environment names."""
    candidates = names or list(DEFAULT_TOKEN_ENVS)
    for name in candidates:
        if not is_environment_name(name):
            raise GoogleTagManagerCliError(f"Invalid token environment variable name: {name}")
        value = os.environ.get(name, "").strip()
        if value:
            return Credential(environment=name, value=value)
    return None


def sanitize_base_url(value: str) -> str:
    """Lock OAuth-authenticated requests to the production v2 service path."""
    parsed = parse.urlsplit(value.strip().rstrip("/"))
    if parsed.scheme.lower() != "https" or parsed.hostname != "tagmanager.googleapis.com":
        raise GoogleTagManagerCliError("API base URL must use the production Tag Manager Google API origin.")
    if parsed.username is not None or parsed.password is not None or parsed.port is not None:
        raise GoogleTagManagerCliError("API base URL must not contain credentials or an explicit port.")
    if parsed.query or parsed.fragment:
        raise GoogleTagManagerCliError("API base URL must not contain a query or fragment.")
    if parsed.path.rstrip("/") != "/tagmanager/v2":
        raise GoogleTagManagerCliError("API base URL must end with /tagmanager/v2.")
    return DEFAULT_BASE_URL


def validate_discovery_url(value: str) -> str:
    """Lock contract discovery to Google's Tag Manager v2 document."""
    parsed = parse.urlsplit(value.strip())
    if parsed.scheme.lower() != "https" or parsed.hostname != "tagmanager.googleapis.com":
        raise GoogleTagManagerCliError("Discovery URL must use the production Tag Manager Google API origin.")
    if parsed.username is not None or parsed.password is not None or parsed.port is not None:
        raise GoogleTagManagerCliError("Discovery URL must not contain credentials or an explicit port.")
    if parsed.path != "/$discovery/rest" or parsed.fragment:
        raise GoogleTagManagerCliError("Discovery URL must use the /$discovery/rest endpoint.")
    if parse.parse_qsl(parsed.query, keep_blank_values=True) != [("version", "v2")]:
        raise GoogleTagManagerCliError("Discovery URL must contain only version=v2.")
    return DEFAULT_DISCOVERY_URL


def resolve_context(arguments: argparse.Namespace) -> GoogleTagManagerContext:
    """Resolve validated URLs and an optional access token."""
    return GoogleTagManagerContext(
        base_url=sanitize_base_url(str(arguments.base_url)),
        credential=resolve_credential(as_string_list(arguments.token_envs)),
        discovery_url=validate_discovery_url(str(arguments.discovery_url)),
    )


def context_payload(context: GoogleTagManagerContext) -> dict[str, JsonValue]:
    """Build an output-safe context report without token introspection."""
    return {
        "accessToken": {
            "configured": context.credential is not None,
            "environment": context.credential.environment if context.credential else None,
            "scopesVerified": False,
        },
        "baseUrl": context.base_url,
        "discoveryUrl": context.discovery_url,
    }


def decode_json(data: bytes, *, source: str) -> dict[str, JsonValue]:
    """Decode a UTF-8 JSON object with a bounded error."""
    try:
        payload = cast("JsonValue", json.loads(data.decode("utf-8")))
    except (UnicodeDecodeError, json.JSONDecodeError) as exception:
        raise GoogleTagManagerCliError(f"Expected JSON from {source}.") from exception
    if not isinstance(payload, dict):
        raise GoogleTagManagerCliError(f"Expected a JSON object from {source}.")
    return payload


def validate_discovery_document(payload: dict[str, JsonValue]) -> None:
    """Reject unrelated or malformed Discovery documents."""
    if payload.get("name") != "tagmanager" or payload.get("version") != "v2":
        raise GoogleTagManagerCliError("Discovery document must describe tagmanager v2.")
    if not isinstance(payload.get("resources"), dict):
        raise GoogleTagManagerCliError("Discovery document does not contain a resources object.")


def load_discovery(arguments: argparse.Namespace, context: GoogleTagManagerContext) -> dict[str, JsonValue]:
    """Load a local or live Tag Manager Discovery document."""
    discovery_file = cast("Path | None", arguments.discovery_file)
    if discovery_file is not None:
        try:
            payload = decode_json(discovery_file.read_bytes(), source=str(discovery_file))
        except OSError as exception:
            raise GoogleTagManagerCliError(f"Could not read Discovery file: {discovery_file}") from exception
    else:
        opener = request.build_opener(NoRedirectHandler())
        discovery_request = request.Request(  # noqa: S310  # validate_discovery_url locks this URL.
            context.discovery_url,
            headers={"Accept": JSON_MEDIA_TYPE, "User-Agent": "codex-google-tag-manager-management/1"},
        )
        try:
            with opener.open(discovery_request, timeout=float(arguments.timeout)) as response:
                payload = decode_json(response.read(), source=context.discovery_url)
        except error.HTTPError as exception:
            raise GoogleTagManagerCliError(f"Discovery request failed with HTTP {exception.code}.") from exception
        except error.URLError as exception:
            raise GoogleTagManagerCliError(f"Discovery request failed: {exception.reason}") from exception
    validate_discovery_document(payload)
    return payload


def parse_parameter(name: str, value: JsonValue) -> OperationParameter | None:
    """Normalize a documented path or query parameter."""
    if not isinstance(value, dict):
        return None
    location = value.get("location")
    if location not in {"path", "query"}:
        return None
    return OperationParameter(location=location, name=name, required=value.get("required") is True)


def parse_method(value: JsonValue) -> DiscoveryOperation | None:
    """Normalize one Discovery method object."""
    if not isinstance(value, dict):
        return None
    operation_id = value.get("id")
    path = value.get("path")
    method = value.get("httpMethod")
    if not all(isinstance(item, str) and item for item in (operation_id, path, method)):
        return None
    parameters_value = value.get("parameters")
    parameters: list[OperationParameter] = []
    if isinstance(parameters_value, dict):
        for name, parameter_value in parameters_value.items():
            parameter = parse_parameter(name, parameter_value)
            if parameter is not None:
                parameters.append(parameter)
    scopes_value = value.get("scopes")
    description = value.get("description")
    return DiscoveryOperation(
        description=description if isinstance(description, str) else "",
        has_request_body=isinstance(value.get("request"), dict),
        method=cast("str", method).upper(),
        operation_id=cast("str", operation_id),
        parameters=tuple(sorted(parameters, key=lambda item: (item.location, item.name))),
        path=cast("str", path),
        scopes=tuple(item for item in scopes_value if isinstance(item, str)) if isinstance(scopes_value, list) else (),
    )


def walk_resources(resources: dict[str, JsonValue], operations: list[DiscoveryOperation]) -> None:
    """Recursively extract methods from nested Discovery resources."""
    for resource_value in resources.values():
        if not isinstance(resource_value, dict):
            continue
        methods = resource_value.get("methods")
        if isinstance(methods, dict):
            for method_value in methods.values():
                operation = parse_method(method_value)
                if operation is not None:
                    operations.append(operation)
        children = resource_value.get("resources")
        if isinstance(children, dict):
            walk_resources(children, operations)


def parse_operations(payload: dict[str, JsonValue]) -> list[DiscoveryOperation]:
    """Extract all current operations from a validated Discovery document."""
    resources = payload.get("resources")
    if not isinstance(resources, dict):
        raise GoogleTagManagerCliError("Discovery document does not contain a resources object.")
    operations: list[DiscoveryOperation] = []
    walk_resources(resources, operations)
    if not operations:
        raise GoogleTagManagerCliError("Discovery document did not expose any operations.")
    return sorted(operations, key=lambda item: item.operation_id)


def load_operations(arguments: argparse.Namespace, context: GoogleTagManagerContext) -> list[DiscoveryOperation]:
    """Load and parse current operation metadata."""
    return parse_operations(load_discovery(arguments, context))


def parse_pairs(values: list[str], *, label: str) -> dict[str, str]:
    """Parse repeatable name=value arguments with duplicate and credential guards."""
    result: dict[str, str] = {}
    for value in values:
        name, separator, item_value = value.partition("=")
        name = name.strip()
        if not separator or not name or not item_value:
            raise GoogleTagManagerCliError(f"{label} values must use non-empty name=value syntax.")
        if name in result:
            raise GoogleTagManagerCliError(f"Duplicate {label} name: {name}")
        if label == "query" and SENSITIVE_KEY.search(name):
            raise GoogleTagManagerCliError(f"Refusing credential-like query parameter: {name}")
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
            raise GoogleTagManagerCliError(f"Could not read request body file: {body_file}") from exception
    if body_text is None:
        return None
    try:
        return cast("JsonValue", json.loads(body_text))
    except json.JSONDecodeError as exception:
        raise GoogleTagManagerCliError("Request body must be valid JSON.") from exception


def operation_by_id(operations: list[DiscoveryOperation], operation_id: str) -> DiscoveryOperation:
    """Resolve exactly one case-sensitive Discovery operation ID."""
    matches = [operation for operation in operations if operation.operation_id == operation_id]
    if len(matches) != 1:
        raise GoogleTagManagerCliError("operation ID must resolve exactly once in the Discovery document.")
    return matches[0]


def fill_path(path_template: str, values: dict[str, str]) -> str:
    """Fill simple and reserved-expansion path parameters."""
    required = [name for _, name in PATH_PARAMETER.findall(path_template)]
    missing = [name for name in required if name not in values]
    unused = [name for name in values if name not in required]
    if missing:
        raise GoogleTagManagerCliError(f"Missing path parameter(s): {', '.join(missing)}")
    if unused:
        raise GoogleTagManagerCliError(f"Unused path parameter(s): {', '.join(unused)}")

    def replace(match: re.Match[str]) -> str:
        reserved, name = match.groups()
        return parse.quote(values[name], safe="/" if reserved else "")

    return PATH_PARAMETER.sub(replace, path_template)


def assert_safe_api_url(base_url: str, candidate: str, *, allow_query: bool) -> str:
    """Validate exact origin, service path, traversal, and query safety."""
    parsed = parse.urlsplit(candidate)
    if parsed.scheme.lower() != "https" or parsed.hostname != "tagmanager.googleapis.com":
        raise GoogleTagManagerCliError("Endpoint origin must match the production Tag Manager API.")
    if parsed.username is not None or parsed.password is not None or parsed.port is not None:
        raise GoogleTagManagerCliError("Endpoint must not contain credentials or an explicit port.")
    decoded_path = parse.unquote(parsed.path)
    if "\\" in decoded_path or any(part == ".." for part in decoded_path.split("/")):
        raise GoogleTagManagerCliError("Endpoint must not contain path traversal.")
    base_path = parse.urlsplit(base_url).path.rstrip("/")
    if parsed.path != base_path and not parsed.path.startswith(f"{base_path}/"):
        raise GoogleTagManagerCliError("Endpoint must remain under the /tagmanager/v2 service path.")
    if parsed.fragment or (parsed.query and not allow_query):
        raise GoogleTagManagerCliError("Endpoint must not contain a query or fragment; use --query.")
    for name, _ in parse.parse_qsl(parsed.query, keep_blank_values=True):
        if SENSITIVE_KEY.search(name):
            raise GoogleTagManagerCliError(f"Refusing credential-like query parameter: {name}")
    return candidate


def validated_endpoint_url(base_url: str, endpoint: str) -> str:
    """Resolve raw and Discovery paths inside the API trust boundary."""
    value = endpoint.strip()
    if not value:
        raise GoogleTagManagerCliError("Endpoint must not be empty.")
    parsed_value = parse.urlsplit(value)
    if parsed_value.query or parsed_value.fragment:
        raise GoogleTagManagerCliError("Endpoint must not contain a query or fragment; use --query.")
    if value.startswith("tagmanager/v2/") or value == "tagmanager/v2":
        candidate = f"https://tagmanager.googleapis.com/{value}"
    elif value.startswith("/tagmanager/v2"):
        candidate = f"https://tagmanager.googleapis.com{value}"
    elif value.startswith("/"):
        candidate = f"{base_url}{value}"
    elif parsed_value.scheme:
        candidate = value
    else:
        raise GoogleTagManagerCliError("Relative endpoint must start with /.")
    return assert_safe_api_url(base_url, candidate, allow_query=False)


def validate_operation_query(operation: DiscoveryOperation, query: dict[str, str]) -> None:
    """Reject query names absent from the live Discovery method."""
    allowed = {item.name for item in operation.parameters if item.location == "query"} | set(GLOBAL_QUERY_PARAMETERS)
    unknown = sorted(set(query) - allowed)
    if unknown:
        raise GoogleTagManagerCliError(f"Unknown query parameter(s) for operation: {', '.join(unknown)}")


def operation_is_high_risk(operation: DiscoveryOperation) -> bool:
    """Identify operations requiring a second exact confirmation."""
    operation_id = operation.operation_id.casefold()
    return (
        operation.method == "DELETE"
        or operation_id.endswith((".publish", ".create_version"))
        or ".user_permissions." in operation_id
    )


def raw_confirmation_value(method: str, url: str) -> str:
    """Build the exact confirmation phrase for a raw high-risk request."""
    path = parse.urlsplit(url).path.removeprefix("/tagmanager/v2") or "/"
    return f"{method} {path}"


def build_plan(arguments: argparse.Namespace, context: GoogleTagManagerContext) -> RequestPlan:
    """Build a raw or Discovery-operation request plan."""
    endpoint = optional_text(arguments.endpoint)
    operation_id = optional_text(arguments.operation_id)
    if endpoint is not None and operation_id is not None:
        raise GoogleTagManagerCliError("Provide either an endpoint or --operation-id, not both.")
    if endpoint is None and operation_id is None:
        raise GoogleTagManagerCliError("Provide an endpoint or --operation-id.")
    method = optional_text(arguments.method)
    query = parse_pairs(as_string_list(arguments.query), label="query")
    body = load_body(arguments)
    required_scopes: tuple[str, ...] = ()
    supports_page_token = True
    high_risk = False
    confirmation_value: str | None = None
    if operation_id is not None:
        operation = operation_by_id(load_operations(arguments, context), operation_id)
        if method is not None and method.upper() != operation.method:
            raise GoogleTagManagerCliError("--method conflicts with the Discovery operation.")
        method = operation.method
        path_values = parse_pairs(as_string_list(arguments.path_values), label="path")
        endpoint = fill_path(operation.path, path_values)
        validate_operation_query(operation, query)
        if operation.has_request_body and body is None:
            raise GoogleTagManagerCliError("Discovery operation requires a JSON request body.")
        if not operation.has_request_body and body is not None:
            raise GoogleTagManagerCliError("Discovery operation does not accept a JSON request body.")
        required_scopes = operation.scopes
        supports_page_token = any(
            item.location == "query" and item.name == "pageToken" for item in operation.parameters
        )
        high_risk = operation_is_high_risk(operation)
        confirmation_value = operation.operation_id if high_risk else None
    elif as_string_list(arguments.path_values):
        raise GoogleTagManagerCliError("--path requires --operation-id.")
    method = (method or "GET").upper()
    if method in SAFE_METHODS and body is not None:
        raise GoogleTagManagerCliError(f"{method} requests must not include a body.")
    url = validated_endpoint_url(context.base_url, cast("str", endpoint))
    if operation_id is None:
        raw_path = parse.urlsplit(url).path.casefold()
        high_risk = method == "DELETE" or ":publish" in raw_path or ":create_version" in raw_path
        high_risk = high_risk or "/user_permissions" in raw_path
        confirmation_value = raw_confirmation_value(method, url) if high_risk else None
    return RequestPlan(
        body=body,
        confirmation_value=confirmation_value,
        high_risk=high_risk,
        method=method,
        operation_id=operation_id,
        query=query,
        required_scopes=required_scopes,
        supports_page_token=supports_page_token,
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
    has_sensitive_query = any(SENSITIVE_KEY.search(name) for name, _ in pairs)
    has_userinfo = parsed.username is not None or parsed.password is not None
    if not has_sensitive_query and not has_userinfo:
        return value
    host = f"[{parsed.hostname}]" if ":" in parsed.hostname else parsed.hostname
    if port is not None:
        host = f"{host}:{port}"
    netloc = f"<redacted>@{host}" if has_userinfo else parsed.netloc
    redacted_pairs = [(name, "<redacted>" if SENSITIVE_KEY.search(name) else item_value) for name, item_value in pairs]
    query = parse.urlencode(redacted_pairs, doseq=True, safe="<>")
    return parse.urlunsplit((parsed.scheme, netloc, parsed.path, query, parsed.fragment))


def redact_json(value: JsonValue, secret: str | None = None) -> JsonValue:
    """Recursively redact credential-like fields and reflected token values."""
    if isinstance(value, dict):
        return {
            key: "<redacted>" if SENSITIVE_KEY.search(key) else redact_json(item, secret) for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_json(item, secret) for item in value]
    if isinstance(value, str):
        result = redact_url_secrets(value)
        return result.replace(secret, "<redacted>") if secret else result
    return value


def encode_url(url: str, query: dict[str, str]) -> str:
    """Append encoded query parameters to a validated URL."""
    parsed = parse.urlsplit(url)
    return parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parse.urlencode(query), ""))


def response_payload(data: bytes, content_type: str) -> JsonValue:
    """Decode JSON or retain bounded external text."""
    if not data:
        return None
    if "json" in content_type.lower():
        try:
            return cast("JsonValue", json.loads(data.decode("utf-8")))
        except (UnicodeDecodeError, json.JSONDecodeError) as exception:
            raise GoogleTagManagerCliError("Expected JSON from the Tag Manager API.") from exception
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
        "User-Agent": "codex-google-tag-manager-management/1",
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
                    raise GoogleTagManagerCliError(f"API request returned unexpected HTTP {status}.")
                return ApiResult(payload=payload, status=status, url=url)
        except error.HTTPError as exception:
            if plan.method in SAFE_METHODS and exception.code in RETRYABLE_STATUS_CODES and attempt < retries:
                time.sleep(retry_delay(exception, attempt))
                continue
            raise GoogleTagManagerCliError(f"API request failed with HTTP {exception.code}.") from exception
        except error.URLError as exception:
            raise GoogleTagManagerCliError(f"API request failed: {exception.reason}") from exception
    raise GoogleTagManagerCliError("API request exhausted its retry budget.")


def next_page_token(payload: JsonValue) -> str | None:
    """Read a nullable Google list-response page token."""
    if not isinstance(payload, dict):
        return None
    value = payload.get("nextPageToken")
    return value if isinstance(value, str) and value.strip() else None


def preview_payload(plan: RequestPlan, context: GoogleTagManagerContext, url: str) -> dict[str, JsonValue]:
    """Build a redacted request preview with authorization requirements."""
    return {
        "confirmationRequired": plan.high_risk,
        "confirmationValue": plan.confirmation_value,
        "credentialEnvironment": context.credential.environment if context.credential else None,
        "dryRun": True,
        "request": {
            "body": redact_json(plan.body, context.credential.value if context.credential else None),
            "method": plan.method,
            "operationId": plan.operation_id,
            "requiredScopes": list(plan.required_scopes),
            "url": url,
        },
    }


def execute_plan(arguments: argparse.Namespace, context: GoogleTagManagerContext, plan: RequestPlan) -> int:
    """Preview or execute one guarded request, optionally traversing pages."""
    is_safe = plan.method in SAFE_METHODS
    if bool(arguments.send) and is_safe:
        raise GoogleTagManagerCliError("--send is only valid for mutating requests; reads execute without it.")
    if bool(arguments.paginate) and not is_safe:
        raise GoogleTagManagerCliError("--paginate is only valid for safe read requests.")
    if bool(arguments.paginate) and plan.operation_id is not None and not plan.supports_page_token:
        raise GoogleTagManagerCliError("Discovery operation does not support pageToken pagination.")
    initial_url = encode_url(plan.url, plan.query)
    preview = bool(arguments.dry_run) or (not is_safe and not bool(arguments.send))
    if preview:
        write_json(preview_payload(plan, context, initial_url))
        return 0
    if context.credential is None:
        raise GoogleTagManagerCliError("No OAuth access token is configured for this request.")
    if plan.high_risk and optional_text(arguments.confirm) != plan.confirmation_value:
        raise GoogleTagManagerCliError(f"High-impact request requires --confirm {plan.confirmation_value!r}.")
    if not bool(arguments.paginate):
        result = send_request(plan, initial_url, context.credential, arguments)
        write_json(
            {
                "data": redact_json(result.payload, context.credential.value),
                "status": result.status,
                "url": result.url,
            }
        )
        return 0
    pages: list[JsonValue] = []
    query = dict(plan.query)
    pending_token: str | None = None
    for _ in range(int(arguments.max_pages)):
        current_url = encode_url(plan.url, query)
        result = send_request(plan, current_url, context.credential, arguments)
        pages.append(
            {
                "data": redact_json(result.payload, context.credential.value),
                "status": result.status,
                "url": result.url,
            }
        )
        pending_token = next_page_token(result.payload)
        if pending_token is None:
            break
        query["pageToken"] = pending_token
    write_json(
        {
            "complete": pending_token is None,
            "nextPageToken": pending_token,
            "pageCount": len(pages),
            "pages": pages,
        }
    )
    return 0


def handle_operations(arguments: argparse.Namespace, context: GoogleTagManagerContext) -> int:
    """Filter and print current Discovery operation metadata."""
    operations = load_operations(arguments, context)
    search = (optional_text(arguments.search) or "").casefold()
    method = (optional_text(arguments.operation_method) or "").upper()
    scope = (optional_text(arguments.scope) or "").casefold()
    selected = [
        operation
        for operation in operations
        if (not method or operation.method == method)
        and (not scope or any(scope in item.casefold() for item in operation.scopes))
        and (not search or search in f"{operation.operation_id} {operation.path} {operation.description}".casefold())
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
    _ = parser.add_argument("--discovery-url", default=DEFAULT_DISCOVERY_URL)
    _ = parser.add_argument("--token-env", action="append", dest="token_envs", default=[])
    _ = parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    _ = parser.add_argument("--retries", type=int, default=DEFAULT_RETRIES)
    return parser


def add_discovery_options(parser: argparse.ArgumentParser) -> None:
    """Add local/live Discovery selection."""
    _ = parser.add_argument("--discovery-file", type=existing_file)


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line interface."""
    parser = argparse.ArgumentParser(description=__doc__)
    common = common_parser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    _ = subparsers.add_parser("context", parents=[common], help="Report safe OAuth and API context")

    operations = subparsers.add_parser("operations", parents=[common], help="Discover API operations")
    add_discovery_options(operations)
    _ = operations.add_argument("--search")
    _ = operations.add_argument("--method", choices=HTTP_METHODS, dest="operation_method")
    _ = operations.add_argument("--scope")

    request_parser = subparsers.add_parser("request", parents=[common], help="Preview or send a guarded request")
    add_discovery_options(request_parser)
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
        raise GoogleTagManagerCliError("--timeout must be greater than zero.")
    if int(arguments.retries) < 0 or int(arguments.retries) > 10:  # noqa: PLR2004  # Explicit safety cap.
        raise GoogleTagManagerCliError("--retries must be between 0 and 10.")
    if arguments.command == "request" and (int(arguments.max_pages) < 1 or int(arguments.max_pages) > MAX_MAX_PAGES):
        raise GoogleTagManagerCliError(f"--max-pages must be between 1 and {MAX_MAX_PAGES}.")


def dispatch_command(arguments: argparse.Namespace, context: GoogleTagManagerContext) -> int:
    """Dispatch one validated command."""
    if arguments.command == "context":
        write_json(context_payload(context))
        return 0
    if arguments.command == "operations":
        return handle_operations(arguments, context)
    if arguments.command == "request":
        return execute_plan(arguments, context, build_plan(arguments, context))
    raise GoogleTagManagerCliError(f"Unsupported command: {arguments.command}")


def main() -> int:
    """Run one helper command."""
    arguments = build_parser().parse_args()
    try:
        validate_arguments(arguments)
        return dispatch_command(arguments, resolve_context(arguments))
    except GoogleTagManagerCliError as exception:
        _ = sys.stderr.write(f"error: {exception}\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
