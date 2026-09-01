#!/usr/bin/env python
# Copyright (c) 2026 Nick2bad4u
"""Inspect WakaTime activity and make privacy-conscious API v1 requests."""

from __future__ import annotations

import argparse
import base64
import json
import math
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import date
from http import client
from pathlib import Path
from typing import TYPE_CHECKING, Never, cast, override
from urllib import error, parse, request

if TYPE_CHECKING:
    from collections.abc import Callable
    from http.client import HTTPMessage
    from typing import IO, Protocol

    class Subparsers(Protocol):
        """Public structural type for argparse subparser collections."""

        def add_parser(
            self,
            name: str,
            *,
            parents: list[argparse.ArgumentParser],
        ) -> argparse.ArgumentParser:
            """Add a parser with inherited common options."""
            ...

    class HeaderLookup(Protocol):
        """Structural header lookup used by urllib response types."""

        def get(self, name: str, failobj: str | None = None) -> str | None:
            """Return one response header when present."""
            ...

    class ReadableResponse(Protocol):
        """Structural response type for bounded urllib reads."""

        @property
        def headers(self) -> HeaderLookup:
            """Return response headers."""
            ...

        def read(self, amount: int = -1, /) -> bytes:
            """Read at most the requested number of bytes."""
            ...


type JsonValue = bool | int | float | str | list[JsonValue] | dict[str, JsonValue] | None

DEFAULT_BASE_URL = "https://api.wakatime.com/api/v1"
DEFAULT_ACCESS_TOKEN_ENV = "WAKATIME_ACCESS_TOKEN"  # noqa: S105  # Environment-variable name, not a credential.
DEFAULT_API_KEY_ENV = "WAKATIME_API_KEY"
DEFAULT_TIMEOUT = 30.0
DEFAULT_RETRIES = 2
API_BASE_PATH = "/api/v1"
MAX_API_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_DECODE_ITERATIONS = 5
MAX_ERROR_RESPONSE_BYTES = 16 * 1024
MAX_RETRIES = 10
MAX_RETRY_DELAY = 60.0
MAX_TIMEOUT = 300.0
MAX_TRANSPORT_RETRY_DELAY = 10.0
MAX_RESPONSE_TEXT = 2000
ASCII_CONTROL_LIMIT = 32
ASCII_DELETE = 127
HTTP_FOUND = 302
HTTP_TOO_MANY_REQUESTS = 429
HTTP_INTERNAL_SERVER_ERROR = 500
HTTP_SERVICE_UNAVAILABLE = 503
HTTP_GATEWAY_TIMEOUT = 504
HTTP_SUCCESS_MIN = 200
HTTP_SUCCESS_LIMIT = 300
RETRYABLE_STATUS_CODES = frozenset(
    {
        HTTP_FOUND,
        HTTP_TOO_MANY_REQUESTS,
        HTTP_INTERNAL_SERVER_ERROR,
        HTTP_SERVICE_UNAVAILABLE,
        HTTP_GATEWAY_TIMEOUT,
    }
)
SAFE_RANGE = re.compile(r"^[A-Za-z0-9_-]+$")
SENSITIVE_NAME_SUFFIXES = frozenset(
    {
        "accesskey",
        "accesstoken",
        "apikey",
        "apitoken",
        "auth",
        "authentication",
        "authorization",
        "bearer",
        "cookie",
        "credential",
        "header",
        "password",
        "passwd",
        "privatekey",
        "refreshtoken",
        "secret",
        "secretkey",
        "securitytoken",
        "session",
        "sessionid",
        "sig",
        "signature",
        "token",
    }
)
DOWNLOAD_URL_KEYS = frozenset(
    {
        "download",
        "downloadhref",
        "downloadlink",
        "downloaduri",
        "downloadurl",
        "exporthref",
        "exportlink",
        "exporturi",
        "exporturl",
    }
)
GENERIC_URL_KEYS = frozenset({"href", "link", "uri", "url"})
COMPLETED_EXPORT_STATES = frozenset({"complete", "completed", "finished", "ready", "succeeded", "success"})
REDACTED_VALUE = "<redacted>"


class WakaTimeCliError(RuntimeError):
    """Report a safe, user-facing helper error."""


class ResponseReadError(WakaTimeCliError):
    """Report a normalized transport failure while reading a response body."""


class StrictJsonNumberError(ValueError):
    """Reject non-standard or non-finite JSON numbers."""


class NoRedirectHandler(request.HTTPRedirectHandler):
    """Reject redirects so credentials never follow a rate-limit redirect."""

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
        """Refuse every redirect and surface the original status."""
        del req, fp, code, msg, headers, newurl
        return None


@dataclass(frozen=True)
class Authentication:
    """Resolved WakaTime authentication without displayable secret data."""

    environment_name: str | None
    scheme: str | None
    secret: str | None


