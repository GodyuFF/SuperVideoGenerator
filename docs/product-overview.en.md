# Product overview

> Updated: 2026-07-21

Language: [中文](product-overview.md) | **English**

**SuperVideoGenerator** is an AI video product built on multi-agent collaboration. You describe an idea in natural language; the lead agent (Super Video Master) orchestrates script, storyboard, image, TTS, and editing sub-agents via **ReAct**, from concept to final cut.

## Positioning

| Dimension | Notes |
|-----------|--------|
| Core capabilities | Script-driven · asset management · shared-pool RAG · visual board |
| Interaction | Chat on the left drives the AI; the script page on the right supports manual polish |
| Orchestration | Plans are visible and reviewable, then executed step by step; optional Goal mode |
| Form factors | Browser dev mode + Electron desktop installer |

## Core principles (summary)

1. Every entity has a globally unique `asset_id`
2. Text assets and media assets are separate; media stays traceable to its source
3. Referenced assets cannot be deleted; the UI shows the reference chain
4. Only characters / props / scenes are shared across scripts
5. Full CRUD while idle; read-only after execution starts

## User value

- RAG reuses characters, scenes, and props to cut repeat work on series
- Plan / A2UI confirmation avoids black-box one-click generation
- Edit Studio multi-track timeline is previewable and writable back
- Data stays under local `data/` by default and is not committed to Git

## Next steps

- Get started: [Getting started](getting-started.en.md) ([中文](getting-started.md))
- Desktop: [apps/desktop/README.md](../apps/desktop/README.md)
