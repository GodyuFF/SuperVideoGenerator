# Tools 参考手册

> 更新日期：2026-07-20（delegate_agent 独占成轮；混用报错回写 observation）

本文档描述 SuperVideoGenerator 中 **MCP 语义 Tool Registry**（`core/llm/tools/`）与各 Agent 可调用的 action。主编排 ReAct 的 `delegate_agent` / `tool_*` 见文末「主编排专用」。

## 工具中心（Tool Center）

- **API**：`GET /api/tools` 返回 `governance`（治理规则）、`agents`（按 Agent 分组）、`catalog`（扁平目录）。
- **字段**：除 `scopes` / `operations` 外，每项含 `asset_layer`（资产层级）、`affected_data_read` / `affected_data_write`（影响数据，中文）、`boundary_note`、`may_write_edit_timeline`。
- **实现**：[`tool_data_scope.py`](../../../core/llm/tools/tool_data_scope.py)、[`tool_taxonomy.py`](../../../core/llm/tools/tool_taxonomy.py)、[`apps/api/routes/tools.py`](../../../apps/api/routes/tools.py)。
- **UI**：Agent 工作台「可选工具」列表与添加弹窗展示上述标签（[`AgentSettingsPage.tsx`](../../../apps/web/src/pages/AgentSettingsPage.tsx)）；添加弹窗每行右侧 **详情** 可展开入参/出参 JSON Schema（`input_schema` / `output_schema`，来自 Registry）。

## 数据边界治理（强制）

| 规则 | 说明 |
|------|------|
| **剪辑时间轴独占写** | `edit_timelines` 的创建与更新**仅**允许 `editing_agent` 的剪辑域 Tool（`plan_edit_timeline`、`add_clip` 等经 `patch_timeline`）。 |
| **分镜域不写时间轴** | `storyboard_refine_agent.sync_actual_assets`、`tts_agent.synthesize`、生图/生视频绑定等**只写分镜计划稿·镜头**，不得调用 `set_edit_timeline`。 |
| **用户 OpenCut** | REST `PATCH /api/.../edit-timeline` 为用户手改通道，不属于 Agent Tool。 |
| **只读 Tool** | `read_only=true` 的 action 不得产生 store 写副作用。 |
| **资产层级** | 写操作应约束在对应层级：文字资产 → 数字媒体 → 分镜计划稿 → 剪辑时间轴（见下表）。 |

### 资产层级（自下而上）

```
项目 → 剧本 → 文字资产 / 数字媒体资产 → 分镜计划稿（镜头） → 剪辑时间轴
```

### 剪辑时间轴相关 Tool（唯一可写）

| action | 影响数据（写） |
|--------|----------------|
| `plan_edit_timeline` | 剪辑时间轴（创建/合并）；读分镜计划稿、数字媒体 |
| `add_clip` / `update_clip` / `remove_clip` | 剪辑时间轴；回写分镜计划稿·镜头 |
| `apply_effect` / `set_keyframe` | 剪辑时间轴·片段元数据 |

其余 Agent 的 Tool 在 `may_write_edit_timeline=false`；详见 `GET /api/tools` 的 `catalog`。

### 跨范围只读资产查询（`multi_scope_read`）

| action | 查询数据范围（`affected_data_read`） | 说明摘要 |
|--------|--------------------------------------|----------|
| `list_text_assets` | 文字资产、数字媒体资产 | 剧本盘点 + 完整 content + linked_media |
| `load_context` | 剧本、文字资产、数字媒体资产、资产引用边 | 分镜设计上下文（plots、配图状态、音色） |
| `load_edit_context` | 分镜计划稿、剪辑时间轴、文字资产、数字媒体资产 | 剪辑准备聚合视图 |
| `tool_list_assets` | 文字资产、数字媒体资产 | 主编排资产总览 |
| `get_shot_details` | 分镜计划稿·镜头、文字资产、数字媒体资产 | 单镜详设与配图 |
| `get_shot_asset_timing` | 分镜计划稿·镜头、数字媒体资产 | 镜内音视频时长 |
| `gather_media` | 剪辑时间轴、数字媒体资产 | 时间轴引用素材与缺失项 |
| `validate_edit_assets` | 剪辑时间轴、数字媒体资产 | 素材齐备性校验 |
| `report_missing_assets` | 剪辑时间轴、数字媒体资产 | 缺失引用上报 |

