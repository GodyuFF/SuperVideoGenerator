# Generation Queue Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 进程内图片/视频统一串行生成队列，WebSocket 快照 + 工作台右侧抽屉展示待办与进度。

**Architecture:** `core/generation/` 持有全局单例 `GenerationQueue`（一条工人）；入队去重后串行调用 runner（二次生成走 `regenerate_asset`，Agent 项走单条 `_generate_one_item` / `_generate_one_clip`）；状态变更经 `EventEmitter` 推送 `generation_queue_snapshot`；前端 `GenerationQueueContext` + `GenerationQueueDrawer`。

**Tech Stack:** Python asyncio、FastAPI、现有 EventEmitter/WebSocket、React Context、`useResizableDrawerWidth` 抽屉模式。

**Spec:** `docs/superpowers/specs/2026-07-16-generation-queue-design.md`

## Global Constraints

- 同一时刻全局仅 1 条 `running`（跨剧本也不并行工人）。
- TTS / audio 二次生成**不入队**，保持现有 `regenerate_asset` 直跑。
- 队列仅内存；进程重启清空。
- 禁止在 `core/` / `apps/` 写 mock；测试 mock 仅在 `tests/`。
- 新类/函数中文 docstring / JSDoc；完成后同步 `docs/superpowers/reference/code-design-plan.md`、`docs/superpowers/reference/product-plan.md`、`docs/superpowers/reference/frontend-style-guide.md`（若有抽屉段落）。
- 保留 `image_gen_progress` / `assets_changed`；侧栏以 snapshot 为准。
- Agnes `create_min_interval_sec` 仍生效，与队列串行叠加为预期行为。

## File Structure

| 路径 | 职责 |
|------|------|
| `core/generation/__init__.py` | 导出 `get_generation_queue` / 类型 |
| `core/generation/models.py` | `GenerationJob`、`GenerationKind`、`GenerationSource`、`QueueSnapshot` |
| `core/generation/queue.py` | 入队、去重、工人、`wait_until_done`、`snapshot_for_script` |
| `core/generation/runner.py` | 按 job 执行单条 image/video |
| `core/generation/bridge.py` | Agent 批处理：拆条入队并等待 |
| `apps/api/routes/generation_queue.py` | `GET` / `POST .../enqueue` |
| `apps/api/state.py` | 挂载单例 queue + emitter |
| `apps/api/routes/projects.py` | image/video regenerate → 入队后立即 202 |
| `apps/api/main.py` | `include_router` |
| `apps/web/src/context/GenerationQueueContext.tsx` | snapshot 状态 |
| `apps/web/src/components/GenerationQueueDrawer.tsx` | 右侧抽屉 |
| `apps/web/src/hooks/useWorkbenchWs.ts` | 转发 snapshot |
| `apps/web/src/utils/batchAssetStudio.ts` | 入队后等待队列完成（concurrency=1 或全量 enqueue + wait） |
| `tests/unit/test_generation_queue.py` | 去重 / 串行 / 失败续跑 / snapshot |
| `tests/api/test_generation_queue_api.py` | GET/POST |

---

### Task 1: `GenerationJob` + `GenerationQueue` 核心（假 runner）

**Files:**
- Create: `core/generation/__init__.py`
- Create: `core/generation/models.py`
- Create: `core/generation/queue.py`
- Test: `tests/unit/test_generation_queue.py`

**Interfaces:**
- Produces:
  - `GenerationJob` dataclass（字段见下）
  - `GenerationQueue.enqueue(...) -> GenerationJob`
  - `GenerationQueue.snapshot_for_script(script_id) -> dict`
  - `GenerationQueue.wait_until_done(job_ids: list[str], timeout_sec: float | None = None) -> list[GenerationJob]`
  - `GenerationQueue.set_runner(runner: Callable[[GenerationJob], Awaitable[None]])`
  - `get_generation_queue() -> GenerationQueue` / `reset_generation_queue_for_tests()`

- [ ] **Step 1: 写失败单测（去重 + 串行 + 失败续跑）**

