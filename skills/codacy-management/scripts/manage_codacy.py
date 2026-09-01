#!/usr/bin/env python
# Copyright (c) 2026 Nick2bad4u
"""Inspect Codacy API operations and make origin-locked v3 requests."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from http.client import HTTPException
from pathlib import Path
from typing import TYPE_CHECKING, cast, override
from urllib import error, parse, request

if TYPE_CHECKING:
    from collections.abc import Callable
    from http.client import HTTPMessage, HTTPResponse
    from typing import IO, Never

type JsonValue = bool | int | float | str | list[JsonValue] | dict[str, JsonValue] | None
type JsonContainer = list[JsonValue] | dict[str, JsonValue]

DEFAULT_BASE_URL = "https://api.codacy.com/api/v3"
DEFAULT_TOKEN_ENVS = ("CODACY_API_TOKEN",)
DEFAULT_TIMEOUT = 30.0
DEFAULT_MAX_PAGES = 100
DEFAULT_RETRIES = 2
API_BASE_PATH = "/api/v3"
ASCII_CONTROL_LIMIT = 32
ASCII_DELETE = 127
MAX_API_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_DECODE_ITERATIONS = 5
MAX_ERROR_BODY_BYTES = 16 * 1024
MAX_JSON_NESTING_DEPTH = 64
MAX_MAX_PAGES = 500
MAX_OPENAPI_BYTES = 16 * 1024 * 1024
MAX_PAGINATED_RESPONSE_BYTES = 32 * 1024 * 1024
MAX_PAGE_LIMIT = 1000
MAX_PORT = 65535
MAX_RETRIES = 10
MAX_RETRY_DELAY = 60.0
MAX_RETRY_DELAY_DIGITS = len(str(int(MAX_RETRY_DELAY)))
MAX_TIMEOUT = 300.0
MAX_UNTRUSTED_TEXT = 1000
MIN_REMOTE_PATH_PARTS = 2
MATCHING_QUOTE_MIN_LENGTH = 2
HTTP_TOO_MANY_REQUESTS = 429
HTTP_REQUEST_TIMEOUT = 408
HTTP_SERVER_ERROR_MIN = 500
HTTP_SERVER_ERROR_LIMIT = 600
HTTP_SERVICE_UNAVAILABLE = 503
HTTP_GATEWAY_TIMEOUT = 504
HTTP_SUCCESS_MIN = 200
HTTP_SUCCESS_LIMIT = 300
RETRYABLE_STATUS_CODES = frozenset({HTTP_TOO_MANY_REQUESTS, HTTP_SERVICE_UNAVAILABLE, HTTP_GATEWAY_TIMEOUT})
ENVIRONMENT_NAME = re.compile(r"^(?!\d)\w+$", re.ASCII)
OPENAPI_PATH = re.compile(r"^ {2}(/[^:]+):\s*$")
OPENAPI_METHOD = re.compile(r"^ {4}(get|post|put|patch|delete):\s*$", re.IGNORECASE)
OPENAPI_OPERATION_ID = re.compile(r"^ {6}operationId:(.+)$")
OPENAPI_SUMMARY = re.compile(r"^ {6}summary:(.+)$")
PATH_PARAMETER = re.compile(r"\{([^{}]+)\}")
RETRY_AFTER_DELAY_SECONDS = re.compile(r"[0-9]+", re.ASCII)
ENCODED_PATH_CONTROL = re.compile(r"%(?:2e|2f|3f|23|5c|25)", re.IGNORECASE)
SENSITIVE_KEY_CORE = r"api[-_]?key|auth(?:entication|orization)?|credential|pass(?:word|wd)|private[-_]?key|secret"
SENSITIVE_KEY_SUFFIX = r"sig(?:nature)?|token|(?:^|[-_.])key(?:$|[-_.])"
SENSITIVE_KEY = re.compile(
    f"{SENSITIVE_KEY_CORE}|{SENSITIVE_KEY_SUFFIX}",
    flags=re.IGNORECASE,
)
JSON_MEDIA_TYPE = "application/json"
REDACTED_VALUE = "<redacted>"


class CodacyCliError(RuntimeError):
    """Report a safe, user-facing helper error."""


class NonFiniteJsonNumberError(ValueError):
    """Mark a non-standard non-finite JSON numeric constant."""


class JsonNestingError(ValueError):
    """Mark JSON that exceeds the explicit container nesting limit."""


class JsonStructureError(ValueError):
    """Mark runtime values that cannot be represented as finite JSON trees."""


class PostSendResponseError(RuntimeError):
    """Carry a response-processing failure without including untrusted details."""

    def __init__(self, cause: BaseException) -> None:
        """Store the original failure without putting its text in exception arguments."""
        super().__init__("Codacy response processing failed.")
        self.cause = cause


class NoRedirectHandler(request.HTTPRedirectHandler):
    """Reject redirects so authenticated headers cannot cross trust boundaries."""

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
        """Refuse every redirect and let urllib surface the original response."""
        del req, fp, code, msg, headers, newurl
        return None


@dataclass(frozen=True)
class RepositorySlug:
    """Codacy repository identity inferred from a git remote."""

    organization: str
    provider: str
    repository: str


@dataclass(frozen=True)
class CodacyContext:
    """Resolved API, repository, and token context."""

    base_url: str
    repository_root: Path
    slug: RepositorySlug | None
    token: str | None
    token_env_name: str | None


@dataclass(frozen=True)
class OpenApiOperation:
    """Minimal operation metadata parsed from Codacy's OpenAPI YAML."""

    method: str
    operation_id: str
    path: str
    summary: str


@dataclass(frozen=True)
class RequestPlan:
    """Resolved request details."""

    body: JsonValue
    endpoint: str
    method: str
    operation_id: str | None
    query: dict[str, str]


@dataclass(frozen=True)
class RequestRuntime:
    """Network controls shared by one or more Codacy requests."""

    retries: int
    retry_base_delay: float
    timeout: float


@dataclass(frozen=True)
class ApiResult:
    """One Codacy API response."""

    payload: JsonValue
    status: int
    url: str
    response_bytes: int = 0


def resolve_repository(value: str) -> Path:
    """Resolve an existing repository directory from a CLI value."""
    try:
        repository = Path(value).expanduser().resolve(strict=True)
    except OSError as exception:
        raise argparse.ArgumentTypeError(f"Repository path does not exist: {value}") from exception
    if not repository.is_dir():
        raise argparse.ArgumentTypeError(f"Repository path is not a directory: {value}")
    return repository


def validate_decoded_path_layer(path: str, label: str) -> None:
    """Reject path structures that can change routing or escape a base path."""
    if "\\" in path or "?" in path or "#" in path:
        raise CodacyCliError(f"{label} contains an encoded path separator or delimiter.")
    if any(ord(character) < ASCII_CONTROL_LIMIT or ord(character) == ASCII_DELETE for character in path):
        raise CodacyCliError(f"{label} contains a control character.")
    if any(segment in {".", ".."} for segment in path.split("/")):
        raise CodacyCliError(f"{label} must not contain traversal path segments.")


def decode_path_strict(path: str, label: str) -> str:
    """Repeatedly decode a URL path under a bounded, traversal-safe contract."""
    current = path
    for iteration in range(MAX_DECODE_ITERATIONS):
        validate_decoded_path_layer(current, label)
        if iteration > 0 and ENCODED_PATH_CONTROL.search(current):
            raise CodacyCliError(f"{label} contains nested encoding that can alter path structure.")
        try:
            decoded = parse.unquote(current, errors="strict")
        except UnicodeError as exception:
            raise CodacyCliError(f"{label} contains invalid percent-encoded UTF-8.") from exception
        if decoded == current:
            if "%" in current:
                raise CodacyCliError(f"{label} contains a residual percent escape.")
            return current
        current = decoded
    raise CodacyCliError(f"{label} exceeds the {MAX_DECODE_ITERATIONS}-pass decoding safety limit.")


def split_url(value: str, label: str) -> parse.SplitResult:
    """Parse a URL while converting authority parser failures to a safe CLI error."""
    try:
        return parse.urlsplit(value)
    except ValueError as exception:
        raise CodacyCliError(f"{label} contains a malformed URL authority.") from exception


