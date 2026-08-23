# Copyright (c) 2026 Nick2bad4u
"""Repository-wide contract tests for every packaged skill."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tomllib
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import pytest

MIN_SECTION_WORDS = 8
MIN_QUOTED_SCALAR_LENGTH = 2
REPO_ROOT = Path(__file__).resolve().parents[1]
SKILLS_ROOT = REPO_ROOT / "skills"
IMPLICIT_INVOCATION_DISABLED = frozenset(
    {
        "verify-oxlint-plugin-compatibility",
        "vsicons-association-recommender",
        "workspace-continuation",
    }
)
SECRET_ENVIRONMENT_VARIABLES = (
    "CODACY_API_TOKEN",
    "CODACY_PROJECT_TOKEN",
    "SNYK_TOKEN",
    "SOCKET_API_KEY",
    "SOCKET_SECURITY_API_KEY",
    "STEPSECURITY_API_TOKEN",
    "STEPSECURITY_TOKEN",
    "WAKATIME_API_KEY",
)


@dataclass(frozen=True)
class SkillContract:
    """Stable routing, workflow, and supporting-resource contract for one skill."""

    description_terms: tuple[str, ...]
    sections: tuple[str, ...]
    resources: tuple[str, ...] = ()


SKILL_CONTRACTS: dict[str, SkillContract] = {
    "agent-skill-instruction-creation": SkillContract(
        description_terms=("SKILL.md", "AGENTS.md", "agent guidance"),
        sections=("Choose The Surface", "Discovery Workflow", "Skill Creation", "Validation"),
        resources=("references/skillcheck-config.md",),
    ),
    "agent-skill-instruction-review": SkillContract(
        description_terms=("SKILL.md", "reviewing", "agent guidance"),
        sections=("Source Of Truth", "Review Workflow", "Fix Workflow", "Reporting"),
        resources=("references/skillcheck-config.md",),
    ),
    "ci-release-readiness": SkillContract(
        description_terms=("CI", "release", "approval"),
        sections=("CI Failure Workflow", "Release Readiness Workflow", "Boundaries"),
    ),
    "codacy-management": SkillContract(
        description_terms=("Codacy", "security findings", "API"),
        sections=("Security Model", "Tool Choice", "Workflow", "Completion Evidence"),
        resources=(
            "references/api-reference.md",
            "references/command-guide.md",
            "scripts/manage_codacy.py",
        ),
    ),
    "code-review-maintenance": SkillContract(
        description_terms=("code-review", "correctness", "security"),
        sections=("Scope Modes", "Workflow", "Output"),
    ),
    "dependency-update-maintenance": SkillContract(
        description_terms=("dependency updates", "lockfile", "quality gates"),
        sections=("Scope Modes", "Workflow", "Validation"),
        resources=(
            "references/dependency-update-validation.md",
            "scripts/audit_dependency_update.py",
        ),
    ),
    "documentation-maintenance": SkillContract(
        description_terms=("TSDoc", "TypeDoc", "Docusaurus"),
        sections=("Ground Truth", "Workflows", "Output"),
    ),
    "eslint-plugin-maintenance": SkillContract(
        description_terms=("ESLint", "rules", "plugin"),
        sections=("Bootstrap A New Plugin", "Audit Best Practices", "Rule Surface Sync", "Validation"),
    ),
    "github-actions-workflow-maintenance": SkillContract(
        description_terms=("GitHub Actions", "permissions", "action pinning"),
        sections=("Inputs", "Outputs", "Security Rules", "Validation"),
        resources=(
            "references/github-actions-best-practices.md",
            "references/review-checklist.md",
        ),
    ),
    "lint-cleanup": SkillContract(
        description_terms=("lint", "suppressions", "root cause"),
        sections=("Workflow", "ESLint Disable Cleanup", "Output"),
    ),
    "mermaid-diagram-maintenance": SkillContract(
        description_terms=("Mermaid", "theming", "diagrams"),
        sections=("First Pass", "Diagram Design", "Editing And Debugging", "Output"),
        resources=("references/theme-and-syntax.md",),
    ),
    "npm-12-migration": SkillContract(
        description_terms=("npm 12", "allowScripts", "migration"),
        sections=("Workflow", "Guardrails", "Output"),
        resources=("references/npm-12-migration.md",),
    ),
    "powershell-development": SkillContract(
        description_terms=("PowerShell", "PSScriptAnalyzer", "Pester"),
        sections=("Workflow", "Safety Invariants", "Command and Output Contract", "Validation"),
        resources=(
            "references/pester-testing.md",
            "references/powershell-engineering.md",
        ),
    ),
    "prettier-plugin-maintenance": SkillContract(
        description_terms=("Prettier", "parser", "printer"),
        sections=("Source Of Truth", "Parser And Printer Design", "Surface Sync", "Validation"),
    ),
    "python-strict-development": SkillContract(
        description_terms=("Ruff", "mypy", "Pyright", "pytest"),
        sections=("Source Priority", "Workflow", "Python Code Standards", "Validation Commands"),
        resources=(
            "references/project-shapes.md",
            "references/strict-fix-patterns.md",
            "references/strict-tooling.md",
            "scripts/audit_python_strict.py",
        ),
    ),
    "release-publish-loop": SkillContract(
        description_terms=("release", "publish", "semver", "artifacts"),
        sections=("Boundaries", "Local Validation And Commit", "Semver Decision", "Final Verification"),
        resources=("references/release-loop-checklist.md",),
    ),
    "remark-plugin-maintenance": SkillContract(
        description_terms=("remark", "Markdown AST", "rules"),
        sections=("Bootstrap A New Plugin", "Rule And Plugin Design", "Surface Sync", "Validation"),
    ),
    "schemastore-pr-maintenance": SkillContract(
        description_terms=("SchemaStore", "JSON schemas", "catalog"),
        sections=("Source Priority", "Workflow", "Adoption Evidence", "Validation"),
        resources=(
            "references/schemastore-standards.md",
            "scripts/audit_schemastore_pr.py",
        ),
    ),
    "snyk-management": SkillContract(
        description_terms=("Snyk", "projects", "REST API"),
        sections=("Security Model", "Access Boundary", "Workflow", "Completion Evidence"),
        resources=(
            "references/api-reference.md",
            "references/command-guide.md",
            "scripts/manage_snyk.py",
        ),
    ),
    "socket-management": SkillContract(
        description_terms=("Socket.dev", "supply-chain", "SBOMs"),
        sections=("Security Model", "Tool Choice", "Workflow", "Completion Evidence"),
        resources=(
            "references/api-reference.md",
            "references/command-guide.md",
            "scripts/manage_socket.py",
        ),
    ),
    "stepsecurity-management": SkillContract(
        description_terms=("StepSecurity", "Harden-Runner", "runtime"),
        sections=("Operating Rules", "Triage Workflow", "REST Safety Pattern", "Completion Standard"),
        resources=(
            "references/api-reference.md",
            "references/command-guide.md",
            "scripts/manage_stepsecurity.py",
        ),
    ),
    "stylelint-plugin-maintenance": SkillContract(
        description_terms=("Stylelint", "rules", "plugin"),
        sections=("Bootstrap A New Plugin", "Audit Best Practices", "Discover Rules", "Validation"),
    ),
    "test-quality-maintenance": SkillContract(
        description_terms=("tests", "coverage", "Playwright"),
        sections=("Inputs", "Outputs", "Shared Workflow", "Error Handling", "Reporting"),
    ),
    "verify-oxlint-plugin-compatibility": SkillContract(
        description_terms=("Oxlint", "ESLint plugin", "compatibility"),
        sections=(
            "Establish The Current Contract",
            "Inventory Rules Before Probing",
            "Compatibility Probe",
            "Report The Result",
        ),
    ),
    "vsicons-association-recommender": SkillContract(
        description_terms=("vscode-icons", "associations", "VS Code settings"),
        sections=("Existing Settings and Placement", "Local Custom Icons", "Workflow", "Selection Rules"),
        resources=(
            "references/icon-source-resolution.md",
            "scripts/inventory_vsicons.py",
        ),
    ),
    "wakatime-management": SkillContract(
        description_terms=("WakaTime", "coding-activity", "privacy"),
        sections=("Security And Privacy Model", "Workflow", "Scope Boundary", "Completion Evidence"),
        resources=(
            "references/api-reference.md",
            "references/command-guide.md",
            "scripts/manage_wakatime.py",
        ),
    ),
    "workspace-continuation": SkillContract(
        description_terms=("handoffs", "resuming", "plan"),
        sections=("Inputs", "Outputs", "Continue Work", "Write A Handoff", "Reporting"),
    ),
}

SKILL_IDS = tuple(sorted(SKILL_CONTRACTS))
HELPER_CASES = tuple(
    (skill_name, resource)
    for skill_name in SKILL_IDS
    for resource in SKILL_CONTRACTS[skill_name].resources
    if resource.startswith("scripts/")
)
HELPER_IDS = tuple(PurePosixPath(relative_path).stem for _, relative_path in HELPER_CASES)


def frontmatter(markdown: str) -> dict[str, str]:
    """Parse the deliberately restricted two-field SKILL.md frontmatter."""
    lines = markdown.splitlines()
    if not lines or lines[0] != "---":
        raise ValueError("SKILL.md must start with frontmatter.")
    try:
        end = lines.index("---", 1)
    except ValueError as error:
        raise ValueError("SKILL.md frontmatter is not closed.") from error

    values: dict[str, str] = {}
    for line in lines[1:end]:
        key, separator, value = line.partition(":")
        if not separator:
            raise ValueError(f"Unsupported frontmatter line: {line}")
        values[key.strip()] = strip_matching_quotes(value.strip())
    return values


def repository_path(relative_path: str) -> Path:
    """Resolve a repository-relative POSIX path without relying on host separators."""
    return REPO_ROOT.joinpath(*PurePosixPath(relative_path).parts)


def section_bodies(markdown: str) -> dict[str, str]:
    """Return second-level Markdown section names and their bodies."""
    matches = list(re.finditer(r"^## (?P<name>[^\r\n]+)$", markdown, flags=re.MULTILINE))
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
        sections[match.group("name")] = markdown[match.end() : end].strip()
    return sections


def strip_matching_quotes(value: str) -> str:
    """Remove one matching pair of YAML scalar quotes."""
    if len(value) >= MIN_QUOTED_SCALAR_LENGTH and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def supporting_resources(skill_root: Path) -> tuple[str, ...]:
    """List reference and script resources owned by one skill."""
    resources: list[str] = []
    for resource_kind in ("references", "scripts"):
        resource_root = skill_root / resource_kind
        if not resource_root.is_dir():
            continue
        resources.extend(
            resource.relative_to(skill_root).as_posix()
            for resource in resource_root.rglob("*")
            if resource.is_file() and "__pycache__" not in resource.parts
        )
    return tuple(sorted(resources))


def yaml_scalar(yaml_text: str, key: str) -> str:
    """Read one scalar from the generated flat metadata fields used by this repo."""
    prefix = f"{key}:"
    for line in yaml_text.splitlines():
        stripped = line.strip()
        if stripped.startswith(prefix):
            return strip_matching_quotes(stripped.removeprefix(prefix).strip())
    raise ValueError(f"Missing generated metadata field: {key}")


def test_contract_manifest_covers_every_skill() -> None:
    """Require every current skill to opt into an explicit test contract."""
    actual = {entry.name for entry in SKILLS_ROOT.iterdir() if entry.is_dir()}
    expected = set(SKILL_CONTRACTS)

    assert actual == expected, (
        f"Skill contract matrix drift. Missing contracts: {sorted(actual - expected)}; "
        f"removed skills still listed: {sorted(expected - actual)}"
    )


@pytest.mark.parametrize("skill_name", SKILL_IDS, ids=SKILL_IDS)
def test_skill_instruction_contract(skill_name: str) -> None:
    """Verify one skill's routing, workflow sections, and supporting resources."""
    contract = SKILL_CONTRACTS[skill_name]
    skill_root = SKILLS_ROOT / skill_name
    skill_markdown = (skill_root / "SKILL.md").read_text(encoding="utf-8")
    metadata = frontmatter(skill_markdown)
    sections = section_bodies(skill_markdown)

    assert set(metadata) == {"name", "description"}
    assert metadata["name"] == skill_name
    description = metadata["description"].casefold()
    missing_terms = [term for term in contract.description_terms if term.casefold() not in description]
    assert not missing_terms, f"Routing description is missing contract terms: {missing_terms}"

    for section_name in contract.sections:
        assert section_name in sections, f"Missing required workflow section: ## {section_name}"
        word_count = len(re.findall(r"\b[\w.-]+\b", sections[section_name]))
        assert word_count >= MIN_SECTION_WORDS, (
            f"Workflow section ## {section_name} is too thin: {word_count} words; expected at least {MIN_SECTION_WORDS}"
        )

    actual_resources = supporting_resources(skill_root)
    assert actual_resources == tuple(sorted(contract.resources))
    for resource in contract.resources:
        assert resource in skill_markdown, f"Owned resource is not routed from SKILL.md: {resource}"


