# OpenCut Classic 深度融合架构

> 更新日期：2026-07-12（音效 API + shot 投影往返）

SuperVideoGenerator 以仓库根目录 [opencut-classic/](../opencut-classic/) 为参考，将完整 Classic 编辑器源码 Vite 化移植到 [`apps/web/src/editor/opencut/`](../apps/web/src/editor/opencut/)，经 SVF 适配层对接 FastAPI 与 editing_agent。

## SSOT 与三端一致

- **权威数据**：`EditTimeline.video_layers` + `tracks`（API/store）；预览、Classic 编辑、FFmpeg 导出均读写此结构。
- **`loadFromSvf`**：始终从 API `video_layers` 构建 video/overlay；`metadata.classic_project` 仅按 clip id **merge 装饰**（effects/masks/animations），不覆盖时序/layout。
- **Transform**：`svfTransformBridge.ts` 将归一化 x/y 映射为 OpenCut 像素偏移 `(x-0.5)*canvas`。
- **运镜**：`svfMotionBridge.ts` 端口化 `core/edit/transform_interp.interpolate_transform`，生成 OpenCut 动画通道。
- **排序**：主层 `z_index=0` clip 按 `video_plan_shot_order` 排序（`svfClipOrder.ts`，与 `compose.py` 一致）。
- **Tab 保存**：`OpenCutPreviewPane` 注册 `saveTimeline` PATCH；导出前 `getClassicBridgeTimeline()` flushSave。

## 路径与术语规范

文档与代码评审中引用 OpenCut 时，**必须使用下表路径**，避免混用已删除目录或含糊简称。

| 术语 | 标准路径 | 运行时 | 说明 |
|------|----------|--------|------|
| **OpenCut Classic 运行时** | `apps/web/src/editor/opencut/` | ✅ | Vite alias `@opencut` 指向此处；用户可见产品名称为「剪辑助手」 |
| **SVF 集成壳层** | `apps/web/src/editor/`（不含 `opencut/` 子目录） | ✅ | 入口、弹窗、适配器、Agent 桥接、Tab 预览 |
| **上游参考源码** | `opencut-classic/` | ❌ | 仅对照/同步，不参与 SVF 前端构建 |
| **WASM 包** | npm `opencut-wasm` | ✅ | 预览与 Classic 渲染共用 |
| ~~旧 iframe 集成~~ | ~~`opencut/`~~、~~`OpenCut-main/`~~ | ❌ 已删除 | 勿在文档中作为有效路径引用 |

**用户界面命名**：剪辑 Tab、弹窗顶栏对外展示 **「剪辑助手」**（en: *Edit Assistant*），不在用户可见文案中暴露 OpenCut 品牌。

## 国际化（i18n）

OpenCut 嵌入层通过 `useOpencutT()`（`apps/web/src/editor/opencut/i18n/useOpencutT.ts`）接入 `opencutTimeline` / `opencutAssets` / `opencutDialogs` / `opencutProperties` 等命名空间；文案位于 `apps/web/src/i18n/locales/{zh-CN,en}/opencut/*.json`。P1 已覆盖时间轴右键菜单、轨道菜单、预览右键、场景/书签、素材面板、蒙版/特效 Tab、引导与加载文案。

## 架构

```
BoardPanel (edit tab)
  └── EditTabSimpleView（左上角「剪辑助手」+ WASM 预览 + 播放 + 导出 +「剪辑修改」打开弹窗）
        ├── OpenCutPreviewPane（仅 PreviewPanel；studioOpen 时 paused，与弹窗互斥 EditorCore）
        │  mount 时 prefetchClassicStudio() 预热 chunk + WASM
        ├── EditorStudioModal（全屏弹窗）
        └── EditorStudioPage（哈希 #/project/.../script/.../edit 独立全屏页）
              └── EditorStudioContent → SvfClassicEditor
                    ├── SvfClassicEditorShell（SvfEditorHeader + 四区布局 + Onboarding）
                    ├── svf-storage-bridge + SvfMediaBridge → PATCH edit-timeline + 媒体注入
                    ├── classicAgentBridge → OpenCut EditorCore 热更新
                    └── opencut-wasm 预览

FastAPI edit-timeline REST ←→ useEditTimeline (PATCH + revision + metadata.classic_project)
editing_agent tools → opencut_handler → patch_timeline → store
双导出：全屏工作室外层 SVF chrome 提供 FFmpeg 导出；`chromeMode=standalone` 时内层 `SvfEditorHeader` 隐藏浏览器导出/完成按钮，避免双层顶栏重复。
```