@dataclass(frozen=True)
class WakaTimeContext:
    """Resolved WakaTime API context."""

    authentication: Authentication
    base_url: str


@dataclass(frozen=True)
class RequestPlan:
    """Resolved API request details."""

    body: JsonValue
    method: str
    query: dict[str, str]
    url: str


@dataclass(frozen=True)
class ApiResult:
    """One WakaTime API response."""

    payload: JsonValue
    status: int
    url: str


def optional_text(value: object) -> str | None:
    """Return a stripped optional string."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def validate_environment_name(value: str) -> str:
    """Reject unsafe environment-variable names."""
    if not value.isascii() or not value.isidentifier():
        raise WakaTimeCliError(f"Invalid credential environment variable name: {value}")
    return value


def split_url_safely(value: str, label: str) -> parse.SplitResult:
    """Parse one URL while converting only parser ValueError into a safe CLI error."""
    try:
        return parse.urlsplit(value)
    except ValueError as exception:
        raise WakaTimeCliError(f"{label} is malformed.") from exception


def url_authority(
    parsed: parse.SplitResult,
    label: str,
) -> tuple[str | None, str | None, str | None, int | None]:
    """Extract URL authority properties with narrow normalization-error handling."""
    try:
        return parsed.username, parsed.password, parsed.hostname, parsed.port
    except ValueError as exception:
        raise WakaTimeCliError(f"{label} has a malformed authority.") from exception


def sanitize_base_url(value: str) -> str:
    """Require and normalize WakaTime's exact official API v1 base URL."""
    base_url = value.strip().rstrip("/")
    parsed = split_url_safely(base_url, "WakaTime API base URL")
    if parsed.scheme.lower() != "https" or not parsed.netloc:
        raise WakaTimeCliError("WakaTime API base URL must be an absolute HTTPS URL.")
    username, password, hostname, port = url_authority(parsed, "WakaTime API base URL")
    if username is not None or password is not None:
        raise WakaTimeCliError("WakaTime API base URL must not contain credentials.")
    if "?" in base_url or "#" in base_url:
        raise WakaTimeCliError("WakaTime API base URL must not contain a query or fragment.")
    if hostname != "api.wakatime.com" or port is not None or parsed.path.rstrip("/") != API_BASE_PATH:
        raise WakaTimeCliError(f"WakaTime API base URL must be exactly {DEFAULT_BASE_URL}.")
    return DEFAULT_BASE_URL


def resolve_authentication(arguments: argparse.Namespace) -> Authentication:
    """Resolve OAuth first, then an account API key."""
    access_name = validate_environment_name(str(arguments.access_token_env))
    key_name = validate_environment_name(str(arguments.api_key_env))
    access_token = os.environ.get(access_name, "").strip()
    api_key = os.environ.get(key_name, "").strip()
    if access_token:
        return Authentication(environment_name=access_name, scheme="oauth", secret=access_token)
    if api_key:
        return Authentication(environment_name=key_name, scheme="api-key", secret=api_key)
    return Authentication(environment_name=None, scheme=None, secret=None)


def resolve_context(arguments: argparse.Namespace) -> WakaTimeContext:
    """Resolve API base and authentication."""
    base_url = sanitize_base_url(str(arguments.base_url))
    return WakaTimeContext(
        authentication=resolve_authentication(arguments),
        base_url=base_url,
    )


def parse_date(value: str) -> date:
    """Parse an ISO calendar date for API commands."""
    try:
        return date.fromisoformat(value)
    except ValueError as exception:
        raise argparse.ArgumentTypeError("Date must use YYYY-MM-DD format.") from exception


def reject_nonfinite_json_constant(value: str) -> Never:
    """Reject JavaScript-style non-finite constants accepted by Python's decoder."""
    del value
    raise StrictJsonNumberError


def validate_finite_json(value: JsonValue) -> None:
    """Recursively require every JSON floating-point number to be finite."""
    if isinstance(value, float) and not math.isfinite(value):
        raise StrictJsonNumberError
    if isinstance(value, list):
        for item in value:
            validate_finite_json(item)
    elif isinstance(value, dict):
        for item in value.values():
            validate_finite_json(item)


def decode_json_strict(value: str, error_message: str) -> JsonValue:
    """Decode standards-compliant JSON and reject finite-syntax overflow."""
    try:
        decoded = cast(
            "JsonValue",
            json.loads(value, parse_constant=reject_nonfinite_json_constant),
        )
        validate_finite_json(decoded)
    except (ValueError, RecursionError) as exception:
        raise WakaTimeCliError(error_message) from exception
    return decoded


