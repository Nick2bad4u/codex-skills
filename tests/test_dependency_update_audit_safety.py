# Copyright (c) 2026 Nick2bad4u
"""Safety and ownership regression tests for the dependency-update auditor."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest

if TYPE_CHECKING:
    from collections.abc import Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
AUDIT_SCRIPT = REPO_ROOT / "skills" / "dependency-update-maintenance" / "scripts" / "audit_dependency_update.py"
GIT_DISCOVERY_ERROR_EXIT = 2
ARGPARSE_ERROR_EXIT = 2
SHA256_HEX_LENGTH = 64
NPM_12_MAJOR = 12


@dataclass(frozen=True)
class PythonOwnerCase:
    """Expected resolution for one isolated Python dependency owner."""

    owner: str
    pyproject: str
    marker: str
    extra_file: str
    install_argv: tuple[str, ...]
    update_argv: tuple[str, ...]


@dataclass(frozen=True)
class YarnCase:
    """Expected generation-specific Yarn behavior."""

    version: str | None
    extra_config: str | None
    lock_content: str
    variant: str
    install_argv: tuple[str, ...]
    update_argv: tuple[str, ...]


@dataclass(frozen=True)
class NpmShrinkwrapCase:
    """Expected npm-major-specific shrinkwrap behavior."""

    version: str
    locks: tuple[str, ...]
    expected_major: int | None
    expect_ci: bool
    warning_fragment: str | None


def run_command(
    *args: str,
    cwd: Path | None = None,
    environment: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a deterministic subprocess and retain its output for assertions."""
    return subprocess.run(  # noqa: S603  # Tests use fixed executables and local fixture arguments.
        list(args),
        cwd=cwd,
        check=False,
        capture_output=True,
        env=environment,
        stdin=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
    )