def authority_parts(parsed: parse.SplitResult) -> tuple[str, int | None] | None:
    """Return a validated hostname and optional explicit port, or None when malformed."""
    try:
        hostname = parsed.hostname
        port = parsed.port
    except ValueError:
        return None
    authority = parsed.netloc.rsplit("@", maxsplit=1)[-1]
    valid_authority = bool(hostname)
    if authority.startswith("["):
        closing_bracket = authority.find("]")
        suffix = authority[closing_bracket + 1 :] if closing_bracket >= 0 else ""
        valid_authority = valid_authority and closing_bracket >= 0
        valid_authority = valid_authority and (not suffix or (suffix.startswith(":") and len(suffix) > 1))
    else:
        valid_authority = valid_authority and authority.count(":") <= 1
        valid_authority = valid_authority and (":" not in authority or bool(authority.rsplit(":", maxsplit=1)[1]))

    valid_port = port is None or 1 <= port <= MAX_PORT
    return (hostname, port) if valid_authority and valid_port and hostname is not None else None


def require_url_authority(parsed: parse.SplitResult, label: str) -> tuple[str, int | None]:
    """Require a hostname and a valid optional port without echoing the authority."""
    parts = authority_parts(parsed)
    if parts is None:
        raise CodacyCliError(f"{label} must contain a valid hostname and optional port from 1 through 65535.")
    return parts


def sanitize_base_url(value: str) -> str:
    """Validate and normalize a token-bearing Codacy v3 base URL."""
    base_url = value.strip()
    parsed = split_url(base_url, "Codacy API base URL")
    if parsed.scheme.lower() != "https" or not parsed.netloc:
        raise CodacyCliError("Codacy API base URL must be an absolute HTTPS URL.")
    _ = require_url_authority(parsed, "Codacy API base URL")
    if parsed.username is not None or parsed.password is not None:
        raise CodacyCliError("Codacy API base URL must not contain credentials.")
    if parsed.query or parsed.fragment:
        raise CodacyCliError("Codacy API base URL must not contain a query or fragment.")
    if parsed.path not in {API_BASE_PATH, f"{API_BASE_PATH}/"}:
        raise CodacyCliError(f"Codacy API base URL path must be exactly {API_BASE_PATH}.")
    decoded_path = decode_path_strict(parsed.path.rstrip("/"), "Codacy API base URL path")
    if decoded_path != API_BASE_PATH:
        raise CodacyCliError(f"Codacy API base URL path must normalize exactly to {API_BASE_PATH}.")
    return parse.urlunsplit(("https", parsed.netloc, API_BASE_PATH, "", ""))


