"""主编排 tool_list_assets：剧本文字 + 媒体资产完整 JSON 载荷。"""

from __future__ import annotations

import json
from typing import Any

from core.llm.tools.script.list import build_text_assets_list_payload
from core.llm.tools.shared.media_list import build_media_list_payload
from core.models.entities import MediaAssetType
from core.store.memory import MemoryStore


def _video_plan_block(store: MemoryStore, script_id: str) -> dict[str, Any] | None:
    vp = store.get_video_plan_for_script(script_id)
    if not vp:
        return None
    return {
        "id": vp.id,
        "script_id": vp.script_id,
        "mode": vp.mode.value,
        "shot_count": len(vp.shots),
    }


def _edit_timeline_block(store: MemoryStore, script_id: str) -> dict[str, Any] | None:
    timeline = store.get_edit_timeline_for_script(script_id)
    if not timeline:
        return None
    tracks = timeline.tracks or {}
    return {
        "id": timeline.id,
        "script_id": timeline.script_id,
        "duration_ms": timeline.duration_ms,
        "track_counts": {name: len(clips) for name, clips in tracks.items()},
    }


def build_script_assets_payload(
    store: MemoryStore,
    script_id: str,
    *,
    include_text_content: bool = False,
) -> dict[str, Any]:
    """汇总剧本文字资产与各类型媒体资产（含 URL/可访问性）。"""
    text_payload = build_text_assets_list_payload(
        store,
        script_id,
        include_content=include_text_content,
    )

    media_sections: dict[str, Any] = {}
    media_counts: dict[str, int] = {}
    accessible_counts: dict[str, int] = {}
    for media_type in (
        MediaAssetType.IMAGE,
        MediaAssetType.AUDIO,
        MediaAssetType.VIDEO,
        MediaAssetType.FINAL,
    ):
        section = build_media_list_payload(store, script_id, media_type)
        key = media_type.value
        media_sections[key] = section
        media_counts[key] = int(section.get("count", 0))
        accessible_counts[key] = int(section.get("accessible_count", 0))

    payload: dict[str, Any] = {
        "script_id": script_id,
        "script": text_payload.get("script"),
        "summary": {
            "text_asset_count": text_payload.get("count", 0),
            "text_counts_by_type": text_payload.get("counts_by_type", {}),
            "media_counts": media_counts,
            "accessible_media_counts": accessible_counts,
            "has_video_plan": _video_plan_block(store, script_id) is not None,
            "has_edit_timeline": _edit_timeline_block(store, script_id) is not None,
        },
        "text_assets": text_payload.get("assets", []),
        "media": media_sections,
        "video_plan": _video_plan_block(store, script_id),
        "edit_timeline": _edit_timeline_block(store, script_id),
    }
    if text_payload.get("message"):
        payload["text_message"] = text_payload["message"]
    if not any(media_counts.values()) and not payload["text_assets"]:
        payload["message"] = "当前尚无产出资产。"
    return payload


def format_script_assets_payload(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def format_script_assets_summary(payload: dict[str, Any]) -> str:
    """JSON 完整载荷（供 ReAct observation 使用）。"""
    return format_script_assets_payload(payload)
