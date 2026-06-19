import { createConfig } from "remark-config-nick2bad4u";

const frontmatterSchemaPlugin =
    /** @type {import("remark-config-nick2bad4u").RemarkConfig["plugins"][number]} */ ([
        "remark-lint-frontmatter-schema",
        {
            schemas: {
                "schemas/skill-frontmatter.schema.json": ["skills/*/SKILL.md"],
            },
        },
    ]);

const remarkConfig = createConfig({
    plugins: [frontmatterSchemaPlugin],
    settings: {},
});

export default remarkConfig;