def run_git(repository: Path, *arguments: str) -> str | None:
    """Run a read-only git command and return stripped output."""
    executable = shutil.which("git")
    if executable is None:
        return None
    result = subprocess.run(  # noqa: S603  # Fixed executable and argument vector; no shell.
        [executable, *arguments],
        cwd=repository,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    output = result.stdout.strip()
    return output or None


def parse_remote_slug(remote_url: str) -> RepositorySlug | None:
    """Parse a GitHub, GitLab, or Bitbucket Cloud remote."""
    value = remote_url.strip()
    if "://" not in value and re.match(r"^[^@\s]+@[^:\s]+:.+$", value):
        user_host, remote_path = value.split(":", maxsplit=1)
        value = f"ssh://{user_host}/{remote_path}"

    parsed = parse.urlsplit(value)
    host = (parsed.hostname or "").lower()
    providers = {
        "bitbucket.org": "bb",
        "github.com": "gh",
        "gitlab.com": "gl",
    }
    provider = providers.get(host)
    if provider is None:
        return None

    parts = [parse.unquote(part) for part in parsed.path.strip("/").split("/") if part]
    if len(parts) < MIN_REMOTE_PATH_PARTS:
        return None
    organization = "/".join(parts[:-1])
    repository = parts[-1].removesuffix(".git")
    if not organization or not repository:
        return None
    return RepositorySlug(organization=organization, provider=provider, repository=repository)


def resolve_slug(arguments: argparse.Namespace, repository_root: Path) -> RepositorySlug | None:
    """Resolve a slug from explicit values and the git origin."""
    detected = None
    remote_url = run_git(repository_root, "remote", "get-url", "origin")
    if remote_url is not None:
        detected = parse_remote_slug(remote_url)

    provider = optional_text(arguments.provider) or (detected.provider if detected else None)
    organization = optional_text(arguments.organization) or (detected.organization if detected else None)
    repository = optional_text(arguments.repository) or (detected.repository if detected else None)
    supplied = [provider, organization, repository]
    if all(value is None for value in supplied):
        return None
    if any(value is None for value in supplied):
        raise CodacyCliError(
            "Repository identity is incomplete. Supply --provider, --organization, and --repository together."
        )
    return RepositorySlug(
        organization=cast("str", organization),
        provider=cast("str", provider),
        repository=cast("str", repository),
    )


def optional_text(value: object) -> str | None:
    """Return a stripped optional string."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def resolve_token(token_envs: list[str]) -> tuple[str | None, str | None]:
    """Resolve the first non-empty account token from safe environment names."""
    candidates = token_envs or list(DEFAULT_TOKEN_ENVS)
    for name in candidates:
        if ENVIRONMENT_NAME.fullmatch(name) is None:
            raise CodacyCliError(f"Invalid token environment variable name: {name}")
        token = os.environ.get(name, "").strip()
        if token:
            return token, name
    return None, None


def as_string_list(value: object, label: str) -> list[str]:
    """Validate a dynamic argparse value as a string list."""
    if isinstance(value, list):
        items = cast("list[object]", value)
        if all(isinstance(item, str) for item in items):
            return [item for item in items if isinstance(item, str)]
    raise CodacyCliError(f"{label} must be a list of strings.")


def resolve_context(arguments: argparse.Namespace) -> CodacyContext:
    """Resolve local repository, slug, base URL, and optional token."""
    repository_root = cast("Path", arguments.repo)
    token, token_env_name = resolve_token(as_string_list(arguments.token_envs, "Token environments"))
    base_url = sanitize_base_url(str(arguments.base_url))
    require_active_token_absent(base_url, token, "Codacy API base URL")
    return CodacyContext(
        base_url=base_url,
        repository_root=repository_root,
        slug=resolve_slug(arguments, repository_root),
        token=token,
        token_env_name=token_env_name,
    )


def yaml_scalar(value: str) -> str:
    """Strip matching quotes from a simple YAML scalar."""
    text = value.strip()
    if len(text) >= MATCHING_QUOTE_MIN_LENGTH and text[0] == text[-1] and text[0] in {'"', "'"}:
        return text[1:-1]
    return text


def parse_openapi_operations(document: str) -> list[OpenApiOperation]:
    """Parse paths, methods, summaries, and operation IDs from OpenAPI YAML."""
    current_path: str | None = None
    current_method: str | None = None
    current_summary = ""
    operations: list[OpenApiOperation] = []
    for line in document.splitlines():
        path_match = OPENAPI_PATH.match(line)
        if path_match:
            current_path = path_match.group(1)
            current_method = None
            current_summary = ""
            continue
        method_match = OPENAPI_METHOD.match(line)
        if current_path is not None and method_match:
            current_method = method_match.group(1).upper()
            current_summary = ""
            continue
        summary_match = OPENAPI_SUMMARY.match(line)
        if current_method is not None and summary_match:
            current_summary = yaml_scalar(summary_match.group(1))
            continue
        operation_match = OPENAPI_OPERATION_ID.match(line)
        if current_path is not None and current_method is not None and operation_match:
            operations.append(
                OpenApiOperation(
                    method=current_method,
                    operation_id=yaml_scalar(operation_match.group(1)),
                    path=current_path,
                    summary=current_summary,
                )
            )
            current_method = None
            current_summary = ""
    return operations


def derived_spec_url(base_url: str) -> str:
    """Derive the standard Codacy OpenAPI URL from a v3 base URL."""
    parsed = parse.urlsplit(base_url)
    return parse.urlunsplit((parsed.scheme, parsed.netloc, "/api/api-docs/swagger.yaml", "", ""))


def load_openapi_document(arguments: argparse.Namespace, context: CodacyContext) -> tuple[str, str]:
    """Load OpenAPI YAML from a file or HTTPS URL."""
    spec_file = cast("Path | None", arguments.spec_file)
    if spec_file is not None:
        try:
            with spec_file.open("rb") as stream:
                document = read_bounded_stream(stream, max_bytes=MAX_OPENAPI_BYTES, label="Codacy OpenAPI document")
            return document.decode("utf-8"), str(spec_file)
        except UnicodeError as exception:
            raise CodacyCliError("Codacy OpenAPI document is not valid UTF-8.") from exception

    spec_url = optional_text(arguments.spec_url) or derived_spec_url(context.base_url)
    parsed = split_url(spec_url, "OpenAPI specification URL")
    if parsed.scheme.lower() != "https" or not parsed.netloc:
        raise CodacyCliError("OpenAPI specification URL must be an absolute HTTPS URL.")
    _ = require_url_authority(parsed, "OpenAPI specification URL")
    if parsed.username is not None or parsed.password is not None:
        raise CodacyCliError("OpenAPI specification URL must not contain credentials.")
    if parsed.fragment:
        raise CodacyCliError("OpenAPI specification URL must not contain a fragment.")
    for name, _value in parse.parse_qsl(parsed.query, keep_blank_values=True):
        if is_sensitive_name(name):
            raise CodacyCliError("Refusing token-like OpenAPI query parameter.")
    require_active_token_absent(spec_url, context.token, "OpenAPI specification URL")
    try:
        spec_request = request.Request(  # noqa: S310  # URL is validated as absolute HTTPS above.
            spec_url,
            headers={"User-Agent": "codacy-management-skill/1"},
        )
        spec_opener = request.build_opener(NoRedirectHandler())
        with spec_opener.open(spec_request, timeout=validate_timeout(float(arguments.timeout))) as response:
            document = read_bounded_response(
                response,
                max_bytes=MAX_OPENAPI_BYTES,
                label="Codacy OpenAPI download",
            )
            return document.decode("utf-8"), spec_url
    except error.HTTPError as exception:
        try:
            raise CodacyCliError(
                f"Unable to load the Codacy OpenAPI document: {safe_exception_text(exception)}"
            ) from exception
        finally:
            exception.close()
    except (error.URLError, UnicodeError, OSError) as exception:
        raise CodacyCliError(
            f"Unable to load the Codacy OpenAPI document: {safe_exception_text(exception)}"
        ) from exception


def safe_exception_text(exception: object) -> str:
    """Return bounded untrusted exception text."""
    return mark_untrusted_text(f"{type(exception).__name__} details omitted")


def mark_untrusted_text(value: str) -> str:
    """Normalize and bound external text."""
    cleaned = " ".join(value.split())[:MAX_UNTRUSTED_TEXT]
    return f"[untrusted-codacy-text] {cleaned or 'no additional details'}"


def decoded_text_variants(value: str) -> tuple[set[str], bool]:
    """Return bounded percent/form-decoded variants and whether decoding stabilized."""
    variants = {value}
    frontier = {value}
    for _iteration in range(MAX_DECODE_ITERATIONS):
        next_frontier = {
            decoded
            for current in frontier
            for decoded in (parse.unquote(current), parse.unquote_plus(current))
            if decoded not in variants
        }
        if not next_frontier:
            return variants, True
        variants.update(next_frontier)
        frontier = next_frontier
    return variants, False


def is_sensitive_name(value: str) -> bool:
    """Detect credential-like names through bounded repeated decoding."""
    variants, stable = decoded_text_variants(value)
    return not stable or any(SENSITIVE_KEY.search(candidate) for candidate in variants)


def text_contains_active_token(value: str, token: str | None) -> tuple[bool, bool]:
    """Detect an active token through plain and repeatedly encoded representations."""
    if not token:
        return False, True
    value_variants, value_stable = decoded_text_variants(value)
    token_variants, _token_stable = decoded_text_variants(token)
    present = any(secret and secret in candidate for secret in token_variants for candidate in value_variants)
    return present, value_stable


def require_active_token_absent(value: str, token: str | None, label: str) -> None:
    """Reject active credentials and excessive encoding without echoing either value."""
    present, stable = text_contains_active_token(value, token)
    if present:
        raise CodacyCliError(f"Refusing {label} because it contains the active Codacy credential.")
    if token and not stable:
        raise CodacyCliError(
            f"Refusing {label} because its encoding did not stabilize within {MAX_DECODE_ITERATIONS} passes."
        )


def require_json_token_absent(value: JsonValue, token: str | None) -> None:
    """Iteratively reject an active token from bounded JSON keys and scalar strings."""
    try:
        validate_json_tree(value, "request body")
    except JsonNestingError as exception:
        raise CodacyCliError(
            f"Request body exceeds the {MAX_JSON_NESTING_DEPTH}-level JSON nesting safety limit."
        ) from exception
    except JsonStructureError as exception:
        raise CodacyCliError("Request body is not a valid JSON tree.") from exception
    except NonFiniteJsonNumberError as exception:
        raise CodacyCliError(
            "Request body contains a non-finite number and cannot be serialized as strict JSON."
        ) from exception

    stack = [value]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            for key, child in item.items():
                require_active_token_absent(key, token, "request body")
                stack.append(child)
        elif isinstance(item, list):
            stack.extend(item)
        elif isinstance(item, str):
            require_active_token_absent(item, token, "request body")


def reject_non_finite_constant(value: str) -> Never:
    """Reject JavaScript-style non-finite constants accepted by Python's decoder."""
    raise NonFiniteJsonNumberError(value)


def validate_json_tree(value: object, source: str) -> None:
    """Iteratively enforce finite numbers, tree shape, cycles, and nesting depth."""
    stack: list[tuple[object, int, bool]] = [(value, 0, False)]
    active_containers: set[int] = set()
    while stack:
        item, parent_depth, exiting = stack.pop()
        if exiting:
            active_containers.remove(id(item))
            continue
        if isinstance(item, float) and not math.isfinite(item):
            raise NonFiniteJsonNumberError(source)
        if not isinstance(item, (dict, list)):
            continue

        container = cast("object", item)
        depth = parent_depth + 1
        if depth > MAX_JSON_NESTING_DEPTH:
            raise JsonNestingError(source)
        identity = id(container)
        if identity in active_containers:
            raise JsonStructureError(source)
        active_containers.add(identity)
        stack.append((container, depth, True))
        if isinstance(item, dict):
            for key, child in cast("dict[object, object]", item).items():
                if not isinstance(key, str):
                    raise JsonStructureError(source)
                stack.append((child, depth, False))
        else:
            stack.extend((child, depth, False) for child in cast("list[object]", item))


def require_finite_json(value: JsonValue, source: str) -> None:
    """Retain the finite-JSON validation boundary for direct callers."""
    validate_json_tree(value, source)


def strict_json_loads(text: str, source: str) -> JsonValue:
    """Decode standards-compliant JSON under explicit finite tree limits."""
    try:
        value = cast("JsonValue", json.loads(text, parse_constant=reject_non_finite_constant))
    except json.JSONDecodeError, NonFiniteJsonNumberError:
        raise
    except RecursionError as exception:
        raise JsonNestingError(source) from exception
    except (ValueError, OverflowError) as exception:
        raise JsonStructureError(source) from exception
    validate_json_tree(value, source)
    return value


def strict_json_dumps(
    value: JsonValue,
    source: str,
    *,
    indent: int | None = None,
    sort_keys: bool = False,
) -> str:
    """Serialize a finite, depth-bounded JSON tree into memory before output."""
    try:
        validate_json_tree(value, source)
        return json.dumps(
            value,
            allow_nan=False,
            indent=indent,
            separators=(",", ":") if indent is None else None,
            sort_keys=sort_keys,
        )
    except JsonNestingError as exception:
        raise CodacyCliError(
            f"Unable to serialize {source}: JSON exceeds the {MAX_JSON_NESTING_DEPTH}-level nesting safety limit."
        ) from exception
    except (JsonStructureError, TypeError, ValueError, OverflowError, RecursionError) as exception:
        raise CodacyCliError(f"Unable to serialize {source} as strict JSON.") from exception


def redact_active_token_text(value: str, token: str | None) -> str:
    """Redact plain or encoded active-token representations from output text."""
    present, stable = text_contains_active_token(value, token)
    if not present and stable:
        return value
    if not token:
        return value
    redacted = value.replace(token, REDACTED_VALUE)
    still_present, still_stable = text_contains_active_token(redacted, token)
    return safe_redaction_placeholder(token) if still_present or not still_stable else redacted


def safe_redaction_placeholder(token: str | None) -> str:
    """Return a marker only when the marker itself cannot reproduce the active token."""
    placeholder_contains_token, _placeholder_stable = text_contains_active_token(REDACTED_VALUE, token)
    return "" if placeholder_contains_token else REDACTED_VALUE


def fail_safe_redacted_text(value: str, token: str | None) -> str:
    """Ensure a redacted string cannot retain a plain or encoded active token."""
    redacted = redact_active_token_text(value, token)
    present, stable = text_contains_active_token(redacted, token)
    if not present and stable:
        return redacted
    return safe_redaction_placeholder(token)


def is_url_string(value: str) -> bool:
    """Return whether a string is an absolute or query-bearing relative URL."""
    try:
        parsed = parse.urlsplit(value)
    except ValueError:
        return False
    return (parsed.scheme.lower() in {"http", "https"} and bool(parsed.netloc)) or (
        value.startswith("/") and bool(parsed.query)
    )


def format_url_authority(hostname: str, port: int | None, *, redact_userinfo: bool) -> str:
    """Reconstruct a valid URL authority while preserving IPv6 brackets and ports."""
    formatted_hostname = f"[{hostname}]" if ":" in hostname else hostname
    formatted_port = f":{port}" if port is not None else ""
    userinfo = "redacted@" if redact_userinfo else ""
    return f"{userinfo}{formatted_hostname}{formatted_port}"


def redact_url(value: str, token: str | None, *, _depth: int = 0) -> str:
    """Redact active and query-key-implied credentials from a URL string."""
    if _depth >= MAX_JSON_NESTING_DEPTH:
        return safe_redaction_placeholder(token)
    try:
        parsed = parse.urlsplit(value)
    except ValueError:
        return fail_safe_redacted_text(value, token)

    path = redact_active_token_text(parsed.path, token)
    netloc = ""
    if parsed.netloc:
        authority = authority_parts(parsed)
        if authority is None:
            return fail_safe_redacted_text(value, token)
        hostname, port = authority
        hostname_contains_token, hostname_stable = text_contains_active_token(hostname, token)
        safe_hostname = "redacted.invalid" if hostname_contains_token or not hostname_stable else hostname
        netloc = format_url_authority(
            safe_hostname,
            port,
            redact_userinfo=parsed.username is not None or parsed.password is not None,
        )

    redacted_query: list[tuple[str, str]] = []
    for name, item in parse.parse_qsl(parsed.query, keep_blank_values=True):
        safe_name = redact_active_token_text(name, token)
        contains_token, stable = text_contains_active_token(item, token)
        if is_sensitive_name(name) or contains_token or not stable:
            safe_item = safe_redaction_placeholder(token)
        elif is_url_string(item):
            safe_item = redact_url(item, token, _depth=_depth + 1)
        else:
            safe_item = redact_active_token_text(item, token)
        redacted_query.append((safe_name, safe_item))

    fragment = parsed.fragment
    if is_sensitive_name(fragment) or text_contains_active_token(fragment, token)[0]:
        fragment = safe_redaction_placeholder(token)
    reconstructed = parse.urlunsplit(
        (
            parsed.scheme,
            netloc,
            path,
            parse.urlencode(redacted_query, doseq=True),
            fragment,
        )
    )
    return fail_safe_redacted_text(reconstructed, token)


def redact_output_string(value: str, token: str | None) -> str:
    """Redact active credentials and credential-bearing URLs from output strings."""
    if is_url_string(value):
        return redact_url(value, token)
    return redact_active_token_text(value, token)


def read_bounded_stream(stream: IO[bytes], *, max_bytes: int, label: str) -> bytes:
    """Read at most a configured byte limit from a binary stream."""
    raw = stream.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise CodacyCliError(f"{label} exceeds the {max_bytes}-byte safety limit.")
    return raw


def read_bounded_response(response: HTTPResponse, *, max_bytes: int, label: str) -> bytes:
    """Enforce declared and actual response sizes before returning bytes."""
    declared_length = response.headers.get("Content-Length")
    if declared_length is not None:
        try:
            parsed_length = int(declared_length)
        except ValueError:
            parsed_length = None
        if parsed_length is not None and parsed_length > max_bytes:
            raise CodacyCliError(f"{label} exceeds the {max_bytes}-byte safety limit.")
    return read_bounded_stream(response, max_bytes=max_bytes, label=label)


def parse_pairs(values: list[str], label: str, *, reject_sensitive: bool = False) -> dict[str, str]:
    """Parse repeatable name=value arguments."""
    result: dict[str, str] = {}
    for value in values:
        name, separator, item = value.partition("=")
        name = name.strip()
        if separator == "" or not name or not item:
            raise CodacyCliError(f"{label} values must use non-empty name=value syntax.")
        if name in result:
            raise CodacyCliError(f"Duplicate {label} name.")
        if reject_sensitive and is_sensitive_name(name):
            raise CodacyCliError(f"Refusing token-like {label} parameter.")
        result[name] = item
    if "limit" in result:
        try:
            limit = int(result["limit"])
        except ValueError as exception:
            raise CodacyCliError("Codacy pagination limit must be an integer.") from exception
        if not 1 <= limit <= MAX_PAGE_LIMIT:
            raise CodacyCliError(f"Codacy pagination limit must be between 1 and {MAX_PAGE_LIMIT}.")
    return result


def expand_endpoint(endpoint: str, context: CodacyContext, path_values: dict[str, str]) -> str:
    """Fill standard and explicit OpenAPI path parameters."""
    values = dict(path_values)
    if context.slug is not None:
        _ = values.setdefault("provider", context.slug.provider)
        _ = values.setdefault("remoteOrganizationName", context.slug.organization)
        _ = values.setdefault("repositoryName", context.slug.repository)

    def replacement(match: re.Match[str]) -> str:
        name = match.group(1)
        value = values.get(name)
        if value is None:
            safe_name = redact_output_string(name, context.token)
            raise CodacyCliError(f"Missing path parameter --path {safe_name}=<value>.")
        return parse.quote(value, safe="")

    return PATH_PARAMETER.sub(replacement, endpoint)


def parsed_origin(parsed: parse.SplitResult) -> tuple[str, str, int | None] | None:
    """Return a normalized URL origin, or None for any malformed authority."""
    authority = authority_parts(parsed)
    if authority is None:
        return None
    hostname, port = authority
    scheme = parsed.scheme.lower()
    normalized_port = 443 if scheme == "https" and port is None else port
    return scheme, hostname.casefold(), normalized_port


def decoded_path_is_under_base(path: str, label: str) -> bool:
    """Return whether a strictly decoded path remains under the v3 API base."""
    decoded = decode_path_strict(path, label).rstrip("/")
    return decoded == API_BASE_PATH or decoded.startswith(f"{API_BASE_PATH}/")


def same_origin_and_base_path(base_url: str, candidate_url: str) -> bool:
    """Return whether an absolute endpoint stays inside the configured v3 base."""
    try:
        base = parse.urlsplit(sanitize_base_url(base_url))
        candidate = parse.urlsplit(candidate_url)
    except CodacyCliError, ValueError:
        return False
    base_origin = parsed_origin(base)
    candidate_origin = parsed_origin(candidate)
    if base_origin is None or candidate_origin is None or candidate_origin != base_origin:
        return False
    if not (candidate.path == API_BASE_PATH or candidate.path.startswith(f"{API_BASE_PATH}/")):
        return False
    try:
        return decoded_path_is_under_base(candidate.path, "Codacy endpoint path")
    except CodacyCliError:
        return False


def validate_endpoint_url(endpoint_url: str) -> None:
    """Reject URL components that can leak credentials or escape the API path."""
    parsed = split_url(endpoint_url, "Codacy endpoint")
    if parsed.scheme or parsed.netloc:
        _ = require_url_authority(parsed, "Codacy endpoint")
    if parsed.username is not None or parsed.password is not None:
        raise CodacyCliError("Codacy endpoint must not contain URL credentials.")
    if parsed.fragment:
        raise CodacyCliError("Codacy endpoint must not contain a fragment.")
    _ = decode_path_strict(parsed.path, "Codacy endpoint path")
    for name, _value in parse.parse_qsl(parsed.query, keep_blank_values=True):
        if is_sensitive_name(name):
            raise CodacyCliError("Refusing token-like endpoint query parameter.")


def build_url(base_url: str, endpoint: str, query: dict[str, str]) -> str:
    """Build an origin-locked request URL."""
    base_url = sanitize_base_url(base_url)
    validate_endpoint_url(endpoint)
    parsed_endpoint = split_url(endpoint, "Codacy endpoint")
    if parsed_endpoint.scheme:
        if not same_origin_and_base_path(base_url, endpoint):
            raise CodacyCliError("Absolute endpoint must match the configured HTTPS origin and API base path.")
        base_endpoint = endpoint
    else:
        if not endpoint.startswith("/") or endpoint.startswith("//"):
            raise CodacyCliError("Relative endpoint must start with '/'.")
        base_endpoint = f"{base_url}{endpoint}"

    parsed = split_url(base_endpoint, "Codacy endpoint")
    combined_query = dict(parse.parse_qsl(parsed.query, keep_blank_values=True))
    combined_query.update(query)
    built_url = parse.urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, parse.urlencode(combined_query, doseq=False), "")
    )
    if not same_origin_and_base_path(base_url, built_url):
        raise CodacyCliError("Codacy endpoint path must remain structurally under /api/v3 after decoding.")
    return built_url


