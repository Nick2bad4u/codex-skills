#!/usr/bin/env python
# Copyright (c) 2026 Nick2bad4u
"""Inspect Socket OpenAPI operations and make origin-locked v0 requests."""

from __future__ import annotations

import argparse
import base64
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from http.client import HTTPException
from pathlib import Path
from typing import TYPE_CHECKING, cast, override
from urllib import error, parse, request

if TYPE_CHECKING:
    from collections.abc import Callable
    from email.message import Message
    from http.client import HTTPMessage
    from typing import IO

type JsonValue = bool | int | float | str | list[JsonValue] | dict[str, JsonValue] | None

DEFAULT_BASE_URL = "https://api.socket.dev/v0"
DEFAULT_SPEC_URL = "https://api.socket.dev/v0/openapi"
DEFAULT_TOKEN_ENVS = ("SOCKET_SECURITY_API_TOKEN", "SOCKET_API_TOKEN")
DEFAULT_TIMEOUT = 30.0
DEFAULT_RETRIES = 2
DEFAULT_MAX_PAGES = 100
MAX_RESPONSE_TEXT = 2000
MAX_LOCAL_SPEC_BYTES = 16 * 1024 * 1024
MAX_REMOTE_SPEC_BYTES = 16 * 1024 * 1024
MAX_API_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_ERROR_RESPONSE_BYTES = 16 * 1024
MAX_PAGINATED_RESPONSE_BYTES = 32 * 1024 * 1024
MAX_UNTRUSTED_REASON_TEXT = 1000
MAX_RETRIES = 10
MAX_PAGES = 1000
MAX_RETRY_DELAY_SECONDS = 60.0
MAX_PATH_DECODE_ROUNDS = 8
CONTROL_C0_LIMIT = 32
CONTROL_DELETE = 127
CONTROL_C1_LIMIT = 160
QUOTED_CREDENTIAL_MIN_LENGTH = 2
MIN_UNQUOTED_TOKEN_CREDENTIAL_LENGTH = 16
JSON_MEDIA_TYPE = "application/json"
REDACTED_TEXT = "<redacted>"
HTTP_TOO_MANY_REQUESTS = 429
HTTP_REQUEST_TIMEOUT = 408
HTTP_INTERNAL_SERVER_ERROR = 500
HTTP_BAD_GATEWAY = 502
HTTP_SERVICE_UNAVAILABLE = 503
HTTP_GATEWAY_TIMEOUT = 504
HTTP_SUCCESS_MIN = 200
HTTP_SUCCESS_LIMIT = 300
GET_RETRYABLE_STATUS_CODES = frozenset(
    {
        HTTP_REQUEST_TIMEOUT,
        HTTP_TOO_MANY_REQUESTS,
        HTTP_INTERNAL_SERVER_ERROR,
        HTTP_BAD_GATEWAY,
        HTTP_SERVICE_UNAVAILABLE,
        HTTP_GATEWAY_TIMEOUT,
    }
)
WRITE_INDETERMINATE_STATUS_CODES = frozenset({HTTP_REQUEST_TIMEOUT, HTTP_TOO_MANY_REQUESTS, *range(500, 600)})
PATH_PARAMETER = re.compile(r"\{([^{}]+)\}")
PERCENT_ESCAPE = re.compile(r"%[0-9A-Fa-f]{2}")
RESIDUAL_ESCAPE_LIKE = re.compile(r"%(?:[A-Za-z0-9]{2}|[A-Za-z0-9](?![A-Za-z0-9]))")
AUTHORIZATION_ASSIGNMENT = re.compile(
    r"\bauthorization\s*[:=]\s*(?:\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'|" + r"(?:(?:bearer|basic|token)\s+)?[^\s,;]+)",
    re.IGNORECASE,
)
SCHEME_CREDENTIAL = re.compile(
    r"\b(?P<scheme>bearer|basic|token)\s+(?P<credential>\"(?:\\.|[^\"\\])+\"|" + r"'(?:\\.|[^'\\])+'|[^\s,;]+)",
    re.IGNORECASE,
)
URL_USERINFO = re.compile(r"\b([a-z][a-z0-9+.-]*://)([^/\s?#@]+)@", re.IGNORECASE)
ASSIGNMENT_KEY_PATTERN = r"(?P<key_quote>[\"']?)(?P<name>[a-z0-9_.%~-]+)(?P=key_quote)"
ASSIGNMENT_SEPARATOR_PATTERN = r"(?P<before>\s*)(?P<separator>=|:(?!//))(?P<after>\s*)"
ASSIGNMENT_PREFIX_PATTERN = r"(?P<prefix>^|[\s{[(,;?&])"
SENSITIVE_ASSIGNMENTS = tuple(
    re.compile(
        ASSIGNMENT_PREFIX_PATTERN + ASSIGNMENT_KEY_PATTERN + ASSIGNMENT_SEPARATOR_PATTERN + value_pattern,
        re.IGNORECASE | re.MULTILINE,
    )
    for value_pattern in (r'"(?:\\.|[^"\\])*"', r"'(?:\\.|[^'\\])*'", r"[^\s,;}&\]]*")
)
SENSITIVE_TERMINAL_TOKENS = frozenset(
    {"authorization", "cookie", "credential", "password", "secret", "session", "token", "webhook"}
)
SENSITIVE_KEY_QUALIFIERS = frozenset({"access", "api", "integration", "provider", "secret", "sentinel"})
SENSITIVE_TOKEN_PLURALS = {
    "authorizations": "authorization",
    "cookies": "cookie",
    "credentials": "credential",
    "keys": "key",
    "passwords": "password",
    "secrets": "secret",
    "sessions": "session",
    "tokens": "token",
    "urls": "url",
    "webhooks": "webhook",
}
SCHEME_PROSE_WORDS = frozenset(
    {
        "auth",
        "authentication",
        "configuration",
        "enabled",
        "expiration",
        "expires",
        "expiry",
        "is",
        "lifetime",
        "rotation",
        "scheme",
        "timeout",
        "uses",
        "was",
    }
)


class SocketCliError(RuntimeError):
    """Report a safe, user-facing helper error."""


class NoRedirectHandler(request.HTTPRedirectHandler):
    """Reject redirects so authenticated headers never cross a trust boundary."""

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
class RepositorySlug:
    """GitHub identity inferred from an origin URL."""

    organization: str
    repository: str


