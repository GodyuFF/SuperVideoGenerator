"""Freesound API v2 客户端（Token 认证）。"""

from __future__ import annotations

import os
from typing import Any

import httpx

FREESOUND_API_BASE = "https://freesound.org/apiv2"
FREESOUND_FIELDS = (
    "id,name,description,previews,duration,filesize,type,username,tags,license,"
    "created,num_downloads,avg_rating,num_ratings,download"
)


def freesound_api_key() -> str:
    """读取 Freesound API Key（环境变量 FREESOUND_API_KEY）。"""
    return os.environ.get("FREESOUND_API_KEY", "").strip()


def _commercial_license_filter() -> str:
    """可商用许可过滤（排除 NonCommercial）。"""
    return '(license:"Creative Commons 0" OR license:"Attribution")'


async def search_freesound(
    *,
    query: str = "",
    page: int = 1,
    page_size: int = 50,
    commercial_only: bool = True,
    sort: str = "downloads",
) -> dict[str, Any]:
    """调用 Freesound 文本搜索，返回原始 API JSON。"""
    api_key = freesound_api_key()
    if not api_key:
        raise RuntimeError("未配置 FREESOUND_API_KEY")

    filters: list[str] = ["duration:[0.1 TO 120]"]
    if commercial_only:
        filters.append(_commercial_license_filter())

    params: dict[str, Any] = {
        "page": max(1, page),
        "page_size": max(1, min(150, page_size)),
        "fields": FREESOUND_FIELDS,
        "filter": " ".join(filters),
    }
    q = query.strip()
    if q:
        params["query"] = q
    else:
        params["query"] = "effect"
        params["sort"] = "downloads_desc" if sort == "downloads" else "rating_desc"

    headers = {"Authorization": f"Token {api_key}"}
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(
            f"{FREESOUND_API_BASE}/search/text/",
            params=params,
            headers=headers,
        )
        resp.raise_for_status()
        return resp.json()


async def fetch_freesound_preview_url(sound_id: int) -> str:
    """获取 Freesound 音效预览 MP3 直链。"""
    api_key = freesound_api_key()
    if not api_key:
        raise RuntimeError("未配置 FREESOUND_API_KEY")

    headers = {"Authorization": f"Token {api_key}"}
    params = {"fields": "id,previews"}
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(
            f"{FREESOUND_API_BASE}/sounds/{sound_id}/",
            params=params,
            headers=headers,
        )
        resp.raise_for_status()
        data = resp.json()
    previews = data.get("previews") or {}
    url = (
        previews.get("preview-hq-mp3")
        or previews.get("preview-lq-mp3")
        or previews.get("preview-hq-ogg")
        or ""
    )
    if not url:
        raise ValueError(f"Freesound {sound_id} 无预览地址")
    return str(url)
