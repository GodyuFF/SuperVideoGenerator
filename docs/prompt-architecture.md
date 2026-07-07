# 提示词架构（core/llm/prompt）

> 更新日期：2026-07-06（多图层 video_layers、plan_edit_timeline transform）

本文档描述 SuperVideoGenerator 中 Agent 提示词的 **固定区 / 动态区** 分层设计，参考 Claude Code 的 system prompt 组装模式。

## 1. 设计原则

| 概念 | Claude Code | 本项目 |
|------|-------------|--------|
| 固定区 | system prompt 中可缓存的静态段落 | `rules/*.md` + `agents/*/fixed/*.md` → **system** |
| 动态区 | 会话/环境/历史等运行时内容 | 模板槽位 + Store 快照 → **user** |
| 项目规则 | CLAUDE.md 注入对话 | 项目 `role_prompt` override（`prompt_resolver`） |
| 按需加载 | Skills / MCP | `PromptProfile` + **单轮 Skill**（`/skillId` → `core/llm/prompt/skills/`） |

**边界约定**：提示词在 `core/llm/prompt/` 组装为 canonical **`LlmRequest`**（`system` / `tools` / `messages` 同级）；wire 层经 `core/llm/client/wire.py` 映射为 **Anthropic Messages API**（`system` 顶层字段、`tools` 为 `{name, description, input_schema}`，**不发送** `output_schema`）；交互日志分列记录 `system`、`tools`、`messages`；Registry 执行结果的结构化载荷写入 ReAct 事件 `tool_structured`。

**Tool 单源**：`core/llm/tools/` 提供 MCP 语义 Registry（`list_tools` / `call_tool`），各 tool 含 `input_schema` + `output_schema`；`core/llm/prompt/tools/registry.py` 的 `build_sub_agent_react_tools` / `build_action_tool` 从 Registry 读取 schema；`core/llm/tools/shared/agent_tools.py` 的 `AGENT_TOOLS` 由 Registry 懒加载生成（兼容层）。

| 字段 | 主编排 | 子 Agent |
|------|--------|----------|
| `system` | `build_react_static_system`（协议 + 角色 + goal_mode） | `build_react_system(role)` 或 `build_action_system` |
| `tools` | `build_master_react_tools`（`delegate_*` 为 `kind: agent`） | `build_sub_agent_react_tools` / `build_action_tool` |
| `messages` | ReAct 历史（**pin_first_user** 保留首条真实用户输入）→ **末条 user** 含 `## 当前编排状态` JSON | `anchor_user`（任务简报）→ ReAct 历史 → **末条 user** 含编排状态或行动上下文 |

## 1.1 消息 Block Schema（canonical）

`core/llm/model/chat_message.py` 定义 prompt / 交互日志层统一格式：

```json
{
  "role": "assistant",
  "content": [
    {"type": "thinking", "thinking": "先委派剧本设计"},
    {"type": "tool_use", "id": "call_msg_xxx", "name": "delegate_script_design", "input": {}}
  ]
}
```

> **Thinking 模式（DeepSeek / Anthropic）**：tool call 多轮对话中，assistant 的 `thinking` block 必须原样回传 API；wire 层 `canonical_to_anthropic_messages` 保留 `thinking`（含可选 `signature`）；历史库中旧版 `text`+`tool_use` 会在 wire 时自动升为 `thinking`+`tool_use`。

**存储层四 Role**（`core/conversation/store.py`，对齐 Spring AI / OpenAI wire）：

| `MessageRole` | 附加字段 | 用途 |
|---------------|----------|------|
| `user` | `content: str` | 用户输入 |
| `assistant` | `content: str \| blocks`；`message_kind` | ReAct 轮（thinking+tool_use）、摘要（`summary`）、任务简报（`task_brief`，审计） |
| `tool` | `tool_call_id` + `content: str` | ReAct 观察结果 |
| `system` | — | 枚举保留；system prompt 仍在 `LlmRequest.system` |

**ReAct 一轮写入**：`ConversationStore.add_react_turn` → `assistant`（`[{thinking}, {tool_use}]`）+ `tool`（observation）。孤立观察（决策失败）→ `assistant` 纯文本 `[观察] …`。

**存储层 → canonical 映射**（`conversation_messages_to_chat_blocks`，近透传）：

