"""分镜复核只读查询：分镜详情与镜内轨道资产时长（新模型）。"""

from __future__ import annotations

from typing import Any, Literal

from core.edit.shot_flatten import effective_shot_duration_ms, shot_offsets
from core.edit.subtitle_align import build_cues_for_audio_media, cues_from_media_metadata
from core.edit.timeline import shot_tts_duration_info
from core.llm.tools.shared.media_list import resolve_media_access
from core.edit.sub_shot_helpers import (
    first_sub_shot_image,
    sub_shot_has_frame_link,
    sub_shot_has_video_clip_link,
)
from core.models.entities import Shot, VideoPlan
from core.models.image_text_asset import FrameContent, normalize_image_text_content
from core.store.memory import MemoryStore

AssetKind = Literal["audio", "video", "all"]


def _resolve_shot_filter(
    plan: VideoPlan,
    *,
    shot_id: str | None = None,
    shot_ids: list[str] | None = None,
) -> tuple[list[Shot], list[str]]:
    """按 shot_id / shot_ids 过滤镜头，返回 warnings。"""
    all_shots = sorted(plan.shots, key=lambda s: s.order)
    warnings: list[str] = []
    if shot_id and str(shot_id).strip():
        sid = str(shot_id).strip()
        matched = [s for s in all_shots if s.id == sid]
        if not matched:
            warnings.append(f"未知 shot_id：{sid}")
        return matched, warnings
    if shot_ids:
        wanted = {str(x).strip() for x in shot_ids if x}
        matched = [s for s in all_shots if s.id in wanted]
        unknown = wanted - {s.id for s in matched}
        for sid in sorted(unknown):
            warnings.append(f"未知 shot_id：{sid}")
        return matched, warnings
    return all_shots, warnings


def _sub_shot_has_media(store: MemoryStore, sub) -> bool:
    """判断子镜是否已有可用配图或视频 media。"""
    img = first_sub_shot_image(sub)
    if img and img.media_id:
        media = store.media_assets.get(img.media_id)
        if media and media.url:
            return True
    if img and img.frame_asset_id:
        frame_asset = store.text_assets.get(img.frame_asset_id)
        if frame_asset and frame_asset.primary_media_id:
            return True
    for vid in sub.videos:
        if vid.media_id and store.media_assets.get(vid.media_id):
            return True
    return False


def _sub_shot_has_video_media(store: MemoryStore, sub) -> bool:
    """判断子镜是否已有可用视频 media（含经 video_clip 资产回填）。"""
    from core.llm.tools.video.source_urls import video_clip_asset_preview_url

    for vid in sub.videos:
        if vid.media_id:
            media = store.media_assets.get(vid.media_id)
            if media and media.url:
                return True
        cid = vid.video_clip_asset_id.strip()
        if cid and video_clip_asset_preview_url(store, cid):
            return True
    return False


def _sub_shot_image_state(
    store: MemoryStore,
    shot: Shot,
) -> tuple[str, bool, list[dict[str, Any]]]:
    """返回子镜摘要、镜级是否全部有图、子镜级缺图列表。"""
    if not shot.sub_shots:
        return "", False, [
            {
                "shot_id": shot.id,
                "sub_shot_id": "",
                "missing_frame": True,
                "missing_media": True,
            }
        ]
    summary_parts: list[str] = []
    sub_gaps: list[dict[str, Any]] = []
    all_have_media = True
    for sub in shot.sub_shots:
        summary_parts.append(sub.description[:60] if sub.description else "")
        img = first_sub_shot_image(sub)
        if img and img.frame_asset_id:
            frame_asset = store.text_assets.get(img.frame_asset_id)
            if frame_asset:
                try:
                    content = FrameContent.model_validate(
                        normalize_image_text_content(frame_asset.type, frame_asset.content)
                    )
                    if content.composition_prompt:
                        summary_parts[-1] += f" · {content.composition_prompt[:80]}"
                except Exception:
                    pass
        missing_frame = not sub_shot_has_frame_link(sub)
        missing_media = not _sub_shot_has_media(store, sub)
        if missing_frame or missing_media:
            sub_gaps.append(
                {
                    "shot_id": shot.id,
                    "sub_shot_id": sub.id,
                    "missing_frame": missing_frame,
                    "missing_media": missing_media,
                }
            )
        if missing_media:
            all_have_media = False
    summary = " / ".join(p for p in summary_parts if p)
    return summary, all_have_media, sub_gaps


