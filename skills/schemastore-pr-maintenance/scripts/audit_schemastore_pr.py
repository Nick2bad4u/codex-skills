#!/usr/bin/env python
# Copyright (c) 2026 Nick2bad4u
"""Summarize SchemaStore PR surfaces and targeted validation commands."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Final, TextIO, cast

DEFAULT_BASE_REFS: Final = ("origin/master", "origin/main")
GIT_COMMIT_PATTERN: Final = re.compile(r"[0-9a-f]{40}")
SCHEMA_FILENAME_PATTERN: Final = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\.json")
SCHEMASTORE_PUBLIC_CATALOG_URL_BASE: Final = "https://www.schemastore.org/"
SCHEMASTORE_RAW_CATALOG_URL_BASE: Final = (
    "https://raw.githubusercontent.com/SchemaStore/schemastore/master/src/schemas/json/"
)
SCHEMASTORE_LOCAL_CATALOG_URL_BASES: Final = (
    SCHEMASTORE_PUBLIC_CATALOG_URL_BASE,
    SCHEMASTORE_RAW_CATALOG_URL_BASE,
)
CRITICAL_EXACT_PATHS: Final = {
    "src/api/json/catalog.json",
    "src/schema-validation.jsonc",
}
CRITICAL_PREFIXES: Final = (
    "src/schemas/json/",
    "src/test/",
    "src/negative_test/",
)
EXIT_AUDIT_FINDINGS: Final = 1
EXIT_OPERATIONAL_ERROR: Final = 2
ASCII_CONTROL_END: Final = 32
ASCII_DELETE: Final = 127
PORCELAIN_RECORD_MIN_LENGTH: Final = 4


@dataclass(frozen=True)
class AuditDiagnostic:
    """A stable machine-readable operational failure."""

    code: str
    message: str
    path: str | None = None


class AuditError(Exception):
    """Stop an audit with one controlled diagnostic."""

    def __init__(self, diagnostic: AuditDiagnostic) -> None:
        """Initialize the exception from its stable diagnostic."""
        super().__init__(diagnostic.message)
        self.diagnostic = diagnostic


@dataclass(frozen=True)
class GitDiscovery:
    """Changed paths discovered from committed and uncommitted Git state."""

    baseline_ref: str | None
    committed_files: list[str]
    uncommitted_files: list[str]


@dataclass(frozen=True)
class ValidationConfig:
    """Relevant structural data from schema-validation.jsonc."""

    coverage: dict[str, bool]
    missing_catalog_urls: set[str]
    skip_tests: set[str]


@dataclass(frozen=True)
class SchemaStorePrAudit:
    """Read-only SchemaStore pull request audit result."""

    baseline_ref: str | None
    catalog_changed: bool
    changed_files: list[str]
    committed_changed_files: list[str]
    deleted_critical_files: list[str]
    explicit_changed_files: list[str]
    local_schemas: list[str]
    missing_catalog_entries: list[str]
    missing_positive_tests: list[str]
    negative_test_schemas: list[str]
    positive_test_schemas: list[str]
    release_blocking_coverage_schemas: list[str]
    repository: str
    schema_validation_changed: bool
    skiptest_test_conflicts: list[str]
    suggested_command_argv: list[list[str]]
    suggested_commands: list[str]
    targeted_coverage_schemas: list[str]
    uncommitted_changed_files: list[str]
    warnings: list[str]


def fail(code: str, message: str, *, path: str | None = None) -> AuditError:
    """Create a controlled audit failure."""
    return AuditError(AuditDiagnostic(code=code, message=message, path=path))


def normalize_path(value: str) -> str:
    """Normalize a path for SchemaStore's repository layout."""
    return value.replace("\\", "/").removeprefix("./")