| 存储 | Chat `role` |
|------|-------------|
| `user` | `user` |
| `assistant` + blocks/str | `assistant` |
| `tool` + `tool_call_id` | `tool` |
| `message_kind=task_brief` 且 `include_task=False` | 跳过 |

ReAct 一轮 canonical / wire：assistant（thinking + tool_use）→ `role: tool`（canonical）→ Anthropic `user` 内 `tool_result` block。孤立观察仍为 `assistant` 文本。

### 1.2 Anthropic Messages API wire 格式

`canonical_to_anthropic_messages` 转换规则：

| canonical | Anthropic wire |
|-----------|----------------|
| `assistant` + thinking + tool_use | `assistant`：`content` block 数组（保留 thinking / tool_use） |
| `assistant` + text + tool_use（历史） | wire 时首块 text 升为 `thinking`（兼容旧存储） |
| `tool` + `tool_call_id` | `user` 消息内 `{type: tool_result, tool_use_id, content}` |
| `assistant` + tool_result block（孤立） | 合并入下一条 `user` 的 `tool_result` |
| `user` | `user` + text blocks |
| `system` | **不进入 messages**（由 `LlmRequest.system` 顶层承载） |

**HTTP**：`POST {base_url}/v1/messages`；认证 `x-api-key` + `anthropic-version: 2023-06-01`。Provider 仅 **DeepSeek**（`https://api.deepseek.com/anthropic`）与 **Anthropic**。

**ReAct 决策与行动执行**：`LLMClient.complete_tool_calls(LlmRequest)` + `core/llm/prompt/tools/registry.py`；`tool_choice` 意图为 `{"type":"any"}`（ReAct）或 `{"type":"tool","name":action}`（单 action 强制）。**Thinking 模型**（如 `deepseek-reasoner` / `deepseek-v4-*`）在 `LLMClient` 层自动降为 `{"type":"auto"}`，避免 API 400；可通过 `SVG_LLM_THINKING_MODE` 或配置 `thinking_mode` 强制开关。

### 1.3 LlmRequest 与 ToolDefinition

`core/llm/model/llm_request.py`：

```json
{
  "system": "rules/react_tools.md + 角色 + 状态 JSON",
  "tools": [
    {
      "name": "delegate_script_design",
      "kind": "agent",
      "agent_name": "script_agent",
      "description": "委派子 Agent …",
      "input_schema": {"type": "object", "properties": {"note": {"type": "string"}}}
    }
  ],
  "messages": [{"role": "user", "content": [{"type": "text", "text": "…"}]}]
}
```

组装入口：`build_llm_request_ordered(...)` / `build_llm_request(...)`（[`chat_messages.py`](../core/llm/prompt/chat_messages.py)）。子 Agent：`decide_sub_agent` 将 `ctx.task_brief` 作为 `anchor_user`；行动执行将任务简报与 `action_context.txt` 动态槽位分离。行动参数字段见各 tool 的 `input_schema`（`core/llm/prompt/tools/schemas.py`），不再拼入 system。

## 2. 目录结构

```
core/llm/prompt/
├── builder.py              # PromptBuilder：组装 system / user
├── chat_messages.py        # ConversationMessage → Chat API 多轮历史
├── context_manager.py      # 每 Agent 动态槽位 Provider
├── context_window.py       # observation / 历史滑窗压缩（snippet 兜底）
├── history_compress.py     # 超 context_window 时 LLM 摘要较早对话
├── registry.py             # 加载 fixed 提示词、PromptProfile
├── loader.py
├── config.py
├── rules/
│   ├── react_tools.md      # 全局 ReAct tool_calls 协议
│   ├── action_tools.md     # 全局行动 function 协议（字段见 tools input_schema）
│   └── history_summary.md  # 较早对话 LLM 摘要 system prompt
├── tools/
│   ├── registry.py         # ToolDefinition 构建（主编排 / 子 Agent / 行动）
│   └── schemas.py          # 各 action 的 input_schema
├── templates/
│   ├── react_context.xml   # 子 Agent ReAct 动态 user 模板（历史命名，内容为 JSON 槽位）
│   └── action_context.txt  # 行动执行动态 user 模板
└── agents/{agent_name}/
    └── fixed/
        ├── role.default.md
        ├── role.dynamic_image.md   # 可选
        ├── role.ai_video.md        # 可选
        ├── agents_catalog.md       # 仅 super_video_master：子 Agent 职责/依赖/产出表
        ├── hint.{profile}.md       # 模式补充（拼入 action system）
        └── summary.md              # 仅 super_video_master
```