def encode_json_strict(value: JsonValue, error_message: str, *, pretty: bool) -> str:
    """Validate and atomically encode strict JSON with non-finite values disabled."""
    try:
        validate_finite_json(value)
        if pretty:
            return json.dumps(
                value,
                allow_nan=False,
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
            )
        return json.dumps(
            value,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError, OverflowError, RecursionError) as exception:
        raise WakaTimeCliError(error_message) from exception


def normalized_key(value: str) -> str:
    """Normalize a field name across casing, separators, and punctuation."""
    return "".join(character for character in value.casefold() if character.isalnum())


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


def is_sensitive_query_name(value: str) -> bool:
    """Classify credential-bearing names across encoding, casing, separators, and plurals."""
    variants, stable = decoded_text_variants(value)
    if not stable:
        return True
    for candidate in variants:
        normalized = normalized_key(candidate)
        forms = {normalized, normalized.removesuffix("s")}
        if any(form.endswith(suffix) for form in forms for suffix in SENSITIVE_NAME_SUFFIXES):
            return True
    return False


def secret_variants(secret: str | None) -> tuple[str, ...]:
    """Return raw and encoded forms of an active credential for detection/redaction."""
    if not secret:
        return ()
    basic = base64.b64encode(secret.encode()).decode("ascii")
    values = {
        secret,
        basic,
        f"Bearer {secret}",
        f"Basic {basic}",
        parse.quote(secret, safe=""),
        parse.quote_plus(secret, safe=""),
        parse.quote(f"Bearer {secret}", safe=""),
        parse.quote_plus(f"Bearer {secret}", safe=""),
        parse.quote(f"Basic {basic}", safe=""),
        parse.quote_plus(f"Basic {basic}", safe=""),
    }
    return tuple(sorted(values, key=len, reverse=True))


def contains_secret(value: str, secret: str | None) -> bool:
    """Return whether text contains the active credential in a raw or encoded form."""
    if not secret:
        return False
    variants = secret_variants(secret)
    decoded_values, stable = decoded_text_variants(value)
    return not stable or any(variant in decoded for decoded in decoded_values for variant in variants)


def redact_text(value: str, secret: str | None) -> str:
    """Redact raw and encoded active-credential variants from text."""
    if not secret:
        return value
    redacted = value
    for variant in secret_variants(secret):
        redacted = redacted.replace(variant, REDACTED_VALUE)
    return REDACTED_VALUE if contains_secret(redacted, secret) else redacted


def validate_query_credentials(query: dict[str, str], authentication: Authentication) -> None:
    """Reject sensitive query names and active credentials in names or values."""
    for name, value in query.items():
        if contains_secret(name, authentication.secret) or contains_secret(value, authentication.secret):
            raise WakaTimeCliError("Refusing a query parameter that contains the loaded WakaTime credential.")
        if is_sensitive_query_name(name):
            raise WakaTimeCliError("Refusing a sensitive query parameter name.")


def parse_pairs(values: list[str], authentication: Authentication | None = None) -> dict[str, str]:
    """Parse repeatable name=value query options without secret-like names or values."""
    result: dict[str, str] = {}
    for value in values:
        name, separator, item_value = value.partition("=")
        name = name.strip()
        if not separator or not name or not item_value:
            raise WakaTimeCliError("Query values must use non-empty name=value syntax.")
        if authentication is not None and (
            contains_secret(name, authentication.secret) or contains_secret(item_value, authentication.secret)
        ):
            raise WakaTimeCliError("Refusing a query parameter that contains the loaded WakaTime credential.")
        if is_sensitive_query_name(name):
            raise WakaTimeCliError("Refusing a sensitive query parameter name.")
        if name in result:
            raise WakaTimeCliError(f"Duplicate query name: {name}")
        result[name] = item_value
    if authentication is not None:
        validate_query_credentials(result, authentication)
    return result


def load_body(arguments: argparse.Namespace) -> JsonValue:
    """Load an optional JSON body from text or a file."""
    body_text = optional_text(arguments.body_json)
    body_file = cast("Path | None", arguments.body_file)
    if body_file is not None:
        try:
            body_text = body_file.read_text(encoding="utf-8")
        except OSError as exception:
            raise WakaTimeCliError(f"Could not read request body file: {body_file}") from exception
    if body_text is None:
        return None
    return decode_json_strict(
        body_text,
        "Request body must be valid strict JSON with finite numbers.",
    )


def validate_decoded_path_layer(path: str, label: str) -> None:
    """Reject path structures that can alter routing or traverse directories."""
    if "\\" in path or "?" in path or "#" in path:
        raise WakaTimeCliError(f"{label} contains an encoded path separator or delimiter.")
    if any(ord(character) < ASCII_CONTROL_LIMIT or ord(character) == ASCII_DELETE for character in path):
        raise WakaTimeCliError(f"{label} contains a control character.")
    if any(segment in {".", ".."} for segment in path.split("/")):
        raise WakaTimeCliError(f"{label} contains a traversal path segment.")