@dataclass(frozen=True)
class SocketContext:
    """Resolved Socket target and authentication context."""

    base_url: str
    organization: str | None
    repository: str | None
    repository_root: Path
    token: str | None
    token_env_name: str | None


@dataclass(frozen=True)
class OpenApiOperation:
    """Small stable view of an OpenAPI operation."""

    deprecated: bool
    method: str
    operation_id: str
    path: str
    summary: str
    tags: tuple[str, ...]


@dataclass(frozen=True)
class RequestPlan:
    """Resolved API request details."""

    body: JsonValue
    method: str
    operation_id: str | None
    query: dict[str, str]
    url: str


@dataclass(frozen=True)
class ApiResult:
    """One Socket API response."""

    payload: JsonValue
    status: int
    url: str
    response_bytes: int = 0


def optional_text(value: object) -> str | None:
    """Return a stripped optional string."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def validated_timeout(value: float | str) -> float:
    """Return a finite positive timeout."""
    timeout = float(value)
    if not math.isfinite(timeout) or timeout <= 0:
        raise SocketCliError("--timeout must be finite and greater than zero.")
    return timeout


def validated_retries(value: int | str) -> int:
    """Return a retry count within the documented safety cap."""
    retries = int(value)
    if not 0 <= retries <= MAX_RETRIES:
        raise SocketCliError(f"--retries must be between zero and {MAX_RETRIES}.")
    return retries


def validated_max_pages(value: int | str) -> int:
    """Return a pagination limit within the documented safety cap."""
    max_pages = int(value)
    if not 1 <= max_pages <= MAX_PAGES:
        raise SocketCliError(f"--max-pages must be between one and {MAX_PAGES}.")
    return max_pages


def reject_json_constant(value: str) -> float:
    """Reject the non-standard NaN and infinity constants accepted by json.loads."""
    raise ValueError(f"Non-finite JSON constant is not permitted: {value}")


def parse_finite_json_float(value: str) -> float:
    """Parse one JSON float while rejecting exponent overflow to infinity."""
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError("JSON number overflowed to a non-finite value.")
    return parsed


def strict_json_loads(value: str, *, source: str) -> JsonValue:
    """Parse standards-compliant JSON with only finite numeric values."""
    try:
        return cast(
            "JsonValue",
            json.loads(
                value,
                parse_constant=reject_json_constant,
                parse_float=parse_finite_json_float,
            ),
        )
    except ValueError as exception:
        raise SocketCliError(f"Expected JSON with only finite numbers from {source}.") from exception


def serialize_json(value: JsonValue, *, pretty: bool, source: str) -> str:
    """Serialize finite JSON completely before callers write or send any bytes."""
    try:
        if pretty:
            return json.dumps(
                value,
                allow_nan=False,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        return json.dumps(value, allow_nan=False, ensure_ascii=True, separators=(",", ":"))
    except (OverflowError, TypeError, ValueError) as exception:
        raise SocketCliError(f"Could not encode {source} as strict finite JSON.") from exception


def is_environment_name(value: str) -> bool:
    """Return whether a name is a safe portable ASCII environment identifier."""
    return value.isascii() and value.isidentifier()


def as_string_list(value: object) -> list[str]:
    """Narrow argparse append values after parser-controlled construction."""
    return cast("list[str]", value)


def resolve_repository(value: str) -> Path:
    """Resolve an existing repository directory from a CLI value."""
    try:
        repository = Path(value).expanduser().resolve(strict=True)
    except OSError as exception:
        raise argparse.ArgumentTypeError(f"Repository path does not exist: {value}") from exception
    if not repository.is_dir():
        raise argparse.ArgumentTypeError(f"Repository path is not a directory: {value}")
    return repository


def sanitize_base_url(value: str) -> str:
    """Validate and normalize the one trusted Socket v0 API base URL."""
    base_url = value.strip().rstrip("/")
    parsed = parse.urlsplit(base_url)
    if parsed.scheme.lower() != "https" or not parsed.netloc:
        raise SocketCliError("Socket API base URL must be an absolute HTTPS URL.")
    if parsed.username is not None or parsed.password is not None:
        raise SocketCliError("Socket API base URL must not contain credentials.")
    if parsed.query or parsed.fragment:
        raise SocketCliError("Socket API base URL must not contain a query or fragment.")
    try:
        port = parsed.port
    except ValueError as exception:
        raise SocketCliError("Socket API base URL contains an invalid port.") from exception
    if parsed.hostname != "api.socket.dev" or port is not None or parsed.path != "/v0":
        raise SocketCliError(f"Socket API base URL must be exactly {DEFAULT_BASE_URL}.")
    return DEFAULT_BASE_URL


def validate_decoded_path_layer(path: str, *, base_path: str, source: str) -> None:
    """Validate one path representation in a repeated-decoding chain."""
    if any(
        ord(character) < CONTROL_C0_LIMIT or CONTROL_DELETE <= ord(character) < CONTROL_C1_LIMIT for character in path
    ):
        raise SocketCliError(f"{source} path contains a control character.")
    if "\\" in path or "?" in path or "#" in path:
        raise SocketCliError(f"{source} path contains an encoded structural delimiter.")
    if any(segment in {".", ".."} for segment in path.split("/")):
        raise SocketCliError(f"{source} path contains an encoded traversal segment.")
    if path != base_path and not path.startswith(f"{base_path}/"):
        raise SocketCliError(f"{source} path must remain under the official Socket /v0 base path.")


def validate_confined_path(path: str, *, base_path: str, source: str) -> None:
    """Reject structural characters revealed by repeated percent decoding."""
    if re.search(r"%(?![0-9A-Fa-f]{2})", path) is not None:
        raise SocketCliError(f"{source} path contains a malformed percent escape.")

    current = path
    normalized_base = base_path.rstrip("/")
    for _round in range(MAX_PATH_DECODE_ROUNDS + 1):
        validate_decoded_path_layer(current, base_path=normalized_base, source=source)

        if PERCENT_ESCAPE.search(current) is None:
            if _round > 0 and RESIDUAL_ESCAPE_LIKE.search(current) is not None:
                raise SocketCliError(f"{source} path contains a malformed residual percent escape.")
            return
        if _round == MAX_PATH_DECODE_ROUNDS:
            raise SocketCliError(f"{source} path contains too many nested percent escapes.")
        try:
            decoded = parse.unquote(current, errors="strict")
        except UnicodeDecodeError as exception:
            raise SocketCliError(f"{source} path contains invalid percent-encoded UTF-8.") from exception
        if decoded.count("/") != current.count("/"):
            raise SocketCliError(f"{source} path contains an encoded slash.")
        current = decoded


def run_git(repository: Path, *arguments: str) -> str | None:
    """Run a fixed read-only git command and return stripped output."""
    executable = shutil.which("git")
    if executable is None:
        return None
    result = subprocess.run(  # noqa: S603  # Fixed executable and argument vector; no shell.
        [executable, *arguments],
        cwd=repository,
        check=False,
        capture_output=True,
        stdin=subprocess.DEVNULL,
        text=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def parse_github_remote(remote_url: str) -> RepositorySlug | None:
    """Parse a GitHub HTTPS or SCP-like SSH remote."""
    value = remote_url.strip()
    if "://" not in value and re.fullmatch(r"[^@\s]+@[^:\s]+:.+", value):
        user_host, remote_path = value.split(":", maxsplit=1)
        value = f"ssh://{user_host}/{remote_path}"
    parsed = parse.urlsplit(value)
    if (parsed.hostname or "").lower() != "github.com":
        return None
    parts = [parse.unquote(part) for part in parsed.path.strip("/").split("/") if part]
    if len(parts) != 2:  # noqa: PLR2004  # GitHub owner/repository shape.
        return None
    organization, repository = parts
    repository = repository.removesuffix(".git")
    if not organization or not repository:
        return None
    return RepositorySlug(organization=organization, repository=repository)


def resolve_token(token_envs: list[str]) -> tuple[str | None, str | None]:
    """Resolve the first non-empty token from safe environment names."""
    candidates = token_envs or list(DEFAULT_TOKEN_ENVS)
    for name in candidates:
        if not is_environment_name(name):
            raise SocketCliError(f"Invalid token environment variable name: {name}")
        token = os.environ.get(name, "").strip()
        if token:
            return token, name
    return None, None


def resolve_context(arguments: argparse.Namespace) -> SocketContext:
    """Resolve repository, target, base URL, and optional token."""
    base_url = sanitize_base_url(str(arguments.base_url))
    repository_root = cast("Path", arguments.repo)
    detected: RepositorySlug | None = None
    remote_url = run_git(repository_root, "remote", "get-url", "origin")
    if remote_url is not None:
        detected = parse_github_remote(remote_url)
    organization = optional_text(arguments.org) or (detected.organization if detected else None)
    repository = optional_text(arguments.repository) or (detected.repository if detected else None)
    token, token_env_name = resolve_token(as_string_list(arguments.token_envs))
    return SocketContext(
        base_url=base_url,
        organization=organization,
        repository=repository,
        repository_root=repository_root,
        token=token,
        token_env_name=token_env_name,
    )


def validate_spec_url(value: str, context: SocketContext) -> str:
    """Validate an HTTPS OpenAPI URL under the trusted Socket v0 base."""
    parsed = parse.urlsplit(value.strip())
    base = parse.urlsplit(sanitize_base_url(context.base_url))
    if parsed.scheme.lower() != "https" or not parsed.netloc:
        raise SocketCliError("OpenAPI specification URL must be absolute HTTPS.")
    if parsed.username is not None or parsed.password is not None:
        raise SocketCliError("OpenAPI specification URL must not contain credentials.")
    if parsed.query or parsed.fragment:
        raise SocketCliError("OpenAPI specification URL must not contain a query or fragment.")
    if (parsed.scheme.lower(), parsed.netloc.lower()) != (base.scheme.lower(), base.netloc.lower()):
        raise SocketCliError("OpenAPI specification origin must be the official Socket API origin.")
    base_path = base.path.rstrip("/")
    if parsed.path != base_path and not parsed.path.startswith(f"{base_path}/"):
        raise SocketCliError("OpenAPI specification must remain under the official Socket /v0 base path.")
    validate_confined_path(parsed.path, base_path=base_path, source="OpenAPI specification")
    return value.strip()


def declared_content_length(headers: Message[str, str]) -> int | None:
    """Return one trustworthy nonnegative decimal Content-Length value."""
    values = headers.get_all("Content-Length")
    if values is not None and len(values) != 1:
        return None
    raw_value = headers.get("Content-Length")
    if raw_value is None:
        return None
    value = str(raw_value).strip()
    if re.fullmatch(r"\d+", value, flags=re.ASCII) is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def read_bounded_response(
    stream: IO[bytes],
    headers: Message[str, str],
    *,
    limit: int,
    source: str,
) -> bytes:
    """Read at most limit plus one byte, using Content-Length only as an early guard."""
    content_length = declared_content_length(headers)
    if content_length is not None and content_length > limit:
        raise SocketCliError(f"{source} exceeds the {limit}-byte safety limit.")
    data = stream.read(limit + 1)
    if len(data) > limit:
        raise SocketCliError(f"{source} exceeds the {limit}-byte safety limit.")
    return data


def decode_json(data: bytes, *, source: str) -> JsonValue:
    """Decode a JSON response with a bounded safe error."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exception:
        raise SocketCliError(f"Expected JSON from {source}.") from exception
    return strict_json_loads(text, source=source)


