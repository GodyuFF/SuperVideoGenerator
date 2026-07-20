# SuperVideoGenerator

**SuperVideoGenerator** 是一款基于多 Agent 协作的 AI 视频生成系统。用户通过自然语言对话描述创意，**超级视频大师** 以 ReAct 模式编排剧本、分镜、生图、配音、剪辑等专业子 Agent，完成从创意到成片的全流程生产；右侧看板支持手工精修，Edit Studio 支持多轨时间轴编辑与 FFmpeg 导出。

---

## 项目优势

### 1. 对话驱动，Plan 先行

- **左侧对话 + 右侧看板**：AI 负责编排与生成，用户在剧本页手工 CRUD 微调资产，再交给 Agent 继续执行。
- **Plan 可见可审**：执行前展示完整生产计划，支持 A2UI 表单确认（剧本结构、成本预估等），避免「黑盒一键生成」。
- **目标模式（Goal Mode）**：可切换为 AI 自主执行至成功/失败，适合批量生产场景。

### 2. 专业子 Agent 流水线

| 子 Agent | 职责 |
|----------|------|
| 剧本设计 | 剧情、旁白、资产清单 |
| 分镜 | 镜头列表、运镜、时长 |
| 生图 | 人物 / 场景 / 道具视觉素材（Agnes / 百炼 / **火山方舟 SeedDream** / 本地 SD） |
| TTS | 多引擎配音（Edge / OpenAI / Azure / Gemini 等） |
| 剪辑 | 时间轴编排、Ken Burns、字幕烧录 |
| 视频 | AI 视频片段（Agnes Video / **火山方舟 SeedDance**） |

主编排通过 **Tool Registry + delegate** 委派子 Agent，每条链路可独立测试、独立演进。

内置视频风格：**故事书**（静图 Ken Burns）、**AI 视频**（文生/图生/关键帧）、**画面图生视频**（实体+frame 合成后以 frame 为唯一图生源 I2V）。

### 3. 资产化管理与跨剧本复用

- 一切实体带全局唯一 `asset_id`，文字资产与数字资产分离，媒体可追溯来源。
- **人物 / 道具 / 场景** 进入项目共享池，跨剧本 RAG 检索复用，降低系列剧重复劳动。
- **详情页二次生成**：图片、TTS、AI 视频可在资产详情页直接重跑；旧版本标记 `superseded`，谱系可追溯。
- **统一生成队列**：图片/视频二次生成与 Agent 批任务经进程内串行队列执行，工作台右侧「生成队列」抽屉实时展示排队与执行状态。
- 未执行态支持全量 CRUD；执行开始后进入只读，关系看板展示引用链与派生关系。

### 4. Edit Studio 可编辑时间轴

- 由只读看板升级为 **可预览、可拖拽、可写回** 的多轨剪辑工作室（OpenCut 剪辑助手）。
- **镜内多轨 Shot** 为权威源：`visuals` / `video_tracks` / `audio_tracks` / `subtitles` → 投影 `EditTimeline`；OpenCut 手改经 `apply_timeline_edits_to_shots` 回写。
- 支持 **多层视频轨**（画中画）、画布变换与关键帧、Ken Burns 运镜预览。
- 默认 **OpenCut 浏览器导出**；遗留 FFmpeg 需 `SVG_EXPORT_ENABLED=1`；Agent 在用户已编辑时间轴上采用 **merge** 策略。

### 5. 工程化 LLM 编排

- **固定区 / 动态区** 提示词分层（`core/llm/prompt`），参考 Claude Code 的 system prompt 组装模式。
- **MCP 语义 Tool Registry**：工具 schema 单源，ReAct 决策与 Action 执行共用。
- **Token 预估与对话压缩**：调用前分项预估 token 占比，超长上下文自动摘要压缩，交互日志可审计。
- **多 Provider**：DeepSeek、Anthropic、OpenAI、OpenRouter、Moonshot、智谱、通义等 LLM；生图/生视频支持火山、百炼、OpenAI、fal.ai、Gemini、Kling、Runway 等。

### 6. 可观测、可测试、可扩展

- **A2UI 协议**：WebSocket 推送确认表单，前后端结构化交互。
- **交互日志**：按项目 / 剧本 / 日期筛选，Token 用量、LLM 请求/响应、ReAct 轮次全记录。
- **970+ 单元/API 测试**，核心编排无 HTTP 依赖，可在 `tests/` 独立验证。
- **Skill 单轮注入**：消息以 `/skillId` 开头即可加载内置 Skill 提示词（如 `/thriller 做悬疑短片`）。

### 7. 本地优先，数据不出库

- 项目数据、媒体、AI 配置（含 API Key）持久化在本地 `data/` 目录，**默认不入 Git**。
- 支持 `dev_store.json` + `data/projects/` 双写，重启后自动扫描恢复项目 meta。

---

## 技术架构

