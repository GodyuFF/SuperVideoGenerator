"""Ken Burns 运镜检测（与预览 kenBurnsPreview.ts 语义对齐）。"""

from __future__ import annotations

from core.models.entities import EditClip

KEN_BURNS_BOUNDARY_STEP_MS = 250


def clip_has_ken_burns(clip: EditClip) -> bool:
    """片段是否含非 static 运镜或 motion_detail 缩放。"""
    motion = (clip.motion or "ken_burns_in").strip().lower()
    if motion and motion != "static":
        return True
    md = clip.motion_detail
    if md is None:
        return False
    if md.scale_from is not None or md.scale_to is not None:
        return True
    if md.from_focal or md.to_focal:
        return True
    return bool((md.type or "").strip() and md.type.strip().lower() != "static")


def add_ken_burns_boundaries(boundaries: set[int], clip: EditClip) -> None:
    """为 Ken Burns clip 插入细粒度边界，避免 composite 切片内运镜冻结。"""
    if not clip_has_ken_burns(clip):
        return
    start = int(clip.start_ms)
    end = int(clip.end_ms)
    if end <= start:
        return
    step = KEN_BURNS_BOUNDARY_STEP_MS
    t = start + step
    while t < end:
        boundaries.add(t)
        t += step
