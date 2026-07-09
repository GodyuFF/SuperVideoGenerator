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
