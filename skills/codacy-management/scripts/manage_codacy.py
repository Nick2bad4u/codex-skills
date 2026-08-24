#!/usr/bin/env python
# Copyright (c) 2026 Nick2bad4u
"""Inspect Codacy API operations and make origin-locked v3 requests."""

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

DEFAULT_BASE_URL = "https://api.codacy.com/api/v3"
DEFAULT_TOKEN_ENVS = ("CODACY_API_TOKEN",)
DEFAULT_TIMEOUT = 30.0
DEFAULT_MAX_PAGES = 100
DEFAULT_RETRIES = 2
MAX_PAGE_LIMIT = 1000
MAX_UNTRUSTED_TEXT = 1000
MIN_REMOTE_PATH_PARTS = 2
MATCHING_QUOTE_MIN_LENGTH = 2
HTTP_TOO_MANY_REQUESTS = 429
HTTP_SERVICE_UNAVAILABLE = 503
HTTP_GATEWAY_TIMEOUT = 504
RETRYABLE_STATUS_CODES = frozenset({HTTP_TOO_MANY_REQUESTS, HTTP_SERVICE_UNAVAILABLE, HTTP_GATEWAY_TIMEOUT})
ENVIRONMENT_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
OPENAPI_PATH = re.compile(r"^  (/[^:]+):\s*$")
OPENAPI_METHOD = re.compile(r"^    (get|post|put|patch|delete):\s*$", re.IGNORECASE)
OPENAPI_OPERATION_ID = re.compile(r"^      operationId:\s*(.+?)\s*$")
OPENAPI_SUMMARY = re.compile(r"^      summary:\s*(.+?)\s*$")
PATH_PARAMETER = re.compile(r"\{([^{}]+)\}")
SENSITIVE_KEY = re.compile(r"(?:^|[-_])(api[-_]?key|authorization|password|secret|token)(?:$|[-_])", re.IGNORECASE)


class CodacyCliError(RuntimeError):
    """Report a safe, user-facing helper error."""


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
    """Validate and normalize a token-bearing Codacy v3 base URL."""
    base_url = value.strip().rstrip("/")
    parsed = parse.urlsplit(base_url)
    if parsed.scheme.lower() != "https" or not parsed.netloc:
        raise CodacyCliError("Codacy API base URL must be an absolute HTTPS URL.")
    if parsed.username is not None or parsed.password is not None:
        raise CodacyCliError("Codacy API base URL must not contain credentials.")
    if parsed.query or parsed.fragment:
        raise CodacyCliError("Codacy API base URL must not contain a query or fragment.")
    return base_url


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


