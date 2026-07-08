# OpenCut Integration Architecture

SuperVideoGenerator 引入 OpenCut (MIT License) 作为剪辑基础设施。本文档描述集成架构、通信协议和开发工作流。

## Overview

```
┌──────────────────────────────────────────────────────────┐
│                  SuperVideoGenerator                      │
│                                                           │
│  ┌────────┐  ┌────────┐  ┌────────────────────────┐     │
│  │AI Chat │  │ Board  │  │  OpenCut Editor        │     │
│  │(Vite/  │  │(React) │  │  (TanStack Start/      │     │
│  │ React) │  │        │  │   iframe embedded)     │     │
│  └───┬────┘  └───┬────┘  └───────────┬────────────┘     │
│      │           │                    │                   │
│      │    ┌──────┴────────┐          │                   │
│      │    │ Agent Bridge  │◄─────────┤                   │
│      │    │ (Python FastAPI│ postMessage/api              │
│      │    │  + MCP tools) │          │                   │
│      │    └───────────────┘          │                   │
│      │           │                    │                   │
│      ▼           ▼                    ▼                   │
│  ┌──────────────────────────────────────────┐            │
│  │         Python Backend (FastAPI)          │            │
│  │  - Agent orchestration (ReAct)           │            │
│  │  - Asset storage & management            │            │
│  │  - Edit session bridge API               │            │
│  │  - FFmpeg export fallback                │            │
│  └──────────────────────────────────────────┘            │
└──────────────────────────────────────────────────────────┘
```

## Tech Stack

| Layer | SuperVideoGenerator | OpenCut |
|-------|-------------------|---------|
| Frontend | Vite + React + TypeScript | TanStack Start + Vite + React + TypeScript |
| Styling | Custom CSS variables | Tailwind CSS + shadcn/ui |
| Backend | Python FastAPI | Elysia (Bun) on Cloudflare Workers |
| Database | File-based + SQLite | PostgreSQL (Drizzle ORM) |
| Build | Manual scripts | Moon + Bun + Turbo |
| Rendering | Canvas 2D | GPU/WASM (Rust wgpu) |
| Package Manager | npm | Bun |

## Development Setup

### Prerequisites

- Bun ≥ 1.3.11 (install via `proto` or directly)
- Docker & Docker Compose (for PostgreSQL, Redis, MinIO)
- Python 3.11+ (for SuperVideoGenerator backend)

### Quick Start

```bash
# 1. Install Bun
curl -fsSL https://bun.sh/install | bash

# 2. Install OpenCut deps
cd opencut/apps/web
bun install

# 3. Start DB services
docker compose up -d db redis minio

# 4. Start OpenCut dev server (port 5173)
cd opencut
bun run apps/web:dev

# 5. Start SuperVideoGenerator backend (port 8000)
cd apps/api
uvicorn main:app --port 8000

# 6. Start SuperVideoGenerator frontend (port 3000)
cd apps/web
npm run dev
```

## Communication Protocol

### iframe Host → Editor (postMessage)

```typescript
// SuperVideoGenerator → OpenCut
interface HostToEditor {
  type: "load_project";
  project: {
    id: string;
    name: string;
    timeline: EditTimelineData;
    mediaAssets: MediaAsset[];
  };
}

// OpenCut → SuperVideoGenerator
interface EditorToHost {
  type: "timeline_changed";
  timeline: EditTimelineData;
}
```

### Agent → Editor (REST API)

```
GET  /api/projects/{id}/scripts/{sid}/edit-session
     → { timeline, media, revision }

PATCH /api/projects/{id}/scripts/{sid}/edit-session
     → Agent applies changes, returns updated session

POST /api/projects/{id}/scripts/{sid}/edit-session/export
     → Triggers export, returns job_id
```

## Data Mapping

### VideoPlan → OpenCut Timeline

| SuperVideoGenerator | OpenCut |
|---------------------|---------|
| VideoPlan.shots[] | Scene elements |
| Shot.narration_text | Text/Subtitle element |
| Shot.duration_ms | Element duration |
| Shot.camera_motion | Ken Burns animation preset |
| MediaAsset (image) | Image element on timeline |
| MediaAsset (audio) | Audio element on timeline |

### Asset Synchronization

1. Agent generates assets → stored in SuperVideoGenerator filesystem
2. Asset metadata registered in Python backend
3. OpenCut requests assets via proxy API (`/api/media/{id}/file`)
4. Python backend serves file with appropriate CORS headers
5. OpenCut caches locally in IndexedDB/MediaSource

## Agent Tool Integration

### New Editing Agent Tools

```
get_edit_timeline   — Query current timeline state
add_clip            — Add media clip to timeline
update_clip         — Modify clip properties
remove_clip         — Delete clip from timeline
apply_effect        — Apply visual effect to clip
set_keyframe        — Set animation keyframe
export_timeline     — Trigger video export
get_export_status   — Query export progress
```

### Tool Communication Flow

1. Agent decides action → calls tool via LLM function calling
2. Python tool handler validates params
3. Handler makes REST call to edit-session API
4. API bridges to OpenCut editor via postMessage or direct state mutation
5. Response flows back through the chain to Agent as observation

## Directory Structure

```
SuperVideoGenerator/
├── opencut/                    # OpenCut project (MIT License)
│   ├── apps/
│   │   ├── web/               # Next.js/TanStack editor frontend
│   │   └── api/               # Elysia API server
│   └── docs/                   # OpenCut-specific docs
├── apps/
│   ├── web/                    # SuperVideoGenerator frontend
│   │   └── src/
│   │       └── edit/
│   │           ├── opencut-bridge.ts       # postMessage bridge
│   │           └── opencut-integration.tsx # iframe host component
│   └── api/                    # SuperVideoGenerator backend
│       └── routes/
│           └── edit_session.py # Agent-Editor bridge API
├── core/
│   └── llm/tools/editing/
│       ├── opencut_tools.py    # Agent tool definitions
│       └── opencut_handler.py  # Tool handler implementations
└── docs/
    └── opencut-integration.md  # This document
```