@pytest.mark.parametrize("skill_name", SKILL_IDS, ids=SKILL_IDS)
def test_skill_generated_metadata_and_icons(skill_name: str) -> None:
    """Verify one skill's generated invocation policy and parseable local icons."""
    skill_root = SKILLS_ROOT / skill_name
    metadata_path = skill_root / "agents" / "openai.yaml"
    metadata = metadata_path.read_text(encoding="utf-8")

    assert yaml_scalar(metadata, "default_prompt").find(f"${skill_name}") >= 0
    expected_invocation = str(skill_name not in IMPLICIT_INVOCATION_DISABLED).lower()
    assert yaml_scalar(metadata, "allow_implicit_invocation") == expected_invocation

    expected_icons = (
        f"./assets/{skill_name}-small.svg",
        f"./assets/{skill_name}.svg",
    )
    actual_icons = (
        yaml_scalar(metadata, "icon_small"),
        yaml_scalar(metadata, "icon_large"),
    )
    assert actual_icons == expected_icons

    for icon in actual_icons:
        icon_path = skill_root.joinpath(*PurePosixPath(icon).parts)
        root = ET.fromstring(icon_path.read_text(encoding="utf-8"))  # noqa: S314 - trusted repository SVG
        assert root.tag.rsplit("}", maxsplit=1)[-1] == "svg"
        assert "viewBox" in root.attrib
        assert all(element.tag.rsplit("}", maxsplit=1)[-1] != "script" for element in root.iter())


