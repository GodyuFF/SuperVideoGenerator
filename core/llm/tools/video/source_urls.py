"""视频生成参考图 URL 收集：画面 / 落盘图片 / 元素引用（角色·场景·道具）。"""

from __future__ import annotations

from typing import Any

from core.llm.tools.image.frames import _resolve_element_media_id
from core.llm.tools.image.reference_url import resolve_reference_url_for_media
from core.models.entities import MediaAssetType, TextAssetType
from core.models.image_text_asset import get_base_variant, normalize_image_text_content
from core.models.video_text_asset import normalize_video_clip_content
from core.store.memory import MemoryStore

_ELEMENT_BUCKETS = ("scene", "character", "prop", "frame")


def resolve_image_url_for_video(store: MemoryStore, media_id: str) -> str:
    """将 media_id 解析为 Agnes 视频 API 可用的图片 URL。"""
    from core.llm.tools.image.agnes_client import AgnesImageGenerationError

    try:
        return resolve_reference_url_for_media(store, media_id.strip())
    except AgnesImageGenerationError as e:
        raise ValueError(str(e)) from e


def frame_asset_preview_url(store: MemoryStore, frame_asset_id: str) -> str:
    """从 frame 文字资产解析主图 media URL。"""
    asset = store.get_text_asset(frame_asset_id.strip())
    if not asset or asset.type != TextAssetType.FRAME:
        return ""
    if asset.primary_media_id:
        try:
            return resolve_image_url_for_video(store, asset.primary_media_id)
        except ValueError:
            return ""
    content = normalize_image_text_content(asset.type, asset.content)
    base = get_base_variant(content)
    if base and base.media_id:
        try:
            return resolve_image_url_for_video(store, base.media_id)
        except ValueError:
            return ""
    return ""


def _append_url(urls: list[str], seen: set[str], url: str) -> None:
    """去重追加可访问图片 URL。"""
    u = (url or "").strip()
    if u and u not in seen:
        urls.append(u)
        seen.add(u)


def collect_video_source_image_urls(
    store: MemoryStore,
    *,
    frame_asset_ids: list[str] | None = None,
    media_ids: list[str] | None = None,
    element_refs: dict[str, list[str]] | None = None,
) -> list[str]:
    """按用户选择顺序收集 Agnes 视频 API 可用的参考图 URL。"""
    urls: list[str] = []
    seen: set[str] = set()

    for mid in media_ids or []:
        media_id = str(mid or "").strip()
        if not media_id:
            continue
        try:
            _append_url(urls, seen, resolve_image_url_for_video(store, media_id))
        except ValueError:
            continue

    for fid in frame_asset_ids or []:
        frame_id = str(fid or "").strip()
        if not frame_id:
            continue
        asset = store.get_text_asset(frame_id)
        if asset and asset.type != TextAssetType.FRAME:
            continue
        _append_url(urls, seen, frame_asset_preview_url(store, frame_id))

    refs = element_refs or {}
    for bucket in _ELEMENT_BUCKETS:
        raw_ids = refs.get(bucket) or []
        if not isinstance(raw_ids, list):
            raw_ids = [raw_ids]
        for tid in raw_ids:
            tid_str = str(tid or "").strip()
            if not tid_str:
                continue
            mid = _resolve_element_media_id(store, tid_str, {})
            if not mid:
                continue
            try:
                _append_url(urls, seen, resolve_image_url_for_video(store, mid))
            except ValueError:
                continue

    return urls


def collect_video_clip_source_urls(
    store: MemoryStore,
    content: dict[str, Any],
) -> list[str]:
    """按 video_clip content 的 reference_order 收集参考图 URL。"""
    normalized = normalize_video_clip_content(content)
    order = normalized.get("reference_order") or [
        "scene",
        "character",
        "prop",
        "frame",
        "media",
    ]
    urls: list[str] = []
    seen: set[str] = set()
    element_refs = normalized.get("element_refs") or {}
    variant_refs = normalized.get("variant_refs") or {}
    if not isinstance(variant_refs, dict):
        variant_refs = {}
    media_refs = normalized.get("media_refs") or []

    for bucket in order:
        if bucket == "media":
            for mid in media_refs:
                mid = str(mid or "").strip()
                if not mid:
                    continue
                media = store.get_media_asset(mid)
                if media and media.type != MediaAssetType.IMAGE:
                    continue
                try:
                    _append_url(urls, seen, resolve_image_url_for_video(store, mid))
                except ValueError:
                    continue
            continue
        raw_ids = element_refs.get(bucket) or []
        if not isinstance(raw_ids, list):
            raw_ids = [raw_ids]
        for tid in raw_ids:
            tid_str = str(tid or "").strip()
            if not tid_str:
                continue
            if bucket == "frame":
                _append_url(urls, seen, frame_asset_preview_url(store, tid_str))
                continue
            mid = _resolve_element_media_id(store, tid_str, variant_refs)
            if not mid:
                continue
            try:
                _append_url(urls, seen, resolve_image_url_for_video(store, mid))
            except ValueError:
                continue
    return urls


def video_clip_asset_preview_url(store: MemoryStore, video_clip_asset_id: str) -> str:
    """从 video_clip 已生成视频解析预览 URL（用于看板）。"""
    asset = store.get_text_asset(video_clip_asset_id.strip())
    if not asset or asset.type != TextAssetType.VIDEO_CLIP:
        return ""
    if asset.primary_media_id:
        media = store.get_media_asset(asset.primary_media_id)
        if media and media.url:
            return media.url.strip()
    return ""
