#!/usr/bin/env python
# Copyright (c) 2026 Nick2bad4u
"""Inspect Snyk REST OpenAPI operations and make constrained requests."""

from __future__ import annotations

import argparse
import base64
import json
import math
import os
import re
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
    from typing import IO, Never

type JsonValue = bool | int | float | str | list[JsonValue] | dict[str, JsonValue] | None

DEFAULT_BASE_URL = "https://api.snyk.io/rest"
DEFAULT_API_VERSION = "2024-10-15"
DEFAULT_TOKEN_ENVS = ("SNYK_TOKEN", "SNYK_API_TOKEN")
DEFAULT_TIMEOUT = 30.0
DEFAULT_RETRIES = 2
DEFAULT_MAX_PAGES = 100
MAX_LOCAL_SPEC_BYTES = 16 * 1024 * 1024
MAX_REMOTE_SPEC_BYTES = 16 * 1024 * 1024
MAX_VERSION_RESPONSE_BYTES = 1 * 1024 * 1024
MAX_API_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_ERROR_RESPONSE_BYTES = 16 * 1024
MAX_PAGINATED_RESPONSE_BYTES = 32 * 1024 * 1024
MAX_UNTRUSTED_REASON_TEXT = 1000
MAX_RETRIES = 10
MAX_PAGES = 1000
MAX_RETRY_DELAY_SECONDS = 60.0
MAX_ASCII_CONTROL_CODEPOINT = 31
ASCII_DELETE_CODEPOINT = 127
MIN_SCHEME_CREDENTIAL_CHARACTERS = 8
SCHEME_CREDENTIAL_PARTS = 2
WEBHOOK_FIELD_TOKEN_COUNT = 2
REDACTED_TEXT = "<redacted>"
OFFICIAL_REST_BASE_URLS = frozenset(
    {
        "https://api.au.snyk.io/rest",
        "https://api.eu.snyk.io/rest",
        "https://api.snyk.io/rest",
        "https://api.us.snyk.io/rest",
    }
)
MAX_RESPONSE_TEXT = 2000
HTTP_REQUEST_TIMEOUT = 408
HTTP_TOO_MANY_REQUESTS = 429
HTTP_INTERNAL_SERVER_ERROR = 500
HTTP_BAD_GATEWAY = 502
HTTP_SERVICE_UNAVAILABLE = 503
HTTP_GATEWAY_TIMEOUT = 504
HTTP_NO_CONTENT = 204
HTTP_SERVER_ERROR_MIN = 500
HTTP_SERVER_ERROR_LIMIT = 600
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
API_VERSION = re.compile(r"^\d{4}-\d{2}-\d{2}(?:~(?:beta|experimental))?$")
PATH_PARAMETER = re.compile(r"\{([^{}]+)\}")
SENSITIVE_NOUNS = frozenset(
    {"authorization", "cookie", "credential", "password", "secret", "session", "token", "webhook"}
)
SENSITIVE_KEY_QUALIFIERS = frozenset({"access", "api", "integration", "provider", "secret", "sentinel"})
SINGULAR_KEY_TOKENS = {
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
KNOWN_SENSITIVE_COMPOUNDS = frozenset(
    {
        "accesskey",
        "accesstoken",
        "apikey",
        "apitoken",
        "integrationkey",
        "providercookie",
        "providercredential",
        "providerkey",
        "providerpassword",
        "providersecret",
        "providersession",
        "providertoken",
        "secretkey",
        "sentinelkey",
        "sessionid",
        "webhookurl",
    }
)
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
AUTHORIZATION_PREFIX_PATTERN = r"(?i)\bauthorization\s*[:=]\s*(?:(?:bearer|token|basic)\s+)?"
AUTHORIZATION_ASSIGNMENTS = tuple(
    re.compile(AUTHORIZATION_PREFIX_PATTERN + value_pattern)
    for value_pattern in (r'"[^"]++"', r"'[^']++'", r"[^\s,;]++")
)
SCHEME_CREDENTIAL = re.compile(r"(?i)\b(?P<scheme>bearer|token|basic)\s+(?P<credential>\"[^\"]+\"|'[^']+'|[^\s,;]+)")
URL_USERINFO = re.compile(r"(?i)(https?://)[^/@\s]+@")
ASSIGNMENT_PREFIX_PATTERN = r"(?P<prefix>^|[?&;\s,{])"
ASSIGNMENT_NAME_PATTERN = r"(?P<name>[a-z0-9_.%~-]+)"
ASSIGNMENT_OPERATOR_PATTERN = r"(?P<operator>\s*[:=]\s*)"
QUERY_CREDENTIAL_ASSIGNMENT = re.compile(
    r"(?P<prefix>[?&])" + ASSIGNMENT_NAME_PATTERN + ASSIGNMENT_OPERATOR_PATTERN + r"(?P<value>[^&#;\s,}\]]+)",
    re.IGNORECASE | re.MULTILINE,
)
QUOTED_CREDENTIAL_ASSIGNMENT = re.compile(
    ASSIGNMENT_PREFIX_PATTERN
    + ASSIGNMENT_NAME_PATTERN
    + ASSIGNMENT_OPERATOR_PATTERN
    + r"(?P<quote>[\"'])(?P<value>.*?)(?P=quote)",
    re.IGNORECASE | re.MULTILINE,
)
BARE_CREDENTIAL_ASSIGNMENT = re.compile(
    ASSIGNMENT_PREFIX_PATTERN + ASSIGNMENT_NAME_PATTERN + ASSIGNMENT_OPERATOR_PATTERN + r"(?P<value>[^&#;\s,}\]]+)",
    re.IGNORECASE | re.MULTILINE,
)
PERCENT_TRIPLET = re.compile(r"%[0-9A-Fa-f]{2}")
MAX_PATH_DECODE_ROUNDS = 8


class SnykCliError(RuntimeError):
    """Report a safe, user-facing helper error."""


class NoRedirectHandler(request.HTTPRedirectHandler):
    """Reject redirects so authentication cannot cross trust boundaries."""

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
class SnykContext:
    """Resolved Snyk REST authentication and version context."""

    api_version: str
    auth_scheme: str
    base_url: str
    token: str | None
    token_env_name: str | None


@dataclass(frozen=True)
class OpenApiOperation:
    """Small stable view of a Snyk OpenAPI operation."""

    deprecated: bool
    method: str
    operation_id: str
    path: str
    summary: str
    tags: tuple[str, ...]


@dataclass(frozen=True)
class RequestPlan:
    """Resolved REST request details."""

    body: JsonValue
    method: str
    operation_id: str | None
    query: dict[str, str]
    url: str


@dataclass(frozen=True)
class ApiResult:
    """One Snyk REST response."""

    payload: JsonValue
    status: int
    sunset: str | None
    url: str
    response_bytes: int = 0


def optional_text(value: object) -> str | None:
    """Return a stripped optional string."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def is_environment_name(value: str) -> bool:
    """Return whether a name is a safe portable ASCII environment identifier."""
    return value.isascii() and value.isidentifier()


def as_string_list(value: object) -> list[str]:
    """Narrow argparse append or validated JSON string-list values."""
    return cast("list[str]", value)


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


def key_tokens(key: str) -> tuple[str, ...]:
    """Tokenize separator, camelCase, and PascalCase field names semantically."""
    decoded = decoded_parameter_name(key)
    tokens = (word.casefold() for word in identifier_words(decoded))
    return tuple(SINGULAR_KEY_TOKENS.get(token, token) for token in tokens)


def is_sensitive_key(key: str) -> bool:
    """Detect semantic credential fields without suffix-based prose false positives."""
    tokens = key_tokens(key)
    if not tokens:
        return False
    if len(tokens) == 1 and tokens[0] in KNOWN_SENSITIVE_COMPOUNDS:
        return True
    if tokens[-1] in SENSITIVE_NOUNS:
        return True
    if tokens[-1] == "key" and any(token in SENSITIVE_KEY_QUALIFIERS for token in tokens[:-1]):
        return True
    if len(tokens) >= WEBHOOK_FIELD_TOKEN_COUNT and tokens[-2:] == ("session", "id"):
        return True
    return len(tokens) >= WEBHOOK_FIELD_TOKEN_COUNT and tokens[-2:] == ("webhook", "url")


def decoded_parameter_name(value: str) -> str:
    """Decode an encoded parameter name enough to expose a credential field."""
    decoded = value
    for _ in range(MAX_PATH_DECODE_ROUNDS):
        next_value = parse.unquote_plus(decoded)
        if next_value == decoded:
            break
        decoded = next_value
    return decoded


def percent_triplet_pattern(value: str) -> str:
    """Match one encoded value while varying only hexadecimal triplet casing."""
    pieces: list[str] = []
    index = 0
    while index < len(value):
        if (
            index + 2 < len(value)
            and value[index] == "%"
            and all(character in "0123456789abcdefABCDEF" for character in value[index + 1 : index + 3])
        ):
            triplet = value[index + 1 : index + 3]
            pieces.append(
                "%"
                + "".join(
                    f"[{character.lower()}{character.upper()}]" if character.isalpha() else character
                    for character in triplet
                )
            )
            index += 3
            continue
        pieces.append(re.escape(value[index]))
        index += 1
    return "".join(pieces)


def encoded_credential_pattern(credential: str) -> re.Pattern[str]:
    """Match raw or arbitrarily percent-encoded bytes of one active credential."""
    pieces: list[str] = []
    for character in credential:
        encoded = "".join(f"%{byte:02X}" for byte in character.encode("utf-8"))
        alternatives = [re.escape(character), percent_triplet_pattern(encoded)]
        if character == " ":
            alternatives.append(r"\+")
        pieces.append(f"(?:{'|'.join(dict.fromkeys(alternatives))})")
    return re.compile("".join(pieces))


def is_credible_scheme_credential(scheme: str, value: str) -> bool:
    """Distinguish credential syntax from ordinary prose after scheme words."""
    credential = value.strip("\"'").rstrip(".!?)]}")
    if scheme.casefold() == "basic":
        try:
            decoded = base64.b64decode(credential, validate=True)
        except ValueError:
            return False
        return b":" in decoded
    if credential.casefold() in SCHEME_PROSE_WORDS:
        return False
    return len(credential) >= MIN_SCHEME_CREDENTIAL_CHARACTERS


def redact_authorization_assignments(value: str) -> str:
    """Redact quoted or bare Authorization assignments."""
    redacted = value
    for assignment_pattern in AUTHORIZATION_ASSIGNMENTS:
        redacted = assignment_pattern.sub(REDACTED_TEXT, redacted)
    return redacted


def redact_untrusted_text(value: object, token: str | None, *, max_characters: int | None = None) -> str:
    """Redact active and syntactically credible credentials from one scalar string."""
    text = str(value)
    credentials: set[str] = set()
    if token:
        credential = token.strip()
        if credential:
            credentials.add(credential)
            scheme_parts = credential.split(maxsplit=1)
            if len(scheme_parts) == SCHEME_CREDENTIAL_PARTS and scheme_parts[0].casefold() in {
                "bearer",
                "basic",
                "token",
            }:
                credentials.add(scheme_parts[1])
    for credential in sorted(credentials, key=len, reverse=True):
        text = encoded_credential_pattern(credential).sub(REDACTED_TEXT, text)
    text = redact_authorization_assignments(text)

    def redact_scheme_credential(match: re.Match[str]) -> str:
        if is_credible_scheme_credential(match.group("scheme"), match.group("credential")):
            return REDACTED_TEXT
        return match.group(0)

    text = SCHEME_CREDENTIAL.sub(redact_scheme_credential, text)
    text = URL_USERINFO.sub(r"\1<redacted>@", text)

    def redact_credential_assignment(match: re.Match[str]) -> str:
        name = match.group("name")
        if not is_sensitive_key(decoded_parameter_name(name)):
            return match.group(0)
        quote = match.groupdict().get("quote", "")
        return f"{match.group('prefix')}{name}{match.group('operator')}{quote}<redacted>{quote}"

    text = QUERY_CREDENTIAL_ASSIGNMENT.sub(redact_credential_assignment, text)
    text = QUOTED_CREDENTIAL_ASSIGNMENT.sub(redact_credential_assignment, text)
    text = BARE_CREDENTIAL_ASSIGNMENT.sub(redact_credential_assignment, text)
    if max_characters is not None and len(text) > max_characters:
        return f"{text[: max_characters - 3]}..."
    return text


def safe_reason(reason: object, token: str | None) -> str:
    """Format one transport reason without leaking credentials or unbounded text."""
    return redact_untrusted_text(reason, token, max_characters=MAX_UNTRUSTED_REASON_TEXT)


def strict_json_float(value: str) -> float:
    """Parse one JSON number and reject exponent overflow to a nonfinite float."""
    parsed_value = float(value)
    if not math.isfinite(parsed_value):
        raise ValueError("JSON numbers must be finite.")
    return parsed_value


def reject_json_constant(value: str) -> Never:
    """Reject JavaScript-style nonfinite constants accepted by Python's decoder."""
    raise ValueError(f"JSON constant {value} is not permitted.")


def strict_json_loads(data: bytes | str, *, source: str) -> JsonValue:
    """Decode strict UTF-8 JSON whose floating-point values are all finite."""
    try:
        text = data.decode("utf-8") if isinstance(data, bytes) else data
        return cast(
            "JsonValue",
            json.loads(text, parse_constant=reject_json_constant, parse_float=strict_json_float),
        )
    except (ValueError, OverflowError) as exception:
        raise SnykCliError(f"{source} returned malformed JSON or a nonfinite number.") from exception


def strict_json_dumps(
    value: JsonValue,
    *,
    source: str,
    ensure_ascii: bool = True,
    style: str = "default",
) -> str:
    """Serialize JSON atomically while refusing nonfinite or unsupported values."""
    indent = 2 if style == "pretty" else None
    sort_keys = style == "pretty"
    separators = (",", ":") if style == "compact" else None
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=ensure_ascii,
            indent=indent,
            sort_keys=sort_keys,
            separators=separators,
        )
    except (TypeError, ValueError, OverflowError) as exception:
        raise SnykCliError(f"{source} contains a nonfinite or non-JSON value.") from exception


