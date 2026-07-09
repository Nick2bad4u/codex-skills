#!/usr/bin/env python
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

GIT_REF_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]*")


@dataclass(frozen=True)
class SchemaStorePrAudit:
    """Read-only SchemaStore pull request audit result."""

    catalog_changed: bool
    changed_files: list[str]
    local_schemas: list[str]
    missing_catalog_entries: list[str]
    missing_positive_tests: list[str]
    negative_test_schemas: list[str]
    positive_test_schemas: list[str]
    repository: str
    schema_validation_changed: bool
    suggested_commands: list[str]
    warnings: list[str]


def normalize_path(value: str) -> str:
    """Normalize a path for SchemaStore's repository layout."""
    return value.replace("\\", "/").removeprefix("./")


def schema_name_from_path(path: str) -> str | None:
    """Return a schema filename from a local schema path."""
    prefix = "src/schemas/json/"
    if path.startswith(prefix) and path.endswith(".json"):
        return path.removeprefix(prefix)
    return None


def test_schema_from_path(path: str, root: str) -> str | None:
    """Return the schema name implied by a positive or negative test path."""
    prefix = f"src/{root}/"
    if not path.startswith(prefix):
        return None
    remainder = path.removeprefix(prefix)
    schema_root = remainder.split("/", maxsplit=1)[0]
    if not schema_root:
        return None
    return f"{schema_root}.json"


def resolve_repository(value: str) -> Path:
    """Resolve an existing repository directory from a CLI value."""
    try:
        repository = Path(value).expanduser().resolve(strict=True)
    except OSError as error:
        raise argparse.ArgumentTypeError(f"Repository path does not exist: {value}") from error
    if not repository.is_dir():
        raise argparse.ArgumentTypeError(f"Repository path is not a directory: {value}")
    return repository


def validate_git_ref(value: str) -> str:
    """Accept simple branch, tag, remote, or commit names without Git revision operators."""
    if (
        GIT_REF_PATTERN.fullmatch(value) is None
        or ".." in value
        or "//" in value
        or value.endswith(("/", ".", ".lock"))
    ):
        raise argparse.ArgumentTypeError("Base must be a simple branch, tag, remote, or commit name.")
    return value