### 固定提示词分段格式（role.*.md）

每个 Agent 的 `role.{profile}.md` 采用统一 Markdown 结构：

- **Identity**：角色身份
- **Capabilities**：能做什么 / 不能做什么
- **Actions**：流水线 / ad_hoc / 只读行动
- **Constraints**：业务约束
- **Collaboration**：与主编排及其他 Agent 的协作关系

## 3. 两条 LLM 调用链

统一 **OpenAI tool_calls** 协议（`rules/react_tools.md` / `rules/action_tools.md`）。**`build_llm_request` 组装 `LlmRequest`，经 `wire.py` 转 HTTP 后由 `LLMClient.complete_tool_calls` 发送。**

### 3.1 ReAct 决策（选 action）

**主编排**（`decide_master_session`）：

```
request = build_llm_request(
  system_prompt = build_react_static_system(session.agent.description),
  tools         = build_master_react_tools(session.available_actions()),
  history       = build_master_react_chat_history(store),
  turn_user     = build_master_react_turn_user(session),  # ## 当前编排状态 JSON
)
LLMClient.complete_tool_calls(request)
```

**子 Agent**（`decide_sub_agent` → `decide_react`）：

```
request = build_llm_request_ordered(
  system_prompt = build_react_static_system(role),
  tools         = build_sub_agent_react_tools(agent, available_actions),
  anchor_user   = task_brief,
  history       = ...,
  turn_user     = build_react_state_turn_content(state_json),  # ## 当前编排状态 JSON
)
LLMClient.complete_tool_calls(request)
```

### 3.2 行动执行（function 参数落盘）

```
request = build_llm_request(
  system_prompt = build_action_system(agent, profile),
  tools         = [build_action_tool(agent, action)],
  history       = build_agent_react_chat_history(store, agent),
  turn_user     = build_action_user(slots),
  tool_choice   = tool_choice_force(action),
)
LLMClient.complete_tool_calls(request)
```

## 4. 动态槽位

| 槽位 | 来源 | 注入位置 | ReAct | Action |
|------|------|----------|-------|--------|
| `role_description` | `resolve_agent_prompts` | system（ReAct 角色段） | ✓ | ✓（user 内，行动链） |
| `task_brief` | 主编排委派 / 会话 | 末条 user 状态 JSON + 首条 user 锚点 | ✓ | ✓（首条 user 锚点） |
| `available_actions` | pipeline / session | **末条 user 状态 JSON**（已完成的一次性步骤已剔除） | ✓ | — |
| `next_actions` | `ReActSession.next_actions()` | **末条 user 状态 JSON**（主编排） | ✓ | — |
| `completed_actions` | 本对话已成功委派的 `ReActSession.completed_step_types` | **末条 user 状态 JSON** | ✓ | **末条 user 行动上下文** |
| `observations` | 会话 OBSERVATION | 末条 user 状态 JSON（无 history 时） | ✓ | 末条 user 行动上下文（无 history 时） |
| `history_summary` | `context_window` snippet 或 `history_compress` LLM 摘要 | 末条 user 状态 JSON / assistant 历史前缀 | ✓ | 末条 user 行动上下文 |
| `store_context` | MemoryStore 快照 | — | — | **末条 user 行动上下文** |
| `style_mode` / `iteration` | work_context | **末条 user 状态 JSON** | ✓ | — |
| `execution_plan` | 主编排 Plan 快照 | **末条 user 状态 JSON** | ✓ | — |
| `plan_status_history` | 主编排 LLM 回写 | **末条 user 状态 JSON** | ✓ | — |
| `last_remaining_plan` | 主编排 LLM 回写 | **末条 user 状态 JSON** | ✓ | — |
| `plan_slice` | `build_plan_slice_for_step` | **末条 user 状态 JSON**（子 Agent） | ✓ | — |
| `project_context` | `build_project_script_context` | **末条 user 状态 JSON** | ✓ | 末条 user 行动上下文 |
| `pipeline_progress` | Store 素材快照（`infer_completed_step_types` 等） | **末条 user 状态 JSON**（主编排） | ✓ | — |
| `user_resume_target` | `detect_resume_target_step` | **末条 user 状态 JSON**（主编排） | ✓ | — |
| `layer_summary` | `build_timeline_layer_summary()` | **load_edit_context / plan_edit_timeline / get_edit_timeline / validate_edit_assets** structured；compose_final 失败 observation | — | ✓（editing_agent） |

