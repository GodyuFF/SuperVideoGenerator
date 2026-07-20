"""Runway Gen-4 视频生成客户端。"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any

import httpx

from core.llm.tools.video.agnes_client import VideoGenMode, _backoff_wait_sec
from core.llm.tools.video.settings import VideoGenSettings, get_video_gen_manager

DEFAULT_RUNWAY_BASE_URL = "https://api.dev.runwayml.com/v1"
DEFAULT_RUNWAY_MODEL = "gen4.5"


class RunwayVideoGenerationError(RuntimeError):
    """Runway 视频生成失败。"""

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


def resolved_runway_api_key(
    settings: VideoGenSettings | None = None,
    explicit_key: str | None = None,
) -> str:
    """解析 Runway API Key。"""
    if explicit_key and explicit_key.strip():
        return explicit_key.strip()
    s = settings or get_video_gen_manager().get_settings()
    if s.api_key and s.api_key.strip():
        return s.api_key.strip()
    for env_name in ("SVG_VIDEO_GEN_API_KEY", "RUNWAY_API_KEY"):
        val = os.getenv(env_name, "").strip()
        if val:
            return val
    return ""


def _auth_headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key.strip()}",
        "Content-Type": "application/json",
        "X-Runway-Version": "2024-11-06",
    }


def _normalize_duration(duration_sec: float | None, settings: VideoGenSettings) -> int:
    raw = duration_sec if duration_sec is not None else float(settings.max_duration_sec or 5)
    return max(2, min(10, int(round(raw))))


def build_runway_video_payload(
    *,
    prompt: str,
    settings: VideoGenSettings,
    mode: VideoGenMode,
    image_url: str | None = None,
    keyframe_urls: list[str] | None = None,
    duration_sec: float | None = None,
) -> tuple[str, dict[str, Any]]:
    """组装 Runway 创建任务 endpoint 与请求体。"""
    model = settings.model or DEFAULT_RUNWAY_MODEL
    duration = _normalize_duration(duration_sec, settings)
    if mode == "img2video" and image_url:
        endpoint = "image_to_video"
        payload: dict[str, Any] = {
            "model": model,
            "promptText": prompt.strip(),
            "promptImage": image_url.strip(),
            "duration": duration,
        }
        return endpoint, payload
    if mode == "keyframes" and keyframe_urls:
        urls = [u.strip() for u in keyframe_urls if u and u.strip()]
        if len(urls) < 2:
            raise RunwayVideoGenerationError("首尾帧模式至少需要 2 张可访问图片 URL")
        endpoint = "image_to_video"
        payload = {
            "model": model,
            "promptText": prompt.strip(),
            "promptImage": urls[0],
            "duration": duration,
            "lastFrame": urls[1],
        }
        return endpoint, payload
    endpoint = "text_to_video"
    payload = {
        "model": model,
        "promptText": prompt.strip(),
        "duration": duration,
    }
    return endpoint, payload


def _task_url(base_url: str, task_id: str) -> str:
    root = (base_url or DEFAULT_RUNWAY_BASE_URL).rstrip("/")
    return f"{root}/tasks/{task_id.strip()}"


def _create_url(base_url: str, endpoint: str) -> str:
    root = (base_url or DEFAULT_RUNWAY_BASE_URL).rstrip("/")
    return f"{root}/{endpoint.strip('/')}"


def _extract_task_id(data: dict[str, Any]) -> str:
    val = str(data.get("id") or data.get("task_id") or "").strip()
    if val:
        return val
    raise RunwayVideoGenerationError("Runway 创建响应缺少 task id")


def _extract_task_status(data: dict[str, Any]) -> str:
    return str(data.get("status") or "").strip().lower()


def _extract_video_url(data: dict[str, Any]) -> str:
    output = data.get("output")
    if isinstance(output, list) and output:
        first = output[0]
        if isinstance(first, str) and first.strip():
            return first.strip()
        if isinstance(first, dict):
            url = str(first.get("url") or first.get("uri") or "").strip()
            if url:
                return url
    if isinstance(output, dict):
        url = str(output.get("url") or output.get("uri") or "").strip()
        if url:
            return url
    url = str(data.get("url") or data.get("video_url") or "").strip()
    if url:
        return url
    raise RunwayVideoGenerationError("Runway 完成响应缺少 video URL")


async def create_runway_video_task_async(
    endpoint: str,
    payload: dict[str, Any],
    *,
    settings: VideoGenSettings | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    """创建 Runway 异步视频任务。"""
    s = settings or get_video_gen_manager().get_settings()
    key = resolved_runway_api_key(s, api_key)
    if not key:
        raise RunwayVideoGenerationError("未配置 Runway API Key")
    url = _create_url(s.base_url, endpoint)
    max_attempts = max(1, int(getattr(s, "create_max_attempts", 4) or 4))

    for attempt in range(max_attempts):
        try:
            async with httpx.AsyncClient(timeout=60.0, trust_env=s.trust_env) as client:
                resp = await client.post(url, headers=_auth_headers(key), json=payload)
        except httpx.HTTPError as e:
            raise RunwayVideoGenerationError(f"Runway 网络错误：{e}") from e

        if resp.status_code == 429 and attempt + 1 < max_attempts:
            await asyncio.sleep(_backoff_wait_sec(attempt=attempt, base_sec=30.0))
            continue

        if resp.status_code >= 400:
            body = resp.text[:2000]
            raise RunwayVideoGenerationError(
                f"Runway 创建失败 {resp.status_code}: {body}",
                http_status=resp.status_code,
                api_message=body,
            )

        data = resp.json()
        if not isinstance(data, dict):
            raise RunwayVideoGenerationError("Runway 创建响应格式无效")
        return data

    raise RunwayVideoGenerationError("Runway 创建失败：429 重试次数已用尽", http_status=429)


async def fetch_runway_video_task_async(
    task_id: str,
    *,
    settings: VideoGenSettings | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    """查询 Runway 视频任务状态。"""
    s = settings or get_video_gen_manager().get_settings()
    key = resolved_runway_api_key(s, api_key)
    if not key:
        raise RunwayVideoGenerationError("未配置 Runway API Key")
    url = _task_url(s.base_url, task_id)
    try:
        async with httpx.AsyncClient(timeout=60.0, trust_env=s.trust_env) as client:
            resp = await client.get(url, headers=_auth_headers(key))
    except httpx.HTTPError as e:
        raise RunwayVideoGenerationError(f"Runway 查询网络错误：{e}") from e
    if resp.status_code >= 400:
        body = resp.text[:2000]
        raise RunwayVideoGenerationError(
            f"Runway 查询失败 {resp.status_code}: {body}",
            http_status=resp.status_code,
            api_message=body,
        )
    data = resp.json()
    if not isinstance(data, dict):
        raise RunwayVideoGenerationError("Runway 查询响应格式无效")
    return data


async def wait_for_runway_video_completion_async(
    task_id: str,
    *,
    settings: VideoGenSettings | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    """轮询 Runway 任务直至完成。"""
    s = settings or get_video_gen_manager().get_settings()
    deadline = time.monotonic() + float(s.timeout_sec or 600.0)
    poll = max(5.0, float(s.poll_interval_sec or 10.0))
    last: dict[str, Any] = {}
    success = {"succeeded", "success", "completed", "done"}
    fail = {"failed", "error", "cancelled", "canceled"}

    while time.monotonic() < deadline:
        try:
            last = await fetch_runway_video_task_async(task_id, settings=s, api_key=api_key)
        except RunwayVideoGenerationError as e:
            if e.http_status == 429:
                await asyncio.sleep(_backoff_wait_sec(attempt=0, base_sec=poll))
                continue
            raise
        status = _extract_task_status(last)
        if status in success:
            url = _extract_video_url(last)
            last["video_url"] = url
            last["url"] = url
            return last
        if status in fail:
            err = last.get("error") or last.get("failure") or "视频生成失败"
            raise RunwayVideoGenerationError(f"Runway 生成失败：{err}", api_message=str(err))
        await asyncio.sleep(poll)

    raise RunwayVideoGenerationError(
        f"Runway 生成超时（>{s.timeout_sec}s），最后状态：{_extract_task_status(last)}"
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
    """创建 Runway 任务并等待完成。"""
    s = settings or get_video_gen_manager().get_settings()
    endpoint, payload = build_runway_video_payload(
        prompt=prompt,
        settings=s,
        mode=mode,
        image_url=image_url,
        keyframe_urls=keyframe_urls,
        duration_sec=duration_sec,
    )
    created = await create_runway_video_task_async(endpoint, payload, settings=s, api_key=api_key)
    task_id = _extract_task_id(created)
    completed = await wait_for_runway_video_completion_async(task_id, settings=s, api_key=api_key)
    url = _extract_video_url(completed)
    meta = {"task_id": task_id, "provider": "runway", "mode": mode, "endpoint": endpoint}
    return url, meta