## 嵌入约束（SVF 弹窗 / 独立页）

- **真全屏布局**：`EditorStudioModal` 与 `EditorStudioPage` 使用 `100dvh` 高度链，overlay 无 padding，Classic 根容器无圆角边框（`editor-studio-modal-shell` / `editor-studio-page-shell`）。
- **TooltipProvider**：`SvfClassicEditorShell` 必须包裹 `TooltipProvider`（与 OpenCut 根 layout 一致），否则素材 Tab 等 `Tooltip` 组件会白屏崩溃。
- **FrameRate**：`svfProjectAdapter.normalizeClassicSettings()` 将 legacy 数字 `fps: 30` 转为 `{ numerator: 30, denominator: 1 }`；OpenCut wasm 不接受浮点 fps。
- **错误边界**：`ClassicEditorErrorBoundary` 包裹 `EditorProvider`，渲染失败时显示重试 UI。
- **保存 debounce**：`svf-storage-bridge` 对 Classic `saveProject` 300ms 合并 PATCH，并同步 `revision` 到 bridge 缓存；保存期间 `SaveManager.pause()`，避免与 Classic autosave 重入。
- **更新风暴防护**：SVF 项目跳过 `loadProject` 缩略图生成；`ProjectManager.setTimelineViewState` 在视图状态未变时不 `notify`；`useEditor` 对 `canvasSize`/`fps` 等浅对象做等价比较。
- **场景初始化顺序**：`loadProject` 先 `initializeScenes` 再 `notify`，预览层 `RenderTreeController` 使用 `getActiveSceneOrNull()`，避免加载窗口期抛出 `No active scene`。
- **原子 loadProject**：`loadProjectInternal` 不再在加载前 `clearScenes()`；失败回滚时才清空。每次加载设 `isLoading=true`，`EditorProvider` 订阅 `project.getIsLoading()` 热重载期间遮挡 UI。
- **Tab/Modal EditorCore 互斥**：`OpenCutPreviewPane.paused`（`studioOpen`）时卸载预览子树并 `unregisterClassicAgentSession`；弹窗关闭后 `reloadClassicFromApi` 恢复 Tab 预览。
- **路由 shim 稳定引用**：`opencut/shims/next-navigation.ts` 的 `useRouter()` 返回单例对象；若每次 render 新建 router，`EditorProvider` 的 `loadProject` effect 会在 `notify()` 后反复重跑，独立页会卡在「加载时间轴与素材…」。
- **字体非阻塞**：`loadProject` 内 Google Fonts 预加载改为 `void loadFonts()`；`google-fonts.ts` 对 CSS 与 `document.fonts.load` 设 4s 超时，避免弱网永久 pending。
- **SVF 主题桥接**：`opencut/svf-opencut-theme.css` 映射 `--svf-*` 设计令牌，时间轴 clip 统一灰底 + 左侧细色条；压制 OpenCut 高饱和蓝青与 Tailwind 硬编码色；主操作色对齐 `--svf-accent`（珊瑚红）。
- **SVF 媒体可见性**：`SvfMediaBridge` 将剧本媒体标记为 `ephemeral: false`，避免 Classic Assets 面板过滤掉已注入媒体。
- **媒体 URL 解析**：API 返回 `url`（相对 data 路径）与 `link`（`/api/...` 可播放路径）；`resolveUrl()` **优先 `link`**，并经 `resolveMediaPlayUrl()` 规范化后写入 Classic 资产，供 `fetch` 水合。
- **媒体水合**：`hydrateSvfMediaFiles(assets, { projectId, scriptId })` 在 bridge 安装时 `fetch` → `File`，供 `videoCache` / WASM 解码；失败标记 `hydrationFailed`，`getVideoHydrationState()` 驱动 `MediaHydrationBanner`；`scene-builder` 拒绝 `file.size === 0`。
- **媒体时长**：`build_media_item` 输出 `duration_ms`（metadata 与本地探测偏差 >5% 时以探测为准）；`SvfMediaBridge` 水合后对 File 调用 `probeMediaDuration` 写入 `asset.duration`；`mergeHydratedDurationsIntoMediaItems` 在 `installSvfStorageBridge` 首载时把水合时长回灌 `loadFromSvf` lookup（与 `reloadClassicFromApi` 一致）。
- **clip trim 语义**：`clipToElement` 对 audio/video 设 `trimEnd=0`（全长 clip）或 `trimEnd=sourceDuration-visible`；`resolveSourceDurationMs` 优先读水合缓存；非 `user_locked` 的 audio 在源长于 clip 时防御性扩展可见时长至源全长，避免时间轴半宽。
- **无波形提示**：音频 clip 水合失败时时间轴显示 `audioClipHydrationMissing` 警告文案。
- **mediaId 重映射**：`loadFromSvf` 对快照场景重写 `mediaId`；`inferClipMediaType` 按媒体类型推断 element type；`reconcileElementMediaType` 避免 classic 装饰把 video 锁成 image。
- **shot 投影往返**（2026-07-12）：`svfShotProjection.ts` + `clipToElement`/`elementToClip` 保留 `source_refs.shot_id`/`video_plan_shot_order` 与 `metadata.shot_offset_ms`/`shot_track_id` 等投影键；PATCH 后 `patch_timeline` 调用 `apply_timeline_edits_to_shots` 回写 VideoPlan；主层 ID 统一为 `vly_z0`。
- **Agent 热更新**：`edit_timeline_updated` → `fetchTimeline` + `reloadClassicFromApi` + `buildTimelineFingerprint` 强制 bridge reload。
- **时间轴 clip 显示**：text/audio clip 背景层铺满 `inset-0` 容器（`w-full` + `h-full`），取消 `CLIP_VISUAL_GAP` 与 ring 内缩，默认态即完整占据时间范围与轨道高度。
- **双层 chrome**：外层 SVF chrome 提供 NLE 工程导出与完成/关闭；内层 `SvfEditorHeader` 始终显示 OpenCut **浏览器「导出」**（成片 MP4/WebM）。
- **剪辑 Tab 布局**：`edit-cinema` flex 高度链 + 状态栏位于预览下方；Tab 内嵌预览隐藏 OpenCut 底部工具栏，避免与顶栏播放控件重复。