def load_local_openapi(spec_file: Path) -> dict[str, JsonValue]:
    """Load one bounded local Socket OpenAPI document."""
    try:
        with spec_file.open("rb") as stream:
            data = stream.read(MAX_LOCAL_SPEC_BYTES + 1)
    except OSError as exception:
        raise SocketCliError(f"Could not parse OpenAPI JSON file: {spec_file}") from exception
    if len(data) > MAX_LOCAL_SPEC_BYTES:
        raise SocketCliError(f"Local OpenAPI specification exceeds the {MAX_LOCAL_SPEC_BYTES}-byte safety limit.")
    try:
        payload = decode_json(data, source=f"OpenAPI JSON file {spec_file}")
    except SocketCliError as exception:
        raise SocketCliError(f"Could not parse OpenAPI JSON file: {spec_file}") from exception
    if not isinstance(payload, dict):
        raise SocketCliError("OpenAPI document root must be an object.")
    return payload


def load_remote_openapi(arguments: argparse.Namespace, context: SocketContext) -> tuple[dict[str, JsonValue], str]:
    """Load one bounded official Socket OpenAPI document."""
    spec_url = validate_spec_url(optional_text(arguments.spec_url) or DEFAULT_SPEC_URL, context)
    opener = request.build_opener(NoRedirectHandler())
    try:
        spec_request = request.Request(  # noqa: S310  # validate_spec_url locks this to the Socket origin.
            spec_url,
            headers={"Accept": JSON_MEDIA_TYPE},
        )
        with opener.open(
            spec_request,
            timeout=validated_timeout(arguments.timeout),
        ) as response:
            data = read_bounded_response(
                response,
                response.headers,
                limit=MAX_REMOTE_SPEC_BYTES,
                source="Remote OpenAPI specification",
            )
            payload = decode_json(data, source="Socket OpenAPI endpoint")
    except error.HTTPError as exception:
        try:
            try:
                data = read_bounded_response(
                    exception,
                    exception.headers,
                    limit=MAX_ERROR_RESPONSE_BYTES,
                    source="OpenAPI error response",
                )
                error_payload = response_payload(data, exception.headers.get("Content-Type", ""), context.token)
                safe_payload = redact_json(error_payload, context.token)
            except (HTTPException, OSError, SocketCliError) as body_exception:
                safe_detail = safe_untrusted_reason(body_exception, context.token)
                message = " ".join(
                    (
                        f"OpenAPI request failed with HTTP {exception.code};",
                        f"its error response could not be safely processed: {safe_detail}",
                    )
                )
                raise SocketCliError(message) from body_exception
            rendered_payload = serialize_json(safe_payload, pretty=False, source="redacted OpenAPI error")
            raise SocketCliError(
                f"OpenAPI request failed with HTTP {exception.code}: {rendered_payload}"
            ) from exception
        finally:
            exception.close()
    except (error.URLError, OSError, HTTPException) as exception:
        raw_reason = exception.reason if isinstance(exception, error.URLError) else exception
        reason = safe_untrusted_reason(raw_reason, context.token)
        raise SocketCliError(f"OpenAPI request failed: {reason}") from exception
    if not isinstance(payload, dict):
        raise SocketCliError("OpenAPI document root must be an object.")
    return payload, spec_url