def validate_changed_path(value: str) -> str:
    """Validate and normalize one repository-relative changed path."""
    normalized = normalize_path(value)
    if not normalized:
        raise fail("unsafe_changed_path", "Changed paths must not be empty.")
    if any(ord(character) < ASCII_CONTROL_END or ord(character) == ASCII_DELETE for character in normalized):
        raise fail(
            "unsafe_changed_path",
            "Changed paths must not contain control characters.",
            path=normalized,
        )
    if normalized.startswith("/") or re.match(r"^[A-Za-z]:", normalized) is not None:
        raise fail(
            "unsafe_changed_path",
            "Changed paths must be repository-relative.",
            path=normalized,
        )
    if any(part in {"", ".", ".."} for part in normalized.split("/")):
        raise fail(
            "unsafe_changed_path",
            "Changed paths must not contain empty, current-directory, or parent-directory segments.",
            path=normalized,
        )
    return normalized


def validate_schema_filename(value: str, *, source_path: str) -> str:
    """Enforce the command-safe SchemaStore local schema filename contract."""
    if SCHEMA_FILENAME_PATTERN.fullmatch(value) is None:
        raise fail(
            "unsafe_schema_filename",
            (
                "Schema filenames must start with an ASCII letter or digit, contain only ASCII letters, "
                "digits, dots, underscores, or hyphens, and end in .json."
            ),
            path=source_path,
        )
    return value


def schema_name_from_path(path: str) -> str | None:
    """Return a validated schema filename from a local schema path."""
    prefix = "src/schemas/json/"
    if not path.startswith(prefix):
        return None
    return validate_schema_filename(path.removeprefix(prefix), source_path=path)


def test_schema_from_path(path: str, root: str) -> str | None:
    """Return the validated schema name implied by a test path."""
    prefix = f"src/{root}/"
    if not path.startswith(prefix):
        return None
    remainder = path.removeprefix(prefix)
    schema_root, separator, _test_path = remainder.partition("/")
    if not schema_root or not separator:
        return None
    schema_name = f"{schema_root}.json"
    return validate_schema_filename(schema_name, source_path=path)


def resolve_repository(value: str) -> Path:
    """Resolve an existing repository directory from a CLI value."""
    try:
        repository = Path(value).expanduser().resolve(strict=True)
    except OSError as error:
        raise argparse.ArgumentTypeError(f"Repository path does not exist: {value}") from error
    if not repository.is_dir():
        raise argparse.ArgumentTypeError(f"Repository path is not a directory: {value}")
    return repository


def find_git() -> str:
    """Resolve Git or fail with a stable diagnostic."""
    git_executable = shutil.which("git")
    if git_executable is None:
        raise fail("git_not_found", "Git is required when --changed-file is not supplied.")
    return git_executable


def run_git(repo: Path, git_executable: str, args: list[str]) -> subprocess.CompletedProcess[bytes]:
    """Run one fixed-argument Git command without a shell."""
    try:
        return subprocess.run(  # noqa: S603  # Resolved Git executable and fixed argument arrays; no shell.
            [git_executable, *args],
            cwd=repo,
            check=False,
            capture_output=True,
            stdin=subprocess.DEVNULL,
        )
    except OSError as error:
        raise fail("git_command_failed", f"Could not execute Git: {error}.") from error


def git_error_message(result: subprocess.CompletedProcess[bytes]) -> str:
    """Return bounded Git stderr suitable for a controlled diagnostic."""
    detail = result.stderr.decode("utf-8", errors="replace").strip()
    return detail[:500] if detail else f"Git exited with status {result.returncode}."


def require_git_success(result: subprocess.CompletedProcess[bytes], *, operation: str) -> bytes:
    """Return Git stdout or raise a command-specific controlled failure."""
    if result.returncode != 0:
        raise fail(
            "git_command_failed",
            f"Git failed while {operation}: {git_error_message(result)}",
        )
    return result.stdout


def decode_git_field(value: bytes, *, operation: str) -> str:
    """Decode a NUL-delimited Git path or status field as UTF-8."""
    try:
        return value.decode("utf-8")
    except UnicodeDecodeError as error:
        raise fail(
            "git_output_invalid",
            f"Git emitted a non-UTF-8 field while {operation}.",
        ) from error


def split_nul_fields(output: bytes, *, operation: str) -> list[bytes]:
    """Split output that must be terminated by a NUL byte."""
    if not output:
        return []
    if not output.endswith(b"\0"):
        raise fail("git_output_invalid", f"Git emitted non-NUL-terminated output while {operation}.")
    return output[:-1].split(b"\0")


