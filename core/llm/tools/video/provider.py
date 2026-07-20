"""视频生成 provider 分发：Agnes / 火山 / Kling / Runway / fal.ai。"""

from __future__ import annotations

from typing import Any

from core.llm.tools.shared.provider_fallback import build_fallback_settings, is_retryable_provider_error
from core.llm.tools.video.agnes_client import VideoGenMode
from core.llm.tools.video.settings import VideoGenSettings, get_video_gen_manager


async def _dispatch_video_generation(
    *,
    provider: str,
    prompt: str,
    mode: VideoGenMode,
    settings: VideoGenSettings,
    api_key: str | None,
    image_url: str | None,
    keyframe_urls: list[str] | None,
    duration_sec: float | None,
) -> tuple[str, dict[str, Any]]:
    """按 provider id 调用对应视频客户端。"""
    if provider == "volcengine":
        from core.llm.tools.video.ark_client import generate_video_async as impl

        return await impl(
            prompt=prompt,
            mode=mode,
            settings=settings,
            api_key=api_key,
            image_url=image_url,
            keyframe_urls=keyframe_urls,
            duration_sec=duration_sec,
        )
    if provider == "kling":
        from core.llm.tools.video.kling_client import generate_video_async as impl

        return await impl(
            prompt=prompt,
            mode=mode,
            settings=settings,
            api_key=api_key,
            image_url=image_url,
            keyframe_urls=keyframe_urls,
            duration_sec=duration_sec,
        )
    if provider == "runway":
        from core.llm.tools.video.runway_client import generate_video_async as impl

        return await impl(
            prompt=prompt,
            mode=mode,
            settings=settings,
            api_key=api_key,
            image_url=image_url,
            keyframe_urls=keyframe_urls,
            duration_sec=duration_sec,
        )
    if provider == "fal":
        from core.llm.tools.video.fal_video_client import generate_video_async as impl

        return await impl(
            prompt=prompt,
            mode=mode,
            settings=settings,
            api_key=api_key,
            image_url=image_url,
            keyframe_urls=keyframe_urls,
            duration_sec=duration_sec,
        )
    from core.llm.tools.video.agnes_client import generate_video_async as impl

    return await impl(
        prompt=prompt,
        mode=mode,
        settings=settings,
        api_key=api_key,
        image_url=image_url,
        keyframe_urls=keyframe_urls,
        duration_sec=duration_sec,
    )


async def generate_video_async(
    *,
    prompt: str,
    mode: VideoGenMode,
    settings: VideoGenSettings | None = None,
    api_key: str | None = None,
    image_url: str | None = None,
    keyframe_urls: list[str] | None = None,
    duration_sec: float | None = None,
) -> tuple[str, dict[str, Any]]:
    """按配置 provider 调用对应视频生成客户端，支持 fallback 降级。"""
    s = settings or get_video_gen_manager().get_settings()
    provider = str(s.provider or "agnes").strip().lower()
    try:
        return await _dispatch_video_generation(
            provider=provider,
            prompt=prompt,
            mode=mode,
            settings=s,
            api_key=api_key,
            image_url=image_url,
            keyframe_urls=keyframe_urls,
            duration_sec=duration_sec,
        )
    except Exception as exc:
        if not is_retryable_provider_error(exc):
            raise
        fb_settings = build_fallback_settings(
            s,
            fallback_provider=s.fallback_provider,
            fallback_model=s.fallback_model,
        )
        if fb_settings is None or fb_settings.provider == provider:
            raise
        url, meta = await _dispatch_video_generation(
            provider=fb_settings.provider,
            prompt=prompt,
            mode=mode,
            settings=fb_settings,
            api_key=api_key,
            image_url=image_url,
            keyframe_urls=keyframe_urls,
            duration_sec=duration_sec,
        )
        meta["fallback_from"] = provider
        meta["fallback_provider"] = fb_settings.provider
        return url, meta
