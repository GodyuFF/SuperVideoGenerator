"""fal.ai 视频生成客户端（聚合 Kling/Veo 等路由）。"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any

import httpx

from core.llm.tools.video.agnes_client import VideoGenMode, _backoff_wait_sec
from core.llm.tools.video.settings import VideoGenSettings, get_video_gen_manager

DEFAULT_FAL_VIDEO_BASE_URL = "https://fal.run"
DEFAULT_FAL_VIDEO_MODEL = "fal-ai/kling-video/v2.1/master/image-to-video"


class FalVideoGenerationError(RuntimeError):
    """fal.ai 视频生成失败。"""

    def __init__(
        self,
        message: str,
        *,
        http_status: int | None = None,
        api_message: str = "",
    ) -> None:
        self.http_status = http_status
        self.api_message = api_message or message
        super().__init__(message)


def resolved_fal_video_api_key(
    settings: VideoGenSettings | None = None,
    explicit_key: str | None = None,
) -> str:
    """解析 fal.ai 视频 API Key。"""
    if explicit_key and explicit_key.strip():
        return explicit_key.strip()
    s = settings or get_video_gen_manager().get_settings()
    if s.api_key and s.api_key.strip():
        return s.api_key.strip()
    for env_name in ("SVG_VIDEO_GEN_API_KEY", "FAL_KEY", "FAL_API_KEY"):
        val = os.getenv(env_name, "").strip()
        if val:
            return val
    return ""


def _fal_model_path(settings: VideoGenSettings, mode: VideoGenMode) -> str:
    model = (settings.model or "").strip()
    if model.startswith("fal-ai/"):
        return model
    if mode == "text2video":
        return "fal-ai/kling-video/v2.1/master/text-to-video"
    return DEFAULT_FAL_VIDEO_MODEL


def _endpoint(base_url: str, model_path: str) -> str:
    root = (base_url or DEFAULT_FAL_VIDEO_BASE_URL).rstrip("/")
    return f"{root}/{model_path.strip('/')}"


def build_fal_video_payload(
    *,
    prompt: str,
    settings: VideoGenSettings,
    mode: VideoGenMode,
    image_url: str | None = None,
    keyframe_urls: list[str] | None = None,
    duration_sec: float | None = None,
) -> dict[str, Any]:
    """组装 fal.ai 视频生成请求体。"""
    dur = duration_sec if duration_sec is not None else float(settings.max_duration_sec or 5)
    payload: dict[str, Any] = {
        "prompt": prompt.strip(),
        "duration": max(3, min(15, int(round(dur)))),
    }
    if mode == "img2video" and image_url:
        payload["image_url"] = image_url.strip()
    elif mode == "keyframes" and keyframe_urls:
        urls = [u.strip() for u in keyframe_urls if u and u.strip()]
        if len(urls) < 2:
            raise FalVideoGenerationError("首尾帧模式至少需要 2 张可访问图片 URL")
        payload["image_url"] = urls[0]
        payload["tail_image_url"] = urls[1]
    return payload


def _extract_video_url(data: dict[str, Any]) -> str:
    video = data.get("video")
    if isinstance(video, dict):
        url = str(video.get("url") or "").strip()
        if url:
            return url
    url = str(data.get("video_url") or data.get("url") or "").strip()
    if url:
        return url
    output = data.get("output")
    if isinstance(output, dict):
        url = str(output.get("video_url") or output.get("url") or "").strip()
        if url:
            return url
    raise FalVideoGenerationError("fal.ai 响应缺少 video URL")


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
    """调用 fal.ai 同步/短轮询视频接口并返回 video_url。"""
    s = settings or get_video_gen_manager().get_settings()
    key = resolved_fal_video_api_key(s, api_key)
    if not key:
        raise FalVideoGenerationError("未配置 fal.ai API Key")
    model_path = _fal_model_path(s, mode)
    payload = build_fal_video_payload(
        prompt=prompt,
        settings=s,
        mode=mode,
        image_url=image_url,
        keyframe_urls=keyframe_urls,
        duration_sec=duration_sec,
    )
    url = _endpoint(s.base_url, model_path)
    headers = {
        "Authorization": f"Key {key}",
        "Content-Type": "application/json",
    }
    deadline = time.monotonic() + float(s.timeout_sec or 600.0)
    max_attempts = max(1, int(getattr(s, "create_max_attempts", 4) or 4))

    for attempt in range(max_attempts):
        if time.monotonic() >= deadline:
            break
        try:
            async with httpx.AsyncClient(timeout=min(120.0, s.timeout_sec), trust_env=s.trust_env) as client:
                resp = await client.post(url, headers=headers, json=payload)
        except httpx.HTTPError as e:
            raise FalVideoGenerationError(f"fal.ai 网络错误：{e}") from e

        if resp.status_code == 429 and attempt + 1 < max_attempts:
            await asyncio.sleep(_backoff_wait_sec(attempt=attempt, base_sec=20.0))
            continue

        if resp.status_code >= 400:
            raise FalVideoGenerationError(
                f"fal.ai 视频生成失败 {resp.status_code}: {resp.text[:500]}",
                http_status=resp.status_code,
                api_message=resp.text[:500],
            )

        data = resp.json()
        if not isinstance(data, dict):
            raise FalVideoGenerationError("fal.ai 响应格式无效")

        if data.get("request_id") and not data.get("video") and not data.get("video_url"):
            request_id = str(data["request_id"])
            status_url = f"https://queue.fal.run/{model_path}/requests/{request_id}/status"
            while time.monotonic() < deadline:
                await asyncio.sleep(max(5.0, float(s.poll_interval_sec or 10.0)))
                async with httpx.AsyncClient(timeout=60.0, trust_env=s.trust_env) as client:
                    status_resp = await client.get(status_url, headers=headers)
                if status_resp.status_code >= 400:
                    continue
                status_data = status_resp.json()
                if isinstance(status_data, dict) and str(status_data.get("status", "")).lower() in {
                    "completed",
                    "succeeded",
                    "success",
                }:
                    data = status_data
                    break
            else:
                raise FalVideoGenerationError("fal.ai 视频生成超时")

        video_url = _extract_video_url(data)
        meta = {"provider": "fal", "mode": mode, "model": model_path}
        return video_url, meta

    raise FalVideoGenerationError("fal.ai 视频生成失败：重试次数已用尽")