def parse_name_status(output: bytes) -> list[str]:
    """Parse `git diff --name-status -z`, retaining both rename paths."""
    fields = split_nul_fields(output, operation="reading committed changes")
    paths: list[str] = []
    index = 0
    while index < len(fields):
        status = decode_git_field(fields[index], operation="reading committed change status")
        index += 1
        if not status or status[0] not in "ACDMRTUXB":
            raise fail("git_output_invalid", f"Git emitted an unsupported committed status: {status!r}.")
        path_count = 2 if status[0] in "RC" else 1
        if index + path_count > len(fields):
            raise fail("git_output_invalid", "Git emitted an incomplete committed change record.")
        paths.extend(
            decode_git_field(field, operation="reading committed change paths")
            for field in fields[index : index + path_count]
        )
        index += path_count
    return paths


def parse_porcelain_status(output: bytes) -> list[str]:
    """Parse `git status --porcelain=v1 -z`, retaining both rename paths."""
    fields = split_nul_fields(output, operation="reading uncommitted changes")
    paths: list[str] = []
    index = 0
    while index < len(fields):
        record = decode_git_field(fields[index], operation="reading uncommitted change status")
        index += 1
        if len(record) < PORCELAIN_RECORD_MIN_LENGTH or record[2] != " ":
            raise fail("git_output_invalid", "Git emitted an invalid porcelain status record.")
        status = record[:2]
        paths.append(record[3:])
        if "R" in status or "C" in status:
            if index >= len(fields):
                raise fail("git_output_invalid", "Git emitted an incomplete uncommitted rename record.")
            paths.append(decode_git_field(fields[index], operation="reading uncommitted rename paths"))
            index += 1
    return paths


def resolve_head(repo: Path, git_executable: str) -> str | None:
    """Resolve HEAD, allowing an unborn repository with only untracked files."""
    result = run_git(repo, git_executable, ["rev-parse", "--verify", "--quiet", "HEAD^{commit}"])
    if result.returncode == 1:
        return None
    output = require_git_success(result, operation="resolving HEAD").decode("ascii", errors="strict").strip()
    if GIT_COMMIT_PATTERN.fullmatch(output) is None:
        raise fail("git_output_invalid", "Git did not resolve HEAD to a full commit SHA.")
    return output


def resolve_base_commit(repo: Path, git_executable: str) -> tuple[str, str] | None:
    """Resolve the first available authoritative remote default-branch ref."""
    for base_ref in DEFAULT_BASE_REFS:
        full_ref = f"refs/remotes/{base_ref}"
        exists = run_git(repo, git_executable, ["show-ref", "--verify", "--quiet", full_ref])
        if exists.returncode == 1:
            continue
        _ = require_git_success(exists, operation=f"checking {base_ref}")
        resolved = (
            require_git_success(
                run_git(repo, git_executable, ["rev-parse", "--verify", f"{base_ref}^{{commit}}"]),
                operation=f"resolving {base_ref}",
            )
            .decode("ascii", errors="strict")
            .strip()
        )
        if GIT_COMMIT_PATTERN.fullmatch(resolved) is None:
            raise fail("git_output_invalid", f"Git did not resolve {base_ref} to a full commit SHA.")
        return base_ref, resolved
    return None


