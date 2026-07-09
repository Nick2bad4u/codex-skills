---
name: mermaid-diagram-maintenance
description: Maintains Mermaid diagrams and config. Use when creating, editing, reviewing, theming, or debugging Mermaid flowcharts, sequence/ER/Gantt diagrams, dark themes, themeVariables, frontmatter config, renderer issues, or Markdown blocks.
---

# Mermaid Diagram Maintenance

Use this skill to produce Mermaid diagrams that are readable, valid in the target renderer, and visually consistent with dark documentation themes. Prefer clear information design over decorative complexity.

## First Pass

1. Identify the target renderer: GitHub Markdown, Docusaurus, Mermaid CLI, Mermaid Live Editor, Docs site plugin, Obsidian, VS Code preview, or another host.
2. Check whether the host supports Mermaid frontmatter config, `init` directives, icons, custom CSS, ELK layout, dark mode switching, or only plain Mermaid syntax.
3. Choose the diagram type from the information shape:
   - Flowchart for process, routing, states with decisions, or system steps.
   - Sequence for time-ordered actor interactions.
   - State for lifecycle and transitions.
   - Class for type/API relationships.
   - ER for data models.
   - Architecture, C4-style, or block diagrams only when the target renderer supports them.
   - Timeline, Gantt, mindmap, or journey only when the reader needs that specific view.
4. Ask for missing domain facts only when guessing would create a false diagram. Otherwise, draft with explicit assumptions.
5. Read `references/theme-and-syntax.md` when the user asks for dark theming, configuration, chart-specific syntax, or a diagram review.

## Diagram Design

1. Put the reader's task first. A diagram should answer one question, not display every fact in the repository.
2. Keep labels short and concrete. Move long descriptions into surrounding prose or notes.
3. Use left-to-right flow for pipelines and dependencies, top-down flow for procedures, and sequence diagrams for call order.
4. Group related nodes with subgraphs or containers when it reduces edge crossings.
5. Prefer stable IDs plus readable labels, for example `build["Build package"]`, so styling and links do not depend on label text.
6. Avoid more than 7-9 nodes in one visual group. Split dense diagrams into separate Mermaid blocks when edge crossings slow the reader down.
7. Avoid relying on color alone. Pair color with labels, line style, shape, or grouping.

## Theming

1. For dark surfaces, prefer `theme: base` plus explicit `themeVariables` so foreground, border, primary, secondary, warning, and error colors stay controlled.
2. Use high-contrast text and muted fills. Saturated fills should mark status, risk, or emphasis, not every node.
3. Keep a small semantic palette:
   - neutral for normal nodes
   - blue or cyan for inputs, services, and reads
   - green for success, completed, or safe paths
   - amber for warning, manual approval, or waiting
   - red for failure, destructive action, or security risk
   - purple only for optional or external systems when it adds meaning
4. For GitHub Markdown, expect limited theming support. Prefer class definitions and simple inline Mermaid styling over renderer-specific global config unless verified.
5. Keep theme snippets close to the diagram when portability matters; keep site-level Mermaid config in the docs framework only when a diagram set should share one palette.

## Editing And Debugging

1. Preserve the user's domain meaning before changing layout or colors.
2. Validate syntax against the target Mermaid version or renderer. Mermaid features vary by host, so do not assume the latest syntax works everywhere.
3. When a diagram fails to render, reduce it to the smallest failing block, then restore styling and details after the parse issue is fixed.
4. Escape labels that contain punctuation, brackets, pipes, Markdown, quotes, or Mermaid control words.
5. Check for common failures: unclosed subgraphs, duplicate IDs with conflicting shapes, unsupported diagram type, unsupported frontmatter config, invalid edge labels, and reserved words used as IDs.
6. If visual output matters, render a preview when tooling is available. Use Mermaid CLI, the project docs preview, browser screenshot, or the target host preview.

## Output

Return the Mermaid code block first when the user asks for a diagram. Include only the minimum explanation needed to state assumptions, renderer constraints, validation run, or how to integrate the config.
