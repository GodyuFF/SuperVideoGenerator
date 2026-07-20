# 子镜画面时段 + produce_mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为子镜关联画面增加相对镜起点的时段字段，并为子镜增加显式 `produce_mode`（still_edit / ai_video / hybrid），使 Agent 与分镜 UI 能基于「画面描述 + 画面时段」决定剪辑或 AI 生视频。

**Architecture:** 领域字段落在 `ShotSubShot` / `ShotSubShotImage`；`core/edit/sub_shot_produce.py` 提供时段回填、区间校验、默认意图推断与 `produce_mode↔videoGenMode` 映射纯函数；Agent 经 `llm_action` 解析与 Tool schema 写入；前端 `shotSegmentUtils` + 子镜卡片/编辑器读写并展示。本期不实现 hybrid 自动拆分启发式。

**Tech Stack:** Python/Pydantic（`core/`）、FastAPI video-plan PATCH（既有）、React/TS 看板（`apps/web`）、pytest、`docs/` 同步。

**Spec:** [`docs/superpowers/specs/2026-07-14-subshot-image-timing-produce-mode-design.md`](../specs/2026-07-14-subshot-image-timing-produce-mode-design.md)

---

## File map

| File | Responsibility |
|------|----------------|
| `core/models/entities.py` | `ProduceMode` Literal；`ShotSubShotImage.start_ms/end_ms`；`ShotSubShot.produce_mode/produce_rationale` |
| `core/edit/sub_shot_produce.py` | **新建**：normalize / validate / infer / mode 映射 |
| `core/edit/shot_validate.py` | 结构校验时调用 image 时段校验 |
| `core/llm/agent/llm_action.py` | `_parse_sub_shot_image` / `_parse_sub_shots` 读新字段并 finalize |
| `core/llm/prompt/tools/schema_builders.py` | Tool JSON schema 暴露新字段 |
| `core/llm/prompt/agents/storyboard_agent/fixed/*.md` | 写入意图与画面时段说明 |
| `core/llm/prompt/agents/storyboard_refine_agent/fixed/*.md` | 复核可改意图/时段 |
| `core/llm/prompt/agents/video_agent/fixed/*.md` | 优先读 `produce_mode` |
| `core/llm/prompt/agents/editing_agent/fixed/*.md`（若存在 role） | 优先读 `produce_mode` |
| `apps/web/src/utils/shotSegmentUtils.ts` | 视图类型、parse/patch/validate、映射 |
| `apps/web/src/components/board/ShotSubShotCard.tsx` | 只读展示时段与意图 |
| `apps/web/src/components/board/ShotSubShotFramePicker.tsx` | 编辑单图时段（若编辑入口在此或 SegmentEditor） |
| `apps/web/src/components/board/ShotSegmentEditor.tsx` | 子镜 produce_mode 编辑 |
| `apps/web/src/i18n/locales/{zh-CN,en}/board.json` | 文案 |
| `docs/superpowers/reference/product-plan.md` 等 | 文档同步 |
| `tests/unit/test_sub_shot_produce.py` | **新建** 纯函数测试 |

---

### Task 1: 领域模型 + 纯函数模块（TDD）

**Files:**
- Create: `core/edit/sub_shot_produce.py`
- Create: `tests/unit/test_sub_shot_produce.py`
- Modify: `core/models/entities.py`（`ShotSubShotImage`、`ShotSubShot` 附近约 463–508 行）

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/test_sub_shot_produce.py
from core.edit.sub_shot_produce import (
    expand_image_timing,
    infer_produce_mode,
    produce_mode_to_video_gen_mode,
    sync_produce_mode_from_video_gen_modes,
    validate_sub_shot_image_timings,
    video_gen_mode_to_produce_mode_hint,
)
from core.models.entities import ShotSubShot, ShotSubShotImage, ShotSubShotVideo


def test_expand_image_timing_unset_fills_sub_range():
    sub = ShotSubShot(start_ms=1000, end_ms=4000, description="d")
    img = ShotSubShotImage(start_ms=0, end_ms=0)
    s, e = expand_image_timing(img, sub)
    assert (s, e) == (1000, 4000)


