# Edit Studio 规格说明

> 更新日期：2026-07-14（WhisperX 字幕强制对齐；EditTimeline 可视化调试页 + 字幕样式按分辨率推荐）

## EditTimeline 可视化调试页

独立于 Workbench / OpenCut / 看板 Tab 的**只读**调试页，用于查看某剧本 `EditTimeline` 全貌、校验与分析结果。

| 项 | 说明 |
|----|------|
| 路由 | `#/viz/edit-timeline?project={project_id}&script={script_id}`（hash 内 query，可书签/分享） |
| 入口 | 项目首页顶栏「EditTimeline 可视化」；加载成功后 URL 同步 query |
| 前端 | [`apps/web/src/pages/EditTimelineVizPage.tsx`](../apps/web/src/pages/EditTimelineVizPage.tsx) + [`apps/web/src/pages/editTimelineViz/`](../apps/web/src/pages/editTimelineViz/) |
| 数据 | 并行调用现有 API：`GET edit-timeline`、`POST validate`、`POST analyze`（默认 `include_analysis: true`） |
| 交互 | 只读 + 刷新；可选 `start_ms` / `end_ms` 后点「重新分析」；**无** PATCH / FFmpeg / NLE 导出 |

**与 Edit Studio 关系：**

- SSOT 仍为 store/API 的 `EditTimeline`（见上文 SSOT 表）；本页不写入、不投影 OpenCut。
- 看板 [`EditTimelineBoard`](../apps/web/src/components/board/EditTimelineBoard.tsx) 将 `video_layers` 拍平为单 video 轨；本页按 **`video_layers[]` 分层**展示，并保留 audio/subtitle 轨。
- 剪辑 Tab / Classic 弹窗的编辑与导出能力不在本页范围内。

## 目标

将只读剪辑看板升级为 **可预览、可拖拽、可写回** 的多轨剪辑工作室；**成片导出默认且唯一走 OpenCut 剪辑助手浏览器导出**；服务端 FFmpeg 合成默认关闭（`SVG_EXPORT_ENABLED=1` 可恢复遗留路径）；专业弹窗内另可选 **Premiere 工程包（NLE）** 导出；`editing_agent` 在用户已编辑时间轴上采用 **merge** 策略。视频采用 **多条视频图层轨**（`video_layers[]`），支持画中画叠加与画布变换/关键帧。

## 单一真相源（SSOT）

**`EditTimeline`（API/store 的 `video_layers` + `tracks.audio/subtitle`）** 是剪辑素材与时间轴的唯一权威：

| 路径 | 读 | 写 |
|------|----|----|
| editing_agent | `get_edit_timeline` / `load_edit_context` | `plan_edit_timeline` → `patch_timeline` |
| 剪辑 Tab 预览 | `loadFromSvf` 只读投影 | Tab `saveTimeline` → PATCH（经 bridge） |
| Classic 编辑 | bridge 缓存 | `saveToSvf` → PATCH |
| FFmpeg 导出（遗留） | store `EditTimeline` | 写 `FINAL` MediaAsset（需 `SVG_EXPORT_ENABLED=1`） |
| Classic 浏览器导出 | OpenCut EditorCore | 用户本机下载 MP4/WebM |
| NLE 工程导出 | store `EditTimeline` | 写 exports/nle_premiere_*.zip |

`metadata.classic_project` **仅存 per-clip 装饰**（effects/masks/animations）；**不得**覆盖 API `video_layers` 的 clip 时序与 layout。预览 transform/运镜与 FFmpeg 共用 `interpolate_transform` 语义（前端 `svfMotionBridge.ts` 端口化）。

## 架构

