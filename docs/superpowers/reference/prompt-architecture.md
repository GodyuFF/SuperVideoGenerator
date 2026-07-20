# 提示词架构（core/llm/prompt）

> 更新日期：2026-07-20（delegate_agent 独占混用：报错回写 observation 可恢复；提示词强化）

本文档描述 SuperVideoGenerator 中 Agent 提示词的 **固定区 / 动态区** 分层设计，参考 Claude Code 的 system prompt 组装模式。主编排末条 user 的 `## 当前编排状态` JSON **字段级组装逻辑**见 [orchestration-state.md](orchestration-state.md)。

## 1. 设计原则

| 概念 | Claude Code | 本项目 |
|------|-------------|--------|
| 固定区 | system prompt 中可缓存的静态段落 | `rules/*.md` + `agents/*/fixed/*.md` → **system** |
| 动态区 | 会话/环境/历史等运行时内容 | 模板槽位 + Store 快照 → **user** |
| 项目规则 | CLAUDE.md 注入对话 | 项目 `role_prompt` override（`prompt_resolver`） |
| 按需加载 | Skills / MCP | `PromptProfile` + **单轮 Skill**（`/skillId` → 内置目录 + `svg.skills` entry_points）；**MCP** 见 [extensions.md](extensions.md) |

**边界约定**：提示词在 `core/llm/prompt/` 组装为 canonical **`LlmRequest`**（`system` / `tools` / `messages` 同级）；wire 层经 `core/llm/client/wire.py` 映射为 **Anthropic Messages API**（`system` 顶层字段、`tools` 为 `{name, description, input_schema}`，**不发送** `output_schema`）；交互日志分列记录 `system`、`tools`、`messages`；Registry 执行结果的结构化载荷写入 ReAct 事件 `tool_structured`。

**Tool 单源**：`core/llm/tools/` 提供 MCP 语义 Registry（`list_tools` / `call_tool`），各 tool 含 `input_schema` + `output_schema`；`core/llm/prompt/tools/registry.py` 的 `build_sub_agent_react_tools` / `build_action_tool` 从 Registry 读取 schema；`core/llm/tools/shared/agent_tools.py` 的 `AGENT_TOOLS` 由 Registry 懒加载生成（兼容层）。

| 字段 | 主编排 | 子 Agent |
|------|--------|----------|
| `system` | `build_react_static_system`（协议 + 角色 + goal_mode） | `build_react_system(role)` 或 `build_action_system` |
| `tools` | `build_master_react_tools`（`delegate_agent` 为 `kind: agent`，`agent_id` enum 会话感知） | `build_sub_agent_react_tools` / `build_action_tool` |
| `messages` | ReAct 历史（**pin_first_user** 保留首条真实用户输入）→ **末条 user** 含 `## 当前编排状态` JSON | `anchor_user`（任务简报）→ ReAct 历史 → **末条 user** 含编排状态或行动上下文 |

## 1.1 消息 Block Schema（canonical）

`core/llm/model/chat_message.py` 定义 prompt / 交互日志层统一格式：

```json
{
  "role": "assistant",
  "content": [
    {"type": "thinking", "thinking": "先委派剧本设计"},
    {"type": "tool_use", "id": "call_msg_xxx", "name": "delegate_agent", "input": {"agent_id": "script_agent"}}
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

**ReAct 一轮写入**：单 tool 时 `ConversationStore.add_react_turn` → `assistant`（`[{thinking}, {tool_use}]`）+ `tool`（observation）；**同轮多 tool**（并行或顺序，见 `batch_mode`）时 `add_react_turn_batch` → `assistant`（`[{thinking}, {tool_use}×N]`）+ `N` 条 `tool`（各自 `tool_call_id` 配对）。独占 `finish` / `ask_user_question` / `delegate_agent` 不可与其他 tool 同轮混用；违反时抛 `ExclusiveToolBatchError`，主编排将报错写入孤立 observation（`[观察] 主编排决策失败：…`）并**继续下一轮**供模型纠正，不因此直接 FAILED。其他决策失败仍中止。

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

**HTTP（Anthropic 协议）**：`POST {base_url}/v1/messages`；认证 `x-api-key` + `anthropic-version: 2023-06-01`。Provider：**DeepSeek**（`https://api.deepseek.com/anthropic`）、**Anthropic**。

**HTTP（OpenAI 协议）**：`POST {base_url}/chat/completions`；认证 `Authorization: Bearer`。Provider：**OpenAI**、**OpenRouter**、**Moonshot**、**智谱**、**通义千问**（DashScope 兼容模式）。wire 实现：`core/llm/client/wire_openai.py`。

