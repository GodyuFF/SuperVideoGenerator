# SuperVideoGenerator 产品计划手册

> 版本：v0.1  
> 更新：2026-07-17 — 剧本 `title` 以 Script 实体为准；创建/设计确认后锁定，对话不得改写；顶栏与看板展示读 `Script.title`（用户 PATCH 可改）；桌面完整离线安装包分发。  
> 更新日期：2026-07-20（分镜「剪辑轴」改为 EditTimeline 全片摘要；create_frames 支持仅 sub_shot_id；source_frame 自动绑）
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

### 1.3 桌面分发（2026-07-17）

除浏览器 + 本地 API 开发模式外，提供 **Electron 完整离线安装包**（Windows NSIS、macOS DMG），用户无需预装 Python/Node。个人开源默认**未签名**分发；用户从 [GitHub Releases](https://github.com/GodyuFF/SuperVideoGenerator/releases) 下载，并按 [`docs/desktop-packaging.md`](desktop-packaging.md) 绕过 SmartScreen / Gatekeeper。打包版通过 `electron-updater` 检查官方 Release 更新；项目数据与 API Key 保存在用户目录，升级保留。

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
| 模式灵活 | 故事书模式（低成本）与 AI 视频模式（高质量）可选 |

---

## 3. 产品形态与页面布局

### 3.0 视觉设计系统（2026-07-09）

前端采用 **「暗房胶片」** 统一视觉语言，支持 **浅色 / 深色 / 跟随系统** 三种主题（`next-themes`，存储键 `svf-theme`）：

| 维度 | 说明 |
|------|------|
| 主题切换 | 顶栏 `ThemeToggle`；全局 `SvfThemeProvider`；OpenCut 嵌入区同步 `html.light` / `html.dark` |
| 深色 | 深空底 + 取景器珊瑚红 + 胶片琥珀辅色 |
| 浅色 | 雾白底 + 深珊瑚主色 + 柔和边框与阴影 |
| 字体 | Newsreader（标题）/ Outfit（界面）/ IBM Plex Mono（代码与时间码） |
| 签名元素 | 顶栏胶片齿孔纹理；执行中 REC 脉冲点 |
| 剪辑工作室 | `edit-cinema` 影院监视器布局；`svf-studio-chrome` 全屏专业剪辑顶栏 |
| 布局组件 | `AppShell` / `AppTopBar` / `AppNavTrail` |
| 样式文件 | `styles/design-system.css`（双主题令牌）、`styles/editor-studio.css`（剪辑深度 UI） |
| OpenCut 桥接 | `svf-opencut-theme.css` 含 `.light` / `.dark` HSL 令牌映射 |

### 3.0.1 界面语言（2026-07-09）

- **支持语言**：简体中文（`zh-CN`，默认）、English（`en`）
- **切换入口**：各页面顶栏 `LocaleSwitcher`（中文 / EN）
- **持久化**：`localStorage` 键 `svg.locale`，刷新后保持选择
- **覆盖范围**：全站按钮、Tab、下拉/右键菜单、工具栏 tooltip；含完整 OpenCut 嵌入层
- **不在范围**：LLM 对话正文、用户项目名、API 下发的 A2UI 动态字段
- **技术细节**：见 [`docs/i18n.md`](i18n.md)

### 3.1 主工作台布局（两阶段）

**阶段 A — 项目级整体看板**（全宽，无对话）：

```
┌─────────────────────────────────────────────────────────────────────┐
│  SuperVideoGenerator    [项目]  [配置]                               │
├─────────────────────────────────────────────────────────────────────┤
│  Tab: 整体看板 | 图文资产（项目共享池）                              │
│  · 剧本卡片列表（按创建顺序编号：剧本 1 / 2 / …）+ 「新建剧本」       │
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
| **Skill（单轮）** | 消息以 `/skillId` 开头（如 `/thriller 做悬疑短片`），仅当前轮注入 Skill 提示词、设定与可选 `tools` 声明；pip `svg.skills` 扩展；输入 `/` 弹出可选 Skill 列表；`GET /api/skills` 列出 Skill |
| **扩展（pip）** | `svg.tools` / `svg.skills` / `svg.mcp_servers` entry_points；详见 [extensions.md](extensions.md) |
| **目标模式** | 项目配置 `execution_mode=goal` 或工作台开关；AI 自主执行至成功/失败，不调用 `ask_user_question`、不弹出任何 A2UI 确认 |

---

## 4. 领域模型与资产体系

> **数据存储与关联关系完整说明**：
> - 表结构设计与 ER 图：[`docs/data-storage-schema.md`](data-storage-schema.md)
> - 持久化流程与目录：[`docs/data-storage.md`](data-storage.md)

### 4.1 层级结构

```
Project（项目）
├── ProjectConfig（五类配置）
├── SharedAssetPool（共享资产池）
│   ├── character（人物）    ← 项目级共享
│   ├── prop（道具）         ← 项目级共享
│   └── scene（空镜）        ← 项目级共享；生图为无人物环境背景板，供 frame 合成
└── Script × N（剧本/章节，粒度用户确认）
    │   └── title：创建或剧本设计确认后锁定；禁止用每轮对话摘要覆盖；展示一律读 Script.title（用户 PATCH 可改）
    ├── plot / narration（剧情、旁白）     ← 剧本私有
    ├── VoiceRoleAsset（声音角色）         ← 关联人物或旁白
    ├── VideoPlan（视频计划稿）
    │   └── Shot × M（镜头）
    ├── ImageAsset（图片，可预生成）
    ├── video_clip（视频片段文字资产，剧本私有）← 前端五块：名称 / summary / element_refs / video_prompt / notes（AI 自用）+ 生成 mp4
    ├── frame（画面文字资产，剧本私有）← 前端五块：名称 / summary / element_refs / image_prompt / notes（AI 自用）+ 生成图片
    ├── VideoAsset（AI 视频数字资产，MediaAssetType.VIDEO）
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
| `txt_` | 文字资产（character/prop/scene/plot/narration/**video_clip**） | 文字 |
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

**查询职责分离**（2026-07-16 更新）：

| 方法 | 用途 | 共享池范围 |
|------|------|------------|
| `MemoryStore.list_assets_for_script` | Agent `list_text_assets`、`load_context`、scan | 与 `list_visible_text_assets_for_script` **一致**：本剧本私有 + **已关联**共享池 |
| `MemoryStore.list_visible_text_assets_for_script` | 剧本级看板 Tab、`GET .../scripts/{id}/assets` | 同上 |
| `MemoryStore.list_shared_assets` | RAG 检索专用（`core/rag/`） | 同项目**全部** `project_shared` |

跨剧本复用不在 list 阶段暴露全池，而在 `create_character` / `create_scene` / `create_prop` 时由 RAG 判定 reuse/fork/create_new 后建立 `rag_reuse` 或 `derived_from` 引用边。

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
| character 扩展 | 原 6 字段 + `ethnicity`, `body_type`, `height`, `build`, `hair_style`, `hair_color`, `eye_color`, `facial_features`, `default_expression`, `default_pose`, `accessories`, **`tts_voice`**（TTS 配音音色，从当前 `ai_config` TTS 服务商可选列表中选择，与 `gender` 匹配；落盘时校验/推断，供后续多角色配音使用） |
| scene 扩展 | 原 6 字段 + `architecture_style`, `key_objects`, `foreground`, `background`, `camera_angle`, `depth_of_field`, `color_tone` |
| prop 扩展 | 原 5 字段 + `shape`, `color`, `texture`, `brand_style`, `visual_details` |
| `image_variants[]` | 多图变体：`kind`（base/expression/pose/action…）、`label`、`meaning`、`variant_prompt`、`media_id`；`description` 为设定主形象，衍生变体以 base 为 reference 生图；编辑器支持**添加/删除**子形象（主形象 base 不可删，最多 8 条） |
| `variant_refs` | 关联资产 → 子形象：`{ text_asset_id: variant_id }`；画面/视频生图取参考时优先该变体图，缺省用主形象 |
| 变体提示词手改 | 看板「编辑」弹窗（`ImageTextAssetEditor`）可逐条编辑 `image_variants[].variant_prompt`；PATCH 后持久化并自动重算该变体 `image_prompt`（资产级 `prompt_locked` 时仍重算变体 prompt） |
| 剧本详情抽屉 | 关系图 / 谱系点击 `kind=script` 时右侧弹出 `ScriptDetailDrawer`，展示正文、统计与剧情段落 |
| 生图策略 | **scene**：空镜背景板（establishing plate），无人物/动物/独立道具主体；`key_objects` 仅环境固定陈设（非 prop 资产）；**character/prop**：绿幕 `#00FF00` 生图后 FFmpeg colorkey 抠透明 PNG（`core/assets/chroma_key.py`） |
| 手动新建 + AI 草稿 | 剧本看板「新建角色/空镜/物品/画面/视频」（`CreateTextAssetDialog`）：角色/空镜/物品可填全部 content；**frame / video_clip 五块**（名称、摘要、关联资产 `element_refs` + 可选子形象 `variant_refs`、提示词 `image_prompt`/`video_prompt`、备注 `notes` 供 AI 编排自用），可只填摘要后 **AI 一键生成**（`POST .../assets/generate-draft`，工作台专用，**不**注册 Agent 工具） |
| 画面/视频 UI 精简 | `ImageTextAssetEditor` / `ImageTextAssetDetailModal` 对 `frame`/`video_clip` 仅展示上述五块（详情另保留关联图片/视频与谱系）；`notes` 不进入生图/生视频提示词组装；存储层多余字段不删，仅前端不展示 |
| 关联资产动态提示词 | 生图/生视频时由 `element_refs` 展开 `【关联资产上下文】`（见 `core/assets/linked_assets_prompt.py`），拼接到最终请求 prompt，**不写回**用户锁存的 `image_prompt`/`video_prompt`；详情页提示词旁「小眼睛」可预览实际生成全文（`GET .../resolved-prompt`） |

旧键 `appearance` 加载时合并入 `description`。图片仍通过 `MediaAsset` + `generates` 关联；`primary_media_id` 固定指向 base 变体 media。

### 4.5 引用关系与资产谱系

运行时引用仍存于 `MemoryStore.references`（JSON dict，非独立 SQL 表）；统一查询层 [`core/assets/lineage.py`](../core/assets/lineage.py) 合并以下多源边：

| 来源 | relation 示例 |
|------|----------------|
| `store.references` | `uses` / `generates` |
| `Shot` 镜内 `sub_shots[].element_refs` | `element_ref` / `shot_ref` |
| `FrameContent.element_refs` | `element_ref`（scene/character/prop/frame 桶与资产类型一一对应；禁止环引用；生图按拓扑序） |
| `FrameContent` / `VideoClipContent.variant_refs` | 关联资产指定子形象（`{ asset_id: variant_id }`）；详情以缩略图展示所选变体 |
| `MediaAsset.source_asset_id` | `generates`（与 references 去重） |

对外契约：`AssetDescriptor` + `LineageEdge` + `AssetLineageView`（单资产 incoming/outgoing）；`build_project_graph` 供看板关系图 Tab。

| relation | 含义 |
|----------|------|
| `uses` | Script/plot/shot 引用某资产 |
| `derived_from` | fork 派生自某共享资产（解析器预留，本阶段未写入） |
| `rag_reuse` | RAG+Judge 产生的复用（审计，本阶段未写入） |
| `generates` | 文字资产 → 图片/视频等数字资产 |
| `voice_of` | 声音角色绑定人物文字资产（本阶段未写入） |
| `shot_ref` | 分镜镜头引用角色/场景/物品/画面 |
| `element_ref` | 画面合成引用场景/角色/物品 |

**删除规则**：存在外部 `uses` 等引用时禁止删除；`DELETE .../assets/{id}` 返回 **409** 与结构化 `references: LineageEdge[]`。详情页与看板「关系图」Tab 展示可跳转关联列表。

**图文详情两套「关联」展示（勿混用）**（2026-07-14）：

| UI 区块 | 数据来源 | 空态文案 |
|---------|----------|----------|
| **关联图片 / 关联视频** | 看板 item 的 `images`/`media`/`variants.preview_url`（`MediaAsset.source_asset_id` → 文字资产；`assetImages` / `assetVideos` 过滤占位 URL）。**video_clip**：`preview` 仅为摘要文案，`preview_url` 与 `media[]` 同源可播放链路；`assetVideos` 优先 `media`，仅在无 media 时回退 `preview_url`，避免同一 mp4 在详情里渲染两次 | 「尚未生成关联图片/视频」 |
| **资产谱系**（媒体详情称「关联资产」） | `GET .../assets/{id}/lineage` 的 incoming/outgoing 边（文字/媒体/分镜引用），**不**渲染图片缩略图 | 「暂无关联资产记录」 |

从谱系 / 关系图 **跳转**打开图文详情时，须先用 `fetchBoardTextAssetItem`（看板 `character|scene|prop|frame|video_clip` 或 `knowledge`）补全完整 item；详情弹窗对仅含 `id/name` 的桩数据也会自愈拉取，避免误显示「尚未生成关联图片」。

### 4.6 详情页二次生成（2026-07-11）

凡经 AI 内容流水线产出的媒体资产，均可在**详情页 / 分镜抽屉**一键二次生成，无需回到对话区重新 Plan。

| 资产类型 | 详情入口 | 二次生成行为 | 旧版处理 |
|----------|----------|--------------|----------|
| character / prop / scene / frame（文字） | 图文资产详情 Modal | 按 `image_prompt` 重新生图（可选指定变体） | 旧图片 `metadata.superseded=true`，谱系保留 |
| video_clip（文字） | 图文资产详情 Modal | 按 `video_prompt` + 参考图重新生成 AI 视频 | 旧视频 superseded；`primary_media_id` 更新 |
| image（数字） | 媒体详情 Modal | 从 `source_asset_id` 文字资产重新生图 | 当前媒体标记 superseded |
| tts / audio（数字） | 媒体详情 Modal | 按 `metadata.shot_id` 重新合成配音 | 旧配音 superseded；自动 `sync_plan_from_tts` |
| video（数字） | 媒体详情 Modal | 按镜头重新生成 AI 视频（需 video API 已配置） | 旧视频 superseded |
| shot（分镜） | ShotDetailDrawer | 分别触发 TTS / frame 画面 / AI 视频；**视频**可勾选 1～N 张参考（画面 / 落盘图片 / 角色·场景·道具形象），1 张→图生视频、2+ 张→关键帧过渡 | 同上 |

**权限与互斥**：
- 未执行态（`draft` / `planned`，且非 AI 执行中）显示「重新生成」按钮；`executing` 或主编排进行中时隐藏并 API 返回 403/409
- 二次生成不删除旧文件，仅标记 superseded，关系看板可追溯 `generates` 边

**API**：
- `POST .../scripts/{sid}/assets/{asset_id}/regenerate`（body 可选 `variant_id`）
- `POST .../scripts/{sid}/shots/{shot_id}/regenerate`（body `{ "kinds": ["tts","frame","video"], "video": { "sub_shot_idx": 0, "source_frame_asset_ids": [], "source_media_ids": [], "source_element_refs": { "character": [] }, "video_mode": "img2video|keyframes" } }`；`video` 可选，未传则按子镜已有画面推断）

实现：[`core/assets/regenerate.py`](../core/assets/regenerate.py)、[`AssetRegenerateButton.tsx`](../apps/web/src/components/AssetRegenerateButton.tsx)

**生成队列（2026-07-16）**：剧本工作台右侧可调宽抽屉，展示当前剧本维度的图片/视频生成任务（排队中 / 执行中 / 最近完成）；顶栏入口带角标，状态经 WebSocket `generation_queue_snapshot` 实时刷新；二次生成、资源列表批量与 Agent 批生图/视频均经后端全局串行队列，同时仅 1 条 running。实现：[`GenerationQueueDrawer.tsx`](../apps/web/src/components/GenerationQueueDrawer.tsx)、[`GenerationQueueContext.tsx`](../apps/web/src/context/GenerationQueueContext.tsx)。

**资源列表（原资源印样台，2026-07-15 更名）**：剧本工作台右侧可调宽抽屉，整表总览 `character` / `scene` / `prop` / `frame` / `video_clip` 媒体齐备度；支持类型/缺媒体筛选、勾选，以及底栏 **生成缺失** / **重新生成所选**（逐条调用 `assets/{id}/regenerate` 入队，由统一队列串行执行）。入口：看板 Tab 旁「资源列表」+ 各资产 Tab 工具栏。实现：[`BatchAssetStudioDrawer.tsx`](../apps/web/src/components/board/BatchAssetStudioDrawer.tsx)、[`batchAssetStudio.ts`](../apps/web/src/utils/batchAssetStudio.ts)。

**关系图 UI（2026-07-10 落地）**：看板 Tab 使用 `@xyflow/react` + `@dagrejs/dagre` **LR（左→右）** 分层布局；`smoothstep` 平滑连线；内置缩放/平移/MiniMap；单击节点打开图内右侧预览侧栏（入边/出边、复制 ID），「打开详情」跳转现有资产 Modal/Drawer。样式令牌 `--svf-graph-*` 定义于 `design-system.css`，随页面 **light/dark** 主题切换。实现：`apps/web/src/components/board/GraphBoard.tsx` 及 `graph/` 子模块。

> 更新：2026-07-10

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
| 5 | **视频风格配置** | mode（故事书/视频生成）、aspectRatio、transition、watermarkFreeImagesOnly、bgmEnabled |
| 6 | **Agent 提示词工作台**（全局） | `style_modes` CRUD（自定义风格：**id + 显示名称 + 可选 `video` 子模式**（文生/图生/关键帧），自动 1:1 绑定同名 PromptProfile，`based_on` 默认 `storybook`）；各 Agent `role_prompt` + `action_hint` 编辑；`tool_overrides` 勾选；内置两风格（`storybook` / `ai_video`）可「恢复系统默认」 |

### 5.2 剧本与 RAG 配置（增补）

```typescript
interface ProjectConfig {
  llm: { ... };
  imageGen: { ... };
  videoGen: { ... };
  tts: { ... };
  style: {
    mode: "storybook" | "ai_video";
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

> **更新 2026-07-10**：主编排改为依赖驱动动态选步（`delegate_readiness`），无固定 pipeline 展示模板。

> **更新 2026-07-09**：故事书/漫画典型依赖链为「文字设计 → 分镜（含 frame）→ 图片 → TTS → 分镜详设 → 剪辑」（无 `video_gen`），**顺序可因用户意图调整**。
>
> **更新 2026-07-12**：`style_hints.target_duration`（预计时长）在首次绑定时会同步写入 `Script.duration_sec`，剧本工作台与 LLM 上下文使用同一秒数；不再仅依赖创建剧本时的默认 60 秒。

> **更新 2026-07-11**：「动态图文模式」更名为**故事书模式**（`storybook`，旧 id `dynamic_image` 自动迁移）。故事书模式硬保证：`persist_plan` 校验每镜必须挂 frame 画面资产；`_image_gen_complete` 要求全部 frame 完成生图（不再豁免 `references_ready=false`）且每镜有 frame。新增剧本级可选提示词 `style_hints`（`image_style` 图片风格 / `target_duration` 预计时长），随视频风格一并锁定并注入 LLM 上下文；未选择则不组装。

### 6.1 模式对比

| 模式 | 标识 | Video Agent | TTS | 剪辑输入 |
|------|------|-------------|-----|----------|
| **故事书模式** | `storybook` | 不调用 | 必须（分镜含配音文案） | 按 frame 画面资产逐镜配图 + Ken Burns 运镜 + 配音 |
| **AI 视频模式** | `ai_video` | 必须 | 按镜头 | AI 视频片段 + 配音 + 合成 |
| **画面图生视频** | `frame_i2v` | 必须 | 必须 | 实体+frame 合成配图 → 以 frame 为唯一图生源 I2V → 配音 + 合成 |

> **更新 2026-07-20**：新增第三种内置风格 **画面图生视频**（`frame_i2v`）：分镜同时创建 `frame` + `video_clip`；`image_agent` 两阶段生图；`video_agent` 以 frame 图片为 I2V 输入，`video_clip` 仅承载 motion prompt。`_image_gen_complete` 在尚无视觉文字资产时返回 false（禁止空剧本误标 `step:image_gen`）；`frame_i2v` 下 `video_gen` 在配图未齐时带 soft_blocker，避免跳过 `image_agent`。

> **更新 2026-07-13**：下线「动态漫画模式」（`dynamic_comic`）与历史「营销视频 AI」（`marketing_video` / `marketing`）；持久化数据自动迁移为 `storybook`。现保留故事书、AI 视频、画面图生视频三种内置风格。

### 6.2 流水线差异

**故事书模式**（`core/llm/master/delegate_deps.py` → `delegates_for_style` / `delegate_readiness`）：

主编排**无固定执行顺序**；每轮据 `user_message` 与 Store 依赖从 `eligible_delegates` 中选一步。典型依赖（可跳步、可分批）：

```
剧本 Agent → [图片 Agent 可为 entity/frame 分批] → 分镜 Agent → TTS → 分镜详设 → 剪辑 Agent
```

**AI 视频模式**：

```
分镜 Agent → [图片补图] → Video Agent → TTS → 分镜详设 → 剪辑 Agent
```

**画面图生视频**（`frame_i2v`）：

```
剧本 Agent → 分镜 Agent（create_frames + create_video_clips）→ 图片 Agent（entity + frame）→ Video Agent（I2V 只认 frame）→ TTS → 分镜详设 → 剪辑 Agent
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

### 6.4 故事书策略补充（2026-07-04）

| 阶段 | 行为 |
|------|------|
| 图片完善 | `image_agent`：`generate_images` 或 `search_images`；**仅搜图**后 `sync_text_from_image` 白名单 auto-patch（`color_palette` 等），生图产出无需 sync；`description/summary` 重大变更需 `apply_major_changes` 或 `update_*` |
| 配图 | `image_agent` 两阶段（单次委派）：`character/prop/scene` 文生图 → `frame` 多参考图生图（分镜创建 frame 后） |
| 分镜 | `storyboard_agent`：`create_shots`（`sub_shots` 子镜轨 + `audio_tracks` + `subtitles`）→ `create_frames`（**每子镜 1 frame**，`sub_shot_id` 必填且可单独定位）→ `persist_plan` |
| 分镜复核 | `storyboard_refine_agent`（TTS + 生图后；**AI 视频另须 video_gen 完成**）：`get_shot_details` → `get_shot_asset_timing` → `sync_actual_assets` → `review_and_restructure` → `update_frames` → `persist_review`；**剪辑前最后一步** |
| 主编排顺序 | **完整成片**遵守 canonical：故事书 `…→tts→shot_detail→edit`；AI 视频 `…→video→tts→shot_detail→edit`。局部请求可跳步；`remaining_plan` 禁止复核后再生视频 |
| 剪辑计划 + 成片 | **分镜复核之后** `editing_agent`：`load_edit_context` → `plan_edit_timeline` → …；`plan_edit_timeline` 可从分镜投影生成时间轴；OpenCut 手改经 `apply_timeline_edits_to_shots` 回写 |
| 剪辑看板 | 看板 Tab `edit`：只读多轨时间轴（含 `edit_description`、转场、背景、source_refs 摘要） |
| 成片 | **storybook/comic**：`EditTimeline` → FFmpeg `compose_final`（运镜/转场/背景/字幕/配音）；**ai_video**：`video_agent.generate_from_timeline` → `editing_agent` 混流 |

实体：`EditTimeline` / `EditClip`（[`core/models/entities.py`](../core/models/entities.py)），持久化 `dev_store.json` → `edit_timelines`。

---

## 7. 主 Agent：ReAct 编排

### 7.1 Director 职责

- 理解用户意图，生成结构化 `PlanDocument`
- 按依赖拓扑调度子 Agent
- 推送 WebSocket 事件驱动 UI
- 失败时触发 Replan（局部或全局）
- 识别 `user_edited` 资产，支持增量 Replan
- **Store 复用（2026-07-14）**：新对话启动时 `seed_completed_steps_for_message` 将 Store 已推断完成的步骤写入 `completed_actions`，避免已有配音/分镜等仍全量重跑；用户说「全部重做」或明确「重新配音 / 从剪辑继续」等时再开放对应步骤及下游。主编排 `## 当前编排状态` 组装见 [orchestration-state.md](orchestration-state.md)

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
| 5 | `storyboard` | 分镜 Agent | 视频计划稿 + 镜头 + frame 文字资产 |
| 6 | `image_gen` | 图片 Agent | 为缺图文字资产生图（角色/道具/场景 → frame 多参考图生图；前端 `PlanPanel` 内嵌逐张进度） |
| 7 | `video_gen` | 视频 Agent | 仅 AI 视频模式；**须在分镜复核之前** |
| 8 | `tts_gen` | TTS Agent | 按镜头/计划稿生成配音 |
| 9 | `shot_detail` | 分镜复核 Agent | **剪辑前最后一步**：TTS + 生图（+ AI 视频）后对比规划/实测；禁止复核后再 `video_gen` |
| 10 | `edit_compose` | 剪辑 Agent | 紧接在分镜复核之后；规划 EditTimeline / 导出 |
| 11 | `qa` | 质检（可选 P2） | 一致性检查 |

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

| 能力 | 说明 | 详情页入口 |
|------|------|------------|
| 按文字资产生图 | 调用 `imageGen` 配置，1:1 关联 | ✅ 图文详情「重新生成图片」 |
| 重新生成 | 新 image_id，旧图标记 superseded | ✅ 媒体图片详情 |
| 删除 | 无分镜/剪辑/成片引用 | — |

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
| 配音文案 | `storybook` 模式必填 |

**Shot 结构**（镜内多轨，2026-07-12；2026-07-14 子镜产出意图 + 画面时段）：

> **子镜与剧本画面**：镜内 `sub_shots[]` 是镜内剧本时间轴时段单元，与剧本 Tab「画面」(frame) **解耦**。子镜可挂接**多张**画面（`images[]`）与**多段**视频片段（`videos[]`）；UI 用图文卡片多选，槽位可编辑/重新生成，并有子镜内时段条可视化。子镜 `produce_mode`（`still` / `text2video` / `img2video`）声明产出意图；`produce_rationale` 为可选短理由。每张 `images[]` / `videos[]` 可有独立 `start_ms`/`end_ms`（相对**镜起点**；画面 `0+0` 表示未显式设置，解析层回填为子镜区间）。

```json
{
  "id": "shot_xxx",
  "order": 0,
  "duration_ms": 4000,
  "sub_shots": [
    {
      "start_ms": 0,
      "end_ms": 4000,
      "description": "子镜描述",
      "produce_mode": "still",
      "produce_rationale": "风光建立镜，长时段静帧",
      "camera_motion": "ken_burns_in",
      "element_refs": { "character": ["txt_char_1"], "scene": ["txt_scene_1"] },
      "images": [{
        "kind": "static",
        "frame_asset_id": "txt_frame_1",
        "media_id": "media_img_1",
        "start_ms": 0,
        "end_ms": 4000
      }],
      "videos": []
    }
  ],
  "video_tracks": [
    {
      "z_index": 0,
      "clips": [
        { "start_ms": 0, "end_ms": 4000, "media_id": "media_img_1", "source_kind": "still" }
      ]
    }
  ],
  "audio_tracks": [
    {
      "kind": "voice",
      "clips": [
        { "start_ms": 0, "end_ms": 2000, "text": "清晨，小镇尚未苏醒。", "character_ref": "" },
        { "start_ms": 2000, "end_ms": 4000, "text": "今天一定行！", "character_ref": "txt_hero", "media_id": "media_tts_1" }
      ]
    }
  ],
  "subtitles": [
    { "start_ms": 0, "end_ms": 1200, "text": "第一句", "character": "", "color": "" }
  ],
  "review_note": "复核展示说明",
  "need_regen": false
}
```

看板 API 另返回派生字段：`timeline_start_ms` / `timeline_end_ms`、`subtitle_lines`（含 `absolute_*_ms`）、`asset_refs`（由镜内引用汇总）、`frame_preview_url` / `frame_asset_name`（**仅** frame/图片 media；AI 视频不占「画面」位）、以及无 frame 图时的兼容预览 `preview_fallback_url` + `preview_fallback_kind=video`（胶片条/表格标注「视频预览」，不冒充画面资产）。分镜详情画面区：有 `frame_asset_id` 展示剧本画面资产；仅有 IMAGE `media_id` 时按「图片素材」展示预览。

**分镜挂接与角色边界**（2026-07-14）：

| 维度 | 规则 |
|------|------|
| 子镜挂接槽位 | **仅**关联剧本私有 **画面资产 `frame`**、**视频资产 `video_clip`**（或已生成的对应 media）；可在分镜编辑中**新建**这两类剧本维度资产 |
| 不可作为子镜挂接目标 | `character` / `scene` / `prop` 不得当作子镜 images/videos 槽位的主关联对象 |
| 角色概念位置 | 分镜内**仅对话/配音幕**有角色：`ShotAudioClip.character_ref` 指向发言角色，实际用于**角色语音（TTS 音色）**；句级字幕可选 `character` 为展示位（默认空） |
| 画面内引用（非挂接） | 主画面卡片上的 `element_refs`（角色/场景/道具）属于 **frame 资产自身** 的构图引用，不是分镜槽位类型 |
| 生视频参考（非挂接） | AI 生视频可勾选画面 / 落盘图 / 角色·场景·道具形象作参考源，同上不属于子镜挂接类型 |

**镜级时间轴**（2026-07-12，2026-07-13 子镜累加，2026-07-19 画面时段钳制）：`resolve_shot_timings` **始终**从镜内结构累加（`plan_estimate`）；`EditTimeline` 仅由 `editing_agent` Tool（`plan_edit_timeline` 等）或用户 OpenCut PATCH 写入。TTS 同步（`sync_plan_from_tts`）绑定 voice clip `media_id`、对齐镜时长、回填 `subtitles`，**不写**剪辑时间轴；同步时子镜按 `start_ms` **累加分段**（相邻首尾相接，末段止于镜有效时长），避免 TTS 拉长镜长后全部子镜 `end_ms` 被拉满；缩短子镜时同步钳制 `images[].start_ms/end_ms` 使其落在子镜区间内（`clamp_image_timings_to_sub`）。看板懒同步：`lazy_sync_storyboard_if_needed`（仅分镜绑定）+ 落盘。

**AI vs 系统职责**：
- **分镜 Agent**：`create_shots` 填写 `sub_shots`（含 `produce_mode`、可选 `produce_rationale`、各 `images[].start_ms/end_ms`）+ `audio_tracks`（voice）+ 可选 `subtitles`；`create_frames` 创建 frame 并绑定 `sub_shots[].images[]`
- **TTS**：从 voice clip `text` 合成（音色按 `character_ref` / clip `voice`）；成功后 `sync_plan_from_tts`
- **分镜复核 Agent**：`review_note`、`camera_motion_refined`（写入 `sub_shots[0]`）、结构性 `restructure_ops`

**用户手动编辑**：PATCH 镜内字段（`sub_shots` / `audio_tracks` / `subtitles` / `duration_ms` / `review_note`）；分镜抽屉编辑模式可**增删改**配音幕（含发言角色→角色语音）、句级字幕（含可选 `character`/`color`）与子镜；子镜仅挂接/新建 **frame / video_clip**；支持**从配音音频一键生成字幕**（绑定 media 的 `subtitle_cues` / WhisperX ASR，**不用**配音幕文案——幕文案可与实际配音不一致）；改旁白或删配音后 TTS 失效并提示重新配音。**镜时长 `duration_ms`**：UI 只读，由绑定音/视频时段自动推算（优先级：剪辑轴 > 子镜视频 > 配音 > 计划）；落盘向上对齐到整秒（不保留毫秒精度）；服务端 PATCH 经 `reconcile_shot_duration_from_media` 按媒体实测时长回填配音终点并同步镜长。

```
storyboard.generate(script_id)
PATCH .../video-plan/shots/{shot_id}   # 镜内多轨 patch
POST  .../video-plan/ops               # 结构 ops（含 reorder）
```

#### 8.3.1 分镜复核 Agent（Storyboard Refine Agent，TTS + 生图后）

| 能力 | 说明 |
|------|------|
| 时长/字幕同步 | `sync_actual_assets` 绑定 TTS media、对齐镜时长、回填字幕（仅写分镜计划稿） |
| 结构性复核 | `review_and_restructure`：`adjust`/`split`/`merge`/`add`/`delete`/`regen` |
| 展示说明 | `review_note`（API 兼容字段 `display_instructions`）、`camera_motion_refined` |
| 补图建议 | `need_regen` + `regen_reason`（可为 JSON 结构化音画偏差） |
| 音画协调 | 按镜 `sync_policy`（narration_master / visual_master / balanced）；`analyze_av_sync` 分层自动修复；详见 [av-sync-plan.md](av-sync-plan.md) |
| 版本 | `VideoPlan.detail_revision` 独立于 `EditTimeline.revision` |

投影层：[`core/edit/shot_flatten.py`](../core/edit/shot_flatten.py)（Shot → EditTimeline）、[`core/edit/shot_detail_sync.py`](../core/edit/shot_detail_sync.py)（TTS 绑定与懒同步）、[`core/edit/shot_media_bind.py`](../core/edit/shot_media_bind.py)（生图/生视频回填 clip `media_id`）。

**TTS 时长来源**：metadata 与本地探测取可靠值；看板/剪辑 `GET edit-timeline` 路径上的 `refresh_shot_tts_durations_if_drifted` 在偏差 >200ms 时重绑定。主 voice clip 须相对镜起点（`start_ms=0`）；非零起点视为相对坐标损坏并强制归零收敛，避免每次打开重复重绑。本地探测结果按文件 mtime/size 进程内缓存。

### 8.4 视频 Agent（Video Agent）

仅在 `style.mode === "ai_video"` 时调度。

| 能力 | 说明 | 详情页入口 |
|------|------|------------|
| 图生视频 | `image_to_video` | ✅ 媒体视频详情 / 分镜抽屉 |
| 首尾帧生成 | `first_last_frame` | — |
| 时长约束 | `duration_ms ≤ videoGen.maxDurationSec` | — |
| 重新生成 | 新 vid_id，旧片段 superseded | ✅ |

```
video.generate_for_shot(shot_id)
video.regenerate(video_asset_id)
video.delete(video_asset_id)
```

### 8.5 TTS Agent（已接入）

| 能力 | 说明 |
|------|------|
| 按镜头生成配音 | 从镜内 voice clip `text` 合成 mp3，写入 `MediaAsset(AUDIO)`，`metadata.shot_id`；成功后自动 `sync_plan_from_tts` 绑定 media 并对齐镜时长 | ✅ 媒体音频详情 / 分镜抽屉「重新配音」 |
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
| 缺失闭环 | 校验不通过时 `report_missing_assets`；主编排据 `suggested_upstream` 重委派上游后再 `delegate_agent(agent_id=editing_agent)` |
| 故事书模式 | 图片轨道 + 运镜（Ken Burns/平移）+ 配音 |
| AI 视频模式 | 视频轨道拼接 + 配音 |
| 混音 | BGM、音量平衡 |
| 导出 | `compose_final` 前硬校验素材与 **edit capabilities**；FFmpeg 渲染 → `assets/exports/` |

```
load_edit_context → plan_edit_timeline → validate_edit_assets
  → report_missing_assets（缺失）| gather_media → compose_final（就绪）
```

---

## 9. RAG 资产复用

> **更新 2026-07-20**：`resolve_shared_text_asset_sync` / 索引 embed 经 [`core/rag/async_bridge.py`](../core/rag/async_bridge.py) 在已有 asyncio 事件循环（FastAPI / ReAct）内也可安全调用，不再抛「不可在运行中的事件循环内同步调用」。
> **更新 2026-07-16**：`core/rag/` 已落地；`create_character` / `create_scene` / `create_prop` 自动 RAG 解析。审计 UI / WebSocket 事件仍为后续 Phase。

### 9.1 适用范围

仅对 **项目共享池** 三类文字资产建立向量索引：`character`、`prop`、`scene`。

### 9.2 Embedding 配置与回退

| 优先级 | 来源 | 说明 |
|--------|------|------|
| 1 | AI 配置页「Embedding / RAG」Tab | 写入 `data/ai_config.json` 的 `embedding` 分区 |
| 2 | `SVG_RAG_EMBEDDING_API_KEY` | `.env` 环境变量 |
| 3 | `OPENAI_API_KEY` | 通用 OpenAI Key 回退 |

未配置可用 Key 时：**不走向量检索**，对共享池同类型资产做**规范化名称精确匹配**（去空白、NFKC、大小写不敏感）；命中则 `reuse`，否则 `create_new`。项目 `config.rag.enabled=false` 时始终新建。

### 9.3 流程

```
识别本集实体需求
→ 有 Embedding Key：构造 RAG Query → 向量检索 Top-K → Judge → reuse / fork / create_new
→ 无 Embedding Key：规范化名称精确匹配 → reuse 或 create_new
→ 写入资产 +（有向量时）更新索引 + 建立引用边（rag_reuse）
```

### 9.4 两阶段检索（需 Embedding）

| 层级 | 检查项 | 动作 |
|------|--------|------|
| 硬规则 | project_id、type 一致；资产有效 | 不合格剔除 |
| 相似度 | score < threshold（默认 0.75） | 不进入 LLM |
| LLM 语义 | 人设/外观是否冲突 | reuse / fork / reject |
| LLM 剧情 | 世界观一致性 | 冲突 → fork 或 create_new |
| 用户策略 | reuseAggression | 保守少复用，激进多复用 |

### 9.5 判定结果

| decision | 行为 |
|----------|------|
| `reuse` | 本片建立 `rag_reuse` 引用边，直接引用共享资产（含已有图片只读引用） |
| `fork` | 共享池新增变体，`derived_from` 指向原资产，重新入索引 |
| `create_new` | 新建共享资产，入索引，供后续 RAG |

### 9.6 ReuseDecision Schema

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

### 9.7 RAG 审计

剧本 Agent 执行后，左侧对话区展示 RAG 摘要；资产库/看板可展开审计面板：query、Top-K 候选、Judge 结果。用户可手动改为「强制新建」或「强制复用」。

---

## 10. 可视化看板

### 10.1 默认视图

- **默认**：`active_script_id` 子图 + 与之相连的共享池节点（`list_visible_text_assets_for_script`）
- **可选**：全项目视图（所有 Script + 共享池，项目级 `knowledge` Tab）

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

**项目图文资产 Tab（`knowledge`）**（2026-07-16）：

- 工具栏：**剧本**下拉（全部 / 各剧本）、**范围**切换（引用 / 来源）、**类型** chip（角色 / 空镜 / 物品等）
- **引用**（默认）：资产在该剧本可见（分镜/画面引用或来源剧本创建）
- **来源**：仅 `source_script_id` 匹配所选剧本
- 展示：响应式卡片网格（与剧本内角色 Tab 一致），按类型分区；卡片 meta 行显示引用/来源剧本
- 筛选偏好：`localStorage` 键 `svg.knowledge.filters`
- 组件：[`KnowledgeBoard.tsx`](../apps/web/src/components/board/KnowledgeBoard.tsx)、[`knowledgeBoardFilters.ts`](../apps/web/src/components/board/knowledgeBoardFilters.ts)
| **剧本级** | `script_details` 单剧本详情（正文预览 + 弹窗编辑 + 剧情段落） | `character` / `scene` / `prop` / `frame` / `storyboard` / `edit` / `media` / `pipeline` |

**剧本详情 Tab（`script_details`）**（2026-07-12）：

- 移除独立「剧本」二级 Tab；正文与剧情段落统一在详情页管理
- 顶部：标题、状态、风格、目标时长与统计行；**编辑剧本** 打开 [`ScriptEditorModal`](../apps/web/src/components/board/ScriptEditorModal.tsx)（标题 / 目标时长 / Markdown 正文）
- 正文区：预览摘录（超 480 字可「查看全文并编辑」）；剧情段落列表支持新建 / 编辑 / 删除（`plot` 资产）
- 组件：[`ScriptDetailsBoard.tsx`](../apps/web/src/components/board/ScriptDetailsBoard.tsx)、[`ScriptEditorModal.tsx`](../apps/web/src/components/board/ScriptEditorModal.tsx)

**分镜 Tab（`storyboard`）**（2026-07-10 UI，2026-07-11 TTS 时长对齐，2026-07-12 镜内多轨抽屉）：

- 默认 **胶片条卡片** 全宽纵向浏览：16:9 预览（优先 frame 图片；无图时视频兼容预览+来源芯片）、时间轨节点、状态徽章（需补图 / 时长漂移 / 待详设）
- 镜头时长行：`({展示时长}s · {来源})`，来源按 **剪辑 > 视频 > 配音 > 计划** 优先级取最高可用档（`display_duration_ms` / `display_duration_source`）；与计划镜长偏差 >200ms 时标「时长漂移」
- 工具栏：镜头数、总时长、视图切换（胶片条 / 紧凑表格）、跳转剪辑 Tab
- 点击镜头 → **右侧抽屉** 镜内多轨详情（顶栏固定、内容区独立纵向滚动；编辑态底栏「取消/保存」吸底）：
  - **迷你时间轴**（配音轨 + 画面轨双轨段块，点击与下方卡片联动高亮）
  - **配音幕列表**：每段含时间码、角色（可选：旁白或已有角色；选中角色且已配置 `tts_voice` 时自动回填音色）、文案、试听与按段 TTS 重生
  - **画面列表**（与剧本 Tab「画面」同一实体）：以**画面卡片**为单元，内含预览、关联资产（空镜/角色/物品）、**本图时段**（`start_ms`–`end_ms`，未设置时显示「= 子镜时段」）、成片模式；子镜头部展示 **产出意图**（`produce_mode` 芯片 + 可选 `produce_rationale` 摘要）；可新增/删除多条关联
  - **视频列表**：可选**源画面**、关联已有成片，或一键**生成视频**（图生视频）
  - 字幕行、展示说明、谱系；支持上一镜/下一镜与复制旁白（合并多幕文案）
  - **编辑模式**：`ShotSegmentEditor` 可增删配音幕与子镜；子镜可编辑 `produce_mode` 下拉与可选 `produce_rationale`；每张关联画面可编辑 `start_ms`/`end_ms`（须落在子镜区间内）；表单仅在切换镜头时从 plan 初始化，编辑中不被 video-plan / 媒体索引刷新冲掉本地文案；抽屉在 `editing` 期间也不用远端 plan 覆盖 `planShot`；**视频**选择器始终可见以便添加；**剪辑轴**仅当剧本已有真正的 `EditTimeline`（`has_edit_timeline`）时展示全片多轨摘要（非子镜 `video_tracks` 短视频复制），并提供「前往剪辑 Tab」；无时间轴时不展示该区块
  - 分镜 Tab 胶片条随右侧 `script-panel-scroll` 纵向滚动（执行计划 + 看板内容一体滚动）
- TTS 试听 URL 统一为 `/api/.../assets/media/`（绝对本地路径自动映射）；打开分镜/剪辑 Tab 时自动刷新 TTS 时长（**不写**剪辑时间轴）
- 视图偏好持久化：`localStorage` 键 `svg.storyboard.view`
- 组件：[`StoryboardBoard.tsx`](../apps/web/src/components/board/StoryboardBoard.tsx)、[`StoryboardShotCard.tsx`](../apps/web/src/components/board/StoryboardShotCard.tsx)、[`ShotDetailDrawer.tsx`](../apps/web/src/components/board/ShotDetailDrawer.tsx)、[`ShotMiniTimeline.tsx`](../apps/web/src/components/board/ShotMiniTimeline.tsx)、[`ShotVoiceActCard.tsx`](../apps/web/src/components/board/ShotVoiceActCard.tsx)、[`ShotSubShotCard.tsx`](../apps/web/src/components/board/ShotSubShotCard.tsx)、[`ShotSegmentEditor.tsx`](../apps/web/src/components/board/ShotSegmentEditor.tsx)、[`shotSegmentUtils.ts`](../apps/web/src/utils/shotSegmentUtils.ts)

### 10.5 剪辑工作室（edit）

- 看板 API：`GET /api/projects/{id}/board/edit?script_id=…`
- **Edit Studio**：`GET/PATCH .../edit-timeline`（revision 乐观锁）；`POST .../export` FFmpeg 异步导出
- 前端剪辑 Tab：[`EditTabSimpleView.tsx`](../apps/web/src/editor/EditTabSimpleView.tsx) 简易预览 + 三种打开方式：
  - **剪辑修改**：全屏弹窗 [`EditorStudioModal`](../apps/web/src/editor/EditorStudioModal.tsx)
  - **单独页面**：哈希 `#/project/{id}/script/{scriptId}/edit` → [`EditorStudioPage`](../apps/web/src/pages/EditorStudioPage.tsx)
  - **新窗口打开**：系统浏览器新标签（`window.open`），保存后通过 `svg:edit-timeline-reloaded` 事件通知工作台刷新
- OpenCut Classic 规格：[`opencut-integration.md`](opencut-integration.md)、[`edit-studio-plan.md`](edit-studio-plan.md)

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

**启动恢复（2026-07-11）**：若进程异常退出后 `dev_store.json` 中剧本仍为 `executing` 且无活跃主编排任务，API 启动时自动重置为 `failed`，避免后续 chat/CRUD 持续 400/403。

**对话 API（2026-07-11）**：`POST .../chat` 返回 **202 Accepted**（含 `conversation_id`），主编排在后台执行；页面刷新后可通过 `GET .../executions/active` 恢复「执行中」UI；进度与结束态经 WebSocket 推送。

**对话性能（2026-07-12）**：长对话首屏仅加载最近 80 条时间线（`limit`/`before` 分页）；设置中关闭「展示 ReAct 详情」可显著降低流式期 DOM 压力。
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

| 资产类型 | 增 | 改 | 删 | 二次生成（未执行态） |
|----------|----|----|-----|---------------------|
| Script | — | ✅ | ✅ 无引用时 | — |
| plot / narration | ✅ | ✅ | ✅ 无引用 | — |
| character / prop / scene | ✅ 进共享池 | ✅ | ✅ 无跨剧本/分镜引用 | ✅ 生图 |
| voice_role | ✅ | ✅ | ✅ 无 TTS/分镜引用 | — |
| video_plan / shot | ✅ | ✅ | ✅ 无下游 | ✅ 分镜抽屉 TTS/frame/video |
| image（预生成） | ✅ | ✅ | ✅ 无分镜/剪辑引用 | ✅ |
| ai_video / tts / final | 执行后产生 | 执行后 | 执行后 | ✅ tts/video（fin 走导出） |

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
│  可选 Electron 壳 apps/desktop（IPC 本地读盘水合剪辑媒体） │
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
│   ├── web/                          # React 前端（Vite）
│   │   ├── layouts/ScriptWorkbench.tsx
│   │   ├── panels/ChatPanel/
│   │   ├── panels/ScriptPanel/
│   │   └── pages/ProjectConfig/
│   ├── api/                          # FastAPI + WebSocket
│   └── desktop/                      # Electron 壳（可选；IPC 本地读盘水合）
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
| 关系图 | @xyflow/react + @dagrejs/dagre | 看板 DAG，LR 布局、缩放与侧栏预览 |
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
| GET/PATCH | `/api/ai/config` | 统一 AI 配置（`llm` / `image` / `video` / `tts` / `export` 分区） |
| POST | `/api/projects/{id}/scripts` | 创建剧本 |
| GET | `/api/projects/{id}/scripts/{script_id}/assets` | 本片资产列表 |
| POST | `/api/projects/{id}/scripts/{script_id}/assets/text` | 新建文字资产 |
| PATCH | `/api/projects/{id}/assets/{asset_id}` | 更新资产 |
| DELETE | `/api/projects/{id}/scripts/{script_id}/assets/{asset_id}` | 删除文字资产；被引用时 **409** + `references[]` |
| GET | `/api/projects/{id}/assets/{asset_id}/lineage` | 单资产谱系 `AssetLineageView` |
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
| GET | `/api/projects/{id}/conversations/{conversation_id}/messages` | 唤醒：`?view=ui` 摘要；`?view=full` 完整时间线（子 Agent 多轮合并，与实时 WS 展示一致） |
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

### Phase 3：生产闭环（故事书模式）

| 任务 | 交付物 |
|------|--------|
| 图片 Agent | 生图 API 已接入（默认 Agnes AI） |
| 分镜 Agent | VideoPlan + Shot |
| TTS Agent | 配音生成 |
| 剪辑 Agent | FFmpeg Ken Burns + 配音 + 字幕合成 |
| 首个可播放成片 | storybook 端到端 |

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
| 4 | Embedding 模型 | AI 配置页独立分区；无 Key 时名称精确匹配回退 | 已实现 |
| 5 | API Key 存储 | 环境变量 / Vault，不落库明文 | 已设计 |
| 6 | 字幕生成 | TTS subtitle_cues → WhisperX 强制对齐（CUDA）→ 标点字数比例；见 `core/edit/whisperx_align.py` | 已实现（含 WhisperX P1） |
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
7. 故事书模式：分镜 → TTS → 剪辑（跳过 Video Agent）。
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