def decode_path_strict(path: str, label: str) -> str:
    """Repeatedly decode a path under a bounded traversal-safe contract."""
    current = path
    for _iteration in range(MAX_DECODE_ITERATIONS):
        validate_decoded_path_layer(current, label)
        try:
            decoded = parse.unquote(current, errors="strict")
        except UnicodeError as exception:
            raise WakaTimeCliError(f"{label} contains invalid percent-encoded UTF-8.") from exception
        if decoded == current:
            if "%" in current:
                raise WakaTimeCliError(f"{label} contains a residual percent escape.")
            return current
        if decoded.count("/") != current.count("/") or "\\" in decoded:
            raise WakaTimeCliError(f"{label} contains an encoded path separator.")
        current = decoded
    raise WakaTimeCliError(f"{label} exceeds the {MAX_DECODE_ITERATIONS}-pass decoding safety limit.")


def validated_endpoint_url(base_url: str, endpoint: str) -> str:
    """Resolve a relative endpoint and lock it to the configured API base."""
    parsed_input = split_url_safely(endpoint, "Endpoint URL")
    if "?" in endpoint or "#" in endpoint:
        raise WakaTimeCliError("Endpoint must not contain query or fragment; use --query.")
    _ = decode_path_strict(parsed_input.path, "Endpoint path")
    if endpoint.startswith("/"):
        candidate = f"{base_url}{endpoint}"
    elif parsed_input.scheme:
        candidate = endpoint
    else:
        raise WakaTimeCliError("Relative endpoint must start with /.")
    base = split_url_safely(base_url, "WakaTime API base URL")
    parsed = split_url_safely(candidate, "Endpoint URL")
    if parsed.scheme.lower() != "https" or not parsed.netloc:
        raise WakaTimeCliError("Endpoint must resolve to an absolute HTTPS URL.")
    base_username, base_password, _base_hostname, _base_port = url_authority(base, "WakaTime API base URL")
    username, password, _hostname, _port = url_authority(parsed, "Endpoint URL")
    if base_username is not None or base_password is not None:
        raise WakaTimeCliError("WakaTime API base URL must not contain credentials.")
    if username is not None or password is not None:
        raise WakaTimeCliError("Endpoint must not contain URL credentials.")
    if (parsed.scheme.lower(), parsed.netloc.lower()) != (base.scheme.lower(), base.netloc.lower()):
        raise WakaTimeCliError("Absolute endpoint origin must match the configured WakaTime API origin.")
    base_path = base.path.rstrip("/")
    decoded_path = decode_path_strict(parsed.path, "Endpoint path")
    if decoded_path != base_path and not decoded_path.startswith(f"{base_path}/"):
        raise WakaTimeCliError("Absolute endpoint must remain under the configured /api/v1 base path.")
    return candidate


def request_plan(
    arguments: argparse.Namespace,
    context: WakaTimeContext,
    *,
    endpoint: str | None = None,
    query: dict[str, str] | None = None,
) -> RequestPlan:
    """Build a raw or wrapped request plan."""
    resolved_endpoint = endpoint or optional_text(arguments.endpoint)
    if resolved_endpoint is None:
        raise WakaTimeCliError("An API endpoint is required.")
    method = (optional_text(arguments.method) or "GET").upper()
    body = load_body(arguments)
    if method == "GET" and body is not None:
        raise WakaTimeCliError("GET requests must not include a body.")
    explicit_query = parse_pairs(cast("list[str]", arguments.query), context.authentication)
    merged_query = dict(query or {})
    for name, value in explicit_query.items():
        if name in merged_query:
            raise WakaTimeCliError(f"Duplicate wrapped and explicit query name: {name}")
        merged_query[name] = value
    validate_query_credentials(merged_query, context.authentication)
    return RequestPlan(
        body=body,
        method=method,
        query=merged_query,
        url=validated_endpoint_url(context.base_url, resolved_endpoint),
    )


def is_bearer_like_url(value: str) -> bool:
    """Return whether an absolute URL contains bearer-like query material."""
    try:
        parsed = parse.urlsplit(value)
    except ValueError:
        return value.casefold().startswith(("http://", "https://"))
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc or not parsed.query:
        return False
    return any(is_sensitive_query_name(name) for name, _ in parse.parse_qsl(parsed.query, keep_blank_values=True))


def mapping_has_completed_state(value: dict[str, JsonValue]) -> bool:
    """Return whether a response object reports a completed export-like state."""
    for key, item in value.items():
        if normalized_key(key) in {"state", "status"} and isinstance(item, str):
            return item.strip().casefold() in COMPLETED_EXPORT_STATES
    return False