def load_json_value(text: str, source: str) -> JsonValue:
    """Parse a JSON value with a safe source label."""
    try:
        return strict_json_loads(text, source)
    except NonFiniteJsonNumberError as exception:
        raise CodacyCliError(f"Invalid JSON in {source}: non-finite numbers are not allowed.") from exception
    except JsonNestingError as exception:
        raise CodacyCliError(
            f"Invalid JSON in {source}: nesting exceeds the {MAX_JSON_NESTING_DEPTH}-level safety limit."
        ) from exception
    except JsonStructureError as exception:
        raise CodacyCliError(f"Invalid JSON in {source}: unsupported JSON structure.") from exception
    except json.JSONDecodeError as exception:
        raise CodacyCliError(
            f"Invalid JSON in {source}: line {exception.lineno}, column {exception.colno}."
        ) from exception


def load_body(arguments: argparse.Namespace) -> JsonValue:
    """Load an optional request body."""
    body_json = optional_text(arguments.body_json)
    body_file = cast("Path | None", arguments.body_file)
    if body_json is not None:
        return load_json_value(body_json, "--body-json")
    if body_file is not None:
        return load_json_value(body_file.read_text(encoding="utf-8"), "--body-file")
    return None


def assign_json_child(parent: JsonContainer, key: str | int, value: JsonValue) -> None:
    """Assign one iteratively redacted child to its typed parent container."""
    if isinstance(parent, list) and isinstance(key, int):
        parent[key] = value
        return
    if isinstance(parent, dict) and isinstance(key, str):
        parent[key] = value
        return
    raise CodacyCliError("Unable to redact an invalid JSON container.")