```
剧本页剪辑 Tab (EditTabSimpleView)  — OpenCut WASM 预览/播放 + Tab 内浏览器导出 + 预加载 Classic 弹窗
  └── OpenCutPreviewPane（仅 PreviewPanel，与弹窗共享 EditorCore；studioOpen 时暂停）
  └── EditorStudioModal — 剪辑助手弹窗（完整 Classic 编辑器，`apps/web/src/editor/opencut/`）
        └── SvfClassicEditor + SvfClassicEditorShell
              ├── SvfEditorHeader（浏览器「导出」/ 快捷键 / 撤销）
              ├── Assets / Preview / Properties / Timeline（完整 Classic）
              └── svf-storage-bridge + SvfMediaBridge

用户 UI  ←PATCH→  timeline_service  →  EditTimeline (store + metadata.classic_project 装饰快照)
editing_agent plan_edit_timeline (mode=merge)  ────────────────┘
Classic ExportButton  →  浏览器渲染 MP4/WebM（默认唯一成片路径）
POST export（遗留 FFmpeg，默认 403）→  ffmpeg_renderer  →  exports/*.mp4
POST export-nle  →  nle_export  →  exports/nle_premiere_*.zip
预览/编辑：loadFromSvf 始终从 API video_layers 构建；`msToTicks`/`ticksToMs` 与 OpenCut wasm `TICKS_PER_SECOND`（120000）对齐，禁止沿用旧版 48000 常量；`project.metadata.duration` 取场景轨元素实际终点（非膨胀的 `timeline.duration_ms`）；`edited_by=user` 的 clip 仅在 Classic 快照与 API `start_ms/end_ms` 一致时恢复布局；音频槽位长于浏览器探测时长时不压短 `sourceDuration`（mergeHydrated 与 hydrate 双路径）；打开专业剪辑/预览时从 API 重建 bridge 并清除陈旧 IndexedDB 工程快照，**但保留已水合媒体 File blob**（避免每次打开重复下载）；409 时自动 refetch 后重试
运镜：svfMotionBridge 与 core/edit/transform_interp.py 对齐；主层 clip 排序与 compose 一致
```

## API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/edit/capabilities` | 运镜/转场/背景枚举 + `ffmpeg_available` / `export_enabled` / `nle_export_enabled` / `max_video_layers` |
| GET | `/api/projects/{pid}/scripts/{sid}/edit-timeline` | 时间轴 + `video_layers` + revision + 每 clip `preview_url`；未生成时返回空结构（200） |
| PATCH | 同上，`If-Match: revision` | 用户写回（`video_layers`、`tracks`、`duration_ms`、`metadata`）；服务端同步 `apply_timeline_edits_to_shots` 回写 VideoPlan；保存时 `duration_ms` 与轨 clip 对齐，**成片有效时长以视频层终点为准** |
| POST | `.../edit-timeline/validate` | 素材与软校验；无时间轴时返回 `ready: false`（200） |
| POST | `.../edit-timeline/analyze` | 按 `start_ms`/`end_ms` 读取区间内 clip 详情（`edit_description`/运镜/transform/`resolved`）及可选结构分析（gaps/overlaps/hints/alignment）；`include_analysis=false` 仅返回 clip 详情；无时间轴时返回空分析 + warning（200） |
| POST | `.../export` | 异步 FFmpeg 导出（**默认 403**；仅 `SVG_EXPORT_ENABLED=1` 时可用） |
| GET | `.../export/{job_id}` | 导出进度 |
| POST | `.../export-nle` | 异步 Premiere Pro 工程包导出（FCP7 XMEML ZIP） |
| GET | `.../export-nle/{job_id}` | NLE 工程导出进度 |

## 数据模型

### video_layers（P0）

| 实体 | 字段 | 说明 |
|------|------|------|
| `EditVideoLayer` | `id`, `name`, `z_index`, `clips[]` | 每层独立 clip 列表；`z_index` 越大越靠上 |
| `EditClip` | `transform`, `layer_id` | 画布变换与所属层 |
| `EditClipTransform` | `x`, `y`, `width`, `height`, `opacity`, `rotation`, `keyframes[]` | 归一化 0–1；中心点语义 |
| `EditClipKeyframe` | `time_ms` + 可选属性 | 相对 clip 起点插值 |

**单源**：视频 clip 仅存于 `video_layers[]`；`tracks` 仅含 `audio` / `subtitle`。Agent 若仍传 `tracks.video`，在 `merge_timeline_with_fallback` 入口经 `extract_agent_video_clips` 一次性转为 `video_layers`，不做双写。

**校验**：`validate_timeline_clips` 同层内重叠 warning；跨层允许同时间段并存。默认最多 **5** 层（`MAX_VIDEO_LAYERS`）。

### 其他字段

`EditTimeline` 扩展：`revision`、`user_edited`、`last_edited_by`、`updated_at`、`metadata`（含 `classic_project` Classic 场景/特效快照）。

`EditClip.metadata` 约定：`edited_by`、`user_locked`（merge 时保护）、`classic`（Classic 元素扩展字段）。

