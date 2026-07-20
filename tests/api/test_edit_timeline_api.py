"""Edit timeline REST API 测试。"""

import pytest
from httpx import ASGITransport, AsyncClient

from apps.api.main import app
from apps.api.state import state
from core.edit.timeline import compile_timeline_from_shots
from core.models.entities import Project, Script, ScriptStatus


@pytest.fixture
def api_ctx():
    state.store.clear()
    project = Project(title="api-p")
    state.store.add_project(project)
    script = Script(project_id=project.id, title="s1", status=ScriptStatus.DRAFT)
    state.store.add_script(script)
    return project.id, script.id


@pytest.mark.asyncio
async def test_get_edit_timeline_empty_before_storyboard():
    """未生成分镜/剪辑时 GET edit-timeline 应返回 200 空时间轴，而非 404。"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post("/api/projects", json={"title": "空时间轴测试"})
        pid = r.json()["id"]
        r = await client.post(f"/api/projects/{pid}/scripts", json={"title": "S1"})
        sid = r.json()["id"]

        r = await client.get(f"/api/projects/{pid}/scripts/{sid}/edit-timeline")
        assert r.status_code == 200
        body = r.json()
        assert body.get("duration_ms") == 0
        assert body.get("revision") == 0
        assert body.get("tracks", {}).get("video") == []
        assert body.get("video_layers") == []
        assert body.get("editable") is True


@pytest.mark.asyncio
async def test_get_video_plan_empty_before_storyboard():
    """未分镜时 GET video-plan 应返回 200 空计划稿，而非 404。"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post("/api/projects", json={"title": "空视频计划测试"})
        pid = r.json()["id"]
        r = await client.post(f"/api/projects/{pid}/scripts", json={"title": "S1"})
        sid = r.json()["id"]

        r = await client.get(f"/api/projects/{pid}/scripts/{sid}/video-plan")
        assert r.status_code == 200
        body = r.json()
        assert body.get("shots") == []
        assert body.get("shot_timings") == []
        assert body.get("script_id") == sid


@pytest.mark.asyncio
async def test_get_edit_capabilities():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/edit/capabilities")
    assert res.status_code == 200
    data = res.json()
    assert "motions" in data
    assert "transitions" in data
    assert data.get("nle_export_enabled") is True
    assert "premiere" in (data.get("nle_export_formats") or [])
    assert data.get("classic_export_enabled") is True
    assert data.get("export_enabled") is False


@pytest.mark.asyncio
async def test_post_export_rejected_when_classic_only(api_ctx):
    """默认禁用 FFmpeg 导出时 POST export 应返回 403。"""
    project_id, script_id = api_ctx
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            f"/api/projects/{project_id}/scripts/{script_id}/export",
        )
    assert res.status_code == 403
    assert "剪辑助手" in res.json().get("detail", "")


@pytest.mark.asyncio
async def test_post_export_nle_returns_job_id(api_ctx, monkeypatch, tmp_path):
    """POST export-nle 应返回 job_id。"""
    from core.store import project_paths

    monkeypatch.setattr(project_paths, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(project_paths, "PROJECTS_ROOT", tmp_path / "projects")

    project_id, script_id = api_ctx
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            f"/api/projects/{project_id}/scripts/{script_id}/export-nle",
        )
    assert res.status_code == 200
    data = res.json()
    assert data.get("ok") is True
    assert data.get("job_id", "").startswith("exp_")


@pytest.mark.asyncio
async def test_patch_edit_timeline(api_ctx):
    project_id, script_id = api_ctx
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.patch(
            f"/api/projects/{project_id}/scripts/{script_id}/edit-timeline",
            json={
                "tracks": {
                    "video": [
                        {
                            "id": "c1",
                            "track": "video",
                            "start_ms": 0,
                            "end_ms": 2000,
                            "label": "test",
                        }
                    ],
                    "audio": [],
                    "subtitle": [],
                }
            },
        )
    assert res.status_code == 200
    data = res.json()
    assert data["revision"] == 1
    assert data["user_edited"] is True


@pytest.mark.asyncio
async def test_get_edit_timeline_after_patch(api_ctx):
    project_id, script_id = api_ctx
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.patch(
            f"/api/projects/{project_id}/scripts/{script_id}/edit-timeline",
            json={"tracks": {"video": [], "audio": [], "subtitle": []}},
        )
        res = await client.get(
            f"/api/projects/{project_id}/scripts/{script_id}/edit-timeline"
        )
    assert res.status_code == 200
    assert res.json()["editable"] is True