def test_validate_image_timing_must_lie_inside_sub():
    sub = ShotSubShot(start_ms=0, end_ms=3000, description="d", images=[
        ShotSubShotImage(start_ms=0, end_ms=4000),
    ])
    issues = validate_sub_shot_image_timings(sub)
    assert any("end_ms" in x or "区间" in x for x in issues)


def test_infer_produce_mode_ai_when_videos_present():
    sub = ShotSubShot(
        start_ms=0,
        end_ms=3000,
        description="跑过广场",
        videos=[ShotSubShotVideo(start_ms=0, end_ms=3000)],
    )
    assert infer_produce_mode(sub) == "ai_video"


def test_produce_mode_to_video_gen_mode():
    assert produce_mode_to_video_gen_mode("still_edit") == "still"
    assert produce_mode_to_video_gen_mode("ai_video") == "img2video"


def test_sync_produce_mode_from_video_gen_modes_all_still():
    assert sync_produce_mode_from_video_gen_modes(["still", "still"]) == "still_edit"


def test_sync_produce_mode_from_video_gen_modes_mixed():
    assert sync_produce_mode_from_video_gen_modes(["still", "img2video"]) == "hybrid"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/unit/test_sub_shot_produce.py -v`  
Expected: FAIL（模块/符号不存在）

- [ ] **Step 3: 扩展实体模型**

在 `core/models/entities.py`：

```python
ProduceMode = Literal["still_edit", "ai_video", "hybrid"]
```

`ShotSubShotImage` 增加：

```python
start_ms: int = 0  # 相对镜起点；0+0 表示未显式设置
end_ms: int = 0
```

`ShotSubShot` 增加：

```python
produce_mode: ProduceMode = "still_edit"
produce_rationale: str = ""
```

类/字段 docstring 用中文说明职责。

- [ ] **Step 4: 实现 `core/edit/sub_shot_produce.py`**

```python
"""子镜画面时段回填、校验与 produce_mode 映射。"""

from __future__ import annotations

from typing import Literal

from core.models.entities import ProduceMode, ShotSubShot, ShotSubShotImage

VideoGenMode = Literal["still", "img2video", "text2video", "keyframes"]


def expand_image_timing(img: ShotSubShotImage, sub: ShotSubShot) -> tuple[int, int]:
    """未显式设置（0,0）时回填所属子镜区间；已设置则原样返回。"""
    if int(img.start_ms or 0) == 0 and int(img.end_ms or 0) == 0:
        return int(sub.start_ms), int(sub.end_ms)
    return max(0, int(img.start_ms)), max(0, int(img.end_ms))


def apply_image_timing_defaults(sub: ShotSubShot) -> ShotSubShot:
    """将 images[] 未设置时段回填为子镜区间（返回新 ShotSubShot）。"""
    if not sub.images:
        return sub
    new_images: list[ShotSubShotImage] = []
    for img in sub.images:
        s, e = expand_image_timing(img, sub)
        if s != img.start_ms or e != img.end_ms:
            new_images.append(img.model_copy(update={"start_ms": s, "end_ms": e}))
        else:
            new_images.append(img)
    return sub.model_copy(update={"images": new_images})


def validate_sub_shot_image_timings(sub: ShotSubShot) -> list[str]:
    """校验每张画面时段落在子镜内且 start < end。"""
    issues: list[str] = []
    sub_s, sub_e = int(sub.start_ms), int(sub.end_ms)
    for i, img in enumerate(sub.images):
        s, e = expand_image_timing(img, sub)
        label = f"images[{i}]"
        if e <= s:
            issues.append(f"{label}: end_ms 必须大于 start_ms")
        if s < sub_s or e > sub_e:
            issues.append(f"{label}: 时段 [{s},{e}] 必须落在子镜 [{sub_s},{sub_e}] 内")
    return issues


def infer_produce_mode(sub: ShotSubShot) -> ProduceMode:
    """旧数据缺 produce_mode 时的推断：视频意图或 videos 非空 → ai_video。"""
    if any(v.media_id or True for v in sub.videos) and sub.videos:
        return "ai_video"
    if any(getattr(img, "kind", "static") == "video" for img in sub.images):
        return "ai_video"
    return "still_edit"