**ReAct 决策与行动执行**：`LLMClient.complete_tool_calls(LlmRequest)` + `core/llm/prompt/tools/registry.py`；`tool_choice` 意图为 `{"type":"any"}`（ReAct）或 `{"type":"tool","name":action}`（单 action 强制）。**Thinking 模型**（如 `deepseek-reasoner` / `deepseek-v4-*`）在 `LLMClient` 层自动降为 `{"type":"auto"}`，避免 API 400；可通过 `SVG_LLM_THINKING_MODE` 或配置 `thinking_mode` 强制开关。

### 1.3 LlmRequest 与 ToolDefinition

`core/llm/model/llm_request.py`：

```json
{
  "system": "rules/react_tools.md + 角色 + 状态 JSON",
  "tools": [
    {
      "name": "delegate_agent",
      "kind": "agent",
      "agent_name": "",
      "description": "委派子 Agent …（含 roster 内各 agent_id 职责摘要）",
      "input_schema": {"type": "object", "properties": {"agent_id": {"type": "string", "enum": ["script_agent"]}, "plan_status": {"type": "string"}}}
    }
  ],
  "messages": [{"role": "user", "content": [{"type": "text", "text": "…"}]}]
}
```

组装入口：`build_llm_request_ordered(...)` / `build_llm_request(...)`（[`chat_messages.py`](../../../core/llm/prompt/chat_messages.py)）。子 Agent：`decide_sub_agent` 将 `ctx.task_brief` 作为 `anchor_user`；行动执行将任务简报与 `action_context.txt` 动态槽位分离。行动参数字段见各 tool 的 `input_schema`（`core/llm/prompt/tools/schemas.py`），不再拼入 system。

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
        ├── role.storybook.md   # 可选
        ├── role.ai_video.md        # 可选
        ├── role.frame_i2v.md       # 可选（画面图生视频）
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
| `completed_actions` | 本对话已成功委派的步骤；**新对话启动时**由 `seed_completed_steps_for_message` 将 Store `inferred_completed_steps` 写入（明确「全部重做」或 `detect_reopen_steps` 命中的步骤及下游除外） | **末条 user 状态 JSON** | ✓ | **末条 user 行动上下文** |
| `observations` | 会话 OBSERVATION | 末条 user 状态 JSON（无 history 时） | ✓ | 末条 user 行动上下文（无 history 时） |
| `history_summary` | 超 `context_window_tokens` 时 `history_compress` LLM 摘要（失败回退 `fit_chat_history` snippet）；未超窗保留完整历史 | 末条 user 状态 JSON / assistant 历史前缀 | ✓ | 末条 user 行动上下文 |
| `store_context` | MemoryStore 快照 | — | — | **末条 user 行动上下文** |
| `style_mode` / `iteration` | work_context | **末条 user 状态 JSON** | ✓ | — |
| `style_hints` | `Script.style_hints`（可选提示词：图片风格/预计时长，随风格锁定；未选择不注入） | **末条 user 状态 JSON**（master extra）/ project_context | ✓ | 末条 user 行动上下文（work_context_line） |
| `execution_plan` | 主编排 Plan 快照 | **末条 user 状态 JSON** | ✓ | — |
| `plan_status_history` | 主编排 LLM 回写 | **末条 user 状态 JSON** | ✓ | — |
| `last_remaining_plan` | 主编排 LLM 回写 | **末条 user 状态 JSON** | ✓ | — |
| `plan_slice` | `build_plan_slice_for_step` | **末条 user 状态 JSON**（子 Agent） | ✓ | — |
| `project_context` | `build_project_script_context` | **末条 user 状态 JSON** | ✓ | 末条 user 行动上下文 |
| `pipeline_progress` | Store 素材快照（`infer_completed_step_types`、`eligible_delegates` 等） | **末条 user 状态 JSON**（主编排） | ✓ | — |
| `sub_agents` | `build_sub_agents_orchestration_state`（agent_id、职责、ready/available/blockers） | **末条 user 状态 JSON**（主编排） | ✓ | — |
| `available_sub_agents` | 本轮可委派 agent_id 列表（与 `delegate_agent` tool enum 一致） | **末条 user 状态 JSON**（主编排） | ✓ | — |
| `delegate_readiness` | `resolve_delegate_readiness`（每 agent_id 的 ready/soft/hard blockers + step_type） | **末条 user 状态 JSON**（主编排） | ✓ | — |
| `user_resume_target` | `detect_resume_target_step` | **末条 user 状态 JSON**（主编排） | ✓ | — |
| `layer_summary` | `build_timeline_layer_summary()` | **load_edit_context / plan_edit_timeline / get_edit_timeline / validate_edit_assets** structured；compose_final 失败 observation | — | ✓（editing_agent） |

