# Repo Cleanup Implementation Plan

> **For agentic workers:** Execute tasks in order; each ends with a quick check.

**Goal:** Clean repo root launchers and unused media; clear rebuildable local caches.

**Architecture:** Delete approved paths, sync docs/i18n, leave `data/` intact.

**Tech Stack:** PowerShell cleanup; Markdown/JSON doc updates.

## Global Constraints

- Root launchers: only `launch-desktop.vbs` and `launch-desktop.bat`
- Do not delete `data/`
- No new mocks outside `tests/`
- Update docs after structural changes

---

### Task 1: Delete launchers and junk media

- [x] Delete root: `dev.bat`, `dev.sh`, `dev-desktop.bat`, `start_api.bat`, `start_api.sh`, `start_web.bat`, `start_web.sh`, `create-desktop-shortcut.bat`
- [x] Delete root: `fake_*.mp4`, `shot_pipeline_out.mp4`
- [x] Delete `apps/web/public/demo/*.mp4` and `apps/web/dist/demo/` if present

### Task 2: Clear rebuildable local directories

- [x] Remove `.worktrees/`, `apps/desktop/runtime/`, `.remotion/`

### Task 3: Sync docs and UI copy

- [x] Update README, CLAUDE.md, desktop READMEs, packaging/integration design docs
- [x] Update EditorStudioContent + i18n hints that mention `dev.bat`

### Task 4: Verify

- [x] Confirm root only has the two launchers
- [x] Run `pytest tests/ -q` (non-live / non-integration)
