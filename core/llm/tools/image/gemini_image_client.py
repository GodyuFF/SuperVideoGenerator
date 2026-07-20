"""Google Gemini 生图客户端。"""

from __future__ import annotations

import base64
import os
from typing import Any

import httpx

from core.llm.tools.image.settings import ImageGenSettings, get_image_gen_settings

DEFAULT_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_GEMINI_IMAGE_MODEL = "gemini-2.0-flash-preview-image-generation"


class GeminiImageGenerationError(RuntimeError):
    """Gemini 生图 API 调用失败。"""

    def __init__(
        self,
        message: str,
        *,
        http_status: int | None = None,
    ) -> None:
        self.http_status = http_status
        super().__init__(message)


def resolved_gemini_api_key(
    settings: ImageGenSettings | None = None,
    explicit_key: str | None = None,
) -> str:
    """解析 Gemini API Key。"""
    if explicit_key and explicit_key.strip():
        return explicit_key.strip()
    s = settings or get_image_gen_settings()
    if s.api_key and s.api_key.strip():
        return s.api_key.strip()
    for env_name in ("SVG_IMAGE_GEN_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"):
        val = os.getenv(env_name, "").strip()
        if val:
            return val
    return ""


def _gemini_generate_url(base_url: str, model: str, api_key: str) -> str:
    root = (base_url or DEFAULT_GEMINI_BASE_URL).rstrip("/")
    model_id = (model or DEFAULT_GEMINI_IMAGE_MODEL).strip()
    return f"{root}/models/{model_id}:generateContent?key={api_key}"


def _extract_gemini_image(data: dict[str, Any]) -> str:
    """从 Gemini generateContent 响应提取 base64 图片。"""
    candidates = data.get("candidates")
    if not isinstance(candidates, list):
        raise GeminiImageGenerationError("Gemini 响应缺少 candidates")
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        content = candidate.get("content") or {}
        parts = content.get("parts") or []
        if not isinstance(parts, list):
            continue
        for part in parts:
            if not isinstance(part, dict):
                continue
            inline = part.get("inlineData") or part.get("inline_data")
            if isinstance(inline, dict):
                b64 = str(inline.get("data") or "").strip()
                mime = str(inline.get("mimeType") or inline.get("mime_type") or "image/png")
                if b64:
                    return f"data:{mime};base64,{b64}"
    raise GeminiImageGenerationError("Gemini 响应未包含 inlineData 图片")


async def gemini_txt2img(
    prompt: str,
    *,
    settings: ImageGenSettings | None = None,
    api_key: str | None = None,
) -> str:
    """Gemini 文生图。"""
    s = settings or get_image_gen_settings()
    key = resolved_gemini_api_key(s, api_key)
    if not key:
        raise GeminiImageGenerationError(
            "未配置 Gemini API Key（SVG_IMAGE_GEN_API_KEY 或 GEMINI_API_KEY）"
        )
    text = prompt.strip()
    if not text:
        raise GeminiImageGenerationError("生图 prompt 不能为空")

    payload: dict[str, Any] = {
        "contents": [{"parts": [{"text": text}]}],
        "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
    }
    url = _gemini_generate_url(s.base_url, s.model, key)
    try:
        async with httpx.AsyncClient(timeout=s.timeout_sec, trust_env=s.trust_env) as client:
            resp = await client.post(url, json=payload)
    except httpx.HTTPError as e:
        raise GeminiImageGenerationError(f"Gemini 网络错误：{e}") from e

    if resp.status_code >= 400:
        raise GeminiImageGenerationError(
            f"Gemini API 错误 {resp.status_code}: {resp.text[:500]}",
            http_status=resp.status_code,
        )

    try:
        body = resp.json()
    except ValueError as e:
        raise GeminiImageGenerationError("Gemini 响应不是有效 JSON") from e
    if not isinstance(body, dict):
        raise GeminiImageGenerationError("Gemini 响应格式无效")
    return _extract_gemini_image(body)


async def gemini_img2img(
    prompt: str,
    reference_urls: list[str],
    *,
    settings: ImageGenSettings | None = None,
    api_key: str | None = None,
) -> str:
    """Gemini 图生图（首张参考图作为 inline 输入）。"""
    s = settings or get_image_gen_settings()
    if not s.reference_enabled:
        raise GeminiImageGenerationError("reference 生图未启用")
    refs = [u.strip() for u in reference_urls if str(u).strip()]
    if not refs:
        raise GeminiImageGenerationError("reference 图片 URL 不能为空")

    key = resolved_gemini_api_key(s, api_key)
    if not key:
        raise GeminiImageGenerationError("未配置 Gemini API Key")

    ref_url = refs[0]
    image_b64 = ""
    mime = "image/png"
    if ref_url.startswith("data:"):
        header, _, data = ref_url.partition(",")
        mime = header.split(";")[0].replace("data:", "") or "image/png"
        image_b64 = data
    else:
        try:
            async with httpx.AsyncClient(timeout=30.0, trust_env=s.trust_env) as client:
                img_resp = await client.get(ref_url)
                img_resp.raise_for_status()
                mime = img_resp.headers.get("content-type", "image/png").split(";")[0]
                image_b64 = base64.b64encode(img_resp.content).decode("ascii")
        except httpx.HTTPError as e:
            raise GeminiImageGenerationError(f"下载参考图失败：{e}") from e

    parts: list[dict[str, Any]] = [
        {"text": prompt.strip()},
        {"inline_data": {"mime_type": mime, "data": image_b64}},
    ]
    payload: dict[str, Any] = {
        "contents": [{"parts": parts}],
        "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
    }
    model = (s.img2img_model or s.reference_model or s.model or DEFAULT_GEMINI_IMAGE_MODEL).strip()
    url = _gemini_generate_url(s.base_url, model, key)
    try:
        async with httpx.AsyncClient(timeout=s.timeout_sec, trust_env=s.trust_env) as client:
            resp = await client.post(url, json=payload)
    except httpx.HTTPError as e:
        raise GeminiImageGenerationError(f"Gemini 网络错误：{e}") from e

    if resp.status_code >= 400:
        raise GeminiImageGenerationError(
            f"Gemini 图生图 API 错误 {resp.status_code}: {resp.text[:500]}",
            http_status=resp.status_code,
        )

    body = resp.json()
    if not isinstance(body, dict):
        raise GeminiImageGenerationError("Gemini 响应格式无效")
    return _extract_gemini_image(body)
