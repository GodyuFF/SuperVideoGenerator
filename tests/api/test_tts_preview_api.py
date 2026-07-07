"""TTS 试听 API 测试。"""

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from apps.api.main import app


@pytest.mark.asyncio
async def test_tts_preview_works_when_tts_disabled_in_saved_config(monkeypatch):
    """试听不依赖 enabled 开关，且接受表单 provider 覆盖。"""
    from apps.api.state import state

    state.ai_config.tts.update(enabled=False, provider="openai")

    preview_file = Path("data/temp/tts_preview/test.mp3")

    def fake_synthesize(text, voice_file, config, **kwargs):
        Path(voice_file).parent.mkdir(parents=True, exist_ok=True)
        Path(voice_file).write_bytes(b"ID3")
        return object()

    monkeypatch.setattr("apps.api.routes.ai.synthesize_speech", fake_synthesize)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/api/ai/tts/preview",
            json={
                "text": "你好",
                "provider": "edge",
                "voice_name": "zh-CN-XiaoxiaoNeural-Female",
                "voice_rate": 1,
                "voice_volume": 1,
            },
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["ok"] is True
        assert data["url"].startswith("/api/ai/tts/preview/")


@pytest.mark.asyncio
async def test_tts_preview_openai_without_key_returns_clear_error():
    from apps.api.state import state

    state.ai_config.tts.update(enabled=False, provider="openai", api_key=None)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/api/ai/tts/preview",
            json={
                "text": "你好",
                "provider": "openai",
                "voice_name": "alloy",
            },
        )
        assert r.status_code == 400
        assert "API Key" in r.json()["detail"]
