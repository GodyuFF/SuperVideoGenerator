# SuperVideoGenerator 代码设计计划

> 版本：v0.1 | 对应产品手册 v0.1

## 1. 目标

在 `docs/product-plan.md` 基础上落地可运行代码骨架，具备：

- ReAct 主编排（超级视频大师 + 子 Agent）
- 分阶段结构化日志
- **A2UI** 不确定信息前端确认（WebSocket 推送表单 → 用户响应）
- **生成模式**：`auto`（自动，跳过视频生成确认）/ `cost_confirm`（费用确认，视频生成前需用户点击）
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
│   ├── super_video_master/     # ReAct 主编排
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

## 3. 生成模式设计

```python
class GenerationMode(str, Enum):
    AUTO = "auto"           # 自动：video_gen 不弹确认，直接调用
    COST_CONFIRM = "cost_confirm"  # 费用确认：video_gen 前 A2UI 展示预估费用
```

| 场景 | AUTO | COST_CONFIRM |
|------|------|--------------|
| 剧本粒度提案 | A2UI（可选，默认仍确认结构） | A2UI |
| Plan 完成后执行 | 可配置 `require_plan_approval` | 通常需确认 |
| **video_gen 步骤** | **跳过确认，直接执行** | **A2UI 费用卡片，用户点击后执行** |
| image_gen / tts | 直接执行 | 直接执行（P1 可扩展费用确认） |

配置路径：`ProjectConfig.generation.mode`

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
- Executor 在 `video_gen` 前调用 `await confirmation_manager.wait_for_video_gen(...)`

## 5. 日志设计

使用 `core.logging.setup_logging()` + 每模块 logger：

```
[STAGE:super_video_master] project=xxx script=xxx message=...
[STAGE:master.react] script=xxx iteration=1 action=delegate_script_design
[STAGE:a2ui] confirmation_id=xxx kind=video_generation_cost waiting=true
```

环境变量 `LOG_LEVEL=DEBUG` 可打开详细日志。

## 6. 实施阶段（本次交付）

| 阶段 | 内容 | 验证 |
|------|------|------|
| **C0** | pyproject、models、logging | `tests/unit/test_models.py` |
| **C1** | guards、store、a2ui | `tests/unit/test_guards.py`, `test_a2ui.py` |
| **C2** | ReAct 主编排 + mock agents | `tests/unit/test_super_video_master.py` |
| **C3** | FastAPI + WebSocket | `tests/api/test_api.py` |
| **C4** | React 工作台 + A2UIModal | 手动 + `npm run build` |
| **C5** | 端到端：cost_confirm 阻塞 video_gen | `tests/unit/test_generation_modes.py` |

## 7. API 端点（MVP）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/projects` | 创建项目 |
| GET | `/api/projects/{id}` | 项目详情 |
| PATCH | `/api/projects/{id}/config` | 含 generation.mode |
| POST | `/api/projects/{id}/scripts` | 创建剧本 |
| GET | `/api/projects/{id}/scripts/{sid}` | 剧本详情 |
| GET | `/api/projects/{id}/scripts/{sid}/assets` | 资产列表 |
| POST | `/api/projects/{id}/scripts/{sid}/plan` | 触发 Plan |
| POST | `/api/projects/{id}/scripts/{sid}/execute` | 触发 Execute |
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
