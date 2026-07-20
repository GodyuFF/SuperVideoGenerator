# Electron Desktop Shell Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an Electron shell that runs existing FastAPI + Vite UI and hydrates OpenCut media via local filesystem IPC instead of HTTP fetch.

**Architecture:** Electron main owns window + IPC path sandboxed to `data/`; preload exposes `window.svfDesktop`; web hydrate prefers IPC when desktop.

**Tech Stack:** Electron 33+, Node ESM/CJS as needed, existing Vite React app, unchanged FastAPI.

## Global Constraints

- No HTTP mocks in production code; tests only under `tests/` or desktop unit tests colocated.
- Chinese JSDoc on new exported functions/classes.
- Update docs after code (`code-design-plan`, product-plan brief note).
- Windows-first; keep browser path working.

---

### Task 1: Electron package scaffold + IPC media reader

**Files:**
- Create: `apps/desktop/package.json`
- Create: `apps/desktop/main.cjs`
- Create: `apps/desktop/preload.cjs`
- Create: `apps/desktop/mediaPath.cjs`
- Create: `apps/desktop/mediaPath.test.cjs` (node:test) or pytest-less node assert script

- [ ] Step 1: Scaffold package with electron dependency and `start` script
- [ ] Step 2: Implement safe relative→absolute media path resolver under data root
- [ ] Step 3: Implement `media:readLocal` IPC returning `{ buffer, mime, name }`
- [ ] Step 4: Create BrowserWindow loading `DESKTOP_WEB_URL` (default `http://127.0.0.1:5173`)
- [ ] Step 5: Run path unit assertions

### Task 2: Frontend desktop bridge + hydrate path

**Files:**
- Create: `apps/web/src/desktop/svfDesktop.ts`
- Create: `apps/web/src/desktop/types.ts`
- Modify: `apps/web/src/editor/adapter/SvfMediaBridge.ts`
- Modify: `apps/web/src/vite-env.d.ts` (if present) for `Window.svfDesktop`
- Create: `apps/web/src/desktop/svfDesktop.test.ts` or unit test via existing vitest — **if no vitest**, keep logic thin and test path via desktop node tests only

- [ ] Step 1: Add typed `getSvfDesktop()` helper
- [ ] Step 2: In `hydrateSingleAsset`, if desktop, IPC read → `File`
- [ ] Step 3: Typecheck / manual smoke notes

### Task 3: Dev launcher + docs

**Files:**
- Create: `dev-desktop.bat`
- Modify: `docs/superpowers/reference/code-design-plan.md` §2
- Modify: `docs/superpowers/reference/product-plan.md` / `README.md` brief
- Modify: `CLAUDE.md` commands if needed

- [ ] Step 1: Batch that starts API + web + electron
- [ ] Step 2: Docs sync
- [ ] Step 3: `pytest tests/ -q` (ensure no regressions)

---
