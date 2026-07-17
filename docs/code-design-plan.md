# SuperVideoGenerator 代码设计计划

> 版本：v0.1 | 对应产品手册 v0.1 | 更新：2026-07-17（桌面安装包打包与发版）

## 1. 目标

在 `docs/product-plan.md` 基础上落地可运行代码骨架，具备：

- ReAct 主编排（超级视频大师 + 子 Agent）
- 分阶段结构化日志
- **A2UI** 不确定信息前端确认（WebSocket 推送表单 → 用户响应）
- **Token 预估**：LLM 调用前按 system/tools/messages + `max_tokens` 分项预估与占比，写入交互日志；超 `context_window_tokens` 时对较早对话 LLM 摘要压缩
- `tests/` 目录可独立验证核心逻辑与 API

## 2. 仓库结构

```
SuperVideoGenerator/
├── core/                       # 领域与编排（无 HTTP 依赖）
│   ├── models/                 # 领域实体（entities、image_text_asset）
│   ├── logging/                # 分阶段日志
│   ├── guards/                 # ReferenceGuard, ScriptEditGuard
│   ├── events/                 # 事件类型与 EventEmitter
│   ├── store/                  # 内存/SQLite 仓储
│   ├── super_video_master/     # 薄入口：run_from_message、summary
│   ├── conversation/           # 主/子 Agent 会话隔离
│   ├── assets/                 # 图文资产 PATCH、image_prompt
│   ├── board/                  # 看板构建
│   └── llm/                    # LLM 编排、提示词、工具、A2UI
│       ├── client/             # HTTP 客户端、wire、settings、tokens
│       ├── master/             # 主编排：session、actions、tools、master_react
│       ├── model/              # LlmRequest、ChatMessage、ReAct 协议模型
│       ├── prompt/             # Agent 提示词（fixed/dynamic 分层）
│       ├── agent/              # 子 Agent（ReAct 决策与执行）
│       ├── a2ui/                 # A2UI 确认协议与 ConfirmationManager
│       ├── hook/               # confirm_gates、react_guard、HookRegistry
│       ├── tools/              # MCP 语义 Tool Registry（按域二级目录）
│       │   ├── script/ image/ storyboard/ video/ tts/ editing/
│   ├── tts/                     # 多引擎 TTS（Edge/OpenAI/Azure/SiliconFlow/Gemini/MiMo）
│       │   ├── web_search/     # 联网搜索（未默认注册 agent）
│       │   └── shared/         # agent_tools、executor、ask_user
│       ├── react_decide.py     # 运行时 ReAct 决策
│       └── protocol.py 等      # JSON 解析、streaming、tools_schema
├── apps/
│   ├── api/                    # FastAPI + WebSocket（生产桌面模式挂载静态前端）
│   ├── web/                    # Vite + React + A2UI 组件
│   │   └── src/i18n/           # i18next 配置与 locales（见 docs/i18n.md）
│   └── desktop/                # Electron 壳：开发快捷启动 + 打包安装包入口
│       ├── main.cjs / preload.cjs
│       ├── devServers.cjs      # 开发：拉起本机 API + Vite
│       ├── prodServers.cjs     # 生产：嵌入式 Python API
│       ├── updater.cjs         # electron-updater（GitHub Releases）
│       ├── electron-builder.yml
│       └── runtime/            # 构建产物（不入库）：python + web/dist + api_boot
├── scripts/
│   └── packaging/              # 桌面打包脚本（prepare-runtime、build-desktop）
├── .github/workflows/
│   └── release-desktop.yml     # tag v*.*.* → Win NSIS + Mac DMG → GitHub Release
├── tests/
│   ├── unit/                   # 核心逻辑（含 test_desktop_static.py）
│   └── api/                    # HTTP/WebSocket
├── docs/
│   └── desktop-packaging.md    # 发版、未签名分发、本地构建说明
├── requirements-desktop.txt    # 生产 pip 依赖（无 pytest；含 torch/WhisperX）
├── pyproject.toml
└── requirements.txt
```

### 2.1 目录分层边界（防重复）

`core/` 顶层与 `core/llm/` 子树**职责不同**，禁止平行复制同名包：

| 职责 | 唯一路径 | 已废弃（勿新建） |
|------|----------|------------------|
| 领域实体（Project、Script、资产） | `core/models/` | — |
| LLM 协议模型（LlmRequest、ChatMessage） | `core/llm/model/` | — |
| Agent 提示词与组装 | `core/llm/prompt/` | `core/prompt/` |
| 子 Agent 编排 | `core/llm/agent/` | `core/agents/` |
| A2UI 确认协议 | `core/llm/a2ui/` | `core/a2ui/` |