---

## 全局工具 override（agent_config）

`data/agents/registry.json` → 全局 `tool_overrides[agent_name]`；`data/agents/profiles/{profile}/workspace.json` → Profile 级 `tool_overrides[agent_name]`（API 聚合为 `tool_overrides_by_profile`）：

| 字段 | 语义 |
|------|------|
| `exclude` | 从 ReAct `available_actions` 剔除（**system** 类工具始终保留） |
| `include_only` | 显式白名单；空 = 使用该 Agent 实现（impl）的默认可配置工具集；**可跨 Agent** 挂载 Registry 中任意非 system action（存在性校验）；与 `exclude` 同时存在时 **exclude 优先** |

**system 工具**（工作台 **UI 不展示**，运行时默认加载；不可写入 `include_only`）：

| Agent | 系统工具 |
|-------|----------|
| 全部 | `finish`、`ask_user_question` |
| 子 Agent | 另含 `return_to_master` |
| 超级视频大师 | 另含 `delegate_agent` 委派行动 |

工作台按 **作用范围**（`scopes`）与 **操作意义**（`operations`）展示工具标签；`system` 类工具不在工作台列出。

**工作台可选工具 UI**：展示当前 Agent 已生效的非 system 工具列表（含 `scopes` / `operations` / `description`）；支持删除与从全局 Registry（`GET /api/tools` 扁平化）跨 Agent 添加；首次编辑时由当前 effective 集初始化 `include_only`。

**Profile Agent roster 与工具**：各 Profile 工作区 `agent_roster` 决定侧栏可见 Agent 与主编排 `delegate_agent` 的 `agent_id` enum / `agents_catalog.md` 注入范围；`super_video_master` 不可删；`default` Profile 只读且磁盘工作区保持空基线（运行时 roster 回退全量内置）。实现：[`agent_registry.py`](../../../core/llm/agent/agent_registry.py)、[`delegate_tool.py`](../../../core/llm/master/delegate_tool.py)、[`agent_tool_config.py`](../../../core/llm/tools/agent_tool_config.py) 中 `list_global_configurable_tools` / `resolve_effective_configurable_tools`。

**工具分类（工作台展示）**：每个 action 附带多标签 `scopes`（作用范围，如 script/plot/character）与 `operations`（操作意义，如 read/create/generate）；**跨范围只读**工具（`multi_scope_read=true`，一次查询 ≥2 类持久化实体）在工作台**单独置顶分区**，描述中含「查询：…」数据范围说明。实现见 [`tool_taxonomy.py`](../../../core/llm/tools/tool_taxonomy.py)、[`tool_data_scope.py`](../../../core/llm/tools/tool_data_scope.py)。

主编排 `super_video_master` 的 override **仅作用于 `tool_*`**，不影响 `delegate_agent`。实现：`core/llm/tools/agent_tool_config.py`。

**单源注册**：各域 [`register.py`](../../../core/llm/tools/bootstrap.py) → [`ToolRegistry`](../../../core/llm/tools/registry.py)。`read_only=true` 表示只读查询；其余 action 可能产生 store 或会话上下文写副作用。Registry 内部 `ToolKind`（`write_pipeline` / `write_ad_hoc`）仅用于 ReAct 编排分桶，**不在工作台 UI 展示**。

**工作台专用工具（不注册 Registry）**：`generate_text_asset_draft`（[`core/llm/tools/workbench/generate_text_asset_draft.py`](../../../core/llm/tools/workbench/generate_text_asset_draft.py)）供剧本看板「新建角色/空镜/物品/画面」弹窗一键 AI 补全字段；经 `POST .../assets/generate-draft` 调用配置 LLM，返回 `{name, content}` JSON；**不出现在** Agent 可选工具列表与 `GET /api/tools` 分组。

