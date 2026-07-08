"""检测本地 Stable Diffusion WebUI（Automatic1111）是否可用。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx

DEFAULT_SD_BASE_URL = "http://127.0.0.1:7860"
SD_DETECT_TIMEOUT = 3.0


@dataclass
class SdDetectResult:
    """本地 SD 检测结果。"""
    available: bool
    current_model: str = ""
    models: list[str] = field(default_factory=list)
    error: str = ""
    base_url: str = DEFAULT_SD_BASE_URL


async def detect_local_sd(
    base_url: str = DEFAULT_SD_BASE_URL,
    timeout: float = SD_DETECT_TIMEOUT,
) -> SdDetectResult:
    """检测本地 SD WebUI 是否运行，返回可用模型列表。"""
    url = f"{base_url.rstrip('/')}/sdapi/v1/sd-models"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url)
    except httpx.HTTPError as e:
        return SdDetectResult(
            available=False,
            error=f"无法连接本地 SD ({base_url})：{e}",
            base_url=base_url,
        )

    if resp.status_code >= 400:
        return SdDetectResult(
            available=False,
            error=f"SD API 返回错误 {resp.status_code}",
            base_url=base_url,
        )

    try:
        body = resp.json()
    except ValueError:
        return SdDetectResult(
            available=False,
            error="SD API 返回非 JSON 响应",
            base_url=base_url,
        )

    models: list[str] = []
    if isinstance(body, list):
        for item in body:
            if isinstance(item, dict):
                title = str(item.get("title", "")).strip()
                if title:
                    models.append(title)

    if not models:
        return SdDetectResult(
            available=False,
            error="SD 未加载任何模型",
            base_url=base_url,
        )

    # 获取当前加载的模型
    current_model = ""
    try:
        opt_url = f"{base_url.rstrip('/')}/sdapi/v1/options"
        async with httpx.AsyncClient(timeout=timeout) as client:
            opt_resp = await client.get(opt_url)
        if opt_resp.status_code < 400:
            opt_body = opt_resp.json()
            if isinstance(opt_body, dict):
                current_model = str(opt_body.get("sd_model_checkpoint", "")).strip()
    except Exception:
        pass

    return SdDetectResult(
        available=True,
        current_model=current_model or models[0],
        models=models,
        base_url=base_url,
    )
