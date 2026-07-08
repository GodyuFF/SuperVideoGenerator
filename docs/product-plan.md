# SuperVideoGenerator 产品计划手册

> 版本：v0.1  
> 更新日期：2026-07-05  
> 状态：规划阶段

---

## 目录

1. [产品概述](#1-产品概述)
2. [目标用户与核心价值](#2-目标用户与核心价值)
3. [产品形态与页面布局](#3-产品形态与页面布局)
4. [领域模型与资产体系](#4-领域模型与资产体系)
5. [项目配置](#5-项目配置)
6. [视频生产模式](#6-视频生产模式)
7. [主 Agent：ReAct 编排](#7-主-agent-react-编排)
8. [子 Agent 设计](#8-子-agent-设计)
9. [RAG 资产复用](#9-rag-资产复用)
10. [可视化看板](#10-可视化看板)
11. [编辑权限与 CRUD 规则](#11-编辑权限与-crud-规则)
12. [技术架构](#12-技术架构)
13. [API 与实时事件](#13-api-与实时事件)
14. [实施路线图](#14-实施路线图)
15. [待确认与开放项](#15-待确认与开放项)

---

## 1. 产品概述

**SuperVideoGenerator** 是一款基于多 Agent 协作的 AI 视频生成产品。用户通过自然语言对话描述创意，系统由主 Agent（超级视频大师）以 **ReAct** 模式编排多个专业子 Agent，完成从剧本、素材、分镜、配音到成片的全流程生产。

### 1.1 产品定位

| 维度 | 说明 |
|------|------|
| 核心能力 | 剧本驱动 + 资产化管理 + 可复用共享池 + 可视化关系看板 |
| 交互范式 | 左侧对话驱动 AI，右侧剧本页手工精修资产 |
| 编排模式 | 先规划可见、可审、可改，再按步骤执行 |
| 差异化 | 跨剧本 RAG 复用人物/道具/场景；未执行态全资产可 CRUD |

### 1.2 核心原则

1. **一切可追踪**：每个实体均有全局唯一 `asset_id`（UUID + 类型前缀）。
2. **分层资产**：文字资产与数字资产分离，数字资产可回溯来源。
3. **引用即约束**：存在引用关系的资产不可删除，UI 展示引用链。
4. **共享有边界**：仅人物、道具、场景跨剧本共享；剧情与分镜剧本私有。
5. **手改优先**：未执行态支持全量 CRUD，便于用户微调后再交给 AI 分析生成。

---

## 2. 目标用户与核心价值

### 2.1 目标用户

- 短视频 / 解说类内容创作者
- 需要批量生产系列剧集的 MCN / 工作室
- 希望用 AI 降本增效的视频制作团队

### 2.2 用户价值

| 价值点 | 说明 |
|--------|------|
| 降低重复劳动 | RAG 检索复用已有人物、场景、道具 |
| 可控可审 | Plan 阶段预览全流程，支持手动确认后再执行 |
| 精细调控 | 右侧资产库对未执行剧本全量增删改 |
| 关系透明 | 看板展示资产关联、RAG 复用、派生关系 |
| 模式灵活 | 动态图片模式（低成本）与 AI 视频模式（高质量）可选 |

---

## 3. 产品形态与页面布局

### 3.1 主工作台布局（两阶段）

**阶段 A — 项目级整体看板**（全宽，无对话）：

```
┌─────────────────────────────────────────────────────────────────────┐
│  SuperVideoGenerator    [项目]  [配置]                               │
├─────────────────────────────────────────────────────────────────────┤
│  Tab: 整体看板 | 图文资产（项目共享池）                              │
│  · 剧本卡片列表 + 「新建剧本」                                       │
│  · 点击「进入剧本」→ 进入阶段 B                                      │
└─────────────────────────────────────────────────────────────────────┘
```

**阶段 B — 剧本工作台**（左对话 + 右看板，进入某剧本后加载）：

```
┌─────────────────────────────────────────────────────────────────────┐
│  SuperVideoGenerator  [剧本标题] [状态]  [返回整体看板]              │
├──────────────────┬──────────────────────────────────────────────────┤
│  左侧 ~35%       │  右侧 ~65%  剧本页                                │
│  对话区          │  Tab: 剧本详情 | 层级2（角色/分镜/剪辑…）         │
│  [输入框]        │  PlanPanel + 看板内容                             │
└──────────────────┴──────────────────────────────────────────────────┘
```

刷新页面时：若 URL 为 `#/project/{id}/script/{sid}` 或 localStorage 记录上次会话，自动恢复项目/剧本工作台。

### 3.1.1 应用入口（项目列表）

| 路由 | 页面 |
|------|------|
| `#/` | **项目列表**：展示全部项目，支持多选批量删除、新建项目 |
| `#/project/{projectId}` | **项目看板**（整体看板 / 图文资产；可新建/删除剧本） |
| `#/project/{projectId}/script/{scriptId}` | **剧本工作台**（对话 + 看板） |
| `#/logs` | **交互日志**（全部项目） |
| `#/project/{projectId}/logs` | **交互日志**（当前项目） |
| `#/project/{projectId}/script/{scriptId}/logs` | **交互日志**（当前剧本） |

点击项目卡片进入项目看板；顶栏「← 项目列表」返回首页。删除项目/剧本时同步清理 `data/projects/` 目录与 `conversations.db`（交互日志保留，可在日志页按项目+日期手动删除）。**启动时**后端会从 `data/projects/` 扫描 `project.json` / `script.json`，补齐 `dev_store.json` 中缺失的项目（图文资产等完整数据仍以 `dev_store.json` 为准）。

**交互日志页**：支持按日期筛选、类型筛选；全局视图（`#/logs`）可选择项目后删除指定日期的 SQLite + JSONL 记录；项目/剧本上下文进入时项目已锁定，删除前二次确认且不可恢复。

### 3.2 区域职责

| 区域 | 职责 |
|------|------|
| **项目看板** | 多剧本总览、项目共享图文资产、新建剧本；**不加载** WebSocket / 对话 |
| **左侧对话** | 仅在进入剧本后加载；与 Director / 子 Agent 交互 |
| **右侧剧本页** | 当前 `active_script_id`：剧本详情 + 层级 2 看板 + PlanPanel |
| **项目配置页** | LLM / 生图 / 生视频 / TTS / 视频风格五类配置 |
| **项目切换器** | 可仅切换项目（回整体看板）或点选剧本（直达剧本工作台） |

### 3.3 右侧剧本页 Tab 结构

| Tab | 功能 | CRUD |
|-----|------|------|
| **剧本正文** | 聚合编辑 plot / narration；底层同步文字资产 | 未执行态 ✅ |
| **资产库** | 人物/道具/场景/声音/剧情等分类列表 + 详情抽屉 | 未执行态 ✅（主 CRUD 入口） |
| **视频计划稿** | 镜头列表、运镜、时长、关联素材、配音文案 | 未执行态 ✅ |
| **关系看板** | 当前剧本子图 + 共享池邻接；双击跳转编辑 | 查看为主，跳转资产库编辑 |

### 3.4 左右联动

- 对话产生新资产 → WebSocket 推送 → 右侧资产库实时刷新
- 用户右侧手改资产 → 标记 `user_edited=true` → 可选同步 Agent 上下文
- 执行开始 → 右侧 CRUD 禁用，进入只读预览
- Plan 完成后继续改资产 → 软提示「建议重新 Plan」（不阻塞编辑）

### 3.5 Skill 与目标模式

| 能力 | 说明 |
|------|------|
| **Skill（单轮）** | 消息以 `/skillId` 开头（如 `/thriller 做悬疑短片`），仅当前轮注入 Skill 提示词与设定；输入 `/` 弹出可选 Skill 列表；`GET /api/skills` 列出内置 Skill |
| **目标模式** | 项目配置 `execution_mode=goal` 或工作台开关；AI 自主执行至成功/失败，不调用 `ask_user_question`、不弹出任何 A2UI 确认 |

---

## 4. 领域模型与资产体系

### 4.1 层级结构

```
Project（项目）
├── ProjectConfig（五类配置）
├── SharedAssetPool（共享资产池）
│   ├── character（人物）    ← 项目级共享
│   ├── prop（道具）         ← 项目级共享
│   └── scene（空镜）        ← 项目级共享；生图为无人物环境背景板，供 frame 合成
└── Script × N（剧本/章节，粒度用户确认）
    ├── plot / narration（剧情、旁白）     ← 剧本私有
    ├── VoiceRoleAsset（声音角色）         ← 关联人物或旁白
    ├── VideoPlan（视频计划稿）
    │   └── Shot × M（镜头）
    ├── ImageAsset（图片，可预生成）
    ├── VideoAsset（AI 视频，ai_video 模式）
    ├── TTSAsset（配音）
    └── FinalVideoAsset（成片）
```

### 4.2 剧本粒度（用户确认驱动）

剧本结构不由系统硬编码，由 Director 在 Plan 阶段生成候选，用户在 UI 确认后锁定。

| 粒度模式 | 结构 | 适用场景 |
|----------|------|----------|
| `single` | Project → 1 Script | 30s–3min 短视频 |
| `chapter` | Project → N Script（章节） | 分集解说、多段剧情 |
| `series` | Project → Season → Episode | 连续剧、系列 IP |
| `custom` | 用户编辑后确认 | 特殊结构 |

Plan 步骤 `script_structure_proposal` 输出候选结构，状态 `awaiting_user_confirmation`，确认后写入 `script_structure_version`。

### 4.3 资产类型与 ID 规范

**ID 格式**：`{prefix}_{uuid}`

| 前缀 | 类型 | 大类 |
|------|------|------|
| `txt_` | 文字资产（character/prop/scene/plot/narration） | 文字 |
| `voc_` | 声音角色资产 | 文字 |
| `plan_` | 视频计划稿 | 计划 |
| `shot_` | 镜头 | 计划 |
| `img_` | 图片数字资产 | 数字 |
| `vid_` | AI 视频数字资产 | 数字 |
| `tts_` | 配音数字资产 | 数字 |
| `fin_` | 成片数字资产 | 数字 |

### 4.4 共享 vs 私有

| 资产类型 | 默认归属 | 跨剧本共享 |
|----------|----------|------------|
| `character` | Project 共享池 | ✅ |
| `prop` | Project 共享池 | ✅ |
| `scene` | Project 共享池 | ✅ |
| `plot` | Script 私有 | ❌ |
| `narration` | Script 私有 | ❌ |
| `voice_role` | Script 级（绑人物/旁白） | 人物声线可跨片引用人物 |
| `video_plan` / `shot` | Script 私有 | ❌ |
| `image` / `video` / `tts` / `final` | 默认 Script 私有 | 可被其他 Script 只读引用 |

**数据字段示意**：

```typescript
interface TextAsset {
  id: string;
  project_id: string;
  scope: "project_shared" | "script_private";
  script_id?: string;           // script_private 时必填
  type: "character" | "prop" | "scene" | "plot" | "narration";
  name: string;
  content: Record<string, unknown>;
  embedding_id?: string;
  source_script_id?: string;  // 首次创建来源
  primary_media_id?: string;
  reuse_policy: "shared" | "private";
  status: AssetStatus;
  user_edited: boolean;
}
```

**图文资产 content**（`type` 为 `character` | `prop` | `scene`，存储于 `TextAsset.content`）：

| 字段 | 说明 |
|------|------|
| `summary` | 卡片一句话摘要 |
| `description` | 主视觉描述（生图主文案，必填） |
| `visual_style` / `color_palette` | 画风与主色调 |
| `tags` | 标签数组 |
| `prompt_hint` | 生图增强 prompt（LLM 填写，纳入组装） |
| `image_prompt` | 系统组装的最终生图 prompt（可用户锁定覆盖） |
| `negative_prompt` | 负向 prompt |
| `prompt_version` / `prompt_locked` | 组装器版本 / 用户锁定标志 |
| `display_mode` | `static_image` \| `dynamic_image` |
| `notes` | 创作备注 |
| character 扩展 | 原 6 字段 + `ethnicity`, `body_type`, `height`, `build`, `hair_style`, `hair_color`, `eye_color`, `facial_features`, `default_expression`, `default_pose`, `accessories` |
| scene 扩展 | 原 6 字段 + `architecture_style`, `key_objects`, `foreground`, `background`, `camera_angle`, `depth_of_field`, `color_tone` |
| prop 扩展 | 原 5 字段 + `shape`, `color`, `texture`, `brand_style`, `visual_details` |
| `image_variants[]` | 多图变体：`kind`（base/expression/pose/action…）、`label`、`meaning`、`variant_prompt`、`media_id`；`description` 为设定主形象，衍生变体以 base 为 reference 生图 |
| 生图策略 | **scene**：空镜背景板（establishing plate），无人物/动物/独立道具主体；`key_objects` 仅环境固定陈设（非 prop 资产）；**character/prop**：绿幕 `#00FF00` 生图后 FFmpeg colorkey 抠透明 PNG（`core/assets/chroma_key.py`） |

旧键 `appearance` 加载时合并入 `description`。图片仍通过 `MediaAsset` + `generates` 关联；`primary_media_id` 固定指向 base 变体 media。

### 4.5 引用关系

独立表 `asset_references` 记录所有关联，支撑删除守卫与看板构图。

| relation | 含义 |
|----------|------|
| `uses` | Script/plot/shot 引用某资产 |
| `derived_from` | fork 派生自某共享资产 |
| `rag_reuse` | RAG+Judge 产生的复用（审计） |
| `generates` | 文字资产 → 图片/视频等数字资产 |
| `voice_of` | 声音角色绑定人物文字资产 |

**删除规则**：存在 `uses` / `generates` / `derived_from` 子引用时禁止删除；UI 展示完整引用链。

---

## 5. 项目配置

配置挂在 **Project 级**，子 Agent 执行时读取 `ProjectConfig`；修改仅影响后续 Plan 步骤（`config_version` 版本化）。

### 5.1 配置页面清单

| # | 配置页 | 主要字段 |
|---|--------|----------|
| 1 | **LLM 模型配置** | provider、model、apiKeyRef、temperature、maxTokens |
| 2 | **AI 生图模型配置** | provider（默认 `agnes`）、model（`agnes-image-2.1-flash`）、apiKey（`SVG_IMAGE_GEN_API_KEY` / `AGNES_API_KEY`）、defaultSize（`1024x768`）；图生图 `img2img_model` 默认同 2.1 |
| 3 | **AI 视频模型配置** | enabled、provider、model、maxDurationSec、supportedModes（图生视频/首尾帧）、resolution |
| 4 | **TTS 模型配置** | provider、model、defaultLanguage、sampleRate |
| 5 | **视频风格配置** | mode（动态图片/视频生成）、aspectRatio、transition、watermarkFreeImagesOnly、bgmEnabled |

### 5.2 剧本与 RAG 配置（增补）

```typescript
interface ProjectConfig {
  llm: { ... };
  imageGen: { ... };
  videoGen: { ... };
  tts: { ... };
  style: {
    mode: "dynamic_image" | "ai_video";
    aspectRatio: "16:9" | "9:16" | "1:1";
    transition: string;
    watermarkFreeImagesOnly: boolean;
    requireAiVideo: boolean;
    bgmEnabled: boolean;
  };
  script: {
    granularity: "pending" | "single" | "chapter" | "series" | "custom";
    requireUserConfirm: true;
  };
  rag: {
    enabled: boolean;
    topK: number;                 // 默认 10
    similarityThreshold: number;    // 默认 0.75
    reuseAggression: "conservative" | "balanced" | "aggressive";
    autoForkOnConflict: boolean;
    indexTypes: ["character", "prop", "scene"];
  };
}
```

---

## 6. 视频生产模式

> **更新 2026-06-29**：视频风格三分——动态图文、动态漫画、AI 视频；动态图文/漫画共用「文字设计 → 图片 → 分镜 → TTS → 剪辑」路径（无 `video_gen`）。

### 6.1 模式对比

| 模式 | 标识 | Video Agent | TTS | 剪辑输入 |
|------|------|-------------|-----|----------|
| **动态图文模式** | `dynamic_image` | 不调用 | 必须（分镜含配音文案） | 讲解类配图 + Ken Burns 运镜 + 配音 |
| **动态漫画模式** | `dynamic_comic` | 不调用 | 必须 | 漫画分格配图 + 运镜 + 配音/对白 |
| **AI 视频模式** | `ai_video` | 必须 | 按镜头 | AI 视频片段 + 配音 + 合成 |

### 6.2 流水线差异

**动态图文 / 动态漫画**（`core/llm/master/actions.py` → `pipeline_for_style`）：

```
剧本 Agent（剧情/角色/道具/场景文字）
  → 图片 Agent（批量生图或搜索，可 A2UI 选择）
  → 分镜 Agent → TTS Agent → 剪辑 Agent → 成片
```

**AI 视频模式**：

```
分镜 Agent → [图片 Agent 补图] → Video Agent → TTS Agent → 剪辑 Agent → 成片
```

### 6.3 图文配置（ImageTextConfig）

| 字段 | 说明 |
|------|------|
| `source_mode` | `generate` / `search` / `user_choice`（图片步骤前弹窗） |
| `image_text_preset` | 图文子风格：`explainer` / `report` / `lecture` |
| `comic_preset` | 漫画画风：`manga` / `webtoon` / `ink` |
| `batch_pending_assets` | 是否批量处理所有缺图文字资产 |
| `allow_search_fallback` | 生图失败时是否允许搜索回退 |

- 项目级：`ProjectConfig.image_text`（PATCH `/api/projects/{id}/config`）
- 全局默认：AI 配置页 → `/api/ai/config` → `image.pipeline`（原 `LLMConfigManager.image_text_defaults`）

### 6.4 动态图文策略补充（2026-07-04）

| 阶段 | 行为 |
|------|------|
| 图片完善 | `image_agent`：`generate_images` 或 `search_images`；**仅搜图**后 `sync_text_from_image` 白名单 auto-patch（`color_palette` 等），生图产出无需 sync；`description/summary` 重大变更需 `apply_major_changes` 或 `update_*` |
| 配图 | `image_agent` 两阶段（单次委派）：`character/prop/scene` 文生图 → `frame` 多参考图生图（分镜创建 frame 后） |
| 分镜 | `storyboard_agent`：`load_context` → `create_shots` → `create_frames` → `persist_plan` |
| 主编排顺序 | `script_design` → `storyboard` → `image_gen` → `tts_gen` → `edit_compose` |
| 剪辑计划 + 成片 | **TTS 之后** `editing_agent`：`load_edit_context` → `plan_edit_timeline` → `validate_edit_assets` →（缺失则 `report_missing_assets` 上报主编排）→ `gather_media` → `compose_final`；主编排可据缺失项重委派 `script_design` / `image_gen` / `tts_gen` / `storyboard` |
| 剪辑看板 | 看板 Tab `edit`：只读多轨时间轴（含 `edit_description`、转场、背景、source_refs 摘要） |
| 成片 | **dynamic_image/comic**：`EditTimeline` → FFmpeg `compose_final`（运镜/转场/背景/字幕/配音）；**ai_video**：`video_agent.generate_from_timeline` → `editing_agent` 混流 |

实体：`EditTimeline` / `EditClip`（[`core/models/entities.py`](../core/models/entities.py)），持久化 `dev_store.json` → `edit_timelines`。

---

## 7. 主 Agent：ReAct 编排

### 7.1 Director 职责

- 理解用户意图，生成结构化 `PlanDocument`
- 按依赖拓扑调度子 Agent
- 推送 WebSocket 事件驱动 UI
- 失败时触发 Replan（局部或全局）
- 识别 `user_edited` 资产，支持增量 Replan

### 7.2 三阶段循环

```
Plan（规划）→ Execute（执行）→ [Replan（重规划）]
```

| 阶段 | 输出 | UI 表现 |
|------|------|---------|
| Plan | `PlanDocument`（步骤 + 依赖 + 资产目标） | 计划列表 / DAG；可选手动确认 |
| Execute | 逐步 `StepResult`、数字资产文件 | 步骤状态、进度条、产物预览 |
| Replan | 新版 `PlanDocument`（version++） | 计划更新通知、受影响步骤高亮 |

**MVP 已落地**：Execute 阶段每轮 ReAct 注入 `PlanDocument` 快照，LLM 回写 `plan_status` / `remaining_plan` 至 `runtime_summary` 与 WS `plan_updated`（见 `core/llm/plan_context.py`）。独立 Plan 预览 UI 与人工审批流仍待后续迭代。

### 7.3 PlanDocument 结构

```typescript
interface PlanDocument {
  version: number;
  goal: string;
  constraints: {
    durationSec: number;
    aspectRatio: string;
    style: string;
  };
  steps: PlanStep[];
}

interface PlanStep {
  id: string;
  type: string;           // 见下表
  title: string;
  description: string;
  agent: string;
  dependsOn: string[];
  status: "pending" | "running" | "completed" | "failed" | "skipped";
  progress?: number;
  outputs?: StepOutput[];
}
```

### 7.4 标准 Plan 步骤序列

| 顺序 | step type | 子 Agent | 说明 |
|------|-----------|----------|------|
| 1 | `script_structure_proposal` | Director | 粒度提案，待用户确认 |
| 2 | `script_design_with_rag` | 剧本 Agent | 剧情设计 + RAG 实体解析 |
| 3 | `text_asset_resolve` | 剧本 Agent | RAG 检索 + 复用判定 |
| 4 | `voice_role_create` | 剧本 Agent | 声音角色资产 |
| 5 | `image_gen` | 图片 Agent | 为缺图文字资产生图（并发 Agnes API；前端 `ImageGenProgressModal` 逐张进度，完成后看板刷新） |
| 6 | `storyboard` | 分镜 Agent | 视频计划稿 + 镜头 |
| 7 | `video_gen` | 视频 Agent | 仅 ai_video 模式 |
| 8 | `tts_gen` | TTS Agent | 按镜头/计划稿生成配音 |
| 9 | `edit_compose` | 剪辑 Agent | FFmpeg 合成成片（dynamic 模式） |
| 10 | `qa` | 质检（可选 P2） | 一致性检查 |

---

## 8. 子 Agent 设计

> **提示词**：各 Agent 的固定角色说明与行动约束存放在 [`core/llm/prompt/agents/*/fixed/`](../core/llm/prompt/agents/)，动态上下文由 `PromptBuilder` + `AgentContextManager` 按轮次注入。详见 [提示词架构](prompt-architecture.md)。

### 8.1 剧本 Agent（Script Agent）

**职责**：内容创作的入口 Agent，管理剧本与文字/声音资产。

| 能力 | 输入 | 输出 | 删除约束 |
|------|------|------|----------|
| 对话/PDF 解析生成剧本 | prompt / PDF | Script + plot 资产 | 无数字资产、无引用 |
| 章节/时长设计 | 总时长、章节数 | 多 Script 或章节结构 | 同上 |
| LLM 剧情设计 | 创意描述 | plot、剧情结构 | — |
| 角色/道具/场景设计 | 剧本内容 | 共享文字资产 | 无图片/分镜/声音引用 |
| RAG 实体解析 | 实体需求列表 | reuse/fork/create | — |
| 声音角色设定 | 角色 + TTS 配置 | VoiceRoleAsset | 无 TTS/分镜引用 |
| 旁白声音设定 | 剧本 | narrator_voice | 同上 |

**Tool 接口**（产品层通用 CRUD 命名；**当前实现**为 type-specific action，与 Registry input_schema 对齐）：

```
# 产品层（目标 API 语义）
script.parse_from_chat(project_id, message)
...
# 当前 ReAct action（core/llm/tools/bootstrap.py）
parse_brief / update_script
create_plot | create_character | create_scene | create_prop   # create 强校验全字段 content
update_* / delete_*                                          # update 支持 partial content merge
list_text_assets                                             # 只读，Registry 直调
read_webpage(url)                                            # script_agent + 主编排；拒绝 localhost/内部 API
```

**共享只读 Tool**（`agent=common`；bootstrap 注入 `script_agent`，主编排为 `tool_read_webpage`；storyboard/tts/editing/image/video **不注入**）：

| action | 说明 |
|--------|------|
| `read_webpage` | 抓取公网 URL HTML 并提取正文；拒绝 localhost/内网与 `/api/projects/` 路径 |

create_* 路径禁止字符串/observation 降级落盘；字段名统一 `content_md`（剧本正文）。

### 8.2 图片素材 Agent（Image Asset Agent）

| 能力 | 说明 |
|------|------|
| 按文字资产生图 | 调用 `imageGen` 配置，1:1 关联 |
| 重新生成 | 新 image_id，旧图标记 superseded |
| 删除 | 无分镜/剪辑/成片引用 |

```
image.generate(text_asset_id, overrides?)
image.regenerate(image_asset_id)
image.delete(image_asset_id)
```

### 8.3 分镜 Agent（Storyboard Agent）

| 能力 | 说明 |
|------|------|
| 生成视频计划稿 | 基于剧本、文字资产、视频配置 |
| 镜头设计 | 运镜、时长、关联素材 |
| 配音文案 | `dynamic_image` 模式必填 |

**VideoPlanShot 结构**：

```json
{
  "shot_id": "shot_xxx",
  "order": 0,
  "duration_ms": 4000,
  "camera_motion": "ken_burns_in",
  "narration_text": "……",
  "asset_refs": {
    "characters": ["txt_char_1"],
    "scenes": ["txt_scene_1"],
    "images": ["img_1"],
    "props": ["txt_prop_2"]
  },
  "ai_video_hint": {
    "mode": "image_to_video",
    "first_frame_image_id": "img_1",
    "last_frame_image_id": null
  }
}
```

```
storyboard.generate(script_id)
storyboard.update_shot(shot_id, patch)
storyboard.delete_plan(plan_id)
storyboard.delete_shot(shot_id)
```

### 8.4 视频 Agent（Video Agent）

仅在 `style.mode === "ai_video"` 时调度。

| 能力 | 说明 |
|------|------|
| 图生视频 | `image_to_video` |
| 首尾帧生成 | `first_last_frame` |
| 时长约束 | `duration_ms ≤ videoGen.maxDurationSec` |

```
video.generate_for_shot(shot_id)
video.regenerate(video_asset_id)
video.delete(video_asset_id)
```

### 8.5 TTS Agent（已接入）

| 能力 | 说明 |
|------|------|
| 按镜头生成配音 | 从 `VideoPlan.shots[].narration_text` 合成 mp3，写入 `MediaAsset(AUDIO)`，`metadata.shot_id` |
| 多引擎 | Edge TTS（默认）、OpenAI、Azure v2、SiliconFlow、Gemini、MiMo、`no-voice` |
| 批量生成 | `synthesize` 并发（默认 3）；失败 3 次重试后 `TtsAbortError` 中止步骤 |
| 合成试听 | 落盘 mp3 经 `resolve_media_access()` 转为 `/api/projects/.../assets/media/{filename}`；前端 `MediaPreview` 内嵌 `<audio controls>` |

实现：`core/tts/` + `core/llm/tools/tts/synthesize.py`；剪辑时间轴通过 `build_tts_by_shot()` 自动关联配音时长。

**合成结果试听入口**（无需下载，页面内直接播放）：

| 位置 | 说明 |
|------|------|
| 计划面板 `PlanPanel` | TTS 步骤 `outputs`（`kind=audio`）内嵌播放器 |
| 看板 · 分镜 `storyboard` | 每镜 `tts_audio_url` + 时长 |
| 看板 · 媒体 `media` | 音频类资产卡片播放器 |
| 看板 · 剪辑 `edit` | 音频轨 clip 下方「配音试听」列表（`preview_url`） |
| AI 配置页 TTS Tab | 短文本 `POST /api/ai/tts/preview` 试听（配置验证，非成片） |

### 8.6 剪辑 Agent（Editing Agent）

| 能力 | 说明 |
|------|------|
| 计划稿 | TTS 之后：`load_edit_context` → `plan_edit_timeline`（三轨 + 运镜/转场/背景/source_refs）→ `validate_edit_assets` |
| 缺失闭环 | 校验不通过时 `report_missing_assets`；主编排据 `suggested_upstream` 重委派上游后再 `delegate_edit_compose` |
| 动态图片模式 | 图片轨道 + 运镜（Ken Burns/平移）+ 配音 |
| AI 视频模式 | 视频轨道拼接 + 配音 |
| 混音 | BGM、音量平衡 |
| 导出 | `compose_final` 前硬校验素材与 **edit capabilities**；FFmpeg 渲染 → `assets/exports/` |

```
load_edit_context → plan_edit_timeline → validate_edit_assets
  → report_missing_assets（缺失）| gather_media → compose_final（就绪）
```

---

## 9. RAG 资产复用

### 9.1 适用范围

仅对 **项目共享池** 三类文字资产建立向量索引：`character`、`prop`、`scene`。

### 9.2 流程

```
识别本集实体需求 → 构造 RAG Query → 向量检索 Top-K
→ 硬规则过滤 → LLM Reuse Judge → reuse / fork / create_new
→ 写入资产 + 更新索引 + 建立引用边（rag_reuse）
```

### 9.3 两阶段检索

| 层级 | 检查项 | 动作 |
|------|--------|------|
| 硬规则 | project_id、type 一致；资产有效 | 不合格剔除 |
| 相似度 | score < threshold（默认 0.75） | 不进入 LLM |
| LLM 语义 | 人设/外观是否冲突 | reuse / fork / reject |
| LLM 剧情 | 世界观一致性 | 冲突 → fork 或 create_new |
| 用户策略 | reuseAggression | 保守少复用，激进多复用 |

### 9.4 判定结果

| decision | 行为 |
|----------|------|
| `reuse` | 本片建立 `uses` 边，直接引用共享资产（含已有图片只读引用） |
| `fork` | 共享池新增变体，`derived_from` 指向原资产，重新入索引 |
| `create_new` | 新建共享资产，入索引，供后续 RAG |

### 9.5 ReuseDecision Schema

```typescript
interface ReuseDecision {
  requirement_id: string;
  requirement_summary: string;
  decision: "reuse" | "fork" | "create_new";
  selected_asset_id?: string;
  fork_patch?: object;
  reason: string;
  confidence: number;
}
```

### 9.6 RAG 审计

剧本 Agent 执行后，左侧对话区展示 RAG 摘要；资产库/看板可展开审计面板：query、Top-K 候选、Judge 结果。用户可手动改为「强制新建」或「强制复用」。

---

## 10. 可视化看板

### 10.1 默认视图

- **默认**：`active_script_id` 子图 + 与之相连的共享池节点
- **可选**：全项目视图（所有 Script + 共享池）

### 10.2 布局示意

```
┌─ 关系看板（当前剧本子图）────────────────────────────┐
│  [共享池泳道]                                          │
│  人物 · 道具 · 场景  （徽章: 被 N 个剧本引用）         │
│       ↓ uses / derived_from                           │
│  [当前剧本 Script]                                     │
│    ├── plot / narration                               │
│    ├── voice_role                                     │
│    ├── video_plan → shots                             │
│    └── 数字资产 image / video / tts / final           │
└──────────────────────────────────────────────────────┘
```

### 10.3 节点样式

| 节点类型 | 颜色 | 展开内容 |
|----------|------|----------|
| 项目 | 深蓝 | 配置摘要、模式 |
| 剧本 | 蓝 | 章节、时长、正文预览 |
| 文字资产 | 绿 | 结构化 JSON / Markdown |
| 声音角色 | 紫 | TTS 参数、试听 |
| 图片 | 橙 | 缩略图 |
| 计划稿/镜头 | 青 | 运镜、关联列表 |
| 视频/TTS/成片 | 红 | 播放器 |

### 10.4 看板 Tab 层级（前端）

| 模式 | 层级 1 | 层级 2 |
|------|--------|--------|
| **项目级** | `overview` 整体看板、`knowledge` 项目共享图文 | 无 |
| **剧本级** | `script_details` 单剧本详情 | `script` / `character` / `scene` / `prop` / `frame` / `storyboard` / `edit` / `media` / `pipeline` |

### 10.5 剪辑工作室（edit）

- 看板 API：`GET /api/projects/{id}/board/edit?script_id=…`
- **Edit Studio**：`GET/PATCH .../edit-timeline`（revision 乐观锁）；`POST .../export` FFmpeg 异步导出
- 前端：[`EditStudio.tsx`](../apps/web/src/edit/EditStudio.tsx) 可拖拽三轨 + Canvas 预览 + ClipInspector
- 规格：[`edit-studio-plan.md`](edit-studio-plan.md)

### 10.6 边样式

| 边类型 | 样式 |
|--------|------|
| `uses` | 实线箭头 |
| `derived_from` | 实线箭头 + 「派生」标签 |
| `rag_reuse` | 虚线 + 「RAG 复用」标签 |
| `generates` | 实线 + 「生成」标签 |

### 10.5 交互

- 点击节点 → 详情面板 + 引用/被引用列表
- 双击节点 → 跳转资产库编辑（未执行态）
- 执行中步骤 → 节点边框动画 + status 徽章
- 筛选：类型、状态、RAG 边、user_edited

---

## 11. 编辑权限与 CRUD 规则

### 11.1 剧本状态与编辑权限

| script.status | 含义 | 右侧 CRUD |
|---------------|------|-----------|
| `draft` | 草稿 | ✅ 全量 |
| `planned` | 已有 Plan，未执行 | ✅ 全量（改后软提示 Replan） |
| `executing` | 执行中 | ❌ 只读 |
| `completed` | 已完成 | ❌ 只读（P2 可选解锁） |
| `failed` | 失败 | ❌ 只读或仅改失败相关 |

**未执行态** = `script.status ∈ { draft, planned }` 且资产 `status !== locked`。

### 11.2 资产状态

| status | 未执行剧本下 |
|--------|--------------|
| `draft` / `ready` | 增删改 ✅ |
| `locked` | 只读 |
| `generated` | 改 ✅；删 ❌（有 generates 引用） |
| `archived` | 隐藏，可恢复 |

### 11.3 CRUD 矩阵（未执行态）

| 资产类型 | 增 | 改 | 删 |
|----------|----|----|-----|
| Script | — | ✅ | ✅ 无引用时 |
| plot / narration | ✅ | ✅ | ✅ 无引用 |
| character / prop / scene | ✅ 进共享池 | ✅ | ✅ 无跨剧本/分镜引用 |
| voice_role | ✅ | ✅ | ✅ 无 TTS/分镜引用 |
| video_plan / shot | ✅ | ✅ | ✅ 无下游 |
| image（预生成） | ✅ | ✅ | ✅ 无分镜/剪辑引用 |
| ai_video / tts / final | 执行后产生 | 执行后 | 执行后 |

### 11.4 共享资产删除 vs 解除引用

- **解除本片引用**：仅删除 `uses` 边，共享实体保留
- **从项目删除**：删除共享实体本身（需无跨剧本引用）

### 11.5 守卫中间件

`ScriptEditGuard`：`executing` 态（AI 执行中）→ 403；`draft` / `planned` / `completed` / `failed` 允许人工 CRUD  
`ReferenceGuard.can_delete(asset_id)`：有引用 → 拒绝 + 返回引用链

---

## 12. 技术架构

### 12.1 系统分层

```
┌─────────────────────────────────────────────────────────┐
│  前端 Web UI（Vite + React + TypeScript）                │
│  shadcn/ui + Tailwind + @xyflow/react                   │
├─────────────────────────────────────────────────────────┤
│  API 层（FastAPI：REST + WebSocket）                     │
├─────────────────────────────────────────────────────────┤
│  核心编排层                                              │
│  Director（ReAct 编排 / Executor / Replanner）            │
│  Agent Registry + 事件总线                               │
├─────────────────────────────────────────────────────────┤
│  子 Agent 层                                             │
│  Script / Image / Storyboard / Video / TTS / Editing     │
├─────────────────────────────────────────────────────────┤
│  支撑服务                                                │
│  RAG（Indexer / Retriever / ReuseJudge）                 │
│  ReferenceGuard / GraphBuilder / ScriptEditGuard         │
├─────────────────────────────────────────────────────────┤
│  工具层                                                  │
│  LLM / 生图 / 生视频 / TTS / FFmpeg                      │
├─────────────────────────────────────────────────────────┤
│  存储                                                    │
│  dev_store.json（MemoryStore 索引）+ data/projects/ 目录双写 │
│  SQLite（MVP）→ PostgreSQL                               │
│  本地 assets/ 文件存储 → S3（生产）                      │
│  向量库：Chroma/sqlite-vec（MVP）→ pgvector              │
└─────────────────────────────────────────────────────────┘
```

### 12.2 目录结构

```
SuperVideoGenerator/
├── apps/
│   ├── web/                          # React 前端
│   │   ├── layouts/ScriptWorkbench.tsx
│   │   ├── panels/ChatPanel/
│   │   ├── panels/ScriptPanel/
│   │   └── pages/ProjectConfig/
│   └── api/                          # FastAPI
│       ├── routes/
│       └── websocket/
├── core/
│   ├── super_video_master/           # 主编排入口
│   ├── llm/                          # LLM 客户端 + master/ 主编排 ReAct
│   ├── conversation/                 # 主/子 Agent 会话隔离
│   ├── prompt/                       # 提示词：fixed 角色 + dynamic 模板 + 滑窗压缩
│   ├── agents/
│   │   ├── script_agent/
│   │   ├── image_agent/
│   │   ├── storyboard_agent/
│   │   ├── video_agent/
│   │   ├── tts_agent/
│   │   └── editing_agent/
│   ├── models/                       # Pydantic 模型
│   ├── rag/                          # indexer, retriever, reuse_judge
│   ├── references/                   # ReferenceGuard
│   ├── graph/                        # SubgraphBuilder
│   └── guards/                       # ScriptEditGuard
├── tools/                            # 外部 API 封装
│   ├── llm/
│   ├── image_gen/
│   ├── video_gen/
│   ├── tts/
│   └── ffmpeg/
├── storage/
│   ├── assets/
│   └── projects/
├── config/
├── tests/
└── docs/
    └── product-plan.md               # 本文档
```

### 12.3 技术选型

| 层级 | 选型 | 说明 |
|------|------|------|
| 前端 | Vite + React + TypeScript | 轻量工作台 |
| UI | Tailwind + shadcn/ui | 组件库 |
| 关系图 | @xyflow/react | 看板 DAG |
| 状态 | Zustand + React Query | 项目状态与缓存 |
| 实时 | WebSocket | 执行事件推送 |
| 后端 | FastAPI | 异步、WebSocket 友好 |
| 编排 | 自研 Plan-Execute（MVP） | 状态清晰 |
| 模型校验 | Pydantic v2 | 全链路 Schema |
| DB | SQLite（MVP） | 渐进扩展 |
| 视频处理 | FFmpeg（成片导出 + TTS/ai_video 混流） | 剪辑导出 |

---

## 13. API 与实时事件

### 13.1 REST API（核心）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/projects` | 创建项目 |
| GET/PATCH | `/api/ai/config` | 统一 AI 配置（`llm` / `image` / `video` / `tts` 分区） |
| GET/PATCH | `/api/llm/config` | LLM 配置（兼容旧版扁平结构） |
| POST | `/api/projects/{id}/scripts` | 创建剧本 |
| GET | `/api/projects/{id}/scripts/{script_id}/assets` | 本片资产列表 |
| POST | `/api/projects/{id}/scripts/{script_id}/assets/text` | 新建文字资产 |
| PATCH | `/api/projects/{id}/assets/{asset_id}` | 更新资产 |
| DELETE | `/api/projects/{id}/assets/{asset_id}` | 删除（ReferenceGuard） |
| POST | `/api/projects/{id}/assets/{id}/link` | 引用共享资产 |
| POST | `/api/projects/{id}/assets/{id}/unlink` | 解除引用 |
| CRUD | `/api/projects/{id}/scripts/{script_id}/plans` | 计划稿 |
| CRUD | `/api/projects/{id}/scripts/{script_id}/plans/{plan_id}/shots` | 镜头 |
| POST | `/api/projects/{id}/scripts/{script_id}/plan` | 触发 Plan |
| POST | `/api/projects/{id}/scripts/{script_id}/execute` | 开始 Execute |
| POST | `/api/projects/{id}/scripts/{script_id}/approve-plan` | 确认计划 |
| GET | `/api/projects/{id}/scripts/{script_id}/graph` | 子图 JSON |
| POST | `/api/projects/{id}/scripts/{script_id}/chat` | 对话消息（body 可选 `conversation_id`） |
| POST | `/api/projects/{id}/scripts/{script_id}/conversations` | 创建对话线程 |
| GET | `/api/projects/{id}/conversations` | 历史对话列表（`?script_id=` 过滤） |
| GET | `/api/projects/{id}/conversations/{conversation_id}/messages` | 唤醒：`?view=ui` 摘要；`?view=full` 完整时间线 |
| WS | `/ws/projects/{id}/scripts/{script_id}` | 实时事件 |

### 13.2 WebSocket 事件

```typescript
type WsEvent =
  | { type: "planning_started" }
  | { type: "plan_ready"; plan: PlanDocument }
  | { type: "plan_updated"; plan: PlanDocument; reason: string }
  | { type: "execution_started" }
  | { type: "execution_paused"; confirmation_id: string; kind: string; conversation_id?: string; step_id?: string }
  | { type: "execution_resumed"; confirmation_id: string; conversation_id?: string }
  | { type: "step_started"; stepId: string }
  | { type: "step_progress"; stepId: string; progress: number }
  | { type: "step_awaiting_confirmation"; step_id: string; step_type: string; kind: string }
  | { type: "step_completed"; stepId: string; outputs: StepOutput[] }
  | { type: "step_resumed"; step_id: string; outputs: StepOutput[] }
  | { type: "step_failed"; stepId: string; error: string }
  | { type: "asset_created"; asset: Asset }
  | { type: "asset_updated"; asset: Asset }
  | { type: "asset_deleted"; assetId: string }
  | { type: "asset_linked"; sourceId: string; targetId: string; relation: string }
  | { type: "rag_search_started"; requirementId: string }
  | { type: "rag_candidate_found"; candidates: RagHit[] }
  | { type: "reuse_decided"; decision: ReuseDecision }
  | { type: "script_locked" }
  | { type: "script_unlocked" }
  | { type: "project_completed"; outputUrl: string }
  | { type: "master_message"; content: string };
```

---

## 14. 实施路线图

### Phase 0：基础骨架（S1–S2）

| 任务 | 交付物 |
|------|--------|
| 项目初始化 | monorepo 结构、依赖、配置 |
| 数据模型 | Pydantic 全量 Schema + SQLite |
| ReferenceGuard | 引用表 + 删除守卫 |
| ScriptEditGuard | 编辑权限中间件 |
| Mock API | 资产 CRUD 可联调 |

### Phase 1：工作台 UI（S3–S4）

| 任务 | 交付物 |
|------|--------|
| ScriptWorkbench 布局 | 左对话 + 右剧本页 |
| 资产库 Tab | 分类列表 + 详情抽屉 + CRUD |
| WebSocket | 事件推送 + 右侧实时刷新 |
| 项目配置页 | 五类配置表单 |
| Mock 数据联调 | 完整 UI 可走通 |

### Phase 2：编排与剧本（S5–S6）

| 任务 | 交付物 |
|------|--------|
| ReAct 主编排 | MasterReActEngine + `decide_master_session` |
| 剧本 Agent | 对话解析 + 剧本 CRUD |
| RAG 服务 | Indexer / Retriever / ReuseJudge（可先 Mock 向量） |
| 粒度确认流程 | script_structure_proposal UI |
| 关系看板 | 子图 + 共享池泳道 |

### Phase 3：生产闭环（动态图片模式）

| 任务 | 交付物 |
|------|--------|
| 图片 Agent | 生图 API 已接入（默认 Agnes AI） |
| 分镜 Agent | VideoPlan + Shot |
| TTS Agent | 配音生成 |
| 剪辑 Agent | FFmpeg Ken Burns + 配音 + 字幕合成 |
| 首个可播放成片 | dynamic_image 端到端 |

### Phase 4：AI 视频模式

| 任务 | 交付物 |
|------|--------|
| Video Agent | 图生视频 / 首尾帧 |
| 剪辑 Agent 扩展 | AI 视频轨道拼接 |
| 并行 Worker | 生图/生视频队列 |
| QA Agent（可选） | 质检与 Replan |

### Phase 5：体验与生产化

| 任务 | 交付物 |
|------|--------|
| user_edited 增量 Replan | 手改后智能重规划 |
| RAG 审计面板 | 用户强制复用/新建 |
| 全项目看板视图 | 多剧本总览 |
| PostgreSQL + pgvector | 生产存储 |
| 解锁编辑（completed） | P2 可选功能 |

---

## 15. 待确认与开放项

| # | 项 | 当前建议 | 状态 |
|---|-----|----------|------|
| 1 | Plan 后改资产是否自动 Replan | 软提示 + 手动「重新 Plan」按钮 | 已建议，待确认 |
| 2 | 执行完成后是否允许解锁编辑 | P2 可选功能 | 待定 |
| 3 | 共享资产图片跨剧本引用策略 | 只读引用已有 image，不自动复制 | 已设计 |
| 4 | Embedding 模型 | 与 LLM 共用或独立配置 | 待定 |
| 5 | API Key 存储 | 环境变量 / Vault，不落库明文 | 已设计 |
| 6 | 字幕生成 | TTS subtitle_cues + enrich_subtitles_from_audio；可选 Whisper/MFA（P2） | 已实现 P0 |
| 7 | 手动/自动 Plan 确认 | 默认手动确认（可看 Plan UI） | 已建议，可配置 |

---

## 附录 A：端到端用户故事

**场景**：用户为系列剧创建第二集，复用第一集人物。

1. 用户进入项目，选择或创建 `script_ep02`，右侧显示 ep02 子图。
2. 左侧输入：「第二集，林小雨在雨天咖啡厅遇到老客户。」
3. Director 触发 `script_design_with_rag`：
   - 林小雨 → RAG 命中 ep01 → Judge → **reuse**
   - 雨天咖啡厅 → 命中普通咖啡厅 → Judge → **fork** → 新场景资产
   - 老客户 → 无候选 → **create_new**
4. 右侧资产库实时出现新资产；用户手改「老客户」外观描述。
5. 用户点击「生成 Plan」，预览 6 步计划，确认。
6. 用户点击「开始执行」；右侧进入只读，左侧显示进度。
7. 动态图片模式：分镜 → TTS → 剪辑（跳过 Video Agent）。
8. 完成后面板展示成片；看板显示完整关系图含 RAG 虚线边。

---

## 附录 B：名词表

| 术语 | 定义 |
|------|------|
| 超级视频大师 | 主 Agent，ReAct 编排者 |
| PlanDocument | 结构化执行计划，含步骤与依赖 |
| 文字资产 | LLM 生成的结构化文本（人物/道具/场景/剧情等） |
| 数字资产 | 文件类产出（图片/视频/音频/成片） |
| 共享池 | 项目级 character/prop/scene 资产集合 |
| VideoPlan | 分镜 Agent 输出的视频计划稿 |
| Shot | 计划稿中的单个镜头单元 |
| VoiceRoleAsset | 声音角色资产，绑定 TTS 参数 |
| RAG 复用 | 向量检索 + Judge 判定后引用已有共享资产 |
| fork | 派生新共享资产变体，保留 derived_from 溯源 |
| 未执行态 | script.status 为 draft 或 planned |

---

*本文档随产品迭代更新。下一版计划：补充 UI 线框图与 OpenAPI 规范。*