def redact_json(value: JsonValue, token: str | None = None) -> JsonValue:
    """Iteratively redact a finite, depth-bounded JSON tree."""
    try:
        validate_json_tree(value, "JSON redaction input")
    except JsonNestingError as exception:
        raise CodacyCliError(
            f"JSON redaction input exceeds the {MAX_JSON_NESTING_DEPTH}-level nesting safety limit."
        ) from exception
    except JsonStructureError as exception:
        raise CodacyCliError("JSON redaction input is not a valid JSON tree.") from exception
    except NonFiniteJsonNumberError as exception:
        raise CodacyCliError("JSON redaction input contains a non-finite number.") from exception

    root: list[JsonValue] = [None]
    tasks: list[tuple[JsonValue, JsonContainer, str | int]] = [(value, root, 0)]
    while tasks:
        item, parent, key = tasks.pop()
        if isinstance(item, dict):
            redacted_object: dict[str, JsonValue] = {}
            assign_json_child(parent, key, redacted_object)
            pending: list[tuple[JsonValue, JsonContainer, str | int]] = []
            for item_key, child in item.items():
                safe_key = redact_output_string(item_key, token)
                if is_sensitive_name(item_key):
                    redacted_object[safe_key] = safe_redaction_placeholder(token)
                else:
                    redacted_object[safe_key] = None
                    pending.append((child, redacted_object, safe_key))
            tasks.extend(reversed(pending))
        elif isinstance(item, list):
            redacted_list: list[JsonValue] = [None] * len(item)
            assign_json_child(parent, key, redacted_list)
            tasks.extend((child, redacted_list, index) for index, child in reversed(list(enumerate(item))))
        elif isinstance(item, str):
            assign_json_child(parent, key, redact_output_string(item, token))
        else:
            assign_json_child(parent, key, item)
    return root[0]


def read_error_body(http_error: error.HTTPError, token: str | None) -> str:
    """Read and redact a bounded HTTP error body."""
    try:
        raw = http_error.read(MAX_ERROR_BODY_BYTES + 1)
    except HTTPException, OSError:
        return mark_untrusted_text("error body unavailable")

    truncated = len(raw) > MAX_ERROR_BODY_BYTES
    bounded = raw[:MAX_ERROR_BODY_BYTES]
    if not truncated:
        try:
            parsed = strict_json_loads(bounded.decode("utf-8"), "Codacy HTTP error body")
        except (
            UnicodeError,
            json.JSONDecodeError,
            NonFiniteJsonNumberError,
            JsonNestingError,
            JsonStructureError,
        ):
            pass
        else:
            try:
                return mark_untrusted_text(
                    strict_json_dumps(redact_json(parsed, token), "Codacy HTTP error body", sort_keys=True)
                )
            except CodacyCliError:
                return mark_untrusted_text("structured error body omitted")

    text = bounded.decode("utf-8", errors="replace")
    notes = ["non-JSON error body omitted"]
    if truncated:
        notes.append("response exceeded the error-body limit")
    if token and token in text:
        notes.append(f"active credential {safe_redaction_placeholder(token)}")
    return mark_untrusted_text("; ".join(notes))


def validate_timeout(value: float) -> float:
    """Validate a finite positive timeout with an explicit upper bound."""
    if not math.isfinite(value):
        raise CodacyCliError("--timeout must be finite.")
    if value <= 0:
        raise CodacyCliError("--timeout must be greater than zero.")
    if value > MAX_TIMEOUT:
        raise CodacyCliError(f"--timeout must be at most {MAX_TIMEOUT:g} seconds.")
    return value


def validate_retry_delay(value: float) -> float:
    """Validate a finite nonnegative retry base delay with an explicit cap."""
    if not math.isfinite(value):
        raise CodacyCliError("--retry-delay must be finite.")
    if value < 0:
        raise CodacyCliError("--retry-delay must be zero or greater.")
    if value > MAX_RETRY_DELAY:
        raise CodacyCliError(f"--retry-delay must be at most {MAX_RETRY_DELAY:g} seconds.")
    return value


def validate_retries(value: int) -> int:
    """Validate the bounded number of safe automatic retries."""
    if value < 0:
        raise CodacyCliError("--retries must be zero or greater.")
    if value > MAX_RETRIES:
        raise CodacyCliError(f"--retries must be at most {MAX_RETRIES}.")
    return value


def validate_max_pages(value: int) -> int:
    """Validate the bounded cursor-pagination page count."""
    if value < 1:
        raise CodacyCliError("--max-pages must be at least one.")
    if value > MAX_MAX_PAGES:
        raise CodacyCliError(f"--max-pages must be at most {MAX_MAX_PAGES}.")
    return value


def validate_request_runtime(runtime: RequestRuntime) -> None:
    """Validate direct-call runtime controls immediately before transport."""
    _ = validate_retries(runtime.retries)
    _ = validate_retry_delay(runtime.retry_base_delay)
    _ = validate_timeout(runtime.timeout)


def bounded_backoff(attempt: int, base_delay: float) -> float:
    """Calculate exponential backoff without exponentiation or overflow."""
    delay = validate_retry_delay(base_delay)
    for _iteration in range(min(max(attempt, 0), MAX_RETRIES)):
        delay = min(delay * 2.0, MAX_RETRY_DELAY)
    return delay


def current_utc_time() -> datetime:
    """Return the current aware UTC time through a deterministic test seam."""
    return datetime.now(tz=UTC)


def parse_retry_after(value: str, now: datetime) -> float | None:
    """Parse RFC delay-seconds or HTTP-date Retry-After values."""
    parsed_delay: float | None = None
    if RETRY_AFTER_DELAY_SECONDS.fullmatch(value) is not None:
        normalized = value.lstrip("0") or "0"
        parsed_delay = (
            MAX_RETRY_DELAY
            if len(normalized) > MAX_RETRY_DELAY_DIGITS
            else min(float(int(normalized)), MAX_RETRY_DELAY)
        )
    else:
        try:
            retry_at = parsedate_to_datetime(value)
            if (
                retry_at.tzinfo is not None
                and retry_at.utcoffset() is not None
                and now.tzinfo is not None
                and now.utcoffset() is not None
            ):
                delay = (retry_at.astimezone(UTC) - now.astimezone(UTC)).total_seconds()
                if math.isfinite(delay):
                    parsed_delay = min(max(delay, 0.0), MAX_RETRY_DELAY)
        except IndexError, OverflowError, TypeError, ValueError:
            pass
    return parsed_delay