**plan tracking**：所有 Registry action（含只读 list/get）的 `input_schema` 均声明 `plan_status` / `remaining_plan`（见 `core/llm/tools/shared/input_common.py` 的 `merge_plan_tracking`），与 ReAct 规则一致。

---

## script_agent

| action | logical_name | 读写 | 说明 | Handler |
|--------|--------------|------|------|---------|
| `parse_brief` | script.parse_brief | 读写 | 解析任务简报并通过 LLM 设计/写入剧本正文 | `script/handler.py` |
| `create_plot` | script.create_plot | 读写 | 创建剧情文字资产 | `script/handler.py` |
| `create_character` | script.create_character | 读写 | 创建人物共享资产 | `script/handler.py` |
| `create_scene` | script.create_scene | 读写 | 创建场景共享资产 | `script/handler.py` |
| `create_prop` | script.create_prop | 读写 | 创建道具共享资产 | `script/handler.py` |
| `update_script` | script.update_script | 读写 | 更新 Markdown 正文/时长；标题仅在占位名时可写入，已确认标题需用户 PATCH | `script/handler.py` + `guards/script_title` |
| `update_plot` | script.update_plot | 读写 | 更新剧情文字资产（需 asset_id） | `script/handler.py` |
| `update_character` | script.update_character | 读写 | 更新人物资产（需 asset_id） | `script/handler.py` |
| `update_scene` | script.update_scene | 读写 | 更新场景资产（需 asset_id） | `script/handler.py` |
| `update_prop` | script.update_prop | 读写 | 更新道具资产（需 asset_id） | `script/handler.py` |
| `delete_plot` | script.delete_plot | 读写 | 删除剧情资产（需 asset_id） | `script/handler.py` |
| `delete_character` | script.delete_character | 读写 | 删除人物资产（需 asset_id） | `script/handler.py` |
| `delete_scene` | script.delete_scene | 读写 | 删除场景资产（需 asset_id） | `script/handler.py` |
| `delete_prop` | script.delete_prop | 读写 | 删除道具资产（需 asset_id） | `script/handler.py` |
| `list_text_assets` | script.list_text_assets | 只读 | 列出剧本相关文字资产及完整 content JSON；output 含 `frame` 类型与 `linked_media` 扩展字段 | `script/handler.py` → `script/list.py` |

---

## image_agent

| action | logical_name | 读写 | 说明 | Handler |
|--------|--------------|------|------|---------|
| `scan_text_assets` | image.scan_text_assets | 读写 | 扫描待生图文字资产（含 **variants[]** / pending_variant_count / reference 就绪状态） | `image/scan.py` + `image/variants.py` |
| `generate_images` | image.generate_images | 读写 | 为文字资产生成图片并落盘 MediaAsset；frame 生图后 `bind_frame_media_to_plan` / `sync_plan_image_media_from_frames` 回填镜内 `sub_shots[].image.media_id` 与 z0 `video_tracks` clip | `image/handler.py` → `shot_media_bind.py` |
| `search_images` | image.search_images | 读写 | 搜索并关联配图（items 或 query+asset_id） | `image/search_sync.py` |
| `sync_text_from_image` | image.sync_text_from_image | 读写 | **仅搜图**后根据实际图片回写文字资产（白名单 auto-patch）；生图产出跳过 | `image/search_sync.py` |
| `list_images` | image.list_images | 只读 | 列出已生成图片资产（含链接/本地路径） | `shared/executor.py` → `shared/media_list.py` |

---

## storyboard_agent

