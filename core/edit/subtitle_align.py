"""字幕轨与 TTS audio 对齐（标点拆分 + cue 时间戳）。"""

from __future__ import annotations

from typing import Any

from core.edit.asset_resolver import resolve_clip_media
from core.edit.timeline import _parse_clip_from_raw
from core.models.entities import EditClip, EditTimeline, MediaAssetType, VideoPlan
from core.store.memory import MemoryStore
from core.tts.subtitle import (
    populate_legacy_submaker_with_full_text,
    subtitle_clips_from_cues,
    subtitle_cues_from_submaker,
)
from edge_tts import SubMaker


def cues_from_media_metadata(media) -> list[dict[str, Any]]:
    """从 MediaAsset.metadata 读取 subtitle_cues。"""
    raw = (media.metadata or {}).get("subtitle_cues")
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, dict) and item.get("text"):
            out.append(dict(item))
    return out


def build_cues_for_audio_media(
    store: MemoryStore,
    media,
    *,
    narration_text: str = "",
) -> list[dict[str, Any]]:
    """无持久化 cues 时，按标点 + 时长比例生成 fallback cues。"""
    cues = cues_from_media_metadata(media)
    if cues:
        return cues
    text = narration_text.strip() or str((media.metadata or {}).get("narration_text") or "").strip()
    if not text:
        return []
    duration_ms = int((media.metadata or {}).get("duration_ms") or 0)
    if duration_ms <= 0:
        return [{"start_ms": 0, "end_ms": 1000, "text": text}]
    duration_sec = max(duration_ms / 1000.0, 0.1)
    sub_maker = populate_legacy_submaker_with_full_text(SubMaker(), text, duration_sec)
    return subtitle_cues_from_submaker(sub_maker)


def enrich_subtitles_from_audio(
    store: MemoryStore,
    timeline: EditTimeline,
    plan: VideoPlan | None = None,
) -> EditTimeline:
    """按 audio 轨 TTS cues 生成/补齐 subtitle 轨（不覆盖 user_locked clip）。"""
    from core.edit.timeline import _clip_is_user_protected

    audio_clips = list(timeline.tracks.get("audio", []))
    if not audio_clips:
        return timeline

    if plan is None:
        plan = store.get_video_plan_for_script(timeline.script_id)
    shot_by_id = {s.id: s for s in plan.shots} if plan and plan.shots else {}
    narration_by_shot = {
        s.id: (s.narration_text or "").strip() for s in (plan.shots if plan else [])
    }

    generated_raw: list[dict[str, Any]] = []
    for audio_clip in sorted(audio_clips, key=lambda c: (c.start_ms, c.end_ms)):
        if not audio_clip.asset_ref:
            resolved = resolve_clip_media(
                store,
                audio_clip,
                script_id=timeline.script_id,
                shot_by_id=shot_by_id,
            )
            media_id = resolved.media_id if resolved else None
        else:
            media_id = audio_clip.asset_ref
        if not media_id:
            continue
        media = store.media_assets.get(media_id)
        if not media or media.type != MediaAssetType.AUDIO:
            continue
        shot_id = str((audio_clip.metadata or {}).get("shot_id") or "").strip()
        if not shot_id and media.metadata:
            shot_id = str((media.metadata or {}).get("shot_id") or "").strip()
        narration = narration_by_shot.get(shot_id, "") or audio_clip.label or ""
        cues = build_cues_for_audio_media(store, media, narration_text=narration)
        offset_ms = int(audio_clip.start_ms)
        generated_raw.extend(
            subtitle_clips_from_cues(cues, offset_ms=offset_ms, shot_id=shot_id)
        )

    if not generated_raw:
        return timeline

    generated: list[EditClip] = []
    for raw in generated_raw:
        clip = _parse_clip_from_raw(raw, track="subtitle")
        if clip:
            generated.append(clip)
    generated.sort(key=lambda c: (c.start_ms, c.end_ms))

    existing = list(timeline.tracks.get("subtitle", []))
    if not existing:
        tracks = dict(timeline.tracks)
        tracks["subtitle"] = generated
        return timeline.model_copy(update={"tracks": tracks})

    protected = [c for c in existing if _clip_is_user_protected(c)]
    if protected and len(protected) == len(existing):
        return timeline

    if not protected:
        tracks = dict(timeline.tracks)
        tracks["subtitle"] = generated
        return timeline.model_copy(update={"tracks": tracks})

    covered_ranges = {(c.start_ms, c.end_ms) for c in protected}
    merged = list(protected)
    for clip in generated:
        overlap = any(
            not (clip.end_ms <= start or clip.start_ms >= end)
            for start, end in covered_ranges
        )
        if overlap:
            continue
        merged.append(clip)
    merged.sort(key=lambda c: (c.start_ms, c.end_ms))
    tracks = dict(timeline.tracks)
    tracks["subtitle"] = merged
    return timeline.model_copy(update={"tracks": tracks})