```python
# tests/unit/test_generation_queue.py
import asyncio
import pytest
from core.generation.queue import GenerationQueue, reset_generation_queue_for_tests
from core.generation.models import GenerationJob


@pytest.fixture(autouse=True)
def _reset_queue():
    reset_generation_queue_for_tests()
    yield
    reset_generation_queue_for_tests()


@pytest.mark.asyncio
async def test_enqueue_dedupes_same_asset():
    q = GenerationQueue()
    order: list[str] = []

    async def runner(job: GenerationJob) -> None:
        order.append(job.asset_id)
        await asyncio.sleep(0.01)

    q.set_runner(runner)
    a = await q.enqueue(
        project_id="p1",
        script_id="s1",
        kind="image",
        asset_id="ta_1",
        label="角色A",
        source="regenerate",
    )
    b = await q.enqueue(
        project_id="p1",
        script_id="s1",
        kind="image",
        asset_id="ta_1",
        label="角色A",
        source="regenerate",
    )
    assert a.id == b.id
    await q.wait_until_done([a.id])
    assert order == ["ta_1"]


@pytest.mark.asyncio
async def test_serial_execution_order():
    q = GenerationQueue()
    running_peak = 0
    current = 0
    order: list[str] = []

    async def runner(job: GenerationJob) -> None:
        nonlocal running_peak, current
        current += 1
        running_peak = max(running_peak, current)
        order.append(job.asset_id)
        await asyncio.sleep(0.02)
        current -= 1

    q.set_runner(runner)
    ids = []
    for aid in ("a", "b", "c"):
        job = await q.enqueue(
            project_id="p1",
            script_id="s1",
            kind="video",
            asset_id=aid,
            label=aid,
            source="agent",
        )
        ids.append(job.id)
    await q.wait_until_done(ids)
    assert order == ["a", "b", "c"]
    assert running_peak == 1


@pytest.mark.asyncio
async def test_failure_continues_next():
    q = GenerationQueue()

    async def runner(job: GenerationJob) -> None:
        if job.asset_id == "bad":
            raise RuntimeError("boom")

    q.set_runner(runner)
    j1 = await q.enqueue(
        project_id="p1", script_id="s1", kind="image",
        asset_id="bad", label="bad", source="batch",
    )
    j2 = await q.enqueue(
        project_id="p1", script_id="s1", kind="image",
        asset_id="ok", label="ok", source="batch",
    )
    done = await q.wait_until_done([j1.id, j2.id])
    by_id = {j.id: j for j in done}
    assert by_id[j1.id].status == "failed"
    assert "boom" in (by_id[j1.id].error or "")
    assert by_id[j2.id].status == "done"


@pytest.mark.asyncio
async def test_snapshot_shape_for_script():
    q = GenerationQueue()
    gate = asyncio.Event()

    async def runner(job: GenerationJob) -> None:
        await gate.wait()

    q.set_runner(runner)
    j = await q.enqueue(
        project_id="p1", script_id="s1", kind="image",
        asset_id="x", label="X", source="regenerate",
    )
    await asyncio.sleep(0.02)  # 让工人进入 running
    snap = q.snapshot_for_script("s1")
    assert snap["type"] == "generation_queue_snapshot"
    assert snap["script_id"] == "s1"
    assert snap["counts"]["running"] == 1 or snap["active"] is not None
    assert any(item["id"] == j.id for item in ([snap["active"]] if snap["active"] else []) + snap["queued"] + snap["recent"])
    gate.set()
    await q.wait_until_done([j.id])
```

- [ ] **Step 2: 跑测确认失败**

Run: `pytest tests/unit/test_generation_queue.py -v`  
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现 models**

```python
# core/generation/models.py
"""生成队列领域模型。"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Literal
import time
import uuid

GenerationKind = Literal["image", "video"]
GenerationStatus = Literal["queued", "running", "done", "failed"]
GenerationSource = Literal["regenerate", "batch", "agent"]


@dataclass
class GenerationJob:
    """单条图片或视频生成任务。"""

    id: str
    script_id: str
    project_id: str
    kind: GenerationKind
    asset_id: str
    label: str
    status: GenerationStatus
    source: GenerationSource
    error: str | None = None
    variant_id: str | None = None
    created_at: float = field(default_factory=lambda: time.time())
    started_at: float | None = None
    finished_at: float | None = None
    # Agent 单项执行载荷；regenerate 路径可为 None
    payload: dict[str, Any] | None = None

    def dedupe_key(self) -> str:
        """同剧本同资产同变体去重键。"""
        return f"{self.script_id}|{self.kind}|{self.asset_id}|{self.variant_id or ''}"

    def to_public_dict(self) -> dict[str, Any]:
        """WS/HTTP 公开字段（不含 payload）。"""
        d = asdict(self)
        d.pop("payload", None)
        return d


def new_job_id() -> str:
    """生成 gen_ 前缀任务 ID。"""
    return f"gen_{uuid.uuid4().hex[:16]}"
```

