"""媒体生成 Provider 能力矩阵（生图 / 生视频）。"""

from __future__ import annotations

from dataclasses import dataclass

_IMAGE_SIZE_OPTIONS = ("1024x768", "1024x1024", "768x1024")
_SEEDREAM_SIZE_OPTIONS = (
    "2K",
    "4K",
    "2048x2048",
    "2304x1728",
    "1728x2304",
    "2496x1664",
    "1664x2496",
    "2560x1440",
    "1440x2560",
    "3024x1296",
    "4096x4096",
    "4704x3520",
    "3520x4704",
    "5504x3040",
    "3040x5504",
)
_VIDEO_PROVIDER_IDS = ("agnes", "volcengine", "kling", "runway", "fal")


@dataclass(frozen=True)
class ImageProviderCapability:
    """生图 Provider 能力描述。"""

    provider_id: str
    supports_txt2img: bool
    supports_img2img: bool
    supports_multi_reference: bool
    max_reference_count: int
    supports_text_in_image: bool
    size_options: tuple[str, ...]


@dataclass(frozen=True)
class VideoProviderCapability:
    """生视频 Provider 能力描述。"""

    provider_id: str
    supports_text2video: bool
    supports_img2video: bool
    supports_keyframes: bool
    supports_multi_shot: bool
    max_duration_sec: int
    max_concurrency: int
    native_audio: bool


_IMAGE_CAPABILITIES: dict[str, ImageProviderCapability] = {
    "agnes": ImageProviderCapability(
        provider_id="agnes",
        supports_txt2img=True,
        supports_img2img=True,
        supports_multi_reference=True,
        max_reference_count=8,
        supports_text_in_image=False,
        size_options=_IMAGE_SIZE_OPTIONS,
    ),
    "local_sd": ImageProviderCapability(
        provider_id="local_sd",
        supports_txt2img=True,
        supports_img2img=True,
        supports_multi_reference=False,
        max_reference_count=1,
        supports_text_in_image=False,
        size_options=_IMAGE_SIZE_OPTIONS,
    ),
    "bailian": ImageProviderCapability(
        provider_id="bailian",
        supports_txt2img=True,
        supports_img2img=True,
        supports_multi_reference=True,
        max_reference_count=4,
        supports_text_in_image=True,
        size_options=_IMAGE_SIZE_OPTIONS,
    ),
    "volcengine": ImageProviderCapability(
        provider_id="volcengine",
        supports_txt2img=True,
        supports_img2img=True,
        supports_multi_reference=True,
        max_reference_count=8,
        supports_text_in_image=False,
        size_options=_SEEDREAM_SIZE_OPTIONS,
    ),
    "openai": ImageProviderCapability(
        provider_id="openai",
        supports_txt2img=True,
        supports_img2img=True,
        supports_multi_reference=False,
        max_reference_count=1,
        supports_text_in_image=True,
        size_options=_IMAGE_SIZE_OPTIONS,
    ),
    "fal": ImageProviderCapability(
        provider_id="fal",
        supports_txt2img=True,
        supports_img2img=True,
        supports_multi_reference=False,
        max_reference_count=1,
        supports_text_in_image=False,
        size_options=_IMAGE_SIZE_OPTIONS,
    ),
    "gemini": ImageProviderCapability(
        provider_id="gemini",
        supports_txt2img=True,
        supports_img2img=True,
        supports_multi_reference=False,
        max_reference_count=1,
        supports_text_in_image=False,
        size_options=_IMAGE_SIZE_OPTIONS,
    ),
}


