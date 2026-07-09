"""分镜镜级时间轴解析与句级字幕时间。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from core.edit.subtitle_align import build_cues_for_audio_media, cues_from_media_metadata
from core.edit.timeline import (
    _shot_tts_duration_ms,
    build_tts_by_shot,
    ensure_video_layers,
    flat_video_clips,
)
from core.models.entities import EditClip, EditTimeline, VideoPlan, VideoPlanShot
from core.store.memory import MemoryStore

TimelineSource = Literal["edit_timeline", "plan_estimate"]


@dataclass
class SubtitleLineView:
    """镜内单句字幕时间（含绝对时间轴）。"""

    text: str
    start_ms: int
    end_ms: int
    absolute_start_ms: int
    absolute_end_ms: int

    def to_dict(self) -> dict[str, Any]:
        """序列化为 JSON 友好字典。"""
        return {
            "text": self.text,
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
            "absolute_start_ms": self.absolute_start_ms,
            "absolute_end_ms": self.absolute_end_ms,
        }


@dataclass
class ShotTimingView:
    """单镜在时间轴上的计划与实际区间。"""

    shot_id: str
    order: int
    duration_ms: int
    timeline_start_ms: int
    timeline_end_ms: int
    timeline_source: TimelineSource
    tts_duration_ms: int = 0
    subtitle_lines: list[SubtitleLineView] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """序列化为看板 / Agent 上下文载荷。"""
        return {
            "shot_id": self.shot_id,
            "order": self.order,
            "duration_ms": self.duration_ms,
            "timeline_start_ms": self.timeline_start_ms,
            "timeline_end_ms": self.timeline_end_ms,
            "timeline_source": self.timeline_source,
            "tts_duration_ms": self.tts_duration_ms,
            "subtitle_lines": [line.to_dict() for line in self.subtitle_lines],
        }


def _clip_shot_id(clip: EditClip) -> str:
    """从 clip source_refs 或 metadata 解析 shot_id。"""
    refs = clip.source_refs
    if refs and refs.shot_id:
        return refs.shot_id.strip()
    return str((clip.metadata or {}).get("shot_id") or "").strip()


def _clip_shot_order(clip: EditClip) -> int | None:
    """从 source_refs 或 metadata 解析 video_plan_shot_order。"""
    refs = clip.source_refs
    if refs and refs.video_plan_shot_order is not None:
        return refs.video_plan_shot_order
    raw = (clip.metadata or {}).get("order")
    if raw is not None:
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None
    return None


def _main_video_clips(timeline: EditTimeline) -> list[EditClip]:
    """优先主视频层（z_index=0），否则取全部 video clip。"""
    timeline = ensure_video_layers(timeline)
    main_layer = next(
        (layer for layer in timeline.video_layers if layer.z_index == 0),
        None,
    )
    if main_layer and main_layer.clips:
        return list(main_layer.clips)
    return flat_video_clips(timeline)


def _find_video_clip_for_shot(
    timeline: EditTimeline,
    shot: VideoPlanShot,
) -> EditClip | None:
    """按 shot_id / order 匹配视频 clip。"""
    candidates = _main_video_clips(timeline)
    by_shot: dict[str, EditClip] = {}
    by_order: dict[int, EditClip] = {}
    for clip in candidates:
        sid = _clip_shot_id(clip)
        if sid:
            by_shot.setdefault(sid, clip)
        order = _clip_shot_order(clip)
        if order is not None:
            by_order.setdefault(order, clip)
    if shot.id in by_shot:
        return by_shot[shot.id]
    if shot.order in by_order:
        return by_order[shot.order]
    return None


def _find_audio_clip_for_shot(
    timeline: EditTimeline,
    shot: VideoPlanShot,
    tts_by_shot: dict[str, str],
) -> EditClip | None:
    """按 metadata.shot_id 或 asset_ref 匹配 audio clip。"""
    audio_clips = timeline.tracks.get("audio", [])
    tts_id = tts_by_shot.get(shot.id)
    for clip in audio_clips:
        if _clip_shot_id(clip) == shot.id:
            return clip
        if tts_id and clip.asset_ref == tts_id:
            return clip
    return None


def _estimate_shot_duration_ms(
    store: MemoryStore,
    shot: VideoPlanShot,
    tts_by_shot: dict[str, str],
) -> int:
    """无时间轴时按 plan + TTS 估算镜时长。"""
    duration = max(int(shot.duration_ms or 0), 1000)
    tts_duration = _shot_tts_duration_ms(store, tts_by_shot.get(shot.id))
    if tts_duration > duration:
        duration = tts_duration
    return duration


def _build_subtitle_lines(
    store: MemoryStore,
    shot: VideoPlanShot,
    *,
    audio_clip: EditClip | None,
    video_clip: EditClip | None,
    tts_by_shot: dict[str, str],
) -> list[SubtitleLineView]:
    """解析镜内句级字幕（绝对时间 = audio 起点 + cue 偏移）。"""
    base_ms = 0
    if audio_clip is not None:
        base_ms = audio_clip.start_ms
    elif video_clip is not None:
        base_ms = video_clip.start_ms

    media = None
    audio_ref = (audio_clip.asset_ref if audio_clip else None) or tts_by_shot.get(shot.id)
    if audio_ref:
        media = store.media_assets.get(audio_ref)

    cues: list[dict[str, Any]] = []
    if media:
        cues = cues_from_media_metadata(media)
        if not cues:
            cues = build_cues_for_audio_media(
                store,
                media,
                narration_text=shot.narration_text or "",
            )

    lines: list[SubtitleLineView] = []
    for cue in cues:
        text = str(cue.get("text") or "").strip()
        if not text:
            continue
        rel_start = int(cue.get("start_ms") or 0)
        rel_end = int(cue.get("end_ms") or rel_start + 500)
        lines.append(
            SubtitleLineView(
                text=text,
                start_ms=rel_start,
                end_ms=rel_end,
                absolute_start_ms=base_ms + rel_start,
                absolute_end_ms=base_ms + rel_end,
            )
        )
    return lines


def resolve_shot_timings(
    store: MemoryStore,
    script_id: str,
    *,
    plan: VideoPlan | None = None,
    timeline: EditTimeline | None = None,
) -> list[ShotTimingView]:
    """解析每镜时间轴区间与句级字幕；有 EditTimeline 时以 clip 为准。"""
    if plan is None:
        plan = store.get_video_plan_for_script(script_id)
    if not plan or not plan.shots:
        return []
    if timeline is None:
        timeline = store.get_edit_timeline_for_script(script_id)

    tts_by_shot = build_tts_by_shot(store, script_id)
    shots = sorted(plan.shots, key=lambda s: s.order)
    views: list[ShotTimingView] = []
    cursor = 0

    for shot in shots:
        video_clip = _find_video_clip_for_shot(timeline, shot) if timeline else None
        audio_clip = _find_audio_clip_for_shot(timeline, shot, tts_by_shot) if timeline else None
        tts_duration = _shot_tts_duration_ms(store, tts_by_shot.get(shot.id))

        if video_clip is not None:
            start_ms = video_clip.start_ms
            end_ms = video_clip.end_ms
            source: TimelineSource = "edit_timeline"
        else:
            duration = _estimate_shot_duration_ms(store, shot, tts_by_shot)
            start_ms = cursor
            end_ms = cursor + duration
            source = "plan_estimate"
            cursor = end_ms

        subtitle_lines = _build_subtitle_lines(
            store,
            shot,
            audio_clip=audio_clip,
            video_clip=video_clip,
            tts_by_shot=tts_by_shot,
        )

        views.append(
            ShotTimingView(
                shot_id=shot.id,
                order=shot.order,
                duration_ms=int(shot.duration_ms or 0),
                timeline_start_ms=start_ms,
                timeline_end_ms=end_ms,
                timeline_source=source,
                tts_duration_ms=tts_duration,
                subtitle_lines=subtitle_lines,
            )
        )

    return views
