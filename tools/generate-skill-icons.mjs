import { mkdir, writeFile } from "node:fs/promises";
import * as path from "node:path";

const root = process.cwd();

const schemaComment =
    "# yaml-language-server: $schema=https://json.schemastore.org/codex-skill-metadata.json";

const skills = [
    {
        accent: "#0891B2",
        displayName: "Agent Skill Instruction Creation",
        glyph: "M152 168h208M152 232h152M152 296h208M184 376l64-64 40 40 72-96",
        name: "agent-skill-instruction-creation",
        prompt: "Use $agent-skill-instruction-creation to create agent skills or instructions for this project.",
        shortDescription: "Create skills and agent instructions",
        title: "AC",
    },
    {
        accent: "#9333EA",
        displayName: "Agent Skill Instruction Review",
        glyph: "M152 160h160M152 224h208M152 288h128M328 312l40 40 80-104",
        name: "agent-skill-instruction-review",
        prompt: "Use $agent-skill-instruction-review to review this repository's agent skills and instructions.",
        shortDescription: "Audit skills and agent instructions",
        title: "SR",
    },
    {
        accent: "#0F766E",
        displayName: "CI Release Readiness",
        glyph: "M144 304h224M176 240l56 56 112-128M120 392h272",
        name: "ci-release-readiness",
        prompt: "Use $ci-release-readiness to debug the failing check or validate this release candidate.",
        shortDescription: "Fix CI failures and verify releases",
        title: "CI",
    },
    {
        accent: "#2563EB",
        displayName: "Code Review Maintenance",
        glyph: "M152 176l-56 80 56 80M360 176l56 80-56 80M216 360l80-208",
        name: "code-review-maintenance",
        prompt: "Use $code-review-maintenance to review this repository or file and handle high-confidence issues.",
        shortDescription: "Review code and fix high-confidence risks",
        title: "RV",
    },
    {
        accent: "#7C3AED",
        displayName: "Documentation Maintenance",
        glyph: "M160 136h144l48 48v192H160zM304 136v56h56M200 240h112M200 288h152M200 336h96",
        name: "documentation-maintenance",
        prompt: "Use $documentation-maintenance to audit and update the documentation for this repository.",
        shortDescription: "Fix docs, TSDoc, TypeDoc, and sites",
        title: "DOC",
    },
    {
        accent: "#4F46E5",
        displayName: "ESLint Plugin Maintenance",
        glyph: "M256 104l128 72v160l-128 72-128-72V176zM256 168l72 40v96l-72 40-72-40v-96z",
        name: "eslint-plugin-maintenance",
        prompt: "Use $eslint-plugin-maintenance to build, audit, or update this ESLint plugin repository.",
        shortDescription: "Bootstrap and maintain ESLint plugins",
        title: "ES",
    },
    {
        accent: "#2DA44E",
        displayName: "GitHub Actions Workflow Maintenance",
        glyph: "M152 160h208M152 224h208M152 288h128M336 288l32 32 64-80M168 352h112",
        name: "github-actions-workflow-maintenance",
        prompt: "Use $github-actions-workflow-maintenance to create, review, or repair GitHub Actions workflows.",
        shortDescription: "Create, review, and repair workflows",
        title: "GA",
    },
    {
        accent: "#DC2626",
        displayName: "Lint Cleanup",
        glyph: "M160 160h192M160 224h152M160 288h192M184 360l48 48 96-112",
        name: "lint-cleanup",
        prompt: "Use $lint-cleanup to fix the lint issues and verify a clean rerun.",
        shortDescription: "Fix lint failures without shortcuts",
        title: "LC",
    },
    {
        accent: "#F59E0B",
        displayName: "Remark Plugin Maintenance",
        glyph: "M152 152h208M152 216h152M152 280h208M184 360h144M344 344l40 40 72-104",
        name: "remark-plugin-maintenance",
        prompt: "Use $remark-plugin-maintenance to build, audit, or update this remark plugin repository.",
        shortDescription: "Bootstrap and maintain remark plugins",
        title: "RM",
    },
    {
        accent: "#0EA5E9",
        displayName: "Stylelint Plugin Maintenance",
        glyph: "M144 336c64-128 128-160 224-160M176 360c64 32 144 24 192-48M144 184c48-48 144-64 224-24",
        name: "stylelint-plugin-maintenance",
        prompt: "Use $stylelint-plugin-maintenance to build, audit, or update this Stylelint plugin repository.",
        shortDescription: "Bootstrap and maintain Stylelint plugins",
        title: "SL",
    },
    {
        accent: "#16A34A",
        displayName: "Test Quality Maintenance",
        glyph: "M184 120h144M224 120v96l-80 144c-16 28 4 64 36 64h152c32 0 52-36 36-64l-80-144v-96M200 344h112",
        name: "test-quality-maintenance",
        prompt: "Use $test-quality-maintenance to add or repair tests and verify the affected behavior.",
        shortDescription: "Fix tests and improve coverage",
        title: "TQ",
    },
    {
        accent: "#2563EB",
        displayName: "VSIcons Association Recommender",
        glyph: "M144 152h224M144 216h160M144 280h224M176 368h112M344 344l40 40 72-104",
        name: "vsicons-association-recommender",
        prompt: "Use $vsicons-association-recommender to recommend vscode-icons associations for this workspace.",
        shortDescription: "Recommend vscode-icons settings blocks",
        title: "VS",
    },
    {
        accent: "#EA580C",
        displayName: "Workspace Continuation",
        glyph: "M152 176h136c56 0 96 40 96 88s-40 88-96 88H168M152 176l64-64M152 176l64 64",
        name: "workspace-continuation",
        prompt: "Use $workspace-continuation to resume this task from the current workspace state.",
        shortDescription: "Continue work, plans, or handoffs",
        title: "WS",
    },
];