def load_openapi(arguments: argparse.Namespace, context: SocketContext) -> tuple[dict[str, JsonValue], str]:
    """Load a local or live Socket OpenAPI JSON document."""
    spec_file = cast("Path | None", arguments.spec_file)
    if spec_file is not None:
        return load_local_openapi(spec_file), str(spec_file)
    return load_remote_openapi(arguments, context)


def openapi_operation(path: str, method: str, value: JsonValue) -> OpenApiOperation | None:
    """Normalize one documented operation, ignoring non-operation path fields."""
    if not isinstance(value, dict):
        return None
    operation_id = value.get("operationId")
    if not isinstance(operation_id, str) or not operation_id:
        return None
    summary_value = value.get("summary")
    tags_value = value.get("tags")
    return OpenApiOperation(
        deprecated=value.get("deprecated") is True,
        method=method.upper(),
        operation_id=operation_id,
        path=path,
        summary=summary_value if isinstance(summary_value, str) else "",
        tags=tuple(item for item in tags_value if isinstance(item, str)) if isinstance(tags_value, list) else (),
    )


def parse_operations(spec: dict[str, JsonValue]) -> list[OpenApiOperation]:
    """Extract useful operations from an OpenAPI JSON object."""
    paths = spec.get("paths")
    if not isinstance(paths, dict):
        raise SocketCliError("OpenAPI document does not contain a paths object.")
    operations: list[OpenApiOperation] = []
    for path_name, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue
        for method in ("get", "post", "put", "patch", "delete"):
            operation = openapi_operation(path_name, method, path_item.get(method))
            if operation is not None:
                operations.append(operation)
    return sorted(operations, key=lambda item: (item.path, item.method, item.operation_id))


def parse_pairs(values: list[str], *, label: str) -> dict[str, str]:
    """Parse repeatable name=value arguments and reject duplicates or secrets."""
    result: dict[str, str] = {}
    for value in values:
        name, separator, item_value = value.partition("=")
        name = name.strip()
        if not separator or not name or not item_value:
            raise SocketCliError(f"{label} values must use non-empty name=value syntax.")
        if name in result:
            raise SocketCliError(f"Duplicate {label} name: {name}")
        if label == "query" and is_sensitive_key(name):
            raise SocketCliError(f"Refusing token-like query parameter: {name}")
        result[name] = item_value
    return result


def load_body(arguments: argparse.Namespace) -> JsonValue:
    """Load an optional JSON request body."""
    body_text = optional_text(arguments.body_json)
    body_file = cast("Path | None", arguments.body_file)
    if body_file is not None:
        try:
            body_text = body_file.read_text(encoding="utf-8")
        except OSError as exception:
            raise SocketCliError(f"Could not read request body file: {body_file}") from exception
    if body_text is None:
        return None
    try:
        return strict_json_loads(body_text, source="request body")
    except SocketCliError as exception:
        raise SocketCliError("Request body must be valid strict JSON with only finite numbers.") from exception


def operation_by_id(operations: list[OpenApiOperation], operation_id: str) -> OpenApiOperation:
    """Resolve exactly one case-sensitive OpenAPI operation ID."""
    matches = [operation for operation in operations if operation.operation_id == operation_id]
    if len(matches) != 1:
        raise SocketCliError("operationId must resolve exactly once in the OpenAPI document.")
    return matches[0]


def fill_path(path_template: str, values: dict[str, str]) -> str:
    """Fill every OpenAPI path parameter and reject unused values."""
    required = PATH_PARAMETER.findall(path_template)
    missing = [name for name in required if name not in values]
    unused = [name for name in values if name not in required]
    if missing:
        raise SocketCliError(f"Missing path parameter(s): {', '.join(missing)}")
    if unused:
        raise SocketCliError(f"Unused path parameter(s): {', '.join(unused)}")
    result = path_template
    for name in required:
        result = result.replace(f"{{{name}}}", parse.quote(values[name], safe=""))
    return result


