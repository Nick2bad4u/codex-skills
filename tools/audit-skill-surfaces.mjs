import { readdir, readFile, stat } from "node:fs/promises";
import * as path from "node:path";
import { types } from "node:util";

const root = process.cwd();
const skillsRoot = path.join(root, "skills");
const longReferenceLineThreshold = 100;

/**
 * @typedef {object} Finding
 *
 * @property {string} message
 * @property {string} path
 */

/**
 * @param {Finding[]} findings
 * @param {string} filePath
 * @param {string} message
 *
 * @returns {void}
 */
function addFinding(findings, filePath, message) {
    findings.push({
        message,
        path: path.relative(root, filePath),
    });
}

/**
 * @param {string} referencePath
 * @param {Finding[]} findings
 *
 * @returns {Promise<void>}
 */
async function auditReference(referencePath, findings) {
    const markdown = await readFile(referencePath, "utf8");
    const lineCount = linesOf(markdown).length;

    if (lineCount > longReferenceLineThreshold && !hasEarlyContents(markdown)) {
        addFinding(
            findings,
            referencePath,
            `reference has ${lineCount} lines and needs an early ## Contents section`
        );
    }
}

/**
 * @param {string} skillRoot
 * @param {string} skillMarkdown
 * @param {"references" | "scripts"} resourceKind
 * @param {Finding[]} findings
 *
 * @returns {Promise<void>}
 */
async function auditResourceDirectory(
    skillRoot,
    skillMarkdown,
    resourceKind,
    findings
) {
    const resourceRoot = path.join(skillRoot, resourceKind);

    if (!(await pathExists(resourceRoot))) {
        return;
    }

    const resourceFiles = await walkFiles(resourceRoot);

    await Promise.all(
        resourceFiles.map(async (resourceFile) => {
            const relativeResourcePath = path
                .relative(skillRoot, resourceFile)
                .split(path.sep)
                .join("/");

            if (!skillMarkdown.includes(relativeResourcePath)) {
                addFinding(
                    findings,
                    resourceFile,
                    `${resourceKind} resource is not linked from SKILL.md as ${relativeResourcePath}`
                );
            }

            if (resourceKind === "references" && resourceFile.endsWith(".md")) {
                await auditReference(resourceFile, findings);
            }
        })
    );
}

/**
 * @param {string} skillName
 * @param {Finding[]} findings
 *
 * @returns {Promise<void>}
 */
async function auditSkill(skillName, findings) {
    const skillRoot = path.join(skillsRoot, skillName);
    const skillMarkdownPath = path.join(skillRoot, "SKILL.md");
    const skillMarkdown = await readFile(skillMarkdownPath, "utf8");

    await Promise.all([
        auditResourceDirectory(
            skillRoot,
            skillMarkdown,
            "references",
            findings
        ),
        auditResourceDirectory(skillRoot, skillMarkdown, "scripts", findings),
    ]);
}

/**
 * @param {string} markdown
 *
 * @returns {boolean}
 */
function hasEarlyContents(markdown) {
    return linesOf(markdown)
        .slice(0, 30)
        .some((line) => /^## (?:Contents|Table Of Contents)$/v.test(line));
}

/**
 * @param {string} text
 *
 * @returns {string[]}
 */
function linesOf(text) {
    return text.replaceAll("\r\n", "\n").replaceAll("\r", "\n").split("\n");
}

/**
 * @returns {Promise<void>}
 */
async function main() {
    const skillNames = await skillDirectories();
    /** @type {Finding[]} */
    const findings = [];

    await Promise.all(
        skillNames.map((skillName) => auditSkill(skillName, findings))
    );

    if (findings.length > 0) {
        for (const finding of findings) {
            console.error(`${finding.path}: ${finding.message}`);
        }
        process.exitCode = 1;
        return;
    }

    console.log(`Audited ${skillNames.length} skill resource surfaces.`);
}

/**
 * @param {string} targetPath
 *
 * @returns {Promise<boolean>}
 */
async function pathExists(targetPath) {
    try {
        await stat(targetPath);
        return true;
    } catch (error) {
        if (
            types.isNativeError(error) &&
            "code" in error &&
            error.code === "ENOENT"
        ) {
            return false;
        }
        throw error;
    }
}

/**
 * @returns {Promise<string[]>}
 */
async function skillDirectories() {
    const entries = await readdir(skillsRoot, { withFileTypes: true });

    return entries
        .filter((entry) => entry.isDirectory())
        .map((entry) => entry.name)
        .toSorted((left, right) => left.localeCompare(right));
}

/**
 * @param {string} directory
 *
 * @returns {Promise<string[]>}
 */
async function walkFiles(directory) {
    const entries = await readdir(directory, { withFileTypes: true });
    const files = await Promise.all(
        entries.map(async (entry) => {
            const entryPath = path.join(directory, entry.name);

            if (entry.name === "__pycache__") {
                return [];
            }

            if (entry.isDirectory()) {
                return walkFiles(entryPath);
            }

            if (entry.isFile()) {
                return [entryPath];
            }

            return [];
        })
    );

    return files.flat().toSorted((left, right) => left.localeCompare(right));
}

try {
    await main();
} catch (error) {
    console.error(error);
    process.exitCode = 1;
}
