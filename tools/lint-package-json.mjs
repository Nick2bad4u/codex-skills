import { readFile } from "node:fs/promises";
import * as path from "node:path";
import { NpmPackageJsonLint, write } from "npm-package-json-lint";

const root = process.cwd();
const packageJsonPath = path.join(root, "package.json");
const packageJsonObject = parseJsonObject(
    await readFile(packageJsonPath, "utf8")
);

const linter = new NpmPackageJsonLint({
    configFile: path.join(root, ".npmpackagejsonlintrc.json"),
    cwd: root,
    packageJsonFilePath: packageJsonPath,
    packageJsonObject,
});

const result = linter.lint();
write(result, false);

if (result.errorCount > 0) {
    Object.assign(process, { exitCode: 1 });
}

/**
 * @param {string} text
 *
 * @returns {Record<string, unknown>}
 */
function parseJsonObject(text) {
    const value = /** @type {unknown} */ (JSON.parse(text));

    if (typeof value !== "object" || value === null || Array.isArray(value)) {
        throw new TypeError("package.json must contain a JSON object.");
    }

    return /** @type {Record<string, unknown>} */ (value);
}