def redact_json(value: JsonValue, secret: str | None) -> JsonValue:
    """Redact sensitive keys, export URLs, and active credential occurrences."""
    if isinstance(value, dict):
        completed = mapping_has_completed_state(value)
        result: dict[str, JsonValue] = {}
        for index, (key, item) in enumerate(value.items(), start=1):
            safe_key = f"redacted-response-key-{index}" if contains_secret(key, secret) else key
            if (
                is_sensitive_query_name(key)
                or normalized_key(key) in DOWNLOAD_URL_KEYS
                or (completed and normalized_key(key) in GENERIC_URL_KEYS and isinstance(item, str))
            ):
                result[safe_key] = REDACTED_VALUE
            else:
                result[safe_key] = redact_json(item, secret)
        return result
    if isinstance(value, list):
        return [redact_json(item, secret) for item in value]
    if isinstance(value, str):
        if is_bearer_like_url(value):
            return REDACTED_VALUE
        return redact_text(value, secret)
    return value


def redact_query(query: dict[str, str], secret: str | None) -> dict[str, str]:
    """Redact sensitive query names and values for defense-in-depth output."""
    result: dict[str, str] = {}
    for index, (name, value) in enumerate(query.items(), start=1):
        name_contains_secret = contains_secret(name, secret)
        safe_name = f"redacted-query-name-{index}" if name_contains_secret else name
        safe_value = redact_text(value, secret)
        if (
            is_sensitive_query_name(name)
            or name_contains_secret
            or contains_secret(value, secret)
            or is_bearer_like_url(value)
        ):
            safe_value = REDACTED_VALUE
        result[safe_name] = safe_value
    return result


def redact_url(url: str, secret: str | None) -> str:
    """Redact credential-bearing URL components before display."""
    parsed = split_url_safely(redact_text(url, secret), "WakaTime response URL")
    pairs = parse.parse_qsl(parsed.query, keep_blank_values=True)
    safe_pairs: list[tuple[str, str]] = []
    for index, (name, value) in enumerate(pairs, start=1):
        name_contains_secret = contains_secret(name, secret)
        safe_name = f"redacted-query-name-{index}" if name_contains_secret else name
        safe_value = (
            REDACTED_VALUE
            if (
                is_sensitive_query_name(name)
                or name_contains_secret
                or contains_secret(value, secret)
                or is_bearer_like_url(value)
            )
            else redact_text(value, secret)
        )
        safe_pairs.append((safe_name, safe_value))
    return parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parse.urlencode(safe_pairs), ""))


def encode_url(url: str, query: dict[str, str]) -> str:
    """Append encoded query parameters to a validated URL."""
    parsed = split_url_safely(url, "WakaTime request URL")
    return parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parse.urlencode(query), ""))


def authentication_header(authentication: Authentication) -> str | None:
    """Build the documented Authorization value."""
    if authentication.secret is None:
        return None
    if authentication.scheme == "oauth":
        return f"Bearer {authentication.secret}"
    encoded = base64.b64encode(authentication.secret.encode()).decode("ascii")
    return f"Basic {encoded}"


def response_payload(data: bytes, content_type: str) -> JsonValue:
    """Decode JSON or retain a bounded external text response."""
    if "json" in content_type.lower():
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as exception:
            raise WakaTimeCliError("WakaTime returned malformed JSON.") from exception
        return decode_json_strict(
            text,
            "WakaTime returned malformed JSON or a non-finite JSON number.",
        )
    return data.decode("utf-8", errors="replace")[:MAX_RESPONSE_TEXT]


def read_bounded_response(
    response: ReadableResponse,
    *,
    max_bytes: int,
    label: str,
    secret: str | None,
) -> bytes:
    """Enforce declared and actual response sizes using a limit-plus-one read."""
    declared_length = response.headers.get("Content-Length")
    if declared_length is not None:
        try:
            parsed_length = int(declared_length)
        except ValueError:
            parsed_length = None
        if parsed_length is not None and parsed_length > max_bytes:
            raise WakaTimeCliError(f"{label} exceeds the {max_bytes}-byte safety limit.")
    try:
        raw = response.read(max_bytes + 1)
    except (OSError, client.HTTPException) as exception:
        safe_reason = redact_text(str(exception), secret).strip()[:MAX_RESPONSE_TEXT]
        detail = f": {safe_reason}" if safe_reason else ""
        raise ResponseReadError(f"{label} could not be read safely{detail}.") from exception
    if len(raw) > max_bytes:
        raise WakaTimeCliError(f"{label} exceeds the {max_bytes}-byte safety limit.")
    return raw


def capped_exponential_delay(attempt: int, cap: float) -> float:
    """Return an overflow-safe exponential delay bounded by a positive cap."""
    normalized_attempt = max(attempt, 0)
    if normalized_attempt >= math.ceil(math.log2(cap)):
        return cap
    return min(math.ldexp(1.0, normalized_attempt), cap)