def _sub_shot_video_state(
    store: MemoryStore,
    shot: Shot,
) -> tuple[str, bool, list[dict[str, Any]]]:
    """返回子镜视频摘要、镜级是否全部有视频成片、子镜级缺视频列表。"""
    if not shot.sub_shots:
        return "", False, [
            {
                "shot_id": shot.id,
                "sub_shot_id": "",
                "missing_video_clip": True,
                "missing_video_media": True,
            }
        ]
    summary_parts: list[str] = []
    sub_gaps: list[dict[str, Any]] = []
    all_have_media = True
    for sub in shot.sub_shots:
        summary_parts.append(sub.description[:60] if sub.description else "")
        for vid in sub.videos:
            if vid.video_clip_asset_id.strip():
                clip_asset = store.text_assets.get(vid.video_clip_asset_id.strip())
                if clip_asset:
                    prompt = str(
                        (clip_asset.content or {}).get("video_prompt")
                        or (clip_asset.content or {}).get("summary")
                        or ""
                    ).strip()
                    if prompt:
                        summary_parts[-1] += f" · {prompt[:80]}"
        missing_video_clip = not sub_shot_has_video_clip_link(sub)
        missing_video_media = not _sub_shot_has_video_media(store, sub)
        if missing_video_clip or missing_video_media:
            sub_gaps.append(
                {
                    "shot_id": shot.id,
                    "sub_shot_id": sub.id,
                    "missing_video_clip": missing_video_clip,
                    "missing_video_media": missing_video_media,
                }
            )
        if missing_video_media:
            all_have_media = False
    summary = " / ".join(p for p in summary_parts if p)
    return summary, all_have_media, sub_gaps


def _serialize_shot_tracks(shot: Shot) -> dict[str, Any]:
    """序列化镜内多轨结构摘要。"""
    return {
        "sub_shots": [
            {
                "id": v.id,
                "start_ms": v.start_ms,
                "end_ms": v.end_ms,
                "description": v.description,
                "camera_motion": v.camera_motion,
                "element_refs": v.element_refs,
                "images": [i.model_dump() for i in v.images],
                "videos": [vid.model_dump() for vid in v.videos],
            }
            for v in shot.sub_shots
        ],
        "video_tracks": [t.model_dump() for t in shot.video_tracks],
        "audio_tracks": [t.model_dump() for t in shot.audio_tracks],
        "subtitles": [s.model_dump() for s in shot.subtitles],
    }


def serialize_shots_for_agent(shots: list[Shot]) -> list[dict[str, Any]]:
    """序列化镜头摘要：shot/sub_shot ID，以及已关联的 frame / video_clip / source_frame。"""
    payload: list[dict[str, Any]] = []
    for shot in sorted(shots, key=lambda s: s.order):
        sub_payload: list[dict[str, Any]] = []
        for sub in shot.sub_shots:
            images = [
                {"frame_asset_id": fid}
                for img in sub.images
                if (fid := (img.frame_asset_id or "").strip())
            ]
            videos = []
            for vid in sub.videos:
                clip_id = (vid.video_clip_asset_id or "").strip()
                src_id = (vid.source_frame_asset_id or "").strip()
                if not clip_id and not src_id:
                    continue
                videos.append(
                    {
                        "video_clip_asset_id": clip_id,
                        "source_frame_asset_id": src_id,
                    }
                )
            block: dict[str, Any] = {
                "id": sub.id,
                "start_ms": sub.start_ms,
                "end_ms": sub.end_ms,
                "description": (sub.description or "")[:120],
            }
            if images:
                block["images"] = images
            if videos:
                block["videos"] = videos
            sub_payload.append(block)
        payload.append(
            {
                "id": shot.id,
                "order": shot.order,
                "duration_ms": shot.duration_ms,
                "sub_shots": sub_payload,
            }
        )
    return payload


def _shot_media_ready(shot: Shot) -> bool:
    """镜内所有视频/音频 clip 是否均已绑定 media。"""
    from core.edit.shot_validate import validate_shots_render_ready

    return not validate_shots_render_ready([shot])


def build_shot_details_query(
    store: MemoryStore,
    script_id: str,
    *,
    shot_id: str | None = None,
    shot_ids: list[str] | None = None,
) -> dict[str, Any]:
    """查询分镜详情：镜内多轨结构 + 子镜配图状态 + 复核字段。"""
    script = store.get_script(script_id)
    if script is None:
        raise ValueError(f"剧本 {script_id} 不存在")
    plan = store.get_video_plan_for_script(script_id)
    if not plan or not plan.shots:
        raise ValueError("未找到视频计划稿")

    filtered, warnings = _resolve_shot_filter(plan, shot_id=shot_id, shot_ids=shot_ids)
    shots_payload: list[dict[str, Any]] = []
    image_gaps: list[str] = []
    image_gap_sub_shots: list[dict[str, Any]] = []
    video_gaps: list[str] = []
    video_gap_sub_shots: list[dict[str, Any]] = []

    for shot in filtered:
        frame_summary, has_image, sub_gaps = _sub_shot_image_state(store, shot)
        video_summary, has_video, video_sub_gaps = _sub_shot_video_state(store, shot)
        if sub_gaps:
            image_gaps.append(shot.id)
            image_gap_sub_shots.extend(sub_gaps)
        if video_sub_gaps:
            video_gaps.append(shot.id)
            video_gap_sub_shots.extend(video_sub_gaps)
        block: dict[str, Any] = {
            "id": shot.id,
            "order": shot.order,
            "duration_ms": shot.duration_ms,
            "title": shot.title,
            "summary": shot.summary,
            "frame_summary": frame_summary,
            "has_frame_image": has_image,
            "sub_shot_gaps": sub_gaps,
            "video_summary": video_summary,
            "has_video_clip": has_video,
            "sub_shot_video_gaps": video_sub_gaps,
            "media_ready": _shot_media_ready(shot),
            "review_revision": shot.review_revision,
            "review_note": shot.review_note,
            "need_regen": shot.need_regen,
            "regen_reason": shot.regen_reason,
            "sync_policy": shot.sync_policy,
            "lip_sync_required": shot.lip_sync_required,
            "sync_notes": shot.sync_notes,
            "proposed_sync_actions": list(shot.proposed_sync_actions or []),
        }
        block.update(_serialize_shot_tracks(shot))
        shots_payload.append(block)

    return {
        "script_id": script_id,
        "plan_id": plan.id,
        "detail_revision": plan.detail_revision,
        "shot_count": len(shots_payload),
        "shots": shots_payload,
        "image_gap_shot_ids": image_gaps,
        "image_gap_sub_shots": image_gap_sub_shots,
        "video_gap_shot_ids": video_gaps,
        "video_gap_sub_shots": video_gap_sub_shots,
        "review_ready": not image_gaps,
        "warnings": warnings,
    }