能力单源：[`core/edit/capabilities.json`](../core/edit/capabilities.json)。

### 运镜归一化

LLM/分镜可能写入创意运镜名（如 `gentle_push_in`）。入库（`_parse_clip_from_raw`）、Agent merge（`finalize_merged_timeline`）与 FFmpeg 导出前会调用 `resolve_motion`：先查 `motion_aliases`，未知值回落为 `ken_burns_in`。`edit_capability_issues` 在校验前亦经归一化，不再因别名阻断导出。

### 导出前 audio / subtitle enrich

`plan_edit_timeline` 若仅写 video 轨会清空 audio。导出与 merge 完成前：

- `enrich_timeline_audio_from_store`：按 VideoPlan + Store TTS 补齐 `tracks.audio`
- `enrich_subtitles_from_audio`：新模型下为 no-op（字幕由镜内 `Shot.subtitles` 投影）
- `build_cues_for_audio_media`（[`subtitle_align.py`](../core/edit/subtitle_align.py)）：生成/补齐 audio `metadata.subtitle_cues` 优先级为 **TTS 持久化 cues → WhisperX 强制对齐（仅 CUDA，[`whisperx_align.py`](../core/edit/whisperx_align.py)）→ 标点 + 时长比例 fallback**；配置 `SVG_WHISPERX_LANGUAGE` / `SVG_WHISPERX_ALIGN_MODEL`
- 句级字幕 / cue 另含可选字段 `character`、`color`（默认空），投影进 EditClip `metadata` 供后续按发言人着色；分镜子镜挂接仅 `frame`/`video_clip`，角色概念在配音幕，见 [`product-plan.md`](product-plan.md)「分镜挂接与角色边界」

不覆盖 `user_locked` 或 `edited_by=user` 的 clip。对非受保护 clip，若 Agent 已写入 `asset_ref` 但时序错误或缺 `shot_id`，`enrich_timeline_audio_from_store` 会按 `compile_timeline_from_shots` 参考轨重算 `start_ms`/`end_ms` 并补全 `metadata.shot_id`。

`finalize_merged_timeline` 在对齐音频后：

1. `sync_audio_clip_durations_to_media`：audio clip 短于素材时延长 `end_ms`；**仅** `sync_policy=visual_master` 时仍钳制到同镜视频终点；`narration_master` / `balanced` 以配音为准。
2. `_extend_video_clips_for_narration_master`：配音长于视频时扩展视频终点，并写入 `freeze_tail_ms`（若尚无 rate）。
3. 分析 API 另输出 `video_shorter_than_audio` hint 与 `proposed_fixes`。

真视频导出支持 `metadata.playback_rate`（`setpts`）与 `freeze_tail_ms`（`tpad`）；详见 [av-sync-plan.md](av-sync-plan.md)。

TTS 落盘时 `persist_single_synthesized_audio` 写入 `used_planned_timeline`（规划合成路径）与探测后的全长 `duration_ms`。

### TTS 同步与时间轴重排

TTS 实测经 `sync_plan_from_tts` 绑定到镜内 `audio_tracks` voice clip、更新 `duration_ms` 与 `subtitles`，并重投影 `EditTimeline`（`user_edited=true` 时跳过）。

| 环节 | 行为 |
|------|------|
| `sync_plan_from_tts` | 绑定 TTS media、对齐镜时长、回填字幕；`realign_edit_timeline_from_plan`（`user_edited` 时跳过）；返回 `probe_failures[]` |
| `compile_timeline_from_shots` | Shot 镜内多轨 → EditTimeline 唯一投影路径（[`shot_flatten.py`](../core/edit/shot_flatten.py)） |
| `apply_timeline_edits_to_shots` | OpenCut 手改回写 Shot；配音 clip 若 label 为 clip id / `sac_` 占位且 `asset_ref` 为空，**保留**镜内已有 `text` 与 `media_id`（防 OpenCut 清空 TTS） |
| `clipToElement`（audio） | `name` 不用 clip id 占位，缺 label 时显示「配音」，避免回写时覆盖旁白文案 |

`compose_timeline_plan` 导出前对主画面层（`z_index=0`）clips 按 `video_plan_shot_order` / `start_ms` 排序，避免 Agent 写入顺序与播放顺序不一致。

### 画布缩放导出