```
┌─────────────────────────────────────────────────────────────┐
│  apps/web (Vite + React)                                     │
│  项目列表 · 剧本工作台 · Edit Studio · AI 设置 · 交互日志    │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTP / WebSocket
┌──────────────────────────▼──────────────────────────────────┐
│  apps/api (FastAPI)                                          │
│  REST + WS · A2UI 确认 · 导出任务 · 媒体访问                  │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│  core/                                                       │
│  llm/ (ReAct · prompt · tools · A2UI)                        │
│  edit/ (时间轴 · FFmpeg) · tts/ · assets/ · conversation/    │
│  store/ · models/ · board/                                   │
└─────────────────────────────────────────────────────────────┘
```

---

## 快速开始

### 环境要求

- Python 3.11+
- Node.js 18+（前端）
- FFmpeg（Edit Studio 导出，需在 PATH 中）

### 1. 安装依赖

```bash
# 后端
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux
pip install -r requirements.txt

# 前端
cd apps/web && npm install && cd ../..
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，至少配置 LLM API Key（默认 DeepSeek）
```

也可在 Web 端 **AI 设置页** 配置 LLM / 生图 / TTS 等，持久化至 `data/ai_config.json`（仅本机）。

**火山方舟（SeedDream / SeedDance）示例：**

```bash
ARK_API_KEY=your_volcengine_ark_api_key
SVG_IMAGE_GEN_PROVIDER=volcengine
SVG_IMAGE_GEN_MODEL=doubao-seedream-5-0-pro
SVG_VIDEO_GEN_ENABLED=true
SVG_VIDEO_GEN_PROVIDER=volcengine
SVG_VIDEO_GEN_MODEL=doubao-seedance-2-0
```

控制台：[SeedDream 5.0 Pro](https://console.volcengine.com/ark/region:cn-beijing/model/detail?name=doubao-seedream-5-0-pro) · [SeedDance 2.0](https://console.volcengine.com/ark/region:cn-beijing/model/detail?name=doubao-seedance-2-0)

### 3. 启动服务

**Windows（推荐，根目录仅此两个入口）：**

```bat
launch-desktop.vbs           # 静默启动桌面端（无黑框；Electron 自动拉 API+Vite）
launch-desktop.bat           # 同上，但显示控制台日志
```

可选：一次生成桌面快捷方式（猫头鹰图标）：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\update_desktop_shortcut.ps1
```

**命令行（浏览器模式，无根目录 bat）：**

```bash
.venv\Scripts\python.exe -m uvicorn apps.api.main:app --host 0.0.0.0 --port 8000
cd apps/web && npm run dev
```

- **桌面（推荐）**：双击 `launch-desktop.vbs`，或使用上述快捷方式。
- **浏览器**：API + Vite 就绪后打开 [http://localhost:5173](http://localhost:5173)。

### 4. 桌面应用（可选）

**开发壳**（需本机 Python + Node）：双击 `launch-desktop.vbs` / `launch-desktop.bat`，或 `cd apps/desktop && npm start`。

**完整离线安装包**：从 [GitHub Releases](https://github.com/GodyuFF/SuperVideoGenerator/releases) 下载安装。个人开源默认未签名，首次打开见 [桌面打包与发版指南](docs/desktop-packaging.md)。

**维护者本地打 Windows 包**：

```powershell
.\scripts\packaging\build-desktop.ps1
```

**正式发布**（对齐 `apps/desktop/package.json` 的 `version`）：

```bash
git tag v0.1.0 && git push origin v0.1.0
```

触发 [Release Desktop](.github/workflows/release-desktop.yml) 工作流，产出 Win NSIS + Mac DMG 并上传 GitHub Release。

### 5. 运行测试

```bash
pytest tests/ -v
```

---

## 生成模式

| 模式 | 说明 |
|------|------|
| `manual` | 关键步骤需用户 A2UI 确认后再执行 |
| `auto` | 视频生成等步骤不等待用户确认 |
| `goal` | AI 自主执行至成功/失败，不弹出确认 |

可在项目配置或工作台中设置 `generation.mode` / `execution_mode`。

---

## 文档

| 文档 | 说明 |
|------|------|
| [产品计划手册](docs/product-plan.md) | 产品定位、页面布局、领域模型、路线图 |
| [代码设计计划](docs/code-design-plan.md) | 仓库结构、持久化、API 设计 |
| [前端风格约束](docs/frontend-style-guide.md) | 暗房胶片设计令牌、详情页与二次生成 UI 规范 |
| [提示词架构](docs/prompt-architecture.md) | `core/llm/prompt` 固定/动态分层 |
| [Edit Studio 规格](docs/edit-studio-plan.md) | 多轨时间轴、FFmpeg 导出 |
| [工具参考](docs/tools-reference.md) | Tool Registry 与各域工具说明 |
| [桌面打包与发版](docs/desktop-packaging.md) | 未签名安装包、SmartScreen/Gatekeeper、tag 发版 |

---

## 本地数据说明

以下目录/文件为**本地运行时数据**，已在 `.gitignore` 中排除，请勿提交至 Git：

| 路径 | 内容 |
|------|------|
| `data/` | 项目、剧本、媒体、对话、AI 配置 |
| `.env` | 环境变量与 API Key |
| `.remotion/` | Remotion headless Chrome（若使用） |

---

## License

Private / 内部项目。使用前请确认各 LLM、生图、TTS 服务商的使用条款。
