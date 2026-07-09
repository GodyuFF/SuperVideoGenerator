"""剪辑时间轴时间段分析与优化建议。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from core.edit.asset_resolver import validate_edit_timeline
from core.edit.edit_capabilities import edit_capability_issues
from core.edit.shot_timing import resolve_shot_timings
from core.edit.timeline import (
    build_timeline_layer_summary,
    ensure_video_layers,
    flat_video_clips,
    timeline_duration_ms,
    validate_timeline_clips,
)
from core.models.entities import EditClip, EditTimeline
from core.store.memory import MemoryStore

DURATION_MISMATCH_THRESHOLD_MS = 500

TrackKind = Literal["video", "audio", "subtitle"]


@dataclass
class AnalyzeTimelineRequest:
    """时间段分析请求参数。"""

    start_ms: int | None = None
    end_ms: int | None = None
    tracks: list[str] | None = None
    layer_ids: list[str] | None = None
    include_hints: bool = True
    include_shot_alignment: bool = True


@dataclass
class AnalyzeTimelineResult:
    """时间段分析结果。"""

    range: dict[str, int]
    clips_in_range: list[dict[str, Any]] = field(default_factory=list)
    gaps: list[dict[str, Any]] = field(default_factory=list)
    overlaps: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    missing_assets: list[dict[str, Any]] = field(default_factory=list)
    shot_alignment: list[dict[str, Any]] = field(default_factory=list)
    optimization_hints: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """序列化为 API / Tool 响应。"""
        return {
            "range": self.range,
            "clips_in_range": self.clips_in_range,
            "gaps": self.gaps,
            "overlaps": self.overlaps,
            "warnings": self.warnings,
            "missing_assets": self.missing_assets,
            "shot_alignment": self.shot_alignment,
            "optimization_hints": self.optimization_hints,
        }


def _clip_intersects_range(clip: EditClip, start_ms: int, end_ms: int) -> bool:
    """判断 clip 是否与 [start_ms, end_ms) 相交。"""
    return clip.start_ms < end_ms and clip.end_ms > start_ms


def _clip_partial_in_range(clip: EditClip, start_ms: int, end_ms: int) -> bool:
    """clip 与区间相交但不完全包含。"""
    if not _clip_intersects_range(clip, start_ms, end_ms):
        return False
    return clip.start_ms < start_ms or clip.end_ms > end_ms


def _serialize_clip_in_range(
    clip: EditClip,
    *,
    track: str,
    layer_id: str | None,
    range_start: int,
    range_end: int,
) -> dict[str, Any]:
    """输出与区间相交的 clip 摘要。"""
    shot_id = ""
    if clip.source_refs and clip.source_refs.shot_id:
        shot_id = clip.source_refs.shot_id
    elif clip.metadata:
        shot_id = str(clip.metadata.get("shot_id") or "")
    return {
        "id": clip.id,
        "track": track,
        "layer_id": layer_id,
        "start_ms": clip.start_ms,
        "end_ms": clip.end_ms,
        "label": clip.label,
        "asset_ref": clip.asset_ref,
        "shot_id": shot_id,
        "partial": _clip_partial_in_range(clip, range_start, range_end),
    }


def _scan_gaps_for_clips(
    clips: list[EditClip],
    range_start: int,
    range_end: int,
    *,
    track: str,
    layer_id: str | None = None,
) -> list[dict[str, Any]]:
    """扫描 sorted clips 在区间内的空白段。"""
    gaps: list[dict[str, Any]] = []
    sorted_clips = sorted(clips, key=lambda c: (c.start_ms, c.end_ms))
    relevant = [c for c in sorted_clips if _clip_intersects_range(c, range_start, range_end)]
    if not relevant:
        if range_end > range_start:
            gaps.append(
                {
                    "track": track,
                    "layer_id": layer_id,
                    "start_ms": range_start,
                    "end_ms": range_end,
                    "duration_ms": range_end - range_start,
                }
            )
        return gaps

    first = relevant[0]
    if first.start_ms > range_start:
        gaps.append(
            {
                "track": track,
                "layer_id": layer_id,
                "start_ms": range_start,
                "end_ms": first.start_ms,
                "duration_ms": first.start_ms - range_start,
            }
        )

    for prev, nxt in zip(relevant, relevant[1:]):
        gap_start = max(prev.end_ms, range_start)
        gap_end = min(nxt.start_ms, range_end)
        if gap_end > gap_start:
            gaps.append(
                {
                    "track": track,
                    "layer_id": layer_id,
                    "start_ms": gap_start,
                    "end_ms": gap_end,
                    "duration_ms": gap_end - gap_start,
                }
            )

    last = relevant[-1]
    if last.end_ms < range_end:
        gaps.append(
            {
                "track": track,
                "layer_id": layer_id,
                "start_ms": last.end_ms,
                "end_ms": range_end,
                "duration_ms": range_end - last.end_ms,
            }
        )
    return gaps


def _filter_overlaps_to_range(
    overlaps: list[dict[str, Any]],
    range_start: int,
    range_end: int,
    timeline: EditTimeline,
) -> list[dict[str, Any]]:
    """将同层重叠过滤到分析区间。"""
    clip_by_id: dict[str, EditClip] = {}
    timeline = ensure_video_layers(timeline)
    for layer in timeline.video_layers:
        for clip in layer.clips:
            clip_by_id[clip.id] = clip
    for track in ("audio", "subtitle"):
        for clip in timeline.tracks.get(track, []):
            clip_by_id[clip.id] = clip

    out: list[dict[str, Any]] = []
    for item in overlaps:
        clip = clip_by_id.get(str(item.get("clip_id") or ""))
        if clip and _clip_intersects_range(clip, range_start, range_end):
            out.append(dict(item))
    return out


def _filter_missing_to_range(
    report_dict: dict[str, Any],
    timeline: EditTimeline,
    range_start: int,
    range_end: int,
) -> list[dict[str, Any]]:
    """过滤区间内 clip 相关的缺失素材项。"""
    clip_by_id: dict[str, EditClip] = {}
    timeline = ensure_video_layers(timeline)
    for layer in timeline.video_layers:
        for clip in layer.clips:
            clip_by_id[clip.id] = clip
    for track in ("audio", "subtitle"):
        for clip in timeline.tracks.get(track, []):
            clip_by_id[clip.id] = clip

    out: list[dict[str, Any]] = []
    for item in report_dict.get("missing_items") or []:
        clip_id = str(item.get("clip_id") or "")
        clip = clip_by_id.get(clip_id)
        if clip is None or _clip_intersects_range(clip, range_start, range_end):
            out.append(dict(item))
    return out


def _build_shot_alignment(
    store: MemoryStore,
    script_id: str,
    timeline: EditTimeline,
) -> list[dict[str, Any]]:
    """对比每镜计划时长与时间轴实际区间。"""
    timings = resolve_shot_timings(store, script_id, timeline=timeline)
    rows: list[dict[str, Any]] = []
    for view in timings:
        actual_ms = view.timeline_end_ms - view.timeline_start_ms
        planned_ms = view.duration_ms
        tts_ms = view.tts_duration_ms
        effective_planned = max(planned_ms, tts_ms) if tts_ms else planned_ms
        delta = actual_ms - effective_planned
        rows.append(
            {
                "shot_id": view.shot_id,
                "order": view.order,
                "planned_duration_ms": planned_ms,
                "tts_duration_ms": tts_ms,
                "timeline_start_ms": view.timeline_start_ms,
                "timeline_end_ms": view.timeline_end_ms,
                "actual_duration_ms": actual_ms,
                "timeline_source": view.timeline_source,
                "delta_ms": delta,
                "mismatch": abs(delta) > DURATION_MISMATCH_THRESHOLD_MS,
            }
        )
    return rows


def _build_optimization_hints(
    *,
    gaps: list[dict[str, Any]],
    overlaps: list[dict[str, Any]],
    shot_alignment: list[dict[str, Any]],
    missing_assets: list[dict[str, Any]],
    timeline: EditTimeline,
    range_start: int,
    range_end: int,
) -> list[dict[str, Any]]:
    """根据 gap/overlap/对齐/缺失生成结构化优化建议。"""
    hints: list[dict[str, Any]] = []

    for gap in gaps:
        if gap.get("track") == "video" and (gap.get("layer_id") or gap.get("z_index") == 0):
            hints.append(
                {
                    "type": "gap",
                    "severity": "warning",
                    "message": "主视频层存在空白区间，建议补 clip 或延长前一片段",
                    "start_ms": gap.get("start_ms"),
                    "end_ms": gap.get("end_ms"),
                    "duration_ms": gap.get("duration_ms"),
                    "layer_id": gap.get("layer_id"),
                }
            )
        elif gap.get("track") in ("audio", "subtitle"):
            hints.append(
                {
                    "type": "gap",
                    "severity": "info",
                    "message": f"{gap.get('track')} 轨存在空白",
                    "start_ms": gap.get("start_ms"),
                    "end_ms": gap.get("end_ms"),
                    "duration_ms": gap.get("duration_ms"),
                }
            )

    for overlap in overlaps:
        hints.append(
            {
                "type": "overlap",
                "severity": "error",
                "message": "同层片段重叠，建议 trim 或 split",
                "clip_id": overlap.get("clip_id"),
                "prev_clip_id": overlap.get("prev_clip_id"),
                "overlap_ms": overlap.get("overlap_ms"),
                "layer_id": overlap.get("layer_id"),
            }
        )

    for row in shot_alignment:
        if not row.get("mismatch"):
            continue
        hints.append(
            {
                "type": "shot_duration_mismatch",
                "severity": "warning",
                "message": "clip 区间与分镜计划/TTS 时长偏差超过阈值",
                "shot_id": row.get("shot_id"),
                "order": row.get("order"),
                "delta_ms": row.get("delta_ms"),
                "planned_duration_ms": row.get("planned_duration_ms"),
                "actual_duration_ms": row.get("actual_duration_ms"),
            }
        )
        tts_ms = int(row.get("tts_duration_ms") or 0)
        actual_ms = int(row.get("actual_duration_ms") or 0)
        if tts_ms > actual_ms + DURATION_MISMATCH_THRESHOLD_MS:
            hints.append(
                {
                    "type": "tts_longer_than_clip",
                    "severity": "warning",
                    "message": "TTS 时长大于视频 clip，可能导致配音被截断",
                    "shot_id": row.get("shot_id"),
                    "tts_duration_ms": tts_ms,
                    "actual_duration_ms": actual_ms,
                }
            )

    for item in missing_assets:
        hints.append(
            {
                "type": "missing_asset",
                "severity": "error",
                "message": item.get("reason") or "素材缺失",
                "clip_id": item.get("clip_id"),
                "category": item.get("category"),
                "shot_id": item.get("shot_id"),
            }
        )

    for clip_id, field_name, reason in edit_capability_issues(timeline):
        clip = None
        for vc in flat_video_clips(timeline):
            if vc.id == clip_id:
                clip = vc
                break
        if clip is None:
            for track in ("audio", "subtitle"):
                for ac in timeline.tracks.get(track, []):
                    if ac.id == clip_id:
                        clip = ac
                        break
        if clip and _clip_intersects_range(clip, range_start, range_end):
            hints.append(
                {
                    "type": "capability_invalid",
                    "severity": "error",
                    "message": reason,
                    "clip_id": clip_id,
                    "field": field_name,
                }
            )

    return hints


def analyze_edit_timeline(
    store: MemoryStore,
    timeline: EditTimeline,
    request: AnalyzeTimelineRequest | None = None,
) -> AnalyzeTimelineResult:
    """分析时间轴指定区间的 clip、空白、重叠与优化建议。"""
    req = request or AnalyzeTimelineRequest()
    timeline = ensure_video_layers(timeline)
    total_duration = timeline_duration_ms(timeline)
    range_start = max(0, int(req.start_ms or 0))
    range_end = int(req.end_ms) if req.end_ms is not None else total_duration
    if range_end < range_start:
        range_end = range_start
    range_end = min(range_end, total_duration) if total_duration else range_end

    track_filter = set(req.tracks) if req.tracks else set(("video", "audio", "subtitle"))
    layer_filter = set(req.layer_ids) if req.layer_ids else None

    clips_in_range: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []

    if "video" in track_filter:
        for layer in sorted(timeline.video_layers, key=lambda item: item.z_index):
            if layer_filter and layer.id not in layer_filter:
                continue
            for clip in layer.clips:
                if _clip_intersects_range(clip, range_start, range_end):
                    clips_in_range.append(
                        _serialize_clip_in_range(
                            clip,
                            track="video",
                            layer_id=layer.id,
                            range_start=range_start,
                            range_end=range_end,
                        )
                    )
            layer_gaps = _scan_gaps_for_clips(
                layer.clips,
                range_start,
                range_end,
                track="video",
                layer_id=layer.id,
            )
            for gap in layer_gaps:
                gap["z_index"] = layer.z_index
            gaps.extend(layer_gaps)

    for track_name in ("audio", "subtitle"):
        if track_name not in track_filter:
            continue
        track_clips = list(timeline.tracks.get(track_name, []))
        for clip in track_clips:
            if _clip_intersects_range(clip, range_start, range_end):
                clips_in_range.append(
                    _serialize_clip_in_range(
                        clip,
                        track=track_name,
                        layer_id=None,
                        range_start=range_start,
                        range_end=range_end,
                    )
                )
        gaps.extend(
            _scan_gaps_for_clips(
                track_clips,
                range_start,
                range_end,
                track=track_name,
            )
        )

    layer_summary = build_timeline_layer_summary(store, timeline)
    overlaps = _filter_overlaps_to_range(
        layer_summary.get("same_layer_overlaps") or [],
        range_start,
        range_end,
        timeline,
    )

    all_warnings = validate_timeline_clips(timeline)
    warnings = [
        w
        for w in all_warnings
        if any(
            _clip_intersects_range(c, range_start, range_end)
            for c in _clips_mentioned_in_warning(w, timeline)
        )
    ] or all_warnings

    validation = validate_edit_timeline(store, timeline)
    missing_assets = _filter_missing_to_range(
        validation.to_dict(),
        timeline,
        range_start,
        range_end,
    )

    shot_alignment: list[dict[str, Any]] = []
    if req.include_shot_alignment:
        shot_alignment = _build_shot_alignment(store, timeline.script_id, timeline)

    optimization_hints: list[dict[str, Any]] = []
    if req.include_hints:
        optimization_hints = _build_optimization_hints(
            gaps=gaps,
            overlaps=overlaps,
            shot_alignment=shot_alignment,
            missing_assets=missing_assets,
            timeline=timeline,
            range_start=range_start,
            range_end=range_end,
        )

    return AnalyzeTimelineResult(
        range={
            "start_ms": range_start,
            "end_ms": range_end,
            "duration_ms": range_end - range_start,
        },
        clips_in_range=sorted(clips_in_range, key=lambda c: (c["start_ms"], c["track"])),
        gaps=gaps,
        overlaps=overlaps,
        warnings=warnings,
        missing_assets=missing_assets,
        shot_alignment=shot_alignment,
        optimization_hints=optimization_hints,
    )


def _clips_mentioned_in_warning(warning: str, timeline: EditTimeline) -> list[EditClip]:
    """从警告文本中提取可能相关的 clip。"""
    timeline = ensure_video_layers(timeline)
    matched: list[EditClip] = []
    for layer in timeline.video_layers:
        for clip in layer.clips:
            if clip.id in warning:
                matched.append(clip)
    for track in ("audio", "subtitle"):
        for clip in timeline.tracks.get(track, []):
            if clip.id in warning:
                matched.append(clip)
    return matched


def build_analyze_summary(
    store: MemoryStore,
    script_id: str,
    timeline: EditTimeline,
) -> dict[str, Any]:
    """轻量分析摘要，供 load_edit_context 使用。"""
    result = analyze_edit_timeline(
        store,
        timeline,
        AnalyzeTimelineRequest(include_hints=False),
    )
    mismatch_count = sum(1 for row in result.shot_alignment if row.get("mismatch"))
    return {
        "warning_count": len(result.warnings),
        "overlap_count": len(result.overlaps),
        "missing_asset_count": len(result.missing_assets),
        "shot_mismatch_count": mismatch_count,
        "gap_count": len(result.gaps),
    }