**editing_agent `layer_summary`**：每层 `id/name/z_index/clip_count/clips[]`（含 `start_ms/end_ms/asset_ref/transform/overlap_with_prev`）、`same_layer_overlaps[]`、`warnings`（全量）、`max_video_layers=5`。`compose_final` 失败时 observation 附加 `【图层摘要】` JSON；FFmpeg stderr 提取有效错误行（非 version 头）。首条 user 为任务简报锚点（或主编排真实用户输入）+ ReAct 多轮 thought/action/observation 历史；**末条 user** 注入 `## 当前编排状态` JSON 或 `## 当前行动上下文`（`turn_user`）。Token 压缩估算时将 static system + turn_user 合并计入。

**历史压缩与 tool 配对**（[`chat_messages.py`](../../../core/llm/prompt/chat_messages.py) / [`history_compress.py`](../../../core/llm/prompt/history_compress.py)）：

- **压缩触发**：`estimate_request_over_window` 仅比较 `prompt_estimated_tokens`（system + tools + messages）与 `context_window_tokens`（默认 1M）；未超窗时 `prepare_react_chat_history` 保留完整历史。
- **超窗路径**：`maybe_compress_chat_history` 对较早消息 LLM 摘要；失败回退 `fit_chat_history` snippet 滑窗。
- `_split_for_compression` 以 **ReAct 轮次**（`assistant+tool_use` 与后续 `tool` 消息）为最小切分单位，避免拆开 tool 对。
- `_with_summary_prefix` 将摘要**合并进首条 user**（不再插入 `assistant(摘要)`），避免阻断 tool 配对。
- 压缩出口调用 `repair_tool_message_pairs`：孤立 `tool` / 无结果的 `tool_use` / **user 内嵌** orphan `tool_result` / 多 `tool_use` 部分配对轮次 → 降级为 `[观察]` / `[行动]` 纯文本。
- `build_llm_request_ordered` 返回前对 `messages` 调用 `repair_tool_message_pairs`（组装层双保险）。
- `canonical_to_anthropic_messages` 对 user 内嵌 `tool_result`/`tool_use` 降级；末尾 `validate_wire_tool_pairs` 做 wire 最终校验。

每轮 ReAct tool_calls 的 arguments **必须**含 `plan_status` 与 `remaining_plan`（见 `react_tools.md` 与 `core/llm/tools/shared/input_common.py`）。

**只读 action schema**：`ToolKind.READ` 的 list/get 工具（如 `list_audio`、`list_images`、`get_plan`、`list_text_assets`）在 `core/llm/tools/shared/input_common.py` 中通过 `merge_plan_tracking(READ_ONLY_QUERY_SCHEMA)` 合并 plan 字段；`registry.call_tool` 校验与 LLM tool 定义一致，避免 LLM 按规则附带 plan 字段时被 `additionalProperties: false` 拒绝。

### 4.1 `plan_edit_timeline` 输出字段（editing_agent）

Schema 单源：[`core/llm/tools/editing/schemas.py`](../../../core/llm/tools/editing/schemas.py)、clip 子结构 [`edit_timeline_schema.py`](../../../core/llm/tools/shared/edit_timeline_schema.py)。

| 字段 | 类型 | 说明 |
|------|------|------|
| `video_layers[]` | 数组 | 视频 clip 单源；每层 `name`、`z_index`、`clips[]` |
| `video_layers[].clips[]` | clip | 含 `transform`（x/y/width/height）、`asset_ref`、`source_refs` |
| `tracks.audio` / `subtitle` | clip 数组 | 配音与字幕轨 |
| `mode` | string | `merge` / `replace`；用户已编辑时默认 merge |

主画面 `z_index=0`；画中画/贴纸放更高层并设置较小 `transform.width/height`。

### 4.2 `load_edit_context` 输出字段（editing_agent）

Schema：[`output_schemas.py`](../../../core/llm/tools/output_schemas.py) `load_edit_context_output_schema()`；载荷构建：[`editing/context.py`](../../../core/llm/tools/editing/context.py)。

| 字段 | 说明 |
|------|------|
| `action` | 固定 `load_edit_context`（输出 schema 必填，修复 generic_action 误校验） |
| `video_plan.shots[]` | 分镜镜头；含 `variant_refs`、`resolved.image_media_id` / `audio_media_id` 及 `*_accessible` |
| `media` | image/audio/video/final 分类型清单 |
| `assets_with_images` | 已链接图文资产摘要（与 storyboard load_context 共用 `linked_assets.py`） |
| `plots` | plot/narration 剧情段落 |
| `script.content_md` | 剧本正文摘要（截断） |
| `edit_timeline` | 已有剪辑时间轴 revision、user_edited、shot_gaps |
| `subtitle_style_context` | `output_canvas` + `subtitle_style`（按分辨率推荐字号/底边距/底中对齐）+ `common_presets`；见 [`subtitle_style.py`](../../../core/edit/subtitle_style.py) |

