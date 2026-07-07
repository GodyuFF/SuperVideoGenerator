"""统一 AI 配置 API 测试。"""

import pytest
from httpx import ASGITransport, AsyncClient

from apps.api.main import app


@pytest.mark.asyncio
async def test_get_ai_config_sections():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/api/ai/config")
        assert r.status_code == 200
        data = r.json()
        assert "llm" in data
        assert "image" in data
        assert "video" in data
        assert "tts" in data
        assert "export" in data
        assert "fps" in data["export"]
        assert data["llm"]["provider"] == "deepseek"
        assert data["image"]["provider"] == "agnes"
        assert data["image"]["model"] == "agnes-image-2.0-flash"
        assert "pipeline" in data["image"]
        assert data["image"]["pipeline"]["source_mode"] == "generate"


@pytest.mark.asyncio
async def test_patch_ai_image_config():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.patch(
            "/api/ai/config",
            json={
                "image": {
                    "enabled": True,
                    "model": "agnes-image-2.1-flash",
                    "default_size": "1024x1024",
                    "pipeline": {"source_mode": "search"},
                }
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert data["image"]["model"] == "agnes-image-2.1-flash"
        assert data["image"]["default_size"] == "1024x1024"
        assert data["image"]["pipeline"]["source_mode"] == "search"


@pytest.mark.asyncio
async def test_llm_config_legacy_compat():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/api/llm/config")
        assert r.status_code == 200
        data = r.json()
        assert data["provider"] == "deepseek"
        assert "image_text_defaults" in data
        assert "image" not in data

        r = await client.patch(
            "/api/llm/config",
            json={"provider": "anthropic", "model": "claude-sonnet-4-20250514"},
        )
        assert r.status_code == 200
        assert r.json()["provider"] == "anthropic"

        r = await client.patch("/api/llm/config", json={"provider": "deepseek"})
        assert r.status_code == 200
