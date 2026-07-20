"""Edit timeline analyze REST API 测试。"""

import pytest
from httpx import ASGITransport, AsyncClient

from apps.api.main import app
from apps.api.state import state
from core.edit.timeline import compile_timeline_from_shots
from core.models.entities import Project, Script, ScriptStatus, VideoPlan, VideoStyleMode
from tests.support.frame_fixtures import ensure_shot_frame_image
from tests.support.shot_fixtures import make_shot


@pytest.fixture
def analyze_api_ctx():
    state.store.clear()
    project = Project(title="analyze-p")
    state.store.add_project(project)
    script = Script(project_id=project.id, title="s1", status=ScriptStatus.DRAFT)
    state.store.add_script(script)
    shot = make_shot(order=0, duration_ms=3000, text="测试")
    ensure_shot_frame_image(
        state.store,
        project_id=project.id,
        script_id=script.id,
        shot=shot,
        image_url="https://images.test/frame.png",
    )
    vp = VideoPlan(
        script_id=script.id,
        mode=VideoStyleMode.STORYBOOK,
        shots=[shot],
    )
    state.store.set_video_plan(vp)
    timeline = compile_timeline_from_shots(state.store, script_id=script.id, plan=vp)
    state.store.set_edit_timeline(timeline)
    return project.id, script.id


@pytest.mark.asyncio
async def test_post_analyze_edit_timeline(analyze_api_ctx):
    project_id, script_id = analyze_api_ctx
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            f"/api/projects/{project_id}/scripts/{script_id}/edit-timeline/analyze",
            json={"start_ms": 0, "end_ms": 2000, "include_hints": True},
        )
    assert res.status_code == 200
    data = res.json()
    assert data["range"]["start_ms"] == 0
    assert data["range"]["end_ms"] == 2000
    assert "clips_in_range" in data
    assert "shot_alignment" in data
    video_clips = [c for c in data["clips_in_range"] if c.get("track") == "video"]
    if video_clips:
        assert "visible_range" in video_clips[0]
        assert "edit_description" in video_clips[0]


@pytest.mark.asyncio
async def test_post_analyze_edit_timeline_detail_only(analyze_api_ctx):
    """include_analysis=false 时 API 仍返回 clip 详情但不含 alignment。"""
    project_id, script_id = analyze_api_ctx
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            f"/api/projects/{project_id}/scripts/{script_id}/edit-timeline/analyze",
            json={"start_ms": 0, "end_ms": 2000, "include_analysis": False},
        )
    assert res.status_code == 200
    data = res.json()
    assert data["clips_in_range"]
    assert data["shot_alignment"] == []
    assert data["optimization_hints"] == []


@pytest.mark.asyncio
async def test_post_analyze_edit_timeline_missing_timeline():
    """无剪辑时间轴时 analyze 应返回 200 空分析结果，而非 404。"""
    state.store.clear()
    project = Project(title="no-tl")
    state.store.add_project(project)
    script = Script(project_id=project.id, title="s1", status=ScriptStatus.DRAFT)
    state.store.add_script(script)
    project_id, script_id = project.id, script.id
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            f"/api/projects/{project_id}/scripts/{script_id}/edit-timeline/analyze",
            json={},
        )
    assert res.status_code == 200
    data = res.json()
    assert data["range"]["start_ms"] == 0
    assert data["range"]["end_ms"] == 0
    assert "尚无剪辑时间轴" in data.get("warnings", [])
