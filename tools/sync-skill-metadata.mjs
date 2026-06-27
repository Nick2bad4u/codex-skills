import { mkdir, writeFile } from "node:fs/promises";
import * as path from "node:path";

const root = process.cwd();

const schemaComment =
    "# yaml-language-server: $schema=https://json.schemastore.org/codex-skill-metadata.json";

/**
 * @typedef {object} SkillDefinition
 *
 * @property {string} accent
 * @property {readonly string[]} [dependencies]
 * @property {string} displayName
 * @property {string} glyph
 * @property {string} longTitle
 * @property {string} name
 * @property {SkillPolicy} [policy]
 * @property {string} prompt
 * @property {string} shortDescription
 * @property {string} shortTitle
 */

/**
 * @typedef {object} SkillPolicy
 *
 * @property {boolean} [allowImplicitInvocation]
 */

/** @type {SkillDefinition[]} */
const skills = [
    {
        accent: "#0891B2",
        displayName: "Agent Skill Instruction Creation",
        glyph: "M152 168h208M152 232h152M152 296h208M184 376l64-64 40 40 72-96",
        longTitle: "Agent Skill Instruction Creation",
        name: "agent-skill-instruction-creation",
        prompt: "Use $agent-skill-instruction-creation to create agent skills or instructions for this project.",
        shortDescription: "Create skills and agent instructions",
        shortTitle: "🧩",
    },
    {
        accent: "#9333EA",
        displayName: "Agent Skill Instruction Review",
        glyph: "M152 160h160M152 224h208M152 288h128M328 312l40 40 80-104",
        longTitle: "Agent Skill Instruction Review",
        name: "agent-skill-instruction-review",
        prompt: "Use $agent-skill-instruction-review to review this repository's agent skills and instructions.",
        shortDescription: "Audit skills and agent instructions",
        shortTitle: "🔎",
    },
    {
        accent: "#0F766E",
        displayName: "CI Release Readiness",
        glyph: "M144 304h224M176 240l56 56 112-128M120 392h272",
        longTitle: "CI Release Readiness",
        name: "ci-release-readiness",
        prompt: "Use $ci-release-readiness to debug the failing check or validate this release candidate.",
        shortDescription: "Fix CI failures and verify releases",
        shortTitle: "🚦",
    },
    {
        accent: "#2563EB",
        displayName: "Code Review Maintenance",
        glyph: "M152 176l-56 80 56 80M360 176l56 80-56 80M216 360l80-208",
        longTitle: "Code Review Maintenance",
        name: "code-review-maintenance",
        prompt: "Use $code-review-maintenance to review this repository or file and handle high-confidence issues.",
        shortDescription: "Review code and fix high-confidence risks",
        shortTitle: "🛡️",
    },
    {
        accent: "#7C3AED",
        displayName: "Documentation Maintenance",
        glyph: "M160 136h144l48 48v192H160zM304 136v56h56M200 240h112M200 288h152M200 336h96",
        longTitle: "Documentation Maintenance",
        name: "documentation-maintenance",
        prompt: "Use $documentation-maintenance to audit and update the documentation for this repository.",
        shortDescription: "Fix docs, TSDoc, TypeDoc, and sites",
        shortTitle: "📚",
    },
    {
        accent: "#2656c7",
        displayName: "ESLint Plugin Maintenance",
        glyph: "M256 104l128 72v160l-128 72-128-72V176zM256 168l72 40v96l-72 40-72-40v-96z",
        longTitle: "ESLint Plugin Maintenance",
        name: "eslint-plugin-maintenance",
        prompt: "Use $eslint-plugin-maintenance to build, audit, or update this ESLint plugin repository.",
        shortDescription: "Bootstrap and maintain ESLint plugins",
        shortTitle: "🔧",
    },
    {
        accent: "#374151",
        displayName: "GitHub Actions Workflow Maintenance",
        glyph: "M152 160h208M152 224h208M152 288h128M336 288l32 32 64-80M168 352h112",
        longTitle: "GitHub Actions Workflow Maintenance",
        name: "github-actions-workflow-maintenance",
        prompt: "Use $github-actions-workflow-maintenance to create, review, or repair GitHub Actions workflows.",
        shortDescription: "Create, review, and repair workflows",
        shortTitle: "⚙️",
    },
    {
        accent: "#e2e616",
        displayName: "Lint Cleanup",
        glyph: "M160 160h192M160 224h152M160 288h192M184 360l48 48 96-112",
        longTitle: "Lint Cleanup",
        name: "lint-cleanup",
        prompt: "Use $lint-cleanup to fix the lint issues and verify a clean rerun.",
        shortDescription: "Fix lint failures without shortcuts",
        shortTitle: "🧹",
    },
    {
        accent: "#f5346e",
        displayName: "Mermaid Diagram Maintenance",
        glyph: "M144 176h96v64h-96zM272 176h96v64h-96zM208 304h96v64h-96zM240 208h32M320 240v32l-40 32M192 240v32l40 32",
        longTitle: "Mermaid Diagram Maintenance",
        name: "mermaid-diagram-maintenance",
        prompt: "Use $mermaid-diagram-maintenance to create or improve Mermaid diagrams for this project.",
        shortDescription: "Create and theme Mermaid diagrams",
        shortTitle: "🧜‍♀️",
    },
    {
        accent: "#C596C7",
        displayName: "Prettier Plugin Maintenance",
        glyph: "M144 184h224M160 256h192M184 328h144M136 384c56-104 184-120 240-40M376 128l16 32 32 16-32 16-16 32-16-32-32-16 32-16z",
        longTitle: "Prettier Plugin Maintenance",
        name: "prettier-plugin-maintenance",
        prompt: "Use $prettier-plugin-maintenance to build, audit, or update this Prettier plugin repository.",
        shortDescription: "Bootstrap and maintain Prettier plugins",
        shortTitle: "💅",
    },
    {
        accent: "#059669",
        displayName: "Release Publish Loop",
        glyph: "M152 320h208M184 256l72-72 72 72M256 184v176M152 392h208M368 152l32 32 64-80",
        longTitle: "Release Publish Loop",
        name: "release-publish-loop",
        policy: {
            allowImplicitInvocation: false,
        },
        prompt: "Use $release-publish-loop to push this release candidate, watch CI, and publish it when ready.",
        shortDescription: "Push, watch CI, and publish releases",
        shortTitle: "✅",
    },
    {
        accent: "#F59E0B",
        displayName: "Remark Plugin Maintenance",
        glyph: "M152 152h208M152 216h152M152 280h208M184 360h144M344 344l40 40 72-104",
        longTitle: "Remark Plugin Maintenance",
        name: "remark-plugin-maintenance",
        prompt: "Use $remark-plugin-maintenance to build, audit, or update this remark plugin repository.",
        shortDescription: "Bootstrap and maintain remark plugins",
        shortTitle: "🔌",
    },
    {
        accent: "#8B5CF6",
        displayName: "Stylelint Plugin Maintenance",
        glyph: "M144 336c64-128 128-160 224-160M176 360c64 32 144 24 192-48M144 184c48-48 144-64 224-24",
        longTitle: "Stylelint Plugin Maintenance",
        name: "stylelint-plugin-maintenance",
        prompt: "Use $stylelint-plugin-maintenance to build, audit, or update this Stylelint plugin repository.",
        shortDescription: "Bootstrap and maintain Stylelint plugins",
        shortTitle: "🎨",
    },
    {
        accent: "#16A34A",
        displayName: "Test Quality Maintenance",
        glyph: "M184 120h144M224 120v96l-80 144c-16 28 4 64 36 64h152c32 0 52-36 36-64l-80-144v-96M200 344h112",
        longTitle: "Test Quality Maintenance",
        name: "test-quality-maintenance",
        prompt: "Use $test-quality-maintenance to add or repair tests and verify the affected behavior.",
        shortDescription: "Fix tests and improve coverage",
        shortTitle: "🧪",
    },
    {
        accent: "#2563EB",
        displayName: "VSIcons Association Recommender",
        glyph: "M144 152h224M144 216h160M144 280h224M176 368h112M344 344l40 40 72-104",
        longTitle: "VSIcons Association Recommender",
        name: "vsicons-association-recommender",
        policy: {
            allowImplicitInvocation: false,
        },
        prompt: "Use $vsicons-association-recommender to recommend vscode-icons associations for this workspace.",
        shortDescription: "Recommend vscode-icons settings blocks",
        shortTitle: "🎭",
    },
    {
        accent: "#3b3ef4",
        displayName: "Workspace Continuation",
        glyph: "M152 176h136c56 0 96 40 96 88s-40 88-96 88H168M152 176l64-64M152 176l64 64",
        longTitle: "Workspace Continuation",
        name: "workspace-continuation",
        policy: {
            allowImplicitInvocation: false,
        },
        prompt: "Use $workspace-continuation to resume this task from the current workspace state.",
        shortDescription: "Continue work, plans, or handoffs",
        shortTitle: "⏭️",
    },
];