def retry_delay(http_error: error.HTTPError, attempt: int) -> float:
    """Return a finite bounded Retry-After or overflow-safe exponential fallback."""
    fallback = capped_exponential_delay(attempt, MAX_RETRY_DELAY)
    value = (http_error.headers.get("Retry-After") or "").strip()
    if not value:
        return fallback
    try:
        delay = float(value)
    except ValueError:
        return fallback
    return min(delay, MAX_RETRY_DELAY) if math.isfinite(delay) and delay >= 0 else fallback


def validate_runtime_controls(timeout: float, retries: int) -> tuple[float, int]:
    """Validate finite timeout and bounded retry controls."""
    if not math.isfinite(timeout) or timeout <= 0 or timeout > MAX_TIMEOUT:
        raise WakaTimeCliError(f"--timeout must be finite, greater than zero, and at most {MAX_TIMEOUT:g} seconds.")
    if retries < 0 or retries > MAX_RETRIES:
        raise WakaTimeCliError(f"--retries must be between zero and {MAX_RETRIES}.")
    return timeout, retries


def indeterminate_write_guidance(plan: RequestPlan) -> str:
    """Explain safe recovery after an ambiguous non-GET failure."""
    if plan.method == "GET":
        return ""
    return " ".join(
        (
            f"The {plan.method} request was attempted once and was not automatically retried because its outcome",
            "may be indeterminate. Verify current WakaTime state before retrying manually.",
        )
    )


def error_response_details(http_error: error.HTTPError, secret: str | None) -> tuple[str, bool]:
    """Return safe bounded error details and whether body reading failed."""
    try:
        raw = read_bounded_response(
            cast("ReadableResponse", http_error),
            max_bytes=MAX_ERROR_RESPONSE_BYTES,
            label="WakaTime API error response",
            secret=secret,
        )
    except ResponseReadError as exception:
        return str(exception), True
    except WakaTimeCliError as exception:
        return str(exception), False
    except OSError:
        return "error response body unavailable", True
    if not raw:
        return "no error response body", False
    try:
        payload = decode_json_strict(
            raw.decode("utf-8"),
            "WakaTime API error response is not strict JSON.",
        )
        safe_payload = redact_json(payload, secret)
        return (
            encode_json_strict(
                safe_payload,
                "WakaTime API error response could not be encoded as strict JSON.",
                pretty=False,
            ),
            False,
        )
    except UnicodeError, WakaTimeCliError:
        return "malformed, undecodable, or non-finite error response body omitted", False


def send_request(context: WakaTimeContext, plan: RequestPlan, arguments: argparse.Namespace) -> ApiResult:
    """Send one WakaTime request without following redirects."""
    canonical_base = sanitize_base_url(context.base_url)
    validated_url = validated_endpoint_url(canonical_base, plan.url)
    validate_query_credentials(plan.query, context.authentication)
    timeout, configured_retries = validate_runtime_controls(float(arguments.timeout), int(arguments.retries))
    url = encode_url(validated_url, plan.query)
    headers = {"Accept": "application/json", "User-Agent": "codex-wakatime-management/1"}
    authorization = authentication_header(context.authentication)
    if authorization is not None:
        headers["Authorization"] = authorization
    body = (
        None
        if plan.body is None
        else encode_json_strict(
            plan.body,
            "Request body could not be encoded as strict JSON with finite numbers.",
            pretty=False,
        ).encode()
    )
    if body is not None:
        headers["Content-Type"] = "application/json"
    opener = request.build_opener(NoRedirectHandler())
    retries = configured_retries if plan.method == "GET" else 0
    for attempt in range(retries + 1):
        api_request = request.Request(  # noqa: S310  # request_plan origin-locks the URL.
            url,
            data=body,
            headers=headers,
            method=plan.method,
        )
        try:
            with opener.open(api_request, timeout=timeout) as response:  # URL is origin locked.
                raw = read_bounded_response(
                    response,
                    max_bytes=MAX_API_RESPONSE_BYTES,
                    label="WakaTime API response",
                    secret=context.authentication.secret,
                )
                return ApiResult(
                    payload=response_payload(raw, response.headers.get("Content-Type", "")),
                    status=int(response.status),
                    url=url,
                )
        except error.HTTPError as exception:
            try:
                if exception.code in RETRYABLE_STATUS_CODES and attempt < retries:
                    time.sleep(retry_delay(exception, attempt))
                    continue
                details, response_read_failed = error_response_details(exception, context.authentication.secret)
                guidance = (
                    indeterminate_write_guidance(plan)
                    if exception.code in RETRYABLE_STATUS_CODES or response_read_failed
                    else ""
                )
                separator = " " if guidance else ""
                raise WakaTimeCliError(
                    f"WakaTime API returned HTTP {exception.code}: {details}{separator}{guidance}"
                ) from exception
            finally:
                exception.close()
        except ResponseReadError as exception:
            if attempt < retries:
                time.sleep(capped_exponential_delay(attempt, MAX_TRANSPORT_RETRY_DELAY))
                continue
            guidance = indeterminate_write_guidance(plan)
            separator = " " if guidance else ""
            raise WakaTimeCliError(f"{exception}{separator}{guidance}") from exception
        except (error.URLError, TimeoutError) as exception:
            if attempt < retries:
                time.sleep(capped_exponential_delay(attempt, MAX_TRANSPORT_RETRY_DELAY))
                continue
            reason = exception.reason if isinstance(exception, error.URLError) else exception
            safe_reason = redact_text(str(reason), context.authentication.secret)[:MAX_RESPONSE_TEXT]
            guidance = indeterminate_write_guidance(plan)
            separator = " " if guidance else ""
            raise WakaTimeCliError(f"WakaTime API request failed: {safe_reason}.{separator}{guidance}") from exception
    raise WakaTimeCliError("WakaTime API retry loop ended unexpectedly.")


