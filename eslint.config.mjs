import { createConfig } from "eslint-config-nick2bad4u";
import * as path from "node:path";
import { fileURLToPath } from "node:url";

const rootDirectory = path.dirname(fileURLToPath(import.meta.url));

/** @type {import("eslint").Linter.Config[]} */
const config = [
    ...createConfig({
        allowDefaultProjectFilePatterns: [],
        rootDirectory,
    }),
    {
        files: ["eslint.config.mjs"],
        rules: {
            "unicorn/prefer-import-meta-properties": "off",
        },
    },
    {
        rules: {
            "copilot/require-skill-file-location": "off",
        },
    },
    {
        files: ["tools/**/*.mjs"],
        rules: {
            "n/no-top-level-await": "off",
            "n/no-unpublished-import": "off",
            "no-console": "off",
            "security/detect-non-literal-fs-filename": "off",
        },
    },
    {
        files: ["tools/run-pytest.mjs"],
        rules: {
            "n/no-process-env": "off",
        },
    },
    {
        files: ["*.toml"],
        rules: {
            "tombi/tombi": "off",
            "toml/array-bracket-newline": "off",
            "toml/array-element-newline": "off",
        },
    },
];

export default config;