| action | logical_name | 读写 | 说明 | Handler |
|--------|--------------|------|------|---------|
| `load_context` | storyboard.load_context | 读写 | 加载剧本正文、plots、图文资产、**voice_speakers**（旁白+角色）与已链接图片；**必传 `script_id`**（须与会话一致） | `storyboard/context.py` / `timeline_handler.py` |
| `create_shots` | storyboard.create_shots | 读写 | 设计镜内多轨 Shot；`sub_shots[]` 含 `produce_mode`、可选 `produce_rationale`、各 `images[].start_ms/end_ms`（相对镜起点）；**voice clip 须按说话人拆分**（旁白 character_ref 空，对白填 txt_*） | `storyboard/handler.py` |
| `create_frames` | storyboard.create_frames | 读写 | **故事书 / 画面图生视频**：每子镜创建 frame（必填 `sub_shot_id` + `image_prompt` + `element_refs`；`sub_shot_id` 全局唯一可单独定位；可选 `summary`/`notes`）；回填 `sub_shots[].images[]`；observation 含 `frame_links` | `storyboard/handler.py` |
| `create_video_clips` | storyboard.create_video_clips | 读写 | **AI 视频 / 画面图生视频**：每子镜创建 video_clip（必填 `sub_shot_id` + `video_prompt` + `element_refs`；可选 `source_frame_asset_id`，缺省自动取同子镜 frame）；回填 `videos[]`；observation 含 `video_clip_links` | `storyboard/handler.py` |
| `get_plan` | storyboard.get_plan | 只读 | 读取计划稿；persist 前返回 pending 的 shot/sub_shot ID 及已关联 frame/video_clip/source_frame | `storyboard/handler.py` |
| `persist_plan` | storyboard.persist_plan | 读写 | 保存 VideoPlan；故事书校验 frame；AI 视频校验 video_clip；**frame_i2v 双校验** | `storyboard/handler.py` |

> **职责边界**：video_clip / frame 的**创建与镜内关联**仅由 storyboard_agent 负责；video_agent 只消费 video_clip 生成 mp4。

---

## storyboard_refine_agent（分镜复核，TTS + 生图后）

| action | logical_name | 读写 | 说明 | Handler |
|--------|--------------|------|------|---------|
| `get_shot_details` | storyboard_refine.get_shot_details | 只读 | 查询分镜详情：镜内 `sub_shots`/`images[]`/`videos[]`、frame 配图状态、`image_gap_sub_shots` | `shot_query.py` → `handler.py` |
| `get_shot_asset_timing` | storyboard_refine.get_shot_asset_timing | 只读 | 查询音频/视频实测时长；音频含 `text_segments` 各时段文字 | `shot_query.py` → `handler.py` |
| `sync_actual_assets` | storyboard_refine.sync_actual_assets | 读写 | 同步实测资产到分镜计划稿·镜头（**不写剪辑时间轴**） | `handler.py` → `sync_actual_assets` |
| `review_shot` | storyboard_refine.review_shot | 读写 | **单镜**复核：增量 patch 时段 + `display_instructions`；patch 可修订 `sub_shots[].produce_mode`/`produce_rationale` 与 `images[].start_ms/end_ms` | `handler.py` → `storyboard_restructure.py` |
| `review_and_restructure` | storyboard_refine.review_and_restructure | 读写 | **跨镜** `restructure_ops[]` + 可选 `patches` | `handler.py` → `storyboard_restructure.py` |
| `update_frames` | storyboard_refine.update_frames | 读写 | 将 `display_instructions` 合并进 frame `notes` | `handler.py` |
| `persist_review` | storyboard_refine.persist_review | 读写 | 保存复核结果并确认 `detail_revision` | `handler.py` |
| `get_refine_plan` | storyboard_refine.get_refine_plan | 只读 | 读取含镜内多轨与复核字段的 VideoPlan | `handler.py` |

**流水线**：`get_shot_details` → `get_shot_asset_timing` → `sync_actual_assets` → **逐镜 `review_shot`** → `update_frames` → `persist_review`（跨镜 split/merge 时用 `review_and_restructure`）

**与用户 REST 共用**：`review_and_restructure` 的 `restructure_ops` 与 `POST .../video-plan/ops` 均调用 [`apply_restructure_ops`](../../../core/edit/storyboard_restructure.py)（含 `reorder`）；单镜字段 PATCH 走 [`video_plan_service.patch_shot_plan_fields`](../../../core/edit/video_plan_service.py)。

### 输入 schema（全部含 `plan_tracking`）

