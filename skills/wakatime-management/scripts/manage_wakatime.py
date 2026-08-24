#!/usr/bin/env python
# Copyright (c) 2026 Nick2bad4u
"""Inspect WakaTime activity and make privacy-conscious API v1 requests."""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, cast, override
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


type JsonValue = bool | int | float | str | list[JsonValue] | dict[str, JsonValue] | None

DEFAULT_BASE_URL = "https://api.wakatime.com/api/v1"
DEFAULT_ACCESS_TOKEN_ENV = "WAKATIME_ACCESS_TOKEN"  # noqa: S105  # Environment-variable name, not a credential.
DEFAULT_API_KEY_ENV = "WAKATIME_API_KEY"
DEFAULT_TIMEOUT = 30.0
DEFAULT_RETRIES = 2
MAX_RESPONSE_TEXT = 2000
HTTP_FOUND = 302
HTTP_TOO_MANY_REQUESTS = 429
HTTP_SERVICE_UNAVAILABLE = 503
HTTP_GATEWAY_TIMEOUT = 504
HTTP_SUCCESS_MIN = 200
HTTP_SUCCESS_LIMIT = 300
RETRYABLE_STATUS_CODES = frozenset({HTTP_FOUND, HTTP_TOO_MANY_REQUESTS, HTTP_SERVICE_UNAVAILABLE, HTTP_GATEWAY_TIMEOUT})
SAFE_RANGE = re.compile(r"^[A-Za-z0-9_-]+$")
SENSITIVE_KEY = re.compile(
    r"(?:^|[-_])(api[-_]?key|authorization|credential|password|secret|token)(?:$|[-_])",
    re.IGNORECASE,
)


class WakaTimeCliError(RuntimeError):
    """Report a safe, user-facing helper error."""


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


def sanitize_base_url(value: str) -> str:
    """Validate and normalize a WakaTime API v1 base URL."""
    base_url = value.strip().rstrip("/")
    parsed = parse.urlsplit(base_url)
    if parsed.scheme.lower() != "https" or not parsed.netloc:
        raise WakaTimeCliError("WakaTime API base URL must be an absolute HTTPS URL.")
    if parsed.username is not None or parsed.password is not None:
        raise WakaTimeCliError("WakaTime API base URL must not contain credentials.")
    if parsed.query or parsed.fragment:
        raise WakaTimeCliError("WakaTime API base URL must not contain a query or fragment.")
    if not parsed.path.rstrip("/").endswith("/api/v1"):
        raise WakaTimeCliError("WakaTime API base URL must end with /api/v1.")
    return base_url


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
    return WakaTimeContext(
        authentication=resolve_authentication(arguments),
        base_url=sanitize_base_url(str(arguments.base_url)),
    )


def parse_date(value: str) -> date:
    """Parse an ISO calendar date for API commands."""
    try:
        return date.fromisoformat(value)
    except ValueError as exception:
        raise argparse.ArgumentTypeError("Date must use YYYY-MM-DD format.") from exception


def parse_pairs(values: list[str]) -> dict[str, str]:
    """Parse repeatable name=value query options without secret-like names."""
    result: dict[str, str] = {}
    for value in values:
        name, separator, item_value = value.partition("=")
        name = name.strip()
        if not separator or not name or not item_value:
            raise WakaTimeCliError("Query values must use non-empty name=value syntax.")
        if name in result:
            raise WakaTimeCliError(f"Duplicate query name: {name}")
        if SENSITIVE_KEY.search(name):
            raise WakaTimeCliError(f"Refusing token-like query parameter: {name}")
        result[name] = item_value
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
    try:
        return cast("JsonValue", json.loads(body_text))
    except json.JSONDecodeError as exception:
        raise WakaTimeCliError("Request body must be valid JSON.") from exception


def validated_endpoint_url(base_url: str, endpoint: str) -> str:
    """Resolve a relative endpoint and lock it to the configured API base."""
    parsed_input = parse.urlsplit(endpoint)
    if "\\" in endpoint or any(part == ".." for part in parsed_input.path.split("/")):
        raise WakaTimeCliError("Endpoint must not contain backslashes or traversal segments.")
    if parsed_input.query or parsed_input.fragment:
        raise WakaTimeCliError("Endpoint must not contain query or fragment; use --query.")
    if endpoint.startswith("/"):
        candidate = f"{base_url}{endpoint}"
    elif parsed_input.scheme:
        candidate = endpoint
    else:
        raise WakaTimeCliError("Relative endpoint must start with /.")
    base = parse.urlsplit(base_url)
    parsed = parse.urlsplit(candidate)
    if parsed.scheme.lower() != "https" or not parsed.netloc:
        raise WakaTimeCliError("Endpoint must resolve to an absolute HTTPS URL.")
    if parsed.username is not None or parsed.password is not None:
        raise WakaTimeCliError("Endpoint must not contain URL credentials.")
    if (parsed.scheme.lower(), parsed.netloc.lower()) != (base.scheme.lower(), base.netloc.lower()):
        raise WakaTimeCliError("Absolute endpoint origin must match the configured WakaTime API origin.")
    base_path = base.path.rstrip("/")
    if parsed.path != base_path and not parsed.path.startswith(f"{base_path}/"):
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
    explicit_query = parse_pairs(cast("list[str]", arguments.query))
    merged_query = dict(query or {})
    for name, value in explicit_query.items():
        if name in merged_query:
            raise WakaTimeCliError(f"Duplicate wrapped and explicit query name: {name}")
        merged_query[name] = value
    return RequestPlan(
        body=body,
        method=method,
        query=merged_query,
        url=validated_endpoint_url(context.base_url, resolved_endpoint),
    )