def resolve_context(arguments: argparse.Namespace) -> CodacyContext:
    """Resolve local repository, slug, base URL, and optional token."""
    repository_root = cast("Path", arguments.repo)
    token, token_env_name = resolve_token(cast("list[str]", arguments.token_envs))
    return CodacyContext(
        base_url=sanitize_base_url(str(arguments.base_url)),
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
        return spec_file.read_text(encoding="utf-8"), str(spec_file)

    spec_url = optional_text(arguments.spec_url) or derived_spec_url(context.base_url)
    parsed = parse.urlsplit(spec_url)
    if parsed.scheme.lower() != "https" or not parsed.netloc:
        raise CodacyCliError("OpenAPI specification URL must be an absolute HTTPS URL.")
    if parsed.username is not None or parsed.password is not None:
        raise CodacyCliError("OpenAPI specification URL must not contain credentials.")
    if parsed.fragment:
        raise CodacyCliError("OpenAPI specification URL must not contain a fragment.")
    for name, _value in parse.parse_qsl(parsed.query, keep_blank_values=True):
        if SENSITIVE_KEY.search(name):
            raise CodacyCliError(f"Refusing token-like OpenAPI query parameter: {name}")
    try:
        spec_request = request.Request(  # noqa: S310  # URL is validated as absolute HTTPS above.
            spec_url,
            headers={"User-Agent": "codacy-management-skill/1"},
        )
        spec_opener = request.build_opener(NoRedirectHandler())
        with spec_opener.open(spec_request, timeout=float(arguments.timeout)) as response:
            return response.read().decode("utf-8"), spec_url
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
    return mark_untrusted_text(str(exception))


def mark_untrusted_text(value: str) -> str:
    """Normalize and bound external text."""
    cleaned = " ".join(value.split())[:MAX_UNTRUSTED_TEXT]
    return f"[untrusted-codacy-text] {cleaned or 'no additional details'}"


def parse_pairs(values: list[str], label: str, *, reject_sensitive: bool = False) -> dict[str, str]:
    """Parse repeatable name=value arguments."""
    result: dict[str, str] = {}
    for value in values:
        name, separator, item = value.partition("=")
        name = name.strip()
        if separator == "" or not name or not item:
            raise CodacyCliError(f"{label} values must use non-empty name=value syntax: {value}")
        if name in result:
            raise CodacyCliError(f"Duplicate {label} name: {name}")
        if reject_sensitive and SENSITIVE_KEY.search(name):
            raise CodacyCliError(f"Refusing token-like {label} parameter: {name}")
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
            raise CodacyCliError(f"Missing path parameter --path {name}=<value>.")
        return parse.quote(value, safe="")

    return PATH_PARAMETER.sub(replacement, endpoint)


def same_origin_and_base_path(base_url: str, candidate_url: str) -> bool:
    """Return whether an absolute endpoint stays inside the configured v3 base."""
    base = parse.urlsplit(base_url)
    candidate = parse.urlsplit(candidate_url)
    base_origin = (base.scheme.lower(), base.hostname, base.port)
    candidate_origin = (candidate.scheme.lower(), candidate.hostname, candidate.port)
    base_path = base.path.rstrip("/")
    candidate_path = candidate.path.rstrip("/")
    return candidate_origin == base_origin and (
        candidate_path == base_path or candidate_path.startswith(f"{base_path}/")
    )


def validate_endpoint_url(endpoint_url: str) -> None:
    """Reject URL components that can leak credentials or escape the API path."""
    parsed = parse.urlsplit(endpoint_url)
    if parsed.username is not None or parsed.password is not None:
        raise CodacyCliError("Codacy endpoint must not contain URL credentials.")
    if parsed.fragment:
        raise CodacyCliError("Codacy endpoint must not contain a fragment.")
    for segment in parsed.path.split("/"):
        decoded_segment = parse.unquote(segment)
        if decoded_segment in {".", ".."} or "\\" in decoded_segment:
            raise CodacyCliError("Codacy endpoint must not contain traversal path segments.")
    for name, _value in parse.parse_qsl(parsed.query, keep_blank_values=True):
        if SENSITIVE_KEY.search(name):
            raise CodacyCliError(f"Refusing token-like endpoint query parameter: {name}")


def build_url(base_url: str, endpoint: str, query: dict[str, str]) -> str:
    """Build an origin-locked request URL."""
    validate_endpoint_url(endpoint)
    parsed_endpoint = parse.urlsplit(endpoint)
    if parsed_endpoint.scheme:
        if not same_origin_and_base_path(base_url, endpoint):
            raise CodacyCliError("Absolute endpoint must match the configured HTTPS origin and API base path.")
        base_endpoint = endpoint
    else:
        if not endpoint.startswith("/"):
            raise CodacyCliError("Relative endpoint must start with '/'.")
        base_endpoint = f"{base_url}{endpoint}"

    parsed = parse.urlsplit(base_endpoint)
    combined_query = dict(parse.parse_qsl(parsed.query, keep_blank_values=True))
    combined_query.update(query)
    return parse.urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, parse.urlencode(combined_query, doseq=False), "")
    )


def load_json_value(text: str, source: str) -> JsonValue:
    """Parse a JSON value with a safe source label."""
    try:
        return cast("JsonValue", json.loads(text))
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
        return load_json_value(body_file.read_text(encoding="utf-8"), str(body_file))
    return None


def redact_json(value: JsonValue, token: str | None = None) -> JsonValue:
    """Redact likely secret fields and the active token from JSON output."""
    if isinstance(value, dict):
        return {
            key: "<redacted>" if SENSITIVE_KEY.search(key) else redact_json(item, token) for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_json(item, token) for item in value]
    if isinstance(value, str) and token and token in value:
        return value.replace(token, "<redacted>")
    return value


def read_error_body(http_error: error.HTTPError, token: str | None) -> str:
    """Read and redact a bounded HTTP error body."""
    try:
        raw = http_error.read(MAX_UNTRUSTED_TEXT).decode("utf-8", errors="replace")
    except OSError:
        raw = str(http_error.reason)
    if token:
        raw = raw.replace(token, "<redacted>")
    return mark_untrusted_text(raw)


def retry_delay(http_error: error.HTTPError, attempt: int, base_delay: float) -> float:
    """Return a bounded retry delay, respecting integer Retry-After values."""
    retry_after = http_error.headers.get("Retry-After")
    if retry_after is not None:
        try:
            return min(max(float(retry_after), 0.0), 60.0)
        except ValueError:
            pass
    return min(base_delay * (2.0**attempt), 60.0)