**editing_agent `layer_summary`**：每层 `id/name/z_index/clip_count/clips[]`（含 `start_ms/end_ms/asset_ref/transform/overlap_with_prev`）、`same_layer_overlaps[]`、`warnings`（全量）、`max_video_layers=5`。`compose_final` 失败时 observation 附加 `【图层摘要】` JSON；FFmpeg stderr 提取有效错误行（非 version 头）。首条 user 为任务简报锚点（或主编排真实用户输入）+ ReAct 多轮 thought/action/observation 历史；**末条 user** 注入 `## 当前编排状态` JSON 或 `## 当前行动上下文`（`turn_user`）。Token 压缩估算时将 static system + turn_user 合并计入。

每轮 ReAct tool_calls 的 arguments **必须**含 `plan_status` 与 `remaining_plan`（见 `react_tools.md` 与 `core/llm/tools/shared/input_common.py`）。

**只读 action schema**：`ToolKind.READ` 的 list/get 工具（如 `list_audio`、`list_images`、`get_plan`、`list_text_assets`）在 `core/llm/tools/shared/input_common.py` 中通过 `merge_plan_tracking(READ_ONLY_QUERY_SCHEMA)` 合并 plan 字段；`registry.call_tool` 校验与 LLM tool 定义一致，避免 LLM 按规则附带 plan 字段时被 `additionalProperties: false` 拒绝。

### 4.1 `plan_edit_timeline` 输出字段（editing_agent）

Schema 单源：[`core/llm/tools/editing/schemas.py`](../core/llm/tools/editing/schemas.py)、clip 子结构 [`edit_timeline_schema.py`](../core/llm/tools/shared/edit_timeline_schema.py)。

| 字段 | 类型 | 说明 |
|------|------|------|
| `video_layers[]` | 数组 | 优先；每层 `name`、`z_index`、`clips[]` |
| `video_layers[].clips[]` | clip | 含 `transform`（x/y/width/height）、`asset_ref`、`source_refs` |
| `tracks.video[]` | clip 数组 | **deprecated**；空 `video_layers` 时归一化进主画面层 |
| `tracks.audio` / `subtitle` | clip 数组 | 与旧版一致 |
| `mode` | string | `merge` / `replace`；用户已编辑时默认 merge |

主画面 `z_index=0`；画中画/贴纸放更高层并设置较小 `transform.width/height`。

### 4.2 `load_edit_context` 输出字段（editing_agent）

Schema：[`output_schemas.py`](../core/llm/tools/output_schemas.py) `load_edit_context_output_schema()`；载荷构建：[`editing/context.py`](../core/llm/tools/editing/context.py)。

| 字段 | 说明 |
|------|------|
| `action` | 固定 `load_edit_context`（输出 schema 必填，修复 generic_action 误校验） |
| `video_plan.shots[]` | 分镜镜头；含 `variant_refs`、`resolved.image_media_id` / `audio_media_id` 及 `*_accessible` |
| `media` | image/audio/video/final 分类型清单 |
| `assets_with_images` | 已链接图文资产摘要（与 storyboard load_context 共用 `linked_assets.py`） |
| `plots` | plot/narration 剧情段落 |
| `script.content_md` | 剧本正文摘要（截断） |
| `edit_timeline` | 已有剪辑时间轴 revision、user_edited、shot_gaps |

## 5. Profile 解析优先级

`core/llm/agent/prompt_resolver.py`：

1. 项目 `role_prompt` 覆盖（仅 role，hint 仍跟 profile）
2. 项目 `prompt_profile`
3. 全局 `agent_config.json` 的 profile
4. `VideoStyleMode` → `PromptProfile` 映射
5. `DEFAULT`

## 6. 扩展新 Agent  checklist

1. 在 `core/llm/tools/bootstrap.py` 注册 tool（`input_schema` 来自 `core/llm/prompt/tools/schemas.py`，`output_schema` 来自 `core/llm/tools/output_schemas.py` 或专用 builder）
2. 在 `core/llm/prompt/agents/{name}/fixed/role.default.md`（及 profile 变体）补充角色说明
3. 在对应域 `core/llm/tools/{domain}/schemas.py` 补充 action 的 `input_schema`（`schema_builders.py` 仍位于 prompt 层）
4. 在 `registry._AGENT_NAMES` 注册（若需出现在设置页 profile 列表）
5. 运行 `pytest tests/unit/test_agent_prompts.py tests/unit/test_tool_registry.py`