def git_changed_files(repo: Path) -> GitDiscovery:
    """Discover committed and uncommitted paths, failing closed on Git errors."""
    git_executable = find_git()
    worktree = run_git(repo, git_executable, ["rev-parse", "--is-inside-work-tree"])
    if worktree.returncode != 0 or worktree.stdout.strip() != b"true":
        raise fail("not_git_worktree", "Repository is not a Git worktree; use --changed-file for fixtures.")
    top_level_output = require_git_success(
        run_git(repo, git_executable, ["rev-parse", "--show-toplevel"]),
        operation="resolving the worktree root",
    )
    top_level_text = decode_git_field(top_level_output.strip(), operation="resolving the worktree root")
    try:
        top_level = Path(top_level_text).resolve(strict=True)
    except OSError as error:
        raise fail(
            "git_output_invalid",
            f"Git reported an inaccessible worktree root: {error}.",
        ) from error
    if top_level != repo:
        raise fail(
            "not_git_worktree",
            "Repository must be the Git worktree root; use --changed-file for nested fixtures.",
        )

    head_commit = resolve_head(repo, git_executable)
    baseline = resolve_base_commit(repo, git_executable)
    if head_commit is not None and baseline is None:
        raise fail(
            "git_baseline_missing",
            "No authoritative origin/master or origin/main baseline is available for committed-change discovery.",
        )

    committed_files: list[str] = []
    baseline_ref: str | None = None
    if head_commit is not None and baseline is not None:
        baseline_ref, baseline_commit = baseline
        output = require_git_success(
            run_git(
                repo,
                git_executable,
                [
                    "diff",
                    "--name-status",
                    "-z",
                    "--find-renames",
                    "--diff-filter=ACDMRTUXB",
                    f"{baseline_commit}...HEAD",
                    "--",
                ],
            ),
            operation="reading committed changes",
        )
        committed_files = parse_name_status(output)

    status_output = require_git_success(
        run_git(repo, git_executable, ["status", "--porcelain=v1", "-z", "--untracked-files=all"]),
        operation="reading uncommitted changes",
    )
    uncommitted_files = parse_porcelain_status(status_output)
    return GitDiscovery(
        baseline_ref=baseline_ref,
        committed_files=normalize_changed_files(committed_files),
        uncommitted_files=normalize_changed_files(uncommitted_files),
    )


def normalize_changed_files(values: list[str]) -> list[str]:
    """Validate, normalize, deduplicate, and sort changed paths."""
    return sorted({validate_changed_path(value) for value in values})


def read_utf8(path: Path, *, code: str, label: str) -> str:
    """Read one UTF-8 source file with a controlled diagnostic on failure."""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise fail(code, f"Could not read {label}: {error}.", path=normalize_path(str(path))) from error


def string_keyed_object(value: object) -> dict[str, object] | None:
    """Convert a dynamic JSON object to a strictly typed string-keyed mapping."""
    if not isinstance(value, dict):
        return None
    result: dict[str, object] = {}
    for key, item in cast("dict[object, object]", value).items():
        if not isinstance(key, str):
            return None
        result[key] = item
    return result


def object_list(value: object) -> list[object] | None:
    """Convert a dynamic JSON array to a strictly typed object list."""
    if not isinstance(value, list):
        return None
    return cast("list[object]", value)


def catalog_entry_urls(entry: object, index: int) -> set[str]:
    """Validate one catalog entry and return its primary and versioned URLs."""
    catalog_entry = string_keyed_object(entry)
    if catalog_entry is None or not isinstance(catalog_entry.get("url"), str):
        raise fail(
            "catalog_structure_invalid",
            f"catalog.json schemas[{index}] must be an object with a string url.",
            path="src/api/json/catalog.json",
        )
    urls = {cast("str", catalog_entry["url"])}
    if "versions" not in catalog_entry:
        return urls
    versions = string_keyed_object(catalog_entry["versions"])
    if versions is None:
        raise fail(
            "catalog_structure_invalid",
            f"catalog.json schemas[{index}].versions must be an object with string URL values.",
            path="src/api/json/catalog.json",
        )
    for version_name, version_url in versions.items():
        if not isinstance(version_url, str):
            raise fail(
                "catalog_structure_invalid",
                f"catalog.json schemas[{index}].versions[{version_name!r}] must be a string URL.",
                path="src/api/json/catalog.json",
            )
        urls.add(version_url)
    return urls


def load_catalog_urls(path: Path) -> set[str]:
    """Parse catalog.json structurally and return its exact URL strings."""
    if not path.is_file():
        return set()
    text = read_utf8(path, code="catalog_read_failed", label="catalog.json")
    try:
        value: object = json.loads(text)
    except json.JSONDecodeError as error:
        raise fail(
            "catalog_json_invalid",
            f"catalog.json is malformed at line {error.lineno}, column {error.colno}: {error.msg}.",
            path="src/api/json/catalog.json",
        ) from error
    catalog = string_keyed_object(value)
    if catalog is None:
        raise fail(
            "catalog_structure_invalid",
            "catalog.json must contain a JSON object.",
            path="src/api/json/catalog.json",
        )
    schemas = object_list(catalog.get("schemas"))
    if schemas is None:
        raise fail(
            "catalog_structure_invalid",
            "catalog.json must contain a schemas array.",
            path="src/api/json/catalog.json",
        )
    urls: set[str] = set()
    for index, entry in enumerate(schemas):
        urls.update(catalog_entry_urls(entry, index))
    return urls


