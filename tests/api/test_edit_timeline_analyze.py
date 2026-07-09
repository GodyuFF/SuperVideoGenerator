"""Edit timeline analyze REST API 测试。"""

import pytest
from httpx import ASGITransport, AsyncClient

from apps.api.main import app
from apps.api.state import state
from core.edit.timeline import compile_timeline_from_shots
from core.models.entities import Project, Script, ScriptStatus, VideoPlan, VideoPlanShot, VideoStyleMode


@pytest.fixture
def analyze_api_ctx():
    state.store.clear()
    project = Project(title="analyze-p")
    state.store.add_project(project)
    script = Script(project_id=project.id, title="s1", status=ScriptStatus.DRAFT)
    state.store.add_script(script)
    vp = VideoPlan(
        script_id=script.id,
        mode=VideoStyleMode.DYNAMIC_IMAGE,
        shots=[VideoPlanShot(order=0, narration_text="测试", duration_ms=3000)],
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


@pytest.mark.asyncio
async def test_post_analyze_edit_timeline_missing_timeline():
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
    assert res.status_code == 404