def validate_timeout(value: object) -> float:
    """Require a finite positive network timeout."""
    try:
        timeout = float(str(value))
    except (TypeError, ValueError, OverflowError) as exception:
        raise SnykCliError("--timeout must be finite and greater than zero.") from exception
    if not math.isfinite(timeout) or timeout <= 0:
        raise SnykCliError("--timeout must be finite and greater than zero.")
    return timeout


def validate_retries(value: object) -> int:
    """Require the documented bounded GET retry count."""
    try:
        retries = int(str(value))
    except (TypeError, ValueError, OverflowError) as exception:
        raise SnykCliError(f"--retries must be between zero and {MAX_RETRIES}.") from exception
    if not 0 <= retries <= MAX_RETRIES:
        raise SnykCliError(f"--retries must be between zero and {MAX_RETRIES}.")
    return retries


def validate_max_pages(value: object) -> int:
    """Require the documented bounded pagination page count."""
    try:
        max_pages = int(str(value))
    except (TypeError, ValueError, OverflowError) as exception:
        raise SnykCliError(f"--max-pages must be between one and {MAX_PAGES}.") from exception
    if not 1 <= max_pages <= MAX_PAGES:
        raise SnykCliError(f"--max-pages must be between one and {MAX_PAGES}.")
    return max_pages


