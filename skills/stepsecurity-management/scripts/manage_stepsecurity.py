#!/usr/bin/env python3
# Copyright (c) 2026 Nick2bad4u
"""Constrained StepSecurity REST inspection and request helper."""

from __future__ import annotations

import argparse
import http.client
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Never, cast, override

if TYPE_CHECKING:
    from collections.abc import Callable
    from http.client import HTTPMessage, HTTPResponse
    from typing import IO

BASE_URL = "https://agent.api.stepsecurity.io/v1"
JSON_MEDIA_TYPE = "application/json"
HTTP_METHODS = {"delete", "get", "patch", "post", "put"}
READ_METHODS = {"GET", "HEAD", "OPTIONS"}
RETRY_STATUSES = {429, 502, 503, 504}
REDIRECT_STATUSES = {301, 302, 303, 307, 308}
MAX_API_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_ERROR_RESPONSE_BYTES = 16 * 1024
MAX_PAGINATED_RESPONSE_BYTES = 32 * 1024 * 1024
MAX_REDIRECTS = 5
MAX_PAGES = 1000
MAX_RETRIES = 10
MAX_TRANSPORT_ERROR_TEXT = 1000
MAX_JSON_DEPTH = 64
MAX_OUTPUT_JSON_DEPTH = MAX_JSON_DEPTH + 8
SENSITIVE_NAME = re.compile(r"(?:api[-_]?key|authorization|cookie|credential|password|secret|token)", re.IGNORECASE)
REDACTED_VALUE = "<redacted>"
OWNER_FROM_REMOTE = re.compile(r"github\.com[:/](?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?$", re.IGNORECASE)
CONTEXT_PATH_NAMES = {
    "organization": "org",
    "organisation": "org",
    "org": "org",
    "owner": "org",
    "customer": "customer",
    "tenant": "customer",
}


class StepSecurityError(RuntimeError):
    """Expected user-facing failure."""


@dataclass(frozen=True)
class Context:
    """Resolved tenant and authentication context."""

    base_url: str
    organization: str | None
    customer: str | None
    repository: str | None
    credential_source: str | None
    credential_present: bool


@dataclass(frozen=True)
class Operation:
    """Relevant OpenAPI operation metadata."""

    operation_id: str
    method: str
    path: str
    summary: str
    tags: list[str]
    parameters: list[dict[str, object]]
    request_body_required: bool


@dataclass(frozen=True)
class RequestRuntime:
    """Network timeout and retry controls."""

    retries: int
    timeout: float
    max_response_bytes: int = MAX_API_RESPONSE_BYTES

    def __post_init__(self) -> None:
        """Reject runtime values that could disable transport limits."""
        if not math.isfinite(self.timeout) or self.timeout <= 0:
            raise StepSecurityError("--timeout must be a finite value greater than zero")
        if not 0 <= self.retries <= MAX_RETRIES:
            raise StepSecurityError(f"--retries must be between 0 and {MAX_RETRIES}")
        if not 1 <= self.max_response_bytes <= MAX_API_RESPONSE_BYTES:
            raise StepSecurityError(f"Response byte limit must be between 1 and {MAX_API_RESPONSE_BYTES}")


@dataclass(frozen=True)
class ApiResult:
    """One bounded StepSecurity API response."""

    headers: dict[str, str]
    payload: object
    response_bytes: int
    status: int


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """Return redirect responses so their targets can be validated."""

    @override
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: IO[bytes],
        code: int,
        msg: str,
        headers: HTTPMessage,
        newurl: str,
    ) -> urllib.request.Request | None:
        """Expose redirects as HTTP errors for same-origin validation."""
        del req, fp, code, msg, headers, newurl
        return None


def emit(value: object) -> None:
    """Write deterministic JSON."""
    output = safe_json_dumps(
        value,
        label="StepSecurity command output",
        indent=2,
        sort_keys=True,
    )
    _ = sys.stdout.write(f"{output}\n")


def parse_pairs(values: list[str] | None, label: str) -> dict[str, str]:
    """Parse repeated name=value arguments."""
    result: dict[str, str] = {}
    for value in values or []:
        if "=" not in value:
            raise StepSecurityError(f"{label} must use name=value: {value!r}")
        name, item = value.split("=", 1)
        name = name.strip()
        if not name:
            raise StepSecurityError(f"{label} name cannot be empty")
        if name in result:
            raise StepSecurityError(f"Duplicate {label} name: {name}")
        result[name] = item
    return result


def normalize_repo(value: str | None) -> str | None:
    """Normalize an owner/repository selector."""
    if value is None:
        return None
    candidate = value.strip().strip("/")
    if candidate.count("/") != 1:
        raise StepSecurityError("--repo must use owner/repository")
    return candidate


def git_remote() -> str | None:
    """Read the current repository's origin without raising."""
    git = shutil.which("git")
    if git is None:
        return None
    completed = subprocess.run(  # noqa: S603  # shutil.which resolves the fixed git executable.
        [git, "remote", "get-url", "origin"],
        capture_output=True,
        check=False,
        text=True,
    )
    if completed.returncode != 0:
        return None
    return completed.stdout.strip() or None