| action | 必填字段 | 可选过滤 |
|--------|----------|----------|
| `get_shot_details` | `observation`, `plan_status`, `remaining_plan` | `shot_id`, `shot_ids` |
| `get_shot_asset_timing` | 同上 | `shot_id`, `shot_ids`, `asset_kind`（audio/video/all） |
| `sync_actual_assets` | `observation`, `plan_status`, `remaining_plan` | — |
| `review_shot` | `observation`, `plan_status`, `remaining_plan`, `shot_id` | `patch` 与/或 `restructure_op` 至少一项非空 |
| `review_and_restructure` | `observation`, `plan_status`, `remaining_plan` | `patches` 或 `restructure_ops` 至少一项非空 |
| `get_refine_plan` | read-only 全套 | — |

### 输出 schema

| action | output schema | required | 备注 |
|--------|---------------|----------|------|
| `get_shot_details` | `shot_details_query` | `script_id`, `shot_count`, `shots` | 含 `image_gap_shot_ids`；**不含** `text_segments` |
| `get_shot_asset_timing` | `shot_asset_timing` | `script_id`, `shot_count`, `shots` | 每镜 `actual_duration_ms`（实时探测）与 `assets.audio.duration_ms` 同源；`cached_actual_duration_ms` 为上次 sync 缓存；`assets.audio` 含 `duration_source`、`metadata_duration_ms`、`text_segments[]` |
| `sync_actual_assets` | `shot_sync` | `shot_count` | 含 `plan_id`, `detail_revision` |
| `review_shot` | `shot_refine_mutation` | `action`, `detail_revision`, `shot_count` | 含 `shot_id` |
| `review_and_restructure` | `shot_refine_mutation` | `action`, `detail_revision`, `shot_count` | — |
| `persist_review` | `shot_persist` | `action`, `plan_id`, `detail_revision` | — |

---

## video_agent

| action | logical_name | 读写 | 说明 | Handler |
|--------|--------------|------|------|---------|
| `scan_video_clips` | video.scan_video_clips | 只读 | 扫描 storyboard 已创建的 video_clip 就绪状态 | `video/scan.py` → `handler.py` |
| `generate_video_clips` | video.generate_video_clips | 读写 | **主流水线**：为已有 video_clip 生成 mp4；**frame_i2v** 经 `frame_i2v_spec` 以 frame 为唯一图生源 | `video/video_clips.py` |
| `load_shots` | video.load_shots | 读写 | 【legacy ad_hoc】加载分镜镜头列表 | `video/handler.py` |
| `generate_clips` | video.generate_clips | 读写 | 【legacy ad_hoc】为镜头生成片段 | `video/handler.py` |
| `generate_from_timeline` | video.generate_from_timeline | 读写 | 【ad_hoc】按剪辑 video 轨生成 | `video/handler.py` |
| `list_videos` | video.list_videos | 只读 | 列出已生成视频资产 | `shared/executor.py` |

> **职责边界**：video_agent **不**创建 video_clip 或镜内关联；缺 video_clip 时应 return_to_master → storyboard_agent。

---

## tts_agent

| action | logical_name | 读写 | 说明 | Handler |
|--------|--------------|------|------|---------|
| `extract_narration` | tts.extract_narration | 读写 | 从 VideoPlan 确定性提取旁白（`extract.py`） | `tts/handler.py` |
| `synthesize` | tts.synthesize | 读写 | 按镜头并发合成 mp3 落盘；成功后自动 `sync_plan_from_tts`（仅写分镜，**不写剪辑时间轴**） | `tts/handler.py` |
| `list_audio` | tts.list_audio | 只读 | 列出配音资产 | `shared/executor.py` |

---

## editing_agent

