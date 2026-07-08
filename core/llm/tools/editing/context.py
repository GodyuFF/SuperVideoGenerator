"""editing_agent load_edit_context 结构化载荷（精简版：仅剪辑所需核心信息）。"""

from __future__ import annotations

from typing import Any

from core.edit.timeline import build_tts_by_shot, resolve_shot_image_ref
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
    """分镜 VideoPlan、已有资源、剪辑时间轴状态（精简输出：仅包含剪辑所需的核心信息）。"""
    script = store.get_script(script_id)
    if script is None:
        raise ValueError(f"剧本 {script_id} 不存在")

    content_md = script.content_md or ""
    if len(content_md) > SCRIPT_MD_MAX:
        content_md = content_md[: SCRIPT_MD_MAX - 1] + "…"

    script_block = {
        "id": script.id,
        "title": script.title,
        "duration_sec": script.duration_sec,
        "content_md": content_md,
    }

    # 精简 plots：仅保留 id + 摘要首行
    plots: list[dict[str, Any]] = []
    for asset in sorted(
        store.list_assets_for_script(script_id),
        key=lambda a: (a.type.value, a.name),
    ):
        if asset.type.value not in ("plot", "narration"):
            continue
        content = asset.content if isinstance(asset.content, dict) else {}
        text = str(content.get("text", "") or content.get("summary", "")).strip()
        if not text and isinstance(asset.content, str):
            text = asset.content.strip()
        text = text[:200]
        plots.append({"id": asset.id, "name": asset.name, "type": asset.type.value, "text": text})

    # 已链接图片资产摘要（仅 clip 引用需要的 id/name/type/media_id）
    assets_with_images: list[dict[str, Any]] = []
    for a in store.list_assets_for_script(script_id):
        if a.type.value not in ("character", "scene", "prop"):
            continue
        if not a.primary_media_id:
            continue
        media = store.media_assets.get(a.primary_media_id)
        if not media or not media.url or str(media.url).startswith("placeholder:"):
            continue
        from core.llm.tools.shared.media_list import resolve_media_access
        accessible = resolve_media_access(media.url).get("is_accessible", False)
        from core.models.image_text_asset import normalize_image_text_content
        nc = normalize_image_text_content(a.type, a.content)
        assets_with_images.append({
            "id": a.id,
            "name": a.name,
            "type": a.type.value,
            "media_id": a.primary_media_id,
            "accessible": accessible,
            "summary": str(nc.get("summary", "") or nc.get("description", "") or "").strip()[:120],
        })

    # VideoPlan
    plan = store.get_video_plan_for_script(script_id)
    tts_by_shot = build_tts_by_shot(store, script_id)
    shots: list[dict[str, Any]] = []
    if plan:
        for shot in sorted(plan.shots, key=lambda s: s.order):
            image_id = resolve_shot_image_ref(store, shot)
            audio_id = tts_by_shot.get(shot.id)
            from core.llm.tools.shared.media_list import resolve_media_access

            def _accessible(mid: str | None) -> bool:
                if not mid:
                    return False
                m = store.media_assets.get(mid)
                return bool(m and resolve_media_access(m.url).get("is_accessible"))

            shots.append({
                "id": shot.id,
                "order": shot.order,
                "duration_ms": shot.duration_ms,
                "camera_motion": shot.camera_motion,
                "narration_text": (shot.narration_text or "").strip()[:200],
                "asset_refs": shot.asset_refs,
                "image_media_id": image_id,
                "image_accessible": _accessible(image_id),
                "audio_media_id": audio_id,
                "audio_accessible": _accessible(audio_id),
            })

    # 时间轴摘要（精简：仅 id + 各轨 clip 数 + 时长 + layer 信息）
    timeline = store.get_edit_timeline_for_script(script_id)
    timeline_summary: dict[str, Any] | None = None
    shot_gaps: list[dict[str, Any]] = []
    if timeline:
        from core.edit.timeline import ensure_video_layers

        timeline = ensure_video_layers(timeline)
        video_layers_info = []
        for layer in sorted(timeline.video_layers, key=lambda l: l.z_index):  # type: ignore
            video_layers_info.append({
                "z_index": layer.z_index,
                "name": layer.name,
                "clip_count": len(layer.clips),
                "clip_ids": [c.id for c in layer.clips],
            })
        timeline_summary = {
            "timeline_id": timeline.id,
            "revision": timeline.revision,
            "user_edited": timeline.user_edited,
            "duration_ms": timeline.duration_ms,
            "video_layers": video_layers_info,
            "audio_clips": len(timeline.tracks.get("audio", [])),
            "subtitle_clips": len(timeline.tracks.get("subtitle", [])),
        }
        # 未被覆盖的镜头
        covered = set()
        for layer in timeline.video_layers:  # type: ignore
            for c in layer.clips:
                sid = str((c.metadata or {}).get("shot_id", "")).strip()
                if sid:
                    covered.add(sid)
        for shot in shots:
            if shot["id"] not in covered:
                shot_gaps.append({"shot_id": shot["id"], "order": shot["order"], "reason": "时间轴缺少该镜头"})

    # 可用媒体数量摘要
    media_counts: dict[str, int] = {}
    for m in store.list_media_for_script(script_id):
        media_counts[m.type.value] = media_counts.get(m.type.value, 0) + 1

    payload: dict[str, Any] = {
        "script": script_block,
        "video_plan": {
            "id": plan.id if plan else "",
            "shot_count": len(shots),
            "shots": shots,
        } if plan else None,
        "edit_timeline": timeline_summary,
        "shot_gaps": shot_gaps,
        "plots": plots,
        "plot_count": len(plots),
        "assets_with_images": assets_with_images,
        "linked_image_count": len(assets_with_images),
        "media_counts": media_counts,
    }
    if not plan:
        payload["message"] = "尚未保存视频计划稿，请先完成 storyboard persist_plan。"
    return payload