def inferred_repo() -> str | None:
    """Infer owner/repository from a GitHub origin."""
    remote = git_remote()
    if remote is None:
        return None
    match = OWNER_FROM_REMOTE.search(remote)
    if match is None:
        return None
    return f"{match.group('owner')}/{match.group('repo')}"


def resolve_context(arguments: argparse.Namespace) -> Context:
    """Resolve explicit flags, environment, and safe repository inference."""
    repository = normalize_repo(getattr(arguments, "repo", None)) or inferred_repo()
    inferred_owner = repository.split("/", 1)[0] if repository else None
    organization = getattr(arguments, "org", None) or inferred_owner
    customer = getattr(arguments, "customer", None) or os.environ.get("STEP_SECURITY_CUSTOMER")
    if os.environ.get("STEP_SECURITY_API_KEY"):
        credential_source = "STEP_SECURITY_API_KEY"
    elif os.environ.get("STEPSECURITY_API_KEY"):
        credential_source = "STEPSECURITY_API_KEY"
    else:
        credential_source = None
    return Context(
        base_url=BASE_URL,
        organization=organization,
        customer=customer,
        repository=repository,
        credential_source=credential_source,
        credential_present=credential_source is not None,
    )


def credential() -> str:
    """Read the StepSecurity API key from supported environment variables."""
    value = os.environ.get("STEP_SECURITY_API_KEY") or os.environ.get("STEPSECURITY_API_KEY")
    if not value:
        raise StepSecurityError("Set STEP_SECURITY_API_KEY before sending an authenticated request")
    return value


def json_object(value: object, label: str) -> dict[str, object]:
    """Require a JSON object."""
    if not isinstance(value, dict):
        raise StepSecurityError(f"{label} must be a JSON object")
    return cast("dict[str, object]", value)


def object_list(value: object) -> list[object] | None:
    """Return a typed object list when the external value is a list."""
    return cast("list[object]", value) if isinstance(value, list) else None


def object_mapping(value: object) -> dict[object, object] | None:
    """Return a typed object mapping when the external value is a mapping."""
    return cast("dict[object, object]", value) if isinstance(value, dict) else None


def json_text_depth(value: str) -> int:
    """Measure structural JSON nesting without recursing or inspecting string contents."""
    depth = 0
    maximum = 0
    escaped = False
    in_string = False
    for character in value:
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
        elif character in "[{":
            depth += 1
            maximum = max(maximum, depth)
        elif character in "]}" and depth:
            depth -= 1
    return maximum


def json_depth_error(label: str, max_depth: int) -> StepSecurityError:
    """Build a fixed, non-echoing JSON nesting failure."""
    return StepSecurityError(f"{label} exceeds the maximum JSON nesting depth of {max_depth}")