- **`core/models` 与 `core/llm/model` 不合并**：前者是业务领域类型，后者是 LLM 请求/消息协议；依赖方向为 `llm → models`，不可反向。
- **提示词单源**：`load_text()` 根目录为 `core/llm/prompt/`；规则类 `.md` 放在 `core/llm/prompt/rules/`（含 `history_summary.md`）。
- **守卫**：`tests/unit/test_core_layout.py` 断言废弃顶层目录不存在；`.cursor/rules/core-layer-boundaries.mdc` 约束 AI 编辑。

### 2.2 前端国际化（`apps/web/src/i18n/`）

- **库**：i18next + react-i18next；入口 `config.ts` 注册 SVF 与 OpenCut 命名空间
- **Provider**：`LocaleProvider` 包裹 `App.tsx`；语言键 `svg.locale`（`zh-CN` | `en`）
- **SVF Hook**：`useAppTranslation.ts`；页面使用 `useTranslation('nav')` 等
- **OpenCut Hook**：`editor/opencut/i18n/useOpencutT.ts`；注册表通过 `labelKey` + `translateRegistryLabel.ts`
- **文案文件**：`locales/{zh-CN,en}/` 下 JSON；OpenCut 独立子目录 `opencut/`
- **详细约定与验收**：[`docs/i18n.md`](i18n.md)

### 2.3 桌面安装包（`apps/desktop` + `scripts/packaging`）

- **开发壳**：`dev-desktop.bat` / `apps/desktop` 的 `npm start`；复用本机 venv 与 Vite，见 [`apps/desktop/README.md`](../apps/desktop/README.md)。
- **生产包**：`prepare-runtime.*` 组装 `apps/desktop/runtime/`（嵌入式 Python、`apps/web/dist`、`api_boot.py`）；`electron-builder` 产出未签名 NSIS / DMG。
- **发版**：`git tag vX.Y.Z && git push origin vX.Y.Z` 触发 `release-desktop.yml`；用户文档见 [`desktop-packaging.md`](desktop-packaging.md)。
- **自动更新**：`electron-updater` + GitHub Releases；设置页「检查更新」（仅打包版）。
- **用户数据**：`%LOCALAPPDATA%\SuperVideoGenerator\`（Win）或 `~/Library/Application Support/SuperVideoGenerator/`（Mac）；升级不覆盖 `data/`。

## 3. Token 预估、finish_reason 与对话压缩

- 模块：`core/llm/client/tokens.py`（`estimate_request_breakdown`：system/tools/messages/completion 分项 + 占比）、`core/llm/client/finish_reason.py`（`stop_reason` 归一化与 `max_tokens`/`length` 截断判定）、`core/llm/client/token_round.py`（单轮汇总，含 breakdown 累计）
- `LLMClient` 在 **发起 HTTP 请求前** 写入 `llm_request` / `llm_response` 的 `meta.token_usage`（`estimated: true`，含 `breakdown` 各分项 `pct_of_total`）；响应侧合并 API `usage` 为 `actual_usage`，并记录 `finish_reason` / `finish_reason_normalized` / `truncated`
- **`complete_tool_calls`**：若 `finish_reason` 为 `max_tokens`/`length` 且 `tool_calls` 为空，**立即** `LlmOutputTruncatedError` abort（不走无 tool_calls 重试）
- **`context_window_tokens`**（默认 1_048_576）超限时：`core/llm/prompt/history_compress.py` 保留最近 `history_keep_messages`（默认 10）条，对更早消息调用 `complete()` 摘要并注入 assistant 前缀；失败时回退 `fit_chat_history` snippet 滑窗
- `run_from_message` 每轮开始 `begin_token_round`，结束写入：
  - `Conversation.last_round_token_usage` / `total_token_usage`（按 model 累计，含 breakdown）
  - 交互日志 `kind=conversation_token_round`

| 配置项 | 默认 | 含义 |
|--------|------|------|
| `max_tokens` | 8192 | API completion 上限（参与预估与截断判定） |
| `context_window_tokens` | 1_048_576 | 输入侧 token gate + LLM 压缩触发 |
| `history_keep_messages` | 10 | 压缩时保留最近 N 条对话 |

## 4. A2UI 协议

### 4.1 服务端 → 客户端

```typescript
interface A2UIConfirmationRequest {
  type: "a2ui_confirmation_required";
  confirmation_id: string;
  kind: "script_structure" | "plan_approval" | "video_generation_cost" | "generic";
  title: string;
  description?: string;
  components: A2UIComponent[];  // 表单字段描述
  estimated_cost_usd?: number;
  expires_in_sec?: number;
}

