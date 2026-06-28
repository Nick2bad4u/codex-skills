# Mermaid Theme And Syntax Reference

Use this reference for dark theme snippets, chart-specific review, and Mermaid configuration. Verify renderer support before using newer syntax.

## Contents

- [Portable Dark Theme](#portable-dark-theme)
- [Palette Guidance](#palette-guidance)
- [Flowchart Patterns](#flowchart-patterns)
- [Sequence Patterns](#sequence-patterns)
- [State And Lifecycle Patterns](#state-and-lifecycle-patterns)
- [Review Checklist](#review-checklist)

## Portable Dark Theme

Use `theme: base` when the renderer accepts frontmatter config:

```mermaid
---
config:
  theme: base
  themeVariables:
    background: "#0b1020"
    mainBkg: "#111827"
    primaryColor: "#1f2937"
    primaryTextColor: "#f8fafc"
    primaryBorderColor: "#38bdf8"
    lineColor: "#94a3b8"
    secondaryColor: "#0f766e"
    tertiaryColor: "#312e81"
    noteBkgColor: "#1e293b"
    noteTextColor: "#f8fafc"
    noteBorderColor: "#64748b"
---
flowchart LR
  input["Input"] --> work["Process"] --> output["Output"]
```

When frontmatter config is not supported, keep the diagram valid with `classDef`:

```mermaid
flowchart LR
  input["Input"] --> work["Process"] --> output["Output"]

  classDef neutral fill:#111827,stroke:#64748b,color:#f8fafc
  classDef info fill:#0c4a6e,stroke:#38bdf8,color:#f0f9ff
  classDef success fill:#14532d,stroke:#22c55e,color:#f0fdf4
  classDef warn fill:#713f12,stroke:#f59e0b,color:#fffbeb
  classDef danger fill:#7f1d1d,stroke:#ef4444,color:#fef2f2

  class input info
  class work neutral
  class output success
```

## Palette Guidance

- Background: `#0b1020`
- Panel fill: `#111827`
- Neutral border: `#64748b`
- Text: `#f8fafc`
- Info: fill `#0c4a6e`, stroke `#38bdf8`
- Success: fill `#14532d`, stroke `#22c55e`
- Warning: fill `#713f12`, stroke `#f59e0b`
- Danger: fill `#7f1d1d`, stroke `#ef4444`
- External: fill `#312e81`, stroke `#a78bfa`

Do not assign every node a different hue. Use color to identify status, ownership, trust boundary, or risk.

## Flowchart Patterns

Use stable IDs and quoted labels:

```mermaid
flowchart TD
  request["User request"] --> validate{"Valid?"}
  validate -->|yes| process["Process request"]
  validate -->|no| reject["Return error"]
```

For complex systems, use subgraphs:

```mermaid
flowchart LR
  subgraph client["Client"]
    ui["UI"]
  end

  subgraph api["API"]
    route["Route"]
    service["Service"]
  end

  ui --> route --> service
```

Use edge labels only when they add meaning. Dense edge labeling makes diagrams harder to scan.

## Sequence Patterns

Use sequence diagrams for call order, not architecture maps:

```mermaid
sequenceDiagram
  autonumber
  participant User
  participant App
  participant API
  participant DB

  User->>App: Submit form
  App->>API: POST /items
  API->>DB: Insert item
  DB-->>API: Item id
  API-->>App: 201 Created
  App-->>User: Show success
```

Use `alt`, `opt`, `par`, and `loop` sparingly. If every branch needs multiple nested blocks, consider a flowchart plus a separate sequence for the important path.

## State And Lifecycle Patterns

Use state diagrams when the main question is "what states can this thing be in?"

```mermaid
stateDiagram-v2
  [*] --> Draft
  Draft --> Queued: submit
  Queued --> Running: worker starts
  Running --> Succeeded: checks pass
  Running --> Failed: checks fail
  Failed --> Queued: retry
  Succeeded --> [*]
```

## Review Checklist

- Does the chart type match the information shape?
- Does the renderer support every diagram feature used?
- Are labels short enough to read without zooming?
- Are IDs stable and separate from visible labels?
- Are class names and colors semantic rather than decorative?
- Does the diagram avoid color-only meaning?
- Does the dark theme have sufficient text and line contrast?
- Are subgraphs used to reduce crossings, not to add visual noise?
- Was the diagram rendered or syntax-checked when visual correctness matters?
