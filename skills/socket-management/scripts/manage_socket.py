#!/usr/bin/env python
# Copyright (c) 2026 Nick2bad4u
"""Inspect Socket OpenAPI operations and make origin-locked v0 requests."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
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

DEFAULT_BASE_URL = "https://api.socket.dev/v0"
DEFAULT_SPEC_URL = "https://api.socket.dev/v0/openapi"
DEFAULT_TOKEN_ENVS = ("SOCKET_SECURITY_API_TOKEN", "SOCKET_API_TOKEN")
DEFAULT_TIMEOUT = 30.0
DEFAULT_RETRIES = 2
DEFAULT_MAX_PAGES = 100
MAX_RESPONSE_TEXT = 2000
HTTP_TOO_MANY_REQUESTS = 429
HTTP_SERVICE_UNAVAILABLE = 503
HTTP_GATEWAY_TIMEOUT = 504
RETRYABLE_STATUS_CODES = frozenset({HTTP_TOO_MANY_REQUESTS, HTTP_SERVICE_UNAVAILABLE, HTTP_GATEWAY_TIMEOUT})
ENVIRONMENT_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
PATH_PARAMETER = re.compile(r"\{([^{}]+)\}")
SENSITIVE_KEY = re.compile(
    r"(?:^|[-_])(api[-_]?key|authorization|credential|password|secret|token)(?:$|[-_])",
    re.IGNORECASE,
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


def optional_text(value: object) -> str | None:
    """Return a stripped optional string."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


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
    """Validate and normalize a token-bearing Socket v0 base URL."""
    base_url = value.strip().rstrip("/")
    parsed = parse.urlsplit(base_url)
    if parsed.scheme.lower() != "https" or not parsed.netloc:
        raise SocketCliError("Socket API base URL must be an absolute HTTPS URL.")
    if parsed.username is not None or parsed.password is not None:
        raise SocketCliError("Socket API base URL must not contain credentials.")
    if parsed.query or parsed.fragment:
        raise SocketCliError("Socket API base URL must not contain a query or fragment.")
    if not parsed.path.rstrip("/").endswith("/v0"):
        raise SocketCliError("Socket API base URL must end with /v0.")
    return base_url


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
        if ENVIRONMENT_NAME.fullmatch(name) is None:
            raise SocketCliError(f"Invalid token environment variable name: {name}")
        token = os.environ.get(name, "").strip()
        if token:
            return token, name
    return None, None


def resolve_context(arguments: argparse.Namespace) -> SocketContext:
    """Resolve repository, target, base URL, and optional token."""
    repository_root = cast("Path", arguments.repo)
    detected: RepositorySlug | None = None
    remote_url = run_git(repository_root, "remote", "get-url", "origin")
    if remote_url is not None:
        detected = parse_github_remote(remote_url)
    organization = optional_text(arguments.org) or (detected.organization if detected else None)
    repository = optional_text(arguments.repository) or (detected.repository if detected else None)
    token, token_env_name = resolve_token(cast("list[str]", arguments.token_envs))
    return SocketContext(
        base_url=sanitize_base_url(str(arguments.base_url)),
        organization=organization,
        repository=repository,
        repository_root=repository_root,
        token=token,
        token_env_name=token_env_name,
    )


def validate_spec_url(value: str, context: SocketContext) -> str:
    """Validate an HTTPS OpenAPI URL on the configured Socket origin."""
    parsed = parse.urlsplit(value.strip())
    base = parse.urlsplit(context.base_url)
    if parsed.scheme.lower() != "https" or not parsed.netloc:
        raise SocketCliError("OpenAPI specification URL must be absolute HTTPS.")
    if parsed.username is not None or parsed.password is not None:
        raise SocketCliError("OpenAPI specification URL must not contain credentials.")
    if parsed.query or parsed.fragment:
        raise SocketCliError("OpenAPI specification URL must not contain a query or fragment.")
    if (parsed.scheme.lower(), parsed.netloc.lower()) != (base.scheme.lower(), base.netloc.lower()):
        raise SocketCliError("OpenAPI specification origin must match the configured Socket API origin.")
    return value.strip()


