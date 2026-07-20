# CLAUDE.md

> SuperVideoGenerator — AI 视频生成系统，基于多 Agent 协作与 ReAct 编排。

## 项目概述

SuperVideoGenerator 是一款基于多 Agent 协作的 AI 视频生成系统。用户通过自然语言对话描述创意，**超级视频大师** 以 ReAct 模式编排剧本、分镜、生图、配音、剪辑等专业子 Agent，完成从创意到成片的全流程生产。

- **后端**: FastAPI (Python 3.11+)，位于 `apps/api/`
- **前端**: Vite + React，位于 `apps/web/`
- **桌面**: Electron 壳 + 可选完整离线安装包，位于 `apps/desktop/`
- **核心领域逻辑**: `core/` 目录，无 HTTP 依赖
- **文档**: `docs/` 目录
- **测试**: `tests/` 目录 (562+ 单元/API 测试)
- **本地数据**: `data/` 目录 (不入 Git)

## 修改前必读文档

**每次修改代码前，必须先读取以下文档以理解项目全貌：**

| 优先级 | 文档 | 内容 |
|--------|------|------|
| ★★★ | `docs/product-plan.md` | 产品定位、页面布局、领域模型、资产体系、ReAct 编排、路线图 |
| ★★★ | `docs/code-design-plan.md` | 仓库结构、目录分层边界、持久化设计、API 设计、各模块职责 |
| ★★☆ | `docs/prompt-architecture.md` | `core/llm/prompt` 固定/动态分层提示词架构 |
| ★★☆ | `docs/tools-reference.md` | MCP 语义 Tool Registry 与各域工具说明 |
| ★★☆ | `docs/edit-studio-plan.md` | 多轨时间轴 Edit Studio、FFmpeg 导出规格 |
| ★☆☆ | `docs/desktop-packaging.md` | 桌面未签名发版、本地构建、用户安装说明 |
| ★☆☆ | `docs/opencut-integration.md` | OpenCut 编辑器集成方案 |
| ★☆☆ | `docs/opencut-migration-review.md` | OpenCut 迁移完成情况评测 |

### 读取策略

- **修改 `core/llm/`** → 必读 `product-plan.md` + `code-design-plan.md` + `prompt-architecture.md` + `tools-reference.md`
- **修改 `core/edit/`** → 必读 `product-plan.md` + `code-design-plan.md` + `edit-studio-plan.md`
- **修改 `core/models/` 或 `core/store/`** → 必读 `product-plan.md` + `code-design-plan.md`
- **修改 `apps/api/`** → 必读 `product-plan.md` + `code-design-plan.md`
- **修改 `apps/web/`** → 必读 `product-plan.md`
- **修改 `apps/desktop/` 或打包脚本** → 必读 `desktop-packaging.md` + `docs/superpowers/specs/2026-07-17-desktop-installer-design.md`
- **新增功能** → 必读全部 ★★★ 和 ★★☆ 文档

## 修改后文档更新

**代码修改完成后，必须检查并更新相关文档：**

1. **如果修改了目录结构或新增/删除模块** → 更新 `docs/code-design-plan.md` 第 2 节（仓库结构）
2. **如果修改了领域模型或数据实体** → 更新 `docs/product-plan.md` 第 4 节（领域模型）和 `docs/code-design-plan.md` 相关章节
3. **如果修改了 Tool 定义或注册** → 更新 `docs/tools-reference.md`
4. **如果修改了提示词或 LLM 编排逻辑** → 更新 `docs/prompt-architecture.md`
5. **如果修改了 Edit Studio 或 FFmpeg 导出** → 更新 `docs/edit-studio-plan.md`
6. **如果新增/修改 API 端点** → 更新 `docs/code-design-plan.md` 第 6 节（API 设计）
7. **涉及 OpenCut 的改动** → 更新 `docs/opencut-integration.md`
8. **涉及桌面打包/发版** → 更新 `docs/desktop-packaging.md`
9. **功能完成或重大变更** → 更新 `README.md` 对应章节

## 仓库结构