_VIDEO_CAPABILITIES: dict[str, VideoProviderCapability] = {
    "agnes": VideoProviderCapability(
        provider_id="agnes",
        supports_text2video=True,
        supports_img2video=True,
        supports_keyframes=True,
        supports_multi_shot=False,
        max_duration_sec=10,
        max_concurrency=1,
        native_audio=False,
    ),
    "volcengine": VideoProviderCapability(
        provider_id="volcengine",
        supports_text2video=True,
        supports_img2video=True,
        supports_keyframes=True,
        supports_multi_shot=False,
        max_duration_sec=12,
        max_concurrency=1,
        native_audio=False,
    ),
    "kling": VideoProviderCapability(
        provider_id="kling",
        supports_text2video=True,
        supports_img2video=True,
        supports_keyframes=True,
        supports_multi_shot=True,
        max_duration_sec=15,
        max_concurrency=1,
        native_audio=True,
    ),
    "runway": VideoProviderCapability(
        provider_id="runway",
        supports_text2video=True,
        supports_img2video=True,
        supports_keyframes=True,
        supports_multi_shot=False,
        max_duration_sec=10,
        max_concurrency=1,
        native_audio=False,
    ),
    "fal": VideoProviderCapability(
        provider_id="fal",
        supports_text2video=True,
        supports_img2video=True,
        supports_keyframes=True,
        supports_multi_shot=False,
        max_duration_sec=10,
        max_concurrency=1,
        native_audio=False,
    ),
}


def get_image_provider_capability(provider_id: str) -> ImageProviderCapability | None:
    """按 provider id 获取生图能力矩阵。"""
    return _IMAGE_CAPABILITIES.get(provider_id.strip().lower())


def get_video_provider_capability(provider_id: str) -> VideoProviderCapability | None:
    """按 provider id 获取生视频能力矩阵。"""
    return _VIDEO_CAPABILITIES.get(provider_id.strip().lower())


def list_image_provider_capabilities() -> list[dict[str, object]]:
    """列出全部已注册生图 Provider 能力（供 API / 前端展示）。"""
    from core.llm.tools.image.settings import IMAGE_PROVIDERS

    rows: list[dict[str, object]] = []
    for provider_id in IMAGE_PROVIDERS:
        cap = _IMAGE_CAPABILITIES.get(provider_id)
        if not cap:
            continue
        rows.append(
            {
                "provider_id": cap.provider_id,
                "supports_txt2img": cap.supports_txt2img,
                "supports_img2img": cap.supports_img2img,
                "supports_multi_reference": cap.supports_multi_reference,
                "max_reference_count": cap.max_reference_count,
                "supports_text_in_image": cap.supports_text_in_image,
                "size_options": list(cap.size_options),
            }
        )
    return rows


def list_video_provider_capabilities() -> list[dict[str, object]]:
    """列出全部已注册生视频 Provider 能力。"""
    rows: list[dict[str, object]] = []
    for provider_id in _VIDEO_PROVIDER_IDS:
        cap = _VIDEO_CAPABILITIES.get(provider_id)
        if not cap:
            continue
        rows.append(
            {
                "provider_id": cap.provider_id,
                "supports_text2video": cap.supports_text2video,
                "supports_img2video": cap.supports_img2video,
                "supports_keyframes": cap.supports_keyframes,
                "supports_multi_shot": cap.supports_multi_shot,
                "max_duration_sec": cap.max_duration_sec,
                "max_concurrency": cap.max_concurrency,
                "native_audio": cap.native_audio,
            }
        )
    return rows


def assert_video_mode_supported(provider_id: str, mode: str) -> None:
    """校验生视频子模式是否被 Provider 支持，不支持则抛 ValueError。"""
    cap = get_video_provider_capability(provider_id)
    if not cap:
        return
    normalized = mode.strip().lower()
    if normalized == "text2video" and not cap.supports_text2video:
        raise ValueError(f"Provider {provider_id} 不支持 text2video")
    if normalized == "img2video" and not cap.supports_img2video:
        raise ValueError(f"Provider {provider_id} 不支持 img2video")
    if normalized == "keyframes" and not cap.supports_keyframes:
        raise ValueError(f"Provider {provider_id} 不支持 keyframes")
