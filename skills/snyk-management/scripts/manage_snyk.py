#!/usr/bin/env python
# Copyright (c) 2026 Nick2bad4u
"""Inspect Snyk REST OpenAPI operations and make constrained requests."""

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
    from collections.abc import Callable
    from http.client import HTTPMessage
    from typing import IO

type JsonValue = bool | int | float | str | list[JsonValue] | dict[str, JsonValue] | None

DEFAULT_BASE_URL = "https://api.snyk.io/rest"
DEFAULT_API_VERSION = "2024-10-15"
DEFAULT_TOKEN_ENVS = ("SNYK_TOKEN", "SNYK_API_TOKEN")
DEFAULT_TIMEOUT = 30.0
DEFAULT_RETRIES = 2
DEFAULT_MAX_PAGES = 100
MAX_RESPONSE_TEXT = 2000
HTTP_TOO_MANY_REQUESTS = 429
HTTP_SERVICE_UNAVAILABLE = 503
HTTP_GATEWAY_TIMEOUT = 504
HTTP_SUCCESS_MIN = 200
HTTP_SUCCESS_LIMIT = 300
RETRYABLE_STATUS_CODES = frozenset({HTTP_TOO_MANY_REQUESTS, HTTP_SERVICE_UNAVAILABLE, HTTP_GATEWAY_TIMEOUT})
API_VERSION = re.compile(r"^\d{4}-\d{2}-\d{2}(?:~(?:beta|experimental))?$")
PATH_PARAMETER = re.compile(r"\{([^{}]+)\}")
SENSITIVE_KEY = re.compile(
    r"(?:^|[-_])(api[-_]?key|authorization|credential|password|secret|token)(?:$|[-_])",
    re.IGNORECASE,
)


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


def sanitize_base_url(value: str) -> str:
    """Validate and normalize a region-specific Snyk REST base URL."""
    base_url = value.strip().rstrip("/")
    parsed = parse.urlsplit(base_url)
    if parsed.scheme.lower() != "https" or not parsed.netloc:
        raise SnykCliError("Snyk REST base URL must be an absolute HTTPS URL.")
    if parsed.username is not None or parsed.password is not None:
        raise SnykCliError("Snyk REST base URL must not contain credentials.")
    if parsed.query or parsed.fragment:
        raise SnykCliError("Snyk REST base URL must not contain a query or fragment.")
    if not parsed.path.rstrip("/").endswith("/rest"):
        raise SnykCliError("Snyk REST base URL must end with /rest.")
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


def resolve_context(arguments: argparse.Namespace) -> SnykContext:
    """Resolve the selected region, version, token, and authentication scheme."""
    token, token_env_name = resolve_token(as_string_list(arguments.token_envs))
    return SnykContext(
        api_version=validate_api_version(str(arguments.api_version)),
        auth_scheme=str(arguments.auth_scheme),
        base_url=sanitize_base_url(str(arguments.base_url)),
        token=token,
        token_env_name=token_env_name,
    )


def response_payload(data: bytes, content_type: str, *, source: str) -> JsonValue:
    """Decode JSON or preserve bounded external text."""
    if "json" in content_type.lower() or not content_type:
        try:
            return cast("JsonValue", json.loads(data.decode("utf-8")))
        except (UnicodeDecodeError, json.JSONDecodeError) as exception:
            raise SnykCliError(f"{source} returned malformed JSON.") from exception
    return data.decode("utf-8", errors="replace")[:MAX_RESPONSE_TEXT]


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
    if (parsed.scheme.lower(), parsed.netloc.lower()) != (base.scheme.lower(), base.netloc.lower()):
        raise SnykCliError("OpenAPI specification origin must match the selected Snyk region.")
    if not parsed.path.startswith(f"{base.path.rstrip('/')}/openapi/"):
        raise SnykCliError("OpenAPI specification must remain under the selected /rest/openapi path.")
    return value.strip()