- `transform.width/height`：预览与 FFmpeg 导出一致（composite 或 `_render_clip_with_transform`）
- Ken Burns：`motion != static` 触发 composite；边界每 250ms 采样（[`ken_burns_filter.py`](../core/edit/ken_burns_filter.py)）；导出时 `transform_to_overlay_pixels` 将 pad 目标规范为偶数，`scale` 滤镜带 `force_divisible_by=2`；`motion=static` 不应用 `motion_detail` 缩放
- storybook 模式默认走 `composite_slices` 导出

## 预览 URL 解析

`timeline_board_items`（[`core/edit/timeline.py`](../core/edit/timeline.py)）对 `video_layers` 每层 clip 调用 [`resolve_clip_media`](../core/edit/asset_resolver.py)，写入：

| 字段 | 说明 |
|------|------|
| `preview_url` | `resolve_media_access` 的 `link`（优先 `/api/projects/.../media/...`） |
| `preview_media_type` | `image` / `video` / `audio` |

镜头关联优先级（与导出一致）：

1. `clip.asset_ref`
2. `source_refs.media_ids` / `text_asset_ids` + `variant_ids`
3. `source_refs.shot_id` 或 `metadata.shot_id`（真实 plan shot ID）
4. **`source_refs.video_plan_shot_order`**：按 0-based `order` 匹配 VideoPlan 镜头

前端 [`OpenCutPreviewPane`](../apps/web/src/editor/OpenCutPreviewPane.tsx) 与 Classic [`PreviewPanel`](../apps/web/src/editor/opencut/preview/components/index.tsx) 共用 `buildScene` + opencut-wasm 渲染。数据链路：

1. `installSvfStorageBridge` 拉取 `/media` + `edit-timeline`
2. `hydrateSvfMediaFiles` 将 URL 水合为可解码 `File`（视频预览必需）；Electron 桌面壳下优先 IPC 读 `data/` 本地文件，失败再回退 HTTP
3. `loadFromSvf` 构建 Classic project（快照场景会重映射 `mediaId`）
4. `EditorProvider.loadProject` → `media.loadProjectMedia` + `initializeScenes`
5. `RenderTreeController` 调用 `buildScene`（要求 `mediaMap` 命中且 `file`+`url` 齐全）

`timeline.revision` / `updated_at` 变化时 Tab 预览会 `force` 刷新 bridge 并重载 `EditorProvider`。

### 预览音频

TTS 配音位于 `tracks.audio`，经 [`clipToElement`](../apps/web/src/editor/adapter/svfProjectAdapter.ts) 映射为 Classic `type: "audio"` 元素。OpenCut [`collectAudioClips`](../apps/web/src/editor/opencut/media/audio.ts) 对 upload 源要求 `sourceType: "upload"` 才会使用 `hydrateSvfMediaFiles` 水合后的 `mediaAsset.file` 解码；SVF 适配器在 `clipToElement` 末尾通过 `ensureUploadAudioSourceType` 自愈该字段。

音频播放链路：Tab 预览（`OpenCutPreviewPane`）与专业剪辑弹窗（`SvfClassicEditor`）共用 `svfProjectAdapter` + `AudioManager`。若 `mediaId` 未匹配或音频水合失败（`file.size === 0`），`collectAudioClips` 为空 → 全页无声；`SvfMediaBridge.getMediaHydrationIssues` 会在预览层展示视频/音频水合失败提示（醒目 `role=alert` 条）。水合未完成或失败时，预览播放与浏览器导出（含音频）会被禁用并给出 toast/内联错误，禁止静默无声成片。

### 浏览器导出（Classic）

成片 MP4/WebM 默认经 OpenCut `RendererManager` 在本机混音导出：

| 环节 | 行为 |
|------|------|
| Popover 层级 | 全屏剪辑弹窗 overlay `z-index: 10000`；`ExportButton` / 顶栏 `DropdownMenu` 的 Radix Portal 须 `z-index: 10001+`（`svf-editor-overlay-content`） |
| 含音频导出 | `includeAudio=true` 时若时间轴无音频轨、媒体未水合或 `createTimelineAudioBuffer` 失败，返回 `success: false` 与明确 `error`，不静默跳过音轨 |
| PR 工程导出 | `EditorStudioContent` 以 sonner toast 反馈成功/失败/取消保存；导出中按钮禁用并显示 loading toast |