### 4.3 空镜（scene）三层约束

**定义**：`scene` = 空镜背景板（establishing plate / matte backdrop），仅作 frame 图生图首参考图；不承载叙事、不含人物/动物/独立道具主体。

| 层级 | 位置 | 作用 |
|------|------|------|
| Agent 填表 | `script_agent` `role.default.md` / `role.storybook.md` + `image_agent` 故事书提示词 | 禁止人物/情节/可携带道具写入 `create_scene` content |
| Schema 描述 | `build_scene_content_schema()`（`schema_builders.py`） | `description` / `key_objects` / `foreground` 字段描述强调背景板语义 |
| 组装生图 | `core/assets/image_prompt.py`（`PROMPT_VERSION=2`） | positive 前缀 `environment background plate…`；扩展 `_SCENE_NEGATIVE`；`key_objects` trait 标注「非 prop 资产」 |

**允许**：空间结构、光线、天气、材质、色调、环境固定陈设。**禁止**：人物/动物、可识别独立道具主体、情节动作、「行人/观众」类描写。可携带物品须 `create_prop`。

### 4.4 分镜子镜 schema（storyboard Agent）

Schema 单源：[`schema_builders.py`](../../../core/llm/prompt/tools/schema_builders.py) `build_sub_shot_schema()` / `build_sub_shot_image_schema()`；解析与缺省回填：[`sub_shot_produce.py`](../../../core/edit/sub_shot_produce.py)。

| 字段 | 写入方 | 说明 |
|------|--------|------|
| `sub_shots[].produce_mode` | `create_shots` / `review_shot` patch | `still` \| `text2video` \| `img2video`；故事书默认静图视频 |
| `sub_shots[].produce_rationale` | 同上 | 可选短理由 |
| `sub_shots[].images[].start_ms` / `end_ms` | 同上 | 画面占用时段（相对镜起点）；省略则等于所属子镜区间 |
| `sub_shots[].start_ms` / `end_ms` | 同上 | 子镜时段（相对镜起点） |

**Agent 推断启发**（`storyboard_agent` / `storyboard_refine_agent` 固定区）：静图+运镜 → `still`；无参考图文生 → `text2video`；有画面图生 → `img2video`。`video_agent` / `editing_agent` 优先读 `produce_mode` 再执行生视频或静图轨规划。

## 5. Profile 解析优先级

`core/llm/agent/prompt_resolver.py` + `core/llm/prompt/profile_registry.py`：

1. 项目 `role_prompt` 覆盖（仅 role，hint 仍跟 profile）
2. 项目 `prompt_profile`
3. 全局 `data/agents/registry.json` 的 `prompt_profiles[agent]`
4. `StyleModeRegistry.default_prompt_profile_for_style(style_id)`（内置 + 自定义 `style_modes`）
5. `DEFAULT`

**正文覆盖**：`data/agents/profiles/{profile_id}/workspace.json` → `prompt_content[agent].role_prompt|action_hint` 优先于磁盘 `fixed/*.md`（API 聚合视图仍为 `prompt_content[agent][profile_id]`）；保存后 `clear_prompt_cache()` 清 LRU，并通过 `AppState.reload_agent_config()` 同步运行时。

**自定义 Profile**：`registry.json` → `custom_profiles[]`（`id`、`label`、`based_on`）合并进 `PromptProfileRegistry.list_all_profiles()`；新建时从 `default` 工作区复制；`default` **不可编辑、不可删除**（仅使用磁盘 `fixed/*.md` 基线）；自定义 Profile 可编辑/删除；磁盘读取按 `based_on` 回退链。

**风格 ↔ Profile 1:1**：自定义 `style_modes[].id` 必须等于 `default_prompt_profile` 与同名 `custom_profiles[].id`；`config_manager._load()` 与 PATCH 前经 [`style_profile_sync.py`](../../../core/llm/agent/style_profile_sync.py) 自动补齐/修正，并移除已下线风格（`dynamic_comic`、`marketing_video`、`marketing`）；`list_all_profiles()` 显示名优先取自 `StyleModeRegistry`。