def validate_json_scalar(value: object, *, label: str) -> None:
    """Require one finite JSON scalar without exposing its value."""
    if value is None or isinstance(value, (bool, int, str)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise StepSecurityError(f"{label} must contain only finite JSON numbers")
        return
    raise StepSecurityError(f"{label} contains a value that JSON cannot represent")


def validate_json_value(value: object, *, label: str, max_depth: int = MAX_JSON_DEPTH) -> None:
    """Validate JSON types, finite numbers, cycles, and nesting iteratively."""
    stack: list[tuple[object, int, bool]] = [(value, 0, False)]
    active_containers: set[int] = set()
    while stack:
        current, parent_depth, exiting = stack.pop()
        current_mapping = object_mapping(current)
        current_items = object_list(current)
        if current_mapping is not None or current_items is not None:
            identifier = id(current)
            if exiting:
                active_containers.remove(identifier)
                continue
            current_depth = parent_depth + 1
            if current_depth > max_depth:
                raise json_depth_error(label, max_depth)
            if identifier in active_containers:
                raise StepSecurityError(f"{label} contains a JSON container cycle")
            active_containers.add(identifier)
            stack.append((current, parent_depth, True))
            if current_mapping is not None:
                if any(not isinstance(key, str) for key in current_mapping):
                    raise StepSecurityError(f"{label} requires string JSON object keys")
                stack.extend((item, current_depth, False) for item in current_mapping.values())
            elif current_items is not None:
                stack.extend((item, current_depth, False) for item in current_items)
            continue
        validate_json_scalar(current, label=label)


def decode_json_document(value: str, *, label: str, max_depth: int = MAX_JSON_DEPTH) -> object:
    """Decode one depth-bounded JSON document and retain malformed-JSON signaling."""
    if json_text_depth(value) > max_depth:
        raise json_depth_error(label, max_depth)
    try:
        decoded = cast("object", json.loads(value))
    except json.JSONDecodeError:
        raise
    except (RecursionError, ValueError) as error:
        raise StepSecurityError(f"{label} could not be parsed safely as JSON") from error
    validate_json_value(decoded, label=label, max_depth=max_depth)
    return decoded


def safe_json_dumps(
    value: object,
    *,
    label: str,
    indent: int | None = None,
    separators: tuple[str, str] | None = None,
    sort_keys: bool = False,
) -> str:
    """Serialize validated finite JSON without recursive failures escaping."""
    validate_json_value(value, label=label, max_depth=MAX_OUTPUT_JSON_DEPTH)
    try:
        return json.dumps(
            value,
            allow_nan=False,
            indent=indent,
            separators=separators,
            sort_keys=sort_keys,
        )
    except (RecursionError, TypeError, ValueError) as error:
        raise StepSecurityError(f"{label} could not be serialized safely as JSON") from error


def load_json_file(path: str, label: str) -> object:
    """Read and parse a UTF-8 JSON file."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as error:
        raise StepSecurityError(f"Could not read {label}: {error}") from error
    try:
        return decode_json_document(text, label=label)
    except json.JSONDecodeError as error:
        raise StepSecurityError(f"Invalid JSON in {label}: {error}") from error


def load_spec(path: str) -> dict[str, object]:
    """Load a local OpenAPI specification."""
    specification = json_object(load_json_file(path, "OpenAPI specification"), "spec")
    version = specification.get("openapi")
    if not isinstance(version, str) or not version.startswith("3."):
        raise StepSecurityError("OpenAPI specification must use OpenAPI 3")
    return specification


def parameter_list(value: object) -> list[dict[str, object]]:
    """Normalize an OpenAPI parameter list and reject unresolved references."""
    if value is None:
        return []
    items = object_list(value)
    if items is None:
        raise StepSecurityError("OpenAPI parameters must be a list")
    result: list[dict[str, object]] = []
    for item in items:
        parameter = json_object(item, "OpenAPI parameter")
        if "$ref" in parameter:
            raise StepSecurityError("Referenced OpenAPI parameters are not supported by this helper")
        result.append(parameter)
    return result


def openapi_operation(path: str, method: str, value: object, inherited: list[dict[str, object]]) -> Operation | None:
    """Normalize one callable operation while ignoring OpenAPI path metadata."""
    if method.lower() not in HTTP_METHODS:
        return None
    operation = json_object(value, f"operation {method} {path}")
    operation_id = operation.get("operationId")
    if not isinstance(operation_id, str) or not operation_id:
        return None
    summary = operation.get("summary")
    tags = object_list(operation.get("tags")) or []
    return Operation(
        operation_id=operation_id,
        method=method.upper(),
        path=path,
        summary=summary if isinstance(summary, str) else "",
        tags=[tag for tag in tags if isinstance(tag, str)],
        parameters=inherited + parameter_list(operation.get("parameters")),
        request_body_required=request_body_is_required(operation.get("requestBody")),
    )


def all_operations(specification: dict[str, object]) -> list[Operation]:
    """Extract callable operations from an OpenAPI specification."""
    paths = json_object(specification.get("paths"), "OpenAPI paths")
    operations: list[Operation] = []
    for path, raw_path_item in paths.items():
        path_item = json_object(raw_path_item, f"path item {path}")
        inherited = parameter_list(path_item.get("parameters"))
        for method, raw_operation in path_item.items():
            operation = openapi_operation(path, method, raw_operation, inherited)
            if operation is not None:
                operations.append(operation)
    return sorted(operations, key=lambda item: (item.path, item.method))


def request_body_is_required(value: object) -> bool:
    """Determine whether an inline request body is required."""
    if value is None:
        return False
    body = json_object(value, "OpenAPI request body")
    if "$ref" in body:
        raise StepSecurityError("Referenced OpenAPI request bodies are not supported by this helper")
    return body.get("required") is True


def find_operation(specification: dict[str, object], operation_id: str) -> Operation:
    """Resolve one operation ID exactly."""
    matches = [operation for operation in all_operations(specification) if operation.operation_id == operation_id]
    if not matches:
        raise StepSecurityError(f"OpenAPI operation not found: {operation_id}")
    if len(matches) != 1:
        raise StepSecurityError(f"OpenAPI operation ID is ambiguous: {operation_id}")
    return matches[0]


def parameter_requirements(operation: Operation) -> tuple[set[str], set[str], set[str], set[str]]:
    """Collect allowed and required OpenAPI path and query names."""
    allowed_path: set[str] = set()
    allowed_query: set[str] = set()
    required_path: set[str] = set()
    required_query: set[str] = set()
    for parameter in operation.parameters:
        name = parameter.get("name")
        location = parameter.get("in")
        if not isinstance(name, str) or not isinstance(location, str):
            continue
        if location == "path":
            allowed_path.add(name)
            if parameter.get("required") is True:
                required_path.add(name)
        elif location == "query":
            allowed_query.add(name)
            if parameter.get("required") is True:
                required_query.add(name)
    return allowed_path, allowed_query, required_path, required_query


def apply_context_paths(operation: Operation, path_values: dict[str, str], context: Context) -> set[str]:
    """Fill recognized organization/customer placeholders from explicit context."""
    placeholders = set(re.findall(r"\{([^{}]+)\}", operation.path))
    for placeholder in placeholders - set(path_values):
        source = CONTEXT_PATH_NAMES.get(placeholder.lower())
        inferred: str | None = None
        if source == "org":
            inferred = context.organization
        elif source == "customer":
            inferred = context.customer
        if inferred:
            path_values[placeholder] = inferred
    return placeholders


def reject_parameter_mismatch(
    *,
    allowed: set[str],
    label: str,
    required: set[str],
    values: dict[str, str],
) -> None:
    """Reject unknown and missing OpenAPI inputs."""
    unknown = sorted(set(values) - allowed)
    missing = sorted(required - set(values))
    if unknown:
        raise StepSecurityError(f"Unknown {label} parameter(s): {', '.join(unknown)}")
    if missing:
        raise StepSecurityError(f"Missing {label} parameter(s): {', '.join(missing)}")


def validate_parameters(
    operation: Operation,
    path_values: dict[str, str],
    query_values: dict[str, str],
    context: Context,
) -> tuple[str, dict[str, str]]:
    """Validate operation inputs and fill explicit tenant context placeholders."""
    allowed_path, allowed_query, required_path, required_query = parameter_requirements(operation)
    placeholders = apply_context_paths(operation, path_values, context)
    allowed_path.update(placeholders)
    required_path.update(placeholders)
    reject_parameter_mismatch(
        allowed=allowed_path,
        label="path",
        required=required_path,
        values=path_values,
    )
    reject_parameter_mismatch(
        allowed=allowed_query,
        label="query",
        required=required_query,
        values=query_values,
    )

    rendered_path = operation.path
    for name, value in path_values.items():
        rendered_path = rendered_path.replace("{" + name + "}", urllib.parse.quote(value, safe=""))
    if "{" in rendered_path or "}" in rendered_path:
        raise StepSecurityError("Unresolved OpenAPI path parameter")
    return rendered_path, query_values


def validated_url(endpoint: str) -> str:
    """Resolve an endpoint while enforcing the production origin and base path."""
    if not endpoint:
        raise StepSecurityError("Endpoint cannot be empty")
    candidate = endpoint if urllib.parse.urlsplit(endpoint).scheme else f"{BASE_URL.rstrip('/')}/{endpoint.lstrip('/')}"
    parsed = urllib.parse.urlsplit(candidate)
    base = urllib.parse.urlsplit(BASE_URL)
    if parsed.scheme != "https" or parsed.netloc.lower() != base.netloc.lower():
        raise StepSecurityError("Endpoint must use the StepSecurity production origin")
    base_path = base.path.rstrip("/")
    normalized_path = parsed.path.rstrip("/") or "/"
    if normalized_path != base_path and not normalized_path.startswith(f"{base_path}/"):
        raise StepSecurityError("Endpoint must remain under the StepSecurity /v1 base path")
    decoded_segments = urllib.parse.unquote(parsed.path).split("/")
    if ".." in decoded_segments:
        raise StepSecurityError("Endpoint path traversal is not allowed")
    if parsed.username or parsed.password:
        raise StepSecurityError("Endpoint credentials are not allowed")
    existing_query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    reject_sensitive_query(dict(existing_query))
    return urllib.parse.urlunsplit(parsed)


def reject_sensitive_query(query: dict[str, str]) -> None:
    """Prevent accidental credential placement in URLs."""
    names = sorted(name for name in query if SENSITIVE_NAME.search(name))
    if names:
        raise StepSecurityError(f"Credential-like query parameter(s) are not allowed: {', '.join(names)}")


def apply_query(url: str, query: dict[str, str]) -> str:
    """Merge query values after validating their names."""
    reject_sensitive_query(query)
    parsed = urllib.parse.urlsplit(url)
    existing = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    merged = existing + list(query.items())
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urllib.parse.urlencode(merged), ""))


def body_bytes(arguments: argparse.Namespace) -> bytes | None:
    """Read and normalize a JSON body."""
    inline = getattr(arguments, "body", None)
    body_file = getattr(arguments, "body_file", None)
    if inline and body_file:
        raise StepSecurityError("Use either --body or --body-file, not both")
    if body_file:
        value = load_json_file(body_file, "request body")
    elif inline:
        try:
            value = decode_json_document(cast("str", inline), label="inline JSON body")
        except json.JSONDecodeError as error:
            raise StepSecurityError(f"Invalid inline JSON body: {error}") from error
    else:
        return None
    return safe_json_dumps(
        value,
        label="request body",
        separators=(",", ":"),
    ).encode()


def safe_headers(headers: dict[str, str]) -> dict[str, str]:
    """Redact sensitive header values."""
    return {name: REDACTED_VALUE if SENSITIVE_NAME.search(name) else value for name, value in headers.items()}


def assign_json_child(
    parent: dict[str, object] | list[object],
    key: str | int,
    value: object,
) -> None:
    """Assign one transformed JSON child to a typed parent container."""
    if isinstance(parent, list):
        parent[cast("int", key)] = value
    else:
        parent[cast("str", key)] = value


def redact(value: object, sensitive_values: tuple[str, ...] = ()) -> object:
    """Redact one validated JSON value iteratively."""
    validate_json_value(value, label="JSON value for redaction")
    holder: list[object] = [None]
    stack: list[tuple[object, dict[str, object] | list[object], str | int]] = [(value, holder, 0)]
    while stack:
        current, parent, key = stack.pop()
        mapping = object_mapping(current)
        if mapping is not None:
            redacted_mapping: dict[str, object] = {}
            assign_json_child(parent, key, redacted_mapping)
            for raw_key, item in reversed(tuple(mapping.items())):
                item_key = cast("str", raw_key)
                if SENSITIVE_NAME.search(item_key):
                    redacted_mapping[item_key] = REDACTED_VALUE
                else:
                    stack.append((item, redacted_mapping, item_key))
            continue
        items = object_list(current)
        if items is not None:
            redacted_items: list[object] = [None] * len(items)
            assign_json_child(parent, key, redacted_items)
            stack.extend((item, redacted_items, index) for index, item in reversed(tuple(enumerate(items))))
            continue
        if isinstance(current, str):
            redacted = current
            for sensitive_value in sensitive_values:
                redacted = redacted.replace(sensitive_value, REDACTED_VALUE)
            assign_json_child(parent, key, redacted)
        else:
            assign_json_child(parent, key, current)
    return holder[0]


def sensitive_header_values(headers: dict[str, str]) -> tuple[str, ...]:
    """Return sensitive header values and scheme-stripped credentials."""
    values: set[str] = set()
    for name, value in headers.items():
        if not SENSITIVE_NAME.search(name) or not value:
            continue
        values.add(value)
        _scheme, separator, credential_value = value.partition(" ")
        if separator and credential_value:
            values.add(credential_value)
    return tuple(sorted(values, key=len, reverse=True))


def safe_transport_reason(reason: object, sensitive_values: tuple[str, ...]) -> str:
    """Return bounded transport text with every known request secret removed."""
    safe = cast("str", redact(str(reason), sensitive_values))
    normalized = " ".join(safe.split())
    return normalized[:MAX_TRANSPORT_ERROR_TEXT] or "transport details unavailable"


def indeterminate_write_message(method: str, detail: str) -> str:
    """Explain recovery after an attempted mutation whose outcome is unknown."""
    return " ".join(
        (
            detail,
            f"The {method} mutation was attempted once and was not replayed; its outcome is indeterminate.",
            "Verify the exact resource or StepSecurity audit log before retrying.",
        )
    )


def parse_response(data: bytes, content_type: str, sensitive_values: tuple[str, ...] = ()) -> object:
    """Decode depth-bounded JSON or preserve the complete bounded text body."""
    text = data.decode("utf-8", errors="replace")
    if "json" in content_type.lower() or text.lstrip().startswith(("{", "[")):
        try:
            return redact(
                decode_json_document(text, label="StepSecurity response body"),
                sensitive_values,
            )
        except json.JSONDecodeError:
            pass
    return redact(text, sensitive_values)


def read_bounded_response(
    response: HTTPResponse | urllib.error.HTTPError,
    *,
    max_bytes: int,
    label: str,
) -> bytes:
    """Enforce declared and actual response sizes with a limit-plus-one read."""
    declared_length = response.headers.get("Content-Length")
    if declared_length is not None:
        try:
            parsed_length = int(declared_length)
        except ValueError:
            parsed_length = None
        if parsed_length is not None and parsed_length > max_bytes:
            raise StepSecurityError(f"{label} exceeds the {max_bytes}-byte safety limit")
    data = response.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise StepSecurityError(f"{label} exceeds the {max_bytes}-byte safety limit")
    return data


def redirect_target(current_url: str, http_error: urllib.error.HTTPError) -> str | None:
    """Return a validated redirect target or None for a non-redirect error."""
    if http_error.code not in REDIRECT_STATUSES:
        return None
    location = http_error.headers.get("Location")
    if not location:
        raise StepSecurityError("Redirect response omitted Location") from http_error
    return validated_url(urllib.parse.urljoin(current_url, location))


def retry_delay(method: str, http_error: urllib.error.HTTPError, attempt: int, runtime: RequestRuntime) -> float | None:
    """Return a bounded delay for a retryable read failure."""
    if method != "GET" or http_error.code not in RETRY_STATUSES or attempt >= runtime.retries:
        return None
    retry_after = http_error.headers.get("Retry-After")
    delay = float(retry_after) if retry_after and retry_after.isdigit() else 2**attempt
    return min(delay, 30.0)


def http_error_message(http_error: urllib.error.HTTPError, sensitive_values: tuple[str, ...]) -> str:
    """Build a bounded, redacted API error message."""
    data = read_bounded_response(
        http_error,
        max_bytes=MAX_ERROR_RESPONSE_BYTES,
        label="StepSecurity error response",
    )
    payload = parse_response(data, http_error.headers.get("Content-Type", ""), sensitive_values)
    serialized = safe_json_dumps(payload, label="StepSecurity error output")
    return f"HTTP {http_error.code}: {serialized}"


def redirect_for_method(
    method: str,
    current_url: str,
    http_error: urllib.error.HTTPError,
    sensitive_values: tuple[str, ...],
) -> str | None:
    """Resolve one redirect and attach ambiguity guidance for attempted writes."""
    try:
        redirected = redirect_target(current_url, http_error)
    except StepSecurityError as redirect_error:
        if method not in READ_METHODS:
            detail = safe_transport_reason(redirect_error, sensitive_values)
            raise StepSecurityError(indeterminate_write_message(method, detail)) from redirect_error
        raise
    if redirected is not None and method not in READ_METHODS:
        detail = f"Refusing to follow HTTP {http_error.code} redirect for {method} request."
        raise StepSecurityError(indeterminate_write_message(method, detail))
    return redirected


def raise_http_failure(
    method: str,
    http_error: urllib.error.HTTPError,
    sensitive_values: tuple[str, ...],
) -> Never:
    """Raise one bounded terminal HTTP failure with write-recovery guidance."""
    try:
        detail = http_error_message(http_error, sensitive_values)
    except StepSecurityError as response_error:
        if method in READ_METHODS:
            raise
        safe_error = safe_transport_reason(response_error, sensitive_values)
        detail = f"HTTP {http_error.code}; error response unavailable: {safe_error}"
        raise StepSecurityError(indeterminate_write_message(method, detail)) from response_error
    if method not in READ_METHODS:
        raise StepSecurityError(indeterminate_write_message(method, detail)) from http_error
    raise StepSecurityError(detail) from http_error


def raise_transport_failure(
    method: str,
    transport_error: OSError | http.client.HTTPException,
    sensitive_values: tuple[str, ...],
) -> Never:
    """Raise a bounded transport failure without exposing request credentials."""
    reason = transport_error.reason if isinstance(transport_error, urllib.error.URLError) else transport_error
    detail = f"Request failed: {safe_transport_reason(reason, sensitive_values)}"
    if method not in READ_METHODS:
        raise StepSecurityError(indeterminate_write_message(method, detail)) from transport_error
    raise StepSecurityError(detail) from transport_error


def success_result(
    method: str,
    response: HTTPResponse,
    runtime: RequestRuntime,
    sensitive_values: tuple[str, ...],
) -> ApiResult:
    """Read one bounded success response with write-recovery guidance."""
    try:
        response_headers = dict(response.headers.items())
        data = read_bounded_response(
            response,
            max_bytes=runtime.max_response_bytes,
            label="StepSecurity API response",
        )
        payload = parse_response(data, response.headers.get("Content-Type", ""), sensitive_values)
    except StepSecurityError as response_error:
        if method in READ_METHODS:
            raise
        detail = safe_transport_reason(response_error, sensitive_values)
        raise StepSecurityError(indeterminate_write_message(method, detail)) from response_error
    return ApiResult(
        headers=response_headers,
        payload=payload,
        response_bytes=len(data),
        status=response.status,
    )


def send_result(
    method: str,
    url: str,
    headers: dict[str, str],
    body: bytes | None,
    runtime: RequestRuntime,
) -> ApiResult:
    """Send one request with bounded reads, retries, and redirects."""
    method = method.upper()
    opener = urllib.request.build_opener(NoRedirect())
    attempt = 0
    current_url = validated_url(url)
    visited_urls = {current_url}
    redirect_count = 0
    sensitive_values = sensitive_header_values(headers)
    while True:
        request = urllib.request.Request(  # noqa: S310  # validated_url origin-locks current_url.
            current_url,
            data=body,
            headers=headers,
            method=method,
        )
        try:
            try:
                response = opener.open(request, timeout=runtime.timeout)
            except urllib.error.HTTPError as error:
                try:
                    redirected = redirect_for_method(method, current_url, error, sensitive_values)
                    if redirected is not None:
                        if redirected in visited_urls:
                            raise StepSecurityError(
                                "StepSecurity returned a repeated redirect URL; refusing a redirect cycle"
                            )
                        if redirect_count >= MAX_REDIRECTS:
                            raise StepSecurityError(f"StepSecurity redirect limit of {MAX_REDIRECTS} was exceeded")
                        redirect_count += 1
                        visited_urls.add(redirected)
                        current_url = redirected
                        continue
                    delay = retry_delay(method, error, attempt, runtime)
                    if delay is not None:
                        time.sleep(delay)
                        attempt += 1
                        continue
                    raise_http_failure(method, error, sensitive_values)
                finally:
                    error.close()
            else:
                try:
                    return success_result(method, response, runtime, sensitive_values)
                finally:
                    response.close()
        except (OSError, http.client.HTTPException) as error:
            raise_transport_failure(method, error, sensitive_values)


def send(
    method: str,
    url: str,
    headers: dict[str, str],
    body: bytes | None,
    runtime: RequestRuntime,
) -> tuple[int, dict[str, str], object]:
    """Preserve the public three-value transport result contract."""
    result = send_result(method, url, headers, body, runtime)
    return result.status, result.headers, result.payload


def request_plan(arguments: argparse.Namespace) -> tuple[dict[str, object], bytes | None]:
    """Build and validate a request without sending it."""
    context = resolve_context(arguments)
    path_values = parse_pairs(arguments.path, "--path")
    query_values = parse_pairs(arguments.query, "--query")
    extra_headers = parse_pairs(arguments.header, "--header")
    if any(SENSITIVE_NAME.search(name) for name in extra_headers):
        raise StepSecurityError("Credential-like custom headers are not allowed; use the environment key")
    body = body_bytes(arguments)

    if arguments.operation_id:
        if not arguments.spec_file:
            raise StepSecurityError("--spec-file is required with --operation-id")
        operation = find_operation(load_spec(arguments.spec_file), arguments.operation_id)
        endpoint, query_values = validate_parameters(operation, path_values, query_values, context)
        method = operation.method
        if operation.request_body_required and body is None:
            raise StepSecurityError("The OpenAPI operation requires a request body")
    else:
        if not arguments.endpoint:
            raise StepSecurityError("Use --operation-id or --endpoint")
        endpoint = arguments.endpoint
        method = arguments.method.upper()

    url = apply_query(validated_url(endpoint), query_values)
    headers = {
        "Accept": JSON_MEDIA_TYPE,
        "Authorization": f"Bearer {credential()}",
        "User-Agent": "codex-stepsecurity-management/1",
        **extra_headers,
    }
    if body is not None:
        headers["Content-Type"] = JSON_MEDIA_TYPE
    plan: dict[str, object] = {
        "body": redact(decode_json_document(body.decode(), label="request body")) if body is not None else None,
        "customer": context.customer,
        "headers": safe_headers(headers),
        "method": method,
        "organization": context.organization,
        "repository": context.repository,
        "url": url,
    }
    return plan, body


def next_link(payload: object) -> str | None:
    """Extract a JSON:API-style next link and reject malformed metadata."""
    payload_mapping = object_mapping(payload)
    if payload_mapping is None:
        return None
    if "links" not in payload_mapping or payload_mapping["links"] is None:
        return None
    links = object_mapping(payload_mapping["links"])
    if links is None:
        raise StepSecurityError("pagination metadata has a non-object links value")
    if "next" not in links or links["next"] is None:
        return None
    candidate = links["next"]
    if isinstance(candidate, str) and candidate.strip():
        return candidate
    candidate_mapping = object_mapping(candidate)
    if candidate_mapping is not None:
        href = candidate_mapping.get("href")
        if isinstance(href, str) and href.strip():
            return href
    raise StepSecurityError("pagination metadata has a malformed links.next value")


def execute_request(arguments: argparse.Namespace) -> None:
    """Preview or execute a constrained request."""
    plan, body = request_plan(arguments)
    method = cast("str", plan["method"])
    if arguments.dry_run or (method not in READ_METHODS and not arguments.execute):
        emit({"executed": False, "request": plan})
        return
    if arguments.paginate and method not in READ_METHODS:
        raise StepSecurityError("Pagination is available only for read requests")
    headers = {
        "Accept": JSON_MEDIA_TYPE,
        "Authorization": f"Bearer {credential()}",
        "User-Agent": "codex-stepsecurity-management/1",
        **parse_pairs(arguments.header, "--header"),
    }
    if body is not None:
        headers["Content-Type"] = JSON_MEDIA_TYPE

    output = execute_pages(arguments, plan, body, headers)
    emit(output)


def execute_pages(
    arguments: argparse.Namespace,
    plan: dict[str, object],
    body: bytes | None,
    headers: dict[str, str],
) -> dict[str, object]:
    """Execute bounded pages and return explicit completeness metadata."""
    pages: list[dict[str, object]] = []
    url = cast("str", plan["url"])
    visited_page_urls = {url}
    pending_link: str | None = None
    response_bytes = 0
    for page_number in range(1, arguments.max_pages + 1):
        remaining_bytes = MAX_PAGINATED_RESPONSE_BYTES - response_bytes
        if arguments.paginate and remaining_bytes <= 0:
            raise StepSecurityError(
                f"StepSecurity pagination exceeds the {MAX_PAGINATED_RESPONSE_BYTES}-byte cumulative safety limit"
            )
        page_limit = min(MAX_API_RESPONSE_BYTES, remaining_bytes) if arguments.paginate else MAX_API_RESPONSE_BYTES
        runtime = RequestRuntime(
            max_response_bytes=page_limit,
            retries=arguments.retries,
            timeout=arguments.timeout,
        )
        try:
            result = send_result(cast("str", plan["method"]), url, headers, body, runtime)
        except StepSecurityError as error:
            page_overflow = f"StepSecurity API response exceeds the {page_limit}-byte safety limit"
            if arguments.paginate and page_limit < MAX_API_RESPONSE_BYTES and str(error) == page_overflow:
                raise StepSecurityError(
                    f"StepSecurity pagination exceeds the {MAX_PAGINATED_RESPONSE_BYTES}-byte cumulative safety limit"
                ) from error
            raise
        response_bytes += result.response_bytes
        pages.append(
            {
                "body": result.payload,
                "page": page_number,
                "status": result.status,
                "request_id": result.headers.get("X-Request-Id") or result.headers.get("X-Request-ID"),
            }
        )
        try:
            candidate = next_link(result.payload)
        except StepSecurityError as error:
            raise StepSecurityError(
                f"StepSecurity pagination is incomplete after {len(pages)} page(s): {error}"
            ) from error
        if candidate is None:
            pending_link = None
            break
        pending_link = validated_url(urllib.parse.urljoin(url, candidate))
        if not arguments.paginate:
            break
        if pending_link in visited_page_urls:
            raise StepSecurityError(
                f"StepSecurity pagination is incomplete after {len(pages)} page(s): repeated next link {pending_link}"
            )
        visited_page_urls.add(pending_link)
        url = pending_link
        body = None
    return {
        "complete": pending_link is None,
        "executed": True,
        "maxPages": arguments.max_pages,
        "nextLink": pending_link,
        "pageCount": len(pages),
        "pages": pages,
    }


def command_context(arguments: argparse.Namespace) -> None:
    """Print redacted context."""
    emit(asdict(resolve_context(arguments)))


def command_operations(arguments: argparse.Namespace) -> None:
    """List operations from a downloaded specification."""
    operations = all_operations(load_spec(arguments.spec_file))
    if arguments.match:
        needle = arguments.match.casefold()
        operations = [
            operation
            for operation in operations
            if needle
            in " ".join(
                [
                    operation.operation_id,
                    operation.method,
                    operation.path,
                    operation.summary,
                    *operation.tags,
                ]
            ).casefold()
        ]
    emit([asdict(operation) for operation in operations])


def add_context_flags(parser: argparse.ArgumentParser) -> None:
    """Add common context selectors."""
    _ = parser.add_argument("--org", help="StepSecurity/GitHub organization")
    _ = parser.add_argument("--customer", help="StepSecurity customer slug")
    _ = parser.add_argument("--repo", help="GitHub owner/repository")


def parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""
    root = argparse.ArgumentParser(description="Inspect StepSecurity OpenAPI operations and make constrained requests.")
    subcommands = root.add_subparsers(dest="command", required=True)

    context = subcommands.add_parser("context", help="Show redacted tenant context")
    add_context_flags(context)
    context.set_defaults(handler=command_context)

    operations = subcommands.add_parser("operations", help="List operations in a downloaded OpenAPI document")
    _ = operations.add_argument("--spec-file", required=True)
    _ = operations.add_argument("--match")
    operations.set_defaults(handler=command_operations)

    request = subcommands.add_parser("request", help="Preview or send a constrained REST request")
    add_context_flags(request)
    _ = request.add_argument("--spec-file")
    _ = request.add_argument("--operation-id")
    _ = request.add_argument("--method", default="GET", choices=sorted(m.upper() for m in HTTP_METHODS))
    _ = request.add_argument("--endpoint")
    _ = request.add_argument("--path", action="append")
    _ = request.add_argument("--query", action="append")
    _ = request.add_argument("--header", action="append")
    _ = request.add_argument("--body")
    _ = request.add_argument("--body-file")
    _ = request.add_argument("--execute", action="store_true")
    _ = request.add_argument("--dry-run", action="store_true")
    _ = request.add_argument("--paginate", action="store_true")
    _ = request.add_argument("--max-pages", type=int, default=10)
    _ = request.add_argument("--timeout", type=float, default=30.0)
    _ = request.add_argument("--retries", type=int, default=2)
    request.set_defaults(handler=execute_request)
    return root


def validate_arguments(arguments: argparse.Namespace) -> None:
    """Validate bounded runtime controls before dispatch."""
    max_pages = int(getattr(arguments, "max_pages", 1))
    timeout = float(getattr(arguments, "timeout", 1.0))
    retries = int(getattr(arguments, "retries", 0))
    if max_pages < 1:
        raise StepSecurityError("--max-pages must be at least 1")
    if max_pages > MAX_PAGES:
        raise StepSecurityError(f"--max-pages cannot exceed {MAX_PAGES}")
    _ = RequestRuntime(retries=retries, timeout=timeout)
    if getattr(arguments, "execute", False) and getattr(arguments, "dry_run", False):
        raise StepSecurityError("--execute and --dry-run are mutually exclusive")


def main() -> int:
    """Run the command-line interface."""
    arguments = parser().parse_args()
    try:
        validate_arguments(arguments)
        handler = cast("Callable[[argparse.Namespace], None]", arguments.handler)
        handler(arguments)
    except StepSecurityError as error:
        _ = sys.stderr.write(f"error: {error}\n")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
