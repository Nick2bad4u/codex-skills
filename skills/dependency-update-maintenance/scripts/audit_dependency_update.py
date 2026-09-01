#!/usr/bin/env python
# Copyright (c) 2026 Nick2bad4u
"""Summarize dependency-update surfaces and likely validation commands."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import stat
import subprocess
import sys
import tomllib
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
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
REMOTE_BASE_REFS = ("origin/main", "origin/master")
PACKAGE_JSON = "package.json"
PACKAGE_LOCK_JSON = "package-lock.json"
NPM_SHRINKWRAP_JSON = "npm-shrinkwrap.json"
PYPROJECT_TOML = "pyproject.toml"
PNPM_LOCK_YAML = "pnpm-lock.yaml"
YARN_LOCK = "yarn.lock"
YARN_CONFIG = ".yarnrc.yml"
BUN_LOCK = "bun.lock"
BUN_BINARY_LOCK = "bun.lockb"
UV_LOCK = "uv.lock"
UV_CONFIG = "uv.toml"
POETRY_LOCK = "poetry.lock"
GO_MOD = "go.mod"
CARGO_TOML = "Cargo.toml"
DOTNET_PROJECT_SUFFIX = ".csproj"
PACKAGES_LOCK_JSON = "packages.lock.json"
EMPTY_LIST_ENTRY = "  - none"
NODE_MANAGERS = ("npm", "pnpm", "yarn", "bun")
NPM_SHRINKWRAP_MAX_MAJOR = 11
PORCELAIN_PATH_OFFSET = 3
PORCELAIN_MIN_RECORD_LENGTH = 4
LEGACY_COMMAND_SHELL = "PowerShell 7"
WINDOWS_DRIVE_PATTERN = re.compile(r"^[A-Za-z]:")
SAFE_POWERSHELL_TOKEN = re.compile(r"[A-Za-z0-9_./:+=-]+")
REV_PARSE_OBJECT_PATTERN = re.compile(r"[0-9A-Fa-f]+")
REV_PARSE_OBJECT_LENGTHS = frozenset({40, 64})
PACKAGE_MANAGER_MAJOR_PATTERN = re.compile(r"^v?(\d+)(?:[.+-]|$)")
REQUIREMENT_PATTERN = re.compile(r"requirements(?:[-_.][^/]+)?\.(?:in|txt)")
DEPENDENCY_REQUIREMENT_PATTERN = re.compile(r"requirements(?:[-_.][^/]+)?\.(?:in|lock|txt)")
NODE_MARKERS = {
    "npm": (PACKAGE_LOCK_JSON, NPM_SHRINKWRAP_JSON, ".npmrc"),
    "pnpm": (PNPM_LOCK_YAML, "pnpm-workspace.yaml"),
    "yarn": (YARN_LOCK, YARN_CONFIG),
    "bun": (BUN_LOCK, BUN_BINARY_LOCK, "bunfig.toml"),
}
FROZEN_INSTALL_LOCKS = {
    "npm": (PACKAGE_LOCK_JSON,),
    "pnpm": (PNPM_LOCK_YAML,),
    "yarn": (YARN_LOCK,),
    "bun": (BUN_LOCK, BUN_BINARY_LOCK),
    "uv": (UV_LOCK,),
    "poetry": (POETRY_LOCK,),
}
DEPENDENCY_SURFACE_NAMES = {
    PACKAGE_JSON,
    PACKAGE_LOCK_JSON,
    NPM_SHRINKWRAP_JSON,
    ".npmrc",
    PNPM_LOCK_YAML,
    "pnpm-workspace.yaml",
    YARN_LOCK,
    YARN_CONFIG,
    BUN_LOCK,
    BUN_BINARY_LOCK,
    "bunfig.toml",
    PYPROJECT_TOML,
    UV_LOCK,
    UV_CONFIG,
    POETRY_LOCK,
    GO_MOD,
    "go.sum",
    CARGO_TOML,
    "Cargo.lock",
    "Directory.Packages.props",
}
MANAGER_UPDATE_ARGV = {
    "bun": ("bun", "update"),
    "go": ("go", "get", "-u", "./..."),
    "npm": ("npm", "update"),
    "pnpm": ("pnpm", "update", "--interactive", "--latest"),
    "poetry": ("poetry", "update"),
    "rust": ("cargo", "update"),
    "uv": ("uv", "lock", "--upgrade"),
}
MANAGER_VALIDATION_ARGV = {
    "dotnet": ("dotnet", "test"),
    "github-actions": ("actionlint",),
    "go": ("go", "test", "./..."),
    "rust": ("cargo", "test"),
}
MANAGER_SORT_ORDER = {
    manager: index
    for index, manager in enumerate(
        ("npm", "pnpm", "yarn", "bun", "uv", "poetry", "pip", "go", "rust", "dotnet", "github-actions")
    )
}


class GitDiscoveryError(RuntimeError):
    """Raised when Git cannot reliably discover changed paths."""


@dataclass(frozen=True)
class DependencyOwner:
    """One surviving, directory-scoped dependency owner."""

    cwd: str
    manager: str
    variant: str | None = None
    version_major: int | None = None


@dataclass(frozen=True)
class PackageManagerDeclaration:
    """One supported packageManager declaration and its parseable major version."""

    manager: str
    version: str | None
    version_major: int | None


@dataclass(frozen=True)
class CommandSpec:
    """A shell-free process invocation suggestion."""

    cwd: str
    argv: tuple[str, ...]


@dataclass(frozen=True)
class DependencyUpdateAudit:
    """Read-only dependency update audit result."""

    changed_files: list[str]
    install_command_specs: list[CommandSpec]
    install_commands: list[str]
    legacy_command_shell: str
    owners: list[DependencyOwner]
    package_managers: list[str]
    repository: str
    update_command_specs: list[CommandSpec]
    update_commands: list[str]
    validation_command_specs: list[CommandSpec]
    validation_commands: list[str]
    warnings: list[str]


def normalize_path(value: str) -> str:
    """Normalize separators and harmless current-directory components."""
    normalized = value.replace("\\", "/")
    parts = [part for part in normalized.split("/") if part not in {"", "."}]
    return "/".join(parts)


def validate_changed_file(value: str) -> str:
    """Validate and normalize one explicit repository-relative changed path."""
    if not value or any(unicodedata.category(character) == "Cc" for character in value):
        raise argparse.ArgumentTypeError("Changed files must not be empty or contain control characters.")
    normalized_separators = value.replace("\\", "/")
    if normalized_separators.startswith("/") or WINDOWS_DRIVE_PATTERN.match(normalized_separators) is not None:
        raise argparse.ArgumentTypeError("Changed files must be repository-relative paths.")
    components = normalized_separators.split("/")
    if ".." in components:
        raise argparse.ArgumentTypeError("Changed files must not traverse outside the repository.")
    normalized = normalize_path(normalized_separators)
    if not normalized:
        raise argparse.ArgumentTypeError("Changed files must identify a repository-relative file.")
    return normalized


def repository_path(root: Path, relative_path: str) -> Path:
    """Build a native path from a normalized repository-relative path."""
    return root.joinpath(*PurePosixPath(relative_path).parts)


def is_reparse_point(path: Path) -> bool:
    """Return whether an existing Windows path is any kind of reparse point."""
    try:
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
    except OSError:
        return False
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def resolved_confined_path(root: Path, relative_path: str) -> Path | None:
    """Resolve one surviving path and reject targets outside the repository root."""
    try:
        resolved = repository_path(root, relative_path).resolve(strict=True)
    except OSError, RuntimeError:
        return None
    return resolved if resolved.is_relative_to(root) else None


def resolved_confined_file(root: Path, relative_path: str) -> Path | None:
    """Resolve a surviving regular file confined to the repository."""
    resolved = resolved_confined_path(root, relative_path)
    return resolved if resolved is not None and resolved.is_file() else None


def resolved_confined_directory(root: Path, relative_path: str) -> Path | None:
    """Resolve a surviving directory confined to the repository."""
    resolved = resolved_confined_path(root, relative_path)
    return resolved if resolved is not None and resolved.is_dir() else None


def changed_path_is_confined(root: Path, relative_path: str) -> bool:
    """Validate a changed path through its nearest surviving filesystem ancestor."""
    candidate = repository_path(root, relative_path)
    while candidate != root:
        if candidate.is_symlink() or is_reparse_point(candidate):
            try:
                resolved_link = candidate.resolve(strict=False)
            except OSError, RuntimeError:
                return False
            return resolved_link.is_relative_to(root)
        try:
            resolved = candidate.resolve(strict=True)
        except FileNotFoundError, NotADirectoryError:
            candidate = candidate.parent
            continue
        except OSError, RuntimeError:
            return False
        return resolved.is_relative_to(root)
    return True


def path_exists(root: Path, relative_path: str) -> bool:
    """Return whether a repository-confined regular file currently survives."""
    return resolved_confined_file(root, relative_path) is not None


def resolve_repository(value: str) -> Path:
    """Resolve an existing repository directory from a CLI value."""
    try:
        repository = Path(value).expanduser().resolve(strict=True)
    except OSError as error:
        raise argparse.ArgumentTypeError(f"Repository path does not exist: {value}") from error
    if not repository.is_dir():
        raise argparse.ArgumentTypeError(f"Repository path is not a directory: {value}")
    return repository


def git_executable() -> str:
    """Resolve Git or fail with an actionable discovery error."""
    executable = shutil.which("git")
    if executable is None:
        raise GitDiscoveryError("Git executable was not found on PATH.")
    return executable


def run_git(
    repo: Path,
    args: list[str],
    *,
    allow_failure: bool = False,
    input_bytes: bytes | None = None,
) -> subprocess.CompletedProcess[bytes]:
    """Run Git without a shell and preserve its byte-oriented NUL output."""
    result = subprocess.run(  # noqa: S603  # Resolved executable and fixed argument arrays; no shell.
        [git_executable(), *args],
        cwd=repo,
        check=False,
        capture_output=True,
        input=input_bytes,
        stdin=subprocess.DEVNULL if input_bytes is None else None,
    )
    if result.returncode != 0 and not allow_failure:
        detail = decode_git_text(result.stderr).strip() or f"exit code {result.returncode}"
        raise GitDiscoveryError(f"git {' '.join(args)} failed: {detail}")
    return result


def decode_git_text(value: bytes) -> str:
    """Decode Git path and diagnostic bytes without losing undecodable bytes."""
    return value.decode("utf-8", errors="surrogateescape")


def parse_rev_parse_commit(value: bytes, reference: str) -> str:
    """Validate exactly one successful full commit object ID without assuming its hash algorithm."""
    lines = decode_git_text(value).splitlines()
    if (
        len(lines) != 1
        or len(lines[0]) not in REV_PARSE_OBJECT_LENGTHS
        or REV_PARSE_OBJECT_PATTERN.fullmatch(lines[0]) is None
    ):
        raise GitDiscoveryError(f"git rev-parse returned malformed commit output for {reference!r}.")
    return lines[0].lower()


def resolve_commit(repo: Path, reference: str) -> str | None:
    """Resolve one optional commit reference, surfacing errors other than absence."""
    args = ["rev-parse", "--verify", "--quiet", f"{reference}^{{commit}}"]
    result = run_git(repo, args, allow_failure=True)
    if result.returncode == 1:
        return None
    if result.returncode != 0:
        detail = decode_git_text(result.stderr).strip() or f"exit code {result.returncode}"
        raise GitDiscoveryError(f"git {' '.join(args)} failed: {detail}")
    return parse_rev_parse_commit(result.stdout, reference)


def resolve_base_commit(repo: Path) -> str | None:
    """Resolve a trusted remote default branch, then the previous local commit."""
    for base_ref in (*REMOTE_BASE_REFS, "HEAD^"):
        resolved = resolve_commit(repo, base_ref)
        if resolved is not None:
            return resolved
    return None


def split_nul_records(value: bytes) -> list[bytes]:
    """Split NUL-delimited Git output and reject a truncated record stream."""
    if not value:
        return []
    if not value.endswith(b"\0"):
        raise GitDiscoveryError("Git returned a non-NUL-terminated path record.")
    return value[:-1].split(b"\0")


def parse_name_status_z(value: bytes) -> list[str]:
    """Parse ``git diff --name-status -z`` including both rename/copy paths."""
    records = split_nul_records(value)
    paths: list[str] = []
    index = 0
    while index < len(records):
        status = decode_git_text(records[index])
        index += 1
        if not status or status[0] not in "ACDMRTUXB":
            raise GitDiscoveryError(f"Git returned an unexpected name-status record: {status!r}")
        path_count = 2 if status[0] in "RC" else 1
        if index + path_count > len(records):
            raise GitDiscoveryError(f"Git returned an incomplete {status!r} name-status record.")
        paths.extend(decode_git_text(path) for path in records[index : index + path_count])
        index += path_count
    return paths


def parse_porcelain_z(value: bytes) -> list[str]:
    """Parse porcelain v1 NUL records without stripping leading status columns."""
    records = split_nul_records(value)
    paths: list[str] = []
    index = 0
    while index < len(records):
        record = records[index]
        index += 1
        if len(record) < PORCELAIN_MIN_RECORD_LENGTH or record[2:PORCELAIN_PATH_OFFSET] != b" ":
            raise GitDiscoveryError(f"Git returned an unexpected porcelain record: {decode_git_text(record)!r}")
        status = decode_git_text(record[:2])
        paths.append(decode_git_text(record[PORCELAIN_PATH_OFFSET:]))
        if "R" in status or "C" in status:
            if index >= len(records):
                raise GitDiscoveryError(f"Git returned an incomplete {status!r} porcelain rename/copy record.")
            paths.append(decode_git_text(records[index]))
            index += 1
    return paths


def committed_changed_files(repo: Path) -> list[str]:
    """Return committed paths, including initial-commit paths and copy sources."""
    base_commit = resolve_base_commit(repo)
    if base_commit is not None:
        result = run_git(
            repo,
            [
                "diff",
                "--name-status",
                "-z",
                "--find-renames",
                "--find-copies-harder",
                f"{base_commit}...HEAD",
                "--",
            ],
        )
        return parse_name_status_z(result.stdout)

    head_commit = resolve_commit(repo, "HEAD")
    if head_commit is None:
        return []
    result = run_git(
        repo,
        [
            "diff-tree",
            "--root",
            "--no-commit-id",
            "-r",
            "--name-status",
            "-z",
            "--find-renames",
            "--find-copies-harder",
            head_commit,
            "--",
        ],
    )
    return parse_name_status_z(result.stdout)


def staged_changed_files(repo: Path) -> list[str]:
    """Return staged paths with reliable rename and harder copy detection."""
    result = run_git(
        repo,
        ["diff", "--cached", "--name-status", "-z", "--find-renames", "--find-copies-harder", "--"],
    )
    return parse_name_status_z(result.stdout)


def git_changed_files(repo: Path) -> list[str]:
    """Return committed, staged, unstaged, deleted, renamed, copied, and untracked paths."""
    inside_work_tree = run_git(repo, ["rev-parse", "--is-inside-work-tree"])
    if decode_git_text(inside_work_tree.stdout).strip() != "true":
        raise GitDiscoveryError(f"Repository is not a Git worktree: {repo}")

    changed_paths = committed_changed_files(repo)
    changed_paths.extend(staged_changed_files(repo))
    status = run_git(repo, ["status", "--porcelain=v1", "-z", "--untracked-files=all"])
    changed_paths.extend(parse_porcelain_z(status.stdout))
    return sorted({normalize_path(path) for path in changed_paths})


def string_object_dict(value: object) -> dict[str, object]:
    """Return a string-keyed object dictionary from dynamic JSON."""
    if not isinstance(value, dict):
        return {}
    return {key: item for key, item in cast("dict[object, object]", value).items() if isinstance(key, str)}


def directory_path(directory: str, name: str) -> str:
    """Join a normalized repository directory and basename."""
    return name if directory == "." else f"{directory}/{name}"


def read_json_object(root: Path, directory: str, name: str) -> dict[str, object]:
    """Read a JSON object, returning an empty object for an absent file."""
    path = resolved_confined_file(root, directory_path(directory, name))
    if path is None:
        return {}
    return string_object_dict(json.loads(path.read_text(encoding="utf-8")))


def read_package_scripts(root: Path, directory: str) -> dict[str, str]:
    """Read directory-scoped package.json scripts as strings."""
    scripts = string_object_dict(read_json_object(root, directory, PACKAGE_JSON).get("scripts"))
    return {key: value for key, value in scripts.items() if isinstance(value, str)}


def read_text(root: Path, directory: str, name: str) -> str:
    """Read a repository file or return an empty string."""
    path = resolved_confined_file(root, directory_path(directory, name))
    if path is None:
        return ""
    return path.read_text(encoding="utf-8")


def normalize_directory(value: str) -> str:
    """Normalize a relative directory, retaining ``.`` for the root."""
    normalized = normalize_path(value)
    return normalized or "."


def changed_names_in_directory(changed_files: list[str], directory: str) -> set[str]:
    """Return direct changed basenames for one repository directory."""
    return {
        PurePosixPath(path).name
        for path in changed_files
        if normalize_directory(str(PurePosixPath(path).parent)) == directory
    }


def candidate_directories(changed_files: list[str]) -> list[str]:
    """Return root plus every changed path ancestor, shallowest first."""
    directories = {"."}
    for changed_file in changed_files:
        parent = PurePosixPath(changed_file).parent
        while str(parent) not in {"", "."}:
            directories.add(normalize_directory(str(parent)))
            parent = parent.parent
    return sorted(directories, key=lambda item: (0 if item == "." else item.count("/") + 1, item))


def directory_exists(root: Path, directory: str) -> bool:
    """Return whether a candidate owner directory survives inside the repository."""
    return resolved_confined_directory(root, directory) is not None


def current_file_names(root: Path, directory: str) -> set[str]:
    """Return direct names of repository-confined files in a surviving directory."""
    path = resolved_confined_directory(root, directory)
    if path is None:
        return set()
    return {
        entry.name
        for entry in path.iterdir()
        if resolved_confined_file(root, directory_path(directory, entry.name)) is not None
    }


def package_manager_major(version: str | None) -> int | None:
    """Parse an exact leading package-manager major without guessing tags or ranges."""
    if version is None:
        return None
    match = PACKAGE_MANAGER_MAJOR_PATTERN.match(version)
    return int(match.group(1)) if match is not None else None


def package_manager_declaration(root: Path, directory: str) -> PackageManagerDeclaration | None:
    """Read a supported Node package manager and its optional declared major."""
    value = read_json_object(root, directory, PACKAGE_JSON).get("packageManager")
    if not isinstance(value, str):
        return None
    manager, separator, version = value.partition("@")
    normalized_manager = manager.lower()
    if normalized_manager not in NODE_MANAGERS:
        return None
    declared_version = version if separator and version else None
    return PackageManagerDeclaration(
        manager=normalized_manager,
        version=declared_version,
        version_major=package_manager_major(declared_version),
    )


def yarn_variant(root: Path, directory: str, declared_version: str | None) -> str:
    """Resolve Yarn classic versus modern behavior from declaration/config/lock metadata."""
    declared_major = package_manager_major(declared_version)
    if declared_major is not None:
        return "classic" if declared_major <= 1 else "modern"
    if path_exists(root, directory_path(directory, YARN_CONFIG)):
        return "modern"
    lock_text = read_text(root, directory, YARN_LOCK)
    if "# yarn lockfile v1" in lock_text:
        return "classic"
    return "modern"


def current_node_marker_names(root: Path, directory: str) -> list[str]:
    """Return current repository-confined Node lock/config marker names."""
    return [
        marker
        for markers in NODE_MARKERS.values()
        for marker in markers
        if path_exists(root, directory_path(directory, marker))
    ]


def npm_version_warnings(root: Path, owner: DependencyOwner) -> list[str]:
    """Warn when npm lock semantics cannot be resolved from the declared major."""
    shrinkwrap = directory_path(owner.cwd, NPM_SHRINKWRAP_JSON)
    if owner.manager != "npm":
        return []
    if owner.version_major is None:
        detail = (
            "npm-shrinkwrap compatibility cannot be determined."
            if path_exists(root, shrinkwrap)
            else "version-dependent npm lock behavior cannot be fully audited."
        )
        return [
            scoped_warning(
                owner.cwd,
                (
                    f"npm major is unknown; {detail} "
                    "A package-lock.json is required for an unambiguous npm ci suggestion."
                ),
            )
        ]
    if path_exists(root, shrinkwrap) and owner.version_major > NPM_SHRINKWRAP_MAX_MAJOR:
        return [
            scoped_warning(
                owner.cwd,
                " ".join(
                    (
                        f"npm {owner.version_major} ignores obsolete npm-shrinkwrap.json;",
                        "migrate the resolution to package-lock.json and remove the shrinkwrap.",
                    )
                ),
            )
        ]
    return []


def choose_node_owner(root: Path, directory: str) -> tuple[DependencyOwner | None, list[str]]:
    """Resolve exactly one current Node owner for a surviving directory."""
    marker_names = current_node_marker_names(root, directory)
    if not path_exists(root, directory_path(directory, PACKAGE_JSON)):
        if not marker_names:
            return (None, [])
        warning = scoped_warning(
            directory,
            " ".join(
                (
                    f"Orphan Node lock/config markers without package.json: {', '.join(marker_names)}.",
                    "They are historical inventory only and cannot define an executable owner.",
                )
            ),
        )
        return (None, [warning])

    declaration = package_manager_declaration(root, directory)
    current_managers = [
        manager for manager, markers in NODE_MARKERS.items() if any(marker in marker_names for marker in markers)
    ]
    warnings: list[str] = []
    if declaration is not None:
        manager = declaration.manager
        conflicts = [candidate for candidate in current_managers if candidate != manager]
        if conflicts:
            warnings.append(
                scoped_warning(
                    directory,
                    " ".join(
                        (
                            f"package.json selects {manager};",
                            f"ignored competing current Node markers for {', '.join(conflicts)}.",
                        )
                    ),
                )
            )
        variant = yarn_variant(root, directory, declaration.version) if manager == "yarn" else None
        version_major = declaration.version_major if manager == "npm" else None
        owner = DependencyOwner(directory, manager, variant, version_major)
        warnings.extend(npm_version_warnings(root, owner))
        return (owner, warnings)
    if not current_managers:
        warnings.append(
            scoped_warning(
                directory,
                (
                    "package.json has no supported packageManager or current Node lock/config; "
                    "no executable owner was selected."
                ),
            )
        )
        return (None, warnings)
    manager = current_managers[0]
    if len(current_managers) > 1:
        warnings.append(
            scoped_warning(
                directory,
                " ".join(
                    (
                        f"Multiple current Node lock/config owners found ({', '.join(current_managers)});",
                        f"selected {manager} by marker precedence.",
                    )
                ),
            )
        )
    variant = yarn_variant(root, directory, None) if manager == "yarn" else None
    owner = DependencyOwner(directory, manager, variant)
    warnings.extend(npm_version_warnings(root, owner))
    return (owner, warnings)


def pyproject_sections(root: Path, directory: str) -> tuple[bool, bool, bool]:
    """Return whether pyproject declares project, uv, and Poetry ownership."""
    text = read_text(root, directory, PYPROJECT_TOML)
    if not text:
        return (False, False, False)
    data = string_object_dict(tomllib.loads(text))
    tool = string_object_dict(data.get("tool"))
    return ("project" in data, "uv" in tool, "poetry" in tool)


def current_requirement_names(root: Path, directory: str) -> list[str]:
    """Return current direct pip-style requirements manifests."""
    disk_directory = resolved_confined_directory(root, directory)
    if disk_directory is None:
        return []
    return sorted(
        path.name
        for path in disk_directory.iterdir()
        if REQUIREMENT_PATTERN.fullmatch(path.name)
        and resolved_confined_file(root, directory_path(directory, path.name)) is not None
    )


def choose_python_owner(root: Path, directory: str) -> tuple[DependencyOwner | None, list[str]]:
    """Resolve exactly one current uv, Poetry, or pip-style owner."""
    pyproject_exists = path_exists(root, directory_path(directory, PYPROJECT_TOML))
    has_project, has_uv_config, has_poetry_config = pyproject_sections(root, directory)
    requirements = current_requirement_names(root, directory)
    has_uv_lock = path_exists(root, directory_path(directory, UV_LOCK))
    has_uv_toml = path_exists(root, directory_path(directory, UV_CONFIG))
    has_poetry_lock = path_exists(root, directory_path(directory, POETRY_LOCK))
    warnings: list[str] = []
    if not pyproject_exists:
        orphan_markers = [
            marker
            for marker, present in (
                (UV_LOCK, has_uv_lock),
                (UV_CONFIG, has_uv_toml),
                (POETRY_LOCK, has_poetry_lock),
            )
            if present
        ]
        if orphan_markers:
            marker_list = ", ".join(orphan_markers)
            warnings.append(
                scoped_warning(
                    directory,
                    " ".join(
                        (
                            f"Orphan uv/Poetry lock/config markers without pyproject.toml: {marker_list}.",
                            "They are historical inventory only and cannot define an executable owner.",
                        )
                    ),
                )
            )
    has_uv = pyproject_exists and (has_uv_config or has_uv_toml or (has_uv_lock and (has_project or not requirements)))
    has_poetry = pyproject_exists and (has_poetry_config or has_poetry_lock)
    precedence = ("poetry", "uv", "pip") if has_poetry_config and not has_uv_config else ("uv", "poetry", "pip")
    presence = {"uv": has_uv, "poetry": has_poetry, "pip": bool(requirements)}
    owners = [manager for manager in precedence if presence[manager]]
    if not owners and path_exists(root, directory_path(directory, PYPROJECT_TOML)):
        owners.append("pip")
    if not owners:
        return (None, warnings)

    manager = owners[0]
    if len(owners) > 1:
        warnings.append(
            scoped_warning(
                directory,
                " ".join(
                    (
                        f"Multiple current Python dependency owners found ({', '.join(owners)});",
                        f"selected {manager} by lock/config precedence.",
                    )
                ),
            )
        )
    return (DependencyOwner(directory, manager), warnings)


def is_ancestor(ancestor: str, directory: str) -> bool:
    """Return whether a normalized directory is an ancestor of another."""
    if ancestor == ".":
        return directory != "."
    return directory.startswith(f"{ancestor}/")


def choose_scoped_node_owner(
    root: Path,
    directory: str,
    ancestor_node_directories: list[str],
) -> tuple[DependencyOwner | None, list[str]]:
    """Resolve a Node owner while enforcing explicit nested owner boundaries."""
    node_owner, node_warnings = choose_node_owner(root, directory)
    ancestor_node = next(
        (ancestor for ancestor in ancestor_node_directories if is_ancestor(ancestor, directory)),
        None,
    )
    package_exists = path_exists(root, directory_path(directory, PACKAGE_JSON))
    declaration = package_manager_declaration(root, directory)
    if ancestor_node is None or not package_exists or declaration is not None or node_owner is None:
        return (node_owner, node_warnings)

    warning = scoped_warning(
        directory,
        " ".join(
            (
                f"Nested Node markers remain under ancestor owner {ancestor_node};",
                "an explicit packageManager declaration is required for an independent owner boundary.",
            )
        ),
    )
    return (None, [warning])


def detect_non_node_owners(root: Path, directory: str) -> tuple[list[DependencyOwner], list[str]]:
    """Detect current Python, Go, Rust, and .NET owners in one directory."""
    owners: list[DependencyOwner] = []
    python_owner, warnings = choose_python_owner(root, directory)
    if python_owner is not None:
        owners.append(python_owner)

    for manager, marker in (("go", GO_MOD), ("rust", CARGO_TOML)):
        if path_exists(root, directory_path(directory, marker)):
            owners.append(DependencyOwner(directory, manager))

    current_names = current_file_names(root, directory)
    if any(name.endswith((DOTNET_PROJECT_SUFFIX, PACKAGES_LOCK_JSON)) for name in current_names):
        owners.append(DependencyOwner(directory, "dotnet"))
    return (owners, warnings)


def detect_dependency_owners(root: Path, changed_files: list[str]) -> tuple[list[DependencyOwner], list[str]]:
    """Detect executable owners only from surviving directories and current files."""
    owners: list[DependencyOwner] = []
    warnings: list[str] = []
    ancestor_node_directories: list[str] = []
    for directory in candidate_directories(changed_files):
        if not directory_exists(root, directory):
            continue
        node_owner, node_warnings = choose_scoped_node_owner(root, directory, ancestor_node_directories)
        warnings.extend(node_warnings)
        if node_owner is not None:
            owners.append(node_owner)
            ancestor_node_directories.append(directory)

        non_node_owners, non_node_warnings = detect_non_node_owners(root, directory)
        owners.extend(non_node_owners)
        warnings.extend(non_node_warnings)

    if any(
        changed_path_is_confined(root, path)
        and (path.startswith(".github/workflows/") or path == ".github/dependabot.yml")
        for path in changed_files
    ):
        owners.append(DependencyOwner(".", "github-actions"))

    ordered = sorted(
        set(owners),
        key=lambda owner: (
            0 if owner.cwd == "." else owner.cwd.count("/") + 1,
            owner.cwd,
            MANAGER_SORT_ORDER[owner.manager],
            owner.variant or "",
            owner.version_major if owner.version_major is not None else -1,
        ),
    )
    return (ordered, dedupe(warnings))


def public_manager(manager: str) -> str:
    """Preserve the legacy Python ecosystem label."""
    return "python" if manager in {"uv", "pip"} else manager


def scoped_warning(directory: str, warning: str) -> str:
    """Prefix nested warnings with their current owning directory."""
    return warning if directory == "." else f"{directory}: {warning}"


def node_marker_inventory(
    root: Path,
    directory: str,
    evidence_names: set[str],
) -> list[str]:
    """Return current or historical Node markers for the legacy inventory."""
    declaration = package_manager_declaration(root, directory)
    managers = [
        manager for manager, markers in NODE_MARKERS.items() if any(marker in evidence_names for marker in markers)
    ]
    inventory = [declaration.manager] if declaration is not None else []
    inventory.extend(managers)
    if not inventory and PACKAGE_JSON in evidence_names:
        inventory.append("npm")
    return dedupe(inventory)


def python_marker_inventory(
    directory: str,
    evidence_names: set[str],
    owners: list[DependencyOwner],
) -> list[str]:
    """Return current or historical Python markers for the legacy inventory."""
    selected = [
        public_manager(owner.manager)
        for owner in owners
        if owner.cwd == directory and owner.manager in {"uv", "poetry", "pip"}
    ]
    inventory = list(selected)
    if POETRY_LOCK in evidence_names:
        inventory.append("poetry")
    has_python_marker = bool({PYPROJECT_TOML, UV_LOCK, UV_CONFIG} & evidence_names) or any(
        DEPENDENCY_REQUIREMENT_PATTERN.fullmatch(name) for name in evidence_names
    )
    if has_python_marker:
        inventory.append("python")
    return dedupe(inventory)


def marker_inventory(root: Path, changed_files: list[str], owners: list[DependencyOwner]) -> list[str]:
    """Build the legacy current-and-historical marker inventory without implying ownership."""
    inventory: list[str] = []
    for directory in candidate_directories(changed_files):
        changed_names = changed_names_in_directory(changed_files, directory)
        current_names = current_file_names(root, directory)
        evidence_names = changed_names | current_names
        inventory.extend(node_marker_inventory(root, directory, evidence_names))
        inventory.extend(python_marker_inventory(directory, evidence_names, owners))

        for manager, marker in (("go", GO_MOD), ("rust", CARGO_TOML)):
            if marker in evidence_names:
                inventory.append(manager)
        if any(name.endswith((DOTNET_PROJECT_SUFFIX, PACKAGES_LOCK_JSON)) for name in evidence_names):
            inventory.append("dotnet")

    if any(owner.manager == "github-actions" for owner in owners):
        inventory.append("github-actions")
    return dedupe(inventory)


def command_spec(cwd: str, *argv: str) -> CommandSpec:
    """Create one non-empty shell-free command specification."""
    if not argv or any(not argument for argument in argv):
        raise ValueError("Command specifications require non-empty argv entries.")
    return CommandSpec(cwd=cwd, argv=argv)


def powershell_quote(value: str) -> str:
    """Quote one PowerShell 7 token when bare token syntax is unsafe."""
    if SAFE_POWERSHELL_TOKEN.fullmatch(value) is not None:
        return value
    return f"'{value.replace("'", "''")}'"


def powershell_literal(value: str) -> str:
    """Render an unconditionally literal PowerShell 7 single-quoted string."""
    return f"'{value.replace("'", "''")}'"


def render_powershell(command: CommandSpec) -> str:
    """Render one legacy command for PowerShell 7 only."""
    invocation = " ".join(powershell_quote(argument) for argument in command.argv)
    if command.cwd == ".":
        return invocation
    cwd = powershell_literal(command.cwd)
    return f"Push-Location -LiteralPath {cwd}; try {{ {invocation} }} finally {{ Pop-Location }}"


def current_requirements_for_owner(root: Path, owner: DependencyOwner) -> list[str]:
    """Return current requirements files for one pip-style owner."""
    return current_requirement_names(root, owner.cwd)


def frozen_install_locks(owner: DependencyOwner) -> tuple[str, ...] | None:
    """Return locks supported by the selected manager/version for frozen installation."""
    if owner.manager == "npm" and owner.version_major is not None and owner.version_major <= NPM_SHRINKWRAP_MAX_MAJOR:
        return (PACKAGE_LOCK_JSON, NPM_SHRINKWRAP_JSON)
    return FROZEN_INSTALL_LOCKS.get(owner.manager)


def install_argv_for_owner(root: Path, owner: DependencyOwner) -> list[str] | None:
    """Return frozen-install argv only when its current lock survives."""
    if owner.manager == "pip":
        requirements = current_requirements_for_owner(root, owner)
        if requirements:
            preferred = "requirements-dev.txt" if "requirements-dev.txt" in requirements else requirements[0]
            return ["python", "-m", "pip", "install", "-r", preferred]
        return None

    required_locks = frozen_install_locks(owner)
    if required_locks is None or not any(path_exists(root, directory_path(owner.cwd, lock)) for lock in required_locks):
        return None
    if owner.manager == "yarn":
        if owner.variant == "classic":
            return ["yarn", "install", "--frozen-lockfile"]
        return ["yarn", "install", "--immutable"]
    commands = {
        "npm": ["npm", "ci"],
        "pnpm": ["pnpm", "install", "--frozen-lockfile"],
        "bun": ["bun", "install", "--frozen-lockfile"],
        "uv": ["uv", "sync", "--frozen"],
        "poetry": ["poetry", "sync"],
    }
    return commands.get(owner.manager)


def build_install_command_specs(root: Path, owners: list[DependencyOwner]) -> list[CommandSpec]:
    """Build shell-free validation install commands from surviving locks only."""
    commands: list[CommandSpec] = []
    for owner in owners:
        if not directory_exists(root, owner.cwd):
            continue
        argv = install_argv_for_owner(root, owner)
        if argv is not None:
            commands.append(command_spec(owner.cwd, *argv))
    return dedupe_specs(commands)


def node_script_argv(manager: str, script: str) -> list[str]:
    """Return the native package-manager argv for one package script."""
    if manager == "yarn":
        return ["yarn", script]
    return [manager, "run", script]


def node_validation_command_specs(root: Path, owner: DependencyOwner) -> list[CommandSpec]:
    """Return validation commands exposed by one Node package owner."""
    scripts = read_package_scripts(root, owner.cwd)
    return [
        command_spec(owner.cwd, *node_script_argv(owner.manager, script))
        for script in NODE_SCRIPT_PRIORITY
        if script in scripts
    ]


def python_validation_command_specs(root: Path, owner: DependencyOwner) -> list[CommandSpec]:
    """Return validation commands supported by one Python package owner."""
    pyproject = read_text(root, owner.cwd, PYPROJECT_TOML)
    commands: list[CommandSpec] = []
    if "[tool.ruff" in pyproject:
        commands.append(command_spec(owner.cwd, "ruff", "check", "."))
        commands.append(command_spec(owner.cwd, "ruff", "format", "--check", "."))
    if "[tool.mypy" in pyproject:
        commands.append(command_spec(owner.cwd, "mypy"))
    if "[tool.pyright" in pyproject:
        commands.append(command_spec(owner.cwd, "pyright"))
    if "[tool.pytest" in pyproject or path_exists(root, directory_path(owner.cwd, "pytest.ini")):
        commands.append(command_spec(owner.cwd, "pytest"))
    commands.append(command_spec(owner.cwd, "python", "-m", "compileall", "-q", "-x", r"[\\/]\.", "."))
    return commands


def validation_command_specs_for_owner(root: Path, owner: DependencyOwner) -> list[CommandSpec]:
    """Return shell-free validation commands for one current owner."""
    commands: list[CommandSpec] = []
    if owner.manager in NODE_MANAGERS:
        commands.extend(node_validation_command_specs(root, owner))
    if owner.manager in {"uv", "poetry", "pip"}:
        commands.extend(python_validation_command_specs(root, owner))
    generic = MANAGER_VALIDATION_ARGV.get(owner.manager)
    if generic is not None:
        commands.append(command_spec(owner.cwd, *generic))
    return commands


def build_validation_command_specs(root: Path, owners: list[DependencyOwner]) -> list[CommandSpec]:
    """Build shell-free validation commands for each surviving owner."""
    commands: list[CommandSpec] = []
    for owner in owners:
        if not directory_exists(root, owner.cwd):
            continue
        commands.extend(validation_command_specs_for_owner(root, owner))
    return dedupe_specs(commands)


def yarn_update_argv(owner: DependencyOwner) -> list[str]:
    """Return the generation-appropriate Yarn update command."""
    if owner.variant == "classic":
        return ["yarn", "upgrade", "--latest"]
    return ["yarn", "upgrade-interactive"]


def node_update_command_specs(root: Path, owner: DependencyOwner) -> list[CommandSpec]:
    """Return direct update scripts exposed by one Node package owner."""
    scripts = read_package_scripts(root, owner.cwd)
    return [
        command_spec(owner.cwd, *node_script_argv(owner.manager, script))
        for script in DIRECT_UPDATE_SCRIPTS
        if script in scripts
    ]


def update_argv_for_owner(root: Path, owner: DependencyOwner) -> list[str] | None:
    """Return the manager-native update argv for one current owner."""
    manager_argv = MANAGER_UPDATE_ARGV.get(owner.manager)
    argv = list(manager_argv) if manager_argv is not None else None
    if owner.manager == "yarn":
        return yarn_update_argv(owner)
    if owner.manager == "pip":
        requirements = current_requirements_for_owner(root, owner)
        if requirements:
            return ["python", "-m", "pip", "install", "--upgrade", "-r", requirements[0]]
    return argv


def update_command_specs_for_owner(root: Path, owner: DependencyOwner) -> list[CommandSpec]:
    """Return shell-free update commands for one current owner."""
    commands = node_update_command_specs(root, owner) if owner.manager in NODE_MANAGERS else []
    argv = update_argv_for_owner(root, owner)
    if argv is not None:
        commands.append(command_spec(owner.cwd, *argv))
    return commands


def build_update_command_specs(
    root: Path,
    owners: list[DependencyOwner],
    *,
    include_update_commands: bool,
) -> list[CommandSpec]:
    """Build optional shell-free mutating update commands."""
    if not include_update_commands:
        return []

    commands: list[CommandSpec] = []
    for owner in owners:
        if not directory_exists(root, owner.cwd):
            continue
        commands.extend(update_command_specs_for_owner(root, owner))
    return dedupe_specs(commands)


def manifest_and_lock_names(owner: DependencyOwner, changed_names: set[str]) -> tuple[set[str], set[str]]:
    """Return manager-specific manifest and lock names used by warning checks."""
    if owner.manager in NODE_MANAGERS:
        return ({PACKAGE_JSON}, set(frozen_install_locks(owner) or ()))
    if owner.manager == "dotnet":
        manifests = {name for name in changed_names if name.endswith(DOTNET_PROJECT_SUFFIX)} | {
            "Directory.Packages.props"
        }
        return (manifests, {PACKAGES_LOCK_JSON})
    names_by_manager = {
        "uv": ({PYPROJECT_TOML, UV_CONFIG}, {UV_LOCK}),
        "poetry": ({PYPROJECT_TOML}, {POETRY_LOCK}),
        "go": ({GO_MOD}, {"go.sum"}),
        "rust": ({CARGO_TOML}, {"Cargo.lock"}),
    }
    return names_by_manager.get(owner.manager, (set(), set()))


def context_change_warnings(root: Path, owner: DependencyOwner, changed_files: list[str]) -> list[str]:
    """Return manifest/lock consistency warnings for one current owner."""
    names = changed_names_in_directory(changed_files, owner.cwd) & current_file_names(root, owner.cwd)
    manifest_names, lock_names = manifest_and_lock_names(owner, names)
    manifest_changed = bool(names & manifest_names)
    lock_changed = bool(names & lock_names)
    warnings: list[str] = []
    if lock_changed and not manifest_changed:
        warnings.append(
            scoped_warning(
                owner.cwd,
                "Lockfile-only change: verify this dependency resolution change is intentional.",
            )
        )
    if manifest_changed and not lock_changed:
        warnings.append(
            scoped_warning(
                owner.cwd,
                "Manifest changed without an obvious lockfile change; confirm repository lockfile policy.",
            )
        )
    return warnings


def missing_frozen_lock_warning(root: Path, owner: DependencyOwner) -> str | None:
    """Warn when a declared owner lacks the surviving lock required for frozen installation."""
    required_locks = frozen_install_locks(owner)
    if required_locks is None or any(path_exists(root, directory_path(owner.cwd, lock)) for lock in required_locks):
        return None
    lock_list = " or ".join(required_locks)
    return scoped_warning(
        owner.cwd,
        f"{owner.manager} owner has no surviving {lock_list}; no frozen install command was suggested.",
    )


def build_warnings(
    root: Path,
    changed_files: list[str],
    owners: list[DependencyOwner],
    resolution_warnings: list[str],
    *,
    include_update_commands: bool,
) -> list[str]:
    """Build directory-aware dependency-update risk warnings."""
    warnings = list(resolution_warnings)
    external_paths = [path for path in changed_files if not changed_path_is_confined(root, path)]
    if external_paths:
        warnings.append(
            " ".join(
                (
                    f"Changed paths resolve outside the repository root: {', '.join(external_paths)}.",
                    "They remain historical evidence only; no executable owner or command may use them.",
                )
            )
        )
    for owner in owners:
        warnings.extend(context_change_warnings(root, owner, changed_files))
        missing_lock = missing_frozen_lock_warning(root, owner)
        if missing_lock is not None:
            warnings.append(missing_lock)

    removed_surfaces = [
        path
        for path in changed_files
        if is_dependency_surface(path) and changed_path_is_confined(root, path) and not path_exists(root, path)
    ]
    if removed_surfaces:
        warnings.append(
            " ".join(
                (
                    f"Dependency surfaces deleted or renamed away: {', '.join(removed_surfaces)}.",
                    "They are historical evidence only; verify the surviving owner and lockfile.",
                )
            )
        )
    if any(owner.manager == "github-actions" for owner in owners):
        warnings.append(
            "Workflow/Dependabot config changed; verify action inputs and permissions against current action metadata."
        )
    if not include_update_commands:
        warnings.append(
            "Mutating update commands omitted; pass --include-update-commands only when update mode is approved."
        )
    return dedupe(warnings)


def is_dependency_surface(path: str) -> bool:
    """Return whether a changed path represents a dependency manifest or lock/config file."""
    name = PurePosixPath(path).name
    return name in DEPENDENCY_SURFACE_NAMES or DEPENDENCY_REQUIREMENT_PATTERN.fullmatch(name) is not None


def build_audit(
    repo: Path,
    changed_files: list[str],
    *,
    include_update_commands: bool,
) -> DependencyUpdateAudit:
    """Build a dependency-update audit."""
    repo = repo.resolve(strict=True)
    normalized_files = sorted({normalize_path(path) for path in changed_files})
    owners, resolution_warnings = detect_dependency_owners(repo, normalized_files)
    install_specs = build_install_command_specs(repo, owners)
    update_specs = build_update_command_specs(repo, owners, include_update_commands=include_update_commands)
    validation_specs = build_validation_command_specs(repo, owners)
    return DependencyUpdateAudit(
        changed_files=normalized_files,
        install_command_specs=install_specs,
        install_commands=[render_powershell(command) for command in install_specs],
        legacy_command_shell=LEGACY_COMMAND_SHELL,
        owners=owners,
        package_managers=marker_inventory(repo, normalized_files, owners),
        repository=str(repo),
        update_command_specs=update_specs,
        update_commands=[render_powershell(command) for command in update_specs],
        validation_command_specs=validation_specs,
        validation_commands=[render_powershell(command) for command in validation_specs],
        warnings=build_warnings(
            repo,
            normalized_files,
            owners,
            resolution_warnings,
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


def dedupe_specs(values: list[CommandSpec]) -> list[CommandSpec]:
    """Return command specifications in first-seen order without duplicates."""
    seen: set[CommandSpec] = set()
    result: list[CommandSpec] = []
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
        "--changed-file",
        action="append",
        default=[],
        type=validate_changed_file,
        help="Normalized repository-relative changed file. Can be repeated; skips Git discovery.",
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
    write_line(f"legacy command shell: {audit.legacy_command_shell}")
    write_list("package manager marker inventory", audit.package_managers)
    write_owner_list("current owners", audit.owners)
    write_list("changed files", audit.changed_files)
    write_command_specs("install command specs", audit.install_command_specs)
    write_list("install commands (legacy PowerShell 7)", audit.install_commands)
    write_command_specs("validation command specs", audit.validation_command_specs)
    write_list("validation commands (legacy PowerShell 7)", audit.validation_commands)
    write_command_specs("update command specs", audit.update_command_specs)
    write_list("update commands (legacy PowerShell 7)", audit.update_commands)
    write_list("warnings", audit.warnings)


def write_owner_list(label: str, owners: list[DependencyOwner]) -> None:
    """Write structured owners as compact JSON entries."""
    write_line(f"{label}:")
    if not owners:
        write_line(EMPTY_LIST_ENTRY)
        return
    for owner in owners:
        write_line(f"  - {json.dumps(asdict(owner), ensure_ascii=False)}")


def write_command_specs(label: str, commands: list[CommandSpec]) -> None:
    """Write structured commands as compact JSON entries."""
    write_line(f"{label}:")
    if not commands:
        write_line(EMPTY_LIST_ENTRY)
        return
    for command in commands:
        write_line(f"  - {json.dumps(asdict(command), ensure_ascii=False)}")


def write_list(label: str, values: list[str]) -> None:
    """Write a labelled list."""
    write_line(f"{label}:")
    if not values:
        write_line(EMPTY_LIST_ENTRY)
        return
    for value in values:
        write_line(f"  - {value}")


def write_line(text: str) -> None:
    """Write text while escaping surrogateescape code points from arbitrary Git bytes."""
    safe_text = text.encode("utf-8", errors="backslashreplace").decode("utf-8")
    _ = sys.stdout.write(f"{safe_text}\n")


def write_error_line(text: str) -> None:
    """Write surrogate-safe diagnostics to stderr."""
    safe_text = text.encode("utf-8", errors="backslashreplace").decode("utf-8")
    _ = sys.stderr.write(f"{safe_text}\n")


def main() -> int:
    """Run the audit."""
    args = parse_args()
    repo = cast("Path", args.repository)
    try:
        changed_files = cast("list[str]", args.changed_file) or git_changed_files(repo)
    except GitDiscoveryError as error:
        write_error_line(f"Git discovery failed: {error}")
        return 2
    audit = build_audit(
        repo,
        changed_files,
        include_update_commands=bool(args.include_update_commands),
    )

    if args.json:
        write_line(json.dumps(asdict(audit), indent=2, ensure_ascii=True))
    else:
        print_text(audit)

    return 0


if __name__ == "__main__":
    sys.exit(main())
