"""EditClip transform 与关键帧插值。"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

from core.models.entities import EditClip, EditClipKeyframe, EditClipTransform

if TYPE_CHECKING:
    from core.models.entities import EditTimeline


@dataclass
class ResolvedTransform:
    x: float
    y: float
    width: float
    height: float
    opacity: float
    rotation: float
    scale: float = 1.0


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _interp_optional(
    base: float,
    kf_before: EditClipKeyframe | None,
    kf_after: EditClipKeyframe | None,
    attr: str,
    t: float,
) -> float:
    if kf_before is None and kf_after is None:
        return base
    if kf_before is not None and kf_after is not None:
        va = getattr(kf_before, attr)
        vb = getattr(kf_after, attr)
        if va is not None and vb is not None:
            return _lerp(float(va), float(vb), t)
    if kf_before is not None:
        val = getattr(kf_before, attr)
        if val is not None:
            return float(val)
    if kf_after is not None:
        val = getattr(kf_after, attr)
        if val is not None:
            return float(val)
    return base


def _keyframes_around(
    keyframes: list[EditClipKeyframe], local_ms: int
) -> tuple[EditClipKeyframe | None, EditClipKeyframe | None, float]:
    if not keyframes:
        return None, None, 0.0
    sorted_kf = sorted(keyframes, key=lambda k: k.time_ms)
    before: EditClipKeyframe | None = None
    after: EditClipKeyframe | None = None
    for kf in sorted_kf:
        if kf.time_ms <= local_ms:
            before = kf
        elif after is None:
            after = kf
            break
    if before is None:
        return None, after, 0.0
    if after is None:
        return before, None, 0.0
    span = max(after.time_ms - before.time_ms, 1)
    t = (local_ms - before.time_ms) / span
    return before, after, t


def default_transform() -> EditClipTransform:
    return EditClipTransform()


def interpolate_transform(clip: EditClip, local_ms: int) -> ResolvedTransform:
    """按 clip 内相对时间插值 transform（含 keyframes）。"""
    base = clip.transform or default_transform()
    local_ms = max(0, local_ms)
    before, after, t = _keyframes_around(base.keyframes, local_ms)
    x = _interp_optional(base.x, before, after, "x", t)
    y = _interp_optional(base.y, before, after, "y", t)
    width = _interp_optional(base.width, before, after, "width", t)
    height = _interp_optional(base.height, before, after, "height", t)
    opacity = _interp_optional(base.opacity, before, after, "opacity", t)
    rotation = _interp_optional(base.rotation, before, after, "rotation", t)
    scale = _interp_optional(1.0, before, after, "scale", t)

    if clip.motion_detail:
        clip_duration = max(clip.end_ms - clip.start_ms, 1)
        progress = min(1.0, max(0.0, local_ms / clip_duration))
        md = clip.motion_detail
        if md.scale_from is not None and md.scale_to is not None:
            kb_scale = _lerp(float(md.scale_from), float(md.scale_to), progress)
            scale *= kb_scale

    return ResolvedTransform(
        x=x,
        y=y,
        width=width,
        height=height,
        opacity=opacity,
        rotation=rotation,
        scale=scale,
    )


def transform_to_overlay_pixels(
    transform: ResolvedTransform,
    *,
    canvas_width: int,
    canvas_height: int,
) -> dict[str, int]:
    """将归一化 transform 转为 FFmpeg overlay 像素参数。"""
    w = max(1, int(transform.width * canvas_width * transform.scale))
    h = max(1, int(transform.height * canvas_height * transform.scale))
    x = int(transform.x * canvas_width - w / 2)
    y = int(transform.y * canvas_height - h / 2)
    return {"x": x, "y": y, "w": w, "h": h}


def build_scaled_video_filter(
    transform: ResolvedTransform,
    *,
    canvas_width: int,
    canvas_height: int,
) -> str:
    """生成 scale/pad + rotation + opacity 滤镜链（用于图层预渲染）。"""
    pixels = transform_to_overlay_pixels(
        transform,
        canvas_width=canvas_width,
        canvas_height=canvas_height,
    )
    w, h = pixels["w"], pixels["h"]
    parts = [
        f"scale={w}:{h}:force_original_aspect_ratio=decrease",
        f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black@0",
    ]
    if abs(transform.rotation) > 0.01:
        rad = transform.rotation * math.pi / 180.0
        parts.append(f"rotate={rad:.6f}:ow=rotw(iw):oh=roth(ih):c=0x00000000")
    if transform.opacity < 0.999:
        parts.append(f"format=rgba,colorchannelmixer=aa={transform.opacity:.4f}")
    return ",".join(parts)


def collect_timeline_boundaries(timeline: EditTimeline) -> list[int]:
    """合并 clip 边界、关键帧与 Ken Burns 采样点，供 composite_slices 细粒度切片。"""
    from core.edit.ken_burns_filter import add_ken_burns_boundaries
    from core.edit.timeline import ensure_video_layers, timeline_duration_ms

    timeline = ensure_video_layers(timeline)
    duration = timeline_duration_ms(timeline)
    boundaries = {0, duration}
    for layer in timeline.video_layers:
        for clip in layer.clips:
            boundaries.add(clip.start_ms)
            boundaries.add(clip.end_ms)
            add_ken_burns_boundaries(boundaries, clip)
            tr = clip.transform
            if tr and tr.keyframes:
                for kf in tr.keyframes:
                    abs_ms = clip.start_ms + kf.time_ms
                    if clip.start_ms < abs_ms < clip.end_ms:
                        boundaries.add(abs_ms)
    return sorted(boundaries)


def clip_has_animated_transform(clip: EditClip) -> bool:
    """片段是否存在关键帧或非默认静态 transform。"""
    tr = clip.transform
    if not tr:
        return False
    if tr.keyframes:
        return True
    default = default_transform()
    return any(
        abs(getattr(tr, attr) - getattr(default, attr)) > 1e-6
        for attr in ("x", "y", "width", "height", "opacity", "rotation")
    )


def timeline_needs_composite_export(timeline: EditTimeline) -> bool:
    """含 transform/关键帧、Ken Burns 或多层时需走 composite 导出路径。"""
    from core.edit.ken_burns_filter import clip_has_ken_burns
    from core.edit.timeline import ensure_video_layers

    timeline = ensure_video_layers(timeline)
    if len(timeline.video_layers) > 1:
        return True
    for layer in timeline.video_layers:
        for clip in layer.clips:
            if clip_has_animated_transform(clip):
                return True
            if clip_has_ken_burns(clip):
                return True
    return False