- [ ] **Step 4: 实现 GenerationQueue**

要点（写入 `core/generation/queue.py`）：

- `_pending: deque[str]`（job id）、`_jobs: dict[str, GenerationJob]`、`_recent: deque`（最多 50）
- `_active_id: str | None`、`_runner`、`_worker_task`、`_lock: asyncio.Lock`
- `enqueue`：去重查 `queued|running`；新建 job；`_ensure_worker()`；若有 `_on_change` 回调则 `await`（用于 emit）
- 工人：循环取 pending → status=running → `await runner(job)` → done/failed → 移入 recent → `_notify_waiters` → 回调 snapshot
- `wait_until_done`：用 `asyncio.Event` 每 job 一个，或 Condition 在状态变 done/failed 时 notify
- `snapshot_for_script`：过滤该 script 的 active/queued/recent，拼 `type/counts`
- 模块级单例 + `reset_generation_queue_for_tests()`

```python
# core/generation/__init__.py
"""图片/视频统一生成队列。"""
from core.generation.queue import get_generation_queue, reset_generation_queue_for_tests
from core.generation.models import GenerationJob

__all__ = [
    "GenerationJob",
    "get_generation_queue",
    "reset_generation_queue_for_tests",
]
```

- [ ] **Step 5: 跑测通过**

Run: `pytest tests/unit/test_generation_queue.py -v`  
Expected: PASS

- [ ] **Step 6: Commit**（仅当用户要求提交时执行）

```bash
git add core/generation tests/unit/test_generation_queue.py
git commit -m "$(cat <<'EOF'
feat(generation): add in-process serial generation queue

EOF
)"
```

---

### Task 2: Runner — 执行单条 image / video

**Files:**
- Create: `core/generation/runner.py`
- Modify: `apps/api/state.py`（绑定 runner + emit 回调）
- Test: 扩展 `tests/unit/test_generation_queue.py` 或新建 `tests/unit/test_generation_runner.py`（用 monkeypatch 替换底层，仅在 tests/）

**Interfaces:**
- Consumes: `GenerationJob`、`MemoryStore`、`EventEmitter`
- Produces: `async def run_generation_job(store, emitter, job: GenerationJob) -> None`

执行规则：

| job.source / payload | 行为 |
|----------------------|------|
| `payload` 含 image item（有 `source_text_asset_id` 等） | 构建 `AgentRunContext`，调用 `core.llm.tools.image.generate._generate_one_item`（或抽出的公开 `generate_one_image_item`） |
| `payload` 含 video clip spec | 调用 `_generate_one_clip` |
| `payload is None` 且 kind image/video | `await regenerate_asset(..., asset_id=job.asset_id, variant_id=job.variant_id)` |
| runner 抛错 | 队列捕获 → `failed` + `error=str(exc)[:500]` |

- [ ] **Step 1: 写 runner 单测（monkeypatch regenerate_asset）**

```python
# tests/unit/test_generation_runner.py
import pytest
from unittest.mock import AsyncMock
from core.generation.models import GenerationJob, new_job_id
from core.generation.runner import run_generation_job


@pytest.mark.asyncio
async def test_runner_calls_regenerate_when_no_payload(monkeypatch):
    called = {}

    async def fake_regenerate(store, emitter, **kwargs):
        called.update(kwargs)
        class R:
            ok = True
            job_id = "r1"
            asset_id = kwargs["asset_id"]
            asset_ids = [kwargs["asset_id"]]
            kind = "image"
            message = "ok"
        return R()

    monkeypatch.setattr(
        "core.generation.runner.regenerate_asset",
        fake_regenerate,
    )
    job = GenerationJob(
        id=new_job_id(),
        script_id="s1",
        project_id="p1",
        kind="image",
        asset_id="ta_1",
        label="A",
        status="running",
        source="regenerate",
        variant_id="v1",
    )
    await run_generation_job(store=None, emitter=None, job=job)
    assert called["asset_id"] == "ta_1"
    assert called["variant_id"] == "v1"
```

- [ ] **Step 2: 实现 `run_generation_job`**

若 `_generate_one_item` / `_generate_one_clip` 为私有且签名难用：在各自模块增加薄公开包装（中文 docstring），例如：