def validated_endpoint_url(base_url: str, endpoint: str) -> str:
    """Resolve a relative endpoint while locking origin and base path."""
    base_url = sanitize_base_url(base_url)
    if parse.urlsplit(endpoint).query or parse.urlsplit(endpoint).fragment:
        raise SocketCliError("Endpoint must not contain query or fragment; use --query.")
    if endpoint.startswith("/"):
        candidate = f"{base_url}{endpoint}"
    else:
        parsed_endpoint = parse.urlsplit(endpoint)
        if not parsed_endpoint.scheme:
            raise SocketCliError("Relative endpoint must start with /.")
        candidate = endpoint
    base = parse.urlsplit(base_url)
    parsed = parse.urlsplit(candidate)
    if parsed.scheme.lower() != "https" or not parsed.netloc:
        raise SocketCliError("Endpoint must resolve to an absolute HTTPS URL.")
    if parsed.username is not None or parsed.password is not None:
        raise SocketCliError("Endpoint must not contain URL credentials.")
    if (parsed.scheme.lower(), parsed.netloc.lower()) != (base.scheme.lower(), base.netloc.lower()):
        raise SocketCliError("Absolute endpoint origin must match the official Socket API origin.")
    base_path = base.path.rstrip("/")
    if parsed.path != base_path and not parsed.path.startswith(f"{base_path}/"):
        raise SocketCliError("Absolute endpoint must remain under the official Socket /v0 base path.")
    validate_confined_path(parsed.path, base_path=base_path, source="Endpoint")
    return candidate


def build_plan(arguments: argparse.Namespace, context: SocketContext) -> RequestPlan:
    """Resolve raw or operation-based request arguments."""
    endpoint = optional_text(arguments.endpoint)
    operation_id = optional_text(arguments.operation_id)
    if endpoint is not None and operation_id is not None:
        raise SocketCliError("Provide either an endpoint or --operation-id, not both.")
    if endpoint is None and operation_id is None:
        raise SocketCliError("Provide an endpoint or --operation-id.")
    method = optional_text(arguments.method)
    if operation_id is not None:
        spec, _ = load_openapi(arguments, context)
        operation = operation_by_id(parse_operations(spec), operation_id)
        if method is not None and method.upper() != operation.method:
            raise SocketCliError("--method conflicts with the OpenAPI operation.")
        method = operation.method
        endpoint = fill_path(operation.path, parse_pairs(as_string_list(arguments.path_values), label="path"))
    elif as_string_list(arguments.path_values):
        raise SocketCliError("--path requires --operation-id.")
    method = (method or "GET").upper()
    body = load_body(arguments)
    if method in {"GET", "DELETE"} and body is not None and method == "GET":
        raise SocketCliError("GET requests must not include a body.")
    url = validated_endpoint_url(context.base_url, cast("str", endpoint))
    return RequestPlan(
        body=body,
        method=method,
        operation_id=operation_id,
        query=parse_pairs(as_string_list(arguments.query), label="query"),
        url=url,
    )


def split_identifier_segment(segment: str) -> list[str]:
    """Split one ASCII alphanumeric identifier segment in deterministic linear time."""
    words: list[str] = []
    word_start = 0
    for index in range(1, len(segment)):
        previous = segment[index - 1]
        current = segment[index]
        following = segment[index + 1] if index + 1 < len(segment) else ""
        acronym_plural_suffix = following == "s" and index + 2 == len(segment)
        if current.isupper() and (
            previous.islower()
            or previous.isdigit()
            or (previous.isupper() and following.islower() and not acronym_plural_suffix)
        ):
            words.append(segment[word_start:index])
            word_start = index
    words.append(segment[word_start:])
    return words


def identifier_words(value: str) -> list[str]:
    """Split an identifier on ASCII separators and semantic case boundaries."""
    words: list[str] = []
    segment_start = 0
    for index, character in enumerate(value):
        if character.isascii() and character.isalnum():
            continue
        if segment_start < index:
            words.extend(split_identifier_segment(value[segment_start:index]))
        segment_start = index + 1
    if segment_start < len(value):
        words.extend(split_identifier_segment(value[segment_start:]))
    return words


def semantic_key_tokens(key: str) -> tuple[str, ...]:
    """Tokenize separators and camel/Pascal boundaries without suffix collisions."""
    return tuple(word.casefold() for word in identifier_words(parse.unquote_plus(key)))


def is_sensitive_key(key: str) -> bool:
    """Detect semantic credential fields while preserving ordinary settings."""
    tokens = semantic_key_tokens(key)
    if not tokens:
        return False
    singular = tuple(SENSITIVE_TOKEN_PLURALS.get(token, token) for token in tokens)
    terminal = singular[-1]
    if terminal in SENSITIVE_TERMINAL_TOKENS:
        return True
    if terminal == "key" and any(token in SENSITIVE_KEY_QUALIFIERS for token in singular[:-1]):
        return True
    return singular[-2:] in {
        ("authorization", "header"),
        ("cookie", "header"),
        ("session", "id"),
        ("webhook", "url"),
    }


def percent_triplet_pattern(value: str) -> re.Pattern[str]:
    """Match one exact value while allowing either hex case in percent triplets."""
    pieces: list[str] = []
    index = 0
    while index < len(value):
        if (
            index + 2 < len(value)
            and value[index] == "%"
            and re.fullmatch(r"[0-9A-Fa-f]{2}", value[index + 1 : index + 3])
        ):
            first = value[index + 1]
            second = value[index + 2]
            first_pattern = f"[{first.lower()}{first.upper()}]" if first.isalpha() else first
            second_pattern = f"[{second.lower()}{second.upper()}]" if second.isalpha() else second
            pieces.append(f"%{first_pattern}{second_pattern}")
            index += 3
            continue
        pieces.append(re.escape(value[index]))
        index += 1
    return re.compile("".join(pieces))


def active_credential_variants(token: str | None) -> tuple[str, ...]:
    """Build raw and JSON-escaped forms of the active credential only."""
    if not token:
        return ()
    credentials = {token.strip()}
    credentials.discard("")
    scheme_parts = token.strip().split(maxsplit=1)
    if len(scheme_parts) == QUOTED_CREDENTIAL_MIN_LENGTH and scheme_parts[0].casefold() in {
        "bearer",
        "basic",
        "token",
    }:
        credentials.add(scheme_parts[1])

    variants = set(credentials)
    for credential in credentials:
        variants.add(json.dumps(credential, allow_nan=False, ensure_ascii=True)[1:-1])
    variants.discard("")
    return tuple(sorted(variants, key=len, reverse=True))


def encoded_credential_pattern(credential: str) -> re.Pattern[str]:
    """Match raw or independently percent-encoded characters of one credential."""
    pieces: list[str] = []
    for character in credential:
        encoded = "".join(f"%{byte:02X}" for byte in character.encode("utf-8"))
        alternatives = [re.escape(character), percent_triplet_pattern(encoded).pattern]
        if character == " ":
            alternatives.append(r"\+")
        pieces.append(f"(?:{'|'.join(dict.fromkeys(alternatives))})")
    return re.compile("".join(pieces))


