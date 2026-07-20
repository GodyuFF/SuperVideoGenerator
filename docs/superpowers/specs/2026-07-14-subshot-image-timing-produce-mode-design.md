# 子镜画面时段 + 产出意图（produce_mode）设计

> 日期：2026-07-14  
> 状态：已批准  

> 方案：B（时段双轨展示/编辑 + 显式意图字段，与现有 videoGenMode 对齐）

---

## 1. 背景与目标

子镜挂接的画面（`sub_shots[].images[]`）本质是对剧本 **frame** 信息的引用；子镜层已有 `start_ms`/`end_ms`，但单张画面暂无独立时段。下游 Agent（video / editing）缺少稳定的结构化线索，难以仅凭描述判断应「静帧剪辑」还是「AI 生视频」。

**目标：**

1. **时段**：UI 展示子镜时段；每张关联画面可编辑自身时段（两者都要）。  
2. **意图**：在子镜上新增显式 `produce_mode`，由分镜/复核 Agent 根据「画面描述 + 画面时段」写出；video / editing Agent 优先执行该意图。  
3. 与现有前端 `VisualVideoGenMode`（`still` / `img2video` / `keyframes` / …）**映射对齐**，避免双轨枚举分叉。

**非目标（本期）：**

- 不新建独立 `edit_plan` JSON 流水线。  
- 不改变「子镜仅挂接 frame / video_clip」的资产边界。  
- 不强制改写已有剪辑轴 `EditTimeline` 写路径（仍由 editing 域 Tool 独占）。

---

## 2. 术语

| 术语 | 含义 |
|------|------|
| 子镜时段 | `ShotSubShot.start_ms` / `end_ms`，相对**镜起点** |
| 画面时段 | `ShotSubShotImage.start_ms` / `end_ms`，相对**镜起点**（与子镜同坐标系） |
| 产出意图 | `ShotSubShot.produce_mode`：静帧剪辑 / AI 生视频 / 混合 |
| videoGenMode | 前端/生视频 UI 已有模式；由 `produce_mode` + 既有 clip 状态映射或用户覆盖 |

---

## 3. 数据模型

### 3.1 `ShotSubShotImage`（`core/models/entities.py`）

新增字段（缺省填所属子镜区间，迁移时回填）：

```python
start_ms: int = 0   # 相对镜起点；默认 = 所属 sub_shot.start_ms
end_ms: int = 0     # 相对镜起点；默认 = 所属 sub_shot.end_ms
```

**校验（保存 / PATCH / Agent 写入时）：**

- `sub.start_ms <= img.start_ms < img.end_ms <= sub.end_ms`
- 同子镜内多图时段**允许重叠**（hybrid / 多参考）；不做强制首尾相接
- `end_ms == 0` 且 `start_ms == 0` 视为「未显式设置」→ 解析层按所属子镜区间展开

### 3.2 `ShotSubShot`

新增：

```python
ProduceMode = Literal["still", "text2video", "img2video"]

produce_mode: ProduceMode = "still"  # 故事书默认；有视频挂接时可推断为 img2video
produce_rationale: str = ""          # 短理由，可选，供下游 Agent / UI
```

> **修订（2026-07-14 同日）**：原 `still_edit`/`ai_video`/`hybrid` 已收敛为上述三值，与 UI「静图视频 / 文生视频 / 图生视频」一致；历史枚举读入时自动规范。

### 3.3 与 `VisualVideoGenMode` 映射

| produce_mode | 默认 videoGenMode | 下游职责 |
|--------------|-------------------|----------|
| `still` | `still` | editing / Ken Burns / 静图轨；挂接 frame |
| `text2video` | `text2video` | video_agent 文生；挂接 video_clip |
| `img2video` | `img2video` | video_agent 图生；挂接 frame + video_clip |

用户在抽屉里改 `videoGenMode` 时：

- 若改为非 `still` → 可将 `produce_mode` 抬升为 `ai_video`（或 hybrid，若同子镜仍有 still）  
- 若全部改回 `still` → `produce_mode = still_edit`  
（具体同步规则在实现计划中写成纯函数，单测锁定。）

### 3.4 持久化与兼容

- SQLite / JSON 计划稿随 Pydantic 模型扩展；旧数据缺字段时：  
  - image 时段 → 所属子镜区间  
  - `produce_mode` → 若子镜已有非 still 视频意图（`images[].kind == video` 或 videos 非空）则 `ai_video`，否则 `still_edit`  
- **无历史兼容双轨逻辑**：不保留旧字段别名层；一次解析默认填充即可（符合仓库「无历史兼容」原则下的「缺省填充」而非双路径执行）。

---

## 4. UI

### 4.1 只读（`ShotSubShotCard`）

- 头部：子镜 `start–end`（已有）  
- 每张画面条目：展示 **本图时段** `formatMs(start)–formatMs(end)` 与时长；无独立时段时显示「= 子镜时段」  
- 芯片：展示 `produce_mode` 文案（静帧剪辑 / AI 生视频 / 混合）与可选 `produce_rationale` 摘要

