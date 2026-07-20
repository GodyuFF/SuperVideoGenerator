# 实际生成提示词预览 Implementation Plan

> **For agentic workers:** Implement task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** 图文详情页提示词旁小眼睛可预览与生图/生视频一致的实际完整提示词。

**Architecture:** `core/assets/resolved_prompt.py` 聚合现有 compose/resolve；`GET .../resolved-prompt` 暴露；前端 `ResolvedPromptPreview` 按需拉取并弹层展示。

**Tech Stack:** FastAPI、现有 `linked_assets_prompt` / `frames.resolve_frame_generation_prompt`、React + `AssetDetailShell` 体系、i18n。

## Global Constraints

- 禁止前端自行拼装关联上下文；必须复用后端解析函数。
- 主区仍显示存档提示词；不写回 content；本期不做双栏对照与分镜抽屉。
- 中文 docstring；无非测试 mock；改后更新 docs + 跑 pytest。

---

### Task 1: 领域层 `build_resolved_prompt`

**Files:**
- Create: `core/assets/resolved_prompt.py`
- Test: `tests/unit/test_resolved_prompt.py`

- [ ] 实现 `build_resolved_prompt(store, project_id, asset_id) -> dict`，按类型分支调用现有函数
- [ ] 单元测试：frame 含关联上下文；无 refs 时 differs=false；未知资产抛错

### Task 2: API 路由

**Files:**
- Modify: `apps/api/routes/projects.py`（lineage 旁）
- Test: `tests/api/test_resolved_prompt.py`（或并入现有 assets API 测试）

- [ ] `GET /projects/{project_id}/assets/{asset_id}/resolved-prompt`
- [ ] 404 / 400 行为与测试

### Task 3: 前端预览 UI

**Files:**
- Create: `apps/web/src/components/assetDetail/ResolvedPromptPreview.tsx`
- Modify: `AssetDetailSection.tsx`（`actions`）
- Modify: `ImageTextAssetDetailModal.tsx`
- Modify: `asset-detail.css`、i18n zh/en

- [ ] 眼睛按钮 + 弹层 + 复制
- [ ] 按需 fetch API

### Task 4: 文档与验证

- [ ] 更新 product-plan / code-design-plan / spec 状态
- [ ] `pytest tests/ -v`（或至少 unit + 新 API 测试）

---