def trusted_content_length(headers: Message[str, str]) -> int | None:
    """Return a nonnegative decimal Content-Length, ignoring malformed values."""
    values = headers.get_all("Content-Length")
    if values is not None and len(values) != 1:
        return None
    value = optional_text(headers.get("Content-Length"))
    if value is None or not value.isascii() or not value.isdecimal():
        return None
    return int(value)


def read_bounded_response(
    stream: IO[bytes],
    headers: Message[str, str],
    *,
    max_bytes: int,
    source: str,
) -> bytes:
    """Read at most one byte beyond a response limit after an optional early rejection."""
    declared_length = trusted_content_length(headers)
    if declared_length is not None and declared_length > max_bytes:
        raise SnykCliError(f"{source} exceeds the {max_bytes}-byte safety limit.")
    data = stream.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise SnykCliError(f"{source} exceeds the {max_bytes}-byte safety limit.")
    return data


def sanitize_base_url(value: str) -> str:
    """Validate and normalize an official regional Snyk REST base URL."""
    parsed = parse.urlsplit(value.strip())
    if parsed.scheme.lower() != "https" or not parsed.netloc:
        raise SnykCliError("Snyk REST base URL must be an absolute HTTPS URL.")
    if parsed.username is not None or parsed.password is not None:
        raise SnykCliError("Snyk REST base URL must not contain credentials.")
    if parsed.query or parsed.fragment:
        raise SnykCliError("Snyk REST base URL must not contain a query or fragment.")
    try:
        port = parsed.port
    except ValueError as exception:
        raise SnykCliError("Snyk REST base URL contains an invalid port.") from exception
    hostname = parsed.hostname.casefold() if parsed.hostname is not None else ""
    if port is not None or parsed.path not in {"/rest", "/rest/"}:
        raise SnykCliError("Snyk REST base URL must use an official regional origin under /rest.")
    base_url = f"https://{hostname}/rest"
    if base_url not in OFFICIAL_REST_BASE_URLS:
        raise SnykCliError("Snyk REST base URL must use an official regional Snyk API origin.")
    return base_url


def validate_api_version(value: str) -> str:
    """Validate Snyk's date and optional stability-tree version syntax."""
    version = value.strip()
    if API_VERSION.fullmatch(version) is None:
        raise SnykCliError("API version must use YYYY-MM-DD, optionally with ~beta or ~experimental.")
    return version


def resolve_token(token_envs: list[str]) -> tuple[str | None, str | None]:
    """Resolve the first non-empty token from safe environment names."""
    candidates = token_envs or list(DEFAULT_TOKEN_ENVS)
    for name in candidates:
        if not is_environment_name(name):
            raise SnykCliError(f"Invalid token environment variable name: {name}")
        token = os.environ.get(name, "").strip()
        if token:
            return token, name
    return None, None


def resolve_context(arguments: argparse.Namespace, *, include_token: bool = True) -> SnykContext:
    """Resolve the selected region, version, token, and authentication scheme."""
    base_url = sanitize_base_url(str(arguments.base_url))
    token, token_env_name = resolve_token(as_string_list(arguments.token_envs)) if include_token else (None, None)
    return SnykContext(
        api_version=validate_api_version(str(arguments.api_version)),
        auth_scheme=str(arguments.auth_scheme),
        base_url=base_url,
        token=token,
        token_env_name=token_env_name,
    )