**内置风格 seed / 恢复**：三种内置视频风格（`storybook` / `ai_video` / `frame_i2v`）出厂配置固化于 [`core/llm/agent/seeds/profiles/`](../../../core/llm/agent/seeds/profiles/)（全量 8 Agent roster、空 `prompt_content`/`tool_overrides`）；`POST /api/agents/profiles/{profile_id}/restore` 与 `POST /api/agents/config/restore-builtin-profiles` 用 seed 覆盖工作区并清理聚合覆盖；内置风格 Profile **不可删除**、**可恢复**；自定义风格仅可删除、不可 restore。

**画面图生视频（frame_i2v）**：分镜同时 `create_frames` + `create_video_clips`；`video_agent` 经 [`frame_i2v_spec.py`](../../../core/llm/tools/video/frame_i2v_spec.py) 以子镜 frame 为唯一 I2V 图生源（2+ frame → keyframes；1 frame → img2video；无 frame → text2video）；`video_clip` 仅提供 motion prompt，禁止以其 content 内嵌参考图作 I2V 输入。

**工具过滤**：`tool_overrides[agent].exclude` 或 `include_only`（exclude 优先）；子 Agent 在 Skill filter 之后、`ReActAgent.decide` 内生效；主编排仅过滤 `tool_*`（`apply_master_tool_overrides`）。始终保留 `finish`、`ask_user_question`、`return_to_master`。

## 6. 扩展新 Agent  checklist

1. 在 `core/llm/tools/bootstrap.py` 注册 tool（`input_schema` 来自 `core/llm/prompt/tools/schemas.py`，`output_schema` 来自 `core/llm/tools/output_schemas.py` 或专用 builder）
2. 在 `core/llm/prompt/agents/{name}/fixed/role.default.md`（及 profile 变体）补充角色说明
3. 在对应域 `core/llm/tools/{domain}/schemas.py` 补充 action 的 `input_schema`（`schema_builders.py` 仍位于 prompt 层）
4. 在 `registry._AGENT_NAMES` 注册（若需出现在设置页 profile 列表）
5. 运行 `pytest tests/unit/test_agent_prompts.py tests/unit/test_tool_registry.py`

## 7. 相关代码入口

| 模块 | 职责 |
|------|------|
| [`core/llm/model/chat_message.py`](../../../core/llm/model/chat_message.py) | Content block 模型、Anthropic wire 适配 |
| [`core/llm/model/llm_request.py`](../../../core/llm/model/llm_request.py) | `LlmRequest` / `ToolDefinition` |
| [`core/llm/client/wire.py`](../../../core/llm/client/wire.py) | canonical ↔ Anthropic wire ↔ 日志 body |
| [`core/llm/tools/schemas.py`](../../../core/llm/tools/schemas.py) | 聚合各域 `*_SCHEMAS` + `action_input_schema` |
| [`core/llm/prompt/tools/schemas.py`](../../../core/llm/prompt/tools/schemas.py) | re-export（prompt 层兼容） |
| [`core/llm/tools/`](../../../core/llm/tools/) | MCP 语义 Tool Registry：`list_tools` / `call_tool` / `output_schema` 校验 |
| [`core/llm/prompt/builder.py`](../../../core/llm/prompt/builder.py) | 固定/动态组装 |
| [`core/llm/prompt/chat_messages.py`](../../../core/llm/prompt/chat_messages.py) | 多轮 Chat 历史构建 |
| [`core/llm/prompt/context_manager.py`](../../../core/llm/prompt/context_manager.py) | 动态槽位 |
| [`core/llm/agent/base.py`](../../../core/llm/agent/base.py) | 子 Agent ReAct / action 入口 |
| [`core/llm/react_decide.py`](../../../core/llm/react_decide.py) | 统一 tool_calls ReAct 决策（主编排 + 子 Agent） |
| [`core/llm/protocol.py`](../../../core/llm/protocol.py) | `parse_react_tool_calls` / `parse_react_tool_calls_batch` |
| [`core/llm/tool_call_batch.py`](../../../core/llm/tool_call_batch.py) | 同轮多 tool 独占校验、并行/顺序分流、上限、`merge_batch_observations` |
| [`core/llm/master/`](../../../core/llm/master/) | 主编排 ReActSession、actions、tools、`MasterReActEngine` |
| [`core/conversation/`](../../../core/conversation/) | 主/子 Agent 消息隔离 |

## 8. 变更记录

