#!/usr/bin/env python
"""Summarize dependency-update surfaces and likely validation commands."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import cast

NODE_SCRIPT_PRIORITY = [
    "release:verify",
    "validate",
    "check",
    "test",
    "typecheck",
    "lint",
    "build",
    "format:check",
]

DIRECT_UPDATE_SCRIPTS = ("update-all", "update-deps", "deps:update", "dependencies:update")
GIT_REF_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]*")
PACKAGE_JSON = "package.json"
PACKAGE_LOCK_JSON = "package-lock.json"
PYPROJECT_TOML = "pyproject.toml"
MANAGER_MARKERS = [
    ("npm", (PACKAGE_LOCK_JSON, "npm-shrinkwrap.json", PACKAGE_JSON)),
    ("pnpm", ("pnpm-lock.yaml", "pnpm-workspace.yaml")),
    ("yarn", ("yarn.lock", ".yarnrc.yml")),
    ("bun", ("bun.lock", "bun.lockb", "bunfig.toml")),
    ("python", (PYPROJECT_TOML, "requirements.txt", "requirements-dev.txt", "uv.lock")),
    ("poetry", ("poetry.lock",)),
    ("go", ("go.mod", "go.sum")),
    ("rust", ("Cargo.toml", "Cargo.lock")),
]
MANAGER_UPDATE_COMMANDS = {
    "bun": "bun update",
    "go": "go get -u ./...",
    "npm": "npm update",
    "pnpm": "pnpm update --interactive --latest",
    "poetry": "poetry update",
    "python": "uv lock --upgrade",
    "rust": "cargo update",
    "yarn": "yarn up -i",
}
MANAGER_VALIDATION_COMMANDS = {
    "dotnet": "dotnet test",
    "github-actions": "actionlint",
    "go": "go test ./...",
    "rust": "cargo test",
}


@dataclass(frozen=True)
class DependencyUpdateAudit:
    """Read-only dependency update audit result."""

    changed_files: list[str]
    install_commands: list[str]
    package_managers: list[str]
    repository: str
    update_commands: list[str]
    validation_commands: list[str]
    warnings: list[str]


def normalize_path(value: str) -> str:
    """Normalize repository paths."""
    return value.replace("\\", "/").removeprefix("./")


def path_exists(root: Path, relative_path: str) -> bool:
    """Return whether a repository-relative path exists."""
    return (root / relative_path).exists()


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


def changed_or_exists(root: Path, changed_files: list[str], *paths: str) -> bool:
    """Return whether any path is changed or present."""
    return any(path in changed_files or path_exists(root, path) for path in paths)


def read_package_scripts(root: Path) -> dict[str, str]:
    """Read package.json scripts as strings."""
    package_json = root / PACKAGE_JSON
    if not package_json.exists():
        return {}

    data = string_object_dict(json.loads(package_json.read_text(encoding="utf-8")))
    scripts = string_object_dict(data.get("scripts"))

    return {key: value for key, value in scripts.items() if isinstance(value, str)}


def string_object_dict(value: object) -> dict[str, object]:
    """Return a string-keyed object dictionary from dynamic JSON."""
    if not isinstance(value, dict):
        return {}

    return {key: item for key, item in cast("dict[object, object]", value).items() if isinstance(key, str)}


def read_text(root: Path, relative_path: str) -> str:
    """Read a repository file or return an empty string."""
    path = root / relative_path
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def detect_package_managers(root: Path, changed_files: list[str]) -> list[str]:
    """Detect dependency ecosystems from changed files and repository markers."""
    managers = [manager for manager, markers in MANAGER_MARKERS if changed_or_exists(root, changed_files, *markers)]
    if any(path.startswith(".github/workflows/") or path == ".github/dependabot.yml" for path in changed_files):
        managers.append("github-actions")
    if any(path.endswith((".csproj", "packages.lock.json")) for path in changed_files):
        managers.append("dotnet")
    return dedupe(managers)


def build_install_commands(root: Path, managers: list[str]) -> list[str]:
    """Build likely install commands for detected ecosystems."""
    commands: list[str] = []
    if "npm" in managers and path_exists(root, PACKAGE_LOCK_JSON):
        commands.append("npm ci")
    if "pnpm" in managers:
        commands.append("pnpm install --frozen-lockfile")
    if "yarn" in managers:
        commands.append("yarn install --immutable")
    if "bun" in managers:
        commands.append("bun install --frozen-lockfile")
    if "python" in managers and path_exists(root, "requirements-dev.txt"):
        commands.append("python -m pip install -r requirements-dev.txt")
    if "poetry" in managers:
        commands.append("poetry install --sync")
    return commands


def build_validation_commands(root: Path, managers: list[str], package_scripts: dict[str, str]) -> list[str]:
    """Build likely validation commands for detected ecosystems."""
    commands = [f"npm run {script}" for script in NODE_SCRIPT_PRIORITY if script in package_scripts]

    pyproject = read_text(root, PYPROJECT_TOML)
    if "python" in managers or "poetry" in managers:
        if "[tool.ruff" in pyproject:
            commands.append("ruff check .")
            commands.append("ruff format --check .")
        if "[tool.mypy" in pyproject:
            commands.append("mypy")
        if "[tool.pyright" in pyproject:
            commands.append("pyright")
        if "[tool.pytest" in pyproject or path_exists(root, "pytest.ini"):
            commands.append("pytest")
        commands.append('python -m compileall -q -x "[\\\\/]\\\\." .')

    commands.extend(command for manager, command in MANAGER_VALIDATION_COMMANDS.items() if manager in managers)

    return dedupe(commands)


def build_update_commands(
    managers: list[str],
    package_scripts: dict[str, str],
    *,
    include_update_commands: bool,
) -> list[str]:
    """Build optional mutating update commands."""
    if not include_update_commands:
        return []

    commands = [f"npm run {script}" for script in DIRECT_UPDATE_SCRIPTS if script in package_scripts]
    commands.extend(command for manager, command in MANAGER_UPDATE_COMMANDS.items() if manager in managers)

    return dedupe(commands)


def build_warnings(
    changed_files: list[str],
    managers: list[str],
    *,
    include_update_commands: bool,
) -> list[str]:
    """Build dependency-update risk warnings."""
    warnings: list[str] = []
    manifest_changed = any(
        path in changed_files
        for path in (PACKAGE_JSON, PYPROJECT_TOML, "Cargo.toml", "go.mod", "Directory.Packages.props")
    )
    lock_changed = any(
        path in changed_files
        for path in (
            PACKAGE_LOCK_JSON,
            "pnpm-lock.yaml",
            "yarn.lock",
            "bun.lock",
            "uv.lock",
            "poetry.lock",
            "Cargo.lock",
            "go.sum",
        )
    )
    if lock_changed and not manifest_changed:
        warnings.append("Lockfile-only update: verify this is an intentional transitive refresh.")
    package_managers = ("npm", "pnpm", "yarn", "bun", "python", "poetry", "rust", "go")
    if manifest_changed and not lock_changed and any(manager in managers for manager in package_managers):
        warnings.append("Manifest changed without an obvious lockfile change; confirm repository lockfile policy.")
    if "github-actions" in managers:
        warnings.append(
            "Workflow/Dependabot config changed; verify action inputs and permissions against current action metadata."
        )
    if not include_update_commands:
        warnings.append(
            "Mutating update commands omitted; pass --include-update-commands only when update mode is approved."
        )
    return warnings


def build_audit(
    repo: Path,
    changed_files: list[str],
    *,
    include_update_commands: bool,
) -> DependencyUpdateAudit:
    """Build a dependency-update audit."""
    normalized_files = sorted({normalize_path(path) for path in changed_files})
    package_scripts = read_package_scripts(repo)
    managers = detect_package_managers(repo, normalized_files)
    return DependencyUpdateAudit(
        changed_files=normalized_files,
        install_commands=build_install_commands(repo, managers),
        package_managers=managers,
        repository=str(repo),
        update_commands=build_update_commands(
            managers,
            package_scripts,
            include_update_commands=include_update_commands,
        ),
        validation_commands=build_validation_commands(repo, managers, package_scripts),
        warnings=build_warnings(
            normalized_files,
            managers,
            include_update_commands=include_update_commands,
        ),
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
    parser = argparse.ArgumentParser(description="Audit dependency-update surfaces and likely validation commands.")
    _ = parser.add_argument(
        "repository",
        nargs="?",
        default=resolve_repository("."),
        type=resolve_repository,
        help="Path to a repository.",
    )
    _ = parser.add_argument(
        "--base",
        default="origin/main",
        type=validate_git_ref,
        help="Base ref for git diff when --changed-file is absent.",
    )
    _ = parser.add_argument(
        "--changed-file",
        action="append",
        default=[],
        help="Changed file path to audit. Can be repeated; skips git discovery.",
    )
    _ = parser.add_argument(
        "--include-update-commands",
        action="store_true",
        help="Include mutating update command suggestions for approved update mode.",
    )
    _ = parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    return parser.parse_args()


def print_text(audit: DependencyUpdateAudit) -> None:
    """Print a concise text audit."""
    write_line(f"Dependency update audit: {audit.repository}")
    write_list("package managers", audit.package_managers)
    write_list("changed files", audit.changed_files)
    write_list("install commands", audit.install_commands)
    write_list("validation commands", audit.validation_commands)
    write_list("update commands", audit.update_commands)
    write_list("warnings", audit.warnings)


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
    repo = cast("Path", args.repository)
    changed_files = [normalize_path(value) for value in args.changed_file] or git_changed_files(repo, args.base)
    audit = build_audit(
        repo,
        changed_files,
        include_update_commands=bool(args.include_update_commands),
    )

    if args.json:
        write_line(json.dumps(asdict(audit), indent=2))
    else:
        print_text(audit)

    return 0


if __name__ == "__main__":
    sys.exit(main())