```python
# core/llm/tools/image/generate.py 末尾附近
async def generate_one_image_item(
    store: MemoryStore,
    ctx: AgentRunContext,
    item: dict[str, Any],
    *,
    index: int = 0,
    total: int = 1,
    step_id: str = "generation_queue",
) -> None:
    """供生成队列串行调用的单条生图入口。"""
    # 复用 _generate_one_item；semaphore 用 Semaphore(1)
```

视频同理 `generate_one_video_clip(...)`。

`build_regenerate_context` 可从 `core.assets.regenerate` 复用。

- [ ] **Step 3: 在 `apps/api/state.py` 绑定**

在现有 `state.emitter` 初始化之后：

```python
from core.generation.queue import get_generation_queue
from core.generation.runner import run_generation_job

def _bind_generation_queue() -> None:
    """将全局生成队列接到 store/emitter。"""
    q = get_generation_queue()

    async def _runner(job):
        await run_generation_job(state.store, state.emitter, job)

    async def _on_change(script_id: str) -> None:
        snap = q.snapshot_for_script(script_id)
        # 全局工人可能切换剧本：对 active/queued 涉及的每个 script_id 各推一次
        await state.emitter.emit(snap)

    q.set_runner(_runner)
    q.set_on_change(_on_change)  # 若设计为多 script，on_change 接收 job 并 emit 对应 script 快照
```

注意：入队/完成时，应对 **该 job 的 script_id** emit；若全局工人从 script A 切到 B，分别推 A、B 快照。推荐 `on_change(job: GenerationJob)` → `emit(snapshot_for_script(job.script_id))`。

- [ ] **Step 4: 跑测**

Run: `pytest tests/unit/test_generation_runner.py tests/unit/test_generation_queue.py -v`  
Expected: PASS

---

### Task 3: HTTP GET / POST enqueue

**Files:**
- Create: `apps/api/routes/generation_queue.py`
- Modify: `apps/api/main.py`（`include_router`）
- Test: `tests/api/test_generation_queue_api.py`

**Interfaces:**
- `GET /api/projects/{project_id}/scripts/{script_id}/generation-queue` → snapshot dict
- `POST /api/projects/{project_id}/scripts/{script_id}/generation-queue/enqueue`  
  body: `{ "kind": "image"|"video", "asset_id": str, "variant_id"?: str, "label"?: str, "source"?: "regenerate"|"batch"|"agent" }`  
  → `{ "job": {...}, "snapshot": {...} }` status 202

- [ ] **Step 1: 写 API 测试**（沿用现有 api fixture：创建 project/script）

```python
# tests/api/test_generation_queue_api.py
def test_get_empty_queue(client, project_and_script):
    pid, sid = project_and_script
    r = client.get(f"/api/projects/{pid}/scripts/{sid}/generation-queue")
    assert r.status_code == 200
    body = r.json()
    assert body["type"] == "generation_queue_snapshot"
    assert body["queued"] == []
    assert body["counts"]["queued"] == 0


def test_enqueue_returns_job(client, project_and_script, monkeypatch):
    pid, sid = project_and_script

    async def noop_runner(job):
        return None

    from core.generation.queue import get_generation_queue
    get_generation_queue().set_runner(noop_runner)

    r = client.post(
        f"/api/projects/{pid}/scripts/{sid}/generation-queue/enqueue",
        json={"kind": "image", "asset_id": "ta_x", "label": "X", "source": "batch"},
    )
    assert r.status_code == 202
    assert r.json()["job"]["asset_id"] == "ta_x"
```

（按仓库现有 `tests/api` fixture 名称调整；若无 `project_and_script`，复制 `test_api_asset_regenerate.py` 的创建方式。）

- [ ] **Step 2: 实现路由并注册**