| action | logical_name | 读写 | 说明 | Handler |
|--------|--------------|------|------|---------|
| `load_edit_context` | edit.load_edit_context | 只读 | 聚合 VideoPlan 分镜、shots.resolved 素材、plots、assets_with_images、media 清单与 edit_timeline 摘要 | `editing/context.py` → `timeline_handler.py` |
| `plan_edit_timeline` | edit.plan_edit_timeline | 读写 | 生成详细剪辑计划稿（三轨 + 运镜/转场/背景/source_refs）；`skip_subtitle_enrich=true` 或 `replace`+空 `subtitle` 轨时跳过 TTS 字幕自动回填 | `editing/timeline_handler.py` |
| `validate_edit_assets` | edit.validate_edit_assets | 只读 | 校验剪辑计划稿素材是否齐备；输出 `{ready, missing_items, resolved_clips, summary}` | `editing/timeline_handler.py` |
| `report_missing_assets` | edit.report_missing_assets | 读写 | 上报缺失素材（内部构造 `ReturnToMasterError`）供主编排重委派上游 | `editing/timeline_handler.py` |
| `get_edit_timeline` | edit.get_edit_timeline | 只读 | 读取剪辑计划稿 | `editing/timeline_handler.py` |
| `analyze_edit_timeline` | edit.analyze_edit_timeline | 只读 | 按 `start_ms`/`end_ms` 读取时间段内各轨 clip 详情（`edit_description`/运镜/转场/transform/`resolved` 素材）；可选 `include_analysis=false` 仅读详情；默认含 gaps/overlaps/hints/alignment | `timeline_handler.py` → `core/edit/timeline_analysis.py` |
| `gather_media` | edit.gather_media | 读写 | 收集 EditTimeline 引用的图片/视频/配音；observation 含 `missing_refs` | `editing/handler.py` → `llm_action.py` |
| `compose_final` | edit.compose_final | 读写 | 校验素材就绪后 FFmpeg 合成成片；`skip_subtitles=true` 导出纯画面+配音 | `editing/handler.py` → `llm_action.py` |
| `list_final` | edit.list_final | 只读 | 列出 FINAL 类型 media 资产 | `editing/handler.py` |

### 精确剪辑工具（OpenCut Classic 融合）

| action | logical_name | 读写 | 说明 | 实现 |
|--------|--------------|------|------|------|
| `add_clip` | edit.add_clip | 读写 | 向 video/audio/subtitle 轨添加片段；`duration_ms` 缺省时读素材真实时长（音频优先本地探测，兜底 3000ms）；audio/subtitle 轨**追加**到现有 clips（不整轨替换）；输出 `{action, clip_id, track?, revision?}` | `opencut_handler.py` |
| `update_clip` | edit.update_clip | 读写 | 修改位置、时长、transform、运镜；输出 `{action, clip_id, revision?}`（**非** asset_mutation） | `opencut_handler.py` |
| `remove_clip` | edit.remove_clip | 读写 | 删除片段；输出 `{action, clip_id}` | `opencut_handler.py` |
| `apply_effect` | edit.apply_effect | 读写 | 应用视觉效果（持久化 metadata）；输出 `{action, clip_id, effect_type, params, revision?}` | `opencut_handler.py` |
| `set_keyframe` | edit.set_keyframe | 读写 | 设置 transform 关键帧；输出 `{action, clip_id, time_ms, properties, revision?}` | `opencut_handler.py` |
| `export_timeline` | edit.export_timeline | 读写 | 触发 FFmpeg 导出，返回 `{action, job_id}` | `opencut_handler.py` |
| `get_export_status` | edit.get_export_status | 只读 | 轮询导出进度；输出对齐 `job_to_dict`（`job_id/status/progress/...`，**不含** `action`） | `opencut_handler.py` |
| `list_final` | edit.list_final | 只读 | 列出成片资产 | `shared/executor.py` |

---

## 全 Agent 共享（common）

| action | logical_name | 读写 | 说明 | Handler |
|--------|--------------|------|------|---------|
| `return_to_master` | common.return_to_master | 读写 | 缺上游素材/需用户确认/阻塞时交还主编排；清空子会话并 `StepStatus.PAUSED` | `shared/return_to_master_handler.py` |
| `read_webpage` | common.read_webpage | 只读 | 读取指定 URL 网页正文（http/https，只读） | `web_fetch/tool.py` |
| `ask_user_question` | common.ask_user_question | ad_hoc | 向用户询问缺失信息（A2UI 弹窗，非 Registry 写操作） | `react_core` + A2UI |