interface A2UIComponent {
  id: string;
  component: "text" | "markdown" | "select" | "checkbox" | "cost_summary";
  label: string;
  value?: unknown;
  options?: { label: string; value: string }[];
  required?: boolean;
}
```

### 4.2 客户端 → 服务端

```typescript
interface A2UIConfirmationResponse {
  type: "a2ui_confirmation_response";
  confirmation_id: string;
  approved: boolean;
  values?: Record<string, unknown>;
}
```

### 4.3 ConfirmationManager

- `request_confirmation(...)` → 注册 Future，通过 EventEmitter 推送 A2UI
- WebSocket 收到 response 后 resolve Future
- 默认 **无超时**：`default_timeout=None` 时无限等待用户操作；仅测试或显式传入 `timeout` 时才会触发 `ConfirmationTimeoutError`
- **执行暂停事件**：`request()` 开始时 emit `execution_paused`（含 `confirmation_id`、`kind`、`conversation_id`）；用户响应后 emit `execution_resumed`
- **`has_pending()`**：主编排委派前防御性检查，避免在有未完成确认时继续 delegate
- 剧本需求补全：`request_script_requirements`
- Agent 动态提问：`request_user_questions`（`ask_user_question` 工具 → `kind=generic` 表单）
- **展示方式**：A2UI 确认表单内嵌于聊天消息流（`A2UIInlineCard`），不再使用全屏 overlay 弹窗
- **答案回传**：`execute_ask_user_question` 将用户 values 合并进 OBSERVATION（`用户回答：{json}`）；`react_observation` WS 事件含 `user_values`；委派子 Agent 时优先使用 `session.task_brief` 中的「用户补充」段
- **ACTION 持久化**：`format_action_content` 以 JSON 写入，避免 Python repr 导致 `raw` 污染
- 声明式确认网关：`core/llm/hook/confirm_gates.py`
  - `CONFIRM_AFTER_STEP`：步骤成功后触发（默认 `script_design` → `kind=script_structure`）
  - 步骤进入 `StepStatus.AWAITING_CONFIRMATION` 并 emit `step_awaiting_confirmation`；用户确认后 emit `step_resumed` 并标记 `COMPLETED`
  - 项目配置 `GenerationConfig.require_script_structure_approval`（默认 `true`）为 `false` 时跳过剧本结构 A2UI
  - 用户长时间未操作 → 主编排保持 `AWAITING_CONFIRMATION` 挂起，不中止、不自动跳过；用户提交确认后继续
  - 用户主动 `abort` → 跳出主编排循环进入 finalize
  - `CONFIRM_BEFORE_ACTION`：高成本 delegate/tool 执行前（预留）
  - **图片来源 A2UI**：`ImageTextConfig.source_mode=user_choice` 时，`delegate_image_gen` 前弹窗选择生图/搜图（`kind=image_source`），结果写入子 Agent `work_context.image_source`
  - 用户 `regenerate` → 清除子 Agent 会话、撤销 `completed_step_types`、写入反馈后重新委派
  - 用户 `abort` → 跳出主编排循环进入 finalize
- **错误中断**：主编排 LLM 决策失败（如未返回 `tool_calls`）立即 `raise`，剧本置 `failed`，不再重试循环；`run_from_message` 跳过摘要 LLM，返回失败说明

### 4.4 ExecutionMode（目标模式）

- `GenerationConfig.execution_mode`：`interactive`（默认）| `goal`
- **interactive**：保留全部 A2UI 与 `ask_user_question`
- **goal**：跳过 `request_script_requirements`、`script_structure`、`image_source`、`CONFIRM_BEFORE_ACTION`；`available_actions` 与 tool 列表不含 `ask_user_question`；system 追加 `rules/goal_mode.md`
- 项目级 PATCH `/api/projects/{id}/config`；单次 chat 可 `execution_mode` 覆盖

### 4.5 Skill 单轮注入

- 目录：`core/llm/prompt/skills/{id}/`（`skill.json`、`system.md`、可选 `settings.json`、`agents/{agent}.md`）
- 用户消息 `/skillId 正文` 仅**当前轮**注入 task_brief 与子 Agent `skill_overlay`（不写入 Conversation 元数据）
- `GET /api/skills` 列表；未知 id 返回错误摘要

## 5. 日志设计

使用 `core.logging.setup_logging()` + 每模块 logger：

```
[STAGE:super_video_master] project=xxx script=xxx message=...
[STAGE:master.react] script=xxx iteration=1 action=delegate_script_design
[STAGE:a2ui] confirmation_id=xxx kind=script_requirements waiting=true
[STAGE:interaction] kind=conversation_token_round total_tokens=...
```

环境变量 `LOG_LEVEL=DEBUG` 可打开详细日志。`LOG_FILE=off` 可关闭文件落盘。

Windows + `uvicorn --reload`：`MainProcess`（热重载监视进程）仅输出到 stdout，子进程写入 `data/logs/app.log`；轮转时若文件被占用（IDE 尾随行、双进程）会跳过当次轮转而非抛错。

**交互日志持久化**（`core/interaction_log/`）：
- SQLite：`data/interaction_logs.db`，按 `project_id` / `script_id` 查询；`DELETE /api/interactions?project_id=&date=` 按项目+日期删除（同步 JSONL）
- JSONL：`data/logs/interactions/{project_id}/{YYYY-MM-DD}.jsonl`（按项目 + 日期分片）
- 新建项目（`create_project`）**不**清空历史交互日志
- 前端 `LogsPage` 默认展示当前项目/剧本记录，可按日期与类型筛选

## 5.1 提示词数据流（core/llm/prompt）

固定区进入 LLM **system**；ReAct/Action **可变编排状态**拼入 messages **末条 user**（`## 当前编排状态` / `## 当前行动上下文`）。其余 user messages 为任务锚点与多轮 ReAct 历史。详见 [prompt-architecture.md](prompt-architecture.md)。