def send_request(
    context: CodacyContext,
    plan: RequestPlan,
    *,
    query: dict[str, str],
    runtime: RequestRuntime,
) -> ApiResult:
    """Send one Codacy request with conservative transient retries."""
    url = build_url(context.base_url, plan.endpoint, query)
    headers = {"Accept": "application/json", "User-Agent": "codacy-management-skill/1"}
    if context.token is not None:
        headers["api-token"] = context.token
    body_bytes = None
    if plan.body is not None:
        headers["Content-Type"] = "application/json"
        body_bytes = json.dumps(plan.body, separators=(",", ":")).encode("utf-8")

    for attempt in range(runtime.retries + 1):
        api_request = request.Request(  # noqa: S310  # build_url enforces the configured HTTPS origin and base.
            url,
            data=body_bytes,
            headers=headers,
            method=plan.method,
        )
        try:
            api_opener = request.build_opener(NoRedirectHandler())
            with api_opener.open(api_request, timeout=runtime.timeout) as response:
                raw = response.read()
                status = int(response.status)
                if not raw:
                    payload: JsonValue = None
                else:
                    try:
                        payload = cast("JsonValue", json.loads(raw.decode("utf-8")))
                    except UnicodeError, json.JSONDecodeError:
                        text = raw.decode("utf-8", errors="replace")
                        if context.token:
                            text = text.replace(context.token, "<redacted>")
                        payload = mark_untrusted_text(text)
                return ApiResult(payload=payload, status=status, url=url)
        except error.HTTPError as exception:
            try:
                if exception.code in RETRYABLE_STATUS_CODES and attempt < runtime.retries:
                    time.sleep(retry_delay(exception, attempt, runtime.retry_base_delay))
                    continue
                details = read_error_body(exception, context.token)
                raise CodacyCliError(f"Codacy API returned HTTP {exception.code}: {details}") from exception
            finally:
                exception.close()
        except error.URLError as exception:
            raise CodacyCliError(f"Unable to reach Codacy: {safe_exception_text(exception.reason)}") from exception
    raise CodacyCliError("Codacy request retry loop ended unexpectedly.")


def json_object(value: JsonValue, label: str) -> dict[str, JsonValue]:
    """Require a JSON object."""
    if not isinstance(value, dict):
        raise CodacyCliError(f"{label} must be a JSON object.")
    return value


def paginate_request(
    context: CodacyContext,
    plan: RequestPlan,
    *,
    max_pages: int,
    runtime: RequestRuntime,
) -> ApiResult:
    """Follow Codacy cursor pagination and merge data arrays."""
    query = dict(plan.query)
    all_data: list[JsonValue] = []
    seen_cursors: set[str] = set()
    results: list[ApiResult] = []
    payloads: list[dict[str, JsonValue]] = []

    for _page_number in range(1, max_pages + 1):
        result = send_request(
            context,
            plan,
            query=query,
            runtime=runtime,
        )
        payload = json_object(result.payload, "Paginated Codacy response")
        data = payload.get("data")
        if not isinstance(data, list):
            raise CodacyCliError("Paginated Codacy response must contain a data array.")
        all_data.extend(data)
        results.append(result)
        payloads.append(payload)

        pagination_value = payload.get("pagination")
        if not isinstance(pagination_value, dict):
            break
        cursor_value = pagination_value.get("cursor")
        if not isinstance(cursor_value, str) or not cursor_value:
            break
        if cursor_value in seen_cursors:
            raise CodacyCliError("Codacy returned a repeated pagination cursor; refusing an infinite loop.")
        seen_cursors.add(cursor_value)
        query["cursor"] = cursor_value
    else:
        raise CodacyCliError(f"Codacy pagination exceeded --max-pages {max_pages}.")

    if not results or not payloads:
        raise CodacyCliError("Codacy pagination returned no pages.")
    first_result = results[0]
    merged = dict(payloads[-1])
    merged["data"] = all_data
    merged["paginationFetch"] = {"fetchedCount": len(all_data), "fetchedPages": len(seen_cursors) + 1}
    return ApiResult(payload=merged, status=first_result.status, url=first_result.url)