/**
 * @param {number} value
 * @param {number} min
 * @param {number} max
 *
 * @returns {number}
 */
function clamp(value, min, max) {
    return Math.min(max, Math.max(min, value));
}

/**
 * @param {string} value
 * @param {number} max
 * @param {number} min
 *
 * @returns {number}
 */
function compactTitleFontSize(value, max, min) {
    return clamp(max - Math.max(0, value.length - 2) * 10, min, max);
}

/**
 * @param {SkillDefinition} skill
 *
 * @returns {string}
 */
function dependenciesYaml(skill) {
    if (skill.dependencies === undefined || skill.dependencies.length === 0) {
        return "";
    }

    const dependencies = skill.dependencies
        .map((dependency) => `    - ${yamlString(dependency)}`)
        .join("\n");

    return `dependencies:
${dependencies}`;
}

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
 * @param {string} value
 *
 * @returns {number}
 */
function fullTitleFontSize(value) {
    return clamp(Math.floor(350 / Math.max(value.length * 0.58, 1)), 16, 27);
}

/**
 * @param {string} value
 *
 * @returns {boolean}
 */
function hasEmojiPresentation(value) {
    for (const character of value) {
        const codePoint = character.codePointAt(0);

        if (
            codePoint !== undefined &&
            ((codePoint >= 126_976 && codePoint <= 129_791) ||
                (codePoint >= 9728 && codePoint <= 10_175))
        ) {
            return true;
        }
    }

    return false;
}

