"""Agnes AI 文生图客户端（OpenAI 兼容 POST /v1/images/generations）。"""

from __future__ import annotations

import json
from typing import Any

import httpx

from core.llm.tools.image.errors import parse_agnes_api_error_body

from core.llm.tools.image.settings import (
    DEFAULT_AGNES_IMAGE_MODEL,
    ImageGenSettings,
    get_image_gen_settings,
    resolved_image_gen_api_key,
)


class AgnesImageGenerationError(RuntimeError):
    """Agnes 生图 API 调用失败。"""

    def __init__(
        self,
        message: str,
        *,
        http_status: int | None = None,
        error_code: str = "",
        error_type: str = "",
        param: str = "",
        api_message: str = "",
    ) -> None:
        self.http_status = http_status
        self.error_code = error_code
        self.error_type = error_type
        self.param = param
        self.api_message = api_message or message
        super().__init__(message)


def _images_url(base_url: str) -> str:
    return f"{base_url.rstrip('/')}/images/generations"


def _extract_image_url(data: dict[str, Any]) -> str:
    items = data.get("data")
    if not isinstance(items, list) or not items:
        raise AgnesImageGenerationError("Agnes 响应缺少 data 数组")
    first = items[0]
    if not isinstance(first, dict):
        raise AgnesImageGenerationError("Agnes 响应 data[0] 无效")
    url = str(first.get("url") or "").strip()
    if url:
        return url
    b64 = str(first.get("b64_json") or "").strip()
    if b64:
        return f"data:image/png;base64,{b64}"
    raise AgnesImageGenerationError("Agnes 响应未包含 url 或 b64_json")


async def generate_text_to_image_async(
    prompt: str,
    *,
    settings: ImageGenSettings | None = None,
    size: str | None = None,
    api_key: str | None = None,
) -> str:
    """异步调用 Agnes Image API 生成单张图片。"""
    s = settings or get_image_gen_settings()
    key = (api_key or resolved_image_gen_api_key(s) or "").strip()
    if not key:
        raise AgnesImageGenerationError(
            "未配置 Agnes 生图 API Key（SVG_IMAGE_GEN_API_KEY 或 AGNES_API_KEY）"
        )
    text = prompt.strip()
    if not text:
        raise AgnesImageGenerationError("生图 prompt 不能为空")

    payload: dict[str, Any] = {
        "model": s.model or DEFAULT_AGNES_IMAGE_MODEL,
        "prompt": text,
        "size": size or s.default_size,
        "extra_body": {"response_format": "url"},
    }
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    url = _images_url(s.base_url)
    try:
        async with httpx.AsyncClient(timeout=s.timeout_sec, trust_env=s.trust_env) as client:
            resp = await client.post(url, headers=headers, json=payload)
    except httpx.HTTPError as e:
        raise AgnesImageGenerationError(f"Agnes 网络错误：{e}") from e

    if resp.status_code >= 400:
        body = resp.text[:2000]
        parsed = parse_agnes_api_error_body(resp.status_code, body)
        raise AgnesImageGenerationError(
            f"Agnes API 错误 {resp.status_code}: {parsed['message']}",
            http_status=resp.status_code,
            error_code=parsed["error_code"],
            error_type=parsed["error_type"],
            param=parsed["param"],
            api_message=parsed["message"],
        )

    try:
        body = resp.json()
    except ValueError as e:
        raise AgnesImageGenerationError("Agnes 响应不是有效 JSON") from e
    if not isinstance(body, dict):
        raise AgnesImageGenerationError("Agnes 响应格式无效")
    return _extract_image_url(body)


async def generate_images_with_references_async(
    prompt: str,
    reference_urls: list[str],
    *,
    settings: ImageGenSettings | None = None,
    size: str | None = None,
    api_key: str | None = None,
) -> str:
    """多参考图图生图（Agnes Image 2.1+，`extra_body.image: [url...]`）。"""
    s = settings or get_image_gen_settings()
    if not s.reference_enabled:
        raise AgnesImageGenerationError(
            "reference 生图未启用（SVG_IMAGE_GEN_REFERENCE_ENABLED=false）"
        )
    key = (api_key or resolved_image_gen_api_key(s) or "").strip()
    if not key:
        raise AgnesImageGenerationError(
            "未配置 Agnes 生图 API Key（SVG_IMAGE_GEN_API_KEY 或 AGNES_API_KEY）"
        )
    text = prompt.strip()
    refs = [u.strip() for u in reference_urls if str(u).strip()]
    if not text:
        raise AgnesImageGenerationError("生图 prompt 不能为空")
    if not refs:
        raise AgnesImageGenerationError("reference 图片 URL 列表不能为空")

    model = (
        s.img2img_model or s.reference_model or s.model or DEFAULT_AGNES_IMAGE_MODEL
    ).strip()
    payload: dict[str, Any] = {
        "model": model,
        "prompt": text,
        "size": size or s.default_size,
        "extra_body": {"image": refs, "response_format": "url"},
    }
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    url = _images_url(s.base_url)
    try:
        async with httpx.AsyncClient(timeout=s.timeout_sec, trust_env=s.trust_env) as client:
            resp = await client.post(url, headers=headers, json=payload)
    except httpx.HTTPError as e:
        raise AgnesImageGenerationError(f"Agnes 网络错误：{e}") from e

    if resp.status_code >= 400:
        body = resp.text[:2000]
        parsed = parse_agnes_api_error_body(resp.status_code, body)
        raise AgnesImageGenerationError(
            f"Agnes 多参考图生图 API 错误 {resp.status_code}: {parsed['message']}",
            http_status=resp.status_code,
            error_code=parsed["error_code"],
            error_type=parsed["error_type"],
            param=parsed["param"],
            api_message=parsed["message"],
        )

    try:
        body = resp.json()
    except ValueError as e:
        raise AgnesImageGenerationError("Agnes 响应不是有效 JSON") from e
    if not isinstance(body, dict):
        raise AgnesImageGenerationError("Agnes 响应格式无效")
    return _extract_image_url(body)


async def generate_image_with_reference_async(
    prompt: str,
    reference_url: str,
    *,
    settings: ImageGenSettings | None = None,
    size: str | None = None,
    api_key: str | None = None,
) -> str:
    """单张 reference 图生图（薄封装，统一走 `extra_body.image` 数组）。"""
    return await generate_images_with_references_async(
        prompt,
        [reference_url],
        settings=settings,
        size=size,
        api_key=api_key,
    )


def generate_text_to_image(
    prompt: str,
    *,
    settings: ImageGenSettings | None = None,
    size: str | None = None,
    api_key: str | None = None,
) -> str:
    """同步包装（测试或非 async 上下文）。"""
    import asyncio

    return asyncio.run(
        generate_text_to_image_async(
            prompt, settings=settings, size=size, api_key=api_key
        )
    )