`read_webpage` 由 [`register_common_tools`](../../../core/llm/tools/common/register.py) 注册。**注入范围**：默认挂载 `script_agent`；**不注入** `storyboard_agent`、`storyboard_refine_agent`、`tts_agent`、`editing_agent`、`image_agent`、`video_agent`（见 [`bootstrap.py`](../../../core/llm/tools/bootstrap.py) `_exclude_common`）。主编排使用 `tool_read_webpage`。

**URL 限制**：拒绝 `localhost`/内网地址及含 `/api/projects/` 的内部 API 路径；失败 observation 引导使用 `list_text_assets` / `list_audio` / `gather_media` 等内置工具。

### 扩展 Tool（svg.tools entry_points）

| action | logical_name | 读写 | 说明 | 注册 |
|--------|--------------|------|------|------|
| `web_search` | utility.web_search | 只读 | 联网搜索（DuckDuckGo / Tavily） | [`core/extensions/builtin/web_search.py`](../../../core/extensions/builtin/web_search.py) |

**输入（ReAct）**：`query`（必填）、`observation`、`plan_status`、`remaining_plan`，可选 `max_results`（1–20）。Handler 与 `ToolSpec.input_schema` 共用 [`web_search_react_input_schema`](../../../core/llm/tools/web_search/schemas.py)，避免 Registry 与 handler 双重校验 schema 不一致。

**执行**：[`search_web`](../../../core/llm/tools/web_search/service.py) → 默认 DuckDuckGo HTML；若 `SVG_WEB_SEARCH_PROVIDER=tavily` 且配置 API Key 则走 Tavily。

默认**不**自动注入各 Agent；Skill `tools.enable` / `tools.agents` 或 pip 扩展包挂载。详见 [extensions.md](extensions.md)。

### 外部 MCP Tool（Phase 2）

Registry 名格式 `mcp.{server_id}.{tool_name}`，`source=mcp`。配置见 `data/mcp_config.json` 与 `GET /api/mcp/servers`。

---

## 主编排专用（super_video_master）

以下 action **不在** MCP Registry，由 [`core/llm/master/tools.py`](../../../core/llm/master/tools.py) 与 [`core/llm/master/actions.py`](../../../core/llm/master/actions.py) 定义，经 `build_master_react_tools` 暴露给主编排 ReAct。

### 委派（delegate_agent）

| 参数 / 字段 | 说明 |
|-------------|------|
| `delegate_agent` | 统一委派工具；`kind: agent`；**必须单独成轮**，禁止与 `tool_*` / `finish` / `ask_user_question` 同轮并行（违反 → `ExclusiveToolBatchError`，observation 回写后可纠正） |
| `agent_id` | Profile roster 中的子 Agent 编码（如 `script_agent`、`copywriter`）；enum 由 `build_delegate_agent_input_schema` 按当前 Profile + 风格动态生成 |
| `step_type`（内部） | 由 `resolve_step_for_roster_agent(agent_id)` 反向解析，用于完成态追踪（`completed_step_types`） |

各 `agent_id` 与步骤说明见 `agents_catalog.md` 与工具 `description`（`build_delegate_agent_description`）。

### 主编排工具（tool_*）

| action | 说明 |
|--------|------|
| `tool_get_plan_summary` | 查询当前计划版本与各步骤执行状态 |
| `tool_list_assets` | 查询剧本文字/图片/音频/视频/成片资产清单（含 URL 与可访问性） |
| `tool_read_webpage` | 读取网页正文（复用 web_fetch 逻辑） |

### 结束

| action | 说明 |
|--------|------|
| `finish` | 主编排或子 Agent 标记当前任务完成 |

### return_to_master 协议

子 Agent 在缺上游素材、需用户确认或外部阻塞时调用 `return_to_master`（**非** `finish`）。该工具以 `COMMON_AGENT` 注册，经 [`bootstrap.py`](../../../core/llm/tools/bootstrap.py) 自动合并进各子 Agent 的 `ad_hoc_actions`；**勿**在 `decide_sub_agent` 中重复追加，否则 LLM API 会报 `Tool names must be unique`。主编排收到后步骤标记 `PAUSED`，清空该子 Agent 会话；补数据后带 `resume_context` 重委派。`report_missing_assets` 为剪辑专用别名，内部同样抛出 `ReturnToMasterError`。

