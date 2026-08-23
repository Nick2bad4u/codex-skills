import { readdir, readFile } from "node:fs/promises";
import * as path from "node:path";
import { fileURLToPath } from "node:url";

const reportDisplayPath = "coverage/python/coverage.xml";
const reportPath = fileURLToPath(
    new URL("../coverage/python/coverage.xml", import.meta.url)
);
const repositoryRoot = fileURLToPath(new URL("../", import.meta.url));
const skillsRoot = fileURLToPath(new URL("../skills/", import.meta.url));
const report = await readFile(reportPath, "utf8");
const filenamePattern = /filename="(?<filename>[^"]+)"/v;
const reportedFiles = new Set(
    report
        .split("<class ")
        .slice(1)
        .map((classElement) => {
            const filename =
                filenamePattern.exec(classElement)?.groups?.filename;

            if (typeof filename !== "string") {
                throw new TypeError(
                    "Coverage report contains a class without a filename."
                );
            }

            return filename
                .replaceAll("&quot;", '"')
                .replaceAll("&apos;", "'")
                .replaceAll("&lt;", "<")
                .replaceAll("&gt;", ">")
                .replaceAll("&amp;", "&");
        })
);

if (reportedFiles.size === 0) {
    throw new Error(
        `Coverage report contains no class filenames: ${reportDisplayPath}`
    );
}

const skillEntries = await readdir(skillsRoot, {
    recursive: true,
    withFileTypes: true,
});
const expectedHelpers = new Set(
    skillEntries
        .filter(
            (entry) =>
                entry.isFile() &&
                entry.name.endsWith(".py") &&
                path.basename(entry.parentPath) === "scripts"
        )
        .map((entry) =>
            path
                .relative(
                    repositoryRoot,
                    path.join(entry.parentPath, entry.name)
                )
                .replaceAll("\\", "/")
        )
);

for (const filename of reportedFiles) {
    const normalizedFilename = filename.replaceAll("\\", "/");
    const hasDrivePrefix = /^[A-Za-z]:\//v.test(normalizedFilename);
    const hasParentTraversal = normalizedFilename.split("/").includes("..");
    const hasWindowsSeparator = filename.includes("\\");
    const isAbsolute = path.isAbsolute(filename);
    const isExpectedHelper = expectedHelpers.has(normalizedFilename);

    if (
        hasDrivePrefix ||
        hasParentTraversal ||
        hasWindowsSeparator ||
        isAbsolute ||
        !isExpectedHelper
    ) {
        throw new Error(
            `Coverage filename is not a tracked repository-relative helper path: ${filename}`
        );
    }
}

const missingHelpers = [];

for (const filename of expectedHelpers) {
    if (!reportedFiles.has(filename)) {
        missingHelpers.push(filename);
    }
}

if (missingHelpers.length > 0) {
    throw new Error(
        `Coverage report is missing tracked Python helpers: ${missingHelpers.join(", ")}`
    );
}

console.log(
    `Validated ${reportedFiles.size} repository-relative Codecov file paths in ${reportDisplayPath}.`
);