```
SuperVideoGenerator/
├── core/                       # 领域与编排（无 HTTP 依赖）
│   ├── models/                 # 领域实体
│   ├── store/                  # 内存/SQLite 仓储
│   ├── super_video_master/     # 主编排入口
│   ├── conversation/           # 会话隔离
│   ├── assets/                 # 图文资产
│   ├── board/                  # 看板构建
│   ├── edit/                   # 时间轴编辑 + FFmpeg 导出
│   ├── tts/                    # 多引擎 TTS
│   ├── llm/                    # LLM 编排核心
│   │   ├── client/             # HTTP 客户端、token 预估
│   │   ├── master/             # 主编排 session/actions/tools
│   │   ├── model/              # ReAct 协议模型
│   │   ├── prompt/             # 固定/动态分层提示词
│   │   ├── agent/              # 子 Agent ReAct
│   │   ├── a2ui/               # A2UI 确认协议
│   │   ├── hook/               # confirm_gates、react_guard
│   │   └── tools/              # MCP 语义 Tool Registry
│   │       ├── script/ image/ storyboard/ video/ tts/ editing/
│   ├── guards/                 # ReferenceGuard, ScriptEditGuard
│   ├── events/                 # EventEmitter
│   ├── logging/                # 分阶段日志
│   ├── execution/              # 执行引擎
│   └── interaction_log/        # 交互日志
├── apps/
│   ├── api/                    # FastAPI + WebSocket (A2UI)
│   ├── web/                    # Vite + React 前端
│   └── desktop/                # Electron 壳 + electron-builder 安装包
├── scripts/packaging/            # prepare-runtime、build-desktop
├── .github/workflows/          # release-desktop.yml（tag 发版）
├── tests/
│   ├── unit/                   # 核心逻辑单元测试
│   └── api/                    # HTTP/WebSocket 集成测试
├── docs/                       # 产品与设计文档
├── data/                       # 本地运行时数据（不入 Git）
├── scripts/                    # 工具脚本
└── demo/                       # 演示脚本
```

## 常用命令

```bash
# 后端
.venv\Scripts\activate           # Windows 激活虚拟环境
pip install -r requirements.txt  # 安装依赖
uvicorn apps.api.main:app --port 8000  # 启动 API（勿加 --reload，避免长任务被热重载打断）

# 前端
cd apps/web && npm install && cd ../..
cd apps/web && npm run dev       # 启动前端开发服务器

# 测试
pytest tests/ -v                 # 运行所有测试（跳过 live/integration）
pytest tests/ -v -m "live"       # 运行需要 API Key 的测试
pytest tests/ -v -m "integration" # 运行需要完整环境的集成测试

# 快捷启动（根目录仅桌面入口）
launch-desktop.vbs               # Windows: 静默启动 Electron（自动拉 API + Vite）
launch-desktop.bat               # Windows: 同上，显示控制台日志
# 浏览器模式：uvicorn apps.api.main:app --port 8000  +  cd apps/web && npm run dev
# 桌面快捷方式：powershell -File scripts/update_desktop_shortcut.ps1

# 桌面安装包（维护者；默认未签名）
.\scripts\packaging\build-desktop.ps1   # Windows 本地打 NSIS
git tag v0.1.0 && git push origin v0.1.0  # 触发 CI Release（Win + Mac）
```

详见 [`docs/desktop-packaging.md`](docs/desktop-packaging.md)。

## 核心架构约束

### 目录分层边界

- `core/` 顶层与 `core/llm/` 子树职责不同，禁止平行复制同名包
- `core/` 领域逻辑无 HTTP 依赖，可独立测试
- `apps/api/` 只做 HTTP/WebSocket 适配，不写业务逻辑
- `core/llm/prompt/` 使用固定区 + 动态区分层组装 system prompt

### 数据流

```
用户消息 → super_video_master (ReAct 编排)
  → delegate 子 Agent (剧本/分镜/生图/TTS/剪辑)
  → Tool Registry 执行具体操作
  → board 构建看板数据 → WebSocket 推前端
  → store 持久化到 data/
```

### 关键设计原则

- 一切实体带全局唯一 `asset_id`（UUID + 类型前缀）
- 文字资产与数字资产分离，数字资产可回溯来源
- 未执行态支持全量 CRUD；执行开始后进入只读
- 人物/道具/场景跨剧本共享（RAG 检索）；剧情与分镜私有
- Token 预估：LLM 调用前分项预估，超长自动摘要压缩
- A2UI 协议：WebSocket 推送确认表单，前后端结构化交互

## 编码规范

- Python: 遵循 PEP 8，类型注解使用 Pydantic 模型
- 前端: TypeScript + React，组件使用 shadcn/ui 风格
- 新增 Tool 必须注册到 `core/llm/tools/` 对应域目录
- 新增子 Agent 需在 `core/llm/prompt/` 添加对应提示词
- 测试: 核心编排无 HTTP 依赖，在 `tests/unit/` 独立验证
