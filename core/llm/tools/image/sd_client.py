"""本地 Stable Diffusion WebUI API 客户端（Automatic1111 txt2img/img2img）。"""

from __future__ import annotations

import base64
from typing import Any

import httpx

from core.llm.tools.image.settings import (
    ImageGenSettings,
    get_image_gen_settings,
)


class SdImageGenerationError(RuntimeError):
    """本地 SD 生图 API 调用失败。"""

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


def _parse_size(size_str: str) -> tuple[int, int]:
    """解析 "1024x768" → (1024, 768)。"""
    parts = size_str.split("x")
    w = int(parts[0]) if parts else 1024
    h = int(parts[1]) if len(parts) > 1 else 768
    return w, h


async def _fetch_image_as_base64(url: str, timeout: float = 30.0) -> str:
    """将远程图片 URL 下载并转为 base64 字符串（SD img2img 需要）。"""
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return base64.b64encode(resp.content).decode("ascii")


async def sd_txt2img(
    prompt: str,
    *,
    settings: ImageGenSettings | None = None,
    size: str | None = None,
    negative_prompt: str | None = None,
    steps: int | None = None,
    cfg_scale: float | None = None,
    sampler: str | None = None,
    base_url_override: str | None = None,
    timeout: float | None = None,
) -> str:
    """调用本地 SD WebUI txt2img，返回 base64 data URL。"""
    s = settings or get_image_gen_settings()
    url = f"{(base_url_override or s.sd_base_url).rstrip('/')}/sdapi/v1/txt2img"

    w, h = _parse_size(size or s.default_size)
    payload: dict[str, Any] = {
        "prompt": prompt.strip(),
        "negative_prompt": (
            negative_prompt if negative_prompt is not None else s.sd_negative_prompt
        ).strip(),
        "width": w,
        "height": h,
        "steps": steps if steps is not None else s.sd_steps,
        "cfg_scale": cfg_scale if cfg_scale is not None else s.sd_cfg_scale,
        "sampler_name": (sampler or s.sd_sampler).strip(),
        "save_images": False,
    }

    t = timeout if timeout is not None else s.timeout_sec
    try:
        async with httpx.AsyncClient(timeout=t, trust_env=False) as client:
            resp = await client.post(url, json=payload)
    except httpx.HTTPError as e:
        raise SdImageGenerationError(f"SD 网络错误：{e}") from e

    if resp.status_code >= 400:
        detail = resp.text[:500]
        raise SdImageGenerationError(
            f"SD txt2img 错误 {resp.status_code}: {detail}",
            http_status=resp.status_code,
        )

    try:
        body = resp.json()
    except ValueError as e:
        raise SdImageGenerationError("SD 响应不是有效 JSON") from e

    images = body.get("images")
    if not isinstance(images, list) or not images:
        raise SdImageGenerationError("SD 响应未包含生成图片")

    # SD 返回 base64 编码的 PNG 图片
    b64_image = str(images[0])
    return f"data:image/png;base64,{b64_image}"


async def sd_img2img(
    prompt: str,
    init_image_b64: str,
    *,
    settings: ImageGenSettings | None = None,
    size: str | None = None,
    negative_prompt: str | None = None,
    steps: int | None = None,
    cfg_scale: float | None = None,
    denoising_strength: float = 0.75,
    sampler: str | None = None,
    base_url_override: str | None = None,
    timeout: float | None = None,
) -> str:
    """调用本地 SD WebUI img2img，返回 base64 data URL。

    init_image_b64 应为纯 base64 字符串（不含 data: 前缀）。
    """
    s = settings or get_image_gen_settings()
    url = f"{(base_url_override or s.sd_base_url).rstrip('/')}/sdapi/v1/img2img"

    w, h = _parse_size(size or s.default_size)
    payload: dict[str, Any] = {
        "init_images": [init_image_b64],
        "prompt": prompt.strip(),
        "negative_prompt": (
            negative_prompt if negative_prompt is not None else s.sd_negative_prompt
        ).strip(),
        "width": w,
        "height": h,
        "steps": steps if steps is not None else s.sd_steps,
        "cfg_scale": cfg_scale if cfg_scale is not None else s.sd_cfg_scale,
        "denoising_strength": denoising_strength,
        "sampler_name": (sampler or s.sd_sampler).strip(),
        "save_images": False,
    }

    t = timeout if timeout is not None else s.timeout_sec
    try:
        async with httpx.AsyncClient(timeout=t, trust_env=False) as client:
            resp = await client.post(url, json=payload)
    except httpx.HTTPError as e:
        raise SdImageGenerationError(f"SD 网络错误：{e}") from e

    if resp.status_code >= 400:
        detail = resp.text[:500]
        raise SdImageGenerationError(
            f"SD img2img 错误 {resp.status_code}: {detail}",
            http_status=resp.status_code,
        )

    try:
        body = resp.json()
    except ValueError as e:
        raise SdImageGenerationError("SD 响应不是有效 JSON") from e

    images = body.get("images")
    if not isinstance(images, list) or not images:
        raise SdImageGenerationError("SD 响应未包含生成图片")

    b64_image = str(images[0])
    return f"data:image/png;base64,{b64_image}"


async def download_reference_as_base64(url: str, timeout: float = 30.0) -> str:
    """将参考图下载为纯 base64（含处理 data: URL 的情况）。

    SD img2img 的 init_images 需要纯 base64 字符串。
    """
    if url.startswith("data:"):
        # 已经是 data URL，提取 base64 部分
        _, _, b64_part = url.partition("base64,")
        if b64_part:
            return b64_part.strip()
        raise SdImageGenerationError("无法解析 data URL 中的 base64 数据")
    return await _fetch_image_as_base64(url, timeout=timeout)