def unquoted_credential(value: str) -> tuple[str, bool]:
    """Return a scheme credential without one matching quote pair."""
    if len(value) >= QUOTED_CREDENTIAL_MIN_LENGTH and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1], True
    return value, False


def valid_basic_credential(value: str) -> bool:
    """Return whether a Basic value is valid base64 containing user/password syntax."""
    credential = value.rstrip(".!?)]}")
    try:
        decoded = base64.b64decode(credential, validate=True)
    except ValueError:
        return False
    return b":" in decoded


def redact_untrusted_scalar(value: str, token: str | None) -> str:
    """Redact credentials in one scalar while preserving explanatory prose."""
    text = value
    for variant in active_credential_variants(token):
        text = encoded_credential_pattern(variant).sub(REDACTED_TEXT, text)

    text = URL_USERINFO.sub(r"\1<redacted>@", text)
    text = AUTHORIZATION_ASSIGNMENT.sub("Authorization: <redacted>", text)

    def redact_assignment(match: re.Match[str]) -> str:
        raw_name = match.group("name")
        if not is_sensitive_key(raw_name):
            return match.group(0)
        return "".join(
            (
                match.group("prefix"),
                match.group("key_quote"),
                raw_name,
                match.group("key_quote"),
                match.group("before"),
                match.group("separator"),
                match.group("after"),
                REDACTED_TEXT,
            )
        )

    for assignment_pattern in SENSITIVE_ASSIGNMENTS:
        text = assignment_pattern.sub(redact_assignment, text)

    def redact_scheme(match: re.Match[str]) -> str:
        scheme = match.group("scheme")
        raw_credential = match.group("credential")
        credential, was_quoted = unquoted_credential(raw_credential)
        normalized_credential = credential.rstrip(".!?)]}")
        if not normalized_credential or normalized_credential.casefold() in SCHEME_PROSE_WORDS:
            return match.group(0)
        if scheme.casefold() == "basic" and not valid_basic_credential(normalized_credential):
            return match.group(0)
        if (
            scheme.casefold() == "token"
            and not was_quoted
            and normalized_credential.isalpha()
            and len(normalized_credential) < MIN_UNQUOTED_TOKEN_CREDENTIAL_LENGTH
        ):
            return match.group(0)
        return f"{scheme} <redacted>"

    return SCHEME_CREDENTIAL.sub(redact_scheme, text)


def safe_untrusted_reason(reason: object, token: str | None) -> str:
    """Bound and redact untrusted transport error text."""
    return redact_untrusted_scalar(str(reason), token)[:MAX_UNTRUSTED_REASON_TEXT]


def redact_json(value: JsonValue, token: str | None) -> JsonValue:
    """Recursively redact sensitive fields and credential-bearing scalars."""
    if isinstance(value, dict):
        return {
            key: REDACTED_TEXT if is_sensitive_key(key) else redact_json(item, token) for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_json(item, token) for item in value]
    if isinstance(value, str):
        return redact_untrusted_scalar(value, token)
    return value


def encode_url(url: str, query: dict[str, str]) -> str:
    """Append encoded query parameters to a validated URL."""
    parsed = parse.urlsplit(url)
    return parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parse.urlencode(query), ""))


def fallback_retry_delay(attempt: int) -> float:
    """Return a capped fallback without exponentiating an unbounded attempt."""
    try:
        numeric_attempt = int(attempt)
    except OverflowError, TypeError, ValueError:
        numeric_attempt = 0
    bounded_attempt = min(max(numeric_attempt, 0), MAX_RETRIES)
    return min(float(1 << bounded_attempt), MAX_RETRY_DELAY_SECONDS)


def parse_retry_after(http_error: error.HTTPError, attempt: int) -> float:
    """Return a finite bounded Retry-After delay or a safe fallback."""
    fallback = fallback_retry_delay(attempt)
    value = http_error.headers.get("Retry-After", "").strip()
    if not value:
        return fallback
    try:
        delay = float(value)
    except ValueError:
        return fallback
    if not math.isfinite(delay) or delay < 0:
        return fallback
    return min(delay, MAX_RETRY_DELAY_SECONDS)


def response_payload(data: bytes, content_type: str, token: str | None = None) -> JsonValue:
    """Decode JSON or retain bounded external response text."""
    if "json" in content_type.lower():
        return decode_json(data, source="Socket API")
    text = data.decode("utf-8", errors="replace")
    return redact_untrusted_scalar(text, token)[:MAX_RESPONSE_TEXT]


def require_write_response_body(data: bytes) -> None:
    """Reject an empty success body after a Socket write may have applied."""
    if not data:
        raise SocketCliError("Socket API write response was empty.")


def prepare_request(
    context: SocketContext, plan: RequestPlan, query: dict[str, str]
) -> tuple[str, bytes | None, dict[str, str]]:
    """Validate the target before constructing authentication-bearing headers."""
    checked_url = validated_endpoint_url(context.base_url, plan.url)
    for name in query:
        if is_sensitive_key(name):
            raise SocketCliError(f"Refusing token-like query parameter: {name}")
    url = encode_url(checked_url, query)
    body = (
        None
        if plan.body is None
        else serialize_json(plan.body, pretty=False, source="Socket request body").encode("utf-8")
    )
    headers = {"Accept": JSON_MEDIA_TYPE, "User-Agent": "codex-socket-management/1"}
    if body is not None:
        headers["Content-Type"] = JSON_MEDIA_TYPE
    if context.token is not None:
        headers["Authorization"] = f"Bearer {context.token}"
    return url, body, headers


def handle_http_error(
    exception: error.HTTPError,
    *,
    context: SocketContext,
    is_read: bool,
    attempt: int,
    retries: int,
) -> bool:
    """Retry a GET HTTP failure or raise a redacted terminal error."""
    try:
        get_retryable = is_read and exception.code in GET_RETRYABLE_STATUS_CODES
        write_indeterminate = not is_read and exception.code in WRITE_INDETERMINATE_STATUS_CODES
        if get_retryable and attempt < retries:
            time.sleep(parse_retry_after(exception, attempt))
            return True
        try:
            data = read_bounded_response(
                exception,
                exception.headers,
                limit=MAX_ERROR_RESPONSE_BYTES,
                source="Socket API error response",
            )
            payload = response_payload(data, exception.headers.get("Content-Type", ""), context.token)
        except (HTTPException, OSError, SocketCliError) as body_exception:
            safe_detail = safe_untrusted_reason(body_exception, context.token)
            if write_indeterminate:
                message = (
                    f"Socket API write returned HTTP {exception.code} after one attempt and was not retried; "
                    "the outcome is indeterminate. Verify Socket state before retrying. "
                    f"The error response could not be safely processed: {safe_detail}"
                )
                raise SocketCliError(message) from body_exception
            raise SocketCliError(
                f"Socket API returned HTTP {exception.code}, but its error response could not be safely processed: "
                + safe_detail
            ) from body_exception
        safe_payload = redact_json(payload, context.token)
        rendered_payload = serialize_json(safe_payload, pretty=False, source="redacted Socket error response")
        if write_indeterminate:
            message = (
                f"Socket API write returned HTTP {exception.code} after one attempt and was not retried; "
                f"the outcome is indeterminate. Verify Socket state before retrying. Response: "
                f"{rendered_payload}"
            )
            raise SocketCliError(message) from exception
        raise SocketCliError(f"Socket API returned HTTP {exception.code}: {rendered_payload}") from exception
    finally:
        exception.close()