def response_payload(data: bytes, content_type: str, *, source: str, token: str | None = None) -> JsonValue:
    """Decode a strict JSON error payload or preserve bounded external text."""
    if not data:
        return None
    if "json" in content_type.lower() or not content_type:
        return strict_json_loads(data, source=source)
    return redact_untrusted_text(
        data.decode("utf-8", errors="replace"),
        token,
        max_characters=MAX_RESPONSE_TEXT,
    )


def rest_success_payload(data: bytes, *, status: int) -> JsonValue:
    """Decode a status-aware successful REST body under the strict JSON contract."""
    if not data:
        if status == HTTP_NO_CONTENT:
            return None
        raise SnykCliError(f"Snyk REST API returned HTTP {status} with an invalid empty response.")
    return strict_json_loads(data, source=f"Snyk REST API HTTP {status} response")


def has_control_character(value: str) -> bool:
    """Return whether text contains a C0 control or ASCII delete."""
    return any(
        ord(character) <= MAX_ASCII_CONTROL_CODEPOINT or ord(character) == ASCII_DELETE_CODEPOINT for character in value
    )


def has_malformed_percent_escape(value: str, *, decoded_once: bool) -> bool:
    """Reject malformed escapes while allowing a decoded non-structural literal percent."""
    index = 0
    while index < len(value):
        if value[index] != "%":
            index += 1
            continue
        if index + 2 < len(value) and all(
            character in "0123456789abcdefABCDEF" for character in value[index + 1 : index + 3]
        ):
            index += 3
            continue
        following = value[index + 1 : index + 2]
        if not decoded_once or (following and following.isalnum()):
            return True
        index += 1
    return False


def validate_decoded_path_segment(value: str, *, source: str) -> None:
    """Reject one path segment once decoding exposes structural data."""
    if value in {".", ".."}:
        raise SnykCliError(f"{source} must not contain traversal segments.")
    if any(character in value for character in ("/", "\\", "?", "#")):
        raise SnykCliError(f"{source} contains an encoded structural delimiter.")
    if has_control_character(value):
        raise SnykCliError(f"{source} must not contain encoded control characters.")


def validate_confined_path(path: str, *, source: str) -> None:
    """Reject structural path data exposed by repeated percent decoding."""
    if has_control_character(path):
        raise SnykCliError(f"{source} must not contain control characters.")
    for raw_segment in path.split("/"):
        decoded = raw_segment
        for decode_round in range(MAX_PATH_DECODE_ROUNDS):
            validate_decoded_path_segment(decoded, source=source)
            if has_malformed_percent_escape(decoded, decoded_once=decode_round > 0):
                raise SnykCliError(f"{source} contains malformed or residual percent encoding.")
            next_value = parse.unquote(decoded)
            if next_value == decoded:
                break
            decoded = next_value
        else:
            if PERCENT_TRIPLET.search(decoded) is not None:
                raise SnykCliError(f"{source} contains dangerous residual percent encoding.")
        validate_decoded_path_segment(decoded, source=source)


def spec_url(context: SnykContext) -> str:
    """Build the official OpenAPI URL for the selected region and version."""
    return f"{context.base_url}/openapi/{parse.quote(context.api_version, safe='~')}"


def validate_spec_url(value: str, context: SnykContext) -> str:
    """Validate an explicit same-origin OpenAPI URL."""
    parsed = parse.urlsplit(value.strip())
    base = parse.urlsplit(context.base_url)
    if parsed.scheme.lower() != "https" or not parsed.netloc:
        raise SnykCliError("OpenAPI specification URL must be absolute HTTPS.")
    if parsed.username is not None or parsed.password is not None:
        raise SnykCliError("OpenAPI specification URL must not contain credentials.")
    if parsed.query or parsed.fragment:
        raise SnykCliError("OpenAPI specification URL must not contain query or fragment.")
    validate_confined_path(parsed.path, source="OpenAPI specification URL path")
    if (parsed.scheme.lower(), parsed.netloc.lower()) != (base.scheme.lower(), base.netloc.lower()):
        raise SnykCliError("OpenAPI specification origin must match the selected Snyk region.")
    if not parsed.path.startswith(f"{base.path.rstrip('/')}/openapi/"):
        raise SnykCliError("OpenAPI specification must remain under the selected /rest/openapi path.")
    return value.strip()


def get_json(
    url: str,
    *,
    timeout: float,
    source: str,
    max_bytes: int = MAX_REMOTE_SPEC_BYTES,
    token: str | None = None,
) -> JsonValue:
    """Fetch bounded public JSON without redirects."""
    opener = request.build_opener(NoRedirectHandler())
    try:
        with opener.open(
            request.Request(  # noqa: S310  # URL validated by caller.
                url,
                headers={"Accept": "application/json"},
            ),
            timeout=validate_timeout(timeout),
        ) as response:
            data = read_bounded_response(
                response,
                response.headers,
                max_bytes=max_bytes,
                source=source,
            )
            return strict_json_loads(data, source=source)
    except error.HTTPError as exception:
        try:
            try:
                data = read_bounded_response(
                    exception,
                    exception.headers,
                    max_bytes=MAX_ERROR_RESPONSE_BYTES,
                    source=f"{source} error response",
                )
                payload = response_payload(
                    data,
                    exception.headers.get("Content-Type", ""),
                    source=source,
                    token=token,
                )
                detail = strict_json_dumps(redact_json(payload, token), source=f"{source} error", ensure_ascii=False)
            except (SnykCliError, OSError, HTTPException) as body_exception:
                detail = safe_reason(body_exception, token)
            raise SnykCliError(f"{source} request failed with HTTP {exception.code}: {detail}") from exception
        finally:
            exception.close()
    except (error.URLError, OSError, HTTPException) as exception:
        reason = exception.reason if isinstance(exception, error.URLError) else exception
        raise SnykCliError(f"{source} request failed: {safe_reason(reason, token)}") from exception


