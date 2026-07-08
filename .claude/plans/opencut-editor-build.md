# OpenCut 编辑器核心 UI 开发计划

## Context

OpenCut 已集成到 SuperVideoGenerator（6 个 commit），集成层架构已完备：
- postMessage 通信桥 (opencut-bridge.ts)
- iframe 宿主组件 (opencut-integration.tsx)
- 编辑会话 REST API (edit_session.py)
- 15 个 Agent 剪辑工具

但 OpenCut 编辑器本体仅有脚手架（TanStack Start + shadcn/ui + "hello world"），无法实际作为嵌入式剪辑器使用。

## 目标

在 opencut/apps/web 中开发完整的编辑器 UI，支持：
1. 多轨时间轴：视频层、音频轨、字幕轨
2. Canvas 预览：实时帧渲染
3. Agent 命令处理：通过 postMessage 接收并执行操作
4. 媒体库面板：浏览和拖放资产
5. 编辑状态管理：Zustand store

## 架构

```
┌─────────────────────────────────────────────────────────┐
│ opencut/apps/web/src/                                   │
│                                                          │
│ editor/              ← 编辑器核心                        │
│   editor-page.tsx    ← 主页面布局                        │
│   host-bridge.ts     ← postMessage 命令处理              │
│   editor-store.ts    ← Zustand 编辑状态                  │
│                                                          │
│ timeline/            ← 时间轴                            │
│   timeline-view.tsx  ← 时间轴容器                        │
│   clip-block.tsx     ← 片段组件                          │
│   track-lane.tsx     ← 轨道行                            │
│   playhead.tsx       ← 播放头                            │
│   ruler.tsx          ← 时间刻度尺                        │
│                                                          │
│ preview/             ← 画布预览                          │
│   preview-canvas.tsx ← Canvas 渲染                      │
│   renderer.ts        ← 渲染管线                          │
│   frame-compositor.ts← 多轨道合成                        │
│                                                          │
│ media/               ← 媒体相关                          │
│   media-panel.tsx    ← 资产浏览器                        │
│   media-item.tsx     ← 资产列表项                        │
│                                                          │
│ commands/            ← Agent 命令                        │
│   execute.ts         ← 命令执行器                        │
│                                                          │
│ routes/              ← 路由                              │
│   editor.tsx         ← /editor 路由                      │
└─────────────────────────────────────────────────────────┘
```

## 实施计划

### Step 1: 编辑器页面骨架
**文件**: `routes/editor.tsx`（新建）
- 编辑器主布局：顶部工具栏 + 左侧预览 + 右侧属性面板 + 底部时间轴
- 使用 react-resizable-panels 实现可缩放面板
- 监听 postMessage 并注册 host-bridge

### Step 2: 状态管理
**文件**: `editor/editor-store.ts`（新建）
- Zustand store：时间轴数据、选中状态、播放头位置
- 导出 actions: addClip, updateClip, removeClip, setPlayhead, setSelected
- 与 host-bridge 的双向同步

### Step 3: 时间轴组件
**文件**: `timeline/`（新建目录,5 个文件）
- 轨道渲染：视频层 + 音频轨 + 字幕轨
- 片段拖拽移动/缩放
- 播放头跟随
- 渲染适配宿主传入的 EditTimelineData

### Step 4: Canvas 预览
**文件**: `preview/`（新建目录,3 个文件）
- Canvas 2D 渲染图片/视频帧
- 多轨道图层合成（z_index + transform）
- 播放时帧同步（requestAnimationFrame）

### Step 5: 媒体面板
**文件**: `media/`（新建目录,2 个文件）
- 从宿主 API 获取媒体资产列表
- 缩略图 + 名称 + 类型展示
- 拖放到时间轴（dragstart → drop on track lane）

### Step 6: Agent 命令集成
**文件**: `commands/execute.ts`（新建）
- 监听 postMessage `apply_action` 命令
- 解析命令类型并调用 editor-store 方法
- 返回操作结果通过 postMessage `timeline_changed` 事件

## 技术约束

1. **无外部后端依赖**：OpenCut 编辑器从宿主的 `/api/projects/{id}/scripts/{sid}/media` 获取资产，通过 postMessage 回传状态变更
2. **纯客户端**：所有编辑操作在本地完成，通过 store → postMessage → 宿主 API 持久化
3. **框架**：TanStack Start + React 19 + Tailwind CSS + shadcn/ui（已配置）
4. **状态管理**：Zustand（需新增依赖）

## 文件清单

### 新建文件 (15个)
| 文件 | 行数估算 | 用途 |
|------|---------|------|
| `src/routes/editor.tsx` | ~80 | 编辑器路由页面 |
| `src/editor/editor-page.tsx` | ~200 | 编辑器主布局 |
| `src/editor/host-bridge.ts` | ~150 | postMessage 命令处理 |
| `src/editor/editor-store.ts` | ~200 | Zustand 状态管理 |
| `src/editor/types.ts` | ~80 | 编辑器类型定义 |
| `src/timeline/timeline-view.tsx` | ~250 | 时间轴容器 |
| `src/timeline/clip-block.tsx` | ~150 | 片段组件 |
| `src/timeline/track-lane.tsx` | ~100 | 轨道行 |
| `src/timeline/playhead.tsx` | ~50 | 播放头 |
| `src/timeline/ruler.tsx` | ~80 | 时间刻度尺 |
| `src/preview/preview-canvas.tsx` | ~150 | Canvas 预览 |
| `src/preview/renderer.ts` | ~100 | 渲染管线 |
| `src/media/media-panel.tsx` | ~120 | 资产面板 |
| `src/media/media-item.tsx` | ~60 | 资产项 |
| `src/commands/execute.ts` | ~100 | Agent 命令执行 |

### 修改文件 (2个)
| 文件 | 改动 |
|------|------|
| `src/routes/__root.tsx` | 添加 /editor 路由注册 |
| `src/styles.css` | 编辑器布局样式 |

### 新增依赖
```json
"zustand": "^5.0.0"
```