def handle_url_error(
    exception: error.URLError | OSError | HTTPException,
    *,
    context: SocketContext,
    is_read: bool,
    attempt: int,
    retries: int,
) -> bool:
    """Retry a GET transport failure or raise an indeterminate write error."""
    if is_read and attempt < retries:
        time.sleep(fallback_retry_delay(attempt))
        return True
    raw_reason = exception.reason if isinstance(exception, error.URLError) else exception
    reason = safe_untrusted_reason(raw_reason, context.token)
    if not is_read:
        message = (
            "Socket API write failed after one attempt and was not retried; the outcome is indeterminate. "
            f"Verify Socket state before retrying. Transport error: {reason}"
        )
        raise SocketCliError(message) from exception
    raise SocketCliError(f"Socket API request failed: {reason}") from exception


def consume_success_response(
    response: IO[bytes],
    headers: Message[str, str],
    *,
    status: int,
    is_read: bool,
    token: str | None,
) -> tuple[JsonValue, bytes]:
    """Read one success response while preserving indeterminate-write guidance."""
    try:
        data = read_bounded_response(
            response,
            headers,
            limit=MAX_API_RESPONSE_BYTES,
            source="Socket API response",
        )
        if not is_read:
            require_write_response_body(data)
        return response_payload(data, headers.get("Content-Type", ""), token), data
    except (HTTPException, OSError, SocketCliError) as response_exception:
        safe_detail = safe_untrusted_reason(response_exception, token)
        if not is_read:
            write_result = f"Socket API write returned HTTP {status} after one attempt and was not retried"
            response_failure = f"Response failure: {safe_detail}"
            message = (
                f"{write_result}, but the success response could not be safely processed; "
                f"the outcome is indeterminate. Verify Socket state before retrying. {response_failure}"
            )
            raise SocketCliError(message) from response_exception
        if isinstance(response_exception, SocketCliError):
            raise
        raise SocketCliError(
            f"Socket API response could not be safely processed: {safe_detail}"
        ) from response_exception


def send_request(
    context: SocketContext, plan: RequestPlan, *, query: dict[str, str], arguments: argparse.Namespace
) -> ApiResult:
    """Send one authenticated request, retrying only idempotent GET reads."""
    url, body, headers = prepare_request(context, plan, query)
    opener = request.build_opener(NoRedirectHandler())
    retries = validated_retries(arguments.retries)
    timeout = validated_timeout(arguments.timeout)
    is_read = plan.method == "GET"
    attempts = retries + 1 if is_read else 1
    for attempt in range(attempts):
        api_request = request.Request(  # noqa: S310  # build_plan origin-locks the URL.
            url,
            data=body,
            headers=headers,
            method=plan.method,
        )
        try:
            with opener.open(api_request, timeout=timeout) as response:  # URL is origin locked.
                status = int(response.status)
                payload, data = consume_success_response(
                    response,
                    response.headers,
                    status=status,
                    is_read=is_read,
                    token=context.token,
                )
                return ApiResult(
                    payload=payload,
                    status=status,
                    url=url,
                    response_bytes=len(data),
                )
        except error.HTTPError as exception:
            if handle_http_error(
                exception,
                context=context,
                is_read=is_read,
                attempt=attempt,
                retries=retries,
            ):
                continue
        except (error.URLError, OSError, HTTPException) as exception:
            if handle_url_error(
                exception,
                context=context,
                is_read=is_read,
                attempt=attempt,
                retries=retries,
            ):
                continue
    raise SocketCliError("Socket API retry loop ended unexpectedly.")


def paginated_request(context: SocketContext, plan: RequestPlan, arguments: argparse.Namespace) -> ApiResult:
    """Follow Socket items/endCursor pages until the cursor is explicitly null."""
    if plan.method != "GET":
        raise SocketCliError("--paginate is supported only for GET requests.")
    query = dict(plan.query)
    merged: list[JsonValue] = []
    response_bytes = 0
    seen_cursors: set[str] = set()
    initial_cursor = query.get("startAfterCursor")
    if initial_cursor:
        seen_cursors.add(initial_cursor)
    max_pages = validated_max_pages(arguments.max_pages)
    for page_number in range(1, max_pages + 1):
        page = send_request(context, plan, query=query, arguments=arguments)
        if page.response_bytes > MAX_PAGINATED_RESPONSE_BYTES - response_bytes:
            message = " ".join(
                (
                    f"Paginated Socket API responses exceeded the {MAX_PAGINATED_RESPONSE_BYTES}-byte cumulative",
                    f"safety limit after {page_number - 1} pages fetched; the overflow page was not retained.",
                )
            )
            raise SocketCliError(message)
        response_bytes += page.response_bytes
        payload = page.payload
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list) or "endCursor" not in payload:
            raise SocketCliError("Paginated response must contain items and endCursor fields.")
        merged.extend(cast("list[JsonValue]", payload["items"]))
        cursor = payload["endCursor"]
        if cursor is None:
            return ApiResult(
                payload={
                    "items": merged,
                    "endCursor": None,
                    "pages": page_number,
                },
                status=page.status,
                url=page.url,
                response_bytes=response_bytes,
            )
        if not isinstance(cursor, str) or not cursor:
            raise SocketCliError("endCursor must be a non-empty string or null.")
        if cursor in seen_cursors:
            raise SocketCliError(
                f"Pagination is incomplete after {page_number} page(s): repeated endCursor; refusing the next request."
            )
        seen_cursors.add(cursor)
        query["startAfterCursor"] = cursor
    raise SocketCliError("Pagination reached --max-pages before endCursor became null.")