def produce_mode_to_video_gen_mode(mode: ProduceMode) -> VideoGenMode:
    """子镜意图 → 默认 UI videoGenMode。"""
    if mode == "still_edit":
        return "still"
    return "img2video"


def video_gen_mode_to_produce_mode_hint(mode: str) -> ProduceMode:
    """单个 videoGenMode → 意图提示。"""
    return "still_edit" if (mode or "still") == "still" else "ai_video"


def sync_produce_mode_from_video_gen_modes(modes: list[str]) -> ProduceMode:
    """抽屉内多个画面/成片模式汇总为子镜 produce_mode。"""
    normalized = [(m or "still").strip() for m in modes] or ["still"]
    any_ai = any(m != "still" for m in normalized)
    any_still = any(m == "still" for m in normalized)
    if any_ai and any_still:
        return "hybrid"
    if any_ai:
        return "ai_video"
    return "still_edit"


def finalize_sub_shot(
    sub: ShotSubShot,
    *,
    produce_mode_from_input: bool,
) -> ShotSubShot:
    """解析后定稿：回填画面时段；若输入未带 produce_mode 则推断。"""
    out = apply_image_timing_defaults(sub)
    if not produce_mode_from_input:
        out = out.model_copy(update={"produce_mode": infer_produce_mode(out)})
    return out
```

注意：`infer_produce_mode` 中 `videos` 非空即 `ai_video`（即使 media_id 空，表示预规划）。修正 Step 1 测试与实现一致，不要写 `any(v.media_id or True ...)` 这种冗余——实现里用 `if sub.videos: return "ai_video"`。

- [ ] **Step 5: 跑测试通过**

Run: `pytest tests/unit/test_sub_shot_produce.py -v`  
Expected: PASS

- [ ] **Step 6: Commit**（仅当用户要求提交时执行）

```bash
git add core/models/entities.py core/edit/sub_shot_produce.py tests/unit/test_sub_shot_produce.py
git commit -m "feat: add sub-shot image timing and produce_mode model helpers"
```

---

### Task 2: 解析路径 + 结构校验接入

**Files:**
- Modify: `core/llm/agent/llm_action.py`（`_parse_sub_shot_image` ~249、`_parse_sub_shots` ~314）
- Modify: `core/edit/shot_validate.py`（`validate_shot_structure`）
- Test: `tests/unit/test_sub_shot_produce.py`（追加 parse 集成或新建 `tests/unit/test_parse_sub_shot_produce.py`）

- [ ] **Step 1: 失败测试——parse 保留字段并回填**

```python
# tests/unit/test_parse_sub_shot_produce.py
from core.llm.agent.llm_action import _parse_sub_shots


def test_parse_sub_shots_keeps_produce_mode_and_image_timing():
    subs = _parse_sub_shots([
        {
            "start_ms": 0,
            "end_ms": 4000,
            "description": "冲刺",
            "produce_mode": "ai_video",
            "produce_rationale": "动作强",
            "images": [
                {"kind": "static", "frame_asset_id": "txt_f1", "start_ms": 500, "end_ms": 2000},
            ],
        }
    ])
    assert len(subs) == 1
    assert subs[0].produce_mode == "ai_video"
    assert subs[0].produce_rationale == "动作强"
    assert subs[0].images[0].start_ms == 500
    assert subs[0].images[0].end_ms == 2000


def test_parse_sub_shots_infers_mode_and_fills_timing_when_absent():
    subs = _parse_sub_shots([
        {
            "start_ms": 0,
            "end_ms": 3000,
            "description": "空镜",
            "images": [{"kind": "static", "frame_asset_id": "txt_f1"}],
        }
    ])
    assert subs[0].produce_mode == "still_edit"
    assert subs[0].images[0].start_ms == 0
    assert subs[0].images[0].end_ms == 3000
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/unit/test_parse_sub_shot_produce.py -v`  
Expected: FAIL（字段未解析 / 未回填）

- [ ] **Step 3: 改 `_parse_sub_shot_image`**

解析 `start_ms`/`end_ms`（`max(0, int(...))`），放入 `fields`。

- [ ] **Step 4: 改 `_parse_sub_shots`**

```python
from core.edit.sub_shot_produce import finalize_sub_shot
from core.models.entities import ProduceMode  # 或校验字面量

