"""LLM 配置 API 测试。"""

import pytest
from httpx import ASGITransport, AsyncClient

from apps.api.main import app


@pytest.mark.asyncio
async def test_get_llm_config():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/api/llm/config")
        assert r.status_code == 200
        data = r.json()
        assert data["provider"] == "deepseek"
        assert "available_providers" in data
        assert any(p["id"] == "anthropic" for p in data["available_providers"])
        assert not any(p["id"] == "openai" for p in data["available_providers"])


@pytest.mark.asyncio
async def test_patch_llm_provider():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.patch(
            "/api/llm/config",
            json={"provider": "anthropic", "model": "claude-sonnet-4-20250514"},
        )
        assert r.status_code == 200
        assert r.json()["provider"] == "anthropic"
        assert r.json()["model"] == "claude-sonnet-4-20250514"

        r = await client.patch("/api/llm/config", json={"provider": "deepseek"})
        assert r.status_code == 200