def run_git(repo: Path, args: list[str]) -> list[str]:
    """Run git and return stdout lines, or an empty list when git is unavailable."""
    git_executable = shutil.which("git")
    if git_executable is None:
        return []

    result = subprocess.run(  # noqa: S603  # Fixed executable and argument list; no shell.
        [git_executable, *args],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def git_changed_files(repo: Path, base: str) -> list[str]:
    """Return changed files using git diff plus uncommitted status."""
    resolved_base = run_git(repo, ["rev-parse", "--verify", "--end-of-options", f"{base}^{{commit}}"])
    if len(resolved_base) != 1 or re.fullmatch(r"[0-9a-f]{40}", resolved_base[0]) is None:
        return []

    diff_files = run_git(
        repo,
        ["diff", "--name-only", "--diff-filter=ACMRTUXB", f"{resolved_base[0]}...HEAD", "--"],
    )
    if not diff_files:
        diff_files = run_git(repo, ["diff", "--name-only", "--diff-filter=ACMRTUXB", "--"])

    status_files: list[str] = []
    for line in run_git(repo, ["status", "--porcelain=v1"]):
        status_path = line[3:]
        if " -> " in status_path:
            status_path = status_path.split(" -> ", maxsplit=1)[1]
        status_files.append(status_path)

    return sorted({normalize_path(path) for path in [*diff_files, *status_files]})


def read_text(path: Path) -> str:
    """Read a UTF-8 file or return an empty string when absent."""
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def positive_test_exists(repo: Path, schema_name: str) -> bool:
    """Return whether a schema has an existing positive test directory with files."""
    test_dir = repo / "src" / "test" / schema_name.removesuffix(".json")
    return test_dir.is_dir() and any(path.is_file() for path in test_dir.iterdir())


def catalog_mentions_schema(catalog_text: str, schema_name: str) -> bool:
    """Return whether catalog.json appears to expose a local schema URL."""
    return (
        f"https://www.schemastore.org/{schema_name}" in catalog_text
        or f"https://raw.githubusercontent.com/SchemaStore/schemastore/master/src/schemas/json/{schema_name}"
        in catalog_text
    )


def validation_config_mentions_schema(validation_text: str, schema_name: str) -> bool:
    """Return whether schema-validation.jsonc appears to intentionally classify a schema."""
    return f'"{schema_name}"' in validation_text


def build_audit(repo: Path, changed_files: list[str]) -> SchemaStorePrAudit:
    """Build a SchemaStore pull request audit from changed file paths."""
    normalized_files = sorted({normalize_path(path) for path in changed_files})
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

    catalog_text = read_text(repo / "src" / "api" / "json" / "catalog.json")
    validation_text = read_text(repo / "src" / "schema-validation.jsonc")

    missing_positive_tests = [
        schema_name for schema_name in local_schemas if not positive_test_exists(repo, schema_name)
    ]
    missing_catalog_entries = [
        schema_name
        for schema_name in local_schemas
        if not catalog_mentions_schema(catalog_text, schema_name)
        and not validation_config_mentions_schema(validation_text, schema_name)
    ]

    warnings: list[str] = []
    if missing_positive_tests:
        warnings.append("Local schema changes are missing positive tests.")
    if missing_catalog_entries:
        warnings.append("Local schema changes are missing catalog entries or validation-config classification.")
    if catalog_changed and not local_schemas:
        warnings.append("Catalog-only change: verify this is an intentional remote/self-hosted schema entry.")
    if schema_validation_changed:
        warnings.append("schema-validation.jsonc changed: explain every exception in the PR.")

    suggested_commands = ["npm clean-install"]
    suggested_commands.extend(f"node ./cli.js check --schema-name={schema_name}" for schema_name in local_schemas)
    if schema_validation_changed or catalog_changed or len(local_schemas) != 1:
        suggested_commands.append("node ./cli.js check")
    if schema_validation_changed:
        suggested_commands.append("node ./cli.js coverage")
    suggested_commands.extend(["npm run typecheck", "npm run eslint", "npm run prettier"])

    return SchemaStorePrAudit(
        catalog_changed=catalog_changed,
        changed_files=normalized_files,
        local_schemas=local_schemas,
        missing_catalog_entries=missing_catalog_entries,
        missing_positive_tests=missing_positive_tests,
        negative_test_schemas=negative_test_schemas,
        positive_test_schemas=positive_test_schemas,
        repository=str(repo),
        schema_validation_changed=schema_validation_changed,
        suggested_commands=dedupe(suggested_commands),
        warnings=warnings,
    )


def dedupe(values: list[str]) -> list[str]:
    """Return values in first-seen order without duplicates."""
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


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
        "--base",
        default="origin/master",
        type=validate_git_ref,
        help="Base ref for git diff when --changed-file is absent.",
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
    write_line(f"changed files: {len(audit.changed_files)}")
    write_list("local schemas", audit.local_schemas)
    write_list("positive test schemas", audit.positive_test_schemas)
    write_list("negative test schemas", audit.negative_test_schemas)
    write_list("missing positive tests", audit.missing_positive_tests)
    write_list("missing catalog/config entries", audit.missing_catalog_entries)
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


def write_line(text: str) -> None:
    """Write one line to stdout."""
    _ = sys.stdout.write(f"{text}\n")


def main() -> int:
    """Run the audit."""
    args = parse_args()
    repo = args.repository
    changed_files = [normalize_path(value) for value in args.changed_file] or git_changed_files(repo, args.base)
    audit = build_audit(repo, changed_files)

    if args.json:
        write_line(json.dumps(asdict(audit), indent=2))
    else:
        print_text(audit)

    return 1 if audit.missing_positive_tests or audit.missing_catalog_entries else 0


if __name__ == "__main__":
    sys.exit(main())
