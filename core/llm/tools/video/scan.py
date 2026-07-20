"""scan_video_clips：扫描待生成视频的 video_clip 文字资产。"""

from __future__ import annotations

from typing import Any

from core.assets.video_prompt import compose_video_clip_prompt
from core.llm.tools.video.source_urls import collect_video_clip_source_urls
from core.models.entities import TextAssetType
from core.models.video_text_asset import normalize_video_clip_content
from core.store.memory import MemoryStore


def scan_video_clips(
    store: MemoryStore,
    script_id: str,
    *,
    asset_ids: list[str] | None = None,
) -> dict[str, Any]:
    """扫描剧本内 video_clip 资产，返回 pending / ready 清单。"""
    wanted = {str(x).strip() for x in (asset_ids or []) if str(x).strip()}
    items: list[dict[str, Any]] = []
    for asset in store.text_assets.values():
        if asset.type != TextAssetType.VIDEO_CLIP:
            continue
        if asset.source_script_id != script_id and asset.script_id != script_id:
            linked = any(
                ref.target_id == asset.id and ref.script_id == script_id
                for ref in store.references.values()
            )
            if not linked:
                continue
        if wanted and asset.id not in wanted:
            continue
        content = normalize_video_clip_content(asset.content)
        prompt = str(content.get("video_prompt") or "").strip()
        if not prompt:
            prompt = compose_video_clip_prompt(content, store=store)
        refs = collect_video_clip_source_urls(store, content)
        has_media = bool(asset.primary_media_id)
        ready = has_media and bool(prompt)
        pending_reason = ""
        if not prompt:
            pending_reason = "缺少 video_prompt"
        elif content.get("video_mode") in ("img2video", "keyframes") and not refs:
            pending_reason = "参考图未就绪"
        items.append(
            {
                "asset_id": asset.id,
                "name": asset.name,
                "ready": ready,
                "has_primary_media": has_media,
                "reference_url_count": len(refs),
                "pending_reason": pending_reason,
                "video_mode": content.get("video_mode") or "auto",
            }
        )
    pending = [i for i in items if not i["ready"]]
    return {
        "script_id": script_id,
        "total": len(items),
        "ready_count": len(items) - len(pending),
        "pending_count": len(pending),
        "items": items,
        "pending_items": pending,
    }