def test_every_helper_is_registered_for_coverage() -> None:
    """Require every bundled Python helper directory to participate in coverage."""
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    coverage_run = pyproject["tool"]["coverage"]["run"]
    include_patterns = tuple(coverage_run["include"])

    assert coverage_run["relative_files"] is True
    assert "source" not in coverage_run, "Coverage source roots collapse Cobertura filenames to ambiguous basenames."

    for skill_name, relative_script in HELPER_CASES:
        script_relative_to_repo = PurePosixPath("skills") / skill_name / relative_script
        assert any(script_relative_to_repo.match(pattern) for pattern in include_patterns), (
            f"Coverage include patterns do not match {script_relative_to_repo}."
        )


@pytest.mark.parametrize(("skill_name", "relative_script"), HELPER_CASES, ids=HELPER_IDS)
def test_helper_entrypoint_and_git_mode(skill_name: str, relative_script: str) -> None:
    """Load every helper CLI safely and preserve executable mode for Linux consumers."""
    script_relative_to_repo = f"skills/{skill_name}/{relative_script}"
    script_path = repository_path(script_relative_to_repo)
    environment = os.environ.copy()
    for variable in SECRET_ENVIRONMENT_VARIABLES:
        _ = environment.pop(variable, None)

    result = subprocess.run(  # noqa: S603 - fixed interpreter and repository-owned helper
        [sys.executable, str(script_path), "--help"],
        cwd=REPO_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        stdin=subprocess.DEVNULL,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout.casefold()
    assert "traceback" not in (result.stdout + result.stderr).casefold()
    assert script_path.read_text(encoding="utf-8").startswith("#!/usr/bin/env python")

    git = shutil.which("git")
    assert git is not None, "Git is required to verify packaged helper modes."
    staged = subprocess.run(  # noqa: S603 - resolved Git executable with fixed read-only arguments
        [git, "ls-files", "--stage", "--", script_relative_to_repo],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        stdin=subprocess.DEVNULL,
        text=True,
        timeout=10,
    )
    assert staged.returncode == 0, staged.stderr
    assert staged.stdout.strip(), f"Helper is not tracked by Git: {script_relative_to_repo}"
    assert staged.stdout.split(maxsplit=1)[0] == "100755"