def write_json(value: JsonValue, *, prefix: str = "") -> None:
    """Atomically encode and write deterministic strict JSON output."""
    serialized = encode_json_strict(
        value,
        "WakaTime output could not be encoded as strict JSON with finite numbers.",
        pretty=True,
    )
    _ = sys.stdout.write(f"{prefix}{serialized}\n")


def execute_plan(arguments: argparse.Namespace, context: WakaTimeContext, plan: RequestPlan) -> int:
    """Preview a write or execute a read/reviewed write."""
    validate_query_credentials(plan.query, context.authentication)
    preview = bool(arguments.dry_run) or (plan.method != "GET" and not bool(arguments.send))
    if preview:
        write_json(
            {
                "body": redact_json(plan.body, context.authentication.secret),
                "dryRun": True,
                "method": plan.method,
                "query": cast("JsonValue", redact_query(plan.query, context.authentication.secret)),
                "url": redact_url(encode_url(plan.url, plan.query), context.authentication.secret),
            }
        )
        return 0
    if context.authentication.secret is None and not bool(arguments.allow_unauthenticated):
        raise WakaTimeCliError("No credential found. Set WAKATIME_ACCESS_TOKEN or WAKATIME_API_KEY.")
    result = send_request(context, plan, arguments)
    output: JsonValue = {
        "meta": {
            "authentication": context.authentication.scheme or "none",
            "status": result.status,
            "untrustedExternalData": True,
            "url": redact_url(result.url, context.authentication.secret),
        },
        "response": redact_json(result.payload, context.authentication.secret),
    }
    prefix = "" if bool(arguments.json) else "[untrusted-wakatime-data]\n"
    write_json(output, prefix=prefix)
    return 0 if HTTP_SUCCESS_MIN <= result.status < HTTP_SUCCESS_LIMIT else 1


def handle_context(arguments: argparse.Namespace) -> int:
    """Print safe authentication context."""
    context = resolve_context(arguments)
    write_json(
        {
            "authentication": context.authentication.scheme or "missing",
            "baseUrl": context.base_url,
            "credentialEnvironment": context.authentication.environment_name,
        }
    )
    return 0


def summaries_target(arguments: argparse.Namespace) -> tuple[str, dict[str, str]]:
    """Build the summaries endpoint and query."""
    start = cast("date", arguments.start)
    end = cast("date", arguments.end)
    if end < start:
        raise WakaTimeCliError("--end must not be earlier than --start.")
    query = {"start": start.isoformat(), "end": end.isoformat()}
    for name in ("project", "branches"):
        value = optional_text(getattr(arguments, name))
        if value:
            query[name] = value
    return "/users/current/summaries", query


def stats_target(arguments: argparse.Namespace) -> tuple[str, dict[str, str]]:
    """Build the stats endpoint."""
    range_value = str(arguments.range)
    if SAFE_RANGE.fullmatch(range_value) is None:
        raise WakaTimeCliError("Stats range contains unsupported characters.")
    return f"/users/current/stats/{parse.quote(range_value, safe='')}", {}


def projects_target(arguments: argparse.Namespace) -> tuple[str, dict[str, str]]:
    """Build the projects endpoint and optional search."""
    query: dict[str, str] = {}
    value = optional_text(arguments.project_query)
    if value:
        query["q"] = value
    return "/users/current/projects", query


def dated_target(arguments: argparse.Namespace) -> tuple[str, dict[str, str]]:
    """Build the durations or heartbeats endpoint."""
    command = str(arguments.command)
    query = {"date": cast("date", arguments.date).isoformat()}
    if command == "durations":
        for name in ("project", "branches"):
            value = optional_text(getattr(arguments, name))
            if value:
                query[name] = value
    return f"/users/current/{command}", query


