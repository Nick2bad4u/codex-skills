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
];

export default config;