def load_openapi(arguments: argparse.Namespace, context: SnykContext) -> tuple[dict[str, JsonValue], str]:
    """Load a local or live Snyk OpenAPI JSON document."""
    spec_file = cast("Path | None", arguments.spec_file)
    if spec_file is not None:
        try:
            with spec_file.open("rb") as file:
                data = file.read(MAX_LOCAL_SPEC_BYTES + 1)
        except OSError as exception:
            raise SnykCliError(f"Could not read OpenAPI JSON file: {spec_file}") from exception
        if len(data) > MAX_LOCAL_SPEC_BYTES:
            raise SnykCliError(f"OpenAPI JSON file exceeds the {MAX_LOCAL_SPEC_BYTES}-byte safety limit.")
        try:
            payload = strict_json_loads(data, source="OpenAPI JSON file")
        except SnykCliError as exception:
            raise SnykCliError(f"Could not parse OpenAPI JSON file: {spec_file}") from exception
        source = str(spec_file)
    else:
        source = validate_spec_url(optional_text(arguments.spec_url) or spec_url(context), context)
        payload = get_json(
            source,
            timeout=validate_timeout(arguments.timeout),
            source="Snyk OpenAPI",
            max_bytes=MAX_REMOTE_SPEC_BYTES,
            token=context.token,
        )
    if not isinstance(payload, dict):
        raise SnykCliError("OpenAPI document root must be an object.")
    return payload, source


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
    """Extract operation metadata from an OpenAPI JSON document."""
    paths = spec.get("paths")
    if not isinstance(paths, dict):
        raise SnykCliError("OpenAPI document does not contain a paths object.")
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
    """Parse repeatable name=value options and reject secrets or duplicates."""
    result: dict[str, str] = {}
    for value in values:
        name, separator, item_value = value.partition("=")
        name = name.strip()
        if not separator or not name or not item_value:
            raise SnykCliError(f"{label} values must use non-empty name=value syntax.")
        if name in result:
            raise SnykCliError(f"Duplicate {label} name: {name}")
        if label == "query" and is_sensitive_key(name):
            raise SnykCliError(f"Refusing token-like query parameter: {name}")
        result[name] = item_value
    return result


def load_body(arguments: argparse.Namespace) -> JsonValue:
    """Load an optional JSON:API body."""
    body_text = optional_text(arguments.body_json)
    body_file = cast("Path | None", arguments.body_file)
    if body_file is not None:
        try:
            body_text = body_file.read_text(encoding="utf-8")
        except OSError as exception:
            raise SnykCliError(f"Could not read request body file: {body_file}") from exception
    if body_text is None:
        return None
    try:
        return strict_json_loads(body_text, source="Request body")
    except SnykCliError as exception:
        raise SnykCliError("Request body must be valid finite JSON.") from exception


def operation_by_id(operations: list[OpenApiOperation], operation_id: str) -> OpenApiOperation:
    """Resolve exactly one case-sensitive operation ID."""
    matches = [operation for operation in operations if operation.operation_id == operation_id]
    if len(matches) != 1:
        raise SnykCliError("operationId must resolve exactly once in the OpenAPI document.")
    return matches[0]


def fill_path(path_template: str, values: dict[str, str]) -> str:
    """Fill every OpenAPI path parameter and reject unused values."""
    required = PATH_PARAMETER.findall(path_template)
    missing = [name for name in required if name not in values]
    unused = [name for name in values if name not in required]
    if missing:
        raise SnykCliError(f"Missing path parameter(s): {', '.join(missing)}")
    if unused:
        raise SnykCliError(f"Unused path parameter(s): {', '.join(unused)}")
    result = path_template
    for name in required:
        result = result.replace(f"{{{name}}}", parse.quote(values[name], safe=""))
    return result


def validated_endpoint_url(base_url: str, endpoint: str) -> str:
    """Resolve an endpoint while locking it to the selected region and /rest."""
    parsed_input = parse.urlsplit(endpoint)
    if parsed_input.netloc and not parsed_input.scheme:
        raise SnykCliError("Relative endpoint must not contain a network-path authority.")
    if parsed_input.query or parsed_input.fragment:
        raise SnykCliError("Endpoint must not contain query or fragment; use --query.")
    validate_confined_path(parsed_input.path, source="Endpoint path")
    if endpoint.startswith("/"):
        candidate = f"{base_url}{endpoint}"
    elif parsed_input.scheme:
        candidate = endpoint
    else:
        raise SnykCliError("Relative endpoint must start with /.")
    base = parse.urlsplit(base_url)
    parsed = parse.urlsplit(candidate)
    if parsed.scheme.lower() != "https" or not parsed.netloc:
        raise SnykCliError("Endpoint must resolve to an absolute HTTPS URL.")
    if parsed.username is not None or parsed.password is not None:
        raise SnykCliError("Endpoint must not contain URL credentials.")
    if (parsed.scheme.lower(), parsed.netloc.lower()) != (base.scheme.lower(), base.netloc.lower()):
        raise SnykCliError("Absolute endpoint origin must match the selected Snyk region.")
    validate_confined_path(parsed.path, source="Resolved endpoint path")
    base_path = base.path.rstrip("/")
    if parsed.path != base_path and not parsed.path.startswith(f"{base_path}/"):
        raise SnykCliError("Absolute endpoint must remain under the configured /rest base path.")
    return candidate


def build_plan(arguments: argparse.Namespace, context: SnykContext) -> RequestPlan:
    """Resolve raw or operation-based request arguments."""
    endpoint = optional_text(arguments.endpoint)
    operation_id = optional_text(arguments.operation_id)
    if endpoint is not None and operation_id is not None:
        raise SnykCliError("Provide either an endpoint or --operation-id, not both.")
    if endpoint is None and operation_id is None:
        raise SnykCliError("Provide an endpoint or --operation-id.")
    method = optional_text(arguments.method)
    if operation_id is not None:
        spec, _ = load_openapi(arguments, context)
        operation = operation_by_id(parse_operations(spec), operation_id)
        if method is not None and method.upper() != operation.method:
            raise SnykCliError("--method conflicts with the OpenAPI operation.")
        method = operation.method
        endpoint = fill_path(operation.path, parse_pairs(as_string_list(arguments.path_values), label="path"))
    elif as_string_list(arguments.path_values):
        raise SnykCliError("--path requires --operation-id.")
    method = (method or "GET").upper()
    body = load_body(arguments)
    if method == "GET" and body is not None:
        raise SnykCliError("GET requests must not include a body.")
    query = parse_pairs(as_string_list(arguments.query), label="query")
    if "version" in query and query["version"] != context.api_version:
        raise SnykCliError("Explicit version query conflicts with --api-version.")
    query["version"] = context.api_version
    return RequestPlan(
        body=body,
        method=method,
        operation_id=operation_id,
        query=query,
        url=validated_endpoint_url(context.base_url, cast("str", endpoint)),
    )


