# Tools 参考手册

> 更新日期：2026-07-06

本文档描述 SuperVideoGenerator 中 **MCP 语义 Tool Registry**（`core/llm/tools/`）与各 Agent 可调用的 action。主编排 ReAct 的 `delegate_*` / `tool_*` 见文末「主编排专用」。

**单源注册**：各域 [`register.py`](../core/llm/tools/bootstrap.py) → [`ToolRegistry`](../core/llm/tools/registry.py)。`read_only=true` 表示只读查询；`write_pipeline` 为流水线写操作；`write_ad_hoc` 为按需修改/删除。

**plan tracking**：所有 Registry action（含只读 list/get）的 `input_schema` 均声明 `plan_status` / `remaining_plan`（见 `core/llm/tools/shared/input_common.py` 的 `merge_plan_tracking`），与 ReAct 规则一致。

---

## script_agent

| action | logical_name | 类型 | 说明 | Handler |
|--------|--------------|------|------|---------|
| `parse_brief` | script.parse_brief | write_pipeline | 解析任务简报并通过 LLM 设计/写入剧本正文 | `script/handler.py` |
| `create_plot` | script.create_plot | write_pipeline | 创建剧情文字资产 | `script/handler.py` |
| `create_character` | script.create_character | write_pipeline | 创建人物共享资产 | `script/handler.py` |
| `create_scene` | script.create_scene | write_pipeline | 创建场景共享资产 | `script/handler.py` |
| `create_prop` | script.create_prop | write_pipeline | 创建道具共享资产 | `script/handler.py` |
| `update_script` | script.update_script | write_ad_hoc | 更新剧本标题或 Markdown 正文 | `script/handler.py` |
| `update_plot` | script.update_plot | write_ad_hoc | 更新剧情文字资产（需 asset_id） | `script/handler.py` |
| `update_character` | script.update_character | write_ad_hoc | 更新人物资产（需 asset_id） | `script/handler.py` |
| `update_scene` | script.update_scene | write_ad_hoc | 更新场景资产（需 asset_id） | `script/handler.py` |
| `update_prop` | script.update_prop | write_ad_hoc | 更新道具资产（需 asset_id） | `script/handler.py` |
| `delete_plot` | script.delete_plot | write_ad_hoc | 删除剧情资产（需 asset_id） | `script/handler.py` |
| `delete_character` | script.delete_character | write_ad_hoc | 删除人物资产（需 asset_id） | `script/handler.py` |
| `delete_scene` | script.delete_scene | write_ad_hoc | 删除场景资产（需 asset_id） | `script/handler.py` |
| `delete_prop` | script.delete_prop | write_ad_hoc | 删除道具资产（需 asset_id） | `script/handler.py` |
| `list_text_assets` | script.list_text_assets | read | 列出剧本相关文字资产及完整 content JSON | `script/handler.py` → `script/list.py` |

---

## image_agent

| action | logical_name | 类型 | 说明 | Handler |
|--------|--------------|------|------|---------|
| `scan_text_assets` | image.scan_text_assets | write_pipeline | 扫描待生图文字资产（含 **variants[]** / pending_variant_count / reference 就绪状态） | `image/scan.py` + `image/variants.py` |
| `generate_images` | image.generate_images | write_pipeline | 为文字资产生成图片（默认 Agnes AI API）并落盘 MediaAsset；**单项失败最多重试 3 次**，仍失败则 `ImageGenerationAbortError`（含全部失败项 `failure_analysis`）；主编排根据 observation 决定是否 `delegate_script_design` 修 prompt | `image/handler.py` → `image/generate.py` → `llm_action.py` |
| `search_images` | image.search_images | write_pipeline | 搜索并关联配图（items 或 query+asset_id） | `image/search_sync.py` |
| `sync_text_from_image` | image.sync_text_from_image | write_ad_hoc | **仅搜图**后根据实际图片回写文字资产（白名单 auto-patch）；生图产出跳过 | `image/search_sync.py` |
| `list_images` | image.list_images | read | 列出已生成图片资产（含链接/本地路径） | `shared/executor.py` → `shared/media_list.py` |

---

## storyboard_agent

| action | logical_name | 类型 | 说明 | Handler |
|--------|--------------|------|------|---------|
| `load_context` | storyboard.load_context | write_pipeline | 加载剧本正文、plots、图文资产与已链接图片（观察结果含完整 JSON；输出 schema 含 `action`） | `storyboard/context.py` |
| `create_shots` | storyboard.create_shots | write_pipeline | 设计镜头列表；`asset_refs` 使用 `image`/`character`/`scene`/`prop` 键（**禁止** `asset_id` 键） | `storyboard/handler.py` |
| `persist_plan` | storyboard.persist_plan | write_pipeline | 保存视频计划稿（**不**自动生成 EditTimeline） | `storyboard/handler.py` |
| `get_plan` | storyboard.get_plan | read | 读取当前视频计划稿 | `storyboard/handler.py` |

---

## video_agent

| action | logical_name | 类型 | 说明 | Handler |
|--------|--------------|------|------|---------|
| `load_shots` | video.load_shots | write_pipeline | 加载分镜镜头列表 | `video/handler.py` |
| `generate_clips` | video.generate_clips | write_pipeline | 为镜头生成 AI 视频片段 | `video/handler.py` |
| `generate_from_timeline` | video.generate_from_timeline | write_pipeline | 按剪辑 video 轨生成片段（ai_video） | `video/handler.py` → `llm_action.py` |
| `list_videos` | video.list_videos | read | 列出已生成视频资产 | `shared/executor.py` |

---

## tts_agent

