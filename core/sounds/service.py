"""音效搜索服务：Freesound 在线检索 + 内置免费目录兜底。"""

from __future__ import annotations

import math
from typing import Any

from core.sounds.builtin_catalog import (
    BuiltinSoundEntry,
    get_builtin_sound,
    search_builtin_sounds,
)
from core.sounds.freesound_client import (
    fetch_freesound_preview_url,
    freesound_api_key,
    search_freesound,
)


def _preview_proxy_url(sound_id: int) -> str:
    """返回经本服务代理的预览地址（避免浏览器 CORS）。"""
    return f"/api/sounds/preview/{sound_id}"


def _builtin_to_dict(entry: BuiltinSoundEntry) -> dict[str, Any]:
    """内置音效转为 OpenCut SoundEffect 兼容结构。"""
    return {
        "id": entry.id,
        "name": entry.name,
        "description": entry.description,
        "url": entry.preview_url,
        "previewUrl": _preview_proxy_url(entry.id),
        "downloadUrl": _preview_proxy_url(entry.id),
        "duration": entry.duration,
        "filesize": 0,
        "type": "audio/mpeg",
        "channels": 2,
        "bitrate": 128000,
        "bitdepth": 16,
        "samplerate": 44100,
        "username": entry.username,
        "tags": list(entry.tags),
        "license": entry.license,
        "created": "",
        "downloads": 0,
        "rating": 0.0,
        "ratingCount": 0,
        "source": "builtin",
    }


def _freesound_to_dict(raw: dict[str, Any]) -> dict[str, Any]:
    """Freesound 单条结果转为 OpenCut SoundEffect 兼容结构。"""
    sid = int(raw.get("id", 0))
    previews = raw.get("previews") or {}
    direct_preview = (
        previews.get("preview-hq-mp3")
        or previews.get("preview-lq-mp3")
        or previews.get("preview-hq-ogg")
        or ""
    )
    return {
        "id": sid,
        "name": str(raw.get("name", "")),
        "description": str(raw.get("description", "")),
        "url": direct_preview,
        "previewUrl": _preview_proxy_url(sid),
        "downloadUrl": _preview_proxy_url(sid),
        "duration": float(raw.get("duration") or 0),
        "filesize": int(raw.get("filesize") or 0),
        "type": str(raw.get("type") or "audio/mpeg"),
        "channels": 2,
        "bitrate": 128000,
        "bitdepth": 16,
        "samplerate": 44100,
        "username": str(raw.get("username", "")),
        "tags": list(raw.get("tags") or []),
        "license": str(raw.get("license", "")),
        "created": str(raw.get("created", "")),
        "downloads": int(raw.get("num_downloads") or 0),
        "rating": float(raw.get("avg_rating") or 0),
        "ratingCount": int(raw.get("num_ratings") or 0),
        "source": "freesound",
    }


def _paginate(
    items: list[dict[str, Any]],
    *,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    """对内存列表分页并生成 next 游标。"""
    total = len(items)
    page = max(1, page)
    page_size = max(1, min(150, page_size))
    start = (page - 1) * page_size
    end = start + page_size
    page_items = items[start:end]
    has_next = end < total
    return {
        "count": total,
        "results": page_items,
        "next": str(page + 1) if has_next else None,
        "previous": str(page - 1) if page > 1 else None,
        "page": page,
        "num_pages": max(1, math.ceil(total / page_size)),
    }


async def search_sound_effects(
    *,
    query: str = "",
    page: int = 1,
    page_size: int = 50,
    commercial_only: bool = True,
    sort: str = "downloads",
    effect_type: str = "effects",
) -> dict[str, Any]:
    """搜索音效：优先 Freesound；失败或未配置 Key 时使用内置目录。"""
    del effect_type
    merged: list[dict[str, Any]] = []
    source = "builtin"

    if freesound_api_key():
        try:
            raw = await search_freesound(
                query=query,
                page=page,
                page_size=page_size,
                commercial_only=commercial_only,
                sort=sort,
            )
            merged = [
                _freesound_to_dict(item)
                for item in raw.get("results") or []
                if isinstance(item, dict)
            ]
            source = "freesound"
            return {
                "count": int(raw.get("count") or len(merged)),
                "results": merged,
                "next": raw.get("next"),
                "previous": raw.get("previous"),
                "source": source,
                "freesound_configured": True,
            }
        except Exception:
            merged = []

    builtin_hits = search_builtin_sounds(
        query,
        commercial_only=commercial_only,
        sort=sort,
    )
    merged = [_builtin_to_dict(entry) for entry in builtin_hits]
    payload = _paginate(merged, page=page, page_size=page_size)
    payload["source"] = source
    payload["freesound_configured"] = bool(freesound_api_key())
    return payload


async def resolve_preview_stream_url(sound_id: int) -> tuple[str, str]:
    """解析预览音频直链与 Content-Type。"""
    if sound_id < 0:
        entry = get_builtin_sound(sound_id)
        if entry is None:
            raise ValueError(f"内置音效 {sound_id} 不存在")
        return entry.preview_url, "audio/mpeg"
    url = await fetch_freesound_preview_url(sound_id)
    return url, "audio/mpeg"
