"""OpenAI Images API 生图客户端（GPT Image / DALL·E 兼容）。"""

from __future__ import annotations

import json
from typing import Any

import httpx

from core.llm.tools.image.errors import parse_agnes_api_error_body
from core.llm.tools.image.settings import ImageGenSettings, get_image_gen_settings

DEFAULT_OPENAI_IMAGE_MODEL = "gpt-image-1"
DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"


class OpenAIImageGenerationError(RuntimeError):
    """OpenAI 生图 API 调用失败。"""

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
    """从 OpenAI Images 响应提取图片 URL 或 base64 data URL。"""
    items = data.get("data")
    if not isinstance(items, list) or not items:
        raise OpenAIImageGenerationError("OpenAI 响应缺少 data 数组")
    first = items[0]
    if not isinstance(first, dict):
        raise OpenAIImageGenerationError("OpenAI 响应 data[0] 无效")
    url = str(first.get("url") or "").strip()
    if url:
        return url
    b64 = str(first.get("b64_json") or "").strip()
    if b64:
        return f"data:image/png;base64,{b64}"
    raise OpenAIImageGenerationError("OpenAI 响应未包含 url 或 b64_json")


def resolved_openai_image_api_key(
    settings: ImageGenSettings | None = None,
    explicit_key: str | None = None,
) -> str:
    """解析 OpenAI 生图 API Key。"""
    if explicit_key and explicit_key.strip():
        return explicit_key.strip()
    s = settings or get_image_gen_settings()
    if s.api_key and s.api_key.strip():
        return s.api_key.strip()
    import os

    for env_name in ("SVG_IMAGE_GEN_API_KEY", "OPENAI_API_KEY"):
        val = os.getenv(env_name, "").strip()
        if val:
            return val
    return ""


async def _post_openai_image(
    payload: dict[str, Any],
    *,
    settings: ImageGenSettings,
    api_key: str,
) -> str:
    """发送 OpenAI Images 请求并返回图片 URL。"""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    url = _images_url(settings.base_url or DEFAULT_OPENAI_BASE_URL)
    from core.interaction_log.media_log import logged_media_request

    try:
        resp = await logged_media_request(
            media_kind="image",
            provider="openai",
            model=str(payload.get("model") or ""),
            method="POST",
            url=url,
            headers=headers,
            json_body=payload,
            timeout=settings.timeout_sec,
            trust_env=settings.trust_env,
            phase="create",
        )
    except httpx.HTTPError as e:
        raise OpenAIImageGenerationError(f"OpenAI 网络错误：{e}") from e

    if resp.status_code >= 400:
        body = resp.text[:2000]
        parsed = parse_agnes_api_error_body(resp.status_code, body)
        raise OpenAIImageGenerationError(
            f"OpenAI API 错误 {resp.status_code}: {parsed['message']}",
            http_status=resp.status_code,
            error_code=parsed["error_code"],
            error_type=parsed["error_type"],
            param=parsed["param"],
            api_message=parsed["message"],
        )

    try:
        body = resp.json()
    except ValueError as e:
        raise OpenAIImageGenerationError("OpenAI 响应不是有效 JSON") from e
    if not isinstance(body, dict):
        raise OpenAIImageGenerationError("OpenAI 响应格式无效")
    return _extract_image_url(body)


async def openai_txt2img(
    prompt: str,
    *,
    settings: ImageGenSettings | None = None,
    size: str | None = None,
    api_key: str | None = None,
) -> str:
    """OpenAI 文生图。"""
    s = settings or get_image_gen_settings()
    key = resolved_openai_image_api_key(s, api_key)
    if not key:
        raise OpenAIImageGenerationError(
            "未配置 OpenAI 生图 API Key（SVG_IMAGE_GEN_API_KEY 或 OPENAI_API_KEY）"
        )
    text = prompt.strip()
    if not text:
        raise OpenAIImageGenerationError("生图 prompt 不能为空")

    payload: dict[str, Any] = {
        "model": s.model or DEFAULT_OPENAI_IMAGE_MODEL,
        "prompt": text,
        "size": size or s.default_size,
        "response_format": "url",
    }
    return await _post_openai_image(payload, settings=s, api_key=key)


async def openai_img2img(
    prompt: str,
    reference_urls: list[str],
    *,
    settings: ImageGenSettings | None = None,
    size: str | None = None,
    api_key: str | None = None,
) -> str:
    """OpenAI 图生图（使用 edits 端点，单张参考图）。"""
    s = settings or get_image_gen_settings()
    if not s.reference_enabled:
        raise OpenAIImageGenerationError("reference 生图未启用")
    key = resolved_openai_image_api_key(s, api_key)
    if not key:
        raise OpenAIImageGenerationError("未配置 OpenAI 生图 API Key")
    refs = [u.strip() for u in reference_urls if str(u).strip()]
    if not refs:
        raise OpenAIImageGenerationError("reference 图片 URL 不能为空")

    # OpenAI edits API 需要下载参考图；此处复用 images/generations 带 image 参数（兼容网关）
    model = (s.img2img_model or s.reference_model or s.model or DEFAULT_OPENAI_IMAGE_MODEL).strip()
    payload: dict[str, Any] = {
        "model": model,
        "prompt": prompt.strip(),
        "size": size or s.default_size,
        "response_format": "url",
        "image": refs[0] if len(refs) == 1 else refs,
    }
    return await _post_openai_image(payload, settings=s, api_key=key)


def build_openai_image_payload_preview(prompt: str, settings: ImageGenSettings) -> dict[str, Any]:
    """构建 OpenAI 生图 payload 预览（测试用）。"""
    return {
        "model": settings.model or DEFAULT_OPENAI_IMAGE_MODEL,
        "prompt": prompt.strip(),
        "size": settings.default_size,
        "response_format": "url",
    }