```
fixed/role.*.md ──► prompt_resolver ──► role_prompt
                                              │
ConversationStore ──► chat_messages ──► build_llm_request (system/tools/messages)
       │                        │                           │
context_window ◄────────────────┘                           │
       │                                                      ▼
       └────► AgentContextManager ──► turn_user ──► LLMClient(LlmRequest)
rules/*.md ──► build_react_system / build_action_system              │
tools/schemas ──► build_*_tools ──► core/llm/tools/registry.py (call_tool)
                                                    client/wire.py → HTTP (Anthropic Messages API)
```

- **canonical 层**：`LlmRequest`（`system` / `tools` / `messages` 分列；messages 为 block 格式）
- **wire 层**：`llm_request_to_anthropic_payload` → `system` 顶层 + Anthropic tools + messages
- **ReAct**：`LLMClient.complete_tool_calls(LlmRequest)` + `core/llm/prompt/tools/registry.py`；子 Agent 只读/参数齐全时 `core/llm/tools/registry.call_tool`
- **Provider**：`deepseek`（`https://api.deepseek.com/anthropic`）、`anthropic`（`https://api.anthropic.com`）；旧 provider 配置自动回退 `deepseek`
- **认证**：`x-api-key` + `anthropic-version: 2023-06-01`；端点 `POST /v1/messages`
- **日志层**：`request_body` 分列 `{system, tools, messages, model, ...}`；`llm_response.response_body` 含完整 assistant 回复（content、tool_calls、finish_reason、usage）
- **ReAct tool_calls**：若模型仅返回 content 无 tool_calls，自动追加纠错 user 消息重试一次；若返回 `$TOOL_NAME`/`$PARAMETER_NAME` 等占位符 tool_call（`core/llm/tool_call_guard.py`），同样纠正重试一次；思考流式 UI 仅在 tool_calls 成功后推送
- **Thinking 模型 tool_choice**：`core/llm/client/tool_choice.py` 检测 `deepseek-reasoner` / `deepseek-v4-*` 等，将 `any`/`tool` 降为 `auto`（`SVG_LLM_THINKING_MODE` 或 `thinking_mode` 可覆盖）

### 5.1.1 Plan 模式（始终开启）

- 模块：[`core/llm/plan_context.py`](../core/llm/plan_context.py)（`build_plan_snapshot`、`build_plan_slice_for_step`、`extract_plan_update`）
- 主编排每轮末条 user 状态 JSON 含 `execution_plan`、`plan_status_history`、`last_remaining_plan`（**pinned**，不受 observation 滑窗压缩）、`pipeline_progress`（Store 推断已完成步骤）、`user_resume_target`（用户续跑意图）
- 子 Agent 动态区含 `plan_slice`（当前步骤 + 已完成步骤摘要）
- LLM 每轮 tool_calls 必填 `plan_status` / `remaining_plan`；回写合并至 `PlanDocument.runtime_summary` 并 emit `plan_updated`

### 5.2 对话主流程（`run_from_message`）

1. 校验剧本状态  
2. 确保 `conversation_id`（API 层创建或校验 `ConversationIndex`）  
3. A2UI 需求补全（可选）  
4. 绑定视频风格  
5. `ConversationStore` 记录用户消息（键：`{conversation_id}:master`）  
6. `MasterReActEngine.run`（`decide_master_session` 循环）  
7. LLM 生成用户可见摘要；更新 `Conversation.last_summary`  