| 字段 | 说明 |
|------|------|
| `reason` | `missing_upstream` / `needs_user_input` / `blocked` / `partial_done` |
| `observation` | 给主编排的自然语言摘要 |
| `missing_items` | 结构化缺失列表（可选） |
| `suggested_agent_ids` | 建议下一步委派的 `agent_id`（可选） |
| `resume_hint` | 补数据后如何重试本 Agent（可选） |

---

## output_schema 注册规则

[`output_schema_for()`](../../../core/llm/tools/register_helpers.py) 按以下优先级解析，**禁止**用宽泛 `startswith("update_")` 误匹配非 script 域 tool：

| 映射表 | 覆盖示例 |
|--------|----------|
| `_STORYBOARD_REFINE_OUTPUT` | `get_shot_details`、`get_shot_asset_timing`、`get_refine_plan`、`update_frames`、`shot_refine_mutation`、`shot_persist` |
| `_EDITING_OUTPUT` | `add_clip`、`update_clip`、`get_export_status`、`export_timeline` |
| `_SCRIPT_UPDATE_OUTPUT` | `update_script`、`update_character`、`update_plot` 等 |
| 具名 fallback | `list_text_assets`、`get_plan`、`load_edit_context` 等 |
| 默认 | `generic_action_output_schema()`（仅 `make_write_handler` 类写操作） |

**context/read tool**（如 `get_shot_details`、`get_export_status`）的 `required` **不得**含 `action`。`ToolRegistry.call_tool` 在 handler 成功后校验 `result.structured`；失败 observation 含 `tool=` 与 `required=` 便于定位。

回归测试：[`tests/unit/test_all_tools_output_schema.py`](../../../tests/unit/test_all_tools_output_schema.py)。

---

## 相关文档

- 提示词与 messages 组装：[`prompt-architecture.md`](prompt-architecture.md)
- 代码结构与 Registry 设计：[`code-design-plan.md`](code-design-plan.md) §5.3.1
- AI 配置 API：[`code-design-plan.md`](code-design-plan.md) §5.3.3（`GET/PATCH /api/ai/config`）

### 生图 / 生视频 Provider（AI 设置页）

| 能力 | provider | 默认模型 | API Key 环境变量 |
|------|----------|----------|------------------|
| **LLM 编排** | `deepseek` / `anthropic` / `openai` / `openrouter` / `moonshot` / `zhipu` / `dashscope` | 见各 provider 预设 | `DEEPSEEK_API_KEY` / `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` 等 |
| 生图 | `agnes` / `local_sd` / `bailian` / **`volcengine`** / **`openai`** / **`fal`** / **`gemini`** | `doubao-seedream-5-0-pro`（火山） | `SVG_IMAGE_GEN_API_KEY` 或 provider 专用 Key |
| 生视频 | `agnes` / **`volcengine`** / **`kling`** / **`runway`** / **`fal`** | `doubao-seedance-2-0`（火山） | `SVG_VIDEO_GEN_API_KEY` 或 provider 专用 Key |

LLM wire 协议：`anthropic`（DeepSeek/Anthropic）与 `openai`（OpenAI/OpenRouter/Moonshot/智谱/通义）。实现：`core/llm/client/wire.py`、`core/llm/client/wire_openai.py`。

Provider 能力矩阵：`core/llm/tools/shared/media_capability.py`。主 Provider 失败（429/5xx）时可配置 `fallback_provider` / `fallback_model` 自动降级。

火山方舟 Base URL：`https://ark.cn-beijing.volces.com/api/v3`。控制台：[SeedDream](https://console.volcengine.com/ark/region:cn-beijing/model/detail?name=doubao-seedream-5-0-pro) · [SeedDance](https://console.volcengine.com/ark/region:cn-beijing/model/detail?name=doubao-seedance-2-0)。实现：`core/llm/tools/image/ark_client.py`、`core/llm/tools/video/ark_client.py`、`core/llm/tools/video/provider.py`。