`clipToElement` 对 `type: audio` 不挂载视频运镜 `animations`，并显式设置 `params.volume=1`。

### 时间轴展示

专业剪辑弹窗底部时间轴（`opencut/timeline/components`）针对 SVF 字幕密集场景做了 UI 层优化（不改 clip `duration` / 播放语义）：

1. **分级展示**（`clip-display.ts`）：按像素宽度分 `bar`（<14px，仅色条 + hover title）、`compact`（<40px，序号/省略号）、`full`（完整 truncate 标签）
2. **视觉缝隙**：相邻 clip 容器宽度减 1px，保留真实 `left`，避免色块粘成一片
3. **分轨配色**（`svf-opencut-theme.css` + `theme.ts`）：画面珊瑚、字幕青绿、音频蓝调半透明填充 + 左色条 + 右帧线分隔
4. **轨道尺寸**：字幕轨高度 32px、轨间距 8px
5. **智能初始 zoom**（`getSubtitleAwareInitialZoom`）：无已保存视图时，按字幕平均时长抬高 zoom（上限 2×），使窄 cue 更易辨认
6. **选中态**：内描边（`svf-timeline-clip--selected`）+ 透明 resize 手柄；极窄 `bar` 档不显示裁切手柄，避免遮挡

## Agent merge 规则

| 场景 | 行为 |
|------|------|
| 无 existing | create 全量 |
| user_edited=false | replace 可全量 |
| user_edited=true + mode=merge | 保留 user/locked clip 与层，追加 Agent 新 clip |
| mode=replace | 全量替换 |

`plan_edit_timeline` 输出 `video_layers[]`；主画面 `z_index=0`，画中画/贴纸放更高层并写明 `transform`。Agent 协议边界仍可在 `tracks.video` 传扁平 clip，入库时归一化为 `video_layers[0]`。

## 前端模块

> 更新日期：2026-07-09 — OpenCut Classic 完整弹窗，无 EditStudio 回退。

| 模块 | 职责 |
|------|------|
| `EditorStudioContent.tsx` | 专业剪辑单层顶栏：导出 Portal + 完成 + 更多（NLE/新标签/快捷键/取消） |
| `svfAnimationBridge.ts` | OpenCut `animations` ↔ SVF `transform.keyframes` 保存回写 |
| `svfProjectAdapter.ts` | `elementToClip` 从 `animations` 提取关键帧；快照优先 `classic.animations` |
| `EditTabSimpleView.tsx` | 剪辑 Tab：时码+播放 | 重新加载+导出+剪辑修改 |
| `OpenCutPreviewPane.tsx` | Tab 轻量 OpenCut WASM 预览（`paused` 与弹窗互斥 EditorCore） |
| `EditorStudioModal.tsx` | 弹窗 + FFmpeg 导出 |
| `opencut/SvfClassicEditor.tsx` | Classic 入口 + bridge 安装 |
| `opencut/SvfClassicEditorShell.tsx` | 顶栏 + 四区布局 |
| `adapter/svfProjectAdapter.ts` | EditTimeline ↔ TProject + classic_project |
| `adapter/SvfMediaBridge.ts` | SVF 媒体 → Classic MediaAsset |
| `classicAgentBridge.ts` | Agent 驱动 Classic EditorCore |
| `edit/useEditTimeline.ts` | PATCH 保存、revision、metadata |
| `agentBridge.ts` | WebSocket 热更新路由 |

## 预览音轨同步

剪辑 Tab 与 Classic 弹窗播放时，由 OpenCut `AudioManager` + 预览渲染管线同步 `tracks.audio` 与画面/字幕；与 FFmpeg 导出使用同一 `buildScene` 合成逻辑。

## FFmpeg 映射

| 场景 | 实现 |
|------|------|
| 单层 / 无叠加 | 串行 segment + concat |
| 多层同时段 | `composite_slices` + `overlay` 滤镜链（[`ffmpeg_renderer.py`](../core/edit/ffmpeg_renderer.py) `_render_composite_slice`） |
| transform | `transform_to_overlay_pixels` + `build_scaled_video_filter`；非全屏简单路径走 `_render_clip_with_transform` |
| 关键帧 / Ken Burns | `collect_timeline_boundaries`（含 250ms Ken Burns 采样）；storybook 默认 composite_slices |
| 素材校验 | 导出前 `validate_edit_timeline`；缺图/配音时拒绝导出 |
| audio 轨 | adelay + amix |
| 字幕 | 预览/OpenCut 文本轨使用 [`subtitle_style.py`](../core/edit/subtitle_style.py) 推荐底中字号；遗留 FFmpeg ASS 烧录（[`subtitle_burn.py`](../core/edit/subtitle_burn.py)）同公式；`load_edit_context.subtitle_style_context` 供 editing_agent 规划 |

