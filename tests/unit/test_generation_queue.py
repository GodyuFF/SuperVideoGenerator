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