def get_json(url: str, *, timeout: float, source: str) -> JsonValue:
    """Fetch public JSON without redirects."""
    opener = request.build_opener(NoRedirectHandler())
    try:
        with opener.open(request.Request(url, headers={"Accept": "application/json"}), timeout=timeout) as response:  # noqa: S310  # URL validated by caller.
            return response_payload(response.read(), response.headers.get("Content-Type", ""), source=source)
    except error.HTTPError as exception:
        try:
            raise SnykCliError(f"{source} request failed with HTTP {exception.code}.") from exception
        finally:
            exception.close()
    except error.URLError as exception:
        raise SnykCliError(f"{source} request failed: {exception.reason}") from exception


def load_openapi(arguments: argparse.Namespace, context: SnykContext) -> tuple[dict[str, JsonValue], str]:
    """Load a local or live Snyk OpenAPI JSON document."""
    spec_file = cast("Path | None", arguments.spec_file)
    if spec_file is not None:
        try:
            payload = cast("JsonValue", json.loads(spec_file.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError) as exception:
            raise SnykCliError(f"Could not parse OpenAPI JSON file: {spec_file}") from exception
        source = str(spec_file)
    else:
        source = validate_spec_url(optional_text(arguments.spec_url) or spec_url(context), context)
        payload = get_json(source, timeout=float(arguments.timeout), source="Snyk OpenAPI")
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
        if label == "query" and SENSITIVE_KEY.search(name):
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
        return cast("JsonValue", json.loads(body_text))
    except json.JSONDecodeError as exception:
        raise SnykCliError("Request body must be valid JSON.") from exception


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
    if "\\" in endpoint or any(part == ".." for part in parsed_input.path.split("/")):
        raise SnykCliError("Endpoint must not contain backslashes or traversal segments.")
    if parsed_input.query or parsed_input.fragment:
        raise SnykCliError("Endpoint must not contain query or fragment; use --query.")
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
    """Redact sensitive keys and exact token occurrences."""
    if isinstance(value, dict):
        return {
            key: "<redacted>" if SENSITIVE_KEY.search(key) else redact_json(item, token) for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_json(item, token) for item in value]
    if isinstance(value, str) and token:
        return value.replace(token, "<redacted>")
    return value


def encode_url(url: str, query: dict[str, str]) -> str:
    """Append encoded query parameters."""
    parsed = parse.urlsplit(url)
    return parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parse.urlencode(query), ""))


def retry_delay(http_error: error.HTTPError, attempt: int) -> float:
    """Return a bounded delay from Retry-After or exponential fallback."""
    value = http_error.headers.get("Retry-After", "").strip()
    try:
        return min(max(float(value), 0.0), 60.0) if value else min(2.0**attempt, 30.0)
    except ValueError:
        return min(2.0**attempt, 30.0)


def send_request(context: SnykContext, plan: RequestPlan, arguments: argparse.Namespace) -> ApiResult:
    """Send one Snyk REST request with bounded retry behavior."""
    url = encode_url(plan.url, plan.query)
    headers = {
        "Accept": "application/vnd.api+json",
        "Content-Type": "application/vnd.api+json",
        "User-Agent": "codex-snyk-management/1",
    }
    if context.token is not None:
        headers["Authorization"] = f"{context.auth_scheme} {context.token}"
    body = None if plan.body is None else json.dumps(plan.body, separators=(",", ":")).encode()
    opener = request.build_opener(NoRedirectHandler())
    for attempt in range(int(arguments.retries) + 1):
        api_request = request.Request(  # noqa: S310  # build_plan region-locks the URL.
            url,
            data=body,
            headers=headers,
            method=plan.method,
        )
        try:
            with opener.open(api_request, timeout=float(arguments.timeout)) as response:  # URL is origin locked.
                return ApiResult(
                    payload=response_payload(
                        response.read(), response.headers.get("Content-Type", ""), source="Snyk REST API"
                    ),
                    status=int(response.status),
                    sunset=optional_text(response.headers.get("Sunset")),
                    url=url,
                )
        except error.HTTPError as exception:
            try:
                payload = response_payload(
                    exception.read(), exception.headers.get("Content-Type", ""), source="Snyk REST API"
                )
                if exception.code in RETRYABLE_STATUS_CODES and attempt < int(arguments.retries):
                    time.sleep(retry_delay(exception, attempt))
                    continue
                safe = redact_json(payload, context.token)
                raise SnykCliError(f"Snyk REST API returned HTTP {exception.code}: {json.dumps(safe)}") from exception
            finally:
                exception.close()
        except error.URLError as exception:
            if attempt < int(arguments.retries):
                time.sleep(min(2.0**attempt, 10.0))
                continue
            raise SnykCliError(f"Snyk REST request failed: {exception.reason}") from exception
    raise SnykCliError("Snyk REST retry loop ended unexpectedly.")