def consume_jsonc_line_comment(text: str, index: int, output: list[str]) -> int:
    """Consume one JSONC line comment, preserving line boundaries."""
    output.extend((" ", " "))
    index += 2
    while index < len(text) and text[index] not in "\r\n":
        output.append(" ")
        index += 1
    return index


def consume_jsonc_block_comment(text: str, index: int, output: list[str]) -> int:
    """Consume one JSONC block comment, preserving line boundaries."""
    output.extend((" ", " "))
    index += 2
    while index < len(text):
        if index + 1 < len(text) and text[index : index + 2] == "*/":
            output.extend((" ", " "))
            return index + 2
        output.append(text[index] if text[index] in "\r\n" else " ")
        index += 1
    raise fail(
        "schema_validation_jsonc_invalid",
        "schema-validation.jsonc contains an unterminated block comment.",
        path="src/schema-validation.jsonc",
    )


def strip_jsonc_comments(text: str) -> str:
    """Replace JSONC comments with whitespace while preserving string contents."""
    output: list[str] = []
    index = 0
    in_string = False
    escaped = False
    while index < len(text):
        character = text[index]
        next_character = text[index + 1] if index + 1 < len(text) else ""
        if in_string:
            output.append(character)
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            index += 1
            continue
        if character == '"':
            in_string = True
            output.append(character)
            index += 1
            continue
        if character == "/" and next_character == "/":
            index = consume_jsonc_line_comment(text, index, output)
            continue
        if character == "/" and next_character == "*":
            index = consume_jsonc_block_comment(text, index, output)
            continue
        output.append(character)
        index += 1
    return "".join(output)


def remove_jsonc_trailing_commas(text: str) -> str:
    """Remove only commas followed by a closing array or object delimiter."""
    output: list[str] = []
    in_string = False
    escaped = False
    for index, character in enumerate(text):
        if in_string:
            output.append(character)
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
            output.append(character)
            continue
        if character == ",":
            lookahead = index + 1
            while lookahead < len(text) and text[lookahead].isspace():
                lookahead += 1
            if lookahead < len(text) and text[lookahead] in "]}":
                output.append(" ")
                continue
        output.append(character)
    return "".join(output)


def load_jsonc_object(path: Path) -> dict[str, object]:
    """Parse a JSONC object using string-aware comment and comma states."""
    if not path.is_file():
        return {}
    text = read_utf8(path, code="schema_validation_read_failed", label="schema-validation.jsonc")
    normalized = remove_jsonc_trailing_commas(strip_jsonc_comments(text))
    try:
        value: object = json.loads(normalized)
    except json.JSONDecodeError as error:
        raise fail(
            "schema_validation_jsonc_invalid",
            (f"schema-validation.jsonc is malformed at line {error.lineno}, column {error.colno}: {error.msg}."),
            path="src/schema-validation.jsonc",
        ) from error
    config = string_keyed_object(value)
    if config is None:
        raise fail(
            "schema_validation_structure_invalid",
            "schema-validation.jsonc must contain a JSON object.",
            path="src/schema-validation.jsonc",
        )
    return config


def string_array(config: dict[str, object], key: str) -> set[str]:
    """Read a named JSONC string array with structural validation."""
    value = config.get(key, [])
    items = object_list(value)
    if items is None or any(not isinstance(item, str) for item in items):
        raise fail(
            "schema_validation_structure_invalid",
            f"schema-validation.jsonc {key} must be an array of strings.",
            path="src/schema-validation.jsonc",
        )
    return {cast("str", item) for item in items}