/**
 * @param {string} hex
 *
 * @returns {{ r: number; g: number; b: number }}
 */
function hexToRgb(hex) {
    const normalized = hex.startsWith("#") ? hex.slice(1) : hex;

    if (!/^[\da-f]{6}$/iv.test(normalized)) {
        throw new Error(`Invalid hex color: ${hex}`);
    }

    return {
        b: Number.parseInt(normalized.slice(4, 6), 16),
        g: Number.parseInt(normalized.slice(2, 4), 16),
        r: Number.parseInt(normalized.slice(0, 2), 16),
    };
}

/**
 * @param {SkillDefinition} skill
 * @param {number} size
 * @param {boolean} small
 *
 * @returns {string}
 */
function iconSvg(skill, size, small) {
    const id = safeSvgId(`skill-${skill.name}-${small ? "small" : "large"}`);

    const accent = skill.accent;
    const accentLight = mixHex(accent, "#ffffff", 0.35);
    const accentSoft = mixHex(accent, "#94a3b8", 0.24);
    const accentDeep = mixHex(accent, "#020617", 0.48);
    const textCool = mixHex(accent, "#38bdf8", 0.38);
    const textWarm = mixHex(accent, "#facc15", 0.46);

    const shortTitle = escapeXml(skill.shortTitle);
    const longTitle = escapeXml(skill.longTitle);
    const displayName = escapeXml(skill.displayName);
    const isShortTitleEmoji = hasEmojiPresentation(skill.shortTitle);

    const compactFontFamily = isShortTitleEmoji
        ? "Segoe UI Emoji, Apple Color Emoji, Noto Color Emoji, Segoe UI Symbol, sans-serif"
        : "Inter, Segoe UI, Arial, sans-serif";
    const compactTitleFill = isShortTitleEmoji ? "#f8fafc" : `url(#${id}-text)`;
    const badgeFontSize = isShortTitleEmoji
        ? 48
        : compactTitleFontSize(skill.shortTitle, 58, 28);
    const badgeTextPaint = isShortTitleEmoji
        ? ""
        : ' stroke="#020617" stroke-width="2" paint-order="stroke"';
    const footerFontSize = fullTitleFontSize(skill.longTitle);
    const smallFontSize = isShortTitleEmoji
        ? 104
        : titleFontSize(skill.shortTitle, 124, 82);
    const smallTextPaint = isShortTitleEmoji
        ? ""
        : ' stroke="#020617" stroke-width="5" paint-order="stroke"';

    if (small) {
        return `<svg xmlns="http://www.w3.org/2000/svg" role="img" viewBox="0 0 512 512" width="${size}" height="${size}">
  <title>${displayName}</title>
  <defs>
    <linearGradient id="${id}-bg" x1="64" y1="32" x2="448" y2="480" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="#111827"/>
      <stop offset="0.52" stop-color="#020617"/>
      <stop offset="1" stop-color="#0f172a"/>
    </linearGradient>
    <linearGradient id="${id}-accent" x1="112" y1="96" x2="400" y2="416" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="${accentLight}"/>
      <stop offset="0.52" stop-color="${accent}"/>
      <stop offset="1" stop-color="${accentDeep}"/>
    </linearGradient>
    <linearGradient id="${id}-text" x1="152" y1="164" x2="360" y2="348" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="#ffffff"/>
      <stop offset="0.3" stop-color="${textCool}"/>
      <stop offset="0.68" stop-color="${textWarm}"/>
      <stop offset="1" stop-color="${accentLight}"/>
    </linearGradient>
    <radialGradient id="${id}-glow" cx="50%" cy="38%" r="62%">
      <stop offset="0" stop-color="${accentLight}" stop-opacity="0.42"/>
      <stop offset="0.58" stop-color="${accent}" stop-opacity="0.16"/>
      <stop offset="1" stop-color="${accentDeep}" stop-opacity="0"/>
    </radialGradient>
    <filter id="${id}-shadow" x="-24%" y="-24%" width="148%" height="148%" color-interpolation-filters="sRGB">
      <feDropShadow dx="0" dy="18" stdDeviation="18" flood-color="#000000" flood-opacity="0.42"/>
    </filter>
  </defs>

  <rect x="20" y="20" width="472" height="472" rx="112" fill="url(#${id}-bg)"/>
  <rect x="24" y="24" width="464" height="464" rx="108" fill="none" stroke="#ffffff" stroke-opacity="0.08" stroke-width="2"/>
  <circle cx="256" cy="220" r="210" fill="url(#${id}-glow)"/>

  <g opacity="0.18">
    <path d="${escapeXml(skill.glyph)}" fill="none" stroke="${accentSoft}" stroke-width="28" stroke-linecap="round" stroke-linejoin="round"/>
  </g>

  <g filter="url(#${id}-shadow)">
    <rect x="104" y="132" width="304" height="248" rx="72" fill="#020617" fill-opacity="0.72"/>
    <rect x="105.5" y="133.5" width="301" height="245" rx="70.5" fill="none" stroke="url(#${id}-accent)" stroke-opacity="0.76" stroke-width="3"/>
    <text x="256" y="256" text-anchor="middle" dominant-baseline="central" font-family="${compactFontFamily}" font-size="${smallFontSize}" font-weight="900" letter-spacing="0" fill="${compactTitleFill}"${smallTextPaint}>${shortTitle}</text>
  </g>

  <path d="M128 410h256" stroke="url(#${id}-accent)" stroke-width="10" stroke-linecap="round" opacity="0.78"/>
</svg>
`;
    }

    return `<svg xmlns="http://www.w3.org/2000/svg" role="img" viewBox="0 0 512 512" width="${size}" height="${size}">
  <title>${displayName}</title>
  <defs>
    <linearGradient id="${id}-bg" x1="48" y1="24" x2="464" y2="488" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="#111827"/>
      <stop offset="0.42" stop-color="#020617"/>
      <stop offset="1" stop-color="#0f172a"/>
    </linearGradient>
    <linearGradient id="${id}-panel" x1="112" y1="96" x2="408" y2="420" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="#1e293b" stop-opacity="0.92"/>
      <stop offset="0.54" stop-color="#020617" stop-opacity="0.94"/>
      <stop offset="1" stop-color="#111827" stop-opacity="0.92"/>
    </linearGradient>
    <linearGradient id="${id}-accent" x1="104" y1="92" x2="408" y2="420" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="${accentLight}"/>
      <stop offset="0.48" stop-color="${accent}"/>
      <stop offset="1" stop-color="${accentDeep}"/>
    </linearGradient>
    <linearGradient id="${id}-text" x1="88" y1="76" x2="424" y2="460" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="#ffffff"/>
      <stop offset="0.3" stop-color="${textCool}"/>
      <stop offset="0.68" stop-color="${textWarm}"/>
      <stop offset="1" stop-color="${accentLight}"/>
    </linearGradient>
    <linearGradient id="${id}-shine" x1="112" y1="96" x2="400" y2="392" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="#ffffff" stop-opacity="0.22"/>
      <stop offset="0.34" stop-color="#ffffff" stop-opacity="0.06"/>
      <stop offset="1" stop-color="#ffffff" stop-opacity="0"/>
    </linearGradient>
    <radialGradient id="${id}-glow" cx="50%" cy="38%" r="62%">
      <stop offset="0" stop-color="${accentLight}" stop-opacity="0.36"/>
      <stop offset="0.55" stop-color="${accent}" stop-opacity="0.15"/>
      <stop offset="1" stop-color="${accentDeep}" stop-opacity="0"/>
    </radialGradient>
    <filter id="${id}-shadow" x="-24%" y="-24%" width="148%" height="148%" color-interpolation-filters="sRGB">
      <feDropShadow dx="0" dy="20" stdDeviation="22" flood-color="#000000" flood-opacity="0.42"/>
    </filter>
    <filter id="${id}-soft-glow" x="-40%" y="-40%" width="180%" height="180%" color-interpolation-filters="sRGB">
      <feGaussianBlur stdDeviation="20" result="blur"/>
      <feMerge>
        <feMergeNode in="blur"/>
        <feMergeNode in="SourceGraphic"/>
      </feMerge>
    </filter>
  </defs>

  <rect x="20" y="20" width="472" height="472" rx="104" fill="url(#${id}-bg)"/>
  <rect x="23" y="23" width="466" height="466" rx="101" fill="none" stroke="#ffffff" stroke-opacity="0.08" stroke-width="2"/>

  <circle cx="256" cy="224" r="224" fill="url(#${id}-glow)"/>

  <g opacity="0.18">
    <path d="M72 396L396 72" stroke="url(#${id}-accent)" stroke-width="104" stroke-linecap="round"/>
    <path d="M96 144h320M96 368h320" stroke="#ffffff" stroke-width="1" stroke-opacity="0.28"/>
    <path d="M144 96v320M368 96v320" stroke="#ffffff" stroke-width="1" stroke-opacity="0.20"/>
  </g>

  <g filter="url(#${id}-shadow)">
    <rect x="82" y="76" width="348" height="324" rx="84" fill="url(#${id}-panel)"/>
    <rect x="84" y="78" width="344" height="320" rx="82" fill="none" stroke="url(#${id}-accent)" stroke-opacity="0.72" stroke-width="3"/>
    <path d="M108 114c56-36 162-52 296-12" fill="none" stroke="url(#${id}-shine)" stroke-width="34" stroke-linecap="round"/>
  </g>

  <g filter="url(#${id}-soft-glow)" opacity="0.52" transform="translate(0 -18)">
    <path d="${escapeXml(skill.glyph)}" fill="none" stroke="${accent}" stroke-width="42" stroke-linecap="round" stroke-linejoin="round"/>
  </g>

  <g transform="translate(0 -18)">
    <path d="${escapeXml(skill.glyph)}" fill="none" stroke="#020617" stroke-opacity="0.55" stroke-width="36" stroke-linecap="round" stroke-linejoin="round"/>
    <path d="${escapeXml(skill.glyph)}" fill="none" stroke="url(#${id}-accent)" stroke-width="22" stroke-linecap="round" stroke-linejoin="round"/>
    <path d="${escapeXml(skill.glyph)}" fill="none" stroke="#ffffff" stroke-opacity="0.24" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"/>
  </g>

  <g filter="url(#${id}-shadow)">
    <rect x="72" y="66" width="130" height="84" rx="30" fill="#020617" fill-opacity="0.82"/>
    <rect x="73.5" y="67.5" width="127" height="81" rx="28.5" fill="none" stroke="url(#${id}-accent)" stroke-width="3"/>
    <text x="137" y="108" text-anchor="middle" dominant-baseline="central" font-family="${compactFontFamily}" font-size="${badgeFontSize}" font-weight="900" letter-spacing="0" fill="${compactTitleFill}"${badgeTextPaint}>${shortTitle}</text>
  </g>

  <g filter="url(#${id}-shadow)">
    <rect x="62" y="418" width="388" height="56" rx="24" fill="#020617" fill-opacity="0.86"/>
    <rect x="63.5" y="419.5" width="385" height="53" rx="22.5" fill="none" stroke="url(#${id}-accent)" stroke-opacity="0.56" stroke-width="2"/>
    <text x="256" y="446" text-anchor="middle" dominant-baseline="middle" font-family="Inter, Segoe UI, Arial, sans-serif" font-size="${footerFontSize}" font-weight="800" letter-spacing="0" fill="url(#${id}-text)" stroke="#020617" stroke-width="3" paint-order="stroke">${longTitle}</text>
  </g>
</svg>
`;
}