def retry_delay(http_error: error.HTTPError, attempt: int, base_delay: float) -> float:
    """Return a bounded retry delay, respecting standards-compliant Retry-After values."""
    retry_after = http_error.headers.get("Retry-After")
    if retry_after is not None:
        parsed_retry_after = parse_retry_after(retry_after, current_utc_time())
        if parsed_retry_after is not None:
            return parsed_retry_after
    return bounded_backoff(attempt, base_delay)


def backoff_delay(attempt: int, base_delay: float) -> float:
    """Return a bounded exponential delay for transport failures."""
    return bounded_backoff(attempt, base_delay)


def retries_are_safe(plan: RequestPlan) -> bool:
    """Return whether automatic replay is safe from the available request metadata."""
    return plan.method.upper() == "GET"


def retry_safety_label(plan: RequestPlan) -> str:
    """Describe the automatic retry policy in previews and output metadata."""
    return "automatic-for-get" if retries_are_safe(plan) else "disabled-for-non-get"


def validate_plan_credential_boundaries(context: CodacyContext, plan: RequestPlan, url: str | None = None) -> str:
    """Keep the active credential out of every request location except its header."""
    built_url = url or build_url(context.base_url, plan.endpoint, plan.query)
    require_active_token_absent(built_url, context.token, "request URL")
    require_json_token_absent(plan.body, context.token)
    return built_url


def decode_api_response(raw: bytes, token: str | None) -> JsonValue:
    """Decode one API response and redact malformed text fallbacks."""
    if not raw:
        return None
    try:
        return strict_json_loads(raw.decode("utf-8"), "Codacy API response")
    except NonFiniteJsonNumberError as exception:
        raise CodacyCliError("Codacy API response contains a non-finite JSON number.") from exception
    except JsonNestingError as exception:
        raise CodacyCliError(
            f"Codacy API response exceeds the {MAX_JSON_NESTING_DEPTH}-level JSON nesting safety limit."
        ) from exception
    except JsonStructureError as exception:
        raise CodacyCliError("Codacy API response contains an unsupported JSON structure.") from exception
    except UnicodeError, json.JSONDecodeError:
        text = raw.decode("utf-8", errors="replace")
        note = "non-JSON response body omitted"
        if token and token in text:
            note = f"{note}; active credential {safe_redaction_placeholder(token)}"
        return mark_untrusted_text(note)


def indeterminate_write_guidance(plan: RequestPlan) -> str:
    """Explain how to recover safely after an ambiguous non-GET failure."""
    if retries_are_safe(plan):
        return ""
    return " ".join(
        (
            f"The {plan.method} request was attempted once and was not automatically retried because its outcome",
            "may be indeterminate. Verify current Codacy state before retrying manually.",
        )
    )


def ambiguous_write_http_status(status: int) -> bool:
    """Return whether a write may have taken effect despite this HTTP status."""
    return (
        status in {HTTP_REQUEST_TIMEOUT, HTTP_TOO_MANY_REQUESTS}
        or HTTP_SERVER_ERROR_MIN <= status < HTTP_SERVER_ERROR_LIMIT
    )


def add_indeterminate_guidance(plan: RequestPlan, message: str) -> str:
    """Append non-GET recovery guidance exactly once."""
    guidance = indeterminate_write_guidance(plan)
    if not guidance or guidance in message:
        return message
    return f"{message} {guidance}"


def raise_post_send_failure(plan: RequestPlan, exception: BaseException, fallback: str) -> Never:
    """Raise a safe response-processing error after a request may have taken effect."""
    message = str(exception) if isinstance(exception, CodacyCliError) else fallback
    raise CodacyCliError(add_indeterminate_guidance(plan, message)) from exception


def raise_api_http_error(context: CodacyContext, plan: RequestPlan, exception: error.HTTPError) -> Never:
    """Convert one final HTTP error to a bounded, redacted CLI failure."""
    details = read_error_body(exception, context.token)
    message = f"Codacy API returned HTTP {exception.code}: {details}"
    if ambiguous_write_http_status(exception.code):
        message = add_indeterminate_guidance(plan, message)
    raise CodacyCliError(message) from exception


def open_api_result(
    api_opener: request.OpenerDirector,
    api_request: request.Request,
    *,
    context: CodacyContext,
    runtime: RequestRuntime,
    url: str,
) -> ApiResult:
    """Open and process one response while distinguishing post-send failures."""
    with api_opener.open(api_request, timeout=runtime.timeout) as response:
        try:
            raw = read_bounded_response(
                response,
                max_bytes=MAX_API_RESPONSE_BYTES,
                label="Codacy API response",
            )
            status = int(response.status)
            return ApiResult(
                payload=decode_api_response(raw, context.token),
                status=status,
                url=url,
                response_bytes=len(raw),
            )
        except (CodacyCliError, HTTPException, OSError, AttributeError, TypeError, ValueError) as exception:
            raise PostSendResponseError(exception) from exception


def send_request(
    context: CodacyContext,
    plan: RequestPlan,
    *,
    query: dict[str, str],
    runtime: RequestRuntime,
) -> ApiResult:
    """Send one Codacy request, retrying only requests proven safe by method."""
    url = build_url(context.base_url, plan.endpoint, query)
    _ = validate_plan_credential_boundaries(context, plan, url)
    validate_request_runtime(runtime)
    headers = {"Accept": JSON_MEDIA_TYPE, "User-Agent": "codacy-management-skill/1"}
    if context.token is not None:
        headers["api-token"] = context.token
    body_bytes = None
    if plan.body is not None:
        headers["Content-Type"] = JSON_MEDIA_TYPE
        body_bytes = strict_json_dumps(plan.body, "Codacy request body").encode("utf-8")

    retries = runtime.retries if retries_are_safe(plan) else 0
    for attempt in range(retries + 1):
        api_request = request.Request(  # noqa: S310  # build_url enforces the configured HTTPS origin and base.
            url,
            data=body_bytes,
            headers=headers,
            method=plan.method,
        )
        try:
            api_opener = request.build_opener(NoRedirectHandler())
            return open_api_result(
                api_opener,
                api_request,
                context=context,
                runtime=runtime,
                url=url,
            )
        except error.HTTPError as exception:
            try:
                if exception.code in RETRYABLE_STATUS_CODES and attempt < retries:
                    time.sleep(retry_delay(exception, attempt, runtime.retry_base_delay))
                    continue
                raise_api_http_error(context, plan, exception)
            finally:
                exception.close()
        except PostSendResponseError as exception:
            if not isinstance(exception.cause, CodacyCliError) and attempt < retries:
                time.sleep(backoff_delay(attempt, runtime.retry_base_delay))
                continue
            raise_post_send_failure(
                plan,
                exception.cause,
                "Unable to read or process the Codacy API response.",
            )
        except (error.URLError, TimeoutError) as exception:
            if attempt < retries:
                time.sleep(backoff_delay(attempt, runtime.retry_base_delay))
                continue
            reason = exception.reason if isinstance(exception, error.URLError) else exception
            guidance = indeterminate_write_guidance(plan)
            separator = " " if guidance else ""
            raise CodacyCliError(
                f"Unable to reach Codacy: {safe_exception_text(reason)}{separator}{guidance}"
            ) from exception
    raise CodacyCliError("Codacy request retry loop ended unexpectedly.")


def json_object(value: JsonValue, label: str) -> dict[str, JsonValue]:
    """Require a JSON object."""
    if not isinstance(value, dict):
        raise CodacyCliError(f"{label} must be a JSON object.")
    return value


def pagination_cursor(payload: dict[str, JsonValue]) -> str | None:
    """Return a strict optional cursor from one Codacy pagination object."""
    if "pagination" not in payload:
        return None
    pagination_value = payload["pagination"]
    if not isinstance(pagination_value, dict):
        raise CodacyCliError("Paginated Codacy response pagination metadata must be a JSON object.")
    if "cursor" not in pagination_value:
        return None
    cursor_value = pagination_value["cursor"]
    if not isinstance(cursor_value, str):
        raise CodacyCliError("Paginated Codacy response cursor must be a string when present.")
    cursor = cursor_value.strip()
    if not cursor or cursor != cursor_value:
        raise CodacyCliError("Paginated Codacy response cursor must be non-empty without surrounding whitespace.")
    return cursor