def redact_json(value: JsonValue, secret: str | None) -> JsonValue:
    """Redact sensitive keys and exact credential occurrences."""
    if isinstance(value, dict):
        return {
            key: "<redacted>" if SENSITIVE_KEY.search(key) else redact_json(item, secret) for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_json(item, secret) for item in value]
    if isinstance(value, str) and secret:
        return value.replace(secret, "<redacted>")
    return value


def encode_url(url: str, query: dict[str, str]) -> str:
    """Append encoded query parameters to a validated URL."""
    parsed = parse.urlsplit(url)
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
            return cast("JsonValue", json.loads(data.decode("utf-8")))
        except (UnicodeDecodeError, json.JSONDecodeError) as exception:
            raise WakaTimeCliError("WakaTime returned malformed JSON.") from exception
    return data.decode("utf-8", errors="replace")[:MAX_RESPONSE_TEXT]


def retry_delay(http_error: error.HTTPError, attempt: int) -> float:
    """Return a bounded retry delay."""
    value = http_error.headers.get("Retry-After", "").strip()
    try:
        return min(max(float(value), 0.0), 60.0) if value else min(2.0**attempt, 30.0)
    except ValueError:
        return min(2.0**attempt, 30.0)


def send_request(context: WakaTimeContext, plan: RequestPlan, arguments: argparse.Namespace) -> ApiResult:
    """Send one WakaTime request without following redirects."""
    url = encode_url(plan.url, plan.query)
    headers = {"Accept": "application/json", "User-Agent": "codex-wakatime-management/1"}
    authorization = authentication_header(context.authentication)
    if authorization is not None:
        headers["Authorization"] = authorization
    body = None if plan.body is None else json.dumps(plan.body, separators=(",", ":")).encode()
    if body is not None:
        headers["Content-Type"] = "application/json"
    opener = request.build_opener(NoRedirectHandler())
    for attempt in range(int(arguments.retries) + 1):
        api_request = request.Request(  # noqa: S310  # request_plan origin-locks the URL.
            url,
            data=body,
            headers=headers,
            method=plan.method,
        )
        try:
            with opener.open(api_request, timeout=float(arguments.timeout)) as response:  # URL is origin locked.
                return ApiResult(
                    payload=response_payload(response.read(), response.headers.get("Content-Type", "")),
                    status=int(response.status),
                    url=url,
                )
        except error.HTTPError as exception:
            try:
                payload = response_payload(exception.read(), exception.headers.get("Content-Type", ""))
                if exception.code in RETRYABLE_STATUS_CODES and attempt < int(arguments.retries):
                    time.sleep(retry_delay(exception, attempt))
                    continue
                safe = redact_json(payload, context.authentication.secret)
                raise WakaTimeCliError(
                    f"WakaTime API returned HTTP {exception.code}: {json.dumps(safe)}"
                ) from exception
            finally:
                exception.close()
        except error.URLError as exception:
            if attempt < int(arguments.retries):
                time.sleep(min(2.0**attempt, 10.0))
                continue
            raise WakaTimeCliError(f"WakaTime API request failed: {exception.reason}") from exception
    raise WakaTimeCliError("WakaTime API retry loop ended unexpectedly.")


def write_json(value: JsonValue) -> None:
    """Write deterministic JSON output."""
    _ = sys.stdout.write(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n")


def execute_plan(arguments: argparse.Namespace, context: WakaTimeContext, plan: RequestPlan) -> int:
    """Preview a write or execute a read/reviewed write."""
    preview = bool(arguments.dry_run) or (plan.method != "GET" and not bool(arguments.send))
    if preview:
        write_json(
            {
                "body": redact_json(plan.body, context.authentication.secret),
                "dryRun": True,
                "method": plan.method,
                "query": cast("JsonValue", plan.query),
                "url": encode_url(plan.url, plan.query),
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
            "url": result.url,
        },
        "response": redact_json(result.payload, context.authentication.secret),
    }
    if not bool(arguments.json):
        _ = sys.stdout.write("[untrusted-wakatime-data]\n")
    write_json(output)
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
    for name in ("project", "branches", "category"):
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
    _ = summaries.add_argument("--category")

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
    if float(arguments.timeout) <= 0:
        raise WakaTimeCliError("--timeout must be greater than zero.")
    if int(arguments.retries) < 0:
        raise WakaTimeCliError("--retries must be zero or greater.")
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
