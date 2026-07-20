"""Kling 3.0 视频生成客户端（异步 task 模式）。"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any

import httpx

from core.llm.tools.video.agnes_client import VideoGenMode, _backoff_wait_sec
from core.llm.tools.video.settings import VideoGenSettings, get_video_gen_manager

DEFAULT_KLING_BASE_URL = "https://api.klingai.com/v1"
DEFAULT_KLING_MODEL = "kling-v3-omni-video"


class KlingVideoGenerationError(RuntimeError):
    """Kling 视频生成失败。"""

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


def resolved_kling_api_key(
    settings: VideoGenSettings | None = None,
    explicit_key: str | None = None,
) -> str:
    """解析 Kling API Key。"""
    if explicit_key and explicit_key.strip():
        return explicit_key.strip()
    s = settings or get_video_gen_manager().get_settings()
    if s.api_key and s.api_key.strip():
        return s.api_key.strip()
    for env_name in ("SVG_VIDEO_GEN_API_KEY", "KLING_API_KEY", "KLING_ACCESS_KEY"):
        val = os.getenv(env_name, "").strip()
        if val:
            return val
    return ""


def _auth_headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key.strip()}",
        "Content-Type": "application/json",
    }


def _normalize_duration(duration_sec: float | None, settings: VideoGenSettings) -> int:
    raw = duration_sec if duration_sec is not None else float(settings.max_duration_sec or 5)
    return max(3, min(15, int(round(raw))))


def build_kling_video_payload(
    *,
    prompt: str,
    settings: VideoGenSettings,
    mode: VideoGenMode,
    image_url: str | None = None,
    keyframe_urls: list[str] | None = None,
    duration_sec: float | None = None,
) -> dict[str, Any]:
    """组装 Kling 创建任务请求体。"""
    payload: dict[str, Any] = {
        "model": settings.model or DEFAULT_KLING_MODEL,
        "prompt": prompt.strip(),
        "duration": _normalize_duration(duration_sec, settings),
    }
    if mode == "img2video" and image_url:
        payload["start_frame_url"] = image_url.strip()
        payload["video_mode"] = "start_end_frame"
    elif mode == "keyframes" and keyframe_urls:
        urls = [u.strip() for u in keyframe_urls if u and u.strip()]
        if len(urls) < 2:
            raise KlingVideoGenerationError("首尾帧模式至少需要 2 张可访问图片 URL")
        payload["start_frame_url"] = urls[0]
        payload["end_frame_url"] = urls[1]
        payload["video_mode"] = "start_end_frame"
    return payload


def _generations_url(base_url: str) -> str:
    root = (base_url or DEFAULT_KLING_BASE_URL).rstrip("/")
    return f"{root}/videos/generations"


def _task_url(base_url: str, task_id: str) -> str:
    root = (base_url or DEFAULT_KLING_BASE_URL).rstrip("/")
    return f"{root}/tasks/{task_id.strip()}"


def _extract_task_id(data: dict[str, Any]) -> str:
    for key in ("task_id", "id", "request_id"):
        val = str(data.get(key) or "").strip()
        if val:
            return val
    inner = data.get("data")
    if isinstance(inner, dict):
        for key in ("task_id", "id"):
            val = str(inner.get(key) or "").strip()
            if val:
                return val
    raise KlingVideoGenerationError("Kling 创建响应缺少 task_id")


def _extract_task_status(data: dict[str, Any]) -> str:
    for key in ("status", "task_status", "state"):
        val = str(data.get(key) or "").strip().lower()
        if val:
            return val
    inner = data.get("data")
    if isinstance(inner, dict):
        val = str(inner.get("status") or inner.get("task_status") or "").strip().lower()
        if val:
            return val
    return ""


def _extract_video_url(data: dict[str, Any]) -> str:
    for key in ("video_url", "url"):
        val = str(data.get(key) or "").strip()
        if val:
            return val
    inner = data.get("data")
    if isinstance(inner, dict):
        for key in ("video_url", "url"):
            val = str(inner.get(key) or "").strip()
            if val:
                return val
        output = inner.get("output")
        if isinstance(output, dict):
            val = str(output.get("video_url") or output.get("url") or "").strip()
            if val:
                return val
    raise KlingVideoGenerationError("Kling 完成响应缺少 video_url")


async def create_kling_video_task_async(
    payload: dict[str, Any],
    *,
    settings: VideoGenSettings | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    """创建 Kling 异步视频任务（含 429 退避）。"""
    s = settings or get_video_gen_manager().get_settings()
    key = resolved_kling_api_key(s, api_key)
    if not key:
        raise KlingVideoGenerationError("未配置 Kling API Key")
    url = _generations_url(s.base_url)
    max_attempts = max(1, int(getattr(s, "create_max_attempts", 4) or 4))
    headers = _auth_headers(key)

    for attempt in range(max_attempts):
        try:
            async with httpx.AsyncClient(timeout=60.0, trust_env=s.trust_env) as client:
                resp = await client.post(url, headers=headers, json=payload)
        except httpx.HTTPError as e:
            raise KlingVideoGenerationError(f"Kling 网络错误：{e}") from e

        if resp.status_code == 429 and attempt + 1 < max_attempts:
            wait = _backoff_wait_sec(attempt=attempt, base_sec=30.0)
            await asyncio.sleep(wait)
            continue

        if resp.status_code >= 400:
            body = resp.text[:2000]
            raise KlingVideoGenerationError(
                f"Kling 创建失败 {resp.status_code}: {body}",
                http_status=resp.status_code,
                api_message=body,
            )

        try:
            data = resp.json()
        except ValueError as e:
            raise KlingVideoGenerationError("Kling 创建响应不是有效 JSON") from e
        if not isinstance(data, dict):
            raise KlingVideoGenerationError("Kling 创建响应格式无效")
        return data

    raise KlingVideoGenerationError("Kling 创建失败：429 重试次数已用尽", http_status=429)


async def fetch_kling_video_task_async(
    task_id: str,
    *,
    settings: VideoGenSettings | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    """查询 Kling 视频任务状态。"""
    s = settings or get_video_gen_manager().get_settings()
    key = resolved_kling_api_key(s, api_key)
    if not key:
        raise KlingVideoGenerationError("未配置 Kling API Key")
    url = _task_url(s.base_url, task_id)
    try:
        async with httpx.AsyncClient(timeout=60.0, trust_env=s.trust_env) as client:
            resp = await client.get(url, headers=_auth_headers(key))
    except httpx.HTTPError as e:
        raise KlingVideoGenerationError(f"Kling 查询网络错误：{e}") from e
    if resp.status_code >= 400:
        body = resp.text[:2000]
        raise KlingVideoGenerationError(
            f"Kling 查询失败 {resp.status_code}: {body}",
            http_status=resp.status_code,
            api_message=body,
        )
    data = resp.json()
    if not isinstance(data, dict):
        raise KlingVideoGenerationError("Kling 查询响应格式无效")
    return data


async def wait_for_kling_video_completion_async(
    task_id: str,
    *,
    settings: VideoGenSettings | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    """轮询 Kling 任务直至完成或失败。"""
    s = settings or get_video_gen_manager().get_settings()
    deadline = time.monotonic() + float(s.timeout_sec or 600.0)
    poll = max(5.0, float(s.poll_interval_sec or 10.0))
    last: dict[str, Any] = {}
    success = {"succeeded", "success", "completed", "done", "finish"}
    fail = {"failed", "error", "cancelled", "canceled"}

    while time.monotonic() < deadline:
        try:
            last = await fetch_kling_video_task_async(task_id, settings=s, api_key=api_key)
        except KlingVideoGenerationError as e:
            if e.http_status == 429:
                wait = _backoff_wait_sec(attempt=0, base_sec=poll)
                await asyncio.sleep(wait)
                continue
            raise
        status = _extract_task_status(last)
        if status in success:
            url = _extract_video_url(last)
            last["video_url"] = url
            last["url"] = url
            return last
        if status in fail:
            err = last.get("error") or last.get("message") or "视频生成失败"
            raise KlingVideoGenerationError(f"Kling 生成失败：{err}", api_message=str(err))
        await asyncio.sleep(poll)

    raise KlingVideoGenerationError(
        f"Kling 生成超时（>{s.timeout_sec}s），最后状态：{_extract_task_status(last)}"
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
    """创建 Kling 任务并等待完成，返回 (video_url, task_meta)。"""
    s = settings or get_video_gen_manager().get_settings()
    payload = build_kling_video_payload(
        prompt=prompt,
        settings=s,
        mode=mode,
        image_url=image_url,
        keyframe_urls=keyframe_urls,
        duration_sec=duration_sec,
    )
    created = await create_kling_video_task_async(payload, settings=s, api_key=api_key)
    task_id = _extract_task_id(created)
    completed = await wait_for_kling_video_completion_async(task_id, settings=s, api_key=api_key)
    url = _extract_video_url(completed)
    meta = {"task_id": task_id, "provider": "kling", "mode": mode, "model": payload.get("model")}
    return url, meta