def process_pagination_page(
    result: ApiResult,
    *,
    current_response_bytes: int,
    max_pages: int,
    page_number: int,
    seen_cursors: set[str],
) -> tuple[int, dict[str, JsonValue], list[JsonValue], str | None]:
    """Validate one page and return its bounded metadata."""
    response_bytes = current_response_bytes + result.response_bytes
    if response_bytes > MAX_PAGINATED_RESPONSE_BYTES:
        raise CodacyCliError(
            f"Codacy pagination exceeds the {MAX_PAGINATED_RESPONSE_BYTES}-byte cumulative safety limit."
        )
    payload = json_object(result.payload, "Paginated Codacy response")
    data = payload.get("data")
    if not isinstance(data, list):
        raise CodacyCliError("Paginated Codacy response must contain a data array.")
    cursor = pagination_cursor(payload)
    if cursor in seen_cursors:
        raise CodacyCliError("Codacy returned a repeated pagination cursor; refusing an infinite loop.")
    if cursor is not None and page_number == max_pages:
        raise CodacyCliError(
            f"Codacy pagination reached --max-pages {max_pages} while a cursor remained; output is incomplete."
        )
    return response_bytes, payload, data, cursor


def paginate_request(
    context: CodacyContext,
    plan: RequestPlan,
    *,
    max_pages: int,
    runtime: RequestRuntime,
) -> ApiResult:
    """Follow Codacy cursor pagination and merge data arrays."""
    _ = validate_max_pages(max_pages)
    query = dict(plan.query)
    all_data: list[JsonValue] = []
    seen_cursors: set[str] = set()
    results: list[ApiResult] = []
    payloads: list[dict[str, JsonValue]] = []
    response_bytes = 0

    for page_number in range(1, max_pages + 1):
        result = send_request(
            context,
            plan,
            query=query,
            runtime=runtime,
        )
        try:
            response_bytes, payload, data, cursor = process_pagination_page(
                result,
                current_response_bytes=response_bytes,
                max_pages=max_pages,
                page_number=page_number,
                seen_cursors=seen_cursors,
            )
            all_data.extend(data)
            results.append(result)
            payloads.append(payload)

            if cursor is None:
                break
            seen_cursors.add(cursor)
            query["cursor"] = cursor
        except CodacyCliError as exception:
            raise_post_send_failure(plan, exception, "Unable to process Codacy pagination metadata.")
        except (HTTPException, OSError, TypeError, ValueError) as exception:
            raise_post_send_failure(plan, exception, "Unable to process Codacy pagination metadata.")

    if not results or not payloads:
        raise CodacyCliError("Codacy pagination returned no pages.")
    first_result = results[0]
    merged = dict(payloads[-1])
    merged["data"] = all_data
    merged["paginationFetch"] = {"fetchedCount": len(all_data), "fetchedPages": len(results)}
    return ApiResult(
        payload=merged,
        status=first_result.status,
        url=first_result.url,
        response_bytes=response_bytes,
    )


def request_plan(arguments: argparse.Namespace, context: CodacyContext) -> RequestPlan:
    """Resolve an endpoint or live OpenAPI operation into a request plan."""
    endpoint = optional_text(arguments.endpoint)
    operation_id = optional_text(arguments.operation_id)
    if operation_id is not None:
        require_active_token_absent(operation_id, context.token, "operation ID")
    requested_method = optional_text(arguments.method)
    method_explicit = requested_method is not None
    method = (requested_method or "GET").upper()
    if endpoint is None and operation_id is None:
        raise CodacyCliError("Provide an endpoint or --operation-id.")
    if endpoint is not None and operation_id is not None:
        raise CodacyCliError("Provide either an endpoint or --operation-id, not both.")

    if operation_id is not None:
        document, _ = load_openapi_document(arguments, context)
        matches = [
            operation for operation in parse_openapi_operations(document) if operation.operation_id == operation_id
        ]
        if len(matches) != 1:
            raise CodacyCliError("OpenAPI operationId must resolve exactly once.")
        operation = matches[0]
        if method_explicit and method != operation.method:
            raise CodacyCliError(f"--method {method} conflicts with OpenAPI operation method {operation.method}.")
        method = operation.method
        endpoint = operation.path

    path_values = parse_pairs(as_string_list(arguments.path_values, "Path values"), "path")
    query = parse_pairs(as_string_list(arguments.query, "Query values"), "query", reject_sensitive=True)
    expanded_endpoint = expand_endpoint(cast("str", endpoint), context, path_values)
    body = load_body(arguments)
    if method == "GET" and body is not None:
        raise CodacyCliError("GET requests must not include a JSON body.")
    plan = RequestPlan(body=body, endpoint=expanded_endpoint, method=method, operation_id=operation_id, query=query)
    _ = validate_plan_credential_boundaries(context, plan)
    return plan


def plan_preview(context: CodacyContext, plan: RequestPlan, *, paginate: bool) -> dict[str, JsonValue]:
    """Build a redacted request preview."""
    url = validate_plan_credential_boundaries(context, plan)
    preview: JsonValue = {
        "body": redact_json(plan.body, context.token),
        "dryRun": True,
        "headers": {
            "Accept": JSON_MEDIA_TYPE,
            "api-token": safe_redaction_placeholder(context.token) if context.token else "<absent>",
        },
        "method": plan.method,
        "operationId": plan.operation_id,
        "paginate": paginate,
        "retrySafety": retry_safety_label(plan),
        "url": redact_url(url, context.token),
    }
    return json_object(redact_json(preview, context.token), "Codacy request preview")


def context_output(context: CodacyContext) -> dict[str, JsonValue]:
    """Build safe local context output."""
    slug: JsonValue = asdict(context.slug) if context.slug is not None else None
    return {
        "baseUrl": redact_output_string(context.base_url, context.token),
        "repositoryRoot": redact_output_string(str(context.repository_root), context.token),
        "slug": redact_json(slug, context.token),
        "token": "configured" if context.token is not None else "absent",
        "tokenEnvironment": (
            redact_output_string(context.token_env_name, context.token) if context.token_env_name is not None else None
        ),
    }


def write_json(value: JsonValue) -> None:
    """Write deterministic JSON."""
    serialized = strict_json_dumps(value, "CLI output", indent=2, sort_keys=True)
    _ = sys.stdout.write(f"{serialized}\n")


def handle_context(arguments: argparse.Namespace) -> int:
    """Print local target and token metadata."""
    context = resolve_context(arguments)
    output = context_output(context)
    if arguments.json:
        write_json(output)
    else:
        lines = [
            f"{key}: {strict_json_dumps(value, 'context output', sort_keys=True)}" for key, value in output.items()
        ]
        _ = sys.stdout.write(f"{'\n'.join(lines)}\n")
    return 0


def handle_operations(arguments: argparse.Namespace) -> int:
    """Search the current Codacy OpenAPI operation catalog."""
    context = resolve_context(arguments)
    document, source = load_openapi_document(arguments, context)
    operations = parse_openapi_operations(document)
    search = optional_text(arguments.search)
    method = optional_text(arguments.filter_method)
    if search is not None:
        needle = search.casefold()
        operations = [
            operation
            for operation in operations
            if needle in f"{operation.operation_id} {operation.path} {operation.summary}".casefold()
        ]
    if method is not None:
        operations = [operation for operation in operations if operation.method == method.upper()]

    safe_source = redact_output_string(source, context.token)
    if arguments.json:
        write_json(
            redact_json(
                {
                    "meta": {
                        "source": safe_source,
                        "untrustedExternalData": arguments.spec_file is None,
                    },
                    "operations": [cast("JsonValue", asdict(operation)) for operation in operations],
                },
                context.token,
            )
        )
    else:
        lines = [f"Codacy operations from {safe_source}: {len(operations)}"]
        for operation in operations:
            operation_id = redact_output_string(operation.operation_id, context.token)
            operation_path = redact_output_string(operation.path, context.token)
            summary = redact_output_string(operation.summary, context.token)
            summary_suffix = f" - {summary}" if summary else ""
            lines.append(f"{operation.method:6} {operation_id:45} {operation_path}{summary_suffix}")
        _ = sys.stdout.write(f"{'\n'.join(lines)}\n")
    return 0


