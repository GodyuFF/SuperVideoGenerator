"""分镜镜级时间轴解析与句级字幕时间（新模型：直接来自镜内多轨结构）。

镜内结构为权威源：镜时长由 shot_flatten.effective_shot_duration_ms 计算，全局偏移由
shot_flatten.shot_offsets 累加；句级字幕直接来自 Shot.subtitles。无 TTS 对齐推断/降级。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from core.edit.shot_flatten import effective_shot_duration_ms, shot_offsets
from core.models.entities import EditClip, EditTimeline, Shot, VideoPlan
from core.store.memory import MemoryStore

TimelineSource = Literal["edit_timeline", "plan_estimate"]

# EditTimeline 与镜内累加时长对齐容差（毫秒）
PLAN_ALIGN_TOLERANCE_MS = 200


@dataclass
class SubtitleLineView:
    """镜内单句字幕时间（含绝对时间轴）。"""

    text: str
    start_ms: int
    end_ms: int
    absolute_start_ms: int
    absolute_end_ms: int
    character: str = ""
    color: str = ""

    def to_dict(self) -> dict[str, Any]:
        """序列化为 JSON 友好字典。"""
        return {
            "text": self.text,
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
            "absolute_start_ms": self.absolute_start_ms,
            "absolute_end_ms": self.absolute_end_ms,
            "character": self.character,
            "color": self.color,
        }


@dataclass
class ShotTimingView:
    """单镜在时间轴上的区间与句级字幕。"""

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
    main_layer = next(
        (layer for layer in timeline.video_layers if layer.z_index == 0),
        None,
    )
    if main_layer and main_layer.clips:
        return list(main_layer.clips)
    out: list[EditClip] = []
    for layer in sorted(timeline.video_layers, key=lambda item: item.z_index):
        out.extend(layer.clips)
    return out


def _find_video_clip_for_shot(timeline: EditTimeline, shot: Shot) -> EditClip | None:
    """按 shot_id / order 匹配视频 clip（取该镜最早的主层片段）。"""
    candidates = _main_video_clips(timeline)
    by_shot: dict[str, EditClip] = {}
    by_order: dict[int, EditClip] = {}
    for clip in sorted(candidates, key=lambda c: c.start_ms):
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
    shot: Shot,
    tts_by_shot: dict[str, str] | None = None,
) -> EditClip | None:
    """按 shot_id 或 asset_ref 匹配 audio clip（取该镜最早片段）。"""
    tts_by_shot = tts_by_shot or {}
    tts_id = tts_by_shot.get(shot.id)
    for clip in sorted(timeline.tracks.get("audio", []), key=lambda c: c.start_ms):
        if _clip_shot_id(clip) == shot.id:
            return clip
        if tts_id and clip.asset_ref == tts_id:
            return clip
    return None


def _shot_voice_duration_ms(shot: Shot) -> int:
    """镜内配音（voice 轨）最大片段跨度，供展示 TTS 时长。"""
    best = 0
    for track in shot.audio_tracks:
        if track.kind != "voice":
            continue
        for clip in track.clips:
            best = max(best, int(clip.end_ms or 0) - int(clip.start_ms or 0))
    return max(best, 0)


def _build_subtitle_lines(
    shot: Shot,
    *,
    offset_ms: int,
) -> list[SubtitleLineView]:
    """把 Shot.subtitles 转为含绝对时间的句级字幕视图。"""
    lines: list[SubtitleLineView] = []
    for sub in sorted(shot.subtitles, key=lambda s: s.start_ms):
        text = (sub.text or "").strip()
        if not text:
            continue
        rel_start = int(sub.start_ms or 0)
        rel_end = int(sub.end_ms or rel_start + 500)
        lines.append(
            SubtitleLineView(
                text=text,
                start_ms=rel_start,
                end_ms=rel_end,
                absolute_start_ms=offset_ms + rel_start,
                absolute_end_ms=offset_ms + rel_end,
                character=(sub.character or "").strip(),
                color=(sub.color or "").strip(),
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
    """解析每镜时间轴区间与句级字幕（镜内结构为权威源，确定性累加）。"""
    del timeline  # 权威源为镜内结构，不再从 EditTimeline 反推
    if plan is None:
        plan = store.get_video_plan_for_script(script_id)
    if not plan or not plan.shots:
        return []
    shots = sorted(plan.shots, key=lambda s: s.order)
    offsets = shot_offsets(shots)
    views: list[ShotTimingView] = []
    for shot in shots:
        start_ms = offsets[shot.id]
        duration = effective_shot_duration_ms(shot)
        views.append(
            ShotTimingView(
                shot_id=shot.id,
                order=shot.order,
                duration_ms=duration,
                timeline_start_ms=start_ms,
                timeline_end_ms=start_ms + duration,
                timeline_source="plan_estimate",
                tts_duration_ms=_shot_voice_duration_ms(shot),
                subtitle_lines=_build_subtitle_lines(shot, offset_ms=start_ms),
            )
        )
    return views
