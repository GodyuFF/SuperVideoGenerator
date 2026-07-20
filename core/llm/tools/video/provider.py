"""视频生成 provider 分发：Agnes / 火山方舟 SeedDance。"""

from __future__ import annotations

from typing import Any

from core.llm.tools.video.agnes_client import VideoGenMode
from core.llm.tools.video.settings import VideoGenSettings, get_video_gen_manager


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
    """按配置 provider 调用对应视频生成客户端。"""
    s = settings or get_video_gen_manager().get_settings()
    provider = str(s.provider or "agnes").strip().lower()
    if provider == "volcengine":
        from core.llm.tools.video.ark_client import generate_video_async as ark_generate

        return await ark_generate(
            prompt=prompt,
            mode=mode,
            settings=s,
            api_key=api_key,
            image_url=image_url,
            keyframe_urls=keyframe_urls,
            duration_sec=duration_sec,
        )
    from core.llm.tools.video.agnes_client import generate_video_async as agnes_generate

    return await agnes_generate(
        prompt=prompt,
        mode=mode,
        settings=s,
        api_key=api_key,
        image_url=image_url,
        keyframe_urls=keyframe_urls,
        duration_sec=duration_sec,
    )
