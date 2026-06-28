# SuperVideoGenerator 代码设计计划

> 版本：v0.1 | 对应产品手册 v0.1

## 1. 目标

在 `docs/product-plan.md` 基础上落地可运行代码骨架，具备：

- ReAct 主编排（超级视频大师 + 子 Agent）
- 分阶段结构化日志
- **A2UI** 不确定信息前端确认（WebSocket 推送表单 → 用户响应）
- **Token 预估**：LLM 调用前按 prompt + `max_tokens` 预估，写入交互日志与对话元数据
- `tests/` 目录可独立验证核心逻辑与 API

## 2. 仓库结构

```
SuperVideoGenerator/
├── core/                       # 领域与编排（无 HTTP 依赖）
│   ├── models/                 # Pydantic 模型
│   ├── logging/                # 分阶段日志
│   ├── guards/                 # ReferenceGuard, ScriptEditGuard
│   ├── a2ui/                   # A2UI 确认协议与 ConfirmationManager
│   ├── events/                 # 事件类型与 EventEmitter
│   ├── store/                  # 内存/SQLite 仓储
│   ├── super_video_master/     # 薄入口：run_from_message、summary
│   ├── conversation/           # 主/子 Agent 会话隔离
│   ├── llm/                    # HTTP 客户端 + JSON ReAct
│   │   └── master/             # 主编排：session、actions、tools、master_react
│   ├── prompt/                 # Agent 提示词（fixed/dynamic 分层）
│   └── agents/                 # 子 Agent（Mock → 真实 API）
├── apps/
│   ├── api/                    # FastAPI + WebSocket
│   └── web/                    # Vite + React + A2UI 组件
├── tests/
│   ├── unit/                   # 核心逻辑
│   └── api/                    # HTTP/WebSocket
├── docs/
├── pyproject.toml
└── requirements.txt
```

## 3. Token 预估与对话轮次日志

- 模块：`core/llm/tokens.py`（调用前启发式预估）、`core/llm/token_round.py`（单轮汇总）
- `LLMClient` 在 **发起 HTTP 请求前** 估算 `prompt_tokens` + `max_tokens`（completion 上限），写入 `llm_request` / `llm_response` 的 `meta.token_usage`（`estimated: true`）
- `run_from_message` 每轮开始 `begin_token_round`，结束写入：
  - `Conversation.last_round_token_usage` / `total_token_usage`（按 model 累计）
  - 交互日志 `kind=conversation_token_round`

配置路径：`LLMConfigManager.max_tokens` 参与 completion 预估。

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
- 超时 → `approved=false` 或抛 `ConfirmationTimeout`
- 剧本需求补全：`request_script_requirements`

## 5. 日志设计

使用 `core.logging.setup_logging()` + 每模块 logger：

```
[STAGE:super_video_master] project=xxx script=xxx message=...
[STAGE:master.react] script=xxx iteration=1 action=delegate_script_design
[STAGE:a2ui] confirmation_id=xxx kind=script_requirements waiting=true
[STAGE:interaction] kind=conversation_token_round total_tokens=...
```

环境变量 `LOG_LEVEL=DEBUG` 可打开详细日志。

## 5.1 提示词数据流（core/prompt）

固定区进入 LLM **system**，动态区进入 **user**（与 Claude Code 缓存边界一致）。详见 [prompt-architecture.md](prompt-architecture.md)。

```
fixed/role.*.md ──► prompt_resolver ──► role_prompt
                                              │
context_window  ◄── ConversationStore ────────┤
       │                                      │
       └────► AgentContextManager ──► PromptBuilder.build_react_json_user / build_action_user
rules/*.md ──► PromptBuilder.build_react_system / build_action_system
```

### 5.2 对话主流程（`run_from_message`）

1. 校验剧本状态  
2. 确保 `conversation_id`（API 层创建或校验 `ConversationIndex`）  
3. A2UI 需求补全（可选）  
4. 绑定视频风格  
5. `ConversationStore` 记录用户消息（键：`{conversation_id}:master`）  
6. `MasterReActEngine.run`（`decide_master_session` 循环）  
7. LLM 生成用户可见摘要；更新 `Conversation.last_summary`  

持久化：`dev_store.json` 字段 `conversations`（元数据）+ `conversation_messages`（消息）。

### 5.3 core/llm 模块

| 文件 | 职责 |
|------|------|
| `client.py` | HTTP 流式：`complete_text` / `complete_json` |
| `react_decide.py` | `decide_react` / `decide_master_session` / `decide_sub_agent` |
| `master/master_react.py` | `MasterReActEngine` 主编排 ReAct 循环 |
| `master/session.py` | `ReActSession` / `create_master_react_session` |
| `master/actions.py` | 委派 action 与流水线元数据 |
| `master/tools.py` | 主编排 `tool_*` 执行器 |
| `protocol.py` | `parse_react_json` |
| `streaming.py` | SSE + `ReactJsonThoughtParser` |
| `tokens.py` | 调用前 token 启发式预估 |
| `token_round.py` | 单轮对话按 model 汇总 |

| 组件 | 路径 | 职责 |
|------|------|------|
| `PromptBuilder` | `core/prompt/builder.py` | 渲染 templates、组装 system/user |
| `AgentContextManager` | `core/prompt/context_manager.py` | 子 Agent / 主编排动态槽位 |
| `prompt_resolver` | `core/agents/prompt_resolver.py` | Profile 与项目覆盖 |
| `context_window` | `core/prompt/context_window.py` | observation 滑窗压缩 |

## 6. 实施阶段（本次交付）

| 阶段 | 内容 | 验证 |
|------|------|------|
| **C0** | pyproject、models、logging | `tests/unit/test_models.py` |
| **C1** | guards、store、a2ui | `tests/unit/test_guards.py`, `test_a2ui.py` |
| **C2** | ReAct 主编排 + mock agents | `tests/unit/test_super_video_master.py` |
| **C3** | FastAPI + WebSocket | `tests/api/test_api.py` |
| **C4** | React 工作台 + A2UIModal | 手动 + `npm run build` |
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
| POST | `/api/projects/{id}/scripts/{sid}/chat` | 对话消息（body 可选 `conversation_id`） |
| POST | `/api/projects/{id}/scripts/{sid}/conversations` | 显式创建对话线程 |
| GET | `/api/projects/{id}/conversations` | 项目历史对话列表（query `script_id` 过滤） |
| GET | `/api/projects/{id}/conversations/{conv_id}/messages` | 唤醒：加载用户可见消息 |
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