/**
 * @param {string} from
 * @param {string} to
 * @param {number} amount
 *
 * @returns {string}
 */
function mixHex(from, to, amount) {
    const a = hexToRgb(from);
    const b = hexToRgb(to);
    const weight = clamp(amount, 0, 1);

    return rgbToHex({
        b: a.b + (b.b - a.b) * weight,
        g: a.g + (b.g - a.g) * weight,
        r: a.r + (b.r - a.r) * weight,
    });
}

/**
 * @param {SkillDefinition} skill
 *
 * @returns {string}
 */
function openaiYaml(skill) {
    const optionalSections = [dependenciesYaml(skill), policyYaml(skill)]
        .filter((section) => section.length > 0)
        .join("\n\n");
    const optionalYaml =
        optionalSections.length > 0 ? `\n\n${optionalSections}` : "";

    return `${schemaComment}
interface:
    brand_color: ${yamlString(skill.accent)}
    default_prompt: ${yamlString(skill.prompt)}
    display_name: ${yamlString(skill.displayName)}
    icon_large: ${yamlString(`./assets/${skill.name}.svg`)}
    icon_small: ${yamlString(`./assets/${skill.name}-small.svg`)}
    short_description: ${yamlString(skill.shortDescription)}${optionalYaml}
`;
}

