#!/usr/bin/env python
"""Inventory vscode-icons bundled and local custom icon names."""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class IconInventory:
    """Resolved icon names from one source directory."""

    file_icons: list[str]
    folder_icons: list[str]
    missing_opened_folder_icons: list[str]
    source: str


def default_custom_icon_dir() -> Path:
    """Return the user's default local custom icon directory."""

    home = Path.home()
    return (
        home
        / "Dropbox"
        / "PC Tool Kit"
        / "WindowsTerminalIcons"
        / "vsicons-custom-icons"
    )


def default_extension_roots() -> list[Path]:
    """Return common extension roots that can contain vscode-icons."""

    home = Path.home()
    roots = [
        home / ".vscode" / "extensions",
        home / ".vscode-insiders" / "extensions",
        home / ".cursor" / "extensions",
        home / ".windsurf" / "extensions",
    ]

    app_data = os.environ.get("APPDATA")
    if app_data:
        roots.extend(
            [
                Path(app_data) / "Code" / "User" / "globalStorage",
                Path(app_data) / "Cursor" / "User" / "globalStorage",
            ]
        )

    return roots


def discover_vscode_icon_dirs(extension_roots: list[Path]) -> list[Path]:
    """Find likely vscode-icons extension directories."""

    directories: list[Path] = []
    for root in extension_roots:
        if not root.exists():
            continue

        for candidate in root.glob("vscode-icons-team.vscode-icons-*"):
            if candidate.is_dir():
                directories.append(candidate)

        for candidate in root.glob("**/vscode-icons-team.vscode-icons-*"):
            if candidate.is_dir():
                directories.append(candidate)

    return sorted(set(directories))


def filter_names(names: list[str], query: str | None) -> list[str]:
    """Filter names by a case-insensitive query."""

    if query is None:
        return names

    normalized_query = query.casefold()
    return [name for name in names if normalized_query in name.casefold()]


def icon_name(path: Path, prefix: str, suffix: str = ".svg") -> str | None:
    """Extract a vscode-icons icon name from a file path."""

    name = path.name
    if not name.startswith(prefix) or not name.endswith(suffix):
        return None
    return name[len(prefix) : -len(suffix)]


def inventory_icon_dir(source: Path, query: str | None = None) -> IconInventory:
    """Inventory file and folder icons below a directory."""

    file_icons: set[str] = set()
    folder_icons: set[str] = set()
    opened_folder_icons: set[str] = set()

    if source.exists():
        for icon_path in source.rglob("*.svg"):
            file_icon = icon_name(icon_path, "file_type_")
            if file_icon is not None:
                file_icons.add(file_icon)
                continue

            opened_folder_icon = icon_name(icon_path, "folder_type_", "_opened.svg")
            if opened_folder_icon is not None:
                opened_folder_icons.add(opened_folder_icon)
                continue

            folder_icon = icon_name(icon_path, "folder_type_")
            if folder_icon is not None:
                folder_icons.add(folder_icon)

    missing_opened = sorted(folder_icons - opened_folder_icons)

    return IconInventory(
        file_icons=filter_names(sorted(file_icons), query),
        folder_icons=filter_names(sorted(folder_icons), query),
        missing_opened_folder_icons=filter_names(missing_opened, query),
        source=str(source),
    )


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(
        description="Inventory vscode-icons bundled and local custom SVG icon names."
    )
    parser.add_argument(
        "--custom-icons",
        action="append",
        default=[],
        help="Custom icon directory to scan. Can be repeated.",
    )
    parser.add_argument(
        "--extension-root",
        action="append",
        default=[],
        help="Extension root to scan for vscode-icons-team.vscode-icons-* directories. Can be repeated.",
    )
    parser.add_argument(
        "--query",
        help="Case-insensitive substring filter for icon names.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON.",
    )
    return parser.parse_args()


def print_text(custom: list[IconInventory], bundled: list[IconInventory]) -> None:
    """Print a concise text summary."""

    for label, inventories in (("custom", custom), ("bundled", bundled)):
        print(f"{label}: {len(inventories)} source(s)")
        for inventory in inventories:
            print(f"  {inventory.source}")
            print(f"    file icons: {len(inventory.file_icons)}")
            print(f"    folder icons: {len(inventory.folder_icons)}")
            print(
                "    folders missing _opened pair: "
                f"{len(inventory.missing_opened_folder_icons)}"
            )
            if inventory.file_icons:
                print(f"    sample file icons: {', '.join(inventory.file_icons[:12])}")
            if inventory.folder_icons:
                print(
                    f"    sample folder icons: {', '.join(inventory.folder_icons[:12])}"
                )


def main() -> int:
    """Run the inventory."""

    args = parse_args()
    custom_dirs = [Path(value).expanduser() for value in args.custom_icons]
    if not custom_dirs:
        custom_dirs = [default_custom_icon_dir()]

    extension_roots = [Path(value).expanduser() for value in args.extension_root]
    if not extension_roots:
        extension_roots = default_extension_roots()

    custom = [
        inventory_icon_dir(icon_dir, args.query)
        for icon_dir in custom_dirs
        if icon_dir.exists()
    ]
    bundled = [
        inventory_icon_dir(icon_dir, args.query)
        for icon_dir in discover_vscode_icon_dirs(extension_roots)
    ]

    if args.json:
        print(
            json.dumps(
                {
                    "bundled": [asdict(inventory) for inventory in bundled],
                    "custom": [asdict(inventory) for inventory in custom],
                },
                indent=2,
            )
        )
    else:
        print_text(custom, bundled)

    return 0


if __name__ == "__main__":
    sys.exit(main())
