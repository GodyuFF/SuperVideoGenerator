"""生成队列 HTTP API 集成测试。"""

import pytest
from httpx import ASGITransport, AsyncClient

from apps.api.main import app
from core.generation.queue import get_generation_queue, reset_generation_queue_for_tests


@pytest.fixture(autouse=True)
def _reset_queue():
    """每个用例前重置全局队列单例，避免跨测污染。"""
    reset_generation_queue_for_tests()
    yield
    reset_generation_queue_for_tests()


async def _create_project_and_script(client: AsyncClient) -> tuple[str, str]:
    """创建测试用项目与剧本，返回 (project_id, script_id)。"""
    r = await client.post("/api/projects", json={"title": "队列测试项目"})
    assert r.status_code == 200
    pid = r.json()["id"]
    r = await client.post(
        f"/api/projects/{pid}/scripts",
        json={"title": "集1", "duration_sec": 60},
    )
    assert r.status_code == 200
    sid = r.json()["id"]
    return pid, sid


@pytest.mark.asyncio
async def test_get_empty_queue():
    """空队列 GET 应返回 snapshot 且 queued 为空。"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        pid, sid = await _create_project_and_script(client)
        r = await client.get(
            f"/api/projects/{pid}/scripts/{sid}/generation-queue",
        )
        assert r.status_code == 200
        body = r.json()
        assert body["type"] == "generation_queue_snapshot"
        assert body["script_id"] == sid
        assert body["queued"] == []
        assert body["counts"]["queued"] == 0
        assert body["counts"]["running"] == 0


@pytest.mark.asyncio
async def test_enqueue_returns_job():
    """POST enqueue 应返回 202 与 job、snapshot。"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        pid, sid = await _create_project_and_script(client)

        async def noop_runner(job):
            return None

        get_generation_queue().set_runner(noop_runner)

        r = await client.post(
            f"/api/projects/{pid}/scripts/{sid}/generation-queue/enqueue",
            json={
                "kind": "image",
                "asset_id": "ta_x",
                "label": "X",
                "source": "batch",
            },
        )
        assert r.status_code == 202
        body = r.json()
        assert body["job"]["asset_id"] == "ta_x"
        assert body["job"]["kind"] == "image"
        assert body["job"]["source"] == "batch"
        assert body["snapshot"]["type"] == "generation_queue_snapshot"
        assert len(body["snapshot"]["queued"]) + (
            1 if body["snapshot"]["active"] else 0
        ) >= 1


@pytest.mark.asyncio
async def test_get_queue_unknown_project():
    """未知项目应返回 404。"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get(
            "/api/projects/proj_missing/scripts/scr_any/generation-queue",
        )
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_get_queue_unknown_script():
    """未知剧本应返回 404。"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post("/api/projects", json={"title": "仅项目"})
        pid = r.json()["id"]
        r = await client.get(
            f"/api/projects/{pid}/scripts/scr_missing/generation-queue",
        )
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_enqueue_unknown_script():
    """向不存在的剧本入队应返回 404。"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post("/api/projects", json={"title": "入队404"})
        pid = r.json()["id"]
        r = await client.post(
            f"/api/projects/{pid}/scripts/scr_missing/generation-queue/enqueue",
            json={"kind": "video", "asset_id": "vid_1"},
        )
        assert r.status_code == 404