def redact_json(value: JsonValue, token: str | None) -> JsonValue:
    """Redact normalized sensitive keys and credentials embedded in strings."""
    if isinstance(value, dict):
        return {
            key: REDACTED_TEXT if is_sensitive_key(key) else redact_json(item, token) for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_json(item, token) for item in value]
    if isinstance(value, str):
        return redact_untrusted_text(value, token)
    return value


def encode_url(url: str, query: dict[str, str]) -> str:
    """Append encoded query parameters."""
    parsed = parse.urlsplit(url)
    return parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parse.urlencode(query), ""))


def canonical_request_url(plan: RequestPlan) -> str:
    """Canonicalize one validated request URL for pagination loop detection."""
    parsed = parse.urlsplit(encode_url(plan.url, plan.query))
    path = parse.quote(parse.unquote(parsed.path), safe="/:@!$&'()*+,;=-._~")
    query = parse.urlencode(sorted(parse.parse_qsl(parsed.query, keep_blank_values=True)))
    return parse.urlunsplit((parsed.scheme.casefold(), parsed.netloc.casefold(), path, query, ""))


def indeterminate_write_error(reason: object, token: str | None = None) -> SnykCliError:
    """Build the required warning for a write whose remote result is unknown."""
    message = " ".join(
        (
            "Snyk REST write failed after one attempt;",
            "indeterminate outcome.",
            f"Verify remote state before any retry: {safe_reason(reason, token)}",
        )
    )
    return SnykCliError(message)


def is_ambiguous_write_status(status: int) -> bool:
    """Return whether an HTTP response cannot safely authorize replaying a write."""
    return (
        status
        in {
            HTTP_REQUEST_TIMEOUT,
            HTTP_TOO_MANY_REQUESTS,
        }
        or HTTP_SERVER_ERROR_MIN <= status < HTTP_SERVER_ERROR_LIMIT
    )


def request_attempts(method: str, retries: int) -> int:
    """Return retry-inclusive attempts for GET and one attempt for writes."""
    return retries + 1 if method == "GET" else 1


def retry_backoff_delay(attempt: int) -> float:
    """Return overflow-safe capped exponential backoff."""
    bounded_attempt = min(max(attempt, 0), MAX_RETRIES)
    return min(float(2**bounded_attempt), MAX_RETRY_DELAY_SECONDS)


def retry_delay(http_error: error.HTTPError, attempt: int) -> float:
    """Return a bounded delay from Retry-After or exponential fallback."""
    value = http_error.headers.get("Retry-After", "").strip()
    try:
        parsed_value = float(value)
    except ValueError:
        return retry_backoff_delay(attempt)
    if not value or not math.isfinite(parsed_value) or parsed_value < 0:
        return retry_backoff_delay(attempt)
    return min(parsed_value, MAX_RETRY_DELAY_SECONDS)


def raise_http_error(http_error: error.HTTPError, token: str | None, *, is_get: bool) -> Never:
    """Raise a redacted HTTP error with write-outcome safety context."""
    ambiguous_write = not is_get and is_ambiguous_write_status(http_error.code)
    try:
        data = read_bounded_response(
            http_error,
            http_error.headers,
            max_bytes=MAX_ERROR_RESPONSE_BYTES,
            source="Snyk REST API error response",
        )
        payload = response_payload(
            data,
            http_error.headers.get("Content-Type", ""),
            source="Snyk REST API",
            token=token,
        )
    except (SnykCliError, OSError, HTTPException) as decode_exception:
        if ambiguous_write:
            raise indeterminate_write_error(
                f"HTTP {http_error.code} with an unreadable bounded error response",
                token,
            ) from decode_exception
        safe_decode_reason = safe_reason(decode_exception, token)
        message = f"Snyk REST API HTTP {http_error.code} error body could not be read safely: {safe_decode_reason}"
        raise SnykCliError(message) from decode_exception
    safe = redact_json(payload, token)
    detail = strict_json_dumps(safe, source="Snyk REST API error response", ensure_ascii=False)
    if ambiguous_write:
        raise indeterminate_write_error(
            f"HTTP {http_error.code}: {detail}",
            token,
        ) from http_error
    raise SnykCliError(f"Snyk REST API returned HTTP {http_error.code}: {detail}") from http_error


def should_retry_read(attempt: int, retries: int, *, is_get: bool) -> bool:
    """Return whether another GET attempt remains."""
    return is_get and attempt < retries


def handle_http_error_attempt(
    exception: error.HTTPError,
    *,
    attempt: int,
    retries: int,
    is_get: bool,
    token: str | None,
) -> None:
    """Delay one retryable GET failure or raise its final safe error."""
    try:
        if exception.code in GET_RETRYABLE_STATUS_CODES and should_retry_read(attempt, retries, is_get=is_get):
            time.sleep(retry_delay(exception, attempt))
            return
        raise_http_error(exception, token, is_get=is_get)
    finally:
        exception.close()


def handle_transport_error_attempt(
    exception: error.URLError | OSError | HTTPException,
    *,
    attempt: int,
    retries: int,
    is_get: bool,
    token: str | None,
) -> None:
    """Delay one retryable GET transport failure or raise its final safe error."""
    if should_retry_read(attempt, retries, is_get=is_get):
        time.sleep(retry_backoff_delay(attempt))
        return
    reason = exception.reason if isinstance(exception, error.URLError) else exception
    if not is_get:
        raise indeterminate_write_error(reason, token) from exception
    raise SnykCliError(f"Snyk REST request failed: {safe_reason(reason, token)}") from exception


def decode_success_response(
    stream: IO[bytes],
    headers: Message[str, str],
    *,
    status: int,
    is_get: bool,
    token: str | None,
) -> tuple[JsonValue, bytes]:
    """Read and decode one success while preserving post-write ambiguity."""
    try:
        data = read_bounded_response(
            stream,
            headers,
            max_bytes=MAX_API_RESPONSE_BYTES,
            source="Snyk REST API response",
        )
        return rest_success_payload(data, status=status), data
    except (SnykCliError, OSError, HTTPException) as exception:
        reason = f"HTTP {status} response could not be read or decoded safely: {safe_reason(exception, token)}"
        if not is_get and HTTP_SUCCESS_MIN <= status < HTTP_SUCCESS_LIMIT:
            raise indeterminate_write_error(reason, token) from exception
        raise SnykCliError(f"Snyk REST {reason}") from exception