持久化：
- **MemoryStore 聚合索引**：`data/dev_store.json`（项目/剧本/资产 JSON）
- **AI 配置**：`data/ai_config.json`（[`core/llm/ai_config_store.py`](../core/llm/ai_config_store.py)；LLM/生图/生视频/TTS 含 API Key；TTS 默认 Edge 无需 Key；`GET /api/ai/tts/voices`、`POST /api/ai/tts/preview` 试听）
- **Agent 提示词**：`data/agent_config.json`（[`core/llm/agent/config_manager.py`](../core/llm/agent/config_manager.py)）
- **项目目录双写**：`data/projects/{project_id}/project.json`、`data/projects/{project_id}/scripts/{script_id}/script.json` 及 `assets/media/`、`assets/exports/`（[`core/store/project_paths.py`](../core/store/project_paths.py)；`save_store` 同步 meta；媒体落盘见 [`media_storage.py`](../core/store/media_storage.py)：支持 `data:` URL 与 **http(s) 远程 URL 下载**到 `assets/media/`，`MediaAsset.url` 存相对路径 `projects/.../assets/media/{media_id}.{ext}`，前端经 `GET /api/projects/{project_id}/scripts/{script_id}/assets/media/{filename}` 访问）
- **启动扫描**：`load_store` 在读取 `dev_store.json` 后调用 `discover_projects_from_disk`、`sync_scripts_from_disk`（合并磁盘 `script.json` 较新 meta）与 **`merge_script_bundles_from_disk`**（从 `store_bundle.json` 恢复缺失资产），并回写 `dev_store.json`
- **剧本资产双写**：`save_store` 同步写入 `data/projects/{pid}/scripts/{sid}/store_bundle.json`（文字/媒体/分镜/剪辑计划）；`schedule_save` 防抖改为可推迟、关键 mutation 立即落盘
- **项目生命周期**：`POST /api/projects` **不再**调用 `reset_history()`，支持多项目并存；`DELETE /api/projects/{id}`、`DELETE .../scripts/{sid}`、`POST /api/projects/batch-delete` 级联清理 MemoryStore、`dev_store.json`、`conversations.db` 与 **`data/projects/{id}/` 目录树**（含媒体；**保留** `interaction_logs.db` / JSONL）；路径经 `resolve_data_root()` 解析为仓库绝对路径
- **对话元数据**：`dev_store.json` 字段 `conversations`；启动与列表 API 从 `conversations.db` 补全缺失 index
- **完整消息归档**：`data/conversations.db`（SQLite，`core/conversation/sqlite_store.py`）
  - `conversation_messages`：含 master/agent 通道、ReAct 轮、子 Agent（`step_id`）
  - `a2ui_records`：A2UI 请求与用户响应
  - 启动时双向同步：SQLite → index；JSON/内存消息 → SQLite backfill
  - `view=full` 读 SQLite；拉消息前若 index 缺失会先 merge SQLite 元数据
  - `clear_agent_session` 仅清内存，**不删** SQLite 归档
- 单条消息字段：`role`、`content`（字符串或 blocks）、`tool_call_id`、`message_kind`、`step_id`

### 5.3 core/llm 模块

| 路径 | 职责 |
|------|------|
| `client/` | HTTP 流式、`wire`、`settings`、`providers`、`tokens`、`tool_calls` |
| `model/` | `LlmRequest`、`ChatMessage`、`ReActAgentInfo` / `ReActToolInfo` |
| `react_decide.py` | 统一 tool_calls ReAct 决策（主编排 + 子 Agent） |
| `hook/react_guard.py` | 子 Agent 连续重复 tool 签名检测；连续第 2 次相同 action+input 抛 `DuplicateActionAbortError` |
| `hook/confirm_gates.py` | 步骤后/动作前 A2UI 确认网关 |
| `master/master_react.py` | `MasterReActEngine` 主编排 ReAct 循环 |
| `master/session.py` | `ReActSession` / `create_master_react_session` |
| `master/actions.py` | 委派 action 与流水线元数据 |
| `master/tools.py` | 主编排 `tool_*` 执行器；`tool_list_assets` 返回文字+媒体完整 JSON |
| `protocol.py` | `parse_react_json` |
| `streaming.py` | SSE + `ReactJsonThoughtParser` |
| `tools_schema.py` | re-export `core/llm/prompt/tools/registry.py` |

### 5.3.1 core/llm/tools 模块（MCP 语义 Registry）

| 路径 | 职责 |
|------|------|
| `registry.py` | `ToolRegistry`：`list_tools` / `call_tool` / `build_tool_definitions` |
| `bootstrap.py` | 聚合 `register_script_tools` … `register_editing_tools` |
| `spec.py` / `result.py` / `validators.py` | ToolSpec、ToolResult、jsonschema 校验 |
| `output_schemas.py` | 各 tool 的 output JSON Schema builder |
| `script/handler.py` + `script/schemas.py` | script_agent CRUD + `list_text_assets` |
| `image/` … `editing/` | 各域 handler；`image/scan.py`、`image/generate.py`（Agnes 生图）、`image/search_sync.py`；`core/edit/` 剪辑时间轴、`shot_timing.py`（分镜镜级/句级时间）、`timeline_analysis.py`（时间段分析）与 `asset_resolver.py` 素材校验 |
| `shared/agent_tools.py` | `AGENT_TOOLS` 懒加载（Registry 兼容层） |
| [`docs/tools-reference.md`](tools-reference.md) | 全 Agent action 用途与 handler 路径总览 |
| `web_search/` | DuckDuckGo / Tavily；**暂未**注册到 agent bootstrap |
| `web_fetch/` | `read_webpage`：浏览器 UA + Cookie 预热 + 正文区域提取 + 可选 Jina Reader 回退；拒绝 localhost/内网与内部 API 路径；仅注入 script_agent |

