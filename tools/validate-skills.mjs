import { access, readdir, readFile } from "node:fs/promises";
import * as path from "node:path";

const root = process.cwd();
const skillsRoot = path.join(root, "skills");
const openaiYamlSchemaComment =
    "# yaml-language-server: $schema=https://json.schemastore.org/codex-skill-metadata.json";

/**
 * @param {unknown} condition
 * @param {string} message
 *
 * @returns {asserts condition}
 */
function assert(condition, message) {
    if (condition !== true) {
        throw new Error(message);
    }
}

/**
 * @param {string} filePath
 *
 * @returns {Promise<void>}
 */
async function assertFile(filePath) {
    await access(filePath);
}

/**
 * @param {string} skillDir
 * @param {string} assetPath
 * @param {string} message
 *
 * @returns {Promise<void>}
 */
async function assertRelativeAsset(skillDir, assetPath, message) {
    assert(assetPath.startsWith("./assets/"), message);
    assert(!assetPath.includes(".."), message);

    const normalizedAssetPath = assetPath.slice("./".length).split("/");
    await assertFile(path.join(skillDir, ...normalizedAssetPath));
}

/**
 * @param {string} markdown
 *
 * @returns {Map<string, string>}
 */
function frontmatter(markdown) {
    const lines = linesOf(markdown);
    assert(lines[0] === "---", "SKILL.md must start with YAML frontmatter");
    const end = lines.indexOf("---", 1);
    assert(end > 1, "SKILL.md frontmatter must close with ---");

    /** @type {Map<string, string>} */
    const values = new Map();
    for (const line of lines.slice(1, end)) {
        const separatorIndex = line.indexOf(":");
        assert(separatorIndex !== -1, `Unsupported frontmatter line: ${line}`);
        const key = line.slice(0, separatorIndex).trim();
        const value = stripMatchingQuotes(
            line.slice(separatorIndex + 1).trim()
        );
        values.set(key, value);
    }

    assert(
        values.size === 2,
        "SKILL.md frontmatter must contain only name and description"
    );
    return values;
}

/**
 * @param {string} value
 *
 * @returns {boolean}
 */
function isSkillName(value) {
    for (const part of value.split("-")) {
        if (part.length === 0) {
            return false;
        }

        for (let index = 0; index < part.length; index += 1) {
            const code = part.codePointAt(index);
            if (code === undefined) {
                return false;
            }

            const isDigit = code >= 48 && code <= 57;
            const isLowercaseLetter = code >= 97 && code <= 122;
            if (!isDigit && !isLowercaseLetter) {
                return false;
            }
        }
    }

    return true;
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
    const entries = await readdir(skillsRoot, { withFileTypes: true });
    const skillDirs = entries
        .filter((entry) => entry.isDirectory())
        .map((entry) => entry.name)
        .toSorted((left, right) => left.localeCompare(right));

    assert(
        skillDirs.length > 0,
        "skills/ must contain at least one skill directory"
    );

    await Promise.all(skillDirs.map((skillName) => validateSkill(skillName)));

    console.log(
        `Validated ${skillDirs.length} skills: ${skillDirs.join(", ")}`
    );
}

/**
 * @param {string} value
 *
 * @returns {string}
 */
function stripMatchingQuotes(value) {
    const first = value.at(0);
    const last = value.at(-1);
    if ((first === '"' || first === "'") && first === last) {
        return value.slice(1, -1);
    }
    return value;
}

/**
 * @param {string} skillName
 *
 * @returns {Promise<void>}
 */
async function validateSkill(skillName) {
    assert(
        isSkillName(skillName),
        `${skillName} must be lowercase hyphen-case`
    );

    const skillDir = path.join(skillsRoot, skillName);
    const skillMdPath = path.join(skillDir, "SKILL.md");
    const openaiYamlPath = path.join(skillDir, "agents", "openai.yaml");

    await assertFile(skillMdPath);
    await assertFile(openaiYamlPath);

    const skillMd = await readFile(skillMdPath, "utf8");
    const metadata = frontmatter(skillMd);

    assert(
        metadata.get("name") === skillName,
        `${skillName} frontmatter name must match folder`
    );
    assert(
        (metadata.get("description")?.length ?? 0) > 80,
        `${skillName} description must explain when to use the skill`
    );
    assert(
        !skillMd.includes("[TODO"),
        `${skillName} SKILL.md must not contain TODO placeholders`
    );

    const openaiYaml = await readFile(openaiYamlPath, "utf8");
    const defaultPrompt = yamlValue(openaiYaml, "default_prompt");
    const displayName = yamlValue(openaiYaml, "display_name");
    const iconLarge = yamlValue(openaiYaml, "icon_large");
    const iconSmall = yamlValue(openaiYaml, "icon_small");
    const shortDescription = yamlValue(openaiYaml, "short_description");

    assert(
        linesOf(openaiYaml)[0] === openaiYamlSchemaComment,
        `${skillName} agents/openai.yaml must declare the Codex skill metadata schema`
    );

    assert(
        displayName !== undefined && displayName.length > 0,
        `${skillName} agents/openai.yaml must define display_name`
    );
    assert(
        shortDescription !== undefined && shortDescription.length > 0,
        `${skillName} agents/openai.yaml must define short_description`
    );
    assert(
        defaultPrompt?.includes(`$${skillName}`) === true,
        `${skillName} default_prompt must mention $${skillName}`
    );

    assert(
        iconLarge !== undefined && iconLarge.length > 0,
        `${skillName} agents/openai.yaml must define icon_large`
    );
    assert(
        iconSmall !== undefined && iconSmall.length > 0,
        `${skillName} agents/openai.yaml must define icon_small`
    );

    await Promise.all([
        assertRelativeAsset(
            skillDir,
            iconLarge,
            `${skillName} icon_large must point to an existing ./assets/ file`
        ),
        assertRelativeAsset(
            skillDir,
            iconSmall,
            `${skillName} icon_small must point to an existing ./assets/ file`
        ),
    ]);
}

/**
 * @param {string} YAML
 * @param {string} key
 *
 * @returns {string | undefined}
 */
function yamlValue(YAML, key) {
    const prefix = `${key}:`;
    for (const line of linesOf(YAML)) {
        const trimmed = line.trim();
        if (trimmed.startsWith(prefix)) {
            return stripMatchingQuotes(trimmed.slice(prefix.length).trim());
        }
    }
    return undefined;
}

try {
    await main();
} catch (error) {
    console.error(error);
    process.exitCode = 1;
}