```python
# apps/api/routes/generation_queue.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from apps.api.state import state
from core.generation.queue import get_generation_queue

router = APIRouter(prefix="/api")


class EnqueueBody(BaseModel):
    """生成队列入队请求。"""
    kind: str = Field(..., pattern="^(image|video)$")
    asset_id: str
    variant_id: str | None = None
    label: str | None = None
    source: str = "regenerate"


@router.get("/projects/{project_id}/scripts/{script_id}/generation-queue")
async def get_generation_queue_snapshot(project_id: str, script_id: str):
    """返回剧本维度的生成队列快照。"""
    # 校验 project/script 存在…
    return get_generation_queue().snapshot_for_script(script_id)


@router.post(
    "/projects/{project_id}/scripts/{script_id}/generation-queue/enqueue",
    status_code=202,
)
async def enqueue_generation_job(project_id: str, script_id: str, body: EnqueueBody):
    """将图片或视频生成任务加入全局串行队列。"""
    # 校验…；label 缺省用 asset_id
    job = await get_generation_queue().enqueue(
        project_id=project_id,
        script_id=script_id,
        kind=body.kind,  # type: ignore[arg-type]
        asset_id=body.asset_id,
        label=body.label or body.asset_id,
        source=body.source,  # type: ignore[arg-type]
        variant_id=body.variant_id,
    )
    return {
        "job": job.to_public_dict(),
        "snapshot": get_generation_queue().snapshot_for_script(script_id),
    }
```

`main.py`：

```python
from apps.api.routes.generation_queue import router as generation_queue_router
# ...
app.include_router(generation_queue_router)
```

- [ ] **Step 3: 跑测**

Run: `pytest tests/api/test_generation_queue_api.py -v`  
Expected: PASS

---

### Task 4: regenerate 入口改入队（image/video）

**Files:**
- Modify: `apps/api/routes/projects.py` — `regenerate_asset_route`
- Modify: `core/assets/regenerate.py` — 可选增加 `infer_generation_queue_kind(store, asset_id) -> "image"|"video"|None`
- Test: 更新 `tests/api/test_api_asset_regenerate.py` / `tests/unit/test_asset_regenerate.py`（TTS 仍同步；image 期望立即返回 job 且队列有条目）

**行为：**

```python
# regenerate_asset_route 伪代码
kind = infer_generation_queue_kind(state.store, asset_id)
if kind is None:
    # TTS / 不支持类型：保持原 await regenerate_asset
    ...
else:
    label = _asset_label(state.store, asset_id)
    job = await get_generation_queue().enqueue(
        project_id=project_id,
        script_id=script_id,
        kind=kind,
        asset_id=asset_id,
        label=label,
        source="regenerate",
        variant_id=variant_id,
    )
    return JSONResponse(
        status_code=202,
        content={
            "accepted": True,
            "job_id": job.id,
            "asset_id": asset_id,
            "kind": kind,
            "ok": True,
            "message": "已加入生成队列",
            "snapshot": get_generation_queue().snapshot_for_script(script_id),
        },
    )
```

`infer_generation_queue_kind`：

- text `video_clip` → `"video"`
- text image kinds（character/scene/prop/frame…）→ `"image"`
- media IMAGE → `"image"`；media VIDEO → `"video"`
- media AUDIO / 其他 → `None`（直跑）

分镜 `regenerate_shot_route`：`frame`/`video` kinds 改为按 shot 相关资产入队（或对 shot 内目标 asset 逐条 enqueue）；`tts` 仍直跑。若现有实现是 `regenerate_shot_assets` 内部串行，可改为：对 frame/video 入队后立即 202，TTS 仍 await。MVP 最小改动：shot 的 frame/video 也走 enqueue（解析出目标 text asset id）。

- [ ] **Step 1: 实现 `infer_generation_queue_kind` + 改 route**
- [ ] **Step 2: 更新 regenerate API 测试**（image 路径不再 mock 完整生图完成；断言 202 + `accepted` + queue 非空）
- [ ] **Step 3: 跑相关测试**

Run: `pytest tests/api/test_api_asset_regenerate.py tests/unit/test_asset_regenerate.py -v`

---

### Task 5: Agent 批处理改「拆条入队 + 等待」

**Files:**
- Create: `core/generation/bridge.py`
- Modify: `core/llm/tools/image/generate.py` — `run_concurrent_image_generation`
- Modify: `core/llm/tools/video/video_clips.py` — `run_concurrent_video_clip_generation`
- Modify: `core/llm/tools/video/generate.py` — `run_concurrent_video_generation`（镜头视频同样串行入队，避免绕过）
- Test: `tests/unit/test_generation_bridge.py`；必要时改 `tests/unit/test_image_generate.py` 期望（并发 → 串行队列）

**Interfaces:**
- Produces: `async def enqueue_and_wait_image_items(...)` / `enqueue_and_wait_video_clip_specs(...)`

