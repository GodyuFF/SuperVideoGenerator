"""探测单镜 TTS / 视频 / 槽位时长。"""

from __future__ import annotations

from core.edit.av_sync.types import ShotDurationProbe
from core.edit.shot_duration import _bound_media_duration_ms
from core.edit.shot_flatten import effective_shot_duration_ms
from core.edit.timeline import build_tts_by_shot, _shot_tts_duration_ms
from core.models.entities import Shot, VideoPlan
from core.store.memory import MemoryStore


def _shot_has_character_dialogue(shot: Shot) -> bool:
    """判断镜内 voice clip 是否绑定角色对白（非旁白）。"""
    for track in shot.audio_tracks:
        if track.kind != "voice":
            continue
        for clip in track.clips:
            if str(clip.character_ref or "").strip() and str(clip.text or "").strip():
                return True
    return False


def _resolve_tts_ms(store: MemoryStore, shot: Shot, tts_by_shot: dict[str, str]) -> int:
    """解析配音实测时长：clip 绑定 media 优先，其次 tts_by_shot。"""
    best = 0
    for track in shot.audio_tracks:
        if track.kind != "voice":
            continue
        for clip in track.clips:
            mid = str(clip.media_id or "").strip()
            if mid:
                best = max(best, _bound_media_duration_ms(store, mid))
            span = max(0, int(clip.end_ms or 0) - int(clip.start_ms or 0))
            best = max(best, span)
    mid = tts_by_shot.get(shot.id, "")
    if mid:
        best = max(best, int(_shot_tts_duration_ms(store, mid) or 0))
    return best


def _resolve_video_ms(store: MemoryStore, shot: Shot) -> int:
    """解析镜内视频素材最大实测时长（仅 source_kind=video）。"""
    best = 0
    for track in shot.video_tracks:
        for clip in track.clips:
            if str(clip.source_kind or "") != "video":
                continue
            mid = str(clip.media_id or "").strip()
            if mid:
                best = max(best, _bound_media_duration_ms(store, mid))
    for sub in shot.sub_shots:
        for vid in sub.videos:
            mid = str(vid.media_id or "").strip()
            if mid:
                best = max(best, _bound_media_duration_ms(store, mid))
    return best


def probe_shot_durations(
    store: MemoryStore,
    shot: Shot,
    *,
    plan: VideoPlan | None = None,
    tts_by_shot: dict[str, str] | None = None,
) -> ShotDurationProbe:
    """探测单镜 TTS / 视频 / 槽位时长并标记是否含角色对白。"""
    if tts_by_shot is None and plan is not None:
        tts_by_shot = build_tts_by_shot(store, plan.script_id)
    tts_by_shot = tts_by_shot or {}
    style_mode = ""
    if plan is not None:
        mode = plan.mode
        style_mode = mode.value if hasattr(mode, "value") else str(mode or "")
    return ShotDurationProbe(
        shot_id=shot.id,
        tts_ms=_resolve_tts_ms(store, shot, tts_by_shot),
        video_ms=_resolve_video_ms(store, shot),
        slot_ms=effective_shot_duration_ms(shot),
        has_character_dialogue=_shot_has_character_dialogue(shot),
        style_mode=style_mode,
    )