| 日期 | 变更 |
|------|------|
| 2026-07-14 | **关联资产动态提示词**：生图 `resolve_frame_generation_prompt` / 生视频 `compose_video_clip_prompt` 在最终请求中拼接 `【关联资产上下文】`（`linked_assets_prompt.py`），辅助模型理解角色/空镜/物品；不覆盖用户主提示词 |
| 2026-07-20 | **实际生成提示词预览**：`GET .../assets/{id}/resolved-prompt`（`core/assets/resolved_prompt.py`）与生图/生视频路径一致；详情页提示词旁小眼睛弹层展示 |
| 2026-07-14 | **frame / video_clip 字段收敛**：`create_frames` 必填 `image_prompt`+`element_refs`（可选 `summary`/`notes`）；`create_video_clips` 必填 `video_prompt`+`element_refs`；工作台草稿与 `compose_frame_image_prompt` 以 `image_prompt` 为主；`notes` 不进提示词 |
| 2026-07-14 | **子镜产出意图 + 画面时段**：`build_sub_shot_schema` 增 `produce_mode`/`produce_rationale`；`images[]` 增 `start_ms`/`end_ms`；`create_shots`/`review_shot` 写入；`llm_action` + `sub_shot_produce` 回填与校验 |
| 2026-07-14 | **产出意图三值收敛**：`produce_mode` 改为 `still`/`text2video`/`img2video`（静图视频/文生/图生）；字幕生成强制非重叠；子镜挂接 UI 对齐剧本画面 Tab |
| 2026-07-13 | 配音幕说话人：`voice_speakers` 上下文；create_shots voice clip `character_ref` 旁白留空/对白填 txt_*；校验与 storyboard prompt 规则 |
| 2026-07-13 | 新增 `video_clip` 文字资产：`create_video_clips` / `scan_video_clips` / `generate_video_clips`；content 含 `video_prompt`、`tags`、`element_refs`、`media_refs` |
| 2026-07-13 | `load_edit_context` 增 `subtitle_style_context`（按成片分辨率推荐字幕字号/底边距/底中对齐）；`edit_capabilities.md` 字幕样式表；OpenCut `subtitleClipToTextElement` 修复居中大字 |
| 2026-07-11 | 风格 ↔ Profile 1:1 强制同步（`style_profile_sync.py`）；内置三风格 seed（`core/llm/agent/seeds/profiles/`）与 restore API；内置风格不可删、可恢复系统默认 |
| 2026-07-05 | `tts_agent`：`synthesize` 由后端按 VideoPlan 合成 mp3，LLM 禁止编造 url；`extract_narration` 确定性读取 shots |
| 2026-07-04 | `parse_tool_arguments` 修复流式 tool input 内未转义引号（如 `"森林之王"`）及 `content` 嵌套 JSON 字符串；`ToolCallAccumulator` 完整 input 时忽略 delta |
| 2026-07-04 | 修复 Anthropic 流式 `tool_use`：`content_block_start` 含完整 `input` 时忽略后续 `input_json_delta`，避免 arguments 尾部重复 `}`；`parse_tool_arguments` 容错解析 |
| 2026-07-04 | 子 Agent `project_context` 注入 ReAct extra 与行动 `work_context_line`；`scan_text_assets` 专用 handler 修复 output schema；`data/projects/` 目录双写 |
| 2026-07-04 | `scan_text_assets` 结构化 JSON 载荷（`image/scan.py`）；新增 [`tools-reference.md`](tools-reference.md)；`build_llm_request_ordered` + `pin_first_user` 修复 messages 时间序（任务简报前置） |
| 2026-07-03 | Plan 模式：注入 `execution_plan` / `plan_slice`；LLM 回写 `plan_status` + `remaining_plan`；`plan_updated` WS 事件 |
| 2026-07-01 | `list_text_assets` 专用 input（`types`/`include_content`）与嵌套 output schema；observation 恢复完整 JSON；资产项含 `linked`/`counts_by_type` |
| 2026-07-01 | 引入 `core/tools/` MCP 语义 Registry（`list_tools`/`call_tool`）；各 tool 含 `output_schema` 运行时校验；`create_*` 强校验结构化 content；ReAct 决策阶段 write/ad_hoc 使用完整 `input_schema`；`tool_structured` 写入 agent_react_observation |
| 2026-07-20 | LLM 双 wire：Anthropic Messages + OpenAI Chat Completions；新增 openai/openrouter/moonshot/zhipu/dashscope provider |
| 2026-07-20 | 生图扩充 openai/fal/gemini；生视频扩充 kling/runway/fal；Provider 能力矩阵与 fallback 降级链 |
| 2026-07-10 | 移除历史兼容：`tracks.video` 双写、`parse_react_json`、7-role 会话 migrate、text→thinking wire 自动升级；时间轴单源 `video_layers` |
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
| 2026-07-12 | **子镜 Agent/Tools 升级**：`visuals` → `sub_shots`；`build_sub_shot_schema`（`images[]`/`videos[]`）；`create_frames.sub_shot_id` 必填；persist 校验每子镜 frame；`get_shot_details` 输出 `image_gap_sub_shots` |
| 2026-07-13 | **单镜复核 + 384K 输出**：新增 `review_shot`（镜维度增量 patch）；`max_tokens` 上限 393216；`storyboard_refine_agent` 流水线改为逐镜 `review_shot`；跨镜仍用 `review_and_restructure` |
| 2026-07-20 | **delegate_agent 独占混用可恢复**：`ExclusiveToolBatchError`；主编排将「不可与其他 tool 同轮调用」写回 observation 并继续；`react_tools.md` / master role / `MASTER_STATE_INSTRUCTIONS` / `delegate_agent` description 强化独占约束 |
| 2026-07-20 | **画面图生视频（frame_i2v）**：第三种内置风格；`role.frame_i2v.md` / `hint.frame_i2v.md`；分镜 create_frames + create_video_clips；`frame_i2v_spec.py` I2V 只认 frame |
| 2026-07-20 | **分镜子镜定位修复**：`create_frames`/`create_video_clips` 支持仅用 `sub_shot_id` 全局反查；空槽 upsert；observation 回传 `frame_links`/`video_clip_links`；`create_video_clips` 自动绑 `source_frame_asset_id`；`get_plan`/`serialize_shots_for_agent` 暴露资产映射 |
| 2026-07-13 | **下线动态漫画/营销视频 AI**：保留 `storybook` / `ai_video` / `frame_i2v` 内置风格；`style_profile_sync` 移除 `dynamic_comic`/`marketing_*`；历史 id 迁移为 `storybook` |
| 2026-07-13 | **Agent 职责边界**：script_agent 仅 plot/character/scene/prop；storyboard_agent 负责 element_refs + create_frames/create_video_clips；video_agent 仅 scan/generate_video_clips；按 style_mode 过滤分镜/视频 pipeline |
| 2026-07-13 | **ReAct 同轮多 tool 并行**：`parse_react_tool_calls_batch` + `validate_tool_call_batch`；子 Agent / 主编排 `asyncio.gather` 并行 act；`add_react_turn_batch` 落盘；WS `agent_react_action_batch` / `react_action_batch`；默认上限 `SVG_REACT_MAX_PARALLEL_TOOLS=16` |
| 2026-07-14 | **同轮多 tool 顺序分流**：非并行白名单组合改为 `batch_mode=sequential` 按序执行；仅 `finish` / `ask_user_question` / `delegate_agent` 独占仍拒绝混用 |
| 2026-07-13 | **分镜配音幕强制**：`role.storybook` 写明 `audio_tracks[kind=voice].clips[].text` 必填；ReAct `build_react_static_system` 合并 action_hint；`create_shots` schema 强制 voice；`validate_shots_voice_content` + `_tts_complete` 修正 |
| 2026-07-12 | **镜内多轨 Shot**：`create_shots` schema 改为 `sub_shots` + `audio_tracks` + `subtitles`；移除 `shot_plan`/`shot_detail`/`narration_text` 提示词；TTS 从 voice clip `text` 提取 |
| 2026-07-10 | **分镜复核旧别名清理**：Registry 仅暴露 7 个 canonical tool；`execute_action` 对 `load_review_context` 等废弃名运行时重定向到 `get_shot_details` 等，避免旧对话触发 `action` required 校验失败 |
| 2026-07-10 | **分镜复核查询拆分**：新增 read tool `get_shot_details` / `get_shot_asset_timing`（音频含 `text_segments`）；hint/role 引导先查询再 sync |
| 2026-07-10 | **分镜复核 Tool Schema**：7 个 refine tool 统一 `plan_tracking` 入参；`review_and_restructure` 专用 `shot_refine_mutation` 输出；`persist_review` 用 `shot_persist`；handler 层 preflight（无效 `shot_id` → `ok=false` 不写 store） |
| 2026-07-10 | **分镜复核 Registry 热重载**：`ReActAgent._tool_registry` 改为 property；API startup 调用 `reset_tool_registry()`，避免旧 output_schema 缓存导致 `action` required |
| 2026-07-10 | **剪辑时间段详情**：`analyze_edit_timeline` 的 `clips_in_range` 含完整 clip 字段与 `resolved` 素材；新增 `include_analysis`；剪辑 Agent prompt 引导按时间窗查询 |
| 2026-07-10 | **ReAct 思考流式**：`complete_tool_calls` SSE 循环内实时 `on_delta`（thinking + content），经 WS `llm_stream_*` 推送至 Workbench |
| 2026-07-10 | **ShotDetailSpec schema**：`build_video_plan_shot_schema` 移除 `shot_detail` 悬空 `$ref`；`shot_detail` 仅由 TTS 同步与 `storyboard_refine_agent` 填写 |
| 2026-07-10 | **tool 配对补强**：摘要合并 user、user 内嵌 tool_result 净化、`validate_wire_tool_pairs`、`build_llm_request_ordered` 双保险 |
| 2026-07-10 | **历史压缩 tool 配对**：`group_react_turns` 轮次原子切分；`repair_tool_message_pairs` 孤立 tool 降级为观察文本；wire 层兜底避免 Anthropic `tool_result` 校验错误 |
| 2026-07-11 | **统一委派工具**：7 个 `delegate_*` 合并为 `delegate_agent(agent_id)`；`delegate_tool.py` 动态 description/schema enum；`completed_actions` 以 `step:*` 记录；`return_to_master.suggested_agent_ids`；删除 `ACTION_TO_STEP` |
| 2026-07-10 | **分镜三步骤 + 复核**：`storyboard_agent` 必填 `shot_plan` 精确时间轴；`planned_synthesis` 约束 TTS；`storyboard_refine_agent` 升级为复核流水线（`review_and_restructure` 支持拆分/合并镜头）；`delegate_shot_detail` 软依赖 `image_gen` |
| 2026-07-09 | **TTS 后分镜详设**：新增 `storyboard_refine_agent`（`core/llm/prompt/agents/storyboard_refine_agent/fixed/`）；主编排 `delegate_shot_detail`；`pipeline_progress` 要求 `shot_detail` 完成后方可 `edit_compose` |
| 2026-07-09 | **剪辑 Tab 性能 + 画面看板**：OpenCut Core 懒加载；EditorStudioModal Portal；frame Tab 接线；分镜 `frame_preview_url`；WS `svg:ws-event` + delta throttle；主编排 canonical 顺序 script→storyboard→image→tts→**shot_detail**→edit |
| 2026-07-07 | **空镜 + 绿幕抠图**：scene 生图 prompt 强制无人物空镜；character/prop 绿幕 `#00FF00` 生图 + `chroma_key.py` 抠透明 PNG；看板 scene 展示为「空镜」 |
| 2026-07-07 | **空镜背景板语义强化**：scene = establishing plate / matte backdrop；script/image Agent 提示词 + `build_scene_content_schema` + `image_prompt.py`（`PROMPT_VERSION=2`）三层约束；`key_objects` 仅环境固定陈设 |
| 2026-07-07 | **剪辑图层摘要**：`build_timeline_layer_summary` 注入 load/plan/get/validate；compose_final 失败附【图层摘要】；FFmpeg 同层重叠 preflight |
| 2026-07-16 | **编排状态组装专文**：新增 [orchestration-state.md](orchestration-state.md)，说明 `## 当前编排状态` JSON 的注入形态、seed/progress/readiness/`sub_agents` 组装流水线与字段来源 |
| 2026-07-16 | **完整成片 canonical 顺序**：主编排 `role.default.md` / `agents_catalog.md` 写明 `storyboard_refine_agent` 为剪辑前最后一步；AI 视频 `video_agent`→`tts`→`refine`→`editing`；`delegate_deps` 在 ai_video 下对 `shot_detail` 软依赖 `video_gen`；去掉「顺序不限」 |
| 2026-07-16 | storyboard_agent `load_context`：**必传 `script_id`**（schema + handler 校验须与会话一致）；去掉 hint「勿传 script_id」 |
| 2026-07-14 | **新对话复用 Store 完成态**：`seed_completed_steps_for_message` 启动时写入 `completed_actions`；「全部重做」清空；仅明确重做/续跑（`detect_reopen_steps`，如「重新配音」「从剪辑继续」）剔除该步及下游；普通提及「旁白」等不误伤 |
| 2026-07-07 | **新对话重新编排**（已由 2026-07-14 覆盖）：曾改为启动不 seed completed；现改回默认复用 Store；goal 仍取 user_message |
| 2026-07-07 | **Windows 字幕导出 + 编排修复**：ASS 路径转义/drawtext 回退；`validate_edit_assets` 专用 output schema；`plan_edit_timeline.skip_subtitle_enrich`；`pipeline_progress` frame 缺图时不推断 image_gen 完成；LLM 日志区分 estimated/actual completion tokens |
| 2026-07-07 | **ASS 路径修复 + skip_subtitles**：Windows 去掉滤镜路径单引号（修复 FFmpeg 解析失败）；`compose_final.skip_subtitles` 跳过字幕回填与烧录 |
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