| action | logical_name | 类型 | 说明 | Handler |
|--------|--------------|------|------|---------|
| `extract_narration` | tts.extract_narration | write_pipeline | 从 VideoPlan 确定性提取旁白（`extract.py`） | `tts/handler.py` |
| `synthesize` | tts.synthesize | write_pipeline | 按镜头并发合成 mp3 落盘（`synthesize.py` → `core/tts/`）；LLM 无需填 url | `tts/handler.py` |
| `list_audio` | tts.list_audio | read | 列出配音资产 | `shared/executor.py` |

---

## editing_agent

| action | logical_name | 类型 | 说明 | Handler |
|--------|--------------|------|------|---------|
| `load_edit_context` | edit.load_edit_context | read | 聚合 VideoPlan 分镜、shots.resolved 素材、plots、assets_with_images、media 清单与 edit_timeline 摘要 | `editing/context.py` → `timeline_handler.py` |
| `plan_edit_timeline` | edit.plan_edit_timeline | write_pipeline | 生成详细剪辑计划稿（三轨 + 运镜/转场/背景/source_refs） | `editing/timeline_handler.py` |
| `validate_edit_assets` | edit.validate_edit_assets | read | 校验剪辑计划稿素材是否齐备 | `editing/timeline_handler.py` |
| `report_missing_assets` | edit.report_missing_assets | write_pipeline | 上报缺失素材（内部构造 `ReturnToMasterError`）供主编排重委派上游 | `editing/timeline_handler.py` |
| `get_edit_timeline` | edit.get_edit_timeline | read | 读取剪辑计划稿 | `editing/timeline_handler.py` |
| `gather_media` | edit.gather_media | write_pipeline | 收集 EditTimeline 引用的图片/视频/配音；observation 含 `missing_refs` | `editing/handler.py` → `llm_action.py` |
| `compose_final` | edit.compose_final | write_pipeline | 校验素材就绪后 FFmpeg 合成成片（唯一导出路径） | `editing/handler.py` → `llm_action.py` |
| `list_final` | edit.list_final | read | 列出成片资产 | `shared/executor.py` |

---

## 全 Agent 共享（common）

| action | logical_name | 类型 | 说明 | Handler |
|--------|--------------|------|------|---------|
| `return_to_master` | common.return_to_master | write_ad_hoc | 缺上游素材/需用户确认/阻塞时交还主编排；清空子会话并 `StepStatus.PAUSED` | `shared/return_to_master_handler.py` |
| `read_webpage` | common.read_webpage | read | 读取指定 URL 网页正文（http/https，只读） | `web_fetch/tool.py` |
| `ask_user_question` | common.ask_user_question | ad_hoc | 向用户询问缺失信息（A2UI 弹窗，非 Registry 写操作） | `react_core` + A2UI |

`read_webpage` 由 [`register_common_tools`](../core/llm/tools/common/register.py) 注册。**注入范围**：默认挂载 `script_agent`；**不注入** `storyboard_agent`、`tts_agent`、`editing_agent`、`image_agent`、`video_agent`（见 [`bootstrap.py`](../core/llm/tools/bootstrap.py) `_exclude_common`）。主编排使用 `tool_read_webpage`。

**URL 限制**：拒绝 `localhost`/内网地址及含 `/api/projects/` 的内部 API 路径；失败 observation 引导使用 `list_text_assets` / `list_audio` / `gather_media` 等内置工具。

---

## 主编排专用（super_video_master）

以下 action **不在** MCP Registry，由 [`core/llm/master/tools.py`](../core/llm/master/tools.py) 与 [`core/llm/master/actions.py`](../core/llm/master/actions.py) 定义，经 `build_master_react_tools` 暴露给主编排 ReAct。

### 委派（delegate_*）

| action | 对应步骤 | 说明 |
|--------|----------|------|
| `delegate_script_design` | script_design | 委派剧本与文字资产设计 |
| `delegate_image_gen` | image_gen | 委派图片素材生成 |
| `delegate_storyboard` | storyboard | 委派分镜与视频计划稿 |
| `delegate_video_gen` | video_gen | 委派 AI 视频生成（ai_video 风格） |
| `delegate_tts_gen` | tts_gen | 委派配音生成 |
| `delegate_edit_compose` | edit_compose | 委派剪辑合成 |

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

子 Agent 在缺上游素材、需用户确认或外部阻塞时调用 `return_to_master`（**非** `finish`）。该工具以 `COMMON_AGENT` 注册，经 [`bootstrap.py`](../core/llm/tools/bootstrap.py) 自动合并进各子 Agent 的 `ad_hoc_actions`；**勿**在 `decide_sub_agent` 中重复追加，否则 LLM API 会报 `Tool names must be unique`。主编排收到后步骤标记 `PAUSED`，清空该子 Agent 会话；补数据后带 `resume_context` 重委派。`report_missing_assets` 为剪辑专用别名，内部同样抛出 `ReturnToMasterError`。

| 字段 | 说明 |
|------|------|
| `reason` | `missing_upstream` / `needs_user_input` / `blocked` / `partial_done` |
| `observation` | 给主编排的自然语言摘要 |
| `missing_items` | 结构化缺失列表（可选） |
| `suggested_delegates` | 建议下一步 `delegate_*`（可选） |
| `resume_hint` | 补数据后如何重试本 Agent（可选） |

---

## 相关文档

- 提示词与 messages 组装：[`prompt-architecture.md`](prompt-architecture.md)
- 代码结构与 Registry 设计：[`code-design-plan.md`](code-design-plan.md) §5.3.1
- AI 配置 API：[`code-design-plan.md`](code-design-plan.md) §5.3.3（`GET/PATCH /api/ai/config`）
