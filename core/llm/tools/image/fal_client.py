"""fal.ai FLUX 生图客户端。"""

from __future__ import annotations

import os
from typing import Any

import httpx

from core.llm.tools.image.settings import ImageGenSettings, get_image_gen_settings

DEFAULT_FAL_BASE_URL = "https://fal.run"
DEFAULT_FAL_IMAGE_MODEL = "fal-ai/flux-pro/v1.1"


class FalImageGenerationError(RuntimeError):
    """fal.ai 生图 API 调用失败。"""

    def __init__(
        self,
        message: str,
        *,
        http_status: int | None = None,
    ) -> None:
        self.http_status = http_status
        super().__init__(message)


def resolved_fal_api_key(
    settings: ImageGenSettings | None = None,
    explicit_key: str | None = None,
) -> str:
    """解析 fal.ai API Key。"""
    if explicit_key and explicit_key.strip():
        return explicit_key.strip()
    s = settings or get_image_gen_settings()
    if s.api_key and s.api_key.strip():
        return s.api_key.strip()
    for env_name in ("SVG_IMAGE_GEN_API_KEY", "FAL_KEY", "FAL_API_KEY"):
        val = os.getenv(env_name, "").strip()
        if val:
            return val
    return ""


def _fal_model_path(settings: ImageGenSettings) -> str:
    model = (settings.model or DEFAULT_FAL_IMAGE_MODEL).strip()
    if model.startswith("fal-ai/"):
        return model
    return DEFAULT_FAL_IMAGE_MODEL


def _fal_endpoint(base_url: str, model_path: str) -> str:
    root = (base_url or DEFAULT_FAL_BASE_URL).rstrip("/")
    path = model_path.strip("/")
    return f"{root}/{path}"


def _extract_fal_image_url(data: dict[str, Any]) -> str:
    """从 fal.ai 同步响应提取图片 URL。"""
    images = data.get("images")
    if isinstance(images, list) and images:
        first = images[0]
        if isinstance(first, dict):
            url = str(first.get("url") or "").strip()
            if url:
                return url
        elif isinstance(first, str) and first.strip():
            return first.strip()
    image = data.get("image")
    if isinstance(image, dict):
        url = str(image.get("url") or "").strip()
        if url:
            return url
    url = str(data.get("url") or "").strip()
    if url:
        return url
    raise FalImageGenerationError("fal.ai 响应未包含图片 URL")


def _parse_fal_size(size: str) -> dict[str, int]:
    """将 WxH 尺寸转为 fal image_size 对象。"""
    raw = (size or "1024x768").strip().lower().replace("×", "x")
    if "x" in raw:
        w_str, _, h_str = raw.partition("x")
        try:
            return {"width": int(w_str), "height": int(h_str)}
        except ValueError:
            pass
    return {"width": 1024, "height": 768}


async def fal_txt2img(
    prompt: str,
    *,
    settings: ImageGenSettings | None = None,
    size: str | None = None,
    api_key: str | None = None,
) -> str:
    """fal.ai FLUX 文生图。"""
    s = settings or get_image_gen_settings()
    key = resolved_fal_api_key(s, api_key)
    if not key:
        raise FalImageGenerationError(
            "未配置 fal.ai API Key（SVG_IMAGE_GEN_API_KEY 或 FAL_KEY）"
        )
    text = prompt.strip()
    if not text:
        raise FalImageGenerationError("生图 prompt 不能为空")

    model_path = _fal_model_path(s)
    payload: dict[str, Any] = {
        "prompt": text,
        "image_size": _parse_fal_size(size or s.default_size),
        "num_images": 1,
    }
    headers = {
        "Authorization": f"Key {key}",
        "Content-Type": "application/json",
    }
    url = _fal_endpoint(s.base_url, model_path)
    try:
        async with httpx.AsyncClient(timeout=s.timeout_sec, trust_env=s.trust_env) as client:
            resp = await client.post(url, headers=headers, json=payload)
    except httpx.HTTPError as e:
        raise FalImageGenerationError(f"fal.ai 网络错误：{e}") from e

    if resp.status_code >= 400:
        raise FalImageGenerationError(
            f"fal.ai API 错误 {resp.status_code}: {resp.text[:500]}",
            http_status=resp.status_code,
        )

    try:
        body = resp.json()
    except ValueError as e:
        raise FalImageGenerationError("fal.ai 响应不是有效 JSON") from e
    if not isinstance(body, dict):
        raise FalImageGenerationError("fal.ai 响应格式无效")
    return _extract_fal_image_url(body)


async def fal_img2img(
    prompt: str,
    reference_urls: list[str],
    *,
    settings: ImageGenSettings | None = None,
    size: str | None = None,
    api_key: str | None = None,
) -> str:
    """fal.ai 图生图（单张参考图）。"""
    s = settings or get_image_gen_settings()
    if not s.reference_enabled:
        raise FalImageGenerationError("reference 生图未启用")
    refs = [u.strip() for u in reference_urls if str(u).strip()]
    if not refs:
        raise FalImageGenerationError("reference 图片 URL 不能为空")

    key = resolved_fal_api_key(s, api_key)
    if not key:
        raise FalImageGenerationError("未配置 fal.ai API Key")

    model_path = (s.img2img_model or s.reference_model or _fal_model_path(s)).strip()
    if not model_path.startswith("fal-ai/"):
        model_path = "fal-ai/flux/dev/image-to-image"

    payload: dict[str, Any] = {
        "prompt": prompt.strip(),
        "image_url": refs[0],
        "image_size": _parse_fal_size(size or s.default_size),
        "num_images": 1,
    }
    headers = {
        "Authorization": f"Key {key}",
        "Content-Type": "application/json",
    }
    url = _fal_endpoint(s.base_url, model_path)
    try:
        async with httpx.AsyncClient(timeout=s.timeout_sec, trust_env=s.trust_env) as client:
            resp = await client.post(url, headers=headers, json=payload)
    except httpx.HTTPError as e:
        raise FalImageGenerationError(f"fal.ai 网络错误：{e}") from e

    if resp.status_code >= 400:
        raise FalImageGenerationError(
            f"fal.ai 图生图 API 错误 {resp.status_code}: {resp.text[:500]}",
            http_status=resp.status_code,
        )

    body = resp.json()
    if not isinstance(body, dict):
        raise FalImageGenerationError("fal.ai 响应格式无效")
    return _extract_fal_image_url(body)