def _audio_clip_text_segments(store: MemoryStore, shot: Shot) -> list[dict[str, Any]]:
    """解析镜内 voice 音频各时段对应文字（clip.text 优先，其次 media cue）。"""
    segments: list[dict[str, Any]] = []
    for track in shot.audio_tracks:
        if track.kind != "voice":
            continue
        for clip in track.clips:
            if clip.text:
                segments.append(
                    {"start_ms": clip.start_ms, "end_ms": clip.end_ms, "text": clip.text}
                )
                continue
            if clip.media_id:
                media = store.media_assets.get(clip.media_id)
                cues = cues_from_media_metadata(media) if media else []
                if not cues and media:
                    cues = build_cues_for_audio_media(store, media)
                for c in cues:
                    text = str(c.get("text") or "").strip()
                    if text:
                        segments.append(
                            {
                                "start_ms": clip.start_ms + int(c.get("start_ms") or 0),
                                "end_ms": clip.start_ms + int(c.get("end_ms") or 0),
                                "text": text,
                            }
                        )
    return segments


def build_shot_asset_timing_query(
    store: MemoryStore,
    script_id: str,
    *,
    shot_id: str | None = None,
    shot_ids: list[str] | None = None,
    asset_kind: AssetKind = "all",
) -> dict[str, Any]:
    """查询镜头镜内音频/视频 clip 时长与实测偏差；音频含各时段文字。"""
    script = store.get_script(script_id)
    if script is None:
        raise ValueError(f"剧本 {script_id} 不存在")
    plan = store.get_video_plan_for_script(script_id)
    if not plan or not plan.shots:
        raise ValueError("未找到视频计划稿")

    kind = asset_kind if asset_kind in ("audio", "video", "all") else "all"
    filtered, warnings = _resolve_shot_filter(plan, shot_id=shot_id, shot_ids=shot_ids)
    offsets = shot_offsets(plan.shots)

    shots_payload: list[dict[str, Any]] = []
    for shot in filtered:
        start_ms = offsets.get(shot.id, 0)
        duration = effective_shot_duration_ms(shot)
        assets: dict[str, Any] = {}
        probed_ms = 0

        if kind in ("audio", "all"):
            voice_clip = None
            for track in shot.audio_tracks:
                if track.kind == "voice" and track.clips:
                    voice_clip = track.clips[0]
                    break
            if voice_clip and voice_clip.media_id:
                media = store.media_assets.get(voice_clip.media_id)
                info = shot_tts_duration_info(store, voice_clip.media_id)
                probed_ms = int(info.get("duration_ms") or 0)
                accessible = bool(media and resolve_media_access(media.url).get("is_accessible"))
                assets["audio"] = {
                    "media_id": voice_clip.media_id,
                    "duration_ms": probed_ms,
                    "clip_span_ms": voice_clip.end_ms - voice_clip.start_ms,
                    "duration_source": str(info.get("duration_source") or "none"),
                    "metadata_duration_ms": int(info.get("metadata_duration_ms") or 0),
                    "accessible": accessible,
                    "text_segments": _audio_clip_text_segments(store, shot),
                }

        if kind in ("video", "all"):
            video_clip = None
            for track in sorted(shot.video_tracks, key=lambda t: t.z_index):
                if track.clips:
                    video_clip = track.clips[0]
                    break
            if video_clip:
                assets["video"] = {
                    "media_id": video_clip.media_id,
                    "source_kind": video_clip.source_kind,
                    "duration_ms": video_clip.end_ms - video_clip.start_ms,
                }

        shots_payload.append(
            {
                "shot_id": shot.id,
                "order": shot.order,
                "planned_duration_ms": shot.duration_ms,
                "actual_duration_ms": probed_ms if probed_ms > 0 else duration,
                "timeline_start_ms": start_ms,
                "timeline_end_ms": start_ms + duration,
                "assets": assets,
            }
        )

    return {
        "script_id": script_id,
        "plan_id": plan.id,
        "detail_revision": plan.detail_revision,
        "shot_count": len(shots_payload),
        "asset_kind": kind,
        "shots": shots_payload,
        "warnings": warnings,
    }
