"""媒体 Provider 能力矩阵与 fallback 测试。"""

from core.llm.tools.shared.media_capability import (
    assert_video_mode_supported,
    get_image_provider_capability,
    get_video_provider_capability,
    list_image_provider_capabilities,
    list_video_provider_capabilities,
)
from core.llm.tools.shared.provider_fallback import (
    build_fallback_settings,
    is_retryable_provider_error,
)
from core.llm.tools.image.settings import ImageGenSettings
from core.llm.tools.video.kling_client import build_kling_video_payload
from core.llm.tools.video.settings import VideoGenSettings


def test_image_capabilities_cover_new_providers():
    caps = {row["provider_id"] for row in list_image_provider_capabilities()}
    assert {"openai", "fal", "gemini"}.issubset(caps)


def test_video_capabilities_cover_new_providers():
    caps = {row["provider_id"] for row in list_video_provider_capabilities()}
    assert {"kling", "runway", "fal"}.issubset(caps)


def test_openai_supports_text_in_image():
    cap = get_image_provider_capability("openai")
    assert cap is not None
    assert cap.supports_text_in_image is True


def test_kling_supports_multi_shot():
    cap = get_video_provider_capability("kling")
    assert cap is not None
    assert cap.supports_multi_shot is True


def test_assert_video_mode_supported_noop_for_unknown_provider():
    """未知 provider 不阻断（由 API 层报错）。"""
    assert_video_mode_supported("unknown_provider", "text2video")


def test_build_kling_img2video_payload():
    settings = VideoGenSettings(model="kling-v3-omni-video")
    payload = build_kling_video_payload(
        prompt="镜头推进",
        settings=settings,
        mode="img2video",
        image_url="https://example.com/frame.png",
        duration_sec=5,
    )
    assert payload["start_frame_url"] == "https://example.com/frame.png"
    assert payload["video_mode"] == "start_end_frame"


def test_is_retryable_provider_error():
    class _Err(Exception):
        http_status = 429

    assert is_retryable_provider_error(_Err("rate limit"))
    assert not is_retryable_provider_error(ValueError("bad prompt"))


def test_build_fallback_image_settings():
    settings = ImageGenSettings(provider="volcengine", model="doubao-seedream-5-0-pro")
    fb = build_fallback_settings(
        settings,
        fallback_provider="fal",
        fallback_model="fal-ai/flux-pro/v1.1",
    )
    assert fb is not None
    assert fb.provider == "fal"
    assert fb.model == "fal-ai/flux-pro/v1.1"