def pagination_plan(context: SnykContext, plan: RequestPlan, next_link: str) -> RequestPlan:
    """Validate and convert a JSON:API links.next value into the next request."""
    parsed = parse.urlsplit(next_link)
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
    query = dict(parse.parse_qsl(parsed.query, keep_blank_values=False))
    if any(SENSITIVE_KEY.search(name) for name in query):
        raise SnykCliError("Pagination link contains a token-like query parameter.")
    if query.get("version") != context.api_version:
        raise SnykCliError("Pagination link changed the selected API version.")
    return RequestPlan(body=None, method="GET", operation_id=plan.operation_id, query=query, url=absolute)


def paginated_request(context: SnykContext, plan: RequestPlan, arguments: argparse.Namespace) -> ApiResult:
    """Follow JSON:API links.next until it is absent or null."""
    if plan.method != "GET":
        raise SnykCliError("--paginate is supported only for GET requests.")
    merged: list[JsonValue] = []
    current = plan
    latest: ApiResult | None = None
    pages = 0
    for pages in range(1, int(arguments.max_pages) + 1):
        latest = send_request(context, current, arguments)
        payload = latest.payload
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            raise SnykCliError("Paginated response must contain a data array.")
        merged.extend(cast("list[JsonValue]", payload["data"]))
        links = payload.get("links")
        if not isinstance(links, dict):
            return ApiResult(
                payload={"data": merged, "links": {"next": None}, "meta": {"pages": pages}},
                status=latest.status,
                sunset=latest.sunset,
                url=latest.url,
            )
        next_link = links.get("next")
        if next_link is None:
            return ApiResult(
                payload={"data": merged, "links": {"next": None}, "meta": {"pages": pages}},
                status=latest.status,
                sunset=latest.sunset,
                url=latest.url,
            )
        if not isinstance(next_link, str) or not next_link:
            raise SnykCliError("links.next must be a non-empty string or null.")
        current = pagination_plan(context, plan, next_link)
    raise SnykCliError("Pagination reached --max-pages before links.next became null.")


def write_json(value: JsonValue) -> None:
    """Write deterministic JSON output."""
    _ = sys.stdout.write(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n")


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
    payload = get_json(url, timeout=float(arguments.timeout), source="Snyk OpenAPI versions")
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
    if not bool(arguments.json):
        _ = sys.stdout.write("[untrusted-snyk-data]\n")
    write_json(output)
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
    if float(arguments.timeout) <= 0:
        raise SnykCliError("--timeout must be greater than zero.")
    if hasattr(arguments, "max_pages") and int(arguments.max_pages) < 1:
        raise SnykCliError("--max-pages must be at least one.")
    if hasattr(arguments, "retries") and int(arguments.retries) < 0:
        raise SnykCliError("--retries must be zero or greater.")
    if hasattr(arguments, "send") and bool(arguments.send) and bool(arguments.dry_run):
        raise SnykCliError("--send and --dry-run are mutually exclusive.")


def main() -> int:
    """Run the Snyk management helper."""
    parser = build_parser()
    arguments = parser.parse_args()
    try:
        validate_arguments(arguments)
        handler = cast("Callable[[argparse.Namespace], int]", arguments.handler)
        return handler(arguments)
    except (SnykCliError, OSError) as exception:
        _ = sys.stderr.write(f"Error: {exception}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