## 目录

| 路径 | 职责 |
|------|------|
| `apps/web/src/editor/EditTabSimpleView.tsx` | 剪辑 Tab + WASM 预览 + 预加载 +「剪辑修改」打开弹窗 |
| `apps/web/src/editor/OpenCutPreviewPane.tsx` | Tab 轻量 OpenCut WASM 预览（与弹窗共享 EditorCore） |
| `apps/web/src/editor/EditorStudioModal.tsx` | 专业剪辑弹窗 |
| `apps/web/src/editor/EditorStudioContent.tsx` | 弹窗与独立页共用核心 UI |
| `apps/web/src/pages/EditorStudioPage.tsx` | 哈希路由独立剪辑全屏页 |
| `apps/web/src/editor/editorStudioUrls.ts` | 独立页 URL 构建与新窗口打开 |
| `apps/web/src/editor/classicPrefetch.ts` | Classic chunk / WASM 预热 |
| `apps/web/src/editor/classicAgentBridge.ts` | Classic 弹窗 Agent 会话与热更新 |
| `apps/web/src/editor/opencut/SvfClassicEditor.tsx` | Classic 入口 + 分阶段 loading |
| `apps/web/src/editor/opencut/SvfClassicEditorShell.tsx` | 完整顶栏 + 四区布局 |
| `apps/web/src/editor/opencut/SvfEditorHeader.tsx` | SVF 定制 EditorHeader（`chromeMode` 控制导出/完成可见性） |
| `apps/web/src/editor/opencut/` | 移植的 OpenCut Classic 源码（609+ 文件） |
| `apps/web/src/editor/adapter/svfShotProjection.ts` | 镜内多轨投影 metadata 往返（shot_offset_ms / source_refs） |
| `apps/web/src/editor/adapter/svfProjectAdapter.ts` | EditTimeline ↔ TProject 双向映射（SSOT + classic 装饰） |
| `apps/web/src/editor/adapter/svfTransformBridge.ts` | 归一化 transform ↔ OpenCut 像素 params |
| `apps/web/src/editor/adapter/svfMotionBridge.ts` | 运镜/关键帧插值 → OpenCut animations |
| `apps/web/src/editor/adapter/svfClipOrder.ts` | 主层 clip 导出排序键 |
| `apps/web/src/editor/adapter/SvfMediaBridge.ts` | SVF 媒体 → Classic MediaAsset |
| `apps/web/src/editor/adapter/probeMediaDuration.ts` | 浏览器端 File 时长探测 |
| `apps/web/src/editor/adapter/svfTrimFields.ts` | clip trim/sourceDuration 计算 |
| `apps/web/src/edit/` | snake_case 类型 + `useEditTimeline` hook |
| `opencut-classic/` | 上游参考源码 |