/**
 * @param {SkillDefinition} skill
 *
 * @returns {string}
 */
function policyYaml(skill) {
    if (skill.policy?.allowImplicitInvocation === undefined) {
        return "";
    }

    return `policy:
    allow_implicit_invocation: ${String(skill.policy.allowImplicitInvocation)}`;
}

/**
 * @param {{ r: number; g: number; b: number }} rgb
 *
 * @returns {string}
 */
function rgbToHex(rgb) {
    return `#${toHex(rgb.r)}${toHex(rgb.g)}${toHex(rgb.b)}`;
}

/**
 * @param {string} value
 *
 * @returns {string}
 */
function safeSvgId(value) {
    let result = "";

    for (const character of value) {
        const code = character.codePointAt(0);
        const isDigit = code !== undefined && code >= 48 && code <= 57;
        const isUppercase = code !== undefined && code >= 65 && code <= 90;
        const isLowercase = code !== undefined && code >= 97 && code <= 122;
        const isSeparator = character === "-" || character === "_";

        result +=
            isDigit || isUppercase || isLowercase || isSeparator
                ? character
                : "-";
    }

    return result;
}

/**
 * @param {string} value
 * @param {number} max
 * @param {number} min
 *
 * @returns {number}
 */
function titleFontSize(value, max, min) {
    return clamp(max - Math.max(0, value.length - 2) * 6, min, max);
}

/**
 * @param {number} value
 *
 * @returns {string}
 */
function toHex(value) {
    return clamp(Math.round(value), 0, 255).toString(16).padStart(2, "0");
}

/**
 * @param {string} value
 *
 * @returns {string}
 */
function yamlString(value) {
    return JSON.stringify(value);
}

await Promise.all(
    skills.map(async (skill) => {
        const skillRoot = path.join(root, "skills", skill.name);
        const assetsRoot = path.join(skillRoot, "assets");
        const agentsRoot = path.join(skillRoot, "agents");

        await mkdir(assetsRoot, { recursive: true });
        await mkdir(agentsRoot, { recursive: true });

        await Promise.all([
            writeFile(
                path.join(assetsRoot, `${skill.name}.svg`),
                iconSvg(skill, 512, false),
                "utf8"
            ),
            writeFile(
                path.join(assetsRoot, `${skill.name}-small.svg`),
                iconSvg(skill, 96, true),
                "utf8"
            ),
            writeFile(
                path.join(agentsRoot, "openai.yaml"),
                openaiYaml(skill),
                "utf8"
            ),
        ]);
    })
);

console.log(`Synced ${skills.length} skill metadata and icon sets.`);