/**
 * @param {string} value
 *
 * @returns {string}
 */
function escapeXml(value) {
    return value
        .replaceAll("&", "&amp;")
        .replaceAll('"', "&quot;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;");
}

/**
 * @param {(typeof skills)[number]} skill
 * @param {number} size
 * @param {boolean} small
 *
 * @returns {string}
 */
function iconSvg(skill, size, small) {
    const fontSize = small ? 24 : 52;
    const lineWidth = small ? 32 : 18;
    const titleY = small ? 58 : 116;
    const iconOpacity = small ? "0.18" : "0.16";
    const title = small
        ? ""
        : `  <text x="256" y="${titleY}" text-anchor="middle" font-family="Inter, Segoe UI, Arial, sans-serif" font-size="${fontSize}" font-weight="800" fill="#f8fafc">${escapeXml(skill.title)}</text>
`;

    return `<svg xmlns="http://www.w3.org/2000/svg" role="img" viewBox="0 0 512 512" width="${size}" height="${size}">
  <title>${escapeXml(skill.displayName)}</title>
  <rect width="512" height="512" rx="96" fill="#0f172a"/>
  <path d="M96 416L416 96" stroke="${skill.accent}" stroke-width="120" stroke-linecap="round" opacity="${iconOpacity}"/>
  <circle cx="256" cy="256" r="168" fill="${skill.accent}" opacity="0.18"/>
  <path d="${skill.glyph}" fill="none" stroke="${skill.accent}" stroke-width="${lineWidth}" stroke-linecap="round" stroke-linejoin="round"/>
${title}
</svg>
`;
}

/**
 * @param {(typeof skills)[number]} skill
 *
 * @returns {string}
 */
function openaiYaml(skill) {
    return `${schemaComment}
interface:
    brand_color: "${skill.accent}"
    default_prompt: "${skill.prompt}"
    display_name: "${skill.displayName}"
    icon_large: "./assets/${skill.name}.svg"
    icon_small: "./assets/${skill.name}-small.svg"
    short_description: "${skill.shortDescription}"
`;
}

await Promise.all(
    skills.map(async (skill) => {
        const skillRoot = path.join(root, "skills", skill.name);
        const assetsRoot = path.join(skillRoot, "assets");
        await mkdir(assetsRoot, { recursive: true });
        await writeFile(
            path.join(assetsRoot, `${skill.name}.svg`),
            iconSvg(skill, 512, false)
        );
        await writeFile(
            path.join(assetsRoot, `${skill.name}-small.svg`),
            iconSvg(skill, 96, true)
        );
        await writeFile(
            path.join(skillRoot, "agents", "openai.yaml"),
            openaiYaml(skill)
        );
    })
);

console.log(`Generated ${skills.length} skill icon sets.`);