_VALID_PRODUCE = {"still_edit", "ai_video", "hybrid"}

# 循环内：
raw_mode = str(item.get("produce_mode") or "").strip()
produce_mode_from_input = raw_mode in _VALID_PRODUCE
mode = raw_mode if produce_mode_from_input else "still_edit"
sub = ShotSubShot(
    ...,
    produce_mode=mode,  # type: ignore[arg-type]
    produce_rationale=str(item.get("produce_rationale") or "").strip(),
    images=...,
    videos=...,
)
sub_shots.append(finalize_sub_shot(sub, produce_mode_from_input=produce_mode_from_input))
```

- [ ] **Step 5: `validate_shot_structure` 追加**

在子镜循环处（读现有 sub_shots 校验逻辑附近）：

```python
from core.edit.sub_shot_produce import validate_sub_shot_image_timings

for si, sub in enumerate(shot.sub_shots):
    for msg in validate_sub_shot_image_timings(sub):
        issues.append(f"{label} sub_shots[{si}]: {msg}")
```

- [ ] **Step 6: 跑测试**

Run: `pytest tests/unit/test_parse_sub_shot_produce.py tests/unit/test_sub_shot_produce.py tests/unit/test_shot_validate.py -q`（若无后者则跳过该文件）  
Expected: PASS

- [ ] **Step 7: Commit**（仅当用户要求时）

```bash
git add core/llm/agent/llm_action.py core/edit/shot_validate.py tests/unit/test_parse_sub_shot_produce.py
git commit -m "feat: parse and validate sub-shot image timing and produce_mode"
```

---

### Task 3: Tool schema + Prompt

**Files:**
- Modify: `core/llm/prompt/tools/schema_builders.py`（`build_sub_shot_image_schema`、`build_sub_shot_schema`）
- Modify: `core/llm/prompt/agents/storyboard_agent/fixed/role.default.md`
- Modify: `core/llm/prompt/agents/storyboard_agent/fixed/role.storybook.md`
- Modify: `core/llm/prompt/agents/storyboard_agent/fixed/role.ai_video.md`
- Modify: `core/llm/prompt/agents/storyboard_refine_agent/fixed/role.default.md`
- Modify: `core/llm/prompt/agents/video_agent/fixed/role.default.md` 与 `role.ai_video.md` / `role.storybook.md`
- Modify: editing_agent 固定区中描述分镜输入的文件（全局搜索 `sub_shots` 后更新）

- [ ] **Step 1: 扩展 schema**

`build_sub_shot_image_schema` properties 增加：

```python
"start_ms": {"type": "integer", "description": "该画面占用时段起点，相对镜起点毫秒；省略则等于所属子镜 start_ms"},
"end_ms": {"type": "integer", "description": "该画面占用时段终点，相对镜起点毫秒；省略则等于所属子镜 end_ms"},
```

`build_sub_shot_schema` properties 增加：

```python
"produce_mode": {
    "type": "string",
    "enum": ["still_edit", "ai_video", "hybrid"],
    "description": "产出意图：still_edit=静帧剪辑；ai_video=AI生视频；hybrid=混合",
},
"produce_rationale": {
    "type": "string",
    "description": "可选短理由（依据画面描述与时段）",
},
```

- [ ] **Step 2: Prompt 片段（写入方）**

在 storyboard `role.default.md` / storybook / ai_video 增加要点（中文）：

- 每个 `sub_shots[]` 须根据描述动作强度与时段推断 `produce_mode`（风光长静帧→`still_edit`；强动作短促→`ai_video`；同子镜多意图→`hybrid`）。
- 多图时为 `images[]` 填写相对镜起点的 `start_ms`/`end_ms`（落在子镜区间内）。
- 可选 `produce_rationale`。

refine agent：复核时可修订上述字段。

- [ ] **Step 3: Prompt 片段（执行方）**

video_agent：生成前读取 `produce_mode`；`still_edit` 不强制 generate clips；`ai_video`/`hybrid` 按画面时段与参考图执行。

editing_agent：`still_edit`/`hybrid` 用画面时段 + `camera_motion` 规划；`ai_video` 以已生成 clip 为主。

- [ ] **Step 4: 冒烟——schema 含新键**

```python
# tests/unit/test_sub_shot_schema_produce.py
from core.llm.prompt.tools.schema_builders import build_sub_shot_schema, build_sub_shot_image_schema