def send_request(context: SnykContext, plan: RequestPlan, arguments: argparse.Namespace) -> ApiResult:
    """Send one Snyk REST request, retrying only idempotent GET reads."""
    base_url = sanitize_base_url(context.base_url)
    method = plan.method.upper()
    if method not in {"DELETE", "GET", "PATCH", "POST", "PUT"}:
        raise SnykCliError(f"Unsupported HTTP method: {plan.method}")
    if any(is_sensitive_key(name) for name in plan.query):
        raise SnykCliError("Refusing token-like query parameter before authentication.")
    url = encode_url(validated_endpoint_url(base_url, plan.url), plan.query)
    body = (
        None
        if plan.body is None
        else strict_json_dumps(plan.body, source="Snyk REST request body", style="compact").encode("utf-8")
    )
    headers = {
        "Accept": "application/vnd.api+json",
        "Content-Type": "application/vnd.api+json",
        "User-Agent": "codex-snyk-management/1",
    }
    if context.token is not None:
        headers["Authorization"] = f"{context.auth_scheme} {context.token}"
    opener = request.build_opener(NoRedirectHandler())
    retries = validate_retries(arguments.retries)
    timeout = validate_timeout(arguments.timeout)
    is_get = method == "GET"
    attempts = request_attempts(method, retries)
    for attempt in range(attempts):
        api_request = request.Request(  # noqa: S310  # build_plan region-locks the URL.
            url,
            data=body,
            headers=headers,
            method=method,
        )
        try:
            with opener.open(api_request, timeout=timeout) as response:  # URL is origin locked.
                status = int(response.status)
                payload, data = decode_success_response(
                    response,
                    response.headers,
                    status=status,
                    is_get=is_get,
                    token=context.token,
                )
                return ApiResult(
                    payload=payload,
                    status=status,
                    sunset=optional_text(response.headers.get("Sunset")),
                    url=url,
                    response_bytes=len(data),
                )
        except error.HTTPError as exception:
            handle_http_error_attempt(
                exception,
                attempt=attempt,
                retries=retries,
                is_get=is_get,
                token=context.token,
            )
            continue
        except (error.URLError, OSError, HTTPException) as exception:
            handle_transport_error_attempt(
                exception,
                attempt=attempt,
                retries=retries,
                is_get=is_get,
                token=context.token,
            )
            continue
    raise SnykCliError("Snyk REST retry loop ended unexpectedly.")


def pagination_plan(context: SnykContext, plan: RequestPlan, next_link: str) -> RequestPlan:
    """Validate and convert a JSON:API links.next value into the next request."""
    try:
        parsed = parse.urlsplit(next_link)
    except ValueError as exception:
        raise SnykCliError("Pagination link is malformed.") from exception
    if parsed.fragment:
        raise SnykCliError("Pagination link must not contain a fragment.")
    if parsed.netloc and not parsed.scheme:
        raise SnykCliError("Pagination link must not use a network-path authority.")
    if parsed.scheme:
        absolute = parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
        _ = validated_endpoint_url(context.base_url, absolute)
    else:
        path = parsed.path
        base_path = parse.urlsplit(context.base_url).path.rstrip("/")
        endpoint = path[len(base_path) :] if path.startswith(f"{base_path}/") else path
        if not endpoint.startswith("/"):
            raise SnykCliError("Pagination link path must be absolute.")
        absolute = validated_endpoint_url(context.base_url, endpoint)
    try:
        query = dict(parse.parse_qsl(parsed.query, keep_blank_values=False, strict_parsing=True))
    except ValueError as exception:
        raise SnykCliError("Pagination link query is malformed.") from exception
    if any(is_sensitive_key(name) for name in query):
        raise SnykCliError("Pagination link contains a token-like query parameter.")
    if query.get("version") != context.api_version:
        raise SnykCliError("Pagination link changed the selected API version.")
    return RequestPlan(body=None, method="GET", operation_id=plan.operation_id, query=query, url=absolute)


def pagination_page(payload: JsonValue) -> tuple[list[JsonValue], str | None]:
    """Validate one JSON:API page and return its data plus optional next link."""
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise SnykCliError("Paginated response must contain a data array.")
    data = cast("list[JsonValue]", payload["data"])
    links = payload.get("links")
    if links is None:
        return data, None
    if not isinstance(links, dict):
        raise SnykCliError("Paginated response links must be an object or null when present.")
    next_link = links.get("next")
    if next_link is None:
        return data, None
    if not isinstance(next_link, str) or not next_link.strip():
        raise SnykCliError("links.next must be a non-empty string or null.")
    return data, next_link


def merged_pagination_result(
    latest: ApiResult,
    merged: list[JsonValue],
    *,
    pages: int,
    response_bytes: int,
) -> ApiResult:
    """Build the stable terminal payload for fully consumed pagination."""
    return ApiResult(
        payload={"data": merged, "links": {"next": None}, "meta": {"pages": pages}},
        status=latest.status,
        sunset=latest.sunset,
        url=latest.url,
        response_bytes=response_bytes,
    )


def paginated_request(context: SnykContext, plan: RequestPlan, arguments: argparse.Namespace) -> ApiResult:
    """Follow JSON:API links.next until it is absent or null."""
    if plan.method != "GET":
        raise SnykCliError("--paginate is supported only for GET requests.")
    merged: list[JsonValue] = []
    current = plan
    latest: ApiResult | None = None
    response_bytes = 0
    seen_urls = {canonical_request_url(current)}
    pages = 0
    max_pages = validate_max_pages(arguments.max_pages)
    for pages in range(1, max_pages + 1):
        latest = send_request(context, current, arguments)
        next_response_bytes = response_bytes + latest.response_bytes
        if next_response_bytes > MAX_PAGINATED_RESPONSE_BYTES:
            raise SnykCliError(
                " ".join(
                    (
                        f"Snyk pagination exceeded the {MAX_PAGINATED_RESPONSE_BYTES}-byte cumulative safety limit",
                        f"after {pages - 1} retained page(s); page {pages} was fetched but not retained.",
                    )
                )
            )
        page_data, next_link = pagination_page(latest.payload)
        merged.extend(page_data)
        response_bytes = next_response_bytes
        if next_link is None:
            return merged_pagination_result(
                latest,
                merged,
                pages=pages,
                response_bytes=response_bytes,
            )
        next_plan = pagination_plan(context, plan, next_link)
        canonical_next_url = canonical_request_url(next_plan)
        if canonical_next_url in seen_urls:
            raise SnykCliError(
                f"Snyk pagination is incomplete after {pages} page(s); refusing a repeated links.next URL."
            )
        seen_urls.add(canonical_next_url)
        current = next_plan
    raise SnykCliError("Pagination reached --max-pages before links.next became null.")