```python
# core/generation/bridge.py
async def enqueue_and_wait_image_items(
    *,
    project_id: str,
    script_id: str,
    items: list[dict],
    source: str = "agent",
) -> list[GenerationJob]:
    """将生图 items 逐条入队并等待全部结束。"""
    q = get_generation_queue()
    ids = []
    for item in items:
        asset_id = str(item.get("source_text_asset_id") or item.get("asset_id") or "")
        label = str(item.get("name") or asset_id)
        variant_id = item.get("variant_id")
        job = await q.enqueue(
            project_id=project_id,
            script_id=script_id,
            kind="image",
            asset_id=asset_id,
            label=label,
            source=source,  # type: ignore
            variant_id=str(variant_id) if variant_id else None,
            payload=item,
        )
        ids.append(job.id)
    return await q.wait_until_done(ids)
```

在 `run_concurrent_image_generation` 内：收集 `items` 后**不再** `asyncio.gather` + semaphore，改为：

```python
jobs = await enqueue_and_wait_image_items(
    project_id=ctx.project_id,  # 若 ctx 无 project_id，从 script 取
    script_id=script_id,
    items=items,
    source="agent",
)
# 根据 jobs 的 done/failed 组装 generated / failures / observation
# 失败策略：保持现有 ImageGenerationAbortError 语义（若有失败则抛或汇总）
```

视频 clip / shot 同理。observation 示例：`已入队并完成 3 条视频生成（成功 2，失败 1）`。

- [ ] **Step 1: bridge + 改三处 concurrent runner**
- [ ] **Step 2: 单测 bridge（假 queue runner）**
- [ ] **Step 3: 跑** `pytest tests/unit/test_image_generate.py tests/unit/test_generation_bridge.py -v`（及现有 video 相关 unit）

---

### Task 6: 前端 Context + WS

**Files:**
- Create: `apps/web/src/context/GenerationQueueContext.tsx`
- Create: `apps/web/src/utils/generationQueueStatus.ts`（reduce snapshot）
- Modify: `apps/web/src/hooks/useWorkbenchWs.ts`
- Modify: `apps/web/src/pages/Workbench.tsx`（Provider）
- Modify: `apps/web/src/types.ts`（可选 `GenerationQueueSnapshotEvent`）

**Interfaces:**
- `useGenerationQueue()` → `{ snapshot, open, setOpen, refresh, counts }`
- `applySnapshot(event)` / `applyWsEvent`

```typescript
/** 生成队列快照（与后端 generation_queue_snapshot 对齐）。 */
export interface GenerationQueueSnapshot {
  type: "generation_queue_snapshot";
  script_id: string;
  project_id?: string;
  active: GenerationQueueJob | null;
  queued: GenerationQueueJob[];
  recent: GenerationQueueJob[];
  counts: { queued: number; running: number };
}

export interface GenerationQueueJob {
  id: string;
  kind: "image" | "video";
  asset_id: string;
  label: string;
  status: "queued" | "running" | "done" | "failed";
  error?: string | null;
  variant_id?: string | null;
  source?: string;
}
```

`useWorkbenchWs`：

```typescript
if (e?.type === "generation_queue_snapshot") {
  opt.generationQueue?.applyWsEvent(e);
}
```

打开工作台 / 切换剧本时 `GET .../generation-queue` 拉一次。

- [ ] **Step 1: 实现 Context + reduce**
- [ ] **Step 2: 挂载 Provider 与 WS**
- [ ] **Step 3: 前端 typecheck** — `cd apps/web && npx tsc --noEmit`（或项目既有 check 脚本）

---

### Task 7: `GenerationQueueDrawer` + 角标

**Files:**
- Create: `apps/web/src/components/GenerationQueueDrawer.tsx`
- Modify: `apps/web/src/pages/Workbench.tsx` 或 `BoardPanel.tsx`（角标按钮 + 抽屉）
- Modify: `apps/web/src/i18n/locales/zh-CN/board.json`、`en/board.json`
- Modify: `apps/web/src/index.css` 或既有 drawer CSS（复用 `shot-detail-drawer`）

**UI：**

- 按钮文案：`生成队列` / `Queue`；角标 = `counts.queued + counts.running`
- 抽屉：`useResizableDrawerWidth({ storageKey: "svf-generation-queue-drawer-width", defaultWidth: 400 })`
- 分区标题：进行中 / 排队中 / 最近完成
- 行：kind 徽章（图/视频）、label、`asset_id` 后 6 位、status、error
- 空态：`暂无生成任务`
- 脚注：`视频创建约 1 次/分钟，队列串行执行`