## 7. 相关代码入口

| 模块 | 职责 |
|------|------|
| [`core/llm/model/chat_message.py`](../core/llm/model/chat_message.py) | Content block 模型、Anthropic wire 适配 |
| [`core/llm/model/llm_request.py`](../core/llm/model/llm_request.py) | `LlmRequest` / `ToolDefinition` |
| [`core/llm/client/wire.py`](../core/llm/client/wire.py) | canonical ↔ Anthropic wire ↔ 日志 body |
| [`core/llm/tools/schemas.py`](../core/llm/tools/schemas.py) | 聚合各域 `*_SCHEMAS` + `action_input_schema` |
| [`core/llm/prompt/tools/schemas.py`](../core/llm/prompt/tools/schemas.py) | re-export（prompt 层兼容） |
| [`core/llm/tools/`](../core/llm/tools/) | MCP 语义 Tool Registry：`list_tools` / `call_tool` / `output_schema` 校验 |
| [`core/llm/prompt/builder.py`](../core/llm/prompt/builder.py) | 固定/动态组装 |
| [`core/llm/prompt/chat_messages.py`](../core/llm/prompt/chat_messages.py) | 多轮 Chat 历史构建 |
| [`core/llm/prompt/context_manager.py`](../core/llm/prompt/context_manager.py) | 动态槽位 |
| [`core/llm/agent/base.py`](../core/llm/agent/base.py) | 子 Agent ReAct / action 入口 |
| [`core/llm/react_decide.py`](../core/llm/react_decide.py) | 统一 tool_calls ReAct 决策（主编排 + 子 Agent） |
| [`core/llm/protocol.py`](../core/llm/protocol.py) | `parse_react_tool_calls`（`parse_react_json` 仅 legacy 测试） |
| [`core/llm/master/`](../core/llm/master/) | 主编排 ReActSession、actions、tools、`MasterReActEngine` |
| [`core/conversation/`](../core/conversation/) | 主/子 Agent 消息隔离 |

## 8. 变更记录

