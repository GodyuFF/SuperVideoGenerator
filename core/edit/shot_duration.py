"""镜时长与 voice 片段跨度（新模型：镜内多轨 Shot）。"""

from __future__ import annotations

from core.edit.shot_flatten import effective_shot_duration_ms
from core.edit.timeline import _shot_tts_duration_ms
from core.models.entities import MediaAssetType, Shot, ShotAudioTrack, ShotSubShot
from core.store.memory import MemoryStore

# 落盘镜时长步进：整秒（避免精确到毫秒的脏值）
SHOT_DURATION_QUANTUM_MS = 1000


def quantize_duration_ms(ms: int | float, *, quantum_ms: int = SHOT_DURATION_QUANTUM_MS) -> int:
    """将时长向上对齐到整秒（默认），避免裁短音视频。"""
    n = max(0, int(ms or 0))
    q = max(1, int(quantum_ms))
    if n <= 0:
        return q
    return ((n + q - 1) // q) * q


def is_planned_tts_media(store: MemoryStore, media_id: str) -> bool:
    """判断媒体是否为规划阶段 TTS（metadata.used_planned_timeline）。"""
    media = store.media_assets.get(media_id)
    if not media:
        return False
    return bool((media.metadata or {}).get("used_planned_timeline"))


def _bound_media_duration_ms(store: MemoryStore, media_id: str) -> int:
    """读取已绑定媒体的实测时长（音频探测 / 视频 metadata 或文件探测）。"""
    mid = (media_id or "").strip()
    if not mid:
        return 0
    media = store.media_assets.get(mid)
    if not media:
        return 0
    if media.type == MediaAssetType.AUDIO:
        return max(0, int(_shot_tts_duration_ms(store, mid) or 0))
    if media.type == MediaAssetType.VIDEO:
        from core.llm.tools.shared.media_list import (
            resolve_media_access,
            resolve_media_duration_ms,
        )

        access = resolve_media_access(media.url)
        probed = resolve_media_duration_ms(media, access)
        return max(0, int(probed or 0))
    return 0


def resolve_shot_voice_span_ms(
    store: MemoryStore,
    shot: Shot,
    tts_by_shot: dict[str, str],
) -> tuple[int, int]:
    """返回镜内 voice 片段相对跨度 (start_ms, end_ms)。"""
    media_id = tts_by_shot.get(shot.id)
    for track in shot.audio_tracks:
        if track.kind != "voice":
            continue
        for clip in track.clips:
            if clip.media_id and (not media_id or clip.media_id == media_id):
                return int(clip.start_ms or 0), int(clip.end_ms or 0)
    if media_id and is_planned_tts_media(store, media_id):
        probed = _shot_tts_duration_ms(store, media_id)
        if probed > 0:
            return 0, probed
    end = effective_shot_duration_ms(shot)
    return 0, end


def resolve_effective_shot_duration_ms(
    store: MemoryStore,
    shot: Shot,
    tts_by_shot: dict[str, str] | None = None,
) -> int:
    """镜有效时长：镜内结构最大值与已绑定音视频实测取较大者。"""
    tts_by_shot = tts_by_shot or {}
    base = effective_shot_duration_ms(shot)
    media_id = tts_by_shot.get(shot.id)
    if media_id:
        probed = _shot_tts_duration_ms(store, media_id)
        if probed > 0:
            base = max(base, probed)
    for track in shot.audio_tracks:
        if track.kind != "voice":
            continue
        for clip in track.clips:
            mid = (clip.media_id or "").strip()
            if not mid:
                continue
            probed = _bound_media_duration_ms(store, mid)
            if probed > 0:
                base = max(base, int(clip.start_ms or 0) + probed)
    for sub in shot.sub_shots:
        for video in sub.videos or []:
            mid = (video.media_id or "").strip()
            if not mid:
                continue
            start = int(video.start_ms if video.start_ms is not None else sub.start_ms or 0)
            end = int(video.end_ms if video.end_ms is not None else sub.end_ms or 0)
            if end > start:
                base = max(base, end)
                continue
            probed = _bound_media_duration_ms(store, mid)
            if probed > 0:
                base = max(base, start + probed)
    for track in shot.video_tracks:
        for clip in track.clips:
            mid = (clip.media_id or "").strip()
            if not mid:
                continue
            if str(clip.source_kind or "still").strip().lower() != "video":
                continue
            start = int(clip.start_ms or 0)
            end = int(clip.end_ms or 0)
            if end > start:
                base = max(base, end)
                continue
            probed = _bound_media_duration_ms(store, mid)
            if probed > 0:
                base = max(base, start + probed)
    return base


def reconcile_shot_duration_from_media(store: MemoryStore, shot: Shot) -> Shot:
    """按绑定音视频实测时长回填配音终点，并同步镜级 duration_ms。"""
    audio_tracks: list[ShotAudioTrack] = []
    for track in shot.audio_tracks:
        if track.kind != "voice":
            audio_tracks.append(track)
            continue
        new_clips = []
        for clip in track.clips:
            mid = (clip.media_id or "").strip()
            if not mid:
                new_clips.append(clip)
                continue
            probed = _bound_media_duration_ms(store, mid)
            if probed <= 0:
                new_clips.append(clip)
                continue
            start = int(clip.start_ms or 0)
            desired_end = quantize_duration_ms(start + probed)
            cur_end = int(clip.end_ms or 0)
            if cur_end < desired_end:
                new_clips.append(clip.model_copy(update={"end_ms": desired_end}))
            else:
                # 已有终点也按整秒对齐（不缩短媒体覆盖所需的最小终点）
                q_end = max(desired_end, quantize_duration_ms(cur_end))
                if q_end != cur_end:
                    new_clips.append(clip.model_copy(update={"end_ms": q_end}))
                else:
                    new_clips.append(clip)
        audio_tracks.append(track.model_copy(update={"clips": new_clips}))

    sub_shots: list[ShotSubShot] = []
    for sub in shot.sub_shots:
        videos = list(sub.videos or [])
        changed = False
        new_videos = []
        for video in videos:
            mid = (video.media_id or "").strip()
            if not mid:
                new_videos.append(video)
                continue
            start = int(video.start_ms if video.start_ms is not None else sub.start_ms or 0)
            end = int(video.end_ms if video.end_ms is not None else sub.end_ms or 0)
            if end > start:
                q_end = quantize_duration_ms(end)
                if q_end != end:
                    changed = True
                    new_videos.append(video.model_copy(update={"end_ms": q_end}))
                else:
                    new_videos.append(video)
                continue
            probed = _bound_media_duration_ms(store, mid)
            if probed <= 0:
                new_videos.append(video)
                continue
            changed = True
            new_videos.append(
                video.model_copy(
                    update={"start_ms": start, "end_ms": quantize_duration_ms(start + probed)}
                )
            )
        if changed:
            sub_shots.append(sub.model_copy(update={"videos": new_videos}))
        else:
            sub_shots.append(sub)

    updated = shot.model_copy(update={"audio_tracks": audio_tracks, "sub_shots": sub_shots})
    duration_ms = resolve_effective_shot_duration_ms(store, updated) or int(
        updated.duration_ms or 3000
    )
    if duration_ms < 500:
        duration_ms = max(500, int(updated.duration_ms or 3000))
    duration_ms = quantize_duration_ms(duration_ms)
    return updated.model_copy(update={"duration_ms": duration_ms})


def resolve_display_shot_duration_ms(
    shot: Shot,
    tts_duration_ms: int = 0,
) -> tuple[int, str]:
    """展示用镜时长及来源，优先级：剪辑轴 > 视频 > 配音 > 计划镜长。

    返回 (duration_ms, source)，source 为 timeline | video | voice | plan。
    """
    plan_ms = max(0, int(shot.duration_ms or 3000))

    tl_start: int | None = None
    tl_end = 0
    for track in shot.video_tracks:
        for clip in track.clips:
            if not (clip.media_id or "").strip():
                continue
            if str(clip.source_kind or "still").strip().lower() != "video":
                continue
            start = int(clip.start_ms or 0)
            end = int(clip.end_ms or 0)
            if end > start:
                tl_start = start if tl_start is None else min(tl_start, start)
                tl_end = max(tl_end, end)
    if tl_end > (tl_start or 0) and tl_start is not None:
        return tl_end - tl_start, "timeline"

    video_start: int | None = None
    video_end = 0
    for sub in shot.sub_shots:
        sub_start = int(sub.start_ms or 0)
        sub_end = int(sub.end_ms or 0)
        for video in sub.videos or []:
            if not (video.media_id or "").strip():
                continue
            start = int(video.start_ms if video.start_ms is not None else sub_start)
            end = int(video.end_ms if video.end_ms is not None else sub_end)
            if end > start:
                video_start = start if video_start is None else min(video_start, start)
                video_end = max(video_end, end)
    if video_end > (video_start or 0) and video_start is not None:
        return video_end - video_start, "video"

    voice_start: int | None = None
    voice_end = 0
    for track in shot.audio_tracks:
        if track.kind != "voice":
            continue
        for clip in track.clips:
            start = int(clip.start_ms or 0)
            end = int(clip.end_ms or 0)
            has_content = bool((clip.text or "").strip() or (clip.media_id or "").strip())
            if not has_content:
                continue
            effective_end = end if end > start else plan_ms
            voice_start = start if voice_start is None else min(voice_start, start)
            voice_end = max(voice_end, effective_end)
    if voice_end > (voice_start or 0) and voice_start is not None:
        return voice_end - voice_start, "voice"
    if tts_duration_ms > 0:
        return tts_duration_ms, "voice"

    return plan_ms, "plan"