对齐 `BatchAssetStudioDrawer` 结构：backdrop + aside + `ResizableDrawerEdge`。

- [ ] **Step 1: 实现抽屉组件 + i18n**
- [ ] **Step 2: 挂到 Workbench 顶栏或看板工具条**
- [ ] **Step 3: 手动验收清单写在 PR/提交说明**（连续入队可见排队、仅 1 条 running）

---

### Task 8: 批量印样与二次生成按钮适配

**Files:**
- Modify: `apps/web/src/utils/batchAssetStudio.ts`
- Modify: `apps/web/src/components/AssetRegenerateButton.tsx`
- Modify: `apps/web/src/components/board/BatchAssetStudioDrawer.tsx`（concurrency 默认改 1 或去掉本地并行语义）

**行为变更：**

1. `regenerateStudioAsset`：仍 POST regenerate；响应变为快速 202（`accepted`）。**不要**把 HTTP 返回当作生成完成。
2. `runBatchRegenerate`：
   - 对每行 POST enqueue/regenerate，`onRowStatus(id, "queued")`
   - 用 `waitForQueueIdle(assetIds)`：轮询 `GET generation-queue` 或订阅 Context，直到这些 `asset_id` 均不在 active/queued（进入 recent done/failed）
   - 根据 recent 状态设 `done` / `error`
   - 默认 `concurrency` 改为 `1` 仅用于「发起 HTTP」也可 `Math.min(queue.length, 4)` 并行 POST（服务端串行执行）

```typescript
/** 等待指定资产离开队列的 active/queued。 */
export async function waitForGenerationJobs(
  projectId: string,
  scriptId: string,
  assetIds: Set<string>,
  opts?: { pollMs?: number; shouldCancel?: () => boolean },
): Promise<Map<string, "done" | "failed" | string>> {
  // GET /generation-queue 直到 assetIds 全在 recent 或消失且不在 queued
}
```

3. `AssetRegenerateButton`：POST 后保持 `markGenerating`，直到 `assets_changed` 或 queue snapshot 中该 asset `done|failed`（可用 Context 监听）。

- [ ] **Step 1: 实现 wait helper + 改 batch**
- [ ] **Step 2: 改 RegenerateButton 完成判定**
- [ ] **Step 3: 相关前端逻辑自测 / 既有 vitest（若有）**

---

### Task 9: 文档同步 + 全量测试

**Files:**
- Modify: `docs/superpowers/reference/code-design-plan.md` — §2 仓库结构增加 `core/generation/`；§API 增加 generation-queue 端点；注明 regenerate image/video 入队
- Modify: `docs/superpowers/reference/product-plan.md` — 工作台「生成队列」侧栏一句
- Modify: `docs/superpowers/reference/frontend-style-guide.md` 或 `.cursor/rules/frontend-style.mdc` 提及抽屉 — 若已有 Batch 抽屉描述则并列
- Modify: `docs/superpowers/specs/2026-07-16-generation-queue-design.md` — 状态改为「已实现」或「实现中」
- Modify: `README.md` — 仅当用户可见能力列表需要时加一行

- [ ] **Step 1: 更新文档日期与章节**
- [ ] **Step 2: 全量测试**

Run: `pytest tests/ -v -m "not live and not integration"`  
Expected: 100% 相关失败已修复；全绿

- [ ] **Step 3: 确认无生产 mock**

Run: `rg -n "mock|MagicMock|stub" core/generation apps/api/routes/generation_queue.py`  
Expected: 无测试替身

---

## Spec Coverage Checklist

| Spec 要求 | Task |
|-----------|------|
| 统一串行队列 | 1–2 |
| 上一条完成再下一条 | 1 |
| 侧栏可见 | 6–7 |
| regenerate / batch / agent 入口 | 4–5, 8 |
| WS snapshot | 2, 6 |
| HTTP GET/POST | 3 |
| 去重 | 1 |
| 内存不持久化 | 1（文档 9） |
| TTS 不入队 | 4 |
| Agnes 间隔仍生效 | 2（组合，无改动客户端） |
| 文档同步 | 9 |
| 验收：同时仅 1 running | 1 + 手动 7 |

## Out of Scope（勿实现）

- 拖拽排序、整队暂停、取消 running
- 队列落盘 / 多 worker
- TTS 入队、`video_gen_progress` 细粒度事件（可用 snapshot 代替）
