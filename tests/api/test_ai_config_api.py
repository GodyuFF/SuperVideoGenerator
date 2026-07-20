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
        assert data["image"]["model"] == "agnes-image-2.1-flash"
        assert "pipeline" in data["image"]
        assert data["image"]["pipeline"]["source_mode"] == "generate"
        assert any(p["id"] == "volcengine" for p in data["image"]["available_providers"])
        assert any(p["id"] == "volcengine" for p in data["video"]["available_providers"])


@pytest.mark.asyncio
async def test_patch_ai_volcengine_image_and_video():
    """PATCH 可切换火山方舟 SeedDream / SeedDance。"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.patch(
            "/api/ai/config",
            json={
                "image": {
                    "provider": "volcengine",
                    "model": "doubao-seedream-5-0-pro",
                    "api_key": "ark-test-key",
                    "base_url": "https://ark.cn-beijing.volces.com/api/v3",
                },
                "video": {
                    "enabled": True,
                    "provider": "volcengine",
                    "model": "doubao-seedance-2-0",
                    "api_key": "ark-test-key",
                    "base_url": "https://ark.cn-beijing.volces.com/api/v3",
                },
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert data["image"]["provider"] == "volcengine"
        assert data["image"]["model"] == "doubao-seedream-5-0-pro"
        assert data["video"]["provider"] == "volcengine"
        assert data["video"]["model"] == "doubao-seedance-2-0"
        assert data["video"]["enabled"] is True


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
async def test_patch_ai_llm_token_config():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.patch(
            "/api/ai/config",
            json={
                "llm": {
                    "max_tokens": 4096,
                    "context_window_tokens": 200_000,
                    "history_keep_messages": 8,
                }
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert data["llm"]["max_tokens"] == 4096
        assert data["llm"]["context_window_tokens"] == 200_000
        assert data["llm"]["history_keep_messages"] == 8