`core/llm/agent/base.py` 在只读或 ReAct 决策参数齐全时直调 Registry，否则走 `run_llm_action`。

### 5.3.2 生图（Agnes AI）

- 默认 [`Agnes AI API`](https://agnes-ai.com/zh-Hans/docs/overview)（OpenAI 兼容 `POST /v1/images/generations`）
- 配置：`SVG_IMAGE_GEN_*` 或 `AGNES_API_KEY`（见 `.env.example`）；默认模型 `agnes-image-2.1-flash`（图生图同模型，`img2img_model` 可覆盖），Base URL `https://apihub.agnes-ai.com/v1`；`max_concurrency` 默认 4
- **文生图**：character/prop/scene；**图生图（2.1）**：`frame` 画面资产，`extra_body.image: [url...]` 多参考合成（scene 为首图）
- 模块：`core/llm/tools/image/settings.py`、`agnes_client.py`（`generate_text_to_image_async` + **`generate_image_with_reference_async`**）、`variants.py`、`reference_url.py`、`generate.py`
- **多图变体**：`TextAsset.content.image_variants[]`（base 设定主形象 + expression/pose/action 衍生）；`scan` 按变体输出 `variants[]`/`pending_variant_count`；`generate_images` 先 base 后 derivative（reference 生图）；`primary_media_id` 仅 base 更新
- `generate_images` handler 并发调用 Agnes API，逐张落盘并通过 WebSocket `image_gen_progress` 推送进度；**单项 API 失败最多重试 3 次**，仍失败则 `ImageGenerationAbortError` 中止子 Agent 步骤；**全部失败项**结构化写入 `failure_analysis`（原因分类、API 说明、prompt 摘要），主编排 observation 供 super_video_master 分析是否需 `delegate_script_design` 修订提示词
- LLM **仅填 observation**（可选 `items[].source_text_asset_id`）；禁止 items 内写 image_prompt（易截断 JSON）；后端 `slim_generate_images_args` + scan 补全待生图项
- JSON 截断容错：`json_parse.salvage_truncated_tool_arguments` 保留 observation 丢弃未闭合 items
- 落盘：`llm_action.persist_single_generated_image`（含 `variant_id`）→ 更新变体 `media_id`；**仅 base** 写 `primary_media_id`
- 前端：`ImageGenProgressModal` 展示逐张状态；`Workbench` 监听 `image_gen_progress`

### 5.3.3 统一 AI 配置 API

- 模块：[`core/llm/ai_config.py`](../core/llm/ai_config.py) 聚合 `LLMConfigManager`、`ImageGenConfigManager`、`VideoGenConfigManager`、`TtsConfigManager`、`ExportConfigManager`
- `GET/PATCH /api/ai/config` 返回/更新 `{ llm, image, video, tts, export }` 五区；`export` 含 fps/width/height；TTS 含 `default_voice`、`voice_rate`、多引擎 Key；`llm.show_react_details` 控制工作台 ReAct 展示（默认 `true` 完整思考/观察，`false` 仅工具名称）
- `GET /api/ai/tts/voices?locale=`、`POST /api/ai/tts/preview`（短文本试听 mp3；**不依赖** `tts.enabled`，请求体可覆盖 provider/音色/Key 以验证未保存的表单配置）
- 兼容：`GET/PATCH /api/llm/config` 仍为扁平 LLM + `image_text_defaults`
- 前端：`AiSettingsPage` TTS Tab（短文本试听）；合成 mp3 试听：`MediaPreview` + `resolveMediaPlayUrl()`，用于计划面板、分镜/媒体/剪辑看板

### 5.3.4 剪辑成片（FFmpeg + Edit Studio）

- **默认导出**：[`core/edit/ffmpeg_renderer.py`](../core/edit/ffmpeg_renderer.py) + [`core/edit/export_settings.py`](../core/edit/export_settings.py)；多层同时段走 `composite_slices` + FFmpeg `overlay`；[`core/tts/ffmpeg_util.py`](../core/tts/ffmpeg_util.py) 统一路径探测（系统 PATH → Windows 常见路径 → **imageio-ffmpeg 内置**）与 `is_ffmpeg_available`
- **NLE 工程导出**：[`core/edit/nle_export/`](../core/edit/nle_export/) 将 `EditTimeline` 转为 FCP7 XMEML v5 + 素材 ZIP（`nle_premiere_*.zip`）；`POST .../export-nle` 异步 job；**不依赖 FFmpeg**；`GET /api/edit/capabilities` 返回 `nle_export_enabled` / `nle_export_formats: ["premiere"]`
- **Edit Studio（OpenCut Classic 融合，2026-07-09）**：[`EditTabSimpleView.tsx`](../apps/web/src/editor/EditTabSimpleView.tsx) 预加载 + [`EditorStudioModal.tsx`](../apps/web/src/editor/EditorStudioModal.tsx) 全屏 Classic（无回退）+ [`apps/web/src/editor/opencut/SvfClassicEditor*`](../apps/web/src/editor/opencut/) + [`adapter/SvfMediaBridge.ts`](../apps/web/src/editor/adapter/SvfMediaBridge.ts)；PATCH 支持 `video_layers` 与 `metadata.classic_project`；用户可见名称为「剪辑助手」
- **中止执行**：`POST .../chat/abort` + [`core/execution/cancel.py`](../core/execution/cancel.py)（`check_cancelled` / `wait_or_cancel` / `gather_with_cancel`）；取消标记在 **主编排 ReAct 循环头、LLM SSE 流、子 Agent decide/act、批量生图/TTS、FFmpeg 分段导出** 等多点协作检查；前端 `execution_abort_requested` 即时进入「中止中…」，收到 `execution_aborted` 后恢复 idle
- **preview_url**：`timeline_board_items` 遍历 `video_layers` 经 `resolve_clip_media` 填充；见 [`docs/edit-studio-plan.md`](edit-studio-plan.md)
- **能力单源**：[`core/edit/capabilities.json`](../core/edit/capabilities.json)；`GET /api/edit/capabilities` 合并 `ffmpeg_available` / `export_enabled` / `nle_export_enabled` / `max_video_layers`
- **Agent merge**：`plan_edit_timeline` 输出 `video_layers` + `transform`；`merge_agent_timeline` 按层/clip `edited_by` 保护（[`core/edit/timeline.py`](../core/edit/timeline.py)）
- **transform 插值**：[`core/edit/transform_interp.py`](../core/edit/transform_interp.py)（`collect_timeline_boundaries`、`build_scaled_video_filter`、`snap_even_dim`）；`build_scaled_video_filter` 对 pad 目标使用**偶数尺寸** + `force_divisible_by=2`，避免 Ken Burns 中间 scale 产生奇数高宽导致 FFmpeg pad 失败；`motion=static` 时忽略 `motion_detail` 的 scale 插值；前端预览与导出均经 OpenCut `buildScene` / opencut-wasm 对齐。
- **媒体路径**：[`core/edit/media_paths.py`](../core/edit/media_paths.py)、[`core/edit/export_paths.py`](../core/edit/export_paths.py)、[`core/edit/edit_capabilities.py`](../core/edit/edit_capabilities.py)
- 规格：[`docs/edit-studio-plan.md`](edit-studio-plan.md)

**EditTimeline / EditClip**（[`core/models/entities.py`](../core/models/entities.py)）：

| 字段 | 说明 |
|------|------|
| `video_layers[]` | `EditVideoLayer`：多层视频轨，`z_index` 叠放顺序 |
| `EditClip.transform` | `EditClipTransform`：x/y/width/height（归一化中心点语义）+ keyframes |
| `EditClip.edit_description` | 该时间段剪辑意图自然语言详述 |
| `transition_in` / `transition_out` | `EditClipTransition`：cut/fade/dissolve + duration_ms |
| `background` | `EditClipBackground`：solid/image/blur + color/asset_ref |
| `motion_detail` | `EditClipMotionDetail`：Ken Burns 起止焦点与 scale |
| `source_refs` | 关联 shot_id、text_asset_ids、media_ids |
| 校验 | [`core/edit/asset_resolver.py`](../core/edit/asset_resolver.py)：`validate_edit_timeline` → `MissingItem.suggested_upstream`；**导出前强制校验**，缺素材时 `FfmpegExportError`（composite 路径不再静默黑屏） |

**editing_agent 流水线**（TTS 之后）：`load_edit_context` → `plan_edit_timeline` → `validate_edit_assets` →（缺失）`report_missing_assets` /（就绪）`gather_media` → `compose_final`。用户询问某段时间剪辑结构时可用 `analyze_edit_timeline`（`core/edit/timeline_analysis.py`）。storyboard 仅产出 VideoPlan。

### 5.4 图文资产（character / prop / scene）

| 模块 | 职责 |
|------|------|
| `core/models/image_text_asset.py` | 图文资产 content + **`ImageVariant` / `image_variants[]`** |
| `core/assets/image_prompt.py` | `compose_base_image_prompt` / `compose_variant_image_prompt`；scene 空镜背景板（`PROMPT_VERSION=2`，无人物/无 prop 主体）；character/prop 绿幕 prompt |
| `core/assets/chroma_key.py` | `generate_images` 落盘后 character/prop FFmpeg colorkey → `{media_id}.png` 透明图；`POST .../assets/reapply-chroma` 修复历史资产 |
| `core/assets/service.py` | 用户 PATCH 更新、`user_edited`、prompt 重算 |
| `core/llm/tools/script/list.py` | `list_text_assets` 载荷：`types` 过滤、`include_content` 裁剪、`linked`/`counts_by_type`；observation 为完整 JSON |
| `core/llm/tools/image/scan.py` | `scan_text_assets`：`variants[]`、`pending_variant_count`、变体级 `needs_generation` |
| `core/board/builder.py` | `_image_text_item` 统一看板 item；Tab：整体看板 / 图文资产 / **script_details** / 角色 / 场景 / **物品** / 剪辑 |
| `apps/web/src/hooks/useApi.ts` | `WorkspaceMode`（`project` \| `script`）；`enterScript` / `exitToProject` / `createScriptInProject` |
| `apps/web/src/pages/Workbench.tsx` | 项目模式全宽无对话；剧本模式左对话 + 右看板 |
| `apps/web/.../ImageTextAssetCard.tsx` | 完整属性 + 生图 prompt 展示 |
| `apps/web/.../ImageTextAssetEditor.tsx` | 看板编辑表单 |
| `apps/web/.../manual/*` | 人工增删改：创建对话框、剧情编辑、执行中禁用横幅 |
| `apps/web/.../Workbench.tsx` | `manualEditEnabled`：AI 执行中禁用看板人工操作 |

| `GET .../assets?type=character|prop|scene` | 可按类型过滤。`PATCH /api/projects/{id}/assets/{asset_id}` 更新图文 content；`POST/DELETE .../scripts/{sid}/assets` 用户手动增删；`PATCH .../scripts/{sid}` 更新剧本正文。`dev_store.json` 加载时对图文资产 content 惰性升级并补全 `image_prompt`。 |

| 组件 | 路径 | 职责 |
|------|------|------|
| `PromptBuilder` | `core/llm/prompt/builder.py` | 渲染 templates、组装 system/user |
| `AgentContextManager` | `core/llm/prompt/context_manager.py` | 子 Agent / 主编排动态槽位 |
| `prompt_resolver` | `core/llm/agent/prompt_resolver.py` | Profile 与项目覆盖 |
| `context_window` | `core/llm/prompt/context_window.py` | observation 滑窗压缩（轻量兜底） |
| `history_compress` | `core/llm/prompt/history_compress.py` | 超 token 预算时对较早对话 LLM 摘要 |

## 6. 实施阶段（本次交付）

| 阶段 | 内容 | 验证 |
|------|------|------|
| **C0** | pyproject、models、logging | `tests/unit/test_models.py` |
| **C1** | guards、store、a2ui | `tests/unit/test_guards.py`, `test_a2ui.py` |
| **C2** | ReAct 主编排 + mock agents | `tests/unit/test_super_video_master.py` |
| **C3** | FastAPI + WebSocket | `tests/api/test_api.py` |
| **C4** | React 工作台 + A2UIInlineCard（聊天内嵌） | 手动 + `npm run build` |
| **C5** | 端到端：对话轮次 token 预估日志 | `tests/unit/test_llm_tokens.py` |

## 7. API 端点（MVP）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/projects` | 创建项目 |
| GET | `/api/projects/{id}` | 项目详情 |
| PATCH | `/api/projects/{id}/config` | 含 generation.mode |
| POST | `/api/projects/{id}/scripts` | 创建剧本 |
| GET | `/api/projects/{id}/scripts/{sid}` | 剧本详情 |
| GET | `/api/projects/{id}/scripts/{sid}/assets` | 资产列表 |
| POST | `/api/projects/{id}/scripts/{sid}/assets` | 用户手动创建文字资产 |
| DELETE | `/api/projects/{id}/scripts/{sid}/assets/{asset_id}` | 用户手动删除文字资产 |
| PATCH | `/api/projects/{id}/scripts/{sid}` | 用户手动更新剧本标题/正文 |
| PATCH | `/api/projects/{id}/assets/{asset_id}` | 用户手动更新图文资产 |
| POST | `/api/projects/{id}/scripts/{sid}/chat` | 对话消息（body 可选 `conversation_id`） |
| POST | `/api/projects/{id}/scripts/{sid}/conversations` | 显式创建对话线程 |
| GET | `/api/projects/{id}/conversations` | 项目历史对话列表（query `script_id` 过滤） |
| GET | `/api/projects/{id}/conversations/{conv_id}/messages` | 唤醒：`view=ui`（默认）用户可见消息；`view=full` 完整时间线（ReAct/子 Agent/A2UI） |
| WS | `/ws/projects/{id}/scripts/{sid}` | 事件 + A2UI |

## 8. 依赖

**Python**: fastapi, uvicorn, pydantic>=2, pytest, pytest-asyncio, httpx, websockets

**前端**: react, vite, typescript, zustand

## 9. 运行方式

```bash
# 后端
pip install -e ".[dev]"
pytest tests/ -v
uvicorn apps.api.main:app --reload --port 8000

# 前端
cd apps/web && npm install && npm run dev
```
