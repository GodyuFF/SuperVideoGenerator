"""音效搜索与预览代理 API（OpenCut 剪辑助手素材面板）。"""

from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from core.sounds.service import resolve_preview_stream_url, search_sound_effects

router = APIRouter(prefix="/api/sounds", tags=["sounds"])


@router.get("/search")
async def search_sounds(
    q: str = Query("", description="搜索关键词"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=150),
    type: str = Query("effects", description="音效类型占位，当前均为短音效"),
    commercial_only: bool = Query(
        True,
        description="仅返回可商用许可（CC0 / Attribution）",
    ),
    sort: str = Query("downloads", description="排序：downloads | rating"),
):
    """搜索免费音效；已配置 FREESOUND_API_KEY 时走 Freesound，否则返回内置目录。"""
    del type
    try:
        return await search_sound_effects(
            query=q,
            page=page,
            page_size=page_size,
            commercial_only=commercial_only,
            sort=sort,
        )
    except Exception as exc:
        raise HTTPException(502, f"音效搜索失败：{exc}") from exc


@router.get("/preview/{sound_id}")
async def preview_sound(sound_id: int):
    """代理预览音频流，供剪辑时间轴 fetch 与试听（绕过第三方 CORS）。"""
    try:
        upstream_url, media_type = await resolve_preview_stream_url(sound_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"预览拉取失败：{exc}") from exc

    async def _stream():
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            async with client.stream("GET", upstream_url) as resp:
                resp.raise_for_status()
                async for chunk in resp.aiter_bytes():
                    yield chunk

    return StreamingResponse(_stream(), media_type=media_type)
