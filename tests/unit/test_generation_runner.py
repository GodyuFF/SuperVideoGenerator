"""生成队列 runner 单元测试（monkeypatch 仅在 tests/）。"""
import pytest

from core.assets.regenerate import RegenerateError
from core.generation.models import GenerationJob, new_job_id
from core.generation.runner import run_generation_job


@pytest.mark.asyncio
async def test_runner_calls_regenerate_when_no_payload(monkeypatch):
    """无 payload 时应走 regenerate_asset 二次生成路径。"""
    called: dict = {}

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
    assert called["project_id"] == "p1"
    assert called["script_id"] == "s1"


@pytest.mark.asyncio
async def test_runner_calls_generate_one_image_item_with_payload(monkeypatch):
    """payload 含 image item 时应调用单条生图入口。"""
    called: dict = {}

    async def fake_generate(store, ctx, item, **kwargs):
        called["item"] = item
        called["ctx_script_id"] = ctx.script_id

    monkeypatch.setattr(
        "core.generation.runner.generate_one_image_item",
        fake_generate,
    )
    item = {
        "source_text_asset_id": "ta_char",
        "name": "角色A",
        "image_prompt": "a hero",
    }
    job = GenerationJob(
        id=new_job_id(),
        script_id="s1",
        project_id="p1",
        kind="image",
        asset_id="ta_char",
        label="角色A",
        status="running",
        source="agent",
        payload=item,
    )
    await run_generation_job(store=None, emitter=None, job=job)
    assert called["item"] == item
    assert called["ctx_script_id"] == "s1"


@pytest.mark.asyncio
async def test_runner_calls_generate_one_video_clip_with_payload(monkeypatch):
    """payload 含 video clip spec 时应调用单条视频生成入口。"""
    called: dict = {}

    async def fake_generate(store, ctx, spec, **kwargs):
        called["spec"] = spec
        called["ctx_script_id"] = ctx.script_id

    monkeypatch.setattr(
        "core.generation.runner.generate_one_video_clip",
        fake_generate,
    )
    payload = {
        "shot_id": "shot_1",
        "order": 1,
        "mode": "text2video",
        "prompt": "rain",
        "image_url": None,
        "keyframe_urls": [],
        "duration_sec": 5.0,
        "sub_shot_idx": 0,
        "video_clip_asset_id": "ta_vc_1",
    }
    job = GenerationJob(
        id=new_job_id(),
        script_id="s1",
        project_id="p1",
        kind="video",
        asset_id="ta_vc_1",
        label="片段1",
        status="running",
        source="batch",
        payload=payload,
    )
    await run_generation_job(store=None, emitter=None, job=job)
    assert called["spec"].video_clip_asset_id == "ta_vc_1"
    assert called["spec"].prompt == "rain"
    assert called["ctx_script_id"] == "s1"


@pytest.mark.asyncio
async def test_runner_propagates_image_failure(monkeypatch):
    """生图失败时应向上抛出异常供队列标记 failed。"""
    async def fake_generate(*_a, **_kw):
        raise RuntimeError("image boom")

    monkeypatch.setattr(
        "core.generation.runner.generate_one_image_item",
        fake_generate,
    )
    job = GenerationJob(
        id=new_job_id(),
        script_id="s1",
        project_id="p1",
        kind="image",
        asset_id="ta_x",
        label="X",
        status="running",
        source="agent",
        payload={"source_text_asset_id": "ta_x", "name": "X", "image_prompt": "x"},
    )
    with pytest.raises(RuntimeError, match="image boom"):
        await run_generation_job(store=None, emitter=None, job=job)


@pytest.mark.asyncio
async def test_runner_propagates_regenerate_failure(monkeypatch):
    """regenerate 返回 ok=False 时应向上抛出异常供队列标记 failed。"""
    async def fake_regenerate(store, emitter, **kwargs):
        class R:
            ok = False
            job_id = "r1"
            asset_id = kwargs["asset_id"]
            asset_ids = []
            kind = "image"
            message = "生图未产出媒体"

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
    with pytest.raises(RegenerateError, match="生图未产出媒体"):
        await run_generation_job(store=None, emitter=None, job=job)