### 4.2 编辑（`ShotSegmentEditor` / 画面选择器附近）

- 子镜：`produce_mode` 下拉 + 可选 rationale 文本  
- 每张关联画面：`start_ms` / `end_ms` 数字输入；校验失败时表单错误（与现有 `validateShotSegmentEdits` 对齐）  
- PATCH 体经 `buildShotPatchFromSegments` 写出新字段

### 4.3 i18n

`board.json` 增加 `storyboard.subShot.produceMode*`、`imageStartMs` / `imageEndMs` 等键（中/英）。

---

## 5. Agent / Prompt / Tool

### 5.1 写入方

| Agent | 行为 |
|-------|------|
| `storyboard_agent` | `create_shots` 填写子镜描述、时段、挂接画面；按描述动作强度与时段长度推断 `produce_mode`；多图时尽量写出各 `images[].start_ms/end_ms` |
| `storyboard_refine_agent` | `review_shot` / 结构调整时可修订 `produce_mode` 与画面时段 |

### 5.2 执行方

| Agent | 行为 |
|-------|------|
| `video_agent` | 优先读 `produce_mode`；`still_edit` 跳过或仅补静图绑定；`ai_video`/`hybrid` 按画面时段与参考图生成 |
| `editing_agent` | `still_edit`/`hybrid` 时用画面时段 + `camera_motion` 规划静图轨/运镜；`ai_video` 以已生成 clip 为主 |

### 5.3 Prompt / Schema

- 更新 `storyboard_agent` / `storyboard_refine_agent` 固定区：说明字段语义与推断启发（动作强、时段短 → 倾向 ai_video；风光建立、长时段静帧 → still_edit）  
- Tool schema（`create_shots` / refine patch）增加 `produce_mode`、`produce_rationale`、`images[].start_ms/end_ms`  
- 更新 `docs/superpowers/reference/prompt-architecture.md`、`docs/superpowers/reference/tools-reference.md`、`docs/superpowers/reference/product-plan.md` 对应章节

---

## 6. API

- 镜 PATCH 已接受 `sub_shots` 数组：新字段随模型自动进出，**不新增**独立 REST 端点  
- 看板 / video-plan 序列化带出新字段，供前端与 Agent 上下文使用  
- 校验错误：400 + 明确字段路径（如 `sub_shots[0].images[1].end_ms`）

---

## 7. 测试

| 层级 | 要点 |
|------|------|
| 单元 | 默认回填；区间校验；`produce_mode` ↔ videoGenMode 映射纯函数 |
| 单元 | PATCH / parse / buildShotPatch 往返保留新字段 |
| Prompt/Agent（现有 scripted LLM） | create_shots 响应含新字段时计划稿落盘正确 |
| 回归 | 旧计划稿无新字段时仍可加载与展示 |

禁止在 `core/`、`apps/` 增加 mock；仅用 `tests/support` 脚本化响应。

---

## 8. 文件影响（实现时对照）

| 区域 | 文件（预期） |
|------|----------------|
| 模型 | `core/models/entities.py` |
| 解析/校验 | `core/llm/agent/llm_action.py`、shot sync / video-plan patch 路径 |
| Prompt | `core/llm/prompt/agents/storyboard_*`、`schema_builders.py` |
| 前端视图 | `shotSegmentUtils.ts`、`ShotSubShotCard.tsx`、`ShotSubShotFramePicker.tsx`、i18n |
| 文档 | `product-plan.md`、`data-storage.md` / schema、`prompt-architecture.md`、`tools-reference.md` |

---

## 9. 验收标准

1. 打开分镜编辑：子镜与单张画面均可看到时段；改画面时段并保存后刷新仍在。  
2. Agent `create_shots` 可写入 `produce_mode`；下游 Tool 上下文能读到。  
3. 故事书默认 `still_edit`；存在明确动作描述时 Agent 可标 `ai_video`/`hybrid`。  
4. 全量 `pytest tests/ -q` 通过；无非测试目录 mock。

---

## 10. 开放项（已锁定）

- [x] hybrid 下「自动拆分 still / img2video」是否本期做启发式，还是仅存意图、由 Agent 逐步填满？**已决定：本期只存意图 + 时段；hybrid 自动拆分启发式延后**（`core/edit/sub_shot_produce.py` 仅提供 `produce_mode↔videoGenMode` 映射，不做时段拆分）。  
- [x] `produce_rationale` 是否必填？**已决定：可选**（schema 与模型默认 `""`）。

---

## 审阅检查（self-review）

- [x] 无 TBD/占位符作为主路径  
- [x] 与「子镜仅挂 frame/video_clip」边界一致  
- [x] 坐标系统一为相对镜起点  
- [x] 与现有 videoGenMode 有明确映射表  
- [x] 范围已砍掉独立 edit_plan  