def test_sub_shot_schema_has_produce_mode():
    s = build_sub_shot_schema()
    assert "produce_mode" in s["properties"]
    assert set(s["properties"]["produce_mode"]["enum"]) == {"still_edit", "ai_video", "hybrid"}

def test_sub_shot_image_schema_has_timing():
    s = build_sub_shot_image_schema()
    assert "start_ms" in s["properties"] and "end_ms" in s["properties"]
```

Run: `pytest tests/unit/test_sub_shot_schema_produce.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**（仅当用户要求时）

```bash
git add core/llm/prompt/
git commit -m "feat: expose produce_mode and image timing in storyboard tool schemas"
```

---

### Task 4: 前端类型、parse/patch/validate、映射

**Files:**
- Modify: `apps/web/src/utils/shotSegmentUtils.ts`
- Modify: `apps/web/src/types/videoPlan.ts`（若有独立 ShotSubShot 类型）
- Create: `apps/web/src/utils/subShotProduce.ts`（可选；若希望与后端对称的纯函数）

> 仓库可能无前端单元测试 runner；用 TS 类型自洽 + 手测清单。若存在 vitest，则加对应测试。

- [ ] **Step 1: 扩展视图类型**

`ShotSubShotFrameView` 增加：

```typescript
startMs?: number;
endMs?: number;
```

`ShotSubShotView` 增加：

```typescript
produceMode: "still_edit" | "ai_video" | "hybrid";
produceRationale?: string;
```

- [ ] **Step 2: 映射纯函数（可放同文件底部）**

```typescript
export type ProduceMode = "still_edit" | "ai_video" | "hybrid";

/** produce_mode → 默认 videoGenMode。 */
export function produceModeToVideoGenMode(mode: ProduceMode): VisualVideoGenMode {
  return mode === "still_edit" ? "still" : "img2video";
}

/** 多个 videoGenMode 汇总子镜 produce_mode。 */
export function syncProduceModeFromVideoGenModes(modes: VisualVideoGenMode[]): ProduceMode {
  const list = modes.length ? modes : (["still"] as VisualVideoGenMode[]);
  const anyAi = list.some((m) => m !== "still");
  const anyStill = list.some((m) => m === "still");
  if (anyAi && anyStill) return "hybrid";
  if (anyAi) return "ai_video";
  return "still_edit";
}
```

- [ ] **Step 3: `parseSubShotImagesFromPlan`**

从 `img.start_ms`/`end_ms` 读入；若均为 0/缺省，用子镜 `startMs`/`endMs` 填视图字段。

- [ ] **Step 4: `parseSubShotsFromPlan` / `newSubShot` / fallback**

写入 `produceMode`（默认 `still_edit` 或来自 plan）、`produceRationale`。  
`newSubShot`：`produceMode: "still_edit"`。  
当 `videoGenMode` 变更时，可选调用 `syncProduceModeFromVideoGenModes` 更新子镜（在 SegmentEditor 的 updateSubShot 或专用 handler）。

- [ ] **Step 5: `buildShotPatchFromSegments`**

`images` map 增加 `start_ms`/`end_ms`；sub_shot 增加 `produce_mode`/`produce_rationale`。

- [ ] **Step 6: `validateShotSegmentEdits`**

对每个 subShot 的每张 image：若设置了 start/end，须 `sub.startMs <= img.startMs < img.endMs <= sub.endMs`；失败返回新 i18n key，例如 `storyboard.subShot.validationImageTime`。

---

### Task 5: UI + i18n

