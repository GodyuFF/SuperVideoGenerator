# OpenCut Classic → SVF 移植清单

> 基于 opencut-classic Architecture（EditorCore + Managers）与 SVF EditTimeline 适配层。

## 必移植（P0）

| Classic 模块 | SVF 目标路径 | 状态 |
|--------------|--------------|------|
| EditorCore 单例 | `apps/web/src/editor/classic/core/EditorCore.ts` | 已实现 |
| CommandManager（Undo/Redo） | `apps/web/src/editor/classic/core/CommandManager.ts` | 已实现 |
| Timeline UI + 拖拽 | `apps/web/src/editor/classic/timeline/ClassicTimelineView.tsx` | 已实现 |
| 预览 Canvas | `apps/web/src/editor/svf/PreviewPanel.tsx` + Ken Burns | 已回迁 |
| 素材库 | `apps/web/src/editor/classic/media/MediaPanel.tsx` | 已整合 |
| SVF 适配层 | `apps/web/src/editor/adapter/*` | 已实现 |
| Agent 桥 | `apps/web/src/editor/agentBridge.ts` | 已实现 |

## 不移植

- better-auth / Drizzle / PostgreSQL
- Next.js 路由与 Cloudflare 部署
- Classic 导出管线（SVF 使用 FFmpeg `POST .../export`）
- opencut-wasm GPU 预览（P1 可选）

## 数据边界

持久化始终序列化为 SVF `EditTimeline`（`video_layers` + `tracks`），见 `adapter/timelineMapper.ts`。
