import { readdir } from "node:fs/promises";
import * as path from "node:path";
import { types } from "node:util";

const auditUrl = "https://add-skill.vercel.sh/audit";
const defaultSource = "Nick2bad4u/codex-skills";
const root = process.cwd();
const skillsRoot = path.join(root, "skills");

/**
 * @typedef {object} AuditEntry
 *
 * @property {{ analyzedAt?: string; risk?: string }} [ath]
 * @property {{
 *     alerts?: number;
 *     analyzedAt?: string;
 *     risk?: string;
 *     score?: number;
 * }} [socket]
 * @property {{ analyzedAt?: string; risk?: string }} [snyk]
 */

/**
 * @typedef {object} Options
 *
 * @property {boolean} help
 * @property {boolean} jsonOutput
 * @property {string} source
 * @property {number} timeoutMs
 */

/**
 * @param {string[]} skillNames
 * @param {Options} options
 *
 * @returns {Promise<Record<string, AuditEntry>>}
 */
async function fetchAudit(skillNames, options) {
    const parameters = new URLSearchParams({
        skills: skillNames.join(","),
        source: options.source,
    });
    const response = await fetch(`${auditUrl}?${parameters.toString()}`, {
        signal: AbortSignal.timeout(options.timeoutMs),
    });

    if (!response.ok) {
        throw new Error(
            `Audit request failed with ${response.status} ${response.statusText}`
        );
    }

    return normalizeAudit(await response.json());
}

/**
 * @param {AuditEntry | undefined} entry
 *
 * @returns {string}
 */
function genRisk(entry) {
    return riskLabel(entry?.ath?.risk);
}

/**
 * @returns {Promise<string[]>}
 */
async function getSkillNames() {
    const entries = await readdir(skillsRoot, { withFileTypes: true });

    return entries
        .filter((entry) => entry.isDirectory())
        .map((entry) => entry.name)
        .toSorted((left, right) => left.localeCompare(right));
}

/**
 * @param {AuditEntry | undefined} entry
 *
 * @returns {string}
 */
function latestAnalysis(entry) {
    const analyzedAtValues = [
        entry?.ath?.analyzedAt,
        entry?.socket?.analyzedAt,
        entry?.snyk?.analyzedAt,
    ]
        .filter((value) => typeof value === "string")
        .toSorted((left, right) => left.localeCompare(right));

    return analyzedAtValues.at(-1) ?? "--";
}

/**
 * @param {unknown} value
 *
 * @returns {Record<string, AuditEntry>}
 */
function normalizeAudit(value) {
    if (typeof value !== "object" || value === null || Array.isArray(value)) {
        throw new TypeError("Audit endpoint returned an invalid response");
    }

    return /** @type {Record<string, AuditEntry>} */ (value);
}

/**
 * @param {string} value
 * @param {number} width
 *
 * @returns {string}
 */
function padEnd(value, width) {
    return value + " ".repeat(Math.max(0, width - value.length));
}

/**
 * @param {string[]} commandLineArguments
 *
 * @returns {Options}
 */
function parseOptions(commandLineArguments) {
    /** @type {Options} */
    const options = {
        help: false,
        jsonOutput: false,
        source: defaultSource,
        timeoutMs: 15_000,
    };

    for (let index = 0; index < commandLineArguments.length; index += 1) {
        const argument = commandLineArguments[index] ?? "";

        if (argument === "--json") {
            options.jsonOutput = true;
        } else if (argument === "--source") {
            const source = commandLineArguments.at(index + 1);
            if (source === undefined || source.startsWith("-")) {
                throw new Error("--source requires an owner/repo value");
            }
            options.source = source;
            index += 1;
        } else if (argument.startsWith("--source=")) {
            options.source = argument.slice("--source=".length);
        } else if (argument === "--timeout-ms") {
            const timeout = commandLineArguments.at(index + 1);
            if (timeout === undefined || timeout.startsWith("-")) {
                throw new Error("--timeout-ms requires a numeric value");
            }
            options.timeoutMs = parseTimeout(timeout);
            index += 1;
        } else if (argument.startsWith("--timeout-ms=")) {
            options.timeoutMs = parseTimeout(
                argument.slice("--timeout-ms=".length)
            );
        } else if (argument === "--help" || argument === "-h") {
            options.help = true;
        } else {
            throw new Error(`Unknown argument: ${argument}`);
        }
    }

    return options;
}

/**
 * @param {string} value
 *
 * @returns {number}
 */
function parseTimeout(value) {
    const timeout = Number(value);

    if (!Number.isSafeInteger(timeout) || timeout <= 0) {
        throw new Error("--timeout-ms must be a positive integer");
    }

    return timeout;
}

function printHelp() {
    console.log(`Usage: npm run audit:skills -- [options]

Options:
  --json                 Print raw audit JSON.
  --source <owner/repo>  Audit source slug. Defaults to ${defaultSource}.
  --timeout-ms <ms>      Request timeout. Defaults to 15000.
  --help, -h             Show this help.
`);
}

/**
 * @param {Record<string, AuditEntry>} audit
 * @param {string[]} skillNames
 * @param {Options} options
 *
 * @returns {void}
 */
function printTable(audit, skillNames, options) {
    const skillWidth = Math.max(
        "Skill".length,
        ...skillNames.map((skillName) => skillName.length)
    );
    const rows = [
        `${padEnd("Skill", skillWidth)}  ${padEnd("Gen", 10)}  ${padEnd("Socket", 12)}  ${padEnd("Snyk", 10)}  Latest Analysis`,
        `${"-".repeat(skillWidth)}  ${"-".repeat(10)}  ${"-".repeat(12)}  ${"-".repeat(10)}  ${"-".repeat(15)}`,
    ];

    for (const skillName of skillNames) {
        const entry = audit[skillName];
        rows.push(
            `${padEnd(skillName, skillWidth)}  ${padEnd(genRisk(entry), 10)}  ${padEnd(socketRisk(entry), 12)}  ${padEnd(snykRisk(entry), 10)}  ${latestAnalysis(entry)}`
        );
    }

    rows.push("", `Details: https://skills.sh/${options.source}`);
    console.log(rows.join("\n"));
}

/**
 * @param {string | undefined} risk
 *
 * @returns {string}
 */
function riskLabel(risk) {
    switch (risk) {
        case "critical": {
            return "Critical";
        }
        case "high": {
            return "High";
        }
        case "low": {
            return "Low";
        }
        case "medium": {
            return "Medium";
        }
        case "safe": {
            return "Safe";
        }
        case undefined: {
            return "--";
        }
        default: {
            return "--";
        }
    }
}

/**
 * @param {AuditEntry | undefined} entry
 *
 * @returns {string}
 */
function snykRisk(entry) {
    return riskLabel(entry?.snyk?.risk);
}

/**
 * @param {AuditEntry | undefined} entry
 *
 * @returns {string}
 */
function socketRisk(entry) {
    if (entry?.socket === undefined) {
        return "--";
    }

    const alerts = entry.socket.alerts ?? 0;

    return `${alerts} alert${alerts === 1 ? "" : "s"}`;
}

try {
    const options = parseOptions(process.argv.slice(2));

    if (options.help) {
        printHelp();
    } else {
        const skillNames = await getSkillNames();
        const audit = await fetchAudit(skillNames, options);

        if (options.jsonOutput) {
            process.stdout.write(`${JSON.stringify(audit, null, 2)}\n`);
        } else {
            printTable(audit, skillNames, options);
        }
    }
} catch (error) {
    console.error(types.isNativeError(error) ? error.message : error);
    process.exitCode = 1;
}