def request_plan(arguments: argparse.Namespace, context: CodacyContext) -> RequestPlan:
    """Resolve an endpoint or live OpenAPI operation into a request plan."""
    endpoint = optional_text(arguments.endpoint)
    operation_id = optional_text(arguments.operation_id)
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
            raise CodacyCliError(f"OpenAPI operationId must resolve exactly once: {operation_id}")
        operation = matches[0]
        if method_explicit and method != operation.method:
            raise CodacyCliError(
                f"--method {method} conflicts with OpenAPI operation {operation_id} method {operation.method}."
            )
        method = operation.method
        endpoint = operation.path

    path_values = parse_pairs(cast("list[str]", arguments.path_values), "path")
    query = parse_pairs(cast("list[str]", arguments.query), "query", reject_sensitive=True)
    expanded_endpoint = expand_endpoint(cast("str", endpoint), context, path_values)
    body = load_body(arguments)
    if method == "GET" and body is not None:
        raise CodacyCliError("GET requests must not include a JSON body.")
    return RequestPlan(body=body, endpoint=expanded_endpoint, method=method, operation_id=operation_id, query=query)


def plan_preview(context: CodacyContext, plan: RequestPlan, *, paginate: bool) -> dict[str, JsonValue]:
    """Build a redacted request preview."""
    return {
        "body": redact_json(plan.body, context.token),
        "dryRun": True,
        "headers": {"Accept": "application/json", "api-token": "<redacted>" if context.token else "<absent>"},
        "method": plan.method,
        "operationId": plan.operation_id,
        "paginate": paginate,
        "url": build_url(context.base_url, plan.endpoint, plan.query),
    }


def context_output(context: CodacyContext) -> dict[str, JsonValue]:
    """Build safe local context output."""
    slug: JsonValue = asdict(context.slug) if context.slug is not None else None
    return {
        "baseUrl": context.base_url,
        "repositoryRoot": str(context.repository_root),
        "slug": slug,
        "token": "configured" if context.token is not None else "absent",
        "tokenEnvironment": context.token_env_name,
    }


def write_json(value: JsonValue) -> None:
    """Write deterministic JSON."""
    _ = sys.stdout.write(f"{json.dumps(value, indent=2, sort_keys=True)}\n")


def handle_context(arguments: argparse.Namespace) -> int:
    """Print local target and token metadata."""
    context = resolve_context(arguments)
    output = context_output(context)
    if arguments.json:
        write_json(output)
    else:
        for key, value in output.items():
            _ = sys.stdout.write(f"{key}: {json.dumps(value, sort_keys=True)}\n")
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

    if arguments.json:
        write_json(
            {
                "meta": {"source": source, "untrustedExternalData": arguments.spec_file is None},
                "operations": [cast("JsonValue", asdict(operation)) for operation in operations],
            }
        )
    else:
        _ = sys.stdout.write(f"Codacy operations from {source}: {len(operations)}\n")
        for operation in operations:
            summary_suffix = f" - {operation.summary}" if operation.summary else ""
            _ = sys.stdout.write(f"{operation.method:6} {operation.operation_id:45} {operation.path}{summary_suffix}\n")
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
    if arguments.json:
        write_json(output)
    else:
        _ = sys.stdout.write("[untrusted-codacy-data]\n")
        write_json(output)
    return 0


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
    _ = parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="Request timeout in seconds.")


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
    _ = api_request.add_argument("--max-pages", type=int, default=DEFAULT_MAX_PAGES)
    _ = api_request.add_argument("--retries", type=int, default=DEFAULT_RETRIES)
    _ = api_request.add_argument("--retry-delay", type=float, default=1.0)
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
    if hasattr(arguments, "timeout") and float(arguments.timeout) <= 0:
        raise CodacyCliError("--timeout must be greater than zero.")
    if hasattr(arguments, "max_pages") and int(arguments.max_pages) < 1:
        raise CodacyCliError("--max-pages must be at least one.")
    if hasattr(arguments, "retries") and int(arguments.retries) < 0:
        raise CodacyCliError("--retries must be zero or greater.")
    if hasattr(arguments, "retry_delay") and float(arguments.retry_delay) < 0:
        raise CodacyCliError("--retry-delay must be zero or greater.")
    if hasattr(arguments, "send") and bool(arguments.send) and bool(arguments.dry_run):
        raise CodacyCliError("--send and --dry-run are mutually exclusive.")


def main() -> int:
    """Run the Codacy helper."""
    parser = build_parser()
    arguments = parser.parse_args()
    try:
        validate_numeric_arguments(arguments)
        handler = cast("Callable[[argparse.Namespace], int]", arguments.handler)
        return handler(arguments)
    except (CodacyCliError, OSError) as exception:
        _ = sys.stderr.write(f"Error: {exception}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
