"""火山方舟 SeedDream 生图客户端。"""

from __future__ import annotations

import math
from typing import Any

import httpx

from core.llm.tools.image.settings import ImageGenSettings, get_image_gen_settings
from core.llm.tools.volcengine.ark_common import (
    DEFAULT_ARK_BASE_URL,
    DEFAULT_SEEDREAM_MODEL,
    ark_auth_headers,
    normalize_ark_base_url,
    resolve_ark_api_key,
)


class ArkImageGenerationError(RuntimeError):
    """火山方舟 SeedDream 生图失败。"""

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


def _images_url(base_url: str) -> str:
    """返回图片生成 endpoint。"""
    return f"{normalize_ark_base_url(base_url)}/images/generations"


def _extract_image_url(data: dict[str, Any]) -> str:
    """从 SeedDream 响应中提取图片 URL 或 base64。"""
    items = data.get("data")
    if not isinstance(items, list) or not items:
        raise ArkImageGenerationError("SeedDream 响应缺少 data 数组")
    first = items[0]
    if not isinstance(first, dict):
        raise ArkImageGenerationError("SeedDream 响应 data[0] 无效")
    url = str(first.get("url") or "").strip()
    if url:
        return url
    b64 = str(first.get("b64_json") or "").strip()
    if b64:
        return f"data:image/png;base64,{b64}"
    raise ArkImageGenerationError("SeedDream 响应未包含 url 或 b64_json")


SEEDREAM_MIN_PIXELS = 3_686_400  # Seedream 4.5 / 5.x 总像素下限（2560×1440）

# UI 小尺寸 → 官方推荐 2K 像素（保持大致比例）
_SEEDREAM_SIZE_ALIASES: dict[str, str] = {
    "1k": "2K",
    "2k": "2K",
    "3k": "3K",
    "4k": "4K",
    "1024x1024": "2048x2048",
    "1024x768": "2304x1728",
    "768x1024": "1728x2304",
    "1280x720": "2560x1440",
    "1920x1080": "2560x1440",
}


def _parse_wh(size: str) -> tuple[int, int] | None:
    """解析 WxH 尺寸；失败返回 None。"""
    text = size.strip().lower().replace(" ", "")
    if "x" not in text:
        return None
    left, right = text.split("x", 1)
    try:
        w, h = int(left), int(right)
    except ValueError:
        return None
    if w <= 0 or h <= 0:
        return None
    return w, h


def normalize_seedream_size(size: str | None) -> str:
    """将配置尺寸规范为 SeedDream 合法 size（关键词或 ≥3686400 像素）。"""
    raw = (size or "").strip()
    if not raw:
        return "2048x2048"
    key = raw.lower().replace(" ", "")
    mapped = _SEEDREAM_SIZE_ALIASES.get(key)
    if mapped:
        return mapped
    wh = _parse_wh(raw)
    if wh is None:
        return "2048x2048"
    w, h = wh
    if w * h >= SEEDREAM_MIN_PIXELS:
        return f"{w}x{h}"
    scale = math.sqrt(SEEDREAM_MIN_PIXELS / float(w * h))
    nw = max(1, int(math.ceil(w * scale)))
    nh = max(1, int(math.ceil(h * scale)))
    while nw * nh < SEEDREAM_MIN_PIXELS:
        if nw <= nh:
            nw += 1
        else:
            nh += 1
    return f"{nw}x{nh}"


def _model_supports_sequential_image_generation(model: str) -> bool:
    """判断模型是否支持组图参数 sequential_image_generation（约 Seedream 4.x）。"""
    m = (model or "").strip().lower()
    # 5.0 Pro 部分推理接入点会拒绝该参数；组图能力主要在 4.0 / 4.5 文档中明确。
    return "seedream-4" in m or "seedream_4" in m


def _build_payload(
    prompt: str,
    *,
    settings: ImageGenSettings,
    size: str | None = None,
    reference_urls: list[str] | None = None,
) -> dict[str, Any]:
    """组装 SeedDream 生图请求体（单图；尺寸自动抬到官方像素下限）。"""
    model = settings.model or DEFAULT_SEEDREAM_MODEL
    payload: dict[str, Any] = {
        "model": model,
        "prompt": prompt.strip(),
        "size": normalize_seedream_size(size or settings.default_size),
        "response_format": "url",
        "watermark": False,
    }
    # 仅在模型明确支持时再关闭组图；否则省略（本工具每次只取 data[0]）
    if _model_supports_sequential_image_generation(model):
        payload["sequential_image_generation"] = "disabled"
    refs = [u.strip() for u in (reference_urls or []) if u and u.strip()]
    if len(refs) == 1:
        payload["image"] = refs[0]
    elif len(refs) > 1:
        payload["image"] = refs
    return payload


async def _post_image_generation(
    payload: dict[str, Any],
    *,
    settings: ImageGenSettings,
    api_key: str | None = None,
    timeout: float | None = None,
) -> str:
    """调用 SeedDream API 并返回图片 URL。"""
    try:
        key = resolve_ark_api_key(api_key or settings.api_key)
    except ValueError as e:
        raise ArkImageGenerationError(str(e)) from e
    base = settings.base_url or DEFAULT_ARK_BASE_URL
    url = _images_url(base)
    t = float(timeout if timeout is not None else settings.timeout_sec or 120.0)
    from core.interaction_log.media_log import logged_media_request

    try:
        resp = await logged_media_request(
            media_kind="image",
            provider="volcengine",
            model=str(payload.get("model") or ""),
            method="POST",
            url=url,
            headers=ark_auth_headers(key),
            json_body=payload,
            timeout=t,
            trust_env=settings.trust_env,
            phase="create",
        )
    except httpx.HTTPError as e:
        raise ArkImageGenerationError(f"SeedDream 网络错误：{e}") from e
    if resp.status_code >= 400:
        body = resp.text[:2000]
        raise ArkImageGenerationError(
            f"SeedDream API 错误 {resp.status_code}: {body}",
            http_status=resp.status_code,
            api_message=body,
        )
    try:
        data = resp.json()
    except ValueError as e:
        raise ArkImageGenerationError("SeedDream 响应不是有效 JSON") from e
    if not isinstance(data, dict):
        raise ArkImageGenerationError("SeedDream 响应格式无效")
    return _extract_image_url(data)


async def ark_txt2img(
    prompt: str,
    *,
    settings: ImageGenSettings | None = None,
    size: str | None = None,
    api_key: str | None = None,
    timeout: float | None = None,
) -> str:
    """SeedDream 文生图。"""
    s = settings or get_image_gen_settings()
    text = prompt.strip()
    if not text:
        raise ArkImageGenerationError("生图 prompt 不能为空")
    payload = _build_payload(text, settings=s, size=size)
    return await _post_image_generation(payload, settings=s, api_key=api_key, timeout=timeout)


async def ark_img2img(
    prompt: str,
    reference_urls: list[str],
    *,
    settings: ImageGenSettings | None = None,
    size: str | None = None,
    api_key: str | None = None,
    timeout: float | None = None,
) -> str:
    """SeedDream 单图/多图参考生图。"""
    refs = [u.strip() for u in reference_urls if u and u.strip()]
    if not refs:
        raise ArkImageGenerationError("图生图缺少参考图 URL")
    s = settings or get_image_gen_settings()
    payload = _build_payload(prompt, settings=s, size=size, reference_urls=refs)
    return await _post_image_generation(payload, settings=s, api_key=api_key, timeout=timeout)
