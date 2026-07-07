"""editing_agent load_edit_context 结构化载荷。"""

from __future__ import annotations

from typing import Any

from core.edit.timeline import build_tts_by_shot, resolve_shot_image_ref
from core.edit.timeline import (
    build_timeline_layer_summary,
    timeline_board_items,
)
from core.llm.tools.image.scan import build_scan_text_assets_payload
from core.llm.tools.shared.assets_summary import build_script_assets_payload
from core.llm.tools.shared.linked_assets import (
    build_assets_with_images_from_scan,
    build_plots_for_script,
)
from core.llm.tools.shared.media_list import resolve_media_access
from core.store.memory import MemoryStore

SCRIPT_MD_MAX = 2000


def _media_is_accessible(store: MemoryStore, media_id: str | None) -> bool:
    if not media_id:
        return False
    media = store.media_assets.get(media_id)
    if not media:
        return False
    return bool(resolve_media_access(media.url).get("is_accessible"))


def _resolve_shot_media(
    store: MemoryStore,
    shot,
    tts_by_shot: dict[str, str],
) -> dict[str, Any]:
    image_id = resolve_shot_image_ref(store, shot)
    audio_id = tts_by_shot.get(shot.id)
    return {
        "image_media_id": image_id,
        "audio_media_id": audio_id,
        "image_accessible": _media_is_accessible(store, image_id),
        "audio_accessible": _media_is_accessible(store, audio_id),
    }


def build_edit_context_payload(store: MemoryStore, script_id: str) -> dict[str, Any]:
    """分镜 VideoPlan、已有资源、剧本剧情与剪辑时间轴状态。"""
    script = store.get_script(script_id)
    if script is None:
        raise ValueError(f"剧本 {script_id} 不存在")

    assets_payload = build_script_assets_payload(
        store, script_id, include_text_content=False
    )
    scan_payload = build_scan_text_assets_payload(store, script_id)

    script_block = dict(assets_payload.get("script") or {})
    content_md = script.content_md or ""
    if len(content_md) > SCRIPT_MD_MAX:
        content_md = content_md[: SCRIPT_MD_MAX - 1] + "…"
    script_block["content_md"] = content_md

    plots = build_plots_for_script(store, script_id)
    assets_with_images = build_assets_with_images_from_scan(
        scan_payload.get("assets", [])
    )

    plan = store.get_video_plan_for_script(script_id)
    timeline = store.get_edit_timeline_for_script(script_id)
    tts_by_shot = build_tts_by_shot(store, script_id)

    shots: list[dict[str, Any]] = []
    if plan:
        for shot in sorted(plan.shots, key=lambda s: s.order):
            shots.append(
                {
                    "id": shot.id,
                    "order": shot.order,
                    "duration_ms": shot.duration_ms,
                    "camera_motion": shot.camera_motion,
                    "narration_text": shot.narration_text,
                    "asset_refs": shot.asset_refs,
                    "variant_refs": shot.variant_refs,
                    "resolved": _resolve_shot_media(store, shot, tts_by_shot),
                }
            )

    timeline_summary: dict[str, Any] | None = None
    shot_gaps: list[dict[str, Any]] = []
    if timeline:
        board = timeline_board_items(store, timeline)
        layer_summary = build_timeline_layer_summary(store, timeline)
        timeline_summary = {
            "timeline_id": timeline.id,
            "revision": timeline.revision,
            "user_edited": timeline.user_edited,
            "duration_ms": board["duration_ms"],
            "video_layers": len(board.get("video_layers", [])),
            "video_clips": len(board["tracks"].get("video", [])),
            "audio_clips": len(board["tracks"].get("audio", [])),
            "subtitle_clips": len(board["tracks"].get("subtitle", [])),
            "layer_summary": layer_summary,
            "locked_clip_ids": [
                c["id"]
                for layer in board.get("video_layers", [])
                for c in layer.get("clips", [])
                if (c.get("metadata") or {}).get("user_locked")
                or (c.get("metadata") or {}).get("edited_by") == "user"
            ]
            + [
                c["id"]
                for track in ("audio", "subtitle")
                for c in board["tracks"].get(track, [])
                if (c.get("metadata") or {}).get("user_locked")
                or (c.get("metadata") or {}).get("edited_by") == "user"
            ],
        }
        covered_shots = {
            str((c.get("metadata") or {}).get("shot_id", "")).strip()
            for layer in board.get("video_layers", [])
            for c in layer.get("clips", [])
            if (c.get("metadata") or {}).get("shot_id")
        }
        for shot in shots:
            if shot["id"] not in covered_shots:
                shot_gaps.append(
                    {
                        "shot_id": shot["id"],
                        "order": shot["order"],
                        "reason": "时间轴缺少该镜头对应 clip",
                    }
                )

    payload: dict[str, Any] = {
        "script_id": script_id,
        "script": script_block,
        "video_plan": {
            "id": plan.id if plan else "",
            "mode": plan.mode.value if plan else None,
            "shot_count": len(shots),
            "shots": shots,
        }
        if plan
        else None,
        "edit_timeline": timeline_summary,
        "shot_gaps": shot_gaps,
        "text_assets": assets_payload.get("text_assets", []),
        "media": assets_payload.get("media", {}),
        "summary": assets_payload.get("summary", {}),
        "plots": plots,
        "plot_count": len(plots),
        "assets_with_images": assets_with_images,
        "linked_image_count": len(assets_with_images),
    }
    if not plan:
        payload["message"] = "尚未保存视频计划稿，请先完成 storyboard persist_plan。"
    return payload