| 日期 | 变更 |
|------|------|
| 2026-06-29 | 只读 action schema（`READ_ONLY_QUERY_SCHEMA`、`list_text_assets`）经 `merge_plan_tracking` 声明 `plan_status`/`remaining_plan`，修复 `list_audio` 等只读 tool 执行校验失败 |
| 2026-07-05 | `tts_agent`：`synthesize` 由后端按 VideoPlan 合成 mp3，LLM 禁止编造 url；`extract_narration` 确定性读取 shots |
| 2026-07-04 | `parse_tool_arguments` 修复流式 tool input 内未转义引号（如 `"森林之王"`）及 `content` 嵌套 JSON 字符串；`ToolCallAccumulator` 完整 input 时忽略 delta |
| 2026-07-04 | 修复 Anthropic 流式 `tool_use`：`content_block_start` 含完整 `input` 时忽略后续 `input_json_delta`，避免 arguments 尾部重复 `}`；`parse_tool_arguments` 容错解析 |
| 2026-07-04 | 子 Agent `project_context` 注入 ReAct extra 与行动 `work_context_line`；`scan_text_assets` 专用 handler 修复 output schema；`data/projects/` 目录双写 |
| 2026-07-04 | `scan_text_assets` 结构化 JSON 载荷（`image/scan.py`）；新增 [`tools-reference.md`](tools-reference.md)；`build_llm_request_ordered` + `pin_first_user` 修复 messages 时间序（任务简报前置） |
| 2026-07-03 | Plan 模式：注入 `execution_plan` / `plan_slice`；LLM 回写 `plan_status` + `remaining_plan`；`plan_updated` WS 事件 |
| 2026-07-01 | `list_text_assets` 专用 input（`types`/`include_content`）与嵌套 output schema；observation 恢复完整 JSON；资产项含 `linked`/`counts_by_type` |
| 2026-07-01 | 引入 `core/tools/` MCP 语义 Registry（`list_tools`/`call_tool`）；各 tool 含 `output_schema` 运行时校验；`create_*` 强校验结构化 content；ReAct 决策阶段 write/ad_hoc 使用完整 `input_schema`；`tool_structured` 写入 agent_react_observation |
| 2026-06-29 | LLM wire 全面切换 Anthropic Messages API；仅保留 DeepSeek（`/anthropic`）与 Anthropic provider；`tool_choice` 为 `any`/`tool` |
| 2026-06-30 | 存储层 `MessageRole` 四值（user/assistant/system/tool）；ReAct 写入 `add_react_turn`；`message_kind` 区分 summary/task_brief；旧 JSON 经 `migrate.py` 升级 |
| 2026-06-29 | A2UI 内嵌聊天展示；`ask_user_question` OBSERVATION 含 `user_values` JSON；ACTION 持久化 JSON；委派 `task_brief` 优先 session 用户补充 |
| 2026-06-29 | `complete_tool_calls` 全量记录 response（content/tool_calls/finish_reason/usage）；缺 tool_calls 自动重试一次；思考流仅在 tool_calls 成功后推送 |
| 2026-07-06 | 主编排续跑：`pipeline_progress` 从 Store 推断已完成步骤；`user_resume_target` 识别「从剪辑合成继续」；勿无必要重跑 script_design |
| 2026-07-06 | `load_edit_context`：专用 output schema（修复 `action` 必填误校验）；载荷增 shots.resolved、plots、assets_with_images、script.content_md |
| 2026-07-06 | 多图层剪辑：`video_layers[]` + `EditClip.transform`/keyframes；`plan_edit_timeline` schema 增 `video_layers` 与 clip `transform`；FFmpeg `overlay` 多层导出；Edit Studio 多轨 UI + 多层预览 |
| 2026-07-06 | 占位符 tool_call 防护：`tool_call_guard` 检测 `$TOOL_NAME`/`$PARAMETER_NAME`；`react_decide` 纠正重试 1 次；`load_edit_context` 一次性完成；editing_agent hint 引导 plan_edit_timeline |
| 2026-07-06 | 剧本工作台人工 CRUD：`POST/DELETE .../scripts/{sid}/assets`、`PATCH .../scripts/{sid}`；`ScriptEditGuard` 仅 `executing` 禁止编辑；看板 `manualEditEnabled` 与 AI 执行中联动 |
| 2026-07-04 | Skill 单轮 `/skillId` 注入（`core/llm/prompt/skills/`）；`ExecutionMode.goal` 追加 `goal_mode.md`、禁用 ask_user 与全部 A2UI |
| 2026-07-04 | storyboard `create_shots`/`persist_plan` 输出 schema 修正；`asset_refs` 规范化；tool 失败不写入 completed_actions |
| 2026-07-04 | storyboard_agent：`load_context` 输出 schema（含 `action`）+ 观察 JSON 含剧本/plots/配图；禁用 `read_webpage`；`get_plan` 返回完整 shots JSON |
| 2026-06-30 | `update_*` action schema：顶层必填 `observation`+`asset_id`+`content`；content 为部分更新（`minProperties:1`，无全量 required）；`update_script` 仅必填 observation；只读 list/get 工具注册 schema |
| 2026-06-29 | 图文资产扩展视觉字段 + `image_prompt` 组装；script_agent create/update schema 必填 summary/description/prompt_hint/全部 traits；`PATCH /assets/{id}` |
| 2026-06-29 | 引入 `LlmRequest {system, tools, messages}`；tools 为 JSON Schema `{name, description, input_schema}`；`delegate_*` 为 `kind: agent`；删除 `fixed/actions.md`；日志分列 system/tools/messages |
| 2026-06-29 | 删除废弃 `rules/react_json.md`、`rules/action_json.md`（已由 `react_tools.md` / `action_tools.md` 替代） |
| 2026-06-29 | ReAct 全链路迁移 OpenAI tool_calls：`react_tools.md` / `action_tools.md`；`complete_tool_calls`；canonical tool_result→assistant；wire `role:tool` |
| 2026-06-29 | LLM 消息统一为 canonical block 格式（text/thinking/tool_use/tool_result）；`build_llm_messages` 产出 block 数组 |
| 2026-06-29 | 图文资产统一建模：`character/prop/scene` 共用 content 字段；`script_agent` 新增 `create_prop`；看板与 `ImageTextAssetCard` 统一展示 |
| 2026-07-05 | Thinking 模型 tool_choice 适配：`core/llm/client/tool_choice.py` 将 `any`/`tool` 降为 `auto`；`SVG_LLM_THINKING_MODE` 可强制开关 |
| 2026-07-05 | 生图失败：`ImageGenerationAbortError.failure_analysis` 含全部失败项；主编排 observation 结构化明细 + `role.default.md` 生图失败恢复；内容策略类失败重新开放 `delegate_script_design` |
| 2026-07-05 | 图文资产 **image_variants[]**：设定 base 主形象 + 表情/姿态/动作变体；reference 生图；分镜 `variant_refs`；看板变体列表 |
| 2026-06-29 | Edit Studio：capabilities 迁至 `core/edit/capabilities.json`；PATCH edit-timeline；FFmpeg 默认导出；editing_agent `plan_edit_timeline.mode` merge |
| 2026-07-06 | **编排状态末轮注入**：`## 当前编排状态` / 行动上下文迁至 messages 末条 user（`turn_user`）；system 仅静态协议+角色；`extract_react_state_json` 优先解析末条 user |
| 2026-07-07 | **空镜 + 绿幕抠图**：scene 生图 prompt 强制无人物空镜；character/prop 绿幕 `#00FF00` 生图 + `chroma_key.py` 抠透明 PNG；看板 scene 展示为「空镜」 |
| 2026-07-07 | **剪辑图层摘要**：`build_timeline_layer_summary` 注入 load/plan/get/validate；compose_final 失败附【图层摘要】；FFmpeg 同层重叠 preflight |
| 2026-07-07 | **新对话重新编排**：`completed_actions` 仅记录本对话委派；`pipeline_progress.inferred_completed_steps` 为 Store 快照，启动时不再写入 completed；新对话 goal 取 user_message |
| 2026-07-06 | **Remotion 移除**：成片仅 FFmpeg；`export` 配置区替代 `remotion`；全子 Agent `return_to_master`；主编排 `agents_catalog.md` + 动态 `next_actions`；`StepStatus.PAUSED` |
| 2026-07-05 | Remotion 直连（已废弃，2026-07-06 移除） |
| 2026-07-05 | 剪辑计划稿迁移至 `editing_agent`（TTS 后 `plan_edit_timeline`）；`EditClip` 扩展运镜/转场/背景/source_refs；`asset_resolver` 校验 + 主编排 `EditComposeMissingAssetsError` 缺失闭环 |
| 2026-07-05 | 剪辑时间轴 UI：`EditTimelineBoard` clip 改为 absolute 定位；`read_webpage` 收窄至 script_agent + 主编排，拒绝 localhost/内部 API |
| 2026-07-05 | 去重仅作用于一次性步骤（`delegate_*`、`parse_brief` 等）；`create_*`/update/read 可重复保留在 `available_actions` |
| 2026-07-04 | `available_actions` 与 `completed_actions` 去重：状态 JSON 与 tools 列表均剔除已完成项；主编排 `tool:` 标签映射为 `tool_*` |
| 2026-07-04 | 动态编排状态迁入 system（`## 当前编排状态`）；user 仅保留任务锚点与 ReAct 历史 |
| 2026-06-29 | 主编排 `available_actions` 会话层保留全量 delegate；`next_actions` 提示建议下一步；prompt 层现对已完成项去重 |
| 2026-06-28 | 主编排状态 JSON：completed_actions 统一为 delegate_* 名称；强化仅选 available_actions 的提示词 |
| 2026-06-27 | LLMClient 收敛为 `complete(messages)`；prompt 由 `build_llm_messages` 外层组装 |
| 2026-06-27 | 收敛 `core/llm`：统一 JSON ReAct（`react_decide.py`），删除 XML 遗留；主编排会话迁至 `super_video_master/session.py` |
| 2026-06-28 | 移除对话入口 LLM 意图门卫，用户消息直接进入主编排 ReAct |
| 2026-06-28 | 多轮对话：`Conversation` 实体 + `conversation_id` 隔离消息；持久化至 `dev_store.json`；工作台历史列表与唤醒 |
| 2026-06-24 | 引入 fixed/dynamic 分层、`PromptBuilder`、`AgentContextManager`；7 个 Agent 提示词重写为 Claude Code 分段格式 |
| 2026-06-25 | 修复 TextAsset content 验证错误：修改 script_agent actions.md 与 role.default.md 及全局 action_json.md，明确要求 content 必须为对象（dict），禁止字符串；LLM 现按规范返回对象，normalization 保留兜底 |
