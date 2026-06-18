import { access, readdir, readFile } from "node:fs/promises";
import path from "node:path";

const root = process.cwd();
const skillsRoot = path.join(root, "skills");
const namePattern = /^[a-z0-9]+(?:-[a-z0-9]+)*$/u;

function assert(condition, message) {
    if (!condition) {
        throw new Error(message);
    }
}

function linesOf(text) {
    return text.replaceAll("\r\n", "\n").replaceAll("\r", "\n").split("\n");
}

function stripMatchingQuotes(value) {
    const first = value.at(0);
    const last = value.at(-1);
    if ((first === '"' || first === "'") && first === last) {
        return value.slice(1, -1);
    }
    return value;
}

function frontmatter(markdown) {
    const lines = linesOf(markdown);
    assert(lines[0] === "---", "SKILL.md must start with YAML frontmatter");
    const end = lines.indexOf("---", 1);
    assert(end > 1, "SKILL.md frontmatter must close with ---");

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

function yamlValue(yaml, key) {
    const prefix = `${key}:`;
    for (const line of linesOf(yaml)) {
        const trimmed = line.trim();
        if (trimmed.startsWith(prefix)) {
            return stripMatchingQuotes(trimmed.slice(prefix.length).trim());
        }
    }
    return undefined;
}

async function assertFile(filePath) {
    await access(filePath);
}

const entries = await readdir(skillsRoot, { withFileTypes: true });
const skillDirs = entries
    .filter((entry) => entry.isDirectory())
    .map((entry) => entry.name)
    .sort();

assert(
    skillDirs.length > 0,
    "skills/ must contain at least one skill directory"
);

for (const skillName of skillDirs) {
    assert(
        namePattern.test(skillName),
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
        metadata.get("description")?.length > 80,
        `${skillName} description must explain when to use the skill`
    );
    assert(
        !skillMd.includes("[TODO"),
        `${skillName} SKILL.md must not contain TODO placeholders`
    );

    const openaiYaml = await readFile(openaiYamlPath, "utf8");
    assert(
        yamlValue(openaiYaml, "display_name"),
        `${skillName} agents/openai.yaml must define display_name`
    );
    assert(
        yamlValue(openaiYaml, "short_description"),
        `${skillName} agents/openai.yaml must define short_description`
    );
    assert(
        yamlValue(openaiYaml, "default_prompt")?.includes(`$${skillName}`),
        `${skillName} default_prompt must mention $${skillName}`
    );
}

console.log(`Validated ${skillDirs.length} skills: ${skillDirs.join(", ")}`);