**Files:**
- Modify: `apps/web/src/components/board/ShotSubShotCard.tsx`
- Modify: `apps/web/src/components/board/ShotSegmentEditor.tsx`（或 FramePicker 内联字段）
- Modify: `apps/web/src/i18n/locales/zh-CN/board.json`
- Modify: `apps/web/src/i18n/locales/en/board.json`

- [ ] **Step 1: i18n 键**

```json
"produceMode": "产出意图",
"produceModeStill": "静帧剪辑",
"produceModeAi": "AI 生视频",
"produceModeHybrid": "混合",
"produceRationale": "意图说明",
"imageStartMs": "画面起点(ms)",
"imageEndMs": "画面终点(ms)",
"imageTiming": "{{start}}–{{end}}",
"imageTimingSameAsSub": "与子镜时段相同",
"validationImageTime": "画面时段必须落在所属子镜内且终点大于起点"
```

放在 `storyboard.subShot` 下（中英同步）。

- [ ] **Step 2: 只读卡**

- 子镜头部附近：`meta-chip` 显示 produce_mode 文案；有 rationale 则 `muted` 一行摘要（截断约 80 字）。  
- 每张画面条目：显示本图时段；若与子镜相同显示「与子镜时段相同」。

- [ ] **Step 3: 编辑态**

在 `ShotSubShotCard` editable 字段区增加：

- `select`：`produceMode`  
- `input`：`produceRationale`（可选）  
- 每张画面（FramePicker 列表或 images map）：`startMs`/`endMs` number inputs，`onChange` 更新对应 `images[i]`

保存走既有 `buildShotPatchFromSegments`。

- [ ] **Step 4: 手测清单**

1. 打开分镜编辑 → 见子镜意图与画面时段  
2. 改画面时段越界 → 保存被拦并提示  
3. 合法保存 → 刷新后仍在  
4. 从谱系跳转打开分镜（若适用）不受影响  

---

### Task 6: 产品文档同步

**Files:**
- Modify: `docs/superpowers/reference/product-plan.md`（分镜子镜结构、§10 分镜抽屉）
- Modify: `docs/superpowers/reference/data-storage.md` 或 `docs/superpowers/reference/data-storage-schema.md`（ShotSubShot / Image 字段表）
- Modify: `docs/superpowers/reference/prompt-architecture.md`（storyboard 动态/固定区说明一行）
- Modify: `docs/superpowers/reference/tools-reference.md`（create_shots / refine 字段）
- Modify: design spec 状态保持「已批准」；开放项勾选本期不做 hybrid 启发式

- [ ] **Step 1: 按规格 §3–5 更新各文档日期与字段表**（无占位符）

- [ ] **Step 2: Commit**（仅当用户要求时）

```bash
git add docs/
git commit -m "docs: document sub-shot image timing and produce_mode"
```

---

### Task 7: 全量验证

- [ ] **Step 1: 后端全量测试**

Run: `pytest tests/ -q`  
Expected: 全部通过；无在 `core/`/`apps/` 新增 mock

- [ ] **Step 2: 前端类型（可选）**

Run: `cd apps/web; npx tsc --noEmit -p tsconfig.json`  
若仓库已有大量无关 TS 错误，至少确保本改动文件无新增错误（ReadLints）。

- [ ] **Step 3: 对照验收标准（spec §9）逐条打勾**

---

## Spec coverage self-review

| Spec 要求 | Task |
|-----------|------|
| images[].start_ms/end_ms | 1, 2, 4 |
| produce_mode / rationale | 1, 2, 4, 5 |
| 校验落在子镜内 | 1, 2, 4 |
| (0,0) 回填子镜区间 | 1, 2 |
| 旧数据推断 | 1, 2 |
| videoGenMode 映射 | 1, 4 |
| UI 只读+编辑 | 5 |
| Agent prompt/schema | 3 |
| API 无新端点、PATCH 自动 | 2（随模型） |
| 文档 | 6 |
| 不做 hybrid 启发式拆分 | 刻意省略 |
| 全量 pytest | 7 |

## Placeholder scan

无 TBD；Commit 步骤标注「仅当用户要求时」以遵守仓库提交规则。
