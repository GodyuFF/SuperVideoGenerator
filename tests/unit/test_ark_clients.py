"""火山方舟 SeedDream / SeedDance 客户端单元测试。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.llm.tools.image.ark_client import (
    SEEDREAM_MIN_PIXELS,
    _build_payload,
    _model_supports_sequential_image_generation,
    ark_txt2img,
    normalize_seedream_size,
)
from core.llm.tools.image.settings import ImageGenSettings, reset_image_gen_settings
from core.llm.tools.video.ark_client import (
    ArkVideoGenerationError,
    build_ark_video_payload,
    create_ark_video_task_async,
    generate_video_async,
    wait_for_ark_video_completion_async,
)
from core.llm.tools.video.settings import VideoGenSettings, reset_video_gen_manager


@pytest.fixture(autouse=True)
def _reset_managers(monkeypatch):
    """每个用例重置配置单例。"""
    reset_image_gen_settings()
    reset_video_gen_manager()
    monkeypatch.setenv("ARK_API_KEY", "ark-test-key")


def test_build_ark_video_payload_text2video():
    """文生视频 payload 含 text content。"""
    settings = VideoGenSettings(
        provider="volcengine",
        model="doubao-seedance-2-0",
        resolution="1080p",
        max_duration_sec=8,
    )
    payload = build_ark_video_payload(
        prompt="A cat on beach",
        settings=settings,
        mode="text2video",
    )
    assert payload["model"] == "doubao-seedance-2-0"
    assert payload["content"][0]["type"] == "text"
    assert payload["content"][0]["text"] == "A cat on beach"
    assert payload["resolution"] == "1080p"
    assert payload["duration"] == 8


def test_build_ark_video_payload_img2video():
    """图生视频 payload 含 first_frame。"""
    settings = VideoGenSettings(provider="volcengine")
    payload = build_ark_video_payload(
        prompt="Animate",
        settings=settings,
        mode="img2video",
        image_url="https://example.com/a.png",
    )
    assert len(payload["content"]) == 2
    assert payload["content"][1]["role"] == "first_frame"


def test_build_ark_video_payload_keyframes_requires_two():
    """首尾帧模式至少需要两张图。"""
    settings = VideoGenSettings(provider="volcengine")
    with pytest.raises(ArkVideoGenerationError):
        build_ark_video_payload(
            prompt="transition",
            settings=settings,
            mode="keyframes",
            keyframe_urls=["https://example.com/1.png"],
        )


def test_seedream5_payload_omits_sequential_image_generation():
    """SeedDream 5.0 请求体不得带 sequential_image_generation（会 400）。"""
    settings = ImageGenSettings(
        provider="volcengine",
        model="doubao-seedream-5-0-pro-260628",
        default_size="1024x1024",
    )
    payload = _build_payload("夸父追日", settings=settings)
    assert "sequential_image_generation" not in payload
    assert payload["model"] == "doubao-seedream-5-0-pro-260628"
    assert payload["size"] == "2048x2048"
    assert _model_supports_sequential_image_generation(settings.model) is False


def test_normalize_seedream_size_meets_min_pixels():
    """小尺寸映射后总像素不低于官方下限。"""
    assert normalize_seedream_size("1024x1024") == "2048x2048"
    assert normalize_seedream_size("1024x768") == "2304x1728"
    assert normalize_seedream_size("768x1024") == "1728x2304"
    assert normalize_seedream_size("2K") == "2K"
    wh = normalize_seedream_size("800x600")
    w, h = map(int, wh.split("x"))
    assert w * h >= SEEDREAM_MIN_PIXELS


def test_coerce_image_size_accepts_custom_seedream_wh():
    """火山自定义像素宽高经校验后保留或抬升。"""
    from core.llm.tools.image.settings import coerce_image_size

    assert coerce_image_size("volcengine", "2560x1440") == "2560x1440"
    assert coerce_image_size("volcengine", "2K") == "2K"
    lifted = coerce_image_size("volcengine", "1280x720")
    w, h = map(int, lifted.split("x"))
    assert w * h >= SEEDREAM_MIN_PIXELS
    with pytest.raises(ValueError):
        coerce_image_size("volcengine", "not-a-size")


def test_seedream4_payload_disables_sequential_image_generation():
    """SeedDream 4.x 支持组图参数时应显式 disabled。"""
    settings = ImageGenSettings(
        provider="volcengine",
        model="doubao-seedream-4-0-250828",
    )
    payload = _build_payload("test", settings=settings)
    assert payload["sequential_image_generation"] == "disabled"
    assert _model_supports_sequential_image_generation(settings.model) is True


@pytest.mark.asyncio
async def test_ark_txt2img_returns_url():
    """SeedDream 文生图解析 url。"""
    settings = ImageGenSettings(
        provider="volcengine",
        model="doubao-seedream-5-0-pro",
        base_url="https://ark.cn-beijing.volces.com/api/v3",
        api_key="ark-test-key",
    )
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"data": [{"url": "https://cdn.test/img.png"}]}

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("core.llm.tools.image.ark_client.httpx.AsyncClient", return_value=mock_client):
        url = await ark_txt2img("sunset", settings=settings)
    assert url == "https://cdn.test/img.png"


@pytest.mark.asyncio
async def test_create_ark_video_task_async():
    """SeedDance 创建任务返回 task id。"""
    settings = VideoGenSettings(
        provider="volcengine",
        model="doubao-seedance-2-0",
        base_url="https://ark.cn-beijing.volces.com/api/v3",
        api_key="ark-test-key",
    )
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"id": "cgt-test-1", "status": "queued"}

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    payload = build_ark_video_payload(
        prompt="test",
        settings=settings,
        mode="text2video",
    )
    with patch("core.llm.tools.video.ark_client.httpx.AsyncClient", return_value=mock_client):
        data = await create_ark_video_task_async(payload, settings=settings)
    assert data["id"] == "cgt-test-1"


@pytest.mark.asyncio
async def test_generate_video_async_polls_until_succeeded():
    """SeedDance 端到端轮询直至 succeeded。"""
    settings = VideoGenSettings(
        enabled=True,
        provider="volcengine",
        model="doubao-seedance-2-0",
        base_url="https://ark.cn-beijing.volces.com/api/v3",
        api_key="ark-test-key",
        timeout_sec=30,
    )

    create_resp = MagicMock(status_code=200)
    create_resp.json.return_value = {"id": "cgt-1", "status": "queued"}

    running_resp = MagicMock(status_code=200)
    running_resp.json.return_value = {"id": "cgt-1", "status": "running"}

    done_resp = MagicMock(status_code=200)
    done_resp.json.return_value = {
        "id": "cgt-1",
        "status": "succeeded",
        "content": {"video_url": "https://cdn.test/out.mp4"},
    }

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=create_resp)
    mock_client.get = AsyncMock(side_effect=[running_resp, done_resp])
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("core.llm.tools.video.ark_client.httpx.AsyncClient", return_value=mock_client):
        url, meta = await generate_video_async(
            prompt="drone shot",
            mode="text2video",
            settings=settings,
        )
    assert url == "https://cdn.test/out.mp4"
    assert meta["task_id"] == "cgt-1"


def test_image_settings_switch_to_volcengine():
    """切换生图 provider 为 volcengine 时自动填入 SeedDream 默认模型。"""
    from core.llm.tools.image.settings import ImageGenConfigManager, reset_image_gen_settings

    reset_image_gen_settings()
    mgr = ImageGenConfigManager()
    cfg = mgr.update(
        provider="volcengine",
        api_key="ark-test",
    )
    assert cfg["provider"] == "volcengine"
    assert cfg["model"] == "doubao-seedream-5-0-pro"
    public = mgr.get_public_config()
    assert "2K" in public["available_sizes"]
    assert "2560x1440" in public["available_sizes"]
    assert len(public["available_sizes"]) >= 10


def test_video_settings_switch_to_volcengine():
    """切换视频 provider 为 volcengine 时自动填入 SeedDance 默认模型。"""
    from core.llm.tools.video.settings import VideoGenConfigManager, reset_video_gen_manager

    reset_video_gen_manager()
    mgr = VideoGenConfigManager()
    cfg = mgr.update(
        provider="volcengine",
        api_key="ark-test",
    )
    assert cfg["provider"] == "volcengine"
    assert cfg["model"] == "doubao-seedance-2-0"


@pytest.mark.asyncio
async def test_video_provider_dispatches_volcengine():
    """provider 分发层应路由到 ark_client。"""
    from unittest.mock import AsyncMock, patch

    from core.llm.tools.video.provider import generate_video_async
    from core.llm.tools.video.settings import VideoGenSettings, reset_video_gen_manager

    reset_video_gen_manager()
    settings = VideoGenSettings(
        provider="volcengine",
        model="doubao-seedance-2-0",
        api_key="ark-test",
    )
    with patch(
        "core.llm.tools.video.ark_client.generate_video_async",
        new_callable=AsyncMock,
        return_value=("https://cdn.test/v.mp4", {"task_id": "cgt-1"}),
    ) as mock_ark:
        url, meta = await generate_video_async(
            prompt="test",
            mode="text2video",
            settings=settings,
        )
    mock_ark.assert_awaited_once()
    assert url == "https://cdn.test/v.mp4"
    assert meta["task_id"] == "cgt-1"


@pytest.mark.asyncio
async def test_wait_for_ark_video_failed():
    """SeedDance 任务失败应抛出错误。"""
    settings = VideoGenSettings(provider="volcengine", api_key="ark-test-key")
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = {"id": "cgt-1", "status": "failed", "error": "bad prompt"}

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("core.llm.tools.video.ark_client.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(ArkVideoGenerationError, match="bad prompt"):
            await wait_for_ark_video_completion_async("cgt-1", settings=settings)