def handle_request(arguments: argparse.Namespace) -> int:
    """Preview or send an origin-locked Codacy v3 request."""
    context = resolve_context(arguments)
    plan = request_plan(arguments, context)
    should_preview = bool(arguments.dry_run) or (plan.method != "GET" and not bool(arguments.send))
    if should_preview:
        write_json(cast("JsonValue", plan_preview(context, plan, paginate=bool(arguments.paginate))))
        return 0

    if context.token is None and not (plan.method == "GET" and bool(arguments.allow_unauthenticated)):
        raise CodacyCliError(
            "No account token found. Set CODACY_API_TOKEN, use --token-env, or explicitly allow a public GET."
        )
    runtime = RequestRuntime(
        retries=int(arguments.retries),
        retry_base_delay=float(arguments.retry_delay),
        timeout=float(arguments.timeout),
    )
    if bool(arguments.paginate):
        result = paginate_request(
            context,
            plan,
            max_pages=int(arguments.max_pages),
            runtime=runtime,
        )
    else:
        result = send_request(
            context,
            plan,
            query=plan.query,
            runtime=runtime,
        )

    try:
        output = redact_json(
            {
                "meta": {
                    "method": plan.method,
                    "operationId": plan.operation_id,
                    "retrySafety": retry_safety_label(plan),
                    "status": result.status,
                    "untrustedExternalData": True,
                    "url": redact_url(result.url, context.token),
                },
                "response": redact_json(result.payload, context.token),
            },
            context.token,
        )
        serialized = strict_json_dumps(output, "CLI output", indent=2, sort_keys=True)
        exit_code = int(not HTTP_SUCCESS_MIN <= result.status < HTTP_SUCCESS_LIMIT)
    except (CodacyCliError, HTTPException, OSError, AttributeError, RecursionError, TypeError, ValueError) as exception:
        raise_post_send_failure(plan, exception, "Unable to redact or serialize the Codacy API response.")

    try:
        if arguments.json:
            _ = sys.stdout.write(f"{serialized}\n")
        else:
            _ = sys.stdout.write(f"[untrusted-codacy-data]\n{serialized}\n")
    except OSError as exception:
        raise_post_send_failure(plan, exception, "Unable to write the Codacy API response output.")
    return exit_code


def common_parser() -> argparse.ArgumentParser:
    """Build options shared by every command."""
    common = argparse.ArgumentParser(add_help=False)
    _ = common.add_argument("--repo", type=resolve_repository, default=resolve_repository("."))
    _ = common.add_argument("--provider", help="Codacy provider code; inferred for GitHub/GitLab/Bitbucket Cloud.")
    _ = common.add_argument("--organization", help="Git provider organization or username.")
    _ = common.add_argument("--repository", help="Repository name.")
    _ = common.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Codacy v3 HTTPS base URL.")
    _ = common.add_argument(
        "--token-env",
        action="append",
        dest="token_envs",
        default=[],
        help="Account-token environment variable name. Repeatable.",
    )
    _ = common.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    return common


def add_spec_options(parser: argparse.ArgumentParser) -> None:
    """Add OpenAPI source options."""
    source = parser.add_mutually_exclusive_group()
    _ = source.add_argument("--spec-file", type=Path, help="Read OpenAPI YAML from a local file.")
    _ = source.add_argument("--spec-url", help="Read OpenAPI YAML from an HTTPS URL.")
    _ = parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help=f"Request timeout in seconds; finite, greater than 0, and at most {MAX_TIMEOUT:g}.",
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    common = common_parser()

    context = subparsers.add_parser("context", parents=[common], help="Show local target and token metadata.")
    context.set_defaults(handler=handle_context)

    operations = subparsers.add_parser(
        "operations", parents=[common], help="Search the live Codacy OpenAPI operation catalog."
    )
    add_spec_options(operations)
    _ = operations.add_argument("--search", help="Case-insensitive operation/path/summary filter.")
    _ = operations.add_argument("--method", dest="filter_method", choices=("GET", "POST", "PUT", "PATCH", "DELETE"))
    operations.set_defaults(handler=handle_operations)

    api_request = subparsers.add_parser(
        "request", parents=[common], help="Preview or send an origin-locked Codacy v3 request."
    )
    add_spec_options(api_request)
    _ = api_request.add_argument("endpoint", nargs="?", help="Relative v3 endpoint or same-base absolute URL.")
    _ = api_request.add_argument("--operation-id", help="Resolve method and path from the OpenAPI document.")
    _ = api_request.add_argument(
        "--method",
        choices=("GET", "POST", "PUT", "PATCH", "DELETE"),
    )
    _ = api_request.add_argument("--path", action="append", dest="path_values", default=[], help="Path name=value.")
    _ = api_request.add_argument(
        "--query",
        action="append",
        default=[],
        help="Query name=value; token-like names refused.",
    )
    body = api_request.add_mutually_exclusive_group()
    _ = body.add_argument("--body-json", help="JSON request body.")
    _ = body.add_argument("--body-file", type=Path, help="Read JSON request body from a file.")
    _ = api_request.add_argument(
        "--paginate",
        action="store_true",
        help="Follow and merge cursor-paginated data arrays.",
    )
    _ = api_request.add_argument(
        "--max-pages",
        type=int,
        default=DEFAULT_MAX_PAGES,
        help=f"Maximum cursor pages, from 1 through {MAX_MAX_PAGES}.",
    )
    _ = api_request.add_argument(
        "--retries",
        type=int,
        default=DEFAULT_RETRIES,
        help=f"Automatic GET retries, from 0 through {MAX_RETRIES}; non-GET requests are never retried.",
    )
    _ = api_request.add_argument(
        "--retry-delay",
        type=float,
        default=1.0,
        help=f"GET retry base delay in seconds, from 0 through {MAX_RETRY_DELAY:g}.",
    )
    _ = api_request.add_argument(
        "--send",
        action="store_true",
        help="Send a non-GET request after reviewing its preview.",
    )
    _ = api_request.add_argument("--dry-run", action="store_true", help="Preview even a GET request.")
    _ = api_request.add_argument(
        "--allow-unauthenticated", action="store_true", help="Allow a tokenless GET for public data."
    )
    api_request.set_defaults(handler=handle_request)
    return parser


def validate_numeric_arguments(arguments: argparse.Namespace) -> None:
    """Validate request-bound numeric options."""
    if hasattr(arguments, "timeout"):
        _ = validate_timeout(float(arguments.timeout))
    if hasattr(arguments, "max_pages"):
        _ = validate_max_pages(int(arguments.max_pages))
    if hasattr(arguments, "retries"):
        _ = validate_retries(int(arguments.retries))
    if hasattr(arguments, "retry_delay"):
        _ = validate_retry_delay(float(arguments.retry_delay))
    if hasattr(arguments, "send") and bool(arguments.send) and bool(arguments.dry_run):
        raise CodacyCliError("--send and --dry-run are mutually exclusive.")


def active_error_tokens(arguments: argparse.Namespace) -> list[str]:
    """Resolve configured tokens defensively for the final stderr sanitization boundary."""
    configured = cast("object", vars(arguments).get("token_envs", []))
    names = (
        [name for name in cast("list[object]", configured) if isinstance(name, str)]
        if isinstance(configured, list)
        else []
    )
    if not names:
        names = list(DEFAULT_TOKEN_ENVS)
    tokens: list[str] = []
    for name in names:
        if ENVIRONMENT_NAME.fullmatch(name) is None:
            continue
        token = os.environ.get(name, "").strip()
        if token and token not in tokens:
            tokens.append(token)
    return tokens


def safe_cli_error_message(exception: BaseException, arguments: argparse.Namespace) -> str:
    """Redact every configured active token from the final CLI error boundary."""
    message = str(exception)
    for token in active_error_tokens(arguments):
        message = fail_safe_redacted_text(message, token)
    return message or "Codacy request failed safely; sensitive details were omitted."


def main() -> int:
    """Run the Codacy helper."""
    parser = build_parser()
    arguments = parser.parse_args()
    try:
        validate_numeric_arguments(arguments)
        handler = cast("Callable[[argparse.Namespace], int]", arguments.handler)
        return handler(arguments)
    except (CodacyCliError, HTTPException, OSError, RecursionError) as exception:
        _ = sys.stderr.write(f"Error: {safe_cli_error_message(exception, arguments)}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
