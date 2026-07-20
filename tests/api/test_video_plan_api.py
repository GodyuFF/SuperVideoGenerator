"""VideoPlan 用户编辑 REST API 测试。"""

import pytest
from httpx import ASGITransport, AsyncClient

from apps.api.main import app
from apps.api.state import state
from core.models.entities import (
    Project,
    Script,
    ScriptStatus,
    VideoPlan,
    Shot,
    VideoStyleMode,
)
from tests.support.shot_fixtures import make_shot, shot_design_payload


def _sample_shot():
    return make_shot(order=0, duration_ms=5000, text="原始旁白")


@pytest.fixture
def vp_api_ctx():
    """含 video plan 的 API 测试上下文。"""
    state.store.clear()
    project = Project(title="vp-api")
    state.store.add_project(project)
    script = Script(project_id=project.id, title="s1", status=ScriptStatus.DRAFT)
    state.store.add_script(script)
    shot = _sample_shot()
    plan = VideoPlan(
        script_id=script.id,
        mode=VideoStyleMode.STORYBOOK,
        shots=[shot],
        detail_revision=1,
    )
    state.store.set_video_plan(plan)
    return project.id, script.id, shot.id


@pytest.mark.asyncio
async def test_get_video_plan_includes_editable(vp_api_ctx):
    """GET video-plan 应包含 editable 字段。"""
    project_id, script_id, _ = vp_api_ctx
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get(f"/api/projects/{project_id}/scripts/{script_id}/video-plan")
    assert res.status_code == 200
    assert res.json().get("editable") is True


@pytest.mark.asyncio
async def test_patch_video_plan_shot(vp_api_ctx):
    """PATCH 单镜应递增 detail_revision。"""
    project_id, script_id, shot_id = vp_api_ctx
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.patch(
            f"/api/projects/{project_id}/scripts/{script_id}/video-plan/shots/{shot_id}",
            json={"camera_motion_refined": "ken_burns_in"},
            headers={"If-Match": "1"},
        )
    assert res.status_code == 200
    data = res.json()
    assert data["detail_revision"] == 2
    assert data["shots"][0]["sub_shots"][0]["camera_motion"] == "ken_burns_in"


@pytest.mark.asyncio
async def test_patch_video_plan_revision_conflict(vp_api_ctx):
    """revision 冲突应返回 409。"""
    project_id, script_id, shot_id = vp_api_ctx
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.patch(
            f"/api/projects/{project_id}/scripts/{script_id}/video-plan/shots/{shot_id}",
            json={"duration_ms": 4000},
            headers={"If-Match": "99"},
        )
    assert res.status_code == 409


@pytest.mark.asyncio
async def test_post_video_plan_ops_reorder(vp_api_ctx):
    """POST ops reorder 应重排镜头。"""
    project_id, script_id, shot_id = vp_api_ctx
    shot2 = make_shot(order=1, duration_ms=2000, text="第二镜")
    plan = state.store.get_video_plan_for_script(script_id)
    state.store.set_video_plan(plan.model_copy(update={"shots": [*plan.shots, shot2]}))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            f"/api/projects/{project_id}/scripts/{script_id}/video-plan/ops",
            json={
                "ops": [{"op": "reorder", "ordered_shot_ids": [shot2.id, shot_id]}],
                "expected_revision": 1,
            },
            headers={"If-Match": "1"},
        )
    assert res.status_code == 200
    ids = [s["id"] for s in res.json()["shots"]]
    assert ids == [shot2.id, shot_id]


@pytest.mark.asyncio
async def test_post_video_plan_ops_add(vp_api_ctx):
    """POST ops add 应新增镜头。"""
    project_id, script_id, _ = vp_api_ctx
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            f"/api/projects/{project_id}/scripts/{script_id}/video-plan/ops",
            json={
                "ops": [
                    {
                        "op": "add",
                        "after_order": 0,
                        "new_shot": shot_design_payload(order=1, duration_ms=3000, text="新镜头"),
                    }
                ],
            },
        )
    assert res.status_code == 200
    assert len(res.json()["shots"]) == 2
