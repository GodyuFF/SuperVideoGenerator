"""阿里云百炼 DashScope 生图客户端（文生图 + 图像编辑）。"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx

from core.llm.tools.image.settings import (
    ImageGenSettings,
    get_image_gen_settings,
)


class BailianImageGenerationError(RuntimeError):
    """百炼 API 生图调用失败。"""

    def __init__(
        self,
        message: str,
        *,
        http_status: int | None = None,
        error_code: str = "",
    ) -> None:
        self.http_status = http_status
        self.error_code = error_code
        super().__init__(message)


def _base_url(workspace_id: str) -> str:
    """构建百炼 API base URL。"""
    wid = workspace_id.strip()
    if not wid:
        raise BailianImageGenerationError("百炼 Workspace ID 未配置")
    return f"https://{wid}.cn-beijing.maas.aliyuncs.com"


def _auth_headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def _resolve_api_key(settings: ImageGenSettings) -> str:
    key = (settings.api_key or "").strip()
    if not key:
        import os

        key = os.getenv("DASHSCOPE_API_KEY", "").strip()
    if not key:
        raise BailianImageGenerationError("未配置百炼 API Key（DASHSCOPE_API_KEY 或 SVG_IMAGE_GEN_API_KEY）")
    return key


def _resolve_workspace_id(settings: ImageGenSettings) -> str:
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
    """"1024x768" → "1024*768"。"""
    return size_str.replace("x", "*")


async def bailian_txt2img(
    prompt: str,
    *,
    settings: ImageGenSettings | None = None,
    size: str | None = None,
    negative_prompt: str = "",
    timeout: float = 180.0,
) -> str:
    """百炼文生图（异步提交 + 轮询），返回图片 URL。"""
    s = settings or get_image_gen_settings()
    api_key = _resolve_api_key(s)
    workspace_id = _resolve_workspace_id(s)
    model = s.bailian_txt2img_model or "wanx2.5-t2i-turbo"

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

    # Step 1: 提交异步任务
    try:
        async with httpx.AsyncClient(timeout=t) as client:
            resp = await client.post(url, headers=headers, json=payload)
    except httpx.HTTPError as e:
        raise BailianImageGenerationError(f"百炼网络错误：{e}") from e

    if resp.status_code >= 400:
        detail = resp.text[:1000]
        raise BailianImageGenerationError(
            f"百炼文生图提交失败 {resp.status_code}: {detail}",
            http_status=resp.status_code,
        )

    try:
        body = resp.json()
    except ValueError as e:
        raise BailianImageGenerationError("百炼响应不是有效 JSON") from e

    task_id = body.get("output", {}).get("task_id", "")
    if not task_id:
        raise BailianImageGenerationError(f"百炼未返回 task_id: {body}")

    # Step 2: 轮询结果
    task_url = f"{_base_url(workspace_id)}/api/v1/tasks/{task_id}"
    poll_interval = 1.5
    deadline = time.monotonic() + t

    while time.monotonic() < deadline:
        await asyncio.sleep(poll_interval)
        poll_interval = min(poll_interval * 1.2, 5.0)  # 退避

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                task_resp = await client.get(task_url, headers=_auth_headers(api_key))
        except httpx.HTTPError:
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

        # 未知状态，继续等待
        continue

    raise BailianImageGenerationError(f"百炼文生图任务超时（{t:.0f}s），task_id: {task_id}")


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

    try:
        async with httpx.AsyncClient(timeout=t) as client:
            resp = await client.post(url, headers=_auth_headers(api_key), json=payload)
    except httpx.HTTPError as e:
        raise BailianImageGenerationError(f"百炼网络错误：{e}") from e

    if resp.status_code >= 400:
        detail = resp.text[:1000]
        raise BailianImageGenerationError(
            f"百炼图像编辑失败 {resp.status_code}: {detail}",
            http_status=resp.status_code,
        )

    try:
        body = resp.json()
    except ValueError as e:
        raise BailianImageGenerationError("百炼响应不是有效 JSON") from e

    # 解析响应
    choices = body.get("output", {}).get("choices", [])
    if choices and isinstance(choices, list):
        msg = choices[0].get("message", {})
        contents = msg.get("content", [])
        if contents and isinstance(contents, list):
            img_url = str(contents[0].get("image", "")).strip()
            if img_url:
                return img_url

    raise BailianImageGenerationError(f"百炼图像编辑未返回图片: {body}")