def schema_filename_array(config: dict[str, object], key: str) -> set[str]:
    """Read and validate a schema-filename array from schema-validation.jsonc."""
    return {
        validate_schema_filename(item, source_path="src/schema-validation.jsonc") for item in string_array(config, key)
    }


def parse_validation_config(path: Path) -> ValidationConfig:
    """Parse exact catalog exemptions and coverage registrations from JSONC."""
    config = load_jsonc_object(path)
    missing_catalog_urls = schema_filename_array(config, "missingCatalogUrl")
    skip_tests = schema_filename_array(config, "skiptest")
    raw_coverage = object_list(config.get("coverage", []))
    if raw_coverage is None:
        raise fail(
            "schema_validation_structure_invalid",
            "schema-validation.jsonc coverage must be an array.",
            path="src/schema-validation.jsonc",
        )
    coverage: dict[str, bool] = {}
    for index, entry in enumerate(raw_coverage):
        coverage_entry = string_keyed_object(entry)
        if coverage_entry is None:
            raise fail(
                "schema_validation_structure_invalid",
                f"schema-validation.jsonc coverage[{index}] must be an object.",
                path="src/schema-validation.jsonc",
            )
        schema = coverage_entry.get("schema")
        strict = coverage_entry.get("strict", False)
        if not isinstance(schema, str) or not isinstance(strict, bool):
            raise fail(
                "schema_validation_structure_invalid",
                f"schema-validation.jsonc coverage[{index}] requires a string schema and optional boolean strict.",
                path="src/schema-validation.jsonc",
            )
        validated_schema = validate_schema_filename(schema, source_path="src/schema-validation.jsonc")
        coverage[validated_schema] = coverage.get(validated_schema, False) or strict
    return ValidationConfig(
        coverage=coverage,
        missing_catalog_urls=missing_catalog_urls,
        skip_tests=skip_tests,
    )


def positive_test_exists(repo: Path, schema_name: str) -> bool:
    """Return whether a schema has an existing positive test directory with files."""
    test_dir = repo / "src" / "test" / schema_name.removesuffix(".json")
    return test_dir.is_dir() and any(path.is_file() for path in test_dir.iterdir())


def catalog_contains_schema(catalog_urls: set[str], schema_name: str) -> bool:
    """Return whether an exact supported local-schema URL is in the catalog."""
    accepted_urls = {f"{base}{schema_name}" for base in SCHEMASTORE_LOCAL_CATALOG_URL_BASES}
    return not accepted_urls.isdisjoint(catalog_urls)


def is_critical_path(path: str) -> bool:
    """Return whether deleting a changed path is PR-critical."""
    return path in CRITICAL_EXACT_PATHS or path.startswith(CRITICAL_PREFIXES)


def find_skiptest_test_conflicts(repo: Path, skip_tests: set[str]) -> list[str]:
    """Return existing positive or negative test surfaces forbidden by skiptest."""
    conflicts: list[str] = []
    for schema_name in sorted(skip_tests):
        test_name = schema_name.removesuffix(".json")
        for root in ("test", "negative_test"):
            relative_path = f"src/{root}/{test_name}"
            if (repo / Path(relative_path)).exists():
                conflicts.append(relative_path)
    return conflicts


def command_text(argv: list[str]) -> str:
    """Render already validated fixed argv for human-readable output."""
    return " ".join(argv)


