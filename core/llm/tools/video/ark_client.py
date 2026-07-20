"""火山方舟 SeedDance 视频生成客户端。"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Literal

import httpx

from core.llm.tools.video.agnes_client import VideoGenMode
from core.llm.tools.video.settings import VideoGenSettings, get_video_gen_manager
from core.llm.tools.volcengine.ark_common import (
    DEFAULT_ARK_BASE_URL,
    DEFAULT_SEEDANCE_MODEL,
    ark_auth_headers,
    normalize_ark_base_url,
    resolve_ark_api_key,
)


class ArkVideoGenerationError(RuntimeError):
    """火山方舟 SeedDance 视频生成失败。"""

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


def _tasks_url(base_url: str, task_id: str = "") -> str:
    """返回视频任务创建/查询 endpoint。"""
    root = normalize_ark_base_url(base_url)
    if task_id:
        return f"{root}/contents/generations/tasks/{task_id.strip()}"
    return f"{root}/contents/generations/tasks"


def _normalize_resolution(resolution: str) -> str:
    """将配置分辨率映射为 SeedDance 档位。"""
    key = str(resolution or "720p").strip().lower()
    if key in ("1080p", "1920x1080"):
        return "1080p"
    if key in ("480p", "768x480"):
        return "480p"
    return "720p"


def _normalize_duration(duration_sec: float | None, settings: VideoGenSettings) -> int:
    """SeedDance 时长 4–15 秒整数。"""
    raw = duration_sec if duration_sec is not None else float(settings.max_duration_sec or 5)
    return max(4, min(15, int(round(raw))))


def build_ark_video_payload(
    *,
    prompt: str,
    settings: VideoGenSettings,
    mode: VideoGenMode,
    image_url: str | None = None,
    keyframe_urls: list[str] | None = None,
    duration_sec: float | None = None,
    ratio: str = "16:9",
) -> dict[str, Any]:
    """组装 SeedDance 创建任务请求体。"""
    content: list[dict[str, Any]] = [{"type": "text", "text": prompt.strip()}]
    if mode == "img2video" and image_url:
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": image_url.strip()},
                "role": "first_frame",
            }
        )
    elif mode == "keyframes" and keyframe_urls:
        urls = [u.strip() for u in keyframe_urls if u and u.strip()]
        if len(urls) < 2:
            raise ArkVideoGenerationError("首尾帧模式至少需要 2 张可访问图片 URL")
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": urls[0]},
                "role": "first_frame",
            }
        )
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": urls[1]},
                "role": "last_frame",
            }
        )
    return {
        "model": settings.model or DEFAULT_SEEDANCE_MODEL,
        "content": content,
        "resolution": _normalize_resolution(settings.resolution),
        "ratio": ratio,
        "duration": _normalize_duration(duration_sec, settings),
        "generate_audio": True,
        "watermark": False,
    }


def _extract_task_id(data: dict[str, Any]) -> str:
    """从创建任务响应提取 task_id。"""
    for key in ("id", "task_id"):
        val = str(data.get(key) or "").strip()
        if val:
            return val
    raise ArkVideoGenerationError("SeedDance 创建响应缺少 task id")


def _extract_task_status(data: dict[str, Any]) -> str:
    """读取任务状态字段。"""
    return str(data.get("status") or data.get("task_status") or "").strip().lower()


def _extract_video_url(data: dict[str, Any]) -> str:
    """从完成任务响应提取 video_url。"""
    content = data.get("content")
    if isinstance(content, dict):
        url = str(content.get("video_url") or content.get("url") or "").strip()
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
    raise ArkVideoGenerationError("SeedDance 完成响应缺少 video_url")


async def create_ark_video_task_async(
    payload: dict[str, Any],
    *,
    settings: VideoGenSettings | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    """创建 SeedDance 异步视频任务。"""
    mgr = get_video_gen_manager()
    s = settings or mgr.get_settings()
    try:
        key = resolve_ark_api_key(
            api_key or s.api_key,
            env_names=("SVG_VIDEO_GEN_API_KEY", "ARK_API_KEY"),
        )
    except ValueError as e:
        raise ArkVideoGenerationError(str(e)) from e
    url = _tasks_url(s.base_url or DEFAULT_ARK_BASE_URL)
    try:
        async with httpx.AsyncClient(timeout=60.0, trust_env=s.trust_env) as client:
            resp = await client.post(url, headers=ark_auth_headers(key), json=payload)
    except httpx.HTTPError as e:
        raise ArkVideoGenerationError(f"SeedDance 网络错误：{e}") from e
    if resp.status_code >= 400:
        body = resp.text[:2000]
        raise ArkVideoGenerationError(
            f"SeedDance 创建失败 {resp.status_code}: {body}",
            http_status=resp.status_code,
            api_message=body,
        )
    try:
        data = resp.json()
    except ValueError as e:
        raise ArkVideoGenerationError("SeedDance 创建响应不是有效 JSON") from e
    if not isinstance(data, dict):
        raise ArkVideoGenerationError("SeedDance 创建响应格式无效")
    return data


async def fetch_ark_video_task_async(
    task_id: str,
    *,
    settings: VideoGenSettings | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    """查询 SeedDance 视频任务状态。"""
    mgr = get_video_gen_manager()
    s = settings or mgr.get_settings()
    try:
        key = resolve_ark_api_key(
            api_key or s.api_key,
            env_names=("SVG_VIDEO_GEN_API_KEY", "ARK_API_KEY"),
        )
    except ValueError as e:
        raise ArkVideoGenerationError(str(e)) from e
    url = _tasks_url(s.base_url or DEFAULT_ARK_BASE_URL, task_id)
    try:
        async with httpx.AsyncClient(timeout=60.0, trust_env=s.trust_env) as client:
            resp = await client.get(url, headers=ark_auth_headers(key))
    except httpx.HTTPError as e:
        raise ArkVideoGenerationError(f"SeedDance 查询网络错误：{e}") from e
    if resp.status_code >= 400:
        body = resp.text[:2000]
        raise ArkVideoGenerationError(
            f"SeedDance 查询失败 {resp.status_code}: {body}",
            http_status=resp.status_code,
            api_message=body,
        )
    try:
        data = resp.json()
    except ValueError as e:
        raise ArkVideoGenerationError("SeedDance 查询响应不是有效 JSON") from e
    if not isinstance(data, dict):
        raise ArkVideoGenerationError("SeedDance 查询响应格式无效")
    return data


async def wait_for_ark_video_completion_async(
    task_id: str,
    *,
    settings: VideoGenSettings | None = None,
    api_key: str | None = None,
    poll_interval_sec: float = 3.0,
) -> dict[str, Any]:
    """轮询 SeedDance 任务直至成功或失败。"""
    mgr = get_video_gen_manager()
    s = settings or mgr.get_settings()
    deadline = time.monotonic() + float(s.timeout_sec or 300.0)
    last: dict[str, Any] = {}
    success_states = {"succeeded", "success", "completed", "done"}
    fail_states = {"failed", "error", "cancelled", "canceled"}

    while time.monotonic() < deadline:
        last = await fetch_ark_video_task_async(task_id, settings=s, api_key=api_key)
        status = _extract_task_status(last)
        if status in success_states:
            video_url = _extract_video_url(last)
            last["video_url"] = video_url
            last["url"] = video_url
            return last
        if status in fail_states:
            err = last.get("error") or last.get("message") or "视频生成失败"
            raise ArkVideoGenerationError(f"SeedDance 生成失败：{err}", api_message=str(err))
        await asyncio.sleep(poll_interval_sec)

    raise ArkVideoGenerationError(
        f"SeedDance 生成超时（>{s.timeout_sec}s），最后状态：{_extract_task_status(last)}"
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
    """创建 SeedDance 任务并等待完成，返回 (video_url, task_meta)。"""
    s = settings or get_video_gen_manager().get_settings()
    payload = build_ark_video_payload(
        prompt=prompt,
        settings=s,
        mode=mode,
        image_url=image_url,
        keyframe_urls=keyframe_urls,
        duration_sec=duration_sec,
    )
    created = await create_ark_video_task_async(payload, settings=s, api_key=api_key)
    task_id = _extract_task_id(created)
    completed = await wait_for_ark_video_completion_async(
        task_id,
        settings=s,
        api_key=api_key,
    )
    url = _extract_video_url(completed)
    meta = {
        **created,
        **completed,
        "task_id": task_id,
        "provider": "volcengine",
    }
    return url, meta
