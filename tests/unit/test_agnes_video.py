"""Agnes Video V2.0 客户端单元测试。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.llm.tools.video.agnes_client import (
    AgnesVideoGenerationError,
    _backoff_wait_sec,
    _create_retry_wait_sec,
    build_video_create_payload,
    create_video_task_async,
    fetch_video_task_async,
    generate_video_async,
    normalize_num_frames,
    reset_create_rate_limiter,
    resolution_to_size,
    resolve_create_min_interval_sec,
    resolve_poll_interval_sec,
    wait_for_video_completion_async,
)
from core.llm.tools.video.settings import VideoGenSettings, reset_video_gen_manager


@pytest.fixture(autouse=True)
def _reset_video_mgr(monkeypatch):
    """每个用例重置视频配置管理器与创建限流状态。"""
    reset_video_gen_manager()
    reset_create_rate_limiter()
    monkeypatch.setenv("SVG_VIDEO_GEN_ENABLED", "true")
    monkeypatch.setenv("SVG_VIDEO_GEN_API_KEY", "test-key")
    monkeypatch.setenv("SVG_VIDEO_GEN_CREATE_MIN_INTERVAL_SEC", "0")


def test_normalize_num_frames_8n_plus_one():
    """帧数应符合 8n+1 且不超过 441。"""
    assert normalize_num_frames(5, 24) == 121
    frames_18 = normalize_num_frames(18, 24)
    assert frames_18 <= 441
    assert (frames_18 - 1) % 8 == 0
    assert normalize_num_frames(18.375, 24) == 441


def test_resolution_to_size():
    """分辨率档位映射。"""
    assert resolution_to_size("1080p") == (1920, 1080)
    assert resolution_to_size("720p") == (1152, 768)


def test_build_payload_text2video():
    """文生视频 payload 仅含 prompt。"""
    settings = VideoGenSettings(model="agnes-video-v2.0", max_duration_sec=5)
    payload = build_video_create_payload(
        prompt="A cat on beach",
        settings=settings,
        mode="text2video",
    )
    assert payload["model"] == "agnes-video-v2.0"
    assert payload["prompt"] == "A cat on beach"
    assert "image" not in payload
    assert "extra_body" not in payload
    assert payload["num_frames"] == 121


def test_build_payload_img2video():
    """图生视频 payload 含 image URL。"""
    settings = VideoGenSettings()
    payload = build_video_create_payload(
        prompt="Animate gently",
        settings=settings,
        mode="img2video",
        image_url="https://example.com/a.png",
    )
    assert payload["image"] == "https://example.com/a.png"


def test_build_payload_keyframes_requires_two_urls():
    """关键帧模式至少需要两张图。"""
    settings = VideoGenSettings()
    with pytest.raises(AgnesVideoGenerationError):
        build_video_create_payload(
            prompt="smooth transition",
            settings=settings,
            mode="keyframes",
            keyframe_urls=["https://example.com/1.png"],
        )


def test_build_payload_keyframes():
    """关键帧 payload 使用 extra_body。"""
    settings = VideoGenSettings()
    payload = build_video_create_payload(
        prompt="smooth transition",
        settings=settings,
        mode="keyframes",
        keyframe_urls=[
            "https://example.com/1.png",
            "https://example.com/2.png",
        ],
    )
    assert payload["extra_body"]["mode"] == "keyframes"
    assert len(payload["extra_body"]["image"]) == 2


@pytest.mark.asyncio
async def test_create_video_task_async():
    """创建任务应 POST /v1/videos。"""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "video_id": "video_abc",
        "task_id": "task_abc",
        "status": "queued",
    }
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    settings = VideoGenSettings(
        base_url="https://apihub.agnes-ai.com/v1",
        create_min_interval_sec=0,
    )
    payload = {"model": "agnes-video-v2.0", "prompt": "test"}

    with patch("core.llm.tools.video.agnes_client.httpx.AsyncClient", return_value=mock_client):
        data = await create_video_task_async(payload, settings=settings, api_key="k")

    mock_client.post.assert_awaited_once()
    call_kwargs = mock_client.post.await_args
    assert call_kwargs.args[0] == "https://apihub.agnes-ai.com/v1/videos"
    assert data["video_id"] == "video_abc"


@pytest.mark.asyncio
async def test_fetch_video_task_by_video_id():
    """轮询应使用 /agnesapi?video_id=。"""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"status": "completed", "url": "https://out/v.mp4"}
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    settings = VideoGenSettings(base_url="https://apihub.agnes-ai.com/v1")

    with patch("core.llm.tools.video.agnes_client.httpx.AsyncClient", return_value=mock_client):
        data = await fetch_video_task_async(
            video_id="video_abc", settings=settings, api_key="k"
        )

    call_kwargs = mock_client.get.await_args
    assert call_kwargs.args[0] == "https://apihub.agnes-ai.com/agnesapi"
    assert call_kwargs.kwargs["params"]["video_id"] == "video_abc"
    assert data["url"] == "https://out/v.mp4"


@pytest.mark.asyncio
async def test_generate_video_async_end_to_end(monkeypatch):
    """创建 + 轮询完成应返回 url。"""
    monkeypatch.setattr(
        "core.llm.tools.video.agnes_client.create_video_task_async",
        AsyncMock(
            return_value={"video_id": "video_x", "task_id": "task_x", "status": "queued"}
        ),
    )
    monkeypatch.setattr(
        "core.llm.tools.video.agnes_client.wait_for_video_completion_async",
        AsyncMock(
            return_value={
                "status": "completed",
                "url": "https://platform-outputs/v.mp4",
                "video_id": "video_x",
            }
        ),
    )
    url, meta = await generate_video_async(
        prompt="test",
        mode="text2video",
    )
    assert url == "https://platform-outputs/v.mp4"
    assert meta["video_id"] == "video_x"


def test_resolve_poll_interval_defaults_and_floor():
    """默认轮询 15s，且不得低于 5s。"""
    assert resolve_poll_interval_sec(VideoGenSettings()) == 15.0
    assert resolve_poll_interval_sec(VideoGenSettings(poll_interval_sec=2.0)) == 5.0


def test_backoff_prefers_retry_after_and_caps():
    """429 退避优先 Retry-After，并封顶。"""
    assert _backoff_wait_sec(attempt=0, base_sec=15.0, retry_after_sec=42.0) == 42.0
    assert _backoff_wait_sec(attempt=0, base_sec=15.0) == 15.0
    assert _backoff_wait_sec(attempt=1, base_sec=15.0) == 30.0
    assert _backoff_wait_sec(attempt=5, base_sec=60.0) == 120.0


@pytest.mark.asyncio
async def test_wait_retries_on_429_then_completes(monkeypatch):
    """状态查询遇 429 应退避后继续轮询直至完成。"""
    calls = {"n": 0}

    async def _fetch(**_kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise AgnesVideoGenerationError(
                "Agnes 视频查询失败 429: rate limit",
                http_status=429,
                retry_after_sec=0.01,
            )
        return {"status": "completed", "url": "https://out/ok.mp4"}

    sleeps: list[float] = []

    async def _sleep(sec: float):
        sleeps.append(sec)

    monkeypatch.setattr(
        "core.llm.tools.video.agnes_client.fetch_video_task_async",
        _fetch,
    )
    monkeypatch.setattr("core.llm.tools.video.agnes_client.asyncio.sleep", _sleep)

    settings = VideoGenSettings(
        timeout_sec=60.0,
        poll_interval_sec=15.0,
    )
    data = await wait_for_video_completion_async(
        video_id="video_rate",
        settings=settings,
        api_key="k",
    )
    assert data["url"] == "https://out/ok.mp4"
    assert calls["n"] == 2
    assert sleeps and sleeps[0] == 0.01


def test_create_retry_wait_parses_one_minute_message():
    """创建 429 文案含 1 minute 时应等待至少 60s。"""
    resp = MagicMock()
    resp.headers = {}
    resp.text = (
        '{"error":{"message":"video generation rate limit exceeded: '
        'allows 1 requests per 1 minute(s)"}}'
    )
    assert _create_retry_wait_sec(resp, attempt=0, base_sec=60.0) == 60.0


def test_resolve_create_min_interval_default():
    """显式配置创建最小间隔；0 表示不主动限流。"""
    assert resolve_create_min_interval_sec(VideoGenSettings(create_min_interval_sec=60)) == 60.0
    assert resolve_create_min_interval_sec(VideoGenSettings(create_min_interval_sec=0)) == 0.0


@pytest.mark.asyncio
async def test_create_retries_on_429_then_succeeds(monkeypatch):
    """创建遇 429 应退避后重试直至成功。"""
    ok = MagicMock()
    ok.status_code = 200
    ok.json.return_value = {"video_id": "v1", "task_id": "t1", "status": "queued"}
    limited = MagicMock()
    limited.status_code = 429
    limited.headers = {}
    limited.text = (
        '{"error":{"message":"allows 1 requests per 1 minute(s)","code":"rate_limit_exceeded"}}'
    )

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=[limited, ok])
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    sleeps: list[float] = []

    async def _sleep(sec: float):
        sleeps.append(sec)

    monkeypatch.setattr("core.llm.tools.video.agnes_client.asyncio.sleep", _sleep)

    settings = VideoGenSettings(
        base_url="https://apihub.agnes-ai.com/v1",
        create_min_interval_sec=0,
        create_max_attempts=3,
    )
    with patch("core.llm.tools.video.agnes_client.httpx.AsyncClient", return_value=mock_client):
        data = await create_video_task_async(
            {"model": "agnes-video-v2.0", "prompt": "x"},
            settings=settings,
            api_key="k",
        )
    assert data["video_id"] == "v1"
    assert mock_client.post.await_count == 2
    assert sleeps and sleeps[0] == 60.0