def dedupe_argv(values: list[list[str]]) -> list[list[str]]:
    """Return argv arrays in first-seen order without duplicates."""
    seen: set[tuple[str, ...]] = set()
    result: list[list[str]] = []
    for value in values:
        key = tuple(value)
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def build_audit(
    repo: Path,
    *,
    baseline_ref: str | None,
    committed_files: list[str],
    uncommitted_files: list[str],
    explicit_files: list[str],
) -> SchemaStorePrAudit:
    """Build a SchemaStore pull request audit from separated changed-file sources."""
    normalized_committed = normalize_changed_files(committed_files)
    normalized_uncommitted = normalize_changed_files(uncommitted_files)
    normalized_explicit = normalize_changed_files(explicit_files)
    normalized_files = sorted({*normalized_committed, *normalized_uncommitted, *normalized_explicit})
    local_schemas = sorted(
        schema_name for path in normalized_files if (schema_name := schema_name_from_path(path)) is not None
    )
    positive_test_schemas = sorted(
        schema_name for path in normalized_files if (schema_name := test_schema_from_path(path, "test")) is not None
    )
    negative_test_schemas = sorted(
        schema_name
        for path in normalized_files
        if (schema_name := test_schema_from_path(path, "negative_test")) is not None
    )
    catalog_changed = "src/api/json/catalog.json" in normalized_files
    schema_validation_changed = "src/schema-validation.jsonc" in normalized_files
    deleted_critical_files = [
        path for path in normalized_files if is_critical_path(path) and not (repo / Path(path)).is_file()
    ]

    catalog_urls = load_catalog_urls(repo / "src" / "api" / "json" / "catalog.json")
    validation = parse_validation_config(repo / "src" / "schema-validation.jsonc")

    missing_positive_tests = [
        schema_name
        for schema_name in local_schemas
        if schema_name not in validation.skip_tests and not positive_test_exists(repo, schema_name)
    ]
    missing_catalog_entries = [
        schema_name
        for schema_name in local_schemas
        if not catalog_contains_schema(catalog_urls, schema_name)
        and schema_name not in validation.missing_catalog_urls
        and schema_name not in validation.skip_tests
    ]
    skiptest_test_conflicts = find_skiptest_test_conflicts(repo, validation.skip_tests)

    changed_schema_names = sorted({*local_schemas, *positive_test_schemas, *negative_test_schemas})
    targeted_coverage_schemas = [
        schema_name for schema_name in changed_schema_names if schema_name in validation.coverage
    ]
    release_blocking_coverage_schemas = [
        schema_name for schema_name in targeted_coverage_schemas if validation.coverage[schema_name]
    ]

    warnings: list[str] = []
    if deleted_critical_files:
        warnings.append(
            "Critical schema, catalog, test, or validation-config paths are missing or are not regular files."
        )
    if missing_positive_tests:
        warnings.append("Local schema changes are missing positive tests.")
    if missing_catalog_entries:
        warnings.append("Local schema changes are missing catalog entries or exact catalog exemptions.")
    if skiptest_test_conflicts:
        warnings.append("Schemas listed in skiptest must not have positive or negative test surfaces.")
    if catalog_changed and not local_schemas:
        warnings.append("Catalog-only change: verify this is an intentional remote/self-hosted schema entry.")
    if schema_validation_changed:
        warnings.append("schema-validation.jsonc changed: explain every exception in the PR.")
    if release_blocking_coverage_schemas:
        warnings.append("Strict coverage is release-blocking for the listed changed schemas.")

    suggested_argv = [["npm", "clean-install"]]
    suggested_argv.extend(
        ["node", "./cli.js", "check", f"--schema-name={schema_name}"]
        for schema_name in local_schemas
        if schema_name not in validation.skip_tests
    )
    if schema_validation_changed or catalog_changed or len(local_schemas) != 1:
        suggested_argv.append(["node", "./cli.js", "check"])
    suggested_argv.extend(
        ["node", "./cli.js", "coverage", f"--schema-name={schema_name}"] for schema_name in targeted_coverage_schemas
    )
    if schema_validation_changed:
        suggested_argv.append(["node", "./cli.js", "coverage"])
    suggested_argv.extend(
        [
            ["npm", "run", "typecheck"],
            ["npm", "run", "eslint"],
            ["npm", "run", "prettier"],
        ]
    )
    suggested_command_argv = dedupe_argv(suggested_argv)

    return SchemaStorePrAudit(
        baseline_ref=baseline_ref,
        catalog_changed=catalog_changed,
        changed_files=normalized_files,
        committed_changed_files=normalized_committed,
        deleted_critical_files=deleted_critical_files,
        explicit_changed_files=normalized_explicit,
        local_schemas=local_schemas,
        missing_catalog_entries=missing_catalog_entries,
        missing_positive_tests=missing_positive_tests,
        negative_test_schemas=negative_test_schemas,
        positive_test_schemas=positive_test_schemas,
        release_blocking_coverage_schemas=release_blocking_coverage_schemas,
        repository=str(repo),
        schema_validation_changed=schema_validation_changed,
        skiptest_test_conflicts=skiptest_test_conflicts,
        suggested_command_argv=suggested_command_argv,
        suggested_commands=[command_text(argv) for argv in suggested_command_argv],
        targeted_coverage_schemas=targeted_coverage_schemas,
        uncommitted_changed_files=normalized_uncommitted,
        warnings=warnings,
    )


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Audit changed SchemaStore PR files and print validation commands.")
    _ = parser.add_argument(
        "repository",
        nargs="?",
        default=resolve_repository("."),
        type=resolve_repository,
        help="Path to a SchemaStore checkout.",
    )
    _ = parser.add_argument(
        "--changed-file",
        action="append",
        default=[],
        help="Changed file path to audit. Can be repeated; skips git discovery.",
    )
    _ = parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    return parser.parse_args()


