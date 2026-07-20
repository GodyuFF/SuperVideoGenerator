"""资产二次生成 API 集成测试。"""

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from apps.api.main import app
from apps.api.state import state
from core.generation.queue import get_generation_queue, reset_generation_queue_for_tests
from apps.api.state import state
from core.llm.agent.script_assets import create_text_asset_for_action
from core.models.entities import Project, Script, ScriptStatus, VideoPlan, VideoStyleMode
from tests.support.frame_fixtures import ensure_shot_frame_image
from tests.support.image_text_fixtures import prop_content
from tests.support.shot_fixtures import make_shot


@pytest.fixture(autouse=True)
def _reset_queue():
    """每个用例前重置全局队列单例，避免跨测污染。"""
    reset_generation_queue_for_tests()
    yield
    reset_generation_queue_for_tests()


@pytest.mark.asyncio
async def test_regenerate_asset_route_not_found():
    """未知资产应返回 404。"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post("/api/projects", json={"title": "再生测试"})
        pid = r.json()["id"]
        r = await client.post(
            f"/api/projects/{pid}/scripts",
            json={"title": "集1", "duration_sec": 60},
        )
        sid = r.json()["id"]
        r = await client.post(
            f"/api/projects/{pid}/scripts/{sid}/assets/txt_nonexist/regenerate",
        )
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_regenerate_asset_route_executing():
    """executing 态应返回 403。"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post("/api/projects", json={"title": "再生测试2"})
        pid = r.json()["id"]
        r = await client.post(
            f"/api/projects/{pid}/scripts",
            json={"title": "集1", "duration_sec": 60},
        )
        sid = r.json()["id"]
        script = state.store.get_script(sid)
        assert script is not None
        script.status = ScriptStatus.EXECUTING
        asset = create_text_asset_for_action(
            state.store,
            action="create_prop",
            project_id=pid,
            script_id=sid,
            asset_name="道具",
            content=prop_content(summary="道具", description="测试道具。"),
            observation="",
        ).asset
        r = await client.post(
            f"/api/projects/{pid}/scripts/{sid}/assets/{asset.id}/regenerate",
        )
        assert r.status_code == 403


@pytest.mark.asyncio
async def test_regenerate_asset_route_image_enqueues_without_waiting():
    """图文资产二次生成应立即 202 入队，不等待完整生图。"""
    transport = ASGITransport(app=app)
    generation_finished = asyncio.Event()

    async def slow_runner(job):
        await asyncio.sleep(2)
        generation_finished.set()

    get_generation_queue().set_runner(slow_runner)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post("/api/projects", json={"title": "再生测试3"})
        pid = r.json()["id"]
        r = await client.post(
            f"/api/projects/{pid}/scripts",
            json={"title": "集1", "duration_sec": 60},
        )
        sid = r.json()["id"]
        asset = create_text_asset_for_action(
            state.store,
            action="create_prop",
            project_id=pid,
            script_id=sid,
            asset_name="道具",
            content=prop_content(
                summary="道具",
                description="测试道具描述，用于二次生图入队验证。",
            ),
            observation="",
        ).asset
        r = await client.post(
            f"/api/projects/{pid}/scripts/{sid}/assets/{asset.id}/regenerate",
        )
        assert r.status_code == 202
        body = r.json()
        assert body["accepted"] is True
        assert body["ok"] is True
        assert body["kind"] == "image"
        assert body["asset_id"] == asset.id
        assert body["message"] == "已加入生成队列"
        assert body["job_id"].startswith("gen_")
        snapshot = body["snapshot"]
        assert snapshot["type"] == "generation_queue_snapshot"
        assert snapshot["counts"]["queued"] + (
            1 if snapshot["active"] else 0
        ) >= 1
        assert not generation_finished.is_set()


@pytest.mark.asyncio
async def test_regenerate_shot_route_frame_enqueues_without_waiting():
    """分镜 frame 二次生成应立即 202 入队，不等待完整生图。"""
    state.store.clear()
    generation_finished = asyncio.Event()

    async def slow_runner(job):
        await asyncio.sleep(2)
        generation_finished.set()

    get_generation_queue().set_runner(slow_runner)

    project = Project(title="shot-regen")
    state.store.add_project(project)
    script = Script(project_id=project.id, title="s1", status=ScriptStatus.PLANNED)
    state.store.add_script(script)
    shot = make_shot()
    plan = VideoPlan(script_id=script.id, mode=VideoStyleMode.STORYBOOK, shots=[shot])
    state.store.set_video_plan(plan)
    frame, _ = ensure_shot_frame_image(
        state.store,
        project_id=project.id,
        script_id=script.id,
        shot=shot,
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            f"/api/projects/{project.id}/scripts/{script.id}/shots/{shot.id}/regenerate",
            json={"kinds": ["frame"]},
        )
        assert r.status_code == 202
        body = r.json()
        assert body["accepted"] is True
        assert body["ok"] is True
        assert body["kind"] == "image"
        assert body["asset_id"] == frame.id
        assert body["message"] == "已加入生成队列"
        assert body["job_id"].startswith("gen_")
        snapshot = body["snapshot"]
        assert snapshot["type"] == "generation_queue_snapshot"
        assert snapshot["counts"]["queued"] + (1 if snapshot["active"] else 0) >= 1
        assert not generation_finished.is_set()
