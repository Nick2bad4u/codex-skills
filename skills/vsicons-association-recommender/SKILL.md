---
name: vsicons-association-recommender
description: Recommends copy-pasteable vscode-icons custom association objects for workspace files and folders. Use when Codex needs to inspect a project and map filenames, file extensions, generated files, dotfolders, test folders, config folders, or framework folders to supported VS Code Icons icon names.
---

# VSIcons Association Recommender

Use this skill to recommend `vsicons.associations.files` and `vsicons.associations.folders` entries that a user can paste into VS Code settings.

## Source Lists

- Use the current vscode-icons file list: `https://github.com/vscode-icons/vscode-icons/wiki/ListOfFiles`
- Use the current vscode-icons folder list: `https://github.com/vscode-icons/vscode-icons/wiki/ListOfFolders`
- Use the current fine-tuning docs when the settings schema is uncertain: `https://github.com/vscode-icons/vscode-icons/wiki/FineTuning`
- Use the custom icons docs when recommending local custom icons: `https://github.com/vscode-icons/vscode-icons/wiki/Custom`
- Re-check those pages when the user asks for current or exact icon availability. Do not invent icon names.

## Local Custom Icons

The user may have local custom icons at `%USERPROFILE%\Dropbox\PC Tool Kit\WindowsTerminalIcons\vsicons-custom-icons`. Treat this as an optional icon source, not the default path for every recommendation.

- Use local custom icons only when a supported bundled icon is unavailable, the user asks for custom icons, or an existing local custom icon is a better semantic match.
- Verify the icon file exists before recommending it.
- For file icons, derive `icon` from `file_type_<icon>.svg`.
- For folder icons, require both `folder_type_<icon>.svg` and `folder_type_<icon>_opened.svg`.
- If recommending the custom folder setting, use the parent path, not the icon folder itself.

Recommended local custom folder setting shape:

```json
"vsicons.customIconFolderPath": "<absolute path to the parent WindowsTerminalIcons folder>"
```

## Workflow

1. Inspect the workspace file and folder names before recommending associations.
2. Ignore dependency, VCS, cache, build, coverage, and generated output folders unless the user explicitly asks about them.
3. Identify names that are visible often and would benefit from a better icon: project-specific configs, AI-agent files, snapshots, generated sources, docs, scripts, tool folders, package manager files, and uncommon framework files.
4. Match each candidate to an existing vscode-icons icon name from the supported file or folder list, or to a verified local custom icon when that is a better fit.
5. Prefer exact filename entries for full filenames, dotted config files, multi-extension files, and generated filenames.
6. Prefer extension entries only for true reusable file extensions that should apply broadly.
7. Prefer folder entries for directory names and dotfolders.
8. Avoid recommending entries that duplicate vscode-icons defaults unless the user wants explicit settings or a different icon.

## Output Shape

Return copy-pasteable JSON object snippets, not prose-heavy explanations. Use this file form for exact filenames:

```json
{
    "extensions": [
        "atomicBit-Enhanced.omp.json"
    ],
    "filename": true,
    "format": "svg",
    "icon": "dartlang_generated"
},
```

Use this folder form:

```json
{
    "extensions": [
        "__snapshots__"
    ],
    "format": "svg",
    "icon": "snapchat"
},
```

When the user asks for a full settings block, wrap file snippets in `"vsicons.associations.files": []` and folder snippets in `"vsicons.associations.folders": []`. Otherwise, return the snippets only.

## Selection Rules

- Keep `format` as `"svg"` unless the source icon requires otherwise.
- Include `"filename": true` only for file entries that should match an exact filename rather than an extension.
- Do not include `"filename": true` for folders.
- Put one or more matched names in `extensions`; preserve exact casing for case-sensitive filenames.
- Use lower-risk, semantically close icons when an exact icon is unavailable, and label the recommendation as an approximation outside the JSON.
- If no supported icon is a defensible match, skip the candidate instead of forcing a misleading icon.
- Deduplicate entries and group file recommendations before folder recommendations.

## Validation

Check that every recommended bundled `icon` appears in the current supported file or folder list. For local custom icons, check the corresponding SVG files exist in the custom icons' folder. Before finishing, verify the JSON syntax is pasteable inside an array and that trailing commas match the user's requested style.