def print_text(audit: SchemaStorePrAudit) -> None:
    """Print a concise text audit."""
    write_line(f"SchemaStore PR audit: {audit.repository}")
    write_line(f"baseline: {audit.baseline_ref or 'explicit/unborn'}")
    write_line(f"changed files: {len(audit.changed_files)}")
    write_list("committed changed files", audit.committed_changed_files)
    write_list("uncommitted changed files", audit.uncommitted_changed_files)
    write_list("explicit changed files", audit.explicit_changed_files)
    write_list("local schemas", audit.local_schemas)
    write_list("positive test schemas", audit.positive_test_schemas)
    write_list("negative test schemas", audit.negative_test_schemas)
    write_list("deleted critical files", audit.deleted_critical_files)
    write_list("missing positive tests", audit.missing_positive_tests)
    write_list("missing catalog/config entries", audit.missing_catalog_entries)
    write_list("targeted coverage schemas", audit.targeted_coverage_schemas)
    write_list("release-blocking coverage schemas", audit.release_blocking_coverage_schemas)
    write_list("skiptest test conflicts", audit.skiptest_test_conflicts)
    write_list("warnings", audit.warnings)
    write_list("suggested commands", audit.suggested_commands)


def write_list(label: str, values: list[str]) -> None:
    """Write a labelled list."""
    write_line(f"{label}:")
    if not values:
        write_line("  - none")
        return
    for value in values:
        write_line(f"  - {value}")


def write_line(text: str, *, stream: TextIO = sys.stdout) -> None:
    """Write one line to a text stream."""
    _ = stream.write(f"{text}\n")


def print_failure(error: AuditError, *, as_json: bool) -> None:
    """Print a controlled operational failure in text or JSON form."""
    if as_json:
        write_line(json.dumps({"diagnostics": [asdict(error.diagnostic)], "ok": False}, indent=2))
        return
    location = f" ({error.diagnostic.path})" if error.diagnostic.path is not None else ""
    write_line(
        f"ERROR [{error.diagnostic.code}]{location}: {error.diagnostic.message}",
        stream=sys.stderr,
    )


def main() -> int:
    """Run the audit."""
    args = parse_args()
    repo: Path = args.repository
    try:
        explicit_files = normalize_changed_files(args.changed_file)
        if explicit_files:
            discovery = GitDiscovery(baseline_ref=None, committed_files=[], uncommitted_files=[])
        else:
            discovery = git_changed_files(repo)
        audit = build_audit(
            repo,
            baseline_ref=discovery.baseline_ref,
            committed_files=discovery.committed_files,
            uncommitted_files=discovery.uncommitted_files,
            explicit_files=explicit_files,
        )
    except AuditError as error:
        print_failure(error, as_json=args.json)
        return EXIT_OPERATIONAL_ERROR

    if args.json:
        write_line(json.dumps(asdict(audit), indent=2))
    else:
        print_text(audit)

    has_findings = bool(
        audit.deleted_critical_files
        or audit.missing_positive_tests
        or audit.missing_catalog_entries
        or audit.skiptest_test_conflicts
    )
    return EXIT_AUDIT_FINDINGS if has_findings else 0


if __name__ == "__main__":
    sys.exit(main())