def run_git(repository: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run Git in one temporary fixture repository."""
    return run_command("git", *args, cwd=repository)


def checked_git(repository: Path, *args: str) -> str:
    """Run Git and return stdout after asserting success."""
    result = run_git(repository, *args)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def initialize_repository(repository: Path, *, object_format: str | None = None) -> None:
    """Initialize a deterministic local Git repository."""
    repository.mkdir(parents=True, exist_ok=True)
    args = ["init", "--initial-branch=main"]
    if object_format is not None:
        args.append(f"--object-format={object_format}")
    _ = checked_git(repository, *args)
    _ = checked_git(repository, "config", "user.name", "Dependency Audit Tests")
    _ = checked_git(repository, "config", "user.email", "dependency-audit@example.invalid")


def write_file(repository: Path, relative_path: str, content: str = "fixture\n") -> None:
    """Write one UTF-8 fixture file and create its parent directories."""
    path = repository / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(content, encoding="utf-8")


def write_bytes_file(path: bytes, content: bytes = b"fixture\n") -> None:
    """Write a fixture whose POSIX filename may not be valid UTF-8."""
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        _ = os.write(descriptor, content)
    finally:
        os.close(descriptor)


def commit_all(repository: Path, message: str) -> str:
    """Commit all fixture changes and return the commit SHA."""
    _ = checked_git(repository, "add", "--all")
    _ = checked_git(repository, "commit", "--message", message)
    return checked_git(repository, "rev-parse", "HEAD")


def set_origin_main(repository: Path, commit: str) -> None:
    """Set a local trusted remote-tracking base without requiring a real remote."""
    _ = checked_git(repository, "update-ref", "refs/remotes/origin/main", commit)


def as_string_list(value: object) -> list[str]:
    """Narrow a dynamic JSON value to a list of strings."""
    assert isinstance(value, list)
    items = cast("list[object]", value)
    assert all(isinstance(item, str) for item in items)
    return [item for item in items if isinstance(item, str)]


def as_object(value: object) -> dict[str, object]:
    """Narrow a dynamic JSON value to a string-keyed object."""
    assert isinstance(value, dict)
    mapping = cast("dict[object, object]", value)
    return {str(key): item for key, item in mapping.items()}


def as_object_list(value: object) -> list[dict[str, object]]:
    """Narrow a dynamic JSON value to a list of string-keyed objects."""
    assert isinstance(value, list)
    return [as_object(item) for item in cast("list[object]", value)]


def command_specs(audit: dict[str, object], field: str) -> list[tuple[str, tuple[str, ...]]]:
    """Return command specs as typed cwd/argv tuples."""
    result: list[tuple[str, tuple[str, ...]]] = []
    for item in as_object_list(audit[field]):
        cwd = item.get("cwd")
        assert isinstance(cwd, str)
        result.append((cwd, tuple(as_string_list(item.get("argv")))))
    return result


def owner_specs(audit: dict[str, object]) -> list[tuple[str, str, str | None]]:
    """Return structured current owners as typed tuples."""
    result: list[tuple[str, str, str | None]] = []
    for item in as_object_list(audit["owners"]):
        cwd = item.get("cwd")
        manager = item.get("manager")
        variant = item.get("variant")
        assert isinstance(cwd, str)
        assert isinstance(manager, str)
        assert variant is None or isinstance(variant, str)
        result.append((cwd, manager, variant))
    return result


def owner_version_major(audit: dict[str, object], manager: str) -> int | None:
    """Return the retained major for one structured current owner."""
    matching = [owner for owner in as_object_list(audit["owners"]) if owner.get("manager") == manager]
    assert len(matching) == 1
    version_major = matching[0].get("version_major")
    assert version_major is None or isinstance(version_major, int)
    return version_major


def audit_result(
    repository: Path,
    *changed_files: str,
    include_update_commands: bool = False,
    environment: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run the auditor and return the raw process result."""
    args = [sys.executable, str(AUDIT_SCRIPT), str(repository)]
    for changed_file in changed_files:
        args.extend(("--changed-file", changed_file))
    if include_update_commands:
        args.append("--include-update-commands")
    args.append("--json")
    return run_command(*args, environment=environment)


def audit_result_bytes(repository: Path, *, json_output: bool) -> subprocess.CompletedProcess[bytes]:
    """Run Git discovery without text decoding so arbitrary path bytes can be inspected."""
    args = [sys.executable, str(AUDIT_SCRIPT), str(repository)]
    if json_output:
        args.append("--json")
    return subprocess.run(  # noqa: S603  # Fixed interpreter and local audited script.
        args,
        check=False,
        capture_output=True,
        stdin=subprocess.DEVNULL,
    )


def audit_repository(
    repository: Path,
    *changed_files: str,
    include_update_commands: bool = False,
    environment: Mapping[str, str] | None = None,
) -> dict[str, object]:
    """Run the auditor and decode its public JSON object."""
    result = audit_result(
        repository,
        *changed_files,
        include_update_commands=include_update_commands,
        environment=environment,
    )
    assert result.returncode == 0, result.stderr
    payload = cast("object", json.loads(result.stdout))
    return as_object(payload)


def test_git_discovery_preserves_every_porcelain_state_and_literal_path(tmp_path: Path) -> None:
    """Discover staged, unstaged, mixed, untracked, deleted, and renamed paths verbatim."""
    initialize_repository(tmp_path)
    tracked_paths = (
        "unstaged modified.txt",
        "unstaged deleted.txt",
        "staged modified.txt",
        "mixed status.txt",
        "café quoted name.txt",
        "rename old.txt",
    )
    for path in tracked_paths:
        write_file(tmp_path, path)
    base = commit_all(tmp_path, "initial fixture")
    set_origin_main(tmp_path, base)

    write_file(tmp_path, "unstaged modified.txt", "unstaged change\n")
    (tmp_path / "unstaged deleted.txt").unlink()
    write_file(tmp_path, "staged modified.txt", "staged change\n")
    _ = checked_git(tmp_path, "add", "--", "staged modified.txt")
    write_file(tmp_path, "mixed status.txt", "staged half\n")
    _ = checked_git(tmp_path, "add", "--", "mixed status.txt")
    with (tmp_path / "mixed status.txt").open("a", encoding="utf-8") as stream:
        _ = stream.write("unstaged half\n")
    write_file(tmp_path, "café quoted name.txt", "literal quoted-path change\n")
    _ = checked_git(tmp_path, "mv", "--", "rename old.txt", "rename new with space.txt")
    write_file(tmp_path, "untracked café with space.txt")

    audit = audit_repository(tmp_path)

    assert set(as_string_list(audit["changed_files"])) == {
        "café quoted name.txt",
        "mixed status.txt",
        "rename new with space.txt",
        "rename old.txt",
        "staged modified.txt",
        "unstaged deleted.txt",
        "unstaged modified.txt",
        "untracked café with space.txt",
    }
    assert command_specs(audit, "update_command_specs") == []


def test_git_discovery_includes_committed_deletion_and_both_rename_sides(tmp_path: Path) -> None:
    """Retain historical paths without turning deleted markers into executable owners."""
    initialize_repository(tmp_path)
    write_file(tmp_path, "package.json", '{"packageManager":"npm@12.0.2"}\n')
    write_file(tmp_path, "package-lock.json", '{"lockfileVersion":3}\n')
    write_file(tmp_path, "requirements.txt", "pytest==9.1.1\n")
    base_commit = commit_all(tmp_path, "base dependency state")
    set_origin_main(tmp_path, base_commit)

    _ = checked_git(tmp_path, "mv", "--", "package-lock.json", "pnpm-lock.yaml")
    _ = checked_git(tmp_path, "rm", "--", "requirements.txt")
    write_file(tmp_path, "package.json", '{"packageManager":"pnpm@10.15.0"}\n')
    _ = commit_all(tmp_path, "rename lock and delete requirements")

    audit = audit_repository(tmp_path)

    assert as_string_list(audit["changed_files"]) == [
        "package-lock.json",
        "package.json",
        "pnpm-lock.yaml",
        "requirements.txt",
    ]
    assert owner_specs(audit) == [(".", "pnpm", None)]
    assert as_string_list(audit["package_managers"]) == ["pnpm", "npm", "python"]
    assert command_specs(audit, "install_command_specs") == [(".", ("pnpm", "install", "--frozen-lockfile"))]
    assert any("historical evidence only" in warning for warning in as_string_list(audit["warnings"]))


def test_git_discovery_errors_are_not_reported_as_zero_changes(tmp_path: Path) -> None:
    """Fail visibly when implicit discovery is requested outside a Git worktree."""
    _ = (tmp_path / ".git").write_text("gitdir: missing-git-directory\n", encoding="utf-8")
    result = audit_result(tmp_path)

    assert result.returncode == GIT_DISCOVERY_ERROR_EXIT
    assert "Git discovery failed:" in result.stderr
    assert "not a git repository" in result.stderr.lower()
    assert result.stdout == ""


@pytest.mark.parametrize(
    "changed_file",
    [
        pytest.param("/absolute/package.json", id="posix-absolute"),
        pytest.param(r"C:\absolute\package.json", id="windows-absolute"),
        pytest.param(r"\\server\share\package.json", id="unc-absolute"),
        pytest.param("../outside/package.json", id="parent"),
        pytest.param("nested/../../outside/package.json", id="nested-parent"),
        pytest.param("line\nbreak/package.json", id="newline"),
        pytest.param("tab\tbreak/package.json", id="tab"),
        pytest.param(".", id="empty-normalized"),
    ],
)
def test_explicit_changed_files_reject_unsafe_paths(tmp_path: Path, changed_file: str) -> None:
    """Reject explicit paths that are absolute, traversing, empty, or contain controls."""
    result = audit_result(tmp_path, changed_file)

    assert result.returncode == ARGPARSE_ERROR_EXIT
    assert "changed files must" in result.stderr.lower()
    assert result.stdout == ""


def test_explicit_changed_files_are_normalized(tmp_path: Path) -> None:
    """Normalize harmless dot components and Windows separators before auditing."""
    write_file(tmp_path, "nested/package.json", '{"packageManager":"npm@12.0.2"}\n')

    audit = audit_repository(tmp_path, r".\nested\.\package.json")

    assert as_string_list(audit["changed_files"]) == ["nested/package.json"]
    assert owner_specs(audit) == [("nested", "npm", None)]


def test_structured_commands_contain_adversarial_paths_without_shell_interpolation(tmp_path: Path) -> None:
    """Keep repository-controlled metacharacters in cwd/argv data and quote legacy PowerShell safely."""
    directory = "packages/space café $() `tick; & 'quoted'"
    requirement = "requirements-$() `tick; & 'café file.txt"
    relative_requirement = f"{directory}/{requirement}"
    write_file(tmp_path, relative_requirement, "pytest==9.1.1\n")

    audit = audit_repository(tmp_path, relative_requirement, include_update_commands=True)

    assert audit["legacy_command_shell"] == "PowerShell 7"
    assert owner_specs(audit) == [(directory, "pip", None)]
    assert command_specs(audit, "install_command_specs") == [
        (directory, ("python", "-m", "pip", "install", "-r", requirement))
    ]
    assert command_specs(audit, "update_command_specs") == [
        (directory, ("python", "-m", "pip", "install", "--upgrade", "-r", requirement))
    ]
    expected_cwd = "'packages/space café $() `tick; & ''quoted'''"
    expected_requirement = "'requirements-$() `tick; & ''café file.txt'"
    assert as_string_list(audit["install_commands"]) == [
        " ".join(
            (
                f"Push-Location -LiteralPath {expected_cwd};",
                f"try {{ python -m pip install -r {expected_requirement} }}",
                "finally { Pop-Location }",
            )
        )
    ]


def test_external_directory_symlink_is_historical_only_even_in_update_mode(tmp_path: Path) -> None:
    """Reject an external symlink target as an owner while retaining its changed markers."""
    repository = tmp_path / "repository"
    outside = tmp_path / "outside"
    repository.mkdir()
    write_file(outside, "package.json", '{"packageManager":"npm@12.0.2"}\n')
    write_file(outside, "package-lock.json", '{"lockfileVersion":3}\n')
    (outside / "deleted").mkdir()
    linked_directory = repository / "linked project"
    try:
        linked_directory.symlink_to(outside, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"Directory symlinks are unavailable: {error}")

    audit = audit_repository(
        repository,
        "linked project/package.json",
        "linked project/package-lock.json",
        "linked project/deleted/package-lock.json",
        include_update_commands=True,
    )

    assert owner_specs(audit) == []
    assert as_string_list(audit["package_managers"]) == ["npm"]
    assert "linked project/deleted/package-lock.json" in as_string_list(audit["changed_files"])
    assert command_specs(audit, "install_command_specs") == []
    assert command_specs(audit, "validation_command_specs") == []
    assert command_specs(audit, "update_command_specs") == []
    assert any(
        "linked project/deleted/package-lock.json" in warning and "resolve outside the repository root" in warning
        for warning in as_string_list(audit["warnings"])
    )


@pytest.mark.skipif(os.name != "nt", reason="Windows junctions are reparse-point-specific.")
def test_external_windows_junction_is_historical_only_even_in_update_mode(tmp_path: Path) -> None:
    """Reject an external Windows junction/reparse point as every executable command cwd."""
    repository = tmp_path / "repository"
    outside = tmp_path / "outside"
    repository.mkdir()
    write_file(outside, "package.json", '{"packageManager":"pnpm@10.15.0"}\n')
    write_file(outside, "pnpm-lock.yaml")
    junction = repository / "junction project"
    creation = run_command("cmd.exe", "/d", "/c", "mklink", "/J", str(junction), str(outside))
    assert creation.returncode == 0, creation.stderr
    try:
        audit = audit_repository(
            repository,
            "junction project/package.json",
            "junction project/pnpm-lock.yaml",
            include_update_commands=True,
        )

        assert owner_specs(audit) == []
        assert as_string_list(audit["package_managers"]) == ["pnpm"]
        assert command_specs(audit, "install_command_specs") == []
        assert command_specs(audit, "validation_command_specs") == []
        assert command_specs(audit, "update_command_specs") == []
        assert any("resolve outside the repository root" in warning for warning in as_string_list(audit["warnings"]))
    finally:
        junction.rmdir()


def test_initial_commit_is_compared_against_empty_tree(tmp_path: Path) -> None:
    """Discover committed dependency files in a SHA-1 repository with no parent or origin base."""
    initialize_repository(tmp_path)
    write_file(tmp_path, "package.json", '{"packageManager":"npm@12.0.2"}\n')
    write_file(tmp_path, "package-lock.json", '{"lockfileVersion":3}\n')
    _ = commit_all(tmp_path, "initial dependency commit")

    audit = audit_repository(tmp_path)

    assert as_string_list(audit["changed_files"]) == ["package-lock.json", "package.json"]
    assert command_specs(audit, "install_command_specs") == [(".", ("npm", "ci"))]


def test_sha256_repository_commit_discovery(tmp_path: Path) -> None:
    """Accept SHA-256 commit IDs and discover an initial commit against the empty tree."""
    initialize_repository(tmp_path, object_format="sha256")
    write_file(tmp_path, "package.json", '{"packageManager":"npm@12.0.2"}\n')
    write_file(tmp_path, "package-lock.json", '{"lockfileVersion":3}\n')
    commit = commit_all(tmp_path, "initial SHA-256 dependency commit")
    assert len(commit) == SHA256_HEX_LENGTH

    audit = audit_repository(tmp_path)

    assert as_string_list(audit["changed_files"]) == ["package-lock.json", "package.json"]
    assert command_specs(audit, "install_command_specs") == [(".", ("npm", "ci"))]


def test_no_origin_uses_head_parent(tmp_path: Path) -> None:
    """Use HEAD^ when a repository has commits but no remote-tracking base."""
    initialize_repository(tmp_path)
    write_file(tmp_path, "package.json", '{"packageManager":"npm@12.0.2"}\n')
    write_file(tmp_path, "package-lock.json", '{"lockfileVersion":3}\n')
    _ = commit_all(tmp_path, "base")
    write_file(tmp_path, "package-lock.json", '{"lockfileVersion":3,"changed":true}\n')
    _ = commit_all(tmp_path, "change lock")

    audit = audit_repository(tmp_path)

    assert as_string_list(audit["changed_files"]) == ["package-lock.json"]


def test_malformed_successful_rev_parse_output_fails_discovery(tmp_path: Path) -> None:
    """Reject a successful rev-parse response containing more than one object ID."""
    repository = tmp_path / "repository"
    repository.mkdir()
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    first_hash = "0" * 40
    second_hash = "1" * 40
    if os.name == "nt":
        write_file(
            fake_bin,
            "git.cmd",
            "\n".join(
                (
                    "@echo off",
                    'if "%~1"=="rev-parse" if "%~2"=="--is-inside-work-tree" (echo true& exit /b 0)',
                    f'if "%~1"=="rev-parse" (echo {first_hash}& echo {second_hash}& exit /b 0)',
                    "exit /b 1",
                )
            ),
        )
    else:
        write_file(
            fake_bin,
            "git",
            "\n".join(
                (
                    "#!/bin/sh",
                    'if [ "$1" = "rev-parse" ] && [ "$2" = "--is-inside-work-tree" ]; then echo true; exit 0; fi',
                    f'if [ "$1" = "rev-parse" ]; then echo {first_hash}; echo {second_hash}; exit 0; fi',
                    "exit 1",
                )
            ),
        )
        (fake_bin / "git").chmod(0o755)
    environment = dict(os.environ)
    environment["PATH"] = f"{fake_bin}{os.pathsep}{environment.get('PATH', '')}"

    result = audit_result(repository, environment=environment)

    assert result.returncode == GIT_DISCOVERY_ERROR_EXIT
    assert "malformed commit output" in result.stderr


def test_committed_copy_detection_preserves_source_and_destination(tmp_path: Path) -> None:
    """Use harder copy detection for committed copies with spaces and Unicode."""
    initialize_repository(tmp_path)
    source = "source café with space.txt"
    destination = "committed copy café with space.txt"
    write_file(tmp_path, source, "copy-identical-content\n")
    base = commit_all(tmp_path, "copy source")
    set_origin_main(tmp_path, base)
    write_file(tmp_path, destination, (tmp_path / source).read_text(encoding="utf-8"))
    _ = commit_all(tmp_path, "committed copy")

    audit = audit_repository(tmp_path)

    assert as_string_list(audit["changed_files"]) == [destination, source]


def test_staged_copy_detection_preserves_source_and_destination(tmp_path: Path) -> None:
    """Use a NUL-delimited staged diff to retain both sides of a staged copy."""
    initialize_repository(tmp_path)
    source = "staged source café with space.txt"
    destination = "staged copy café with space.txt"
    write_file(tmp_path, source, "copy-identical-content\n")
    base = commit_all(tmp_path, "copy source")
    set_origin_main(tmp_path, base)
    write_file(tmp_path, destination, (tmp_path / source).read_text(encoding="utf-8"))
    _ = checked_git(tmp_path, "add", "--", destination)

    audit = audit_repository(tmp_path)

    assert as_string_list(audit["changed_files"]) == [destination, source]


@pytest.mark.skipif(os.name == "nt", reason="Windows filenames are Unicode rather than arbitrary byte sequences.")
def test_arbitrary_git_path_bytes_are_valid_json_and_escaped_text(tmp_path: Path) -> None:
    """Round-trip a non-UTF-8 status path through JSON and escape it in text output."""
    initialize_repository(tmp_path)
    write_file(tmp_path, "tracked.txt")
    base = commit_all(tmp_path, "base")
    set_origin_main(tmp_path, base)
    raw_name = b"untracked-\xff.txt"
    raw_path = tmp_path / os.fsdecode(raw_name)
    write_bytes_file(os.fsencode(raw_path))

    json_result = audit_result_bytes(tmp_path, json_output=True)
    text_result = audit_result_bytes(tmp_path, json_output=False)

    assert json_result.returncode == 0, json_result.stderr.decode("utf-8", errors="replace")
    decoded_json = json_result.stdout.decode("utf-8")
    payload = as_object(cast("object", json.loads(decoded_json)))
    assert raw_name in {os.fsencode(path) for path in as_string_list(payload["changed_files"])}
    assert text_result.returncode == 0, text_result.stderr.decode("utf-8", errors="replace")
    assert "untracked-\\udcff.txt" in text_result.stdout.decode("utf-8")


@pytest.mark.skipif(os.name == "nt", reason="Windows filenames are Unicode rather than arbitrary byte sequences.")
def test_arbitrary_git_path_bytes_preserve_both_staged_rename_sides(tmp_path: Path) -> None:
    """Round-trip both raw-byte names in a NUL-delimited staged rename record."""
    initialize_repository(tmp_path)
    source_name = b"source-\xff.txt"
    destination_name = b"destination-\xfe.txt"
    source_path = tmp_path / os.fsdecode(source_name)
    destination_path = tmp_path / os.fsdecode(destination_name)
    write_bytes_file(os.fsencode(source_path))
    base = commit_all(tmp_path, "raw-byte source")
    set_origin_main(tmp_path, base)
    _ = source_path.rename(destination_path)
    _ = checked_git(tmp_path, "add", "--all")

    result = audit_result_bytes(tmp_path, json_output=True)

    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")
    payload = as_object(cast("object", json.loads(result.stdout.decode("utf-8"))))
    changed_bytes = {os.fsencode(path) for path in as_string_list(payload["changed_files"])}
    assert changed_bytes == {source_name, destination_name}


@pytest.mark.parametrize(
    ("manager", "marker", "install_argv", "update_argv"),
    [
        pytest.param("npm", "package-lock.json", ("npm", "ci"), ("npm", "update"), id="npm"),
        pytest.param(
            "pnpm",
            "pnpm-lock.yaml",
            ("pnpm", "install", "--frozen-lockfile"),
            ("pnpm", "update", "--interactive", "--latest"),
            id="pnpm",
        ),
        pytest.param(
            "yarn",
            "yarn.lock",
            ("yarn", "install", "--immutable"),
            ("yarn", "upgrade-interactive"),
            id="yarn-modern",
        ),
        pytest.param(
            "bun",
            "bun.lock",
            ("bun", "install", "--frozen-lockfile"),
            ("bun", "update"),
            id="bun",
        ),
    ],
)
def test_node_package_manager_field_selects_one_owner(
    tmp_path: Path,
    manager: str,
    marker: str,
    install_argv: tuple[str, ...],
    update_argv: tuple[str, ...],
) -> None:
    """Use packageManager for ownership while preserving conflicting marker inventory."""
    version = "4.0.0" if manager == "yarn" else "1.0.0"
    write_file(
        tmp_path,
        "package.json",
        json.dumps({"packageManager": f"{manager}@{version}", "scripts": {"test": "test-command"}}),
    )
    write_file(tmp_path, marker)
    competing_marker = "yarn.lock" if manager == "npm" else "package-lock.json"
    write_file(tmp_path, competing_marker)

    audit = audit_repository(
        tmp_path,
        "package.json",
        marker,
        competing_marker,
        include_update_commands=True,
    )

    expected_variant = "modern" if manager == "yarn" else None
    assert owner_specs(audit) == [(".", manager, expected_variant)]
    assert manager in as_string_list(audit["package_managers"])
    assert command_specs(audit, "install_command_specs") == [(".", install_argv)]
    assert (".", update_argv) in command_specs(audit, "update_command_specs")


def test_package_json_with_npm_lock_falls_back_to_npm(tmp_path: Path) -> None:
    """Use npm as the fallback when package.json has an npm lock and no competing owner."""
    write_file(tmp_path, "package.json", '{"scripts":{"check":"node check.js"}}\n')
    write_file(tmp_path, "package-lock.json", '{"lockfileVersion":3}\n')

    audit = audit_repository(tmp_path, "package.json", "package-lock.json")

    assert owner_specs(audit) == [(".", "npm", None)]
    assert command_specs(audit, "install_command_specs") == [(".", ("npm", "ci"))]
    assert command_specs(audit, "validation_command_specs") == [(".", ("npm", "run", "check"))]


def test_package_json_without_manager_lock_or_config_is_inventory_only(tmp_path: Path) -> None:
    """Do not turn a bare package manifest into an executable npm owner."""
    write_file(tmp_path, "package.json", '{"scripts":{"check":"node check.js"}}\n')

    audit = audit_repository(tmp_path, "package.json", include_update_commands=True)

    assert owner_specs(audit) == []
    assert as_string_list(audit["package_managers"]) == ["npm"]
    assert command_specs(audit, "install_command_specs") == []
    assert command_specs(audit, "validation_command_specs") == []
    assert command_specs(audit, "update_command_specs") == []
    assert any("no executable owner was selected" in warning for warning in as_string_list(audit["warnings"]))


@pytest.mark.parametrize(
    "case",
    [
        pytest.param(
            YarnCase(
                version="1.22.22",
                extra_config=None,
                lock_content="# yarn lockfile v1\n",
                variant="classic",
                install_argv=("yarn", "install", "--frozen-lockfile"),
                update_argv=("yarn", "upgrade", "--latest"),
            ),
            id="declared-classic",
        ),
        pytest.param(
            YarnCase(
                version="4.9.2",
                extra_config=".yarnrc.yml",
                lock_content="__metadata:\n  version: 8\n",
                variant="modern",
                install_argv=("yarn", "install", "--immutable"),
                update_argv=("yarn", "upgrade-interactive"),
            ),
            id="declared-modern",
        ),
        pytest.param(
            YarnCase(
                version=None,
                extra_config=None,
                lock_content="# yarn lockfile v1\n",
                variant="classic",
                install_argv=("yarn", "install", "--frozen-lockfile"),
                update_argv=("yarn", "upgrade", "--latest"),
            ),
            id="lock-classic",
        ),
        pytest.param(
            YarnCase(
                version=None,
                extra_config=".yarnrc.yml",
                lock_content="__metadata:\n  version: 8\n",
                variant="modern",
                install_argv=("yarn", "install", "--immutable"),
                update_argv=("yarn", "upgrade-interactive"),
            ),
            id="config-modern",
        ),
    ],
)
def test_yarn_generation_controls_install_and_update_commands(
    tmp_path: Path,
    case: YarnCase,
) -> None:
    """Preserve Yarn classic versus modern behavior in owners and commands."""
    package_data: dict[str, object] = {}
    if case.version is not None:
        package_data["packageManager"] = f"yarn@{case.version}"
    write_file(tmp_path, "package.json", json.dumps(package_data))
    write_file(tmp_path, "yarn.lock", case.lock_content)
    if case.extra_config is not None:
        write_file(tmp_path, case.extra_config)

    audit = audit_repository(
        tmp_path,
        "package.json",
        "yarn.lock",
        include_update_commands=True,
    )

    assert owner_specs(audit) == [(".", "yarn", case.variant)]
    assert command_specs(audit, "install_command_specs") == [(".", case.install_argv)]
    assert (".", case.update_argv) in command_specs(audit, "update_command_specs")


@pytest.mark.parametrize(
    ("marker", "inventory_manager"),
    [
        pytest.param("package-lock.json", "npm", id="npm"),
        pytest.param("pnpm-lock.yaml", "pnpm", id="pnpm"),
        pytest.param("yarn.lock", "yarn", id="yarn"),
        pytest.param("bun.lock", "bun", id="bun"),
        pytest.param("uv.lock", "python", id="uv"),
        pytest.param("poetry.lock", "poetry", id="poetry"),
    ],
)
def test_lock_only_marker_is_orphan_inventory_without_owner_or_commands(
    tmp_path: Path,
    marker: str,
    inventory_manager: str,
) -> None:
    """Require the ecosystem's current manifest before a lock can define an executable owner."""
    write_file(tmp_path, marker)

    audit = audit_repository(tmp_path, marker, include_update_commands=True)

    assert owner_specs(audit) == []
    assert inventory_manager in as_string_list(audit["package_managers"])
    assert command_specs(audit, "install_command_specs") == []
    assert command_specs(audit, "validation_command_specs") == []
    assert command_specs(audit, "update_command_specs") == []
    assert any("Orphan" in warning for warning in as_string_list(audit["warnings"]))


@pytest.mark.parametrize(
    "case",
    [
        pytest.param(
            PythonOwnerCase(
                owner="uv",
                pyproject='[project]\nname = "uv-project"\nversion = "1.0.0"\n',
                marker="uv.lock",
                extra_file="requirements.txt",
                install_argv=("uv", "sync", "--frozen"),
                update_argv=("uv", "lock", "--upgrade"),
            ),
            id="uv",
        ),
        pytest.param(
            PythonOwnerCase(
                owner="poetry",
                pyproject='[tool.poetry]\nname = "poetry-project"\nversion = "1.0.0"\n',
                marker="poetry.lock",
                extra_file="uv.lock",
                install_argv=("poetry", "sync"),
                update_argv=("poetry", "update"),
            ),
            id="poetry",
        ),
        pytest.param(
            PythonOwnerCase(
                owner="pip",
                pyproject="[tool.pytest.ini_options]\n",
                marker="requirements.txt",
                extra_file="uv.lock",
                install_argv=("python", "-m", "pip", "install", "-r", "requirements.txt"),
                update_argv=("python", "-m", "pip", "install", "--upgrade", "-r", "requirements.txt"),
            ),
            id="requirements",
        ),
    ],
)
def test_python_owners_are_resolved_without_mixed_commands(tmp_path: Path, case: PythonOwnerCase) -> None:
    """Select one current uv, Poetry, or requirements owner and its native commands."""
    write_file(tmp_path, "pyproject.toml", case.pyproject)
    write_file(tmp_path, case.marker)
    write_file(tmp_path, case.extra_file)

    audit = audit_repository(
        tmp_path,
        "pyproject.toml",
        case.marker,
        case.extra_file,
        include_update_commands=True,
    )

    assert owner_specs(audit) == [(".", case.owner, None)]
    assert command_specs(audit, "install_command_specs") == [(".", case.install_argv)]
    assert (".", case.update_argv) in command_specs(audit, "update_command_specs")


def test_deleted_lock_is_inventory_only_and_cannot_emit_frozen_install(tmp_path: Path) -> None:
    """Keep a deleted npm lock as history while executing only from the surviving declaration."""
    initialize_repository(tmp_path)
    write_file(tmp_path, "package.json", '{"packageManager":"npm@12.0.2"}\n')
    write_file(tmp_path, "package-lock.json", '{"lockfileVersion":3}\n')
    base = commit_all(tmp_path, "npm project")
    set_origin_main(tmp_path, base)
    _ = checked_git(tmp_path, "rm", "--", "package-lock.json")

    audit = audit_repository(tmp_path, include_update_commands=True)

    assert owner_specs(audit) == [(".", "npm", None)]
    assert owner_version_major(audit, "npm") == NPM_12_MAJOR
    assert as_string_list(audit["package_managers"]) == ["npm"]
    assert command_specs(audit, "install_command_specs") == []
    assert command_specs(audit, "update_command_specs") == [(".", ("npm", "update"))]
    assert any("no surviving package-lock.json" in warning for warning in as_string_list(audit["warnings"]))
    assert all("Lockfile-only change" not in warning for warning in as_string_list(audit["warnings"]))


def test_competing_node_lock_cannot_satisfy_selected_owner_warning_context(tmp_path: Path) -> None:
    """Do not let a competing manager's changed lock mask the selected owner's unchanged lock."""
    write_file(tmp_path, "package.json", '{"packageManager":"pnpm@10.15.0"}\n')
    write_file(tmp_path, "pnpm-lock.yaml")
    write_file(tmp_path, "package-lock.json", '{"lockfileVersion":3}\n')

    audit = audit_repository(tmp_path, "package.json", "package-lock.json")

    assert owner_specs(audit) == [(".", "pnpm", None)]
    assert any(
        "Manifest changed without an obvious lockfile change" in warning
        for warning in as_string_list(audit["warnings"])
    )


def test_fully_deleted_project_has_no_executable_owner_or_commands(tmp_path: Path) -> None:
    """Treat every marker from a fully deleted nested project as historical inventory only."""
    initialize_repository(tmp_path)
    write_file(tmp_path, "deleted/package.json", '{"packageManager":"pnpm@10.15.0"}\n')
    write_file(tmp_path, "deleted/pnpm-lock.yaml")
    base = commit_all(tmp_path, "nested project")
    set_origin_main(tmp_path, base)
    _ = checked_git(tmp_path, "rm", "-r", "deleted")

    audit = audit_repository(tmp_path, include_update_commands=True)

    assert owner_specs(audit) == []
    assert as_string_list(audit["package_managers"]) == ["pnpm"]
    assert command_specs(audit, "install_command_specs") == []
    assert command_specs(audit, "validation_command_specs") == []
    assert command_specs(audit, "update_command_specs") == []


def test_renamed_project_executes_only_from_surviving_directory(tmp_path: Path) -> None:
    """Keep the old directory historical and scope commands only to the renamed directory."""
    initialize_repository(tmp_path)
    write_file(tmp_path, "old project/package.json", '{"packageManager":"npm@12.0.2"}\n')
    write_file(tmp_path, "old project/package-lock.json", '{"lockfileVersion":3}\n')
    base = commit_all(tmp_path, "old project")
    set_origin_main(tmp_path, base)
    _ = checked_git(tmp_path, "mv", "--", "old project", "new project café")

    audit = audit_repository(tmp_path)

    assert owner_specs(audit) == [("new project café", "npm", None)]
    assert command_specs(audit, "install_command_specs") == [("new project café", ("npm", "ci"))]
    assert all(cwd != "old project" for cwd, _ in command_specs(audit, "install_command_specs"))


@pytest.mark.parametrize("old_owner", ["uv", "poetry"])
def test_python_lock_to_requirements_migration_executes_only_pip(tmp_path: Path, old_owner: str) -> None:
    """Treat deleted uv/Poetry locks as history after migration to requirements/pip."""
    initialize_repository(tmp_path)
    if old_owner == "uv":
        old_pyproject = '[project]\nname = "migrating"\nversion = "1.0.0"\n'
        old_lock = "uv.lock"
    else:
        old_pyproject = '[tool.poetry]\nname = "migrating"\nversion = "1.0.0"\n'
        old_lock = "poetry.lock"
    write_file(tmp_path, "pyproject.toml", old_pyproject)
    write_file(tmp_path, old_lock)
    base = commit_all(tmp_path, f"{old_owner} project")
    set_origin_main(tmp_path, base)
    write_file(tmp_path, "pyproject.toml", "[tool.pytest.ini_options]\n")
    _ = checked_git(tmp_path, "rm", "--", old_lock)
    write_file(tmp_path, "requirements.txt", "pytest==9.1.1\n")

    audit = audit_repository(tmp_path, include_update_commands=True)

    assert owner_specs(audit) == [(".", "pip", None)]
    assert command_specs(audit, "install_command_specs") == [
        (".", ("python", "-m", "pip", "install", "-r", "requirements.txt"))
    ]
    assert all(argv[0] not in {"uv", "poetry"} for _, argv in command_specs(audit, "update_command_specs"))
    expected_inventory = ["python"] if old_owner == "uv" else ["python", "poetry"]
    assert as_string_list(audit["package_managers"]) == expected_inventory


@pytest.mark.parametrize(
    ("manager", "manifest", "content"),
    [
        pytest.param("pnpm", "package.json", '{"packageManager":"pnpm@10.15.0"}\n', id="pnpm"),
        pytest.param("uv", "pyproject.toml", "[tool.uv]\n", id="uv"),
        pytest.param("poetry", "pyproject.toml", "[tool.poetry]\nname='example'\n", id="poetry"),
    ],
)
def test_declaration_without_lock_has_owner_but_no_frozen_install(
    tmp_path: Path,
    manager: str,
    manifest: str,
    content: str,
) -> None:
    """Represent declarations without inventing a frozen install command."""
    write_file(tmp_path, manifest, content)

    audit = audit_repository(tmp_path, manifest)

    assert owner_specs(audit) == [(".", manager, None)]
    assert command_specs(audit, "install_command_specs") == []
    assert any("no surviving" in warning for warning in as_string_list(audit["warnings"]))


@pytest.mark.parametrize(
    "case",
    [
        pytest.param(
            NpmShrinkwrapCase(
                version="11.6.2",
                locks=("npm-shrinkwrap.json",),
                expected_major=11,
                expect_ci=True,
                warning_fragment=None,
            ),
            id="npm11-shrinkwrap-only",
        ),
        pytest.param(
            NpmShrinkwrapCase(
                version="12.0.2",
                locks=("npm-shrinkwrap.json",),
                expected_major=NPM_12_MAJOR,
                expect_ci=False,
                warning_fragment="ignores obsolete npm-shrinkwrap.json",
            ),
            id="npm12-shrinkwrap-only",
        ),
        pytest.param(
            NpmShrinkwrapCase(
                version="latest",
                locks=("npm-shrinkwrap.json",),
                expected_major=None,
                expect_ci=False,
                warning_fragment="npm major is unknown",
            ),
            id="unknown-shrinkwrap-only",
        ),
        pytest.param(
            NpmShrinkwrapCase(
                version="latest",
                locks=("package-lock.json",),
                expected_major=None,
                expect_ci=True,
                warning_fragment="npm major is unknown",
            ),
            id="unknown-package-lock",
        ),
        pytest.param(
            NpmShrinkwrapCase(
                version="11.6.2",
                locks=("package-lock.json", "npm-shrinkwrap.json"),
                expected_major=11,
                expect_ci=True,
                warning_fragment=None,
            ),
            id="npm11-dual-lock",
        ),
        pytest.param(
            NpmShrinkwrapCase(
                version="12.0.2",
                locks=("package-lock.json", "npm-shrinkwrap.json"),
                expected_major=NPM_12_MAJOR,
                expect_ci=True,
                warning_fragment="ignores obsolete npm-shrinkwrap.json",
            ),
            id="npm12-dual-lock",
        ),
        pytest.param(
            NpmShrinkwrapCase(
                version="latest",
                locks=("package-lock.json", "npm-shrinkwrap.json"),
                expected_major=None,
                expect_ci=True,
                warning_fragment="npm major is unknown",
            ),
            id="unknown-dual-lock",
        ),
    ],
)
def test_npm_shrinkwrap_semantics_follow_declared_npm_major(
    tmp_path: Path,
    case: NpmShrinkwrapCase,
) -> None:
    """Use shrinkwrap for npm 11 only and retain ambiguity when the npm major is unknown."""
    write_file(tmp_path, "package.json", json.dumps({"packageManager": f"npm@{case.version}"}))
    for lock in case.locks:
        write_file(tmp_path, lock, '{"lockfileVersion":3}\n')

    audit = audit_repository(tmp_path, "package.json", *case.locks)

    assert owner_specs(audit) == [(".", "npm", None)]
    assert owner_version_major(audit, "npm") == case.expected_major
    expected_install = [(".", ("npm", "ci"))] if case.expect_ci else []
    assert command_specs(audit, "install_command_specs") == expected_install
    warnings = as_string_list(audit["warnings"])
    if case.warning_fragment is None:
        assert all("npm-shrinkwrap" not in warning for warning in warnings)
    else:
        assert any(case.warning_fragment in warning for warning in warnings)


def test_npm12_dual_lock_context_ignores_changed_shrinkwrap(tmp_path: Path) -> None:
    """Do not let an obsolete changed shrinkwrap satisfy npm 12's package-lock consistency check."""
    write_file(tmp_path, "package.json", '{"packageManager":"npm@12.0.2"}\n')
    write_file(tmp_path, "package-lock.json", '{"lockfileVersion":3}\n')
    write_file(tmp_path, "npm-shrinkwrap.json", '{"lockfileVersion":3}\n')

    audit = audit_repository(tmp_path, "package.json", "npm-shrinkwrap.json")

    assert command_specs(audit, "install_command_specs") == [(".", ("npm", "ci"))]
    assert any(
        "Manifest changed without an obvious lockfile change" in warning
        for warning in as_string_list(audit["warnings"])
    )


def test_nested_workspace_lock_requires_explicit_package_manager_boundary(tmp_path: Path) -> None:
    """Keep a nested workspace lock under its ancestor until the package declares an independent manager."""
    write_file(
        tmp_path,
        "package.json",
        json.dumps({"packageManager": "npm@12.0.2", "workspaces": ["packages/*"]}),
    )
    write_file(tmp_path, "package-lock.json", '{"lockfileVersion":3}\n')
    write_file(tmp_path, "packages/member/package.json", '{"name":"workspace-member"}\n')
    write_file(tmp_path, "packages/member/pnpm-lock.yaml")
    changed_files = (
        "package.json",
        "package-lock.json",
        "packages/member/package.json",
        "packages/member/pnpm-lock.yaml",
    )

    audit = audit_repository(tmp_path, *changed_files, include_update_commands=True)

    assert owner_specs(audit) == [(".", "npm", None)]
    assert command_specs(audit, "install_command_specs") == [(".", ("npm", "ci"))]
    assert all(cwd == "." for cwd, _ in command_specs(audit, "update_command_specs"))
    assert any(
        "explicit packageManager declaration is required" in warning for warning in as_string_list(audit["warnings"])
    )


def test_nested_polyglot_projects_receive_directory_scoped_command_specs(tmp_path: Path) -> None:
    """Keep independent nested npm, pnpm, uv, and requirements commands structurally scoped."""
    write_file(
        tmp_path,
        "package.json",
        json.dumps({"packageManager": "npm@12.0.2", "scripts": {"check": "node check.js"}}),
    )
    write_file(tmp_path, "package-lock.json")
    write_file(
        tmp_path,
        "apps/web/package.json",
        json.dumps({"packageManager": "pnpm@10.15.0", "scripts": {"test": "vitest"}}),
    )
    write_file(tmp_path, "apps/web/pnpm-lock.yaml")
    write_file(
        tmp_path,
        "services/api/pyproject.toml",
        '[project]\nname = "api"\nversion = "1.0.0"\n[tool.pytest.ini_options]\n',
    )
    write_file(tmp_path, "services/api/uv.lock")
    write_file(tmp_path, "tools/legacy/requirements.txt", "pytest==9.1.1\n")
    changed_files = (
        "package.json",
        "package-lock.json",
        "apps/web/package.json",
        "apps/web/pnpm-lock.yaml",
        "services/api/pyproject.toml",
        "services/api/uv.lock",
        "tools/legacy/requirements.txt",
    )

    audit = audit_repository(tmp_path, *changed_files)

    assert owner_specs(audit) == [
        (".", "npm", None),
        ("apps/web", "pnpm", None),
        ("services/api", "uv", None),
        ("tools/legacy", "pip", None),
    ]
    assert command_specs(audit, "install_command_specs") == [
        (".", ("npm", "ci")),
        ("apps/web", ("pnpm", "install", "--frozen-lockfile")),
        ("services/api", ("uv", "sync", "--frozen")),
        ("tools/legacy", ("python", "-m", "pip", "install", "-r", "requirements.txt")),
    ]
    assert command_specs(audit, "update_command_specs") == []
    assert ("apps/web", ("pnpm", "run", "test")) in command_specs(audit, "validation_command_specs")
    assert ("services/api", ("pytest",)) in command_specs(audit, "validation_command_specs")

    update_audit = audit_repository(tmp_path, *changed_files, include_update_commands=True)
    assert ("apps/web", ("pnpm", "update", "--interactive", "--latest")) in command_specs(
        update_audit,
        "update_command_specs",
    )
    assert ("services/api", ("uv", "lock", "--upgrade")) in command_specs(
        update_audit,
        "update_command_specs",
    )
    assert (
        "tools/legacy",
        ("python", "-m", "pip", "install", "--upgrade", "-r", "requirements.txt"),
    ) in command_specs(update_audit, "update_command_specs")