## 数据边界

持久化始终使用 SVF `EditTimeline`（`video_layers` + `tracks` + `metadata.classic_project`）。Classic 运行时通过 `svf-storage-bridge` 拦截 `storageService.saveProject/loadAllMediaAssets`，经 `saveToSvf()` 写回 PATCH API。

无法 1:1 映射的 Classic 字段（effects、masks、scenes 等）存入 `clip.metadata.classic` 与 `timeline.metadata.classic_project`。`source_refs` 与 `metadata.shot_offset_ms` 等在 SVF ↔ Classic 往返中保留，供 `apply_timeline_edits_to_shots` 回写镜内 Shot。

## 加载优化

- 剪辑 Tab mount / hover「剪辑修改」时预加载 `SvfClassicEditor` chunk 与 `opencut-wasm`
- Vite `manualChunks`：`opencut-core` / `opencut-wasm` / `transformers`（字幕 Tab 懒加载）
- **SVF 本地项目版本**：`CURRENT_PROJECT_VERSION = 31`（[`constants.ts`](../apps/web/src/editor/opencut/services/storage/constants.ts)）；不再运行 v0→v31 storage migrations，旧 OPFS 项目需清空站点数据后重建
- Modal 传入 `initialTimeline` 避免重复 GET

## Agent 工具

15 个 editing 工具见 `core/llm/tools/editing/opencut_handler.py`。WebSocket `edit_timeline_updated` 经 `agentBridge.reloadFromApi` → `classicAgentBridge.reloadClassicFromApi` 驱动 Classic EditorCore。

## 音效素材（2026-07-12）

剪辑助手左侧 **「音效」** Tab 经 SVF API 检索免费短音效并加入时间轴：

| 能力 | 说明 |
|------|------|
| 内置目录 | [`core/sounds/builtin_catalog.py`](../core/sounds/builtin_catalog.py)：12 条 Mixkit 可商用短音效，**无需 API Key** |
| 在线搜索 | 环境变量 `FREESOUND_API_KEY` → [Freesound API v2](https://freesound.org/docs/api/overview.html) |
| 商用筛选 | `commercial_only=true`（默认）仅 CC0 / Attribution |
| 预览代理 | `GET /api/sounds/preview/{id}` 绕过 CORS，供试听与时间轴 fetch |

- `GET /api/sounds/search?q=&page=&page_size=&commercial_only=&sort=downloads`
- `GET /api/sounds/preview/{sound_id}`（正 ID=Freesound，负 ID=内置）

Key 申请：<https://freesound.org/apiv2/apply>

## 开发启动

```bat
dev.bat        # Windows：API + 前端（先轮询 /health 再启前端，最多 60s）
dev.bat --web  # 仅前端 http://localhost:5173
```

前端构建：`npm run build`（Vite + opencut-wasm）；类型检查：`npm run typecheck`（排除 opencut 子树，集成层文件不直接 typecheck opencut 内部）。
