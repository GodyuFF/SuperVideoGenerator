# 详情页「实际生成提示词」预览设计

> 日期：2026-07-20  
> 状态：已批准 / 已实现  
> 方案：A（后端 resolved-prompt API + 详情页小眼睛弹层）

---

## 1. 背景与目标

图文资产详情主区已展示**存档**提示词（`image_prompt` / `video_prompt`）。实际生图/生视频时，后端还会拼接 `【关联资产上下文】` 等动态块，且**不写回**资产字段，用户无法在 UI 中核对「模型真正看到的完整提示词」。

**目标：**

1. 主区仍显示存档版提示词（行为不变）。  
2. 提示词区块旁提供「小眼睛」入口，点击后展示**实际生成用**完整提示词（只读 + 可复制）。  
3. 预览逻辑与生图/生视频路径一致，禁止前端自行拼装导致漂移。

**非目标（本期）：**

- 不在弹层做「存档版 vs 实际版」双栏对照（可用短说明文案区分即可）。  
- 不分镜抽屉同步入口（可后续加）。  
- 不把完整 prompt 强制写回 `content` 或依赖 media.metadata 历史快照作为主数据源。  
- 不改 Agent / Tool 生图编排本身。

---

## 2. 术语

| 术语 | 含义 |
|------|------|
| 存档提示词 | 资产 `content.image_prompt` / `video_prompt`（及角色等 `compose_base` 结果字段） |
| 实际生成提示词 | 调用生图/生视频 API 时最终使用的 prompt（含关联资产动态块等） |
| 关联资产上下文 | `core/assets/linked_assets_prompt.py` 生成的 `【关联资产上下文】` 块 |

---

## 3. API

### 3.1 端点

```
GET /api/projects/{project_id}/assets/{asset_id}/resolved-prompt
```

只读；与现有 `GET .../lineage` 同级，挂在 `apps/api/routes/projects.py`。

### 3.2 响应

```json
{
  "asset_id": "text_…",
  "asset_type": "frame",
  "kind": "image",
  "authored_prompt": "用户/锁存主提示词原文…",
  "resolved_prompt": "主提示词\n\n【关联资产上下文】\n…",
  "negative_prompt": "…",
  "differs_from_authored": true
}
```

| 字段 | 说明 |
|------|------|
| `kind` | `image` \| `video`（frame/角色等走生图；`video_clip` 走生视频） |
| `authored_prompt` | 存档主提示词（便于前端对照，可选展示） |
| `resolved_prompt` | **实际生成用**全文 |
| `negative_prompt` | 有则返回（生图）；video 可空字符串 |
| `differs_from_authored` | `resolved_prompt` 与 `authored_prompt` 规范化后是否不同（便于 UI 提示「含额外上下文」） |

### 3.3 组装规则（必须复用现有函数）

| `asset_type` | `resolved_prompt` 来源 | `negative_prompt` |
|--------------|------------------------|-------------------|
| `frame` | `resolve_frame_generation_prompt(store, content)` | `compose_frame_image_prompt` / content 中的 negative，与生图一致即可 |
| `video_clip` | `compose_video_clip_prompt(content, store=store)` | `""` |
| `character` / `prop` / `scene` | `compose_base_image_prompt`（或 content 已锁存的 `image_prompt` + 若有关联块则 merge；**本期以资产级主形象为准**，不展开全部变体） | `_compose_negative` / content.negative_prompt |

错误：

- 资产不存在或不属于该项目 → 404  
- 类型不支持预览 → 400（当前仅上述类型）

可选 query：`variant_id`（本期可不实现；若实现则对指定变体走 `compose_variant_image_prompt`）。

---

## 4. 前端 UI

### 4.1 入口

- 组件：`ImageTextAssetDetailModal`  
- 位置：「提示词」/「生图提示词」`AssetDetailSection` 标题行旁小眼睛按钮（扩展 `AssetDetailSection` 支持 `titleExtra` / `actions`，或局部自定义标题行，保持暗房胶片风格）  
- 显示条件：有存档提示词，**或** `element_refs` 非空（仍可能拼出关联块）；否则不渲染按钮  
- 图标：现有设计系统图标集中的 Eye / EyeOff；`aria-label` / tooltip：「查看实际生成提示词」

### 4.2 弹层

- 轻量 Modal / Dialog（复用项目已有 overlay 模式，勿另起一套壳）  
- 标题：「实际生成提示词」  
- 说明一行（muted）：「含关联资产上下文等，未写回资产字段」；若 `differs_from_authored === false` 可改为「与存档提示词一致」  
- 正文：只读 `<pre class="prompt-pre">`  
- 操作：关闭、一键复制 `resolved_prompt`  
- 状态：loading / error（重试）/ 成功  

按需请求：仅在首次打开（或资产 id / 内容变更后）调用 API，避免详情打开即打满。

### 4.3 编辑器

- `ImageTextAssetEditor`：**本期可不加**眼睛按钮（详情 Modal 为主）；若成本低可共用同一弹层组件。

### 4.4 i18n

- `zh-CN` / `en` 同步：按钮 aria、弹层标题、说明、复制成功/失败文案。

---

## 5. 测试

- **单元**：对 store fixture 调用解析函数 / 新 service，断言 frame 含 `【关联资产上下文】` 且含角色名；无 `element_refs` 时 `differs_from_authored` 为 false（若 authored 即 resolved）。  
- **API**：`GET resolved-prompt` 200 字段齐全；未知资产 404。  
- **前端**：可选轻量测试（按钮在有 prompt 时出现）；无强制 E2E。

全量 `pytest tests/ -v`；前端若有相关单测则 `npm test`。

---

## 6. 文档同步

- `docs/product-plan.md`：关联资产动态提示词旁补充「详情页可预览实际生成提示词」。  
- `docs/code-design-plan.md`：API 表增加 `GET .../resolved-prompt`。  
- `docs/frontend-style-guide.md`：若新增 section actions / 弹层模式，补一句。  
- 本文件状态改为「已批准」后进入实现计划。

---

## 7. 实现落点（预览）

| 层 | 文件 |
|----|------|
| 领域 | 新建薄封装如 `core/assets/resolved_prompt.py`（聚合类型分支，调用现有 compose/resolve） |
| API | `apps/api/routes/projects.py` |
| 前端 | `ResolvedPromptPreview`（新小组件）+ `ImageTextAssetDetailModal`；样式 `asset-detail.css` |
| 测试 | `tests/unit/test_resolved_prompt.py`、`tests/api/` 对应用例 |
| i18n | `apps/web/src/i18n/locales/*/board.json` 或 asset 相关命名空间 |

---

## 8. 决策摘要

| 项 | 决定 |
|----|------|
| 方案 | A：后端 API |
| 主区 | 仍显示存档提示词 |
| 眼睛 | 实际生成完整提示词 |
| 双栏对照 | 本期不做 |
| 分镜抽屉 | 本期不做 |
| 写回 content | 否 |
