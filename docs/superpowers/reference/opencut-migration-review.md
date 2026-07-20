# OpenCut 迁移状态评测

> 更新日期：2026-07-09  
> 路径规范见 [`opencut-integration.md`](opencut-integration.md) §路径与术语规范

## 结论

**OpenCut Classic 已深度融合进 SVF 前端**，无 iframe、无 postMessage、无独立 dev server。运行时源码位于 `apps/web/src/editor/opencut/`（`@opencut` alias）。

## 已完成 ✅

| 组件 | 路径 | 说明 |
|------|------|------|
| Classic 编辑器本体 | `apps/web/src/editor/opencut/` | 600+ 文件，时间轴/预览/特效/蒙版/WASM 渲染 |
| SVF 集成壳层 | `apps/web/src/editor/` | `EditTabSimpleView`、`EditorStudioModal`、`SvfClassicEditor*` |
| 数据适配 | `apps/web/src/editor/adapter/` | `svfProjectAdapter`、`SvfMediaBridge`、`svf-storage-bridge` |
| Agent 桥接 | `classicAgentBridge.ts` | WebSocket 热更新 Classic EditorCore |
| REST API | `apps/api/routes/edit_timeline.py` 等 | PATCH + revision + `metadata.classic_project` |
| Agent 剪辑工具 | `core/llm/tools/editing/opencut_handler.py` | 15 个 editing 工具 |
| 国际化 | `apps/web/src/i18n/locales/{zh-CN,en}/opencut/` | 嵌入层文案；用户可见页标题为「剪辑助手」 |

## 上游参考（不运行）

| 组件 | 路径 | 说明 |
|------|------|------|
| OpenCut Classic 上游 | `opencut-classic/` | 对照移植来源 |

## 已废弃 ❌

- `opencut/`（旧 monorepo）
- `OpenCut-main/`
- `apps/web/src/edit/opencut-bridge.ts`、`opencut-integration.tsx` 等 iframe 方案

## 详细架构

见 [`opencut-integration.md`](opencut-integration.md)、[`edit-studio-plan.md`](edit-studio-plan.md)。
