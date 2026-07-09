# Edit Studio 规格说明

> 更新日期：2026-07-09（含 Premiere Pro 工程包导出）

## 目标

将只读剪辑看板升级为 **可预览、可拖拽、可写回** 的多轨剪辑工作室；成片导出默认走 **FFmpeg**；专业弹窗内另提供 **Classic 浏览器导出**；`editing_agent` 在用户已编辑时间轴上采用 **merge** 策略。视频采用 **多条视频图层轨**（`video_layers[]`），支持画中画叠加与画布变换/关键帧。

## 架构

```
剧本页剪辑 Tab (EditTabSimpleView)  — OpenCut WASM 预览/播放/导出 + 预加载 Classic
  └── OpenCutPreviewPane（仅 PreviewPanel，与弹窗共享 EditorCore；studioOpen 时暂停）
  └── EditorStudioModal — 剪辑助手弹窗（完整 Classic 编辑器，`apps/web/src/editor/opencut/`）
        └── SvfClassicEditor + SvfClassicEditorShell
              ├── SvfEditorHeader（浏览器导出 / 快捷键 / 撤销）
              ├── Assets / Preview / Properties / Timeline（完整 Classic）
              └── svf-storage-bridge + SvfMediaBridge

用户 UI  ←PATCH→  timeline_service  →  EditTimeline (store + metadata.classic_project)
editing_agent plan_edit_timeline (mode=merge)  ────────────────┘
compose_final / POST export  →  ffmpeg_renderer  →  exports/*.mp4
POST export-nle  →  nle_export  →  exports/nle_premiere_*.zip
预览：剪辑 Tab 与 Classic 弹窗/独立页均使用 opencut-wasm（buildScene + CanvasRenderer）
```

## API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/edit/capabilities` | 运镜/转场/背景枚举 + `ffmpeg_available` / `export_enabled` / `nle_export_enabled` / `max_video_layers` |
| GET | `/api/projects/{pid}/scripts/{sid}/edit-timeline` | 时间轴 + `video_layers` + revision + 每 clip `preview_url` |
| PATCH | 同上，`If-Match: revision` | 用户写回（`video_layers`、`tracks`、`duration_ms`、`metadata`） |
| POST | `.../edit-timeline/validate` | 素材与软校验 |
| POST | `.../edit-timeline/analyze` | 按时间窗分析 clip/空白/重叠/分镜对齐与优化建议（body：`start_ms`、`end_ms`、`tracks[]`、`layer_ids[]`、`include_hints`、`include_shot_alignment`） |
| POST | `.../export` | 异步 FFmpeg 导出 |
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

**向后兼容**：仅含 `tracks.video[]` 的旧数据在 `ensure_video_layers` 时自动包装为单层 `{name:"主画面", z_index:0}`；写入时 `sync_legacy_video_track` 同步扁平 `tracks.video`。

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
- `enrich_subtitles_from_audio`：读取 audio 资产 `metadata.subtitle_cues`（`tts_gen` 落盘），按 audio 轨 offset 生成逐句 `tracks.subtitle`；无 cues 时按标点 + 时长比例 fallback（[`subtitle_align.py`](../core/edit/subtitle_align.py)）

不覆盖 `user_locked` 或 `edited_by=user` 的 clip。

### 画布缩放导出

- `transform.width/height`：预览与 FFmpeg 导出一致（composite 或 `_render_clip_with_transform`）
- Ken Burns：`motion != static` 触发 composite；边界每 250ms 采样（[`ken_burns_filter.py`](../core/edit/ken_burns_filter.py)）；导出时 `transform_to_overlay_pixels` 将 pad 目标规范为偶数，`scale` 滤镜带 `force_divisible_by=2`；`motion=static` 不应用 `motion_detail` 缩放
- dynamic_image 模式默认走 `composite_slices` 导出

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
4. **`source_refs.video_plan_shot_order`**：先按 0-based `order` 匹配；失败且 order≥1 时再试 `order-1`（兼容 Agent 1-based 写法如 `shot_1` + `order: 1`）

前端 [`OpenCutPreviewPane`](../apps/web/src/editor/OpenCutPreviewPane.tsx) 与 Classic [`PreviewPanel`](../apps/web/src/editor/opencut/preview/components/index.tsx) 共用 `buildScene` + opencut-wasm 渲染。数据链路：

1. `installSvfStorageBridge` 拉取 `/media` + `edit-timeline`
2. `hydrateSvfMediaFiles` 将 URL 水合为可解码 `File`（视频预览必需）
3. `loadFromSvf` 构建 Classic project（快照场景会重映射 `mediaId`）
4. `EditorProvider.loadProject` → `media.loadProjectMedia` + `initializeScenes`
5. `RenderTreeController` 调用 `buildScene`（要求 `mediaMap` 命中且 `file`+`url` 齐全）

`timeline.revision` / `updated_at` 变化时 Tab 预览会 `force` 刷新 bridge 并重载 `EditorProvider`。

## Agent merge 规则

| 场景 | 行为 |
|------|------|
| 无 existing | create 全量 |
| user_edited=false | replace 可全量 |
| user_edited=true + mode=merge | 保留 user/locked clip 与层，追加 Agent 新 clip |
| mode=replace | 全量替换 |

`plan_edit_timeline` 优先输出 `video_layers[]`；主画面 `z_index=0`，画中画/贴纸放更高层并写明 `transform`。过渡期仍接受 `tracks.video`（归一化进 `video_layers[0]`）。

## 前端模块

> 更新日期：2026-07-09 — OpenCut Classic 完整弹窗，无 EditStudio 回退。

| 模块 | 职责 |
|------|------|
| `EditTabSimpleView.tsx` | 剪辑 Tab（左上角「剪辑助手」）+ WASM 预览 +「剪辑修改」打开弹窗 + `prefetchClassicStudio()` |
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
| 关键帧 / Ken Burns | `collect_timeline_boundaries`（含 250ms Ken Burns 采样）；dynamic_image 默认 composite_slices |
| 素材校验 | 导出前 `validate_edit_timeline`；缺图/配音时拒绝导出 |
| audio 轨 | adelay + amix |
| 字幕 | 预览 HTML overlay + 导出 ASS 硬字幕（[`subtitle_burn.py`](../core/edit/subtitle_burn.py)）；Windows 路径 `\:` 转义（无 shell 引号）；ASS 失败时 drawtext 回退；`compose_final.skip_subtitles=true` 或 `SVG_BURN_SUBTITLES=0` 可跳过烧录 |

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

## Premiere Pro 工程包导出（NLE）

除 MP4 成片外，支持导出 **Premiere Pro 可导入的 FCP7 XMEML 工程 ZIP**（不依赖 FFmpeg）：

| 项 | 说明 |
|----|------|
| 模块 | [`core/edit/nle_export/`](../core/edit/nle_export/)：`exporter` / `xmeml_writer` / `media_bundle` / `srt_writer` / `packager` |
| API | `POST .../export-nle` → 异步 job → `GET .../export-nle/{job_id}` |
| 产物 | `data/projects/.../assets/exports/nle_premiere_{id}.zip` |
| 下载 | `GET .../assets/exports/{filename}`（与 MP4 相同） |
| UI | 剪辑 Tab / 专业剪辑顶栏「导出 PR 工程」 |

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