def decode_json(data: bytes, *, source: str) -> JsonValue:
    """Decode a JSON response with a bounded safe error."""
    try:
        return cast("JsonValue", json.loads(data.decode("utf-8")))
    except (UnicodeDecodeError, json.JSONDecodeError) as exception:
        raise SocketCliError(f"Expected JSON from {source}.") from exception


def load_openapi(arguments: argparse.Namespace, context: SocketContext) -> tuple[dict[str, JsonValue], str]:
    """Load a local or live Socket OpenAPI JSON document."""
    spec_file = cast("Path | None", arguments.spec_file)
    if spec_file is not None:
        try:
            payload = cast("JsonValue", json.loads(spec_file.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError) as exception:
            raise SocketCliError(f"Could not parse OpenAPI JSON file: {spec_file}") from exception
        if not isinstance(payload, dict):
            raise SocketCliError("OpenAPI document root must be an object.")
        return payload, str(spec_file)

    spec_url = validate_spec_url(optional_text(arguments.spec_url) or DEFAULT_SPEC_URL, context)
    opener = request.build_opener(NoRedirectHandler())
    try:
        spec_request = request.Request(  # noqa: S310  # validate_spec_url locks this to the Socket origin.
            spec_url,
            headers={"Accept": "application/json"},
        )
        with opener.open(
            spec_request,
            timeout=float(arguments.timeout),
        ) as response:
            payload = decode_json(response.read(), source="Socket OpenAPI endpoint")
    except error.HTTPError as exception:
        raise SocketCliError(f"OpenAPI request failed with HTTP {exception.code}.") from exception
    except error.URLError as exception:
        raise SocketCliError(f"OpenAPI request failed: {exception.reason}") from exception
    if not isinstance(payload, dict):
        raise SocketCliError("OpenAPI document root must be an object.")
    return payload, spec_url


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
            operation = path_item.get(method)
            if not isinstance(operation, dict):
                continue
            operation_id = operation.get("operationId")
            if not isinstance(operation_id, str) or not operation_id:
                continue
            summary_value = operation.get("summary")
            summary = summary_value if isinstance(summary_value, str) else ""
            tags_value = operation.get("tags")
            tags = tuple(item for item in tags_value if isinstance(item, str)) if isinstance(tags_value, list) else ()
            operations.append(
                OpenApiOperation(
                    deprecated=operation.get("deprecated") is True,
                    method=method.upper(),
                    operation_id=operation_id,
                    path=path_name,
                    summary=summary,
                    tags=tags,
                )
            )
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
        if label == "query" and SENSITIVE_KEY.search(name):
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
        return cast("JsonValue", json.loads(body_text))
    except json.JSONDecodeError as exception:
        raise SocketCliError("Request body must be valid JSON.") from exception


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
    if "\\" in endpoint or any(part == ".." for part in endpoint.split("/")):
        raise SocketCliError("Endpoint must not contain backslashes or traversal segments.")
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
        raise SocketCliError("Absolute endpoint origin must match the configured Socket API origin.")
    base_path = base.path.rstrip("/")
    if parsed.path != base_path and not parsed.path.startswith(f"{base_path}/"):
        raise SocketCliError("Absolute endpoint must remain under the configured Socket /v0 base path.")
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
        endpoint = fill_path(operation.path, parse_pairs(cast("list[str]", arguments.path_values), label="path"))
    elif cast("list[str]", arguments.path_values):
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
        query=parse_pairs(cast("list[str]", arguments.query), label="query"),
        url=url,
    )


def redact_json(value: JsonValue, token: str | None) -> JsonValue:
    """Redact sensitive response fields and exact token occurrences."""
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
    """Append encoded query parameters to a validated URL."""
    parsed = parse.urlsplit(url)
    return parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parse.urlencode(query), ""))


