"""Agent 批处理拆条入队 bridge 单元测试。"""

from __future__ import annotations

import pytest

from core.generation.bridge import (
    enqueue_and_wait_image_items,
    enqueue_and_wait_shot_video_specs,
    enqueue_and_wait_video_clip_specs,
)
from core.generation.models import GenerationJob
from core.generation.queue import get_generation_queue, reset_generation_queue_for_tests
from core.llm.tools.video.shot_spec import ShotVideoGenSpec


@pytest.fixture(autouse=True)
def _reset_queue():
    """每个用例前后重置全局队列单例。"""
    reset_generation_queue_for_tests()
    yield
    reset_generation_queue_for_tests()


@pytest.mark.asyncio
async def test_enqueue_and_wait_image_items_serial_order():
    """生图 items 应逐条入队并由假 runner 串行执行。"""
    q = get_generation_queue()
    order: list[str] = []

    async def runner(job: GenerationJob) -> None:
        order.append(job.asset_id)

    q.set_runner(runner)
    items = [
        {"source_text_asset_id": "ta_a", "name": "A", "image_prompt": "a"},
        {"source_text_asset_id": "ta_b", "name": "B", "image_prompt": "b"},
    ]
    jobs = await enqueue_and_wait_image_items(
        project_id="p1",
        script_id="s1",
        items=items,
        source="agent",
    )
    assert len(jobs) == 2
    assert all(j.status == "done" for j in jobs)
    assert order == ["ta_a", "ta_b"]
    assert jobs[0].payload == items[0]
    assert jobs[1].kind == "image"
    assert jobs[1].source == "agent"


@pytest.mark.asyncio
async def test_enqueue_and_wait_image_items_collects_failures():
    """失败任务应标记 failed 且 error 可被上层读取。"""
    q = get_generation_queue()

    async def runner(job: GenerationJob) -> None:
        if job.asset_id == "ta_bad":
            raise RuntimeError("image boom")

    q.set_runner(runner)
    items = [
        {"source_text_asset_id": "ta_ok", "name": "OK"},
        {"source_text_asset_id": "ta_bad", "name": "BAD"},
    ]
    jobs = await enqueue_and_wait_image_items(
        project_id="p1",
        script_id="s1",
        items=items,
    )
    assert jobs[0].status == "done"
    assert jobs[1].status == "failed"
    assert "image boom" in (jobs[1].error or "")


@pytest.mark.asyncio
async def test_enqueue_and_wait_video_clip_specs():
    """video_clip 规格应逐条入队并携带 payload。"""
    q = get_generation_queue()
    seen: list[str] = []

    async def runner(job: GenerationJob) -> None:
        seen.append(job.asset_id)

    q.set_runner(runner)
    specs = [
        ShotVideoGenSpec(
            shot_id="shot_1",
            order=0,
            mode="text2video",
            prompt="rain",
            image_url=None,
            keyframe_urls=[],
            duration_sec=5.0,
            sub_shot_idx=0,
            video_clip_asset_id="ta_vc_1",
        ),
        ShotVideoGenSpec(
            shot_id="shot_2",
            order=1,
            mode="img2video",
            prompt="sun",
            image_url="https://x.test/f.png",
            keyframe_urls=[],
            duration_sec=6.0,
            sub_shot_idx=0,
            video_clip_asset_id="ta_vc_2",
        ),
    ]
    jobs = await enqueue_and_wait_video_clip_specs(
        project_id="p1",
        script_id="s1",
        specs=specs,
    )
    assert len(jobs) == 2
    assert seen == ["ta_vc_1", "ta_vc_2"]
    assert jobs[0].kind == "video"
    assert jobs[0].payload is not None
    assert jobs[0].payload.get("video_clip_asset_id") == "ta_vc_1"


@pytest.mark.asyncio
async def test_enqueue_and_wait_shot_video_specs_marks_payload():
    """镜头视频入队应带 shot_video 标记供 runner 区分 clip 路径。"""
    q = get_generation_queue()
    payloads: list[dict] = []

    async def runner(job: GenerationJob) -> None:
        if job.payload:
            payloads.append(dict(job.payload))

    q.set_runner(runner)
    spec = ShotVideoGenSpec(
        shot_id="shot_99",
        order=2,
        mode="img2video",
        prompt="motion",
        image_url="https://x.test/f.png",
        keyframe_urls=[],
        duration_sec=4.0,
        sub_shot_idx=0,
    )
    jobs = await enqueue_and_wait_shot_video_specs(
        project_id="p1",
        script_id="s1",
        specs=[spec],
    )
    assert len(jobs) == 1
    assert jobs[0].asset_id == "shot_99"
    assert payloads[0].get("shot_video") is True
    assert payloads[0].get("shot_id") == "shot_99"