def write_json(value: JsonValue, *, prefix: str = "") -> None:
    """Serialize strict JSON fully, then emit it with one stdout write."""
    rendered = serialize_json(value, pretty=True, source="command output")
    _ = sys.stdout.write(f"{prefix}{rendered}\n")


def handle_context(arguments: argparse.Namespace) -> int:
    """Print safe resolved context."""
    context = resolve_context(arguments)
    write_json(
        {
            "baseUrl": context.base_url,
            "organization": context.organization,
            "repository": context.repository,
            "repositoryRoot": str(context.repository_root),
            "token": "configured" if context.token else "missing",
            "tokenEnvironment": context.token_env_name,
        }
    )
    return 0


def handle_operations(arguments: argparse.Namespace) -> int:
    """Search the current Socket OpenAPI operation catalog."""
    context = resolve_context(arguments)
    spec, source = load_openapi(arguments, context)
    search = (optional_text(arguments.search) or "").casefold()
    method = (optional_text(arguments.filter_method) or "").upper()
    operations = [
        operation
        for operation in parse_operations(spec)
        if (not method or operation.method == method)
        and (
            not search
            or search
            in " ".join((operation.operation_id, operation.path, operation.summary, *operation.tags)).casefold()
        )
    ]
    write_json({"operations": [cast("JsonValue", asdict(item)) for item in operations], "source": source})
    return 0


def handle_request(arguments: argparse.Namespace) -> int:
    """Preview or send a constrained Socket request."""
    context = resolve_context(arguments)
    plan = build_plan(arguments, context)
    preview = bool(arguments.dry_run) or (plan.method != "GET" and not bool(arguments.send))
    if preview:
        write_json(
            {
                "body": redact_json(plan.body, context.token),
                "dryRun": True,
                "method": plan.method,
                "operationId": plan.operation_id,
                "query": cast("JsonValue", plan.query),
                "url": encode_url(plan.url, plan.query),
            }
        )
        return 0
    if context.token is None and not bool(arguments.allow_unauthenticated):
        raise SocketCliError("No token found. Set SOCKET_SECURITY_API_TOKEN or use --token-env.")
    result = (
        paginated_request(context, plan, arguments)
        if bool(arguments.paginate)
        else send_request(context, plan, query=plan.query, arguments=arguments)
    )
    output: JsonValue = {
        "meta": {
            "method": plan.method,
            "operationId": plan.operation_id,
            "status": result.status,
            "untrustedExternalData": True,
            "url": result.url,
        },
        "response": redact_json(result.payload, context.token),
    }
    prefix = "" if bool(arguments.json) else "[untrusted-socket-data]\n"
    write_json(output, prefix=prefix)
    return 0 if HTTP_SUCCESS_MIN <= result.status < HTTP_SUCCESS_LIMIT else 1


def common_parser() -> argparse.ArgumentParser:
    """Build options shared by every command."""
    parser = argparse.ArgumentParser(add_help=False)
    _ = parser.add_argument("--repo", type=resolve_repository, default=resolve_repository("."))
    _ = parser.add_argument("--org", help="Socket organization slug; inferred from a GitHub origin when possible.")
    _ = parser.add_argument("--repository", help="Socket/GitHub repository name.")
    _ = parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    _ = parser.add_argument("--token-env", action="append", dest="token_envs", default=[])
    _ = parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    return parser


def add_spec_options(parser: argparse.ArgumentParser) -> None:
    """Add OpenAPI source and timeout options."""
    source = parser.add_mutually_exclusive_group()
    _ = source.add_argument("--spec-file", type=Path, help="Read OpenAPI JSON from a local file.")
    _ = source.add_argument("--spec-url", help="Read OpenAPI JSON from the configured Socket origin.")
    _ = parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    common = common_parser()

    context = subparsers.add_parser("context", parents=[common], help="Show safe target and token metadata.")
    context.set_defaults(handler=handle_context)

    operations = subparsers.add_parser("operations", parents=[common], help="Search Socket OpenAPI operations.")
    add_spec_options(operations)
    _ = operations.add_argument("--search")
    _ = operations.add_argument("--method", dest="filter_method", choices=("GET", "POST", "PUT", "PATCH", "DELETE"))
    operations.set_defaults(handler=handle_operations)

    api_request = subparsers.add_parser("request", parents=[common], help="Preview or send a Socket v0 request.")
    add_spec_options(api_request)
    _ = api_request.add_argument("endpoint", nargs="?", help="Relative v0 endpoint or same-base absolute URL.")
    _ = api_request.add_argument("--operation-id")
    _ = api_request.add_argument("--method", choices=("GET", "POST", "PUT", "PATCH", "DELETE"))
    _ = api_request.add_argument("--path", action="append", dest="path_values", default=[])
    _ = api_request.add_argument("--query", action="append", default=[])
    body = api_request.add_mutually_exclusive_group()
    _ = body.add_argument("--body-json")
    _ = body.add_argument("--body-file", type=Path)
    _ = api_request.add_argument("--paginate", action="store_true")
    _ = api_request.add_argument("--max-pages", type=int, default=DEFAULT_MAX_PAGES)
    _ = api_request.add_argument("--retries", type=int, default=DEFAULT_RETRIES)
    _ = api_request.add_argument("--send", action="store_true")
    _ = api_request.add_argument("--dry-run", action="store_true")
    _ = api_request.add_argument("--allow-unauthenticated", action="store_true")
    api_request.set_defaults(handler=handle_request)
    return parser


def validate_arguments(arguments: argparse.Namespace) -> None:
    """Validate numeric and mutually exclusive runtime options."""
    if hasattr(arguments, "timeout"):
        _ = validated_timeout(arguments.timeout)
    if hasattr(arguments, "max_pages"):
        _ = validated_max_pages(arguments.max_pages)
    if hasattr(arguments, "retries"):
        _ = validated_retries(arguments.retries)
    if hasattr(arguments, "send") and bool(arguments.send) and bool(arguments.dry_run):
        raise SocketCliError("--send and --dry-run are mutually exclusive.")


def main() -> int:
    """Run the Socket management helper."""
    parser = build_parser()
    arguments = parser.parse_args()
    try:
        validate_arguments(arguments)
        handler = cast("Callable[[argparse.Namespace], int]", arguments.handler)
        return handler(arguments)
    except (SocketCliError, OSError) as exception:
        _ = sys.stderr.write(f"Error: {exception}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
