#!/usr/bin/env python3
"""Constrained StepSecurity REST inspection and request helper."""

from __future__ import annotations

import argparse
import json
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
from typing import TYPE_CHECKING, cast, override

if TYPE_CHECKING:
    from collections.abc import Callable
    from http.client import HTTPMessage
    from typing import IO

BASE_URL = "https://agent.api.stepsecurity.io/v1"
JSON_MEDIA_TYPE = "application/json"
HTTP_METHODS = {"delete", "get", "patch", "post", "put"}
READ_METHODS = {"GET", "HEAD", "OPTIONS"}
RETRY_STATUSES = {429, 502, 503, 504}
REDIRECT_STATUSES = {301, 302, 303, 307, 308}
SENSITIVE_NAME = re.compile(r"(?:api[-_]?key|authorization|cookie|credential|password|secret|token)", re.IGNORECASE)
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
    _ = sys.stdout.write(f"{json.dumps(value, indent=2, sort_keys=True)}\n")


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


def load_json_file(path: str, label: str) -> object:
    """Read and parse a UTF-8 JSON file."""
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as error:
        raise StepSecurityError(f"Could not read {label}: {error}") from error
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
            value = json.loads(inline)
        except json.JSONDecodeError as error:
            raise StepSecurityError(f"Invalid inline JSON body: {error}") from error
    else:
        return None
    return json.dumps(value, separators=(",", ":")).encode()


def safe_headers(headers: dict[str, str]) -> dict[str, str]:
    """Redact sensitive header values."""
    return {name: "<redacted>" if SENSITIVE_NAME.search(name) else value for name, value in headers.items()}


def redact(value: object) -> object:
    """Recursively redact credential-like response fields."""
    mapping = object_mapping(value)
    if mapping is not None:
        return {
            str(key): "<redacted>" if SENSITIVE_NAME.search(str(key)) else redact(item) for key, item in mapping.items()
        }
    items = object_list(value)
    if items is not None:
        return [redact(item) for item in items]
    return value


def parse_response(data: bytes, content_type: str) -> object:
    """Decode JSON when possible and bounded text otherwise."""
    text = data.decode("utf-8", errors="replace")
    if "json" in content_type.lower() or text.lstrip().startswith(("{", "[")):
        try:
            return redact(cast("object", json.loads(text)))
        except json.JSONDecodeError:
            pass
    return text[:100_000]


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
    if method not in READ_METHODS or http_error.code not in RETRY_STATUSES or attempt >= runtime.retries:
        return None
    retry_after = http_error.headers.get("Retry-After")
    delay = float(retry_after) if retry_after and retry_after.isdigit() else 2**attempt
    return min(delay, 30.0)


def http_error_message(http_error: urllib.error.HTTPError) -> str:
    """Build a bounded, redacted API error message."""
    payload = parse_response(http_error.read(), http_error.headers.get("Content-Type", ""))
    return f"HTTP {http_error.code}: {json.dumps(payload)}"


def send(
    method: str,
    url: str,
    headers: dict[str, str],
    body: bytes | None,
    runtime: RequestRuntime,
) -> tuple[int, dict[str, str], object]:
    """Send one request with bounded read retries and redirect validation."""
    opener = urllib.request.build_opener(NoRedirect())
    attempt = 0
    current_url = validated_url(url)
    while True:
        request = urllib.request.Request(  # noqa: S310  # validated_url origin-locks current_url.
            current_url,
            data=body,
            headers=headers,
            method=method,
        )
        try:
            with opener.open(request, timeout=runtime.timeout) as response:
                response_headers = dict(response.headers.items())
                return (
                    response.status,
                    response_headers,
                    parse_response(response.read(), response.headers.get("Content-Type", "")),
                )
        except urllib.error.HTTPError as error:
            redirected = redirect_target(current_url, error)
            if redirected is not None:
                current_url = redirected
                continue
            delay = retry_delay(method, error, attempt, runtime)
            if delay is not None:
                time.sleep(delay)
                attempt += 1
                continue
            raise StepSecurityError(http_error_message(error)) from error
        except urllib.error.URLError as error:
            raise StepSecurityError(f"Request failed: {error.reason}") from error


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
        "body": redact(json.loads(body)) if body is not None else None,
        "customer": context.customer,
        "headers": safe_headers(headers),
        "method": method,
        "organization": context.organization,
        "repository": context.repository,
        "url": url,
    }
    return plan, body


def next_link(payload: object) -> str | None:
    """Extract a JSON:API-style next link."""
    payload_mapping = object_mapping(payload)
    if payload_mapping is None:
        return None
    links = object_mapping(payload_mapping.get("links"))
    if links is None:
        return None
    candidate = links.get("next")
    if isinstance(candidate, str) and candidate:
        return candidate
    candidate_mapping = object_mapping(candidate)
    if candidate_mapping is not None:
        href = candidate_mapping.get("href")
        return href if isinstance(href, str) and href else None
    return None


def execute_request(arguments: argparse.Namespace) -> None:
    """Preview or execute a constrained request."""
    plan, body = request_plan(arguments)
    method = cast("str", plan["method"])
    if arguments.dry_run or (method not in READ_METHODS and not arguments.execute):
        emit({"executed": False, "request": plan})
        return
    headers = {
        "Accept": JSON_MEDIA_TYPE,
        "Authorization": f"Bearer {credential()}",
        "User-Agent": "codex-stepsecurity-management/1",
        **parse_pairs(arguments.header, "--header"),
    }
    if body is not None:
        headers["Content-Type"] = JSON_MEDIA_TYPE

    pages: list[dict[str, object]] = []
    url = cast("str", plan["url"])
    runtime = RequestRuntime(retries=arguments.retries, timeout=arguments.timeout)
    for page_number in range(1, arguments.max_pages + 1):
        status, response_headers, payload = send(method, url, headers, body, runtime)
        pages.append(
            {
                "body": payload,
                "page": page_number,
                "status": status,
                "request_id": response_headers.get("X-Request-Id") or response_headers.get("X-Request-ID"),
            }
        )
        candidate = next_link(payload) if arguments.paginate else None
        if not candidate:
            break
        if method not in READ_METHODS:
            raise StepSecurityError("Pagination is available only for read requests")
        url = validated_url(urllib.parse.urljoin(url, candidate))
        body = None
    emit({"executed": True, "pages": pages})


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
    if getattr(arguments, "max_pages", 1) < 1:
        raise StepSecurityError("--max-pages must be at least 1")
    if getattr(arguments, "timeout", 1.0) <= 0:
        raise StepSecurityError("--timeout must be greater than zero")
    if getattr(arguments, "retries", 0) < 0:
        raise StepSecurityError("--retries cannot be negative")
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
