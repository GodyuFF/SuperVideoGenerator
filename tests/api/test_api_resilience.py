"""API 韧性测试：事件循环阻塞、executing 恢复、后台 chat。"""

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from apps.api.main import app
from apps.api.state import state
from core.models.entities import GenerationMode, ScriptStatus, VideoStyleMode
from tests.support.chat_wait import wait_for_chat_idle


@pytest.mark.asyncio
async def test_recover_stuck_executing_on_startup():
    """无活跃取消注册时，应把卡死的 executing 恢复为 failed。"""
    from core.execution.cancel import get_execution_cancel_registry

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post("/api/projects", json={"title": "恢复测试"})
        pid = r.json()["id"]
        r = await client.post(
            f"/api/projects/{pid}/scripts",
            json={"title": "S1"},
        )
        sid = r.json()["id"]

    script = state.store.get_script(sid)
    assert script is not None
    get_execution_cancel_registry().clear(sid)
    script.status = ScriptStatus.EXECUTING

    state._recover_stuck_executing_scripts()

    assert script.status == ScriptStatus.FAILED


@pytest.mark.asyncio
async def test_health_responsive_during_asset_patch():
    """async 路由落盘在线程池执行时，/health 应能快速响应。"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post("/api/projects", json={"title": "并发健康"})
        pid = r.json()["id"]
        r = await client.post(
            f"/api/projects/{pid}/scripts",
            json={"title": "S1", "duration_sec": 60},
        )
        sid = r.json()["id"]

        patch_task = asyncio.create_task(
            client.patch(
                f"/api/projects/{pid}/scripts/{sid}",
                json={"content_md": "# 测\n\n并发落盘", "title": "并发"},
            )
        )
        health_task = asyncio.create_task(client.get("/health"))

        health_r, patch_r = await asyncio.gather(health_task, patch_task)
        assert health_r.status_code == 200
        assert health_r.json()["status"] == "ok"
        assert patch_r.status_code == 200


@pytest.mark.asyncio
async def test_post_chat_returns_202_and_active_endpoint():
    """POST chat 应立即 202，active 端点反映执行态。"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post("/api/projects", json={"title": "202 测试"})
        pid = r.json()["id"]
        r = await client.post(f"/api/projects/{pid}/scripts", json={"title": "S1"})
        sid = r.json()["id"]

        r = await client.get(
            f"/api/projects/{pid}/scripts/{sid}/executions/active"
        )
        assert r.status_code == 200
        assert r.json()["active"] is False

        r = await client.post(
            f"/api/projects/{pid}/scripts/{sid}/chat",
            json={
                "message": "写一段简短剧本",
                "generation_mode": GenerationMode.AUTO.value,
                "style_mode": VideoStyleMode.STORYBOOK.value,
            },
        )
        assert r.status_code == 202
        body = r.json()
        assert body.get("accepted") is True
        assert body.get("conversation_id")

        await wait_for_chat_idle(client, pid, sid)
        r = await client.get(
            f"/api/projects/{pid}/scripts/{sid}/executions/active"
        )
        assert r.json()["active"] is False
