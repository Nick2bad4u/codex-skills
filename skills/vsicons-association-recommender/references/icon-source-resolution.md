# Icon Source Resolution

Use this reference when exact vscode-icons icon availability matters.

## Contents

- [Bundled Icon Verification](#bundled-icon-verification)
- [Local Custom Icon Verification](#local-custom-icon-verification)
- [Inventory Script](#inventory-script)
- [Recommendation Rules](#recommendation-rules)

## Bundled Icon Verification

Prefer installed extension/package files over remote docs. Search common local extension roots such as:

- `%USERPROFILE%\.vscode\extensions\vscode-icons-team.vscode-icons-*`
- `%USERPROFILE%\.vscode-insiders\extensions\vscode-icons-team.vscode-icons-*`
- `%USERPROFILE%\.cursor\extensions\vscode-icons-team.vscode-icons-*`

Bundled SVG names usually map to settings names by removing the prefix and suffix:

- `file_type_<icon>.svg` ⇾ `"icon": "<icon>"`
- `folder_type_<icon>.svg` ⇾ `"icon": "<icon>"`

## Local Custom Icon Verification

The user's default custom icon directory is:

```text
%USERPROFILE%\Dropbox\PC Tool Kit\WindowsTerminalIcons\vsicons-custom-icons
```

For custom file icons, verify `file_type_<icon>.svg` exists.

For custom folder icons, verify both files exist:

- `folder_type_<icon>.svg`
- `folder_type_<icon>_opened.svg`

When recommending `"vsicons.customIconFolderPath"`, use the parent folder that contains `vsicons-custom-icons`, not the custom icon folder itself.

## Inventory Script

Run the bundled read-only helper to inventory local bundled and custom icon names:

```powershell
python <skill-root>\scripts\inventory_vsicons.py --query python
python <skill-root>\scripts\inventory_vsicons.py --json
```

Use `--custom-icons <path>` for another custom icon directory and `--extension-root <path>` for a nonstandard VS Code-compatible extension root.

## Recommendation Rules

- Recommend bundled icons first when they are exact and verified.
- Recommend local custom icons when no bundled icon exists or when a custom icon is a better semantic match.
- Skip candidates when the closest icon would be misleading.
- Mark icon names as unverified outside the JSON when local verification is unavailable.
