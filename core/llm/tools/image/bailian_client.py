"""阿里云百炼 DashScope 生图客户端（文生图 + 图像编辑）。"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

from core.llm.tools.image.settings import (
    ImageGenSettings,
    get_image_gen_settings,
)

logger = logging.getLogger(__name__)

# 提交遇 429 时指数退避（秒），封顶后仍重试至 create_max_attempts
_CREATE_MAX_ATTEMPTS = 4
_CREATE_BACKOFF_BASE_SEC = 15.0
_CREATE_BACKOFF_MAX_SEC = 120.0


class BailianImageGenerationError(RuntimeError):
    """百炼 API 生图调用失败。"""

    def __init__(
        self,
        message: str,
        *,
        http_status: int | None = None,
        error_code: str = "",
        retry_after_sec: float | None = None,
    ) -> None:
        self.http_status = http_status
        self.error_code = error_code
        self.retry_after_sec = retry_after_sec
        super().__init__(message)


def _base_url(workspace_id: str) -> str:
    """构建百炼 API base URL。"""
    wid = workspace_id.strip()
    if not wid:
        raise BailianImageGenerationError("百炼 Workspace ID 未配置")
    return f"https://{wid}.cn-beijing.maas.aliyuncs.com"


def _auth_headers(api_key: str) -> dict[str, str]:
    """组装 Bearer 鉴权头。"""
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def _resolve_api_key(settings: ImageGenSettings) -> str:
    """解析百炼 API Key（设置优先，其次 DASHSCOPE_API_KEY）。"""
    key = (settings.api_key or "").strip()
    if not key:
        import os

        key = os.getenv("DASHSCOPE_API_KEY", "").strip()
    if not key:
        raise BailianImageGenerationError("未配置百炼 API Key（DASHSCOPE_API_KEY 或 SVG_IMAGE_GEN_API_KEY）")
    return key


def _resolve_workspace_id(settings: ImageGenSettings) -> str:
    """解析百炼 Workspace ID。"""
    wid = (settings.bailian_workspace_id or "").strip()
    if not wid:
        import os

        wid = os.getenv("SVG_IMAGE_GEN_BAILIAN_WORKSPACE_ID", "").strip()
    if not wid:
        raise BailianImageGenerationError(
            "未配置百炼 Workspace ID（SVG_IMAGE_GEN_BAILIAN_WORKSPACE_ID），"
            "请在百炼控制台 → 模型广场 → 模型详情中查看"
        )
    return wid


def _parse_size_for_bailian(size_str: str) -> str:
    """将「1024x768」转为百炼要求的「1024*768」。"""
    return size_str.replace("x", "*")


def _txt2img_uses_sync_multimodal(model: str) -> bool:
    """判断文生图是否应走同步 multimodal-generation。

    qwen-image*（尤其 2.0）与 wan2.6* 不支持 / 不推荐 HTTP 异步；
    对它们发送 X-DashScope-Async 会 403 AccessDenied
    （current user api does not support asynchronous calls）。
    文档：https://help.aliyun.com/zh/model-studio/qwen-image-api
    """
    m = (model or "").strip().lower()
    if m.startswith("qwen-image"):
        return True
    if m.startswith("wan2.6"):
        return True
    return False


def _extract_multimodal_image_url(body: dict[str, Any]) -> str:
    """从 multimodal-generation 同步响应对提取图片 URL。"""
    choices = body.get("output", {}).get("choices", [])
    if choices and isinstance(choices, list):
        msg = choices[0].get("message", {})
        contents = msg.get("content", [])
        if contents and isinstance(contents, list):
            img_url = str(contents[0].get("image", "")).strip()
            if img_url:
                return img_url
    return ""


def _parse_retry_after_sec(resp: httpx.Response) -> float | None:
    """从响应头解析 Retry-After（秒）。"""
    raw = resp.headers.get("Retry-After") or resp.headers.get("retry-after")
    if not raw:
        return None
    try:
        return max(0.0, float(raw.strip()))
    except (TypeError, ValueError):
        return None


def _extract_error_code(body_text: str) -> str:
    """从错误 JSON 抽取 code（如 Throttling.RateQuota）。"""
    text = (body_text or "").strip()
    if not text:
        return ""
    try:
        import json

        data = json.loads(text)
        if isinstance(data, dict):
            return str(data.get("code") or "").strip()
    except (ValueError, TypeError):
        pass
    return ""


def _create_backoff_wait_sec(
    *,
    attempt: int,
    resp: httpx.Response | None = None,
) -> float:
    """计算提交 429 等待秒数（优先 Retry-After，否则指数退避并封顶）。"""
    if resp is not None:
        ra = _parse_retry_after_sec(resp)
        if ra is not None and ra > 0:
            return min(_CREATE_BACKOFF_MAX_SEC, ra)
    exp = min(max(0, attempt), 3)
    return min(
        _CREATE_BACKOFF_MAX_SEC,
        _CREATE_BACKOFF_BASE_SEC * (2**exp),
    )


async def _post_with_rate_limit_retry(
    *,
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout: float,
    action_label: str,
    provider: str = "bailian",
    model: str = "",
    media_kind: str = "image",
    phase: str = "create",
) -> httpx.Response:
    """
    POST 百炼接口；遇 429 / RateQuota 指数退避后重试。

    其它 4xx/5xx 不在此重试，由调用方抛出。每次尝试写入交互日志。
    """
    from core.interaction_log.media_log import logged_media_request

    last_detail = ""
    last_code = ""
    for attempt in range(_CREATE_MAX_ATTEMPTS):
        try:
            resp = await logged_media_request(
                media_kind=media_kind,  # type: ignore[arg-type]
                provider=provider,
                model=model,
                method="POST",
                url=url,
                headers=headers,
                json_body=payload,
                timeout=timeout,
                trust_env=False,
                phase=phase,  # type: ignore[arg-type]
            )
        except httpx.HTTPError as e:
            raise BailianImageGenerationError(f"百炼网络错误：{e}") from e

        if resp.status_code != 429:
            return resp

        last_detail = resp.text[:1000]
        last_code = _extract_error_code(resp.text)
        wait = _create_backoff_wait_sec(attempt=attempt, resp=resp)
        if attempt + 1 >= _CREATE_MAX_ATTEMPTS:
            break
        logger.warning(
            "百炼%s 429（%s），%.1fs 后重试（%s/%s）",
            action_label,
            last_code or "rate_limit",
            wait,
            attempt + 1,
            _CREATE_MAX_ATTEMPTS,
        )
        await asyncio.sleep(wait)

    raise BailianImageGenerationError(
        f"百炼{action_label}提交失败 429: {last_detail}",
        http_status=429,
        error_code=last_code or "Throttling.RateQuota",
    )


async def _bailian_txt2img_sync_multimodal(
    prompt: str,
    *,
    s: ImageGenSettings,
    api_key: str,
    workspace_id: str,
    model: str,
    size: str | None,
    negative_prompt: str,
    timeout: float,
) -> str:
    """百炼文生图同步 multimodal-generation（qwen-image / wan2.6）。"""
    url = f"{_base_url(workspace_id)}/api/v1/services/aigc/multimodal-generation/generation"
    neg = (negative_prompt or s.sd_negative_prompt or "").strip() or " "
    payload: dict[str, Any] = {
        "model": model,
        "input": {
            "messages": [
                {"role": "user", "content": [{"text": prompt.strip()}]},
            ],
        },
        "parameters": {
            "n": 1,
            "size": _parse_size_for_bailian(size or s.default_size),
            "negative_prompt": neg,
            "prompt_extend": True,
            "watermark": False,
        },
    }
    t = timeout if timeout is not None else s.timeout_sec
    resp = await _post_with_rate_limit_retry(
        url=url,
        headers=_auth_headers(api_key),
        payload=payload,
        timeout=t,
        action_label="文生图",
        provider="bailian",
        model=model,
        media_kind="image",
        phase="create",
    )
    if resp.status_code >= 400:
        detail = resp.text[:1000]
        raise BailianImageGenerationError(
            f"百炼文生图提交失败 {resp.status_code}: {detail}",
            http_status=resp.status_code,
            error_code=_extract_error_code(resp.text),
        )
    try:
        body = resp.json()
    except ValueError as e:
        raise BailianImageGenerationError("百炼响应不是有效 JSON") from e
    img_url = _extract_multimodal_image_url(body)
    if img_url:
        return img_url
    raise BailianImageGenerationError(f"百炼文生图未返回图片: {body}")


async def _bailian_txt2img_async_synthesis(
    prompt: str,
    *,
    s: ImageGenSettings,
    api_key: str,
    workspace_id: str,
    model: str,
    size: str | None,
    negative_prompt: str,
    timeout: float,
) -> str:
    """百炼文生图异步 text2image（wanx / wan2.5 及以下）。"""
    url = f"{_base_url(workspace_id)}/api/v1/services/aigc/text2image/image-synthesis"
    payload: dict[str, Any] = {
        "model": model,
        "input": {
            "prompt": prompt.strip(),
            "negative_prompt": (negative_prompt or s.sd_negative_prompt or "").strip(),
        },
        "parameters": {
            "n": 1,
            "size": _parse_size_for_bailian(size or s.default_size),
        },
    }
    headers = {
        **_auth_headers(api_key),
        "X-DashScope-Async": "enable",
    }
    t = timeout if timeout is not None else s.timeout_sec

    resp = await _post_with_rate_limit_retry(
        url=url,
        headers=headers,
        payload=payload,
        timeout=t,
        action_label="文生图",
        provider="bailian",
        model=model,
        media_kind="image",
        phase="create",
    )

    if resp.status_code >= 400:
        detail = resp.text[:1000]
        raise BailianImageGenerationError(
            f"百炼文生图提交失败 {resp.status_code}: {detail}",
            http_status=resp.status_code,
            error_code=_extract_error_code(resp.text),
        )

    try:
        body = resp.json()
    except ValueError as e:
        raise BailianImageGenerationError("百炼响应不是有效 JSON") from e

    task_id = body.get("output", {}).get("task_id", "")
    if not task_id:
        raise BailianImageGenerationError(f"百炼未返回 task_id: {body}")

    task_url = f"{_base_url(workspace_id)}/api/v1/tasks/{task_id}"
    poll_interval = 1.5
    deadline = time.monotonic() + t

    while time.monotonic() < deadline:
        await asyncio.sleep(poll_interval)
        poll_interval = min(poll_interval * 1.2, 5.0)

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                task_resp = await client.get(task_url, headers=_auth_headers(api_key))
        except httpx.HTTPError:
            continue

        if task_resp.status_code == 429:
            wait = _create_backoff_wait_sec(attempt=0, resp=task_resp)
            logger.warning("百炼文生图轮询 429，%.1fs 后继续", wait)
            await asyncio.sleep(wait)
            continue

        if task_resp.status_code >= 400:
            continue

        try:
            task_body = task_resp.json()
        except ValueError:
            continue

        output = task_body.get("output", {})
        status = output.get("task_status", "")

        if status == "SUCCEEDED":
            results = output.get("results", [])
            if results and isinstance(results, list):
                img_url = str(results[0].get("url", "")).strip()
                if img_url:
                    return img_url
            raise BailianImageGenerationError("百炼任务成功但未返回图片 URL")

        if status == "FAILED":
            msg = output.get("message", "未知错误")
            raise BailianImageGenerationError(f"百炼文生图任务失败: {msg}")

        if status in ("PENDING", "RUNNING"):
            continue

        continue

    raise BailianImageGenerationError(f"百炼文生图任务超时（{t:.0f}s），task_id: {task_id}")


async def bailian_txt2img(
    prompt: str,
    *,
    settings: ImageGenSettings | None = None,
    size: str | None = None,
    negative_prompt: str = "",
    timeout: float = 180.0,
) -> str:
    """百炼文生图：按模型走同步 multimodal 或异步 synthesis，返回图片 URL。"""
    s = settings or get_image_gen_settings()
    api_key = _resolve_api_key(s)
    workspace_id = _resolve_workspace_id(s)
    model = s.bailian_txt2img_model or "qwen-image-2.0-pro"

    if _txt2img_uses_sync_multimodal(model):
        return await _bailian_txt2img_sync_multimodal(
            prompt,
            s=s,
            api_key=api_key,
            workspace_id=workspace_id,
            model=model,
            size=size,
            negative_prompt=negative_prompt,
            timeout=timeout,
        )
    return await _bailian_txt2img_async_synthesis(
        prompt,
        s=s,
        api_key=api_key,
        workspace_id=workspace_id,
        model=model,
        size=size,
        negative_prompt=negative_prompt,
        timeout=timeout,
    )


async def bailian_img2img(
    prompt: str,
    reference_urls: list[str],
    *,
    settings: ImageGenSettings | None = None,
    size: str | None = None,
    negative_prompt: str = "",
    timeout: float = 180.0,
) -> str:
    """百炼图像编辑（多图融合合成），返回图片 URL。

    用于 frame 合成：将场景+角色+道具等参考图融合为一张分镜画面。
    使用 qwen-image-2.0-pro 的 multimodal-generation 端点（同步）。
    """
    s = settings or get_image_gen_settings()
    api_key = _resolve_api_key(s)
    workspace_id = _resolve_workspace_id(s)
    model = s.bailian_img2img_model or "qwen-image-2.0-pro"

    url = f"{_base_url(workspace_id)}/api/v1/services/aigc/multimodal-generation/generation"

    # 构建 messages content
    content: list[dict[str, str]] = []
    for ref_url in reference_urls:
        url_str = str(ref_url).strip()
        if url_str:
            content.append({"image": url_str})
    content.append({"text": prompt.strip()})

    payload: dict[str, Any] = {
        "model": model,
        "input": {
            "messages": [{"role": "user", "content": content}],
        },
        "parameters": {
            "n": 1,
            "size": _parse_size_for_bailian(size or s.default_size),
            "negative_prompt": (negative_prompt or s.sd_negative_prompt or "").strip() or " ",
            "prompt_extend": True,
            "watermark": False,
        },
    }

    t = timeout if timeout is not None else s.timeout_sec

    resp = await _post_with_rate_limit_retry(
        url=url,
        headers=_auth_headers(api_key),
        payload=payload,
        timeout=t,
        action_label="图像编辑",
        provider="bailian",
        model=model,
        media_kind="image",
        phase="edit",
    )

    if resp.status_code >= 400:
        detail = resp.text[:1000]
        raise BailianImageGenerationError(
            f"百炼图像编辑失败 {resp.status_code}: {detail}",
            http_status=resp.status_code,
            error_code=_extract_error_code(resp.text),
        )

    try:
        body = resp.json()
    except ValueError as e:
        raise BailianImageGenerationError("百炼响应不是有效 JSON") from e

    img_url = _extract_multimodal_image_url(body)
    if img_url:
        return img_url
    raise BailianImageGenerationError(f"百炼图像编辑未返回图片: {body}")
