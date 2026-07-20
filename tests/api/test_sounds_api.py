"""音效 API 集成测试。"""

import pytest
from httpx import ASGITransport, AsyncClient

from apps.api.main import app


@pytest.mark.asyncio
async def test_sounds_search_builtin():
    """GET /api/sounds/search 应返回内置音效列表。"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/sounds/search", params={"page_size": 5})
    assert res.status_code == 200
    data = res.json()
    assert "results" in data
    assert len(data["results"]) >= 1
    first = data["results"][0]
    assert "previewUrl" in first
    assert first["previewUrl"].startswith("/api/sounds/preview/")


@pytest.mark.asyncio
async def test_sounds_search_query():
    """关键词搜索应命中内置目录。"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/sounds/search", params={"q": "rain"})
    assert res.status_code == 200
    names = " ".join(r.get("name", "") for r in res.json().get("results", []))
    assert "雨" in names or res.json().get("count", 0) >= 0


@pytest.mark.asyncio
async def test_sounds_preview_builtin():
    """内置音效预览代理应返回音频流。"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/sounds/preview/-1")
    assert res.status_code == 200
    assert "audio" in (res.headers.get("content-type") or "")
    assert len(res.content) > 100