def parse_retry_after(http_error: error.HTTPError, attempt: int) -> float:
    """Return a bounded delay from Retry-After or exponential fallback."""
    value = http_error.headers.get("Retry-After", "").strip()
    try:
        return min(max(float(value), 0.0), 60.0) if value else min(2.0**attempt, 30.0)
    except ValueError:
        return min(2.0**attempt, 30.0)


def response_payload(data: bytes, content_type: str) -> JsonValue:
    """Decode JSON or retain bounded external response text."""
    if "json" in content_type.lower():
        return decode_json(data, source="Socket API")
    text = data.decode("utf-8", errors="replace")
    return text[:MAX_RESPONSE_TEXT]


def send_request(
    context: SocketContext, plan: RequestPlan, *, query: dict[str, str], arguments: argparse.Namespace
) -> ApiResult:
    """Send one authenticated request with bounded retry behavior."""
    url = encode_url(plan.url, query)
    headers = {"Accept": "application/json", "User-Agent": "codex-socket-management/1"}
    if context.token is not None:
        headers["Authorization"] = f"Bearer {context.token}"
    body = None if plan.body is None else json.dumps(plan.body, separators=(",", ":")).encode()
    if body is not None:
        headers["Content-Type"] = "application/json"
    opener = request.build_opener(NoRedirectHandler())
    retries = int(arguments.retries)
    for attempt in range(retries + 1):
        api_request = request.Request(  # noqa: S310  # build_plan origin-locks the URL.
            url,
            data=body,
            headers=headers,
            method=plan.method,
        )
        try:
            with opener.open(api_request, timeout=float(arguments.timeout)) as response:  # URL is origin locked.
                payload = response_payload(response.read(), response.headers.get("Content-Type", ""))
                return ApiResult(payload=payload, status=int(response.status), url=url)
        except error.HTTPError as exception:
            data = exception.read()
            payload = response_payload(data, exception.headers.get("Content-Type", ""))
            if exception.code in RETRYABLE_STATUS_CODES and attempt < retries:
                time.sleep(parse_retry_after(exception, attempt))
                continue
            safe_payload = redact_json(payload, context.token)
            raise SocketCliError(
                f"Socket API returned HTTP {exception.code}: {json.dumps(safe_payload)}"
            ) from exception
        except error.URLError as exception:
            if attempt < retries:
                time.sleep(min(2.0**attempt, 10.0))
                continue
            raise SocketCliError(f"Socket API request failed: {exception.reason}") from exception
    raise SocketCliError("Socket API retry loop ended unexpectedly.")


def paginated_request(context: SocketContext, plan: RequestPlan, arguments: argparse.Namespace) -> ApiResult:
    """Follow Socket items/endCursor pages until the cursor is explicitly null."""
    if plan.method != "GET":
        raise SocketCliError("--paginate is supported only for GET requests.")
    query = dict(plan.query)
    merged: list[JsonValue] = []
    latest: ApiResult | None = None
    for page_number in range(1, int(arguments.max_pages) + 1):
        latest = send_request(context, plan, query=query, arguments=arguments)
        payload = latest.payload
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
                status=latest.status,
                url=latest.url,
            )
        if not isinstance(cursor, str) or not cursor:
            raise SocketCliError("endCursor must be a non-empty string or null.")
        query["startAfterCursor"] = cursor
    raise SocketCliError("Pagination reached --max-pages before endCursor became null.")


def write_json(value: JsonValue) -> None:
    """Write deterministic JSON output."""
    _ = sys.stdout.write(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n")


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
    if not bool(arguments.json):
        _ = sys.stdout.write("[untrusted-socket-data]\n")
    write_json(output)
    return 0


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
    if hasattr(arguments, "timeout") and float(arguments.timeout) <= 0:
        raise SocketCliError("--timeout must be greater than zero.")
    if hasattr(arguments, "max_pages") and int(arguments.max_pages) < 1:
        raise SocketCliError("--max-pages must be at least one.")
    if hasattr(arguments, "retries") and int(arguments.retries) < 0:
        raise SocketCliError("--retries must be zero or greater.")
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
