"""将 SyncAction 应用到 Shot 镜内轨（写入 rate/freeze/槽位）。"""

from __future__ import annotations

from typing import Any

from core.edit.av_sync.types import (
    META_FREEZE_TAIL_MS,
    META_PLAYBACK_RATE,
    SyncAction,
)
from core.edit.shot_flatten import effective_shot_duration_ms
from core.models.entities import Shot


def apply_sync_action_to_shot(shot: Shot, action: SyncAction) -> Shot:
    """将单条协调策略写入镜内 video/audio clip metadata 与时长。"""
    kind = action.kind
    params = action.params or {}
    target_ms = int(params.get("target_ms") or 0)

    if kind == "video_rate":
        rate = float(params.get("playback_rate") or 1.0)
        return _apply_video_rate(shot, rate, target_ms=target_ms)
    if kind == "audio_rate":
        rate = float(params.get("playback_rate") or 1.0)
        return _apply_audio_rate(shot, rate, target_ms=target_ms)
    if kind == "combined_rate":
        v_rate = float(params.get("video_rate") or 1.0)
        a_rate = float(params.get("audio_rate") or 1.0)
        shot = _apply_video_rate(shot, v_rate, target_ms=target_ms)
        return _apply_audio_rate(shot, a_rate, target_ms=target_ms)
    if kind == "freeze_tail":
        freeze_ms = int(params.get("freeze_tail_ms") or 0)
        v_rate = float(params.get("video_rate") or 1.0)
        shot = _apply_video_rate(shot, v_rate, target_ms=target_ms)
        return _apply_freeze_tail(shot, freeze_ms, target_ms=target_ms)
    if kind == "extend_video_slot":
        trim = bool(params.get("trim_video"))
        return _extend_or_trim_video_slot(shot, target_ms, trim=trim)
    # 结构级策略不在此直接改镜（由 Agent / UI 触发）
    return shot


def _set_clip_meta(meta: dict[str, Any] | None, **kwargs: Any) -> dict[str, Any]:
    """合并写入 clip.metadata。"""
    out = dict(meta or {})
    for k, v in kwargs.items():
        if v is None:
            continue
        out[k] = v
    return out


def _apply_video_rate(shot: Shot, rate: float, *, target_ms: int) -> Shot:
    """为镜内真视频 clip 写入 playback_rate，并扩展终点到 target。"""
    if rate <= 0:
        rate = 1.0
    new_tracks = []
    for track in shot.video_tracks:
        clips = []
        for clip in track.clips:
            if str(clip.source_kind or "") != "video" or not clip.media_id:
                clips.append(clip)
                continue
            meta = _set_clip_meta(clip.metadata, **{META_PLAYBACK_RATE: rate})
            end_ms = int(clip.end_ms or 0)
            if target_ms > end_ms:
                end_ms = target_ms
            clips.append(clip.model_copy(update={"metadata": meta, "end_ms": end_ms}))
        new_tracks.append(track.model_copy(update={"clips": clips}))
    updates: dict[str, Any] = {"video_tracks": new_tracks}
    if target_ms > int(shot.duration_ms or 0):
        updates["duration_ms"] = target_ms
    return shot.model_copy(update=updates)


def _apply_audio_rate(shot: Shot, rate: float, *, target_ms: int) -> Shot:
    """为镜内 voice clip 写入 playback_rate（导出 atempo / 重合成提示）。"""
    if rate <= 0:
        rate = 1.0
    new_tracks = []
    for track in shot.audio_tracks:
        if track.kind != "voice":
            new_tracks.append(track)
            continue
        clips = []
        for clip in track.clips:
            meta = _set_clip_meta(clip.metadata, **{META_PLAYBACK_RATE: rate})
            end_ms = int(clip.end_ms or 0)
            if target_ms > 0:
                # visual_master 裁配音展示窗；narration 下通常 target≈tts
                if target_ms < end_ms and rate < 1.0:
                    end_ms = target_ms
                elif target_ms > end_ms:
                    end_ms = target_ms
            clips.append(clip.model_copy(update={"metadata": meta, "end_ms": end_ms}))
        new_tracks.append(track.model_copy(update={"clips": clips}))
    updates: dict[str, Any] = {"audio_tracks": new_tracks}
    if target_ms > int(shot.duration_ms or 0):
        updates["duration_ms"] = target_ms
    return shot.model_copy(update=updates)


def _apply_freeze_tail(shot: Shot, freeze_ms: int, *, target_ms: int) -> Shot:
    """写入 freeze_tail_ms 并扩展视频轨终点。"""
    freeze_ms = max(0, int(freeze_ms))
    new_tracks = []
    for track in shot.video_tracks:
        clips = []
        for clip in track.clips:
            if str(clip.source_kind or "") != "video" or not clip.media_id:
                clips.append(clip)
                continue
            meta = _set_clip_meta(
                clip.metadata,
                **{META_FREEZE_TAIL_MS: freeze_ms},
            )
            end_ms = max(int(clip.end_ms or 0), target_ms or (int(clip.end_ms or 0) + freeze_ms))
            clips.append(clip.model_copy(update={"metadata": meta, "end_ms": end_ms}))
        new_tracks.append(track.model_copy(update={"clips": clips}))
    updates: dict[str, Any] = {"video_tracks": new_tracks}
    if target_ms > int(shot.duration_ms or 0):
        updates["duration_ms"] = target_ms
    elif freeze_ms > 0:
        updates["duration_ms"] = max(
            int(shot.duration_ms or 0),
            effective_shot_duration_ms(shot.model_copy(update={"video_tracks": new_tracks})),
        )
    return shot.model_copy(update=updates)


def _extend_or_trim_video_slot(shot: Shot, target_ms: int, *, trim: bool) -> Shot:
    """扩展或裁短镜内视频轨与 duration_ms 到目标时长。"""
    if target_ms <= 0:
        return shot
    new_tracks = []
    for track in shot.video_tracks:
        clips = []
        for clip in track.clips:
            end_ms = int(clip.end_ms or 0)
            start_ms = int(clip.start_ms or 0)
            if trim and end_ms > target_ms:
                end_ms = max(start_ms + 100, target_ms)
            elif not trim and target_ms > end_ms:
                end_ms = target_ms
            clips.append(clip.model_copy(update={"end_ms": end_ms}))
        new_tracks.append(track.model_copy(update={"clips": clips}))
    # 同步子镜末段
    new_subs = list(shot.sub_shots)
    if new_subs and not trim:
        last = new_subs[-1]
        if int(last.end_ms or 0) < target_ms:
            new_subs[-1] = last.model_copy(update={"end_ms": target_ms})
    elif new_subs and trim:
        last = new_subs[-1]
        if int(last.end_ms or 0) > target_ms:
            new_subs[-1] = last.model_copy(
                update={"end_ms": max(int(last.start_ms or 0) + 100, target_ms)}
            )
    return shot.model_copy(
        update={
            "video_tracks": new_tracks,
            "sub_shots": new_subs,
            "duration_ms": target_ms,
        }
    )