def wrapped_target(arguments: argparse.Namespace) -> tuple[str, dict[str, str]]:
    """Resolve one fixed read endpoint."""
    command = str(arguments.command)
    if command == "summaries":
        return summaries_target(arguments)
    if command == "stats":
        return stats_target(arguments)
    if command == "projects":
        return projects_target(arguments)
    if command in {"durations", "heartbeats"}:
        return dated_target(arguments)
    fixed = {
        "data-dumps": "/users/current/data_dumps",
        "goals": "/users/current/goals",
        "user": "/users/current",
    }
    return fixed[command], {}


def handle_wrapped(arguments: argparse.Namespace) -> int:
    """Execute a fixed read-only resource command."""
    context = resolve_context(arguments)
    endpoint, query = wrapped_target(arguments)
    plan = request_plan(arguments, context, endpoint=endpoint, query=query)
    return execute_plan(arguments, context, plan)


def handle_request(arguments: argparse.Namespace) -> int:
    """Execute the constrained raw request command."""
    context = resolve_context(arguments)
    return execute_plan(arguments, context, request_plan(arguments, context))


def common_parser() -> argparse.ArgumentParser:
    """Build common API options."""
    parser = argparse.ArgumentParser(add_help=False)
    _ = parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    _ = parser.add_argument("--access-token-env", default=DEFAULT_ACCESS_TOKEN_ENV)
    _ = parser.add_argument("--api-key-env", default=DEFAULT_API_KEY_ENV)
    _ = parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    _ = parser.add_argument("--retries", type=int, default=DEFAULT_RETRIES)
    _ = parser.add_argument("--json", action="store_true")
    return parser


def add_execution_options(parser: argparse.ArgumentParser) -> None:
    """Add options used by fixed and raw requests."""
    _ = parser.add_argument("--query", action="append", default=[])
    body = parser.add_mutually_exclusive_group()
    _ = body.add_argument("--body-json")
    _ = body.add_argument("--body-file", type=Path)
    _ = parser.add_argument("--method", choices=("GET", "POST", "PUT", "PATCH", "DELETE"), default="GET")
    _ = parser.add_argument("--send", action="store_true")
    _ = parser.add_argument("--dry-run", action="store_true")
    _ = parser.add_argument("--allow-unauthenticated", action="store_true")


def add_wrapped_parser(subparsers: Subparsers, common: argparse.ArgumentParser, name: str) -> argparse.ArgumentParser:
    """Create one wrapped read command parser."""
    parser = subparsers.add_parser(name, parents=[common])
    add_execution_options(parser)
    parser.set_defaults(handler=handle_wrapped, endpoint=None)
    return parser


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    common = common_parser()

    context = subparsers.add_parser("context", parents=[common])
    context.set_defaults(handler=handle_context)

    user = add_wrapped_parser(subparsers, common, "user")
    user.set_defaults(endpoint=None)

    summaries = add_wrapped_parser(subparsers, common, "summaries")
    _ = summaries.add_argument("--start", type=parse_date, required=True)
    _ = summaries.add_argument("--end", type=parse_date, required=True)
    _ = summaries.add_argument("--project")
    _ = summaries.add_argument("--branches")

    stats = add_wrapped_parser(subparsers, common, "stats")
    _ = stats.add_argument("--range", required=True)

    projects = add_wrapped_parser(subparsers, common, "projects")
    _ = projects.add_argument("--search", dest="project_query")

    _ = add_wrapped_parser(subparsers, common, "goals")

    durations = add_wrapped_parser(subparsers, common, "durations")
    _ = durations.add_argument("--date", type=parse_date, required=True)
    _ = durations.add_argument("--project")
    _ = durations.add_argument("--branches")

    heartbeats = add_wrapped_parser(subparsers, common, "heartbeats")
    _ = heartbeats.add_argument("--date", type=parse_date, required=True)

    _ = add_wrapped_parser(subparsers, common, "data-dumps")

    raw_request = subparsers.add_parser("request", parents=[common])
    _ = raw_request.add_argument("endpoint")
    add_execution_options(raw_request)
    raw_request.set_defaults(handler=handle_request)
    return parser


def validate_arguments(arguments: argparse.Namespace) -> None:
    """Validate runtime options."""
    _ = validate_runtime_controls(float(arguments.timeout), int(arguments.retries))
    if hasattr(arguments, "send") and bool(arguments.send) and bool(arguments.dry_run):
        raise WakaTimeCliError("--send and --dry-run are mutually exclusive.")


def main() -> int:
    """Run the WakaTime management helper."""
    parser = build_parser()
    arguments = parser.parse_args()
    try:
        validate_arguments(arguments)
        handler = cast("Callable[[argparse.Namespace], int]", arguments.handler)
        return handler(arguments)
    except (WakaTimeCliError, OSError) as exception:
        _ = sys.stderr.write(f"Error: {exception}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