## FFmpeg 安装与配置

默认 **`pip install -e .` 已包含内置 FFmpeg**（[`imageio-ffmpeg`](https://pypi.org/project/imageio-ffmpeg/) 随 wheel 分发），**无需单独安装**即可导出成片。

| 方式 | 说明 |
|------|------|
| **内置（默认）** | `pip install -e .` 后自动使用 imageio-ffmpeg 捆绑的 `ffmpeg.exe` |
| PATH | 系统已安装 FFmpeg 时优先使用 PATH 中的版本 |
| `SVG_FFMPEG_PATH` | 显式指定 `ffmpeg.exe` 完整路径 |
| `SVG_SUBTITLE_FONT` | 字幕烧录用字体文件完整路径（默认 Windows 微软雅黑等系统字体） |
| Windows 手动 | `winget install ffmpeg`（仅在内置包不可用时） |
| `SVG_EXPORT_ENABLED=0` | 禁用导出 |

`GET /api/edit/capabilities` 返回 `ffmpeg_available`、`ffmpeg_bundled`、`ffmpeg_path`、`max_video_layers`。仅当内置与系统均未找到 FFmpeg 时，Edit Studio 才禁用导出并提示安装。

## 成片导出

**FFmpeg 为唯一成片路径**（`compose_final` → `ffmpeg_renderer`）。能力单源：[`core/edit/capabilities.json`](../core/edit/capabilities.json) + [`core/edit/edit_capabilities.py`](../core/edit/edit_capabilities.py)。Remotion 栈已移除。

导出完成后前端 [`apps/web/src/utils/exportDownload.ts`](../apps/web/src/utils/exportDownload.ts) 会：

1. 优先 `showSaveFilePicker` 另存为到用户选择路径；不支持时回退浏览器下载
2. 调用 `POST .../assets/exports/{filename}/reveal` 在本机资源管理器中定位 `data/projects/.../assets/exports/` 下的服务端副本

## Premiere Pro 工程包导出（NLE）

除 MP4 成片外，支持导出 **Premiere Pro 可导入的 FCP7 XMEML 工程 ZIP**（不依赖 FFmpeg）：

| 项 | 说明 |
|----|------|
| 模块 | [`core/edit/nle_export/`](../core/edit/nle_export/)：`exporter` / `xmeml_writer` / `media_bundle` / `srt_writer` / `packager` |
| API | `POST .../export-nle` → 异步 job → `GET .../export-nle/{job_id}` |
| 产物 | `data/projects/.../assets/exports/nle_premiere_{id}.zip` |
| 下载 | `GET .../assets/exports/{filename}`（与 MP4 相同） |
| 定位文件夹 | `POST .../assets/exports/{filename}/reveal`：在本机资源管理器中选中 `data/projects/.../assets/exports/` 下文件（Windows `explorer /select`） |
| UI | 剪辑 Tab / 专业剪辑顶栏「导出 PR 工程」；导出完成后自动「另存为」并调用 reveal |

**ZIP 结构：**

```
nle_premiere_{id}.zip
├── project.xml      # FCP7 XMEML v5，素材 pathurl 指向 media/
├── subtitles.srt    # 字幕轨（若有）
├── README.txt       # PR 导入说明
└── media/           # 时间轴引用的图片/视频/音频副本
```

**PR 导入步骤：** 解压 ZIP → Premiere Pro → File → Import → 选择 `project.xml`。若提示离线媒体，确认 `media/` 与 `project.xml` 同级。

**能力边界：**

- 已导出：多视频图层、音频轨、字幕 SRT、片段入出点、基础 transform（静态 opacity 等）
- 未完整迁移：Ken Burns 运镜、复杂转场/Classic 特效、精确 composite（需在 PR 中手动重做）

**剪映草稿导出**：本期未实现（剪映 6.0+ 加密限制）；后续可基于 CapCut 国际版 / 剪映 5.9 + `pyJianYingDraft` 扩展。
