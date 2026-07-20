"""Agnes Video V2.0 异步视频生成客户端。"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Literal

import httpx

from core.llm.tools.video.settings import VideoGenSettings, get_video_gen_manager

logger = logging.getLogger("core.llm.tools.video.agnes_client")

VideoGenMode = Literal["text2video", "img2video", "keyframes"]

KEYFRAMES_MODE_MARKER = "svf:keyframes"

# Free/默认套餐 video status RPM 极低；≥15s 轮询并串行查询以避免 429
_DEFAULT_POLL_INTERVAL_SEC = 15.0
_MIN_POLL_INTERVAL_SEC = 5.0
_MAX_POLL_BACKOFF_SEC = 120.0
_MAX_CREATE_BACKOFF_SEC = 180.0
_DEFAULT_CREATE_MIN_INTERVAL_SEC = 60.0
_status_query_lock = asyncio.Lock()
_create_lock = asyncio.Lock()
_last_create_mono: float = 0.0


class AgnesVideoGenerationError(RuntimeError):
    """Agnes 视频 API 调用失败。"""

    def __init__(
        self,
        message: str,
        *,
        http_status: int | None = None,
        api_message: str = "",
        retry_after_sec: float | None = None,
    ) -> None:
        self.http_status = http_status
        self.api_message = api_message or message
        self.retry_after_sec = retry_after_sec
        super().__init__(message)


def _api_root(base_url: str) -> str:
    """从 /v1 base 推导 API 根域名（轮询 agnesapi 用）。"""
    root = base_url.rstrip("/")
    if root.endswith("/v1"):
        return root[:-3]
    return root


def _videos_create_url(base_url: str) -> str:
    root = base_url.rstrip("/")
    if root.endswith("/v1"):
        return f"{root}/videos"
    return f"{root}/v1/videos"


def _parse_retry_after_sec(resp: httpx.Response) -> float | None:
    """解析 Retry-After 头（秒）；无效则返回 None。"""
    raw = resp.headers.get("Retry-After") or resp.headers.get("retry-after")
    if not raw:
        return None
    try:
        return max(1.0, float(str(raw).strip()))
    except (TypeError, ValueError):
        return None


def _backoff_wait_sec(
    *,
    attempt: int,
    base_sec: float,
    retry_after_sec: float | None = None,
) -> float:
    """计算 429 退避等待秒数（优先 Retry-After，否则指数退避，封顶）。"""
    if retry_after_sec is not None and retry_after_sec > 0:
        return min(_MAX_POLL_BACKOFF_SEC, float(retry_after_sec))
    exp = min(max(0, attempt), 3)
    return min(_MAX_POLL_BACKOFF_SEC, max(_MIN_POLL_INTERVAL_SEC, base_sec * (2**exp)))


def resolve_poll_interval_sec(settings: VideoGenSettings | None = None) -> float:
    """解析状态轮询间隔（下限 5s，默认 15s）。"""
    s = settings or get_video_gen_manager().get_settings()
    raw = getattr(s, "poll_interval_sec", None)
    try:
        val = float(raw if raw is not None else _DEFAULT_POLL_INTERVAL_SEC)
    except (TypeError, ValueError):
        val = _DEFAULT_POLL_INTERVAL_SEC
    return max(_MIN_POLL_INTERVAL_SEC, val)


def resolve_create_min_interval_sec(settings: VideoGenSettings | None = None) -> float:
    """解析两次视频创建的最小间隔（秒）；≤0 表示不主动限流。"""
    s = settings or get_video_gen_manager().get_settings()
    raw = getattr(s, "create_min_interval_sec", None)
    try:
        val = float(raw if raw is not None else _DEFAULT_CREATE_MIN_INTERVAL_SEC)
    except (TypeError, ValueError):
        val = _DEFAULT_CREATE_MIN_INTERVAL_SEC
    return max(0.0, val)


def _create_retry_wait_sec(
    resp: httpx.Response,
    *,
    attempt: int,
    base_sec: float,
) -> float:
    """创建接口 429 的等待秒数（Retry-After / 文案「1 minute」/ 指数退避）。"""
    ra = _parse_retry_after_sec(resp)
    if ra is not None:
        return min(_MAX_CREATE_BACKOFF_SEC, ra)
    body = (resp.text or "").lower()
    if "1 minute" in body or "per 1 minute" in body or "requests per 1 minute" in body:
        return min(_MAX_CREATE_BACKOFF_SEC, max(60.0, base_sec))
    wait = _backoff_wait_sec(attempt=attempt, base_sec=max(60.0, base_sec))
    return min(_MAX_CREATE_BACKOFF_SEC, wait)


async def _wait_create_spacing(min_interval_sec: float) -> None:
    """距上次创建不足间隔时主动等待（全进程串行）。"""
    global _last_create_mono
    if min_interval_sec <= 0:
        return
    now = time.monotonic()
    wait = _last_create_mono + min_interval_sec - now
    if wait > 0:
        logger.info(
            "Agnes 视频创建间隔限流：等待 %.1fs（套餐约 1 次/分钟）",
            wait,
        )
        await asyncio.sleep(wait)


def _mark_create_attempt() -> None:
    """记录一次创建请求时刻，供后续间隔限流。"""
    global _last_create_mono
    _last_create_mono = time.monotonic()


def reset_create_rate_limiter() -> None:
    """测试用：清空创建时间戳。"""
    global _last_create_mono
    _last_create_mono = 0.0


def normalize_num_frames(target_sec: float, frame_rate: float = 24) -> int:
    """将目标秒数映射为 Agnes 要求的 8n+1 帧数（≤441）。"""
    raw = int(max(1.0, target_sec) * frame_rate)
    raw = min(441, max(9, raw))
    n = max(0, round((raw - 1) / 8))
    frames = 8 * n + 1
    return min(441, max(9, frames))


def resolution_to_size(resolution: str) -> tuple[int, int]:
    """将配置档位映射为 width×height（16:9）。"""
    key = (resolution or "720p").strip().lower()
    if key in ("1080p", "1920x1080"):
        return 1920, 1080
    if key in ("480p", "768x480"):
        return 768, 480
    return 1152, 768


def build_video_create_payload(
    *,
    prompt: str,
    settings: VideoGenSettings,
    mode: VideoGenMode,
    image_url: str | None = None,
    keyframe_urls: list[str] | None = None,
    duration_sec: float | None = None,
    frame_rate: float = 24,
    negative_prompt: str = "",
) -> dict[str, Any]:
    """组装 POST /v1/videos 请求体。"""
    width, height = resolution_to_size(settings.resolution)
    dur = duration_sec if duration_sec is not None else float(settings.max_duration_sec or 5)
    dur = max(1.0, min(dur, float(settings.max_duration_sec or 18)))
    num_frames = normalize_num_frames(dur, frame_rate)

    payload: dict[str, Any] = {
        "model": settings.model or "agnes-video-v2.0",
        "prompt": prompt.strip(),
        "height": height,
        "width": width,
        "num_frames": num_frames,
        "frame_rate": frame_rate,
    }
    if negative_prompt.strip():
        payload["negative_prompt"] = negative_prompt.strip()

    if mode == "img2video" and image_url:
        payload["image"] = image_url.strip()
    elif mode == "keyframes" and keyframe_urls:
        urls = [u.strip() for u in keyframe_urls if u and u.strip()]
        if len(urls) < 2:
            raise AgnesVideoGenerationError("关键帧模式至少需要 2 张可访问图片 URL")
        payload["extra_body"] = {"image": urls, "mode": "keyframes"}
    return payload


async def create_video_task_async(
    payload: dict[str, Any],
    *,
    settings: VideoGenSettings | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    """创建异步视频生成任务；全进程串行 + 最小间隔，遇 429 退避重试。"""
    mgr = get_video_gen_manager()
    s = settings or mgr.get_settings()
    key = (api_key or mgr.resolved_api_key() or "").strip()
    if not key:
        raise AgnesVideoGenerationError(
            "未配置 Agnes 视频 API Key（SVG_VIDEO_GEN_API_KEY 或 AGNES_API_KEY）"
        )
    url = _videos_create_url(s.base_url)
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    min_interval = resolve_create_min_interval_sec(s)
    try:
        max_attempts = max(1, int(getattr(s, "create_max_attempts", 4) or 4))
    except (TypeError, ValueError):
        max_attempts = 4

    last_error: AgnesVideoGenerationError | None = None
    async with _create_lock:
        for attempt in range(max_attempts):
            await _wait_create_spacing(min_interval)
            try:
                async with httpx.AsyncClient(timeout=60.0, trust_env=s.trust_env) as client:
                    resp = await client.post(url, headers=headers, json=payload)
            except httpx.HTTPError as e:
                raise AgnesVideoGenerationError(f"Agnes 视频网络错误：{e}") from e
            finally:
                _mark_create_attempt()

            if resp.status_code == 429:
                body = resp.text[:2000]
                wait = _create_retry_wait_sec(
                    resp,
                    attempt=attempt,
                    base_sec=max(60.0, min_interval or 60.0),
                )
                last_error = AgnesVideoGenerationError(
                    f"Agnes 视频创建失败 {resp.status_code}: {body}",
                    http_status=429,
                    api_message=body,
                    retry_after_sec=wait,
                )
                if attempt + 1 >= max_attempts:
                    break
                logger.warning(
                    "Agnes 视频创建 429，%.1fs 后重试（%s/%s）",
                    wait,
                    attempt + 1,
                    max_attempts,
                )
                await asyncio.sleep(wait)
                continue

            if resp.status_code >= 400:
                body = resp.text[:2000]
                raise AgnesVideoGenerationError(
                    f"Agnes 视频创建失败 {resp.status_code}: {body}",
                    http_status=resp.status_code,
                    api_message=body,
                    retry_after_sec=_parse_retry_after_sec(resp),
                )
            try:
                data = resp.json()
            except ValueError as e:
                raise AgnesVideoGenerationError("Agnes 视频创建响应不是有效 JSON") from e
            if not isinstance(data, dict):
                raise AgnesVideoGenerationError("Agnes 视频创建响应格式无效")
            return data

    if last_error:
        raise last_error
    raise AgnesVideoGenerationError("Agnes 视频创建失败：未知错误")


async def fetch_video_task_async(
    *,
    video_id: str | None = None,
    task_id: str | None = None,
    settings: VideoGenSettings | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    """查询视频任务状态（优先 video_id）；全进程串行以免叠压状态查询 RPM。"""
    mgr = get_video_gen_manager()
    s = settings or mgr.get_settings()
    key = (api_key or mgr.resolved_api_key() or "").strip()
    if not key:
        raise AgnesVideoGenerationError("未配置 Agnes 视频 API Key")

    root = _api_root(s.base_url)
    if video_id:
        url = f"{root}/agnesapi"
        params = {"video_id": video_id, "model_name": s.model or "agnes-video-v2.0"}
    elif task_id:
        url = f"{s.base_url.rstrip('/')}/videos/{task_id}"
        params = None
    else:
        raise AgnesVideoGenerationError("缺少 video_id 或 task_id")

    headers = {"Authorization": f"Bearer {key}"}
    async with _status_query_lock:
        try:
            async with httpx.AsyncClient(timeout=60.0, trust_env=s.trust_env) as client:
                resp = await client.get(url, headers=headers, params=params)
        except httpx.HTTPError as e:
            raise AgnesVideoGenerationError(f"Agnes 视频查询网络错误：{e}") from e

        if resp.status_code >= 400:
            body = resp.text[:2000]
            raise AgnesVideoGenerationError(
                f"Agnes 视频查询失败 {resp.status_code}: {body}",
                http_status=resp.status_code,
                api_message=body,
                retry_after_sec=_parse_retry_after_sec(resp),
            )
        try:
            data = resp.json()
        except ValueError as e:
            raise AgnesVideoGenerationError("Agnes 视频查询响应不是有效 JSON") from e
        if not isinstance(data, dict):
            raise AgnesVideoGenerationError("Agnes 视频查询响应格式无效")
        return data


async def wait_for_video_completion_async(
    *,
    video_id: str | None = None,
    task_id: str | None = None,
    settings: VideoGenSettings | None = None,
    api_key: str | None = None,
    poll_interval_sec: float | None = None,
) -> dict[str, Any]:
    """轮询直至 completed / failed 或超时；对 429 指数退避后继续等待。"""
    mgr = get_video_gen_manager()
    s = settings or mgr.get_settings()
    interval = (
        max(_MIN_POLL_INTERVAL_SEC, float(poll_interval_sec))
        if poll_interval_sec is not None
        else resolve_poll_interval_sec(s)
    )
    deadline = time.monotonic() + float(s.timeout_sec or 600.0)
    last: dict[str, Any] = {}
    rate_failures = 0

    while time.monotonic() < deadline:
        try:
            last = await fetch_video_task_async(
                video_id=video_id,
                task_id=task_id,
                settings=s,
                api_key=api_key,
            )
            rate_failures = 0
        except AgnesVideoGenerationError as e:
            if e.http_status == 429:
                wait = _backoff_wait_sec(
                    attempt=rate_failures,
                    base_sec=interval,
                    retry_after_sec=e.retry_after_sec,
                )
                rate_failures += 1
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                wait = min(wait, remaining)
                logger.warning(
                    "Agnes 视频状态查询 429，%.1fs 后重试（第 %s 次）",
                    wait,
                    rate_failures,
                )
                await asyncio.sleep(wait)
                continue
            raise

        status = str(last.get("status") or "").strip().lower()
        if status == "completed":
            url = str(last.get("url") or "").strip()
            if not url:
                raise AgnesVideoGenerationError("视频任务已完成但缺少 url")
            return last
        if status == "failed":
            err = last.get("error")
            msg = str(err) if err else "视频生成失败"
            raise AgnesVideoGenerationError(f"Agnes 视频生成失败：{msg}", api_message=msg)

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        await asyncio.sleep(min(interval, remaining))

    raise AgnesVideoGenerationError(
        f"视频生成超时（>{s.timeout_sec}s），最后状态：{last.get('status')}"
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
    """创建任务并等待完成，返回 (video_url, task_meta)。"""
    s = settings or get_video_gen_manager().get_settings()
    payload = build_video_create_payload(
        prompt=prompt,
        settings=s,
        mode=mode,
        image_url=image_url,
        keyframe_urls=keyframe_urls,
        duration_sec=duration_sec,
    )
    created = await create_video_task_async(payload, settings=s, api_key=api_key)
    video_id = str(created.get("video_id") or "").strip()
    task_id = str(created.get("task_id") or created.get("id") or "").strip()
    if not video_id and not task_id:
        raise AgnesVideoGenerationError("创建响应缺少 video_id / task_id")

    completed = await wait_for_video_completion_async(
        video_id=video_id or None,
        task_id=task_id if not video_id else None,
        settings=s,
        api_key=api_key,
    )
    url = str(completed.get("url") or "").strip()
    if not url:
        raise AgnesVideoGenerationError("完成响应缺少视频 url")
    return url, {**created, **completed}