def write_json(value: JsonValue, *, prefix: str = "") -> None:
    """Write deterministic JSON output."""
    serialized = strict_json_dumps(
        value,
        source="Snyk helper output",
        ensure_ascii=False,
        style="pretty",
    )
    _ = sys.stdout.write(prefix + serialized + "\n")


def handle_context(arguments: argparse.Namespace) -> int:
    """Print safe region, version, and token context."""
    context = resolve_context(arguments)
    write_json(
        {
            "apiVersion": context.api_version,
            "authenticationScheme": context.auth_scheme,
            "baseUrl": context.base_url,
            "token": "configured" if context.token else "missing",
            "tokenEnvironment": context.token_env_name,
        }
    )
    return 0


def handle_versions(arguments: argparse.Namespace) -> int:
    """List OpenAPI versions exposed by the selected Snyk region."""
    context = resolve_context(arguments)
    url = f"{context.base_url}/openapi"
    payload = get_json(
        url,
        timeout=validate_timeout(arguments.timeout),
        source="Snyk OpenAPI versions",
        max_bytes=MAX_VERSION_RESPONSE_BYTES,
        token=context.token,
    )
    if not isinstance(payload, list) or not all(isinstance(item, str) for item in payload):
        raise SnykCliError("Snyk OpenAPI versions response must be an array of strings.")
    versions = as_string_list(payload)
    write_json(
        {
            "configured": context.api_version,
            "latest": versions[-1] if versions else None,
            "versions": cast("JsonValue", versions),
        }
    )
    return 0


def handle_operations(arguments: argparse.Namespace) -> int:
    """Search the selected Snyk OpenAPI operation catalog."""
    context = resolve_context(arguments, include_token=False)
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
    write_json(
        {
            "apiVersion": context.api_version,
            "operations": [cast("JsonValue", asdict(item)) for item in operations],
            "source": source,
        }
    )
    return 0


def handle_request(arguments: argparse.Namespace) -> int:
    """Preview or send a constrained Snyk REST request."""
    validation_context = resolve_context(arguments, include_token=False)
    plan = build_plan(arguments, validation_context)
    context = resolve_context(arguments)
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
        raise SnykCliError("No token found. Set SNYK_TOKEN or use --token-env.")
    result = (
        paginated_request(context, plan, arguments)
        if bool(arguments.paginate)
        else send_request(context, plan, arguments)
    )
    output: JsonValue = {
        "meta": {
            "apiVersion": context.api_version,
            "method": plan.method,
            "operationId": plan.operation_id,
            "status": result.status,
            "sunset": result.sunset,
            "untrustedExternalData": True,
            "url": result.url,
        },
        "response": redact_json(result.payload, context.token),
    }
    write_json(output, prefix="" if bool(arguments.json) else "[untrusted-snyk-data]\n")
    return 0 if HTTP_SUCCESS_MIN <= result.status < HTTP_SUCCESS_LIMIT else 1


def common_parser() -> argparse.ArgumentParser:
    """Build options shared by every command."""
    parser = argparse.ArgumentParser(add_help=False)
    _ = parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    _ = parser.add_argument("--api-version", default=DEFAULT_API_VERSION)
    _ = parser.add_argument("--auth-scheme", choices=("token", "bearer"), default="token")
    _ = parser.add_argument("--token-env", action="append", dest="token_envs", default=[])
    _ = parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    _ = parser.add_argument("--json", action="store_true")
    return parser


def add_spec_options(parser: argparse.ArgumentParser) -> None:
    """Add OpenAPI source options."""
    source = parser.add_mutually_exclusive_group()
    _ = source.add_argument("--spec-file", type=Path)
    _ = source.add_argument("--spec-url")


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    common = common_parser()

    context = subparsers.add_parser("context", parents=[common])
    context.set_defaults(handler=handle_context)

    versions = subparsers.add_parser("versions", parents=[common])
    versions.set_defaults(handler=handle_versions)

    operations = subparsers.add_parser("operations", parents=[common])
    add_spec_options(operations)
    _ = operations.add_argument("--search")
    _ = operations.add_argument("--method", dest="filter_method", choices=("GET", "POST", "PUT", "PATCH", "DELETE"))
    operations.set_defaults(handler=handle_operations)

    api_request = subparsers.add_parser("request", parents=[common])
    add_spec_options(api_request)
    _ = api_request.add_argument("endpoint", nargs="?")
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
    _ = validate_timeout(arguments.timeout)
    if hasattr(arguments, "max_pages"):
        _ = validate_max_pages(arguments.max_pages)
    if hasattr(arguments, "retries"):
        _ = validate_retries(arguments.retries)
    if hasattr(arguments, "send") and bool(arguments.send) and bool(arguments.dry_run):
        raise SnykCliError("--send and --dry-run are mutually exclusive.")


def normalized_cli_arguments(arguments: list[str]) -> list[str]:
    """Keep negative nonfinite timeout spellings attached for safe validation."""
    normalized: list[str] = []
    index = 0
    while index < len(arguments):
        value = arguments[index]
        if value == "--timeout" and index + 1 < len(arguments):
            timeout_value = arguments[index + 1]
            if timeout_value.casefold() in {"-inf", "-infinity", "-nan"}:
                normalized.append(f"--timeout={timeout_value}")
                index += 2
                continue
        normalized.append(value)
        index += 1
    return normalized


def main() -> int:
    """Run the Snyk management helper."""
    parser = build_parser()
    arguments = parser.parse_args(normalized_cli_arguments(sys.argv[1:]))
    try:
        validate_arguments(arguments)
        handler = cast("Callable[[argparse.Namespace], int]", arguments.handler)
        return handler(arguments)
    except (SnykCliError, OSError) as exception:
        _ = sys.stderr.write(f"Error: {exception}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
