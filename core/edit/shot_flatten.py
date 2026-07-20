"""镜内多轨结构 ↔ 剪辑时间轴（EditTimeline）的确定性转换层。

设计原则（剪辑可控为核心，无降级/fallback）：

- 唯一转换路径：Shot 镜内相对时间的多轨结构 → 全局绝对时间的 EditTimeline 投影，
  供 OpenCut / FFmpeg / NLE 消费；OpenCut 手改经 `apply_timeline_edits_to_shots`
  无损回写到镜内结构。
- 投影是确定性的（非 fallback）：分镜是权威源，EditTimeline 是可再生视图。
- 不做任何降级：缺 media 只透传空引用，由上层显式校验，不用占位素材静默出片。

关键往返锚点：每个投影出的 clip 都在 `metadata.shot_offset_ms` 记录其所属分镜的
全局偏移，回写时据此把绝对时间换算回镜内相对时间，保证 round-trip 精确一致。
"""

from __future__ import annotations

from typing import Any

from core.models.entities import (
    EditClip,
    EditClipSourceRefs,
    EditTimeline,
    EditVideoLayer,
    Shot,
    ShotAudioClip,
    ShotAudioTrack,
    ShotSubtitle,
    ShotVideoClip,
    ShotVideoTrack,
)

DEFAULT_LAYER_NAME = "主画面"

# clip.metadata 约定键
META_SHOT_OFFSET = "shot_offset_ms"  # 所属分镜全局偏移
META_SHOT_SUB_SHOT_ID = "shot_sub_shot_id"  # 来源画面 id
META_SOURCE_KIND = "source_kind"  # video / still
META_AUDIO_KIND = "audio_kind"  # voice / background
META_VOICE = "voice"
META_CHARACTER_REF = "character_ref"
META_VOLUME = "volume"
META_TRACK_KEY = "shot_track_id"  # 来源镜内轨 id（回写归轨）
META_SUBTITLE_CHARACTER = "character"  # 字幕角色（与 ShotSubtitle.character 对齐）
META_SUBTITLE_COLOR = "color"  # 字幕颜色（与 ShotSubtitle.color 对齐）


def _sorted_shots(shots: list[Shot]) -> list[Shot]:
    """按 order 排序分镜，order 相同按原顺序稳定排序。"""
    return sorted(shots, key=lambda s: s.order)


def effective_shot_duration_ms(shot: Shot) -> int:
    """计算分镜有效时长：取 duration_ms 与镜内所有片段/画面/字幕的最大终点。

    保证投影后的镜窗口能容纳全部镜内内容；封顶不在此处强制，交由校验层处理。
    """
    end = int(shot.duration_ms or 0)
    for track in shot.video_tracks:
        for clip in track.clips:
            end = max(end, int(clip.end_ms or 0))
    for track in shot.audio_tracks:
        for clip in track.clips:
            end = max(end, int(clip.end_ms or 0))
    for sub in shot.subtitles:
        end = max(end, int(sub.end_ms or 0))
    for vis in shot.sub_shots:
        end = max(end, int(vis.end_ms or 0))
    return max(end, 0)


def shot_offsets(shots: list[Shot]) -> dict[str, int]:
    """按分镜顺序累加有效时长，返回 shot_id → 全局起点偏移毫秒。"""
    offsets: dict[str, int] = {}
    cursor = 0
    for shot in _sorted_shots(shots):
        offsets[shot.id] = cursor
        cursor += effective_shot_duration_ms(shot)
    return offsets


def _video_clip_to_edit_clip(
    shot: Shot, track: ShotVideoTrack, clip: ShotVideoClip, offset_ms: int
) -> EditClip:
    """镜内视频片段 → 全局 EditClip（video 轨）。"""
    metadata: dict[str, Any] = dict(clip.metadata or {})
    metadata[META_SHOT_OFFSET] = offset_ms
    metadata[META_SHOT_SUB_SHOT_ID] = clip.source_sub_shot_id
    metadata[META_SOURCE_KIND] = clip.source_kind
    metadata[META_TRACK_KEY] = track.id
    media_ids = [clip.media_id] if clip.media_id else []
    return EditClip(
        id=clip.id,
        track="video",
        start_ms=offset_ms + int(clip.start_ms or 0),
        end_ms=offset_ms + int(clip.end_ms or 0),
        label=clip.edit_description or "",
        asset_ref=clip.media_id or None,
        motion=clip.camera_motion or None,
        edit_description=clip.edit_description or "",
        transition_in=clip.transition_in,
        transition_out=clip.transition_out,
        background=clip.background,
        motion_detail=clip.motion_detail,
        transform=clip.transform,
        layer_id=f"vly_z{track.z_index}",
        source_refs=EditClipSourceRefs(
            shot_id=shot.id,
            media_ids=media_ids,
            video_plan_shot_order=shot.order,
        ),
        metadata=metadata,
    )


def _audio_clip_to_edit_clip(
    shot: Shot, track: ShotAudioTrack, clip: ShotAudioClip, offset_ms: int
) -> EditClip:
    """镜内音频片段 → 全局 EditClip（audio 轨）。"""
    metadata: dict[str, Any] = dict(clip.metadata or {})
    metadata[META_SHOT_OFFSET] = offset_ms
    metadata[META_AUDIO_KIND] = track.kind
    metadata[META_VOICE] = clip.voice
    metadata[META_CHARACTER_REF] = clip.character_ref
    metadata[META_VOLUME] = clip.volume
    metadata[META_TRACK_KEY] = track.id
    media_ids = [clip.media_id] if clip.media_id else []
    return EditClip(
        id=clip.id,
        track="audio",
        start_ms=offset_ms + int(clip.start_ms or 0),
        end_ms=offset_ms + int(clip.end_ms or 0),
        label=clip.text or "",
        asset_ref=clip.media_id or None,
        source_refs=EditClipSourceRefs(
            shot_id=shot.id,
            media_ids=media_ids,
            video_plan_shot_order=shot.order,
        ),
        metadata=metadata,
    )


def _subtitle_to_edit_clip(shot: Shot, sub: ShotSubtitle, offset_ms: int) -> EditClip:
    """镜内字幕片段 → 全局 EditClip（subtitle 轨）。"""
    metadata: dict[str, Any] = {META_SHOT_OFFSET: offset_ms}
    character = (sub.character or "").strip()
    color = (sub.color or "").strip()
    if character:
        metadata[META_SUBTITLE_CHARACTER] = character
    if color:
        metadata[META_SUBTITLE_COLOR] = color
    return EditClip(
        id=sub.id,
        track="subtitle",
        start_ms=offset_ms + int(sub.start_ms or 0),
        end_ms=offset_ms + int(sub.end_ms or 0),
        label=sub.text or "",
        source_refs=EditClipSourceRefs(
            shot_id=shot.id,
            video_plan_shot_order=shot.order,
        ),
        metadata=metadata,
    )


class ShotFlatten:
    """单个分镜投影出的各轨 clip 集合（全局绝对时间）。"""

    def __init__(
        self,
        video_by_z: dict[int, list[EditClip]],
        audio_clips: list[EditClip],
        subtitle_clips: list[EditClip],
    ) -> None:
        self.video_by_z = video_by_z
        self.audio_clips = audio_clips
        self.subtitle_clips = subtitle_clips


def flatten_shot_to_clips(shot: Shot, offset_ms: int) -> ShotFlatten:
    """把单个分镜的镜内多轨结构展开为全局绝对时间的 clip 集合。"""
    video_by_z: dict[int, list[EditClip]] = {}
    for track in shot.video_tracks:
        bucket = video_by_z.setdefault(int(track.z_index or 0), [])
        for clip in track.clips:
            bucket.append(_video_clip_to_edit_clip(shot, track, clip, offset_ms))
    audio_clips: list[EditClip] = []
    for track in shot.audio_tracks:
        for clip in track.clips:
            audio_clips.append(_audio_clip_to_edit_clip(shot, track, clip, offset_ms))
    subtitle_clips = [
        _subtitle_to_edit_clip(shot, sub, offset_ms) for sub in shot.subtitles
    ]
    return ShotFlatten(video_by_z, audio_clips, subtitle_clips)


def compile_timeline_from_shots(
    shots: list[Shot], *, script_id: str, plan_id: str = ""
) -> EditTimeline:
    """把分镜列表确定性投影为多轨 EditTimeline（OpenCut 可剪辑工程）。

    - 视频：镜内各视频轨按 z_index 归并为 EditVideoLayer（跨镜同 z 合并成一层）。
    - 音频：全部角色音/背景音汇入 tracks["audio"]（kind 记录在 metadata）。
    - 字幕：汇入 tracks["subtitle"]。
    """
    offsets = shot_offsets(shots)
    video_by_z: dict[int, list[EditClip]] = {}
    audio_clips: list[EditClip] = []
    subtitle_clips: list[EditClip] = []
    total_ms = 0
    for shot in _sorted_shots(shots):
        offset = offsets[shot.id]
        flat = flatten_shot_to_clips(shot, offset)
        for z, clips in flat.video_by_z.items():
            video_by_z.setdefault(z, []).extend(clips)
        audio_clips.extend(flat.audio_clips)
        subtitle_clips.extend(flat.subtitle_clips)
        total_ms = offset + effective_shot_duration_ms(shot)

    video_layers: list[EditVideoLayer] = []
    for z in sorted(video_by_z.keys()):
        clips = sorted(video_by_z[z], key=lambda c: c.start_ms)
        name = DEFAULT_LAYER_NAME if z == 0 else f"叠加层 {z}"
        video_layers.append(
            EditVideoLayer(id=f"vly_z{z}", name=name, z_index=z, clips=clips)
        )

    return EditTimeline(
        script_id=script_id,
        plan_id=plan_id,
        duration_ms=total_ms,
        tracks={
            "audio": sorted(audio_clips, key=lambda c: c.start_ms),
            "subtitle": sorted(subtitle_clips, key=lambda c: c.start_ms),
        },
        video_layers=video_layers,
    )


# --- 便捷单轨转换（供预览/局部渲染复用）------------------------------------


def shot_to_video_layers(shot: Shot, offset_ms: int = 0) -> list[EditVideoLayer]:
    """单镜 → EditVideoLayer 列表（按 z_index 归并）。"""
    flat = flatten_shot_to_clips(shot, offset_ms)
    layers: list[EditVideoLayer] = []
    for z in sorted(flat.video_by_z.keys()):
        layers.append(
            EditVideoLayer(
                id=f"vly_z{z}",
                name=DEFAULT_LAYER_NAME if z == 0 else f"叠加层 {z}",
                z_index=z,
                clips=sorted(flat.video_by_z[z], key=lambda c: c.start_ms),
            )
        )
    return layers


def shot_to_audio_clips(shot: Shot, offset_ms: int = 0) -> list[EditClip]:
    """单镜 → 音频轨 clip 列表。"""
    return flatten_shot_to_clips(shot, offset_ms).audio_clips


def shot_to_subtitle_clips(shot: Shot, offset_ms: int = 0) -> list[EditClip]:
    """单镜 → 字幕轨 clip 列表。"""
    return flatten_shot_to_clips(shot, offset_ms).subtitle_clips


# --- 反向：EditTimeline（含 OpenCut 手改）回写镜内结构 ----------------------


def _clip_shot_id(clip: EditClip) -> str:
    """解析 clip 归属的分镜 id。"""
    if clip.source_refs and clip.source_refs.shot_id:
        return clip.source_refs.shot_id
    return str((clip.metadata or {}).get("shot_id", ""))


def _clip_offset_ms(clip: EditClip, fallback: int) -> int:
    """解析 clip 记录的分镜偏移，缺失时用 fallback。"""
    meta = clip.metadata or {}
    if META_SHOT_OFFSET in meta:
        try:
            return int(meta[META_SHOT_OFFSET])
        except (TypeError, ValueError):
            return fallback
    return fallback


def _find_existing_voice_clip(shot: Shot, clip_id: str) -> ShotAudioClip | None:
    """在镜内 voice 轨中按 clip id 查找已有配音幕。"""
    for track in shot.audio_tracks:
        if track.kind != "voice":
            continue
        for clip in track.clips:
            if clip.id == clip_id:
                return clip
    return None


def _is_placeholder_voice_text(text: str, clip_id: str) -> bool:
    """判断 OpenCut 回写 label 是否为占位（空、等于 clip id 或 sac_/vac_ 短 token）。"""
    label = (text or "").strip()
    if not label:
        return True
    cid = (clip_id or "").strip()
    if cid and label == cid:
        return True
    if label.startswith(("sac_", "vac_")) and " " not in label and len(label) <= 32:
        return True
    return False


def _resolve_voice_clip_text(clip: EditClip, existing: ShotAudioClip | None) -> str:
    """回写配音文案：OpenCut 占位 label 时保留镜内已有 text。"""
    label = (clip.label or "").strip()
    if _is_placeholder_voice_text(label, clip.id):
        if existing and (existing.text or "").strip():
            return existing.text.strip()
        return ""
    return label


def _resolve_voice_clip_media_id(clip: EditClip, existing: ShotAudioClip | None) -> str:
    """回写配音 media_id：时间轴 asset_ref 为空时保留镜内或 classic 快照中的 media。"""
    ref = (clip.asset_ref or "").strip()
    if ref:
        return ref
    if existing and (existing.media_id or "").strip():
        return existing.media_id.strip()
    meta = clip.metadata or {}
    classic = meta.get("classic")
    if isinstance(classic, dict):
        mid = str(classic.get("mediaId") or "").strip()
        if mid:
            return mid
    return ""


def apply_timeline_edits_to_shots(
    shots: list[Shot], timeline: EditTimeline
) -> list[Shot]:
    """把 EditTimeline（含 OpenCut 手改）回写到镜内多轨结构，返回新的分镜列表。

    以每个 clip 的 `metadata.shot_offset_ms` 把绝对时间换算回镜内相对时间；按
    source_refs.shot_id 归组重建 video_tracks / audio_tracks / subtitles，
    分镜有效时长按镜内最大终点重算。无归属 shot 的 clip 归入时间上最近的分镜。
    """
    ordered = _sorted_shots(shots)
    by_id = {shot.id: shot for shot in ordered}
    offsets = shot_offsets(ordered)

    # 每个分镜重建的镜内轨容器
    video_tracks: dict[str, dict[str, ShotVideoTrack]] = {s.id: {} for s in ordered}
    audio_tracks: dict[str, dict[str, ShotAudioTrack]] = {s.id: {} for s in ordered}
    subtitles: dict[str, list[ShotSubtitle]] = {s.id: [] for s in ordered}

    def resolve_shot(clip: EditClip) -> str:
        sid = _clip_shot_id(clip)
        if sid and sid in by_id:
            return sid
        # 无归属：按绝对起点落到覆盖它的分镜窗口
        start = int(clip.start_ms or 0)
        for shot in ordered:
            begin = offsets[shot.id]
            end = begin + effective_shot_duration_ms(shot)
            if begin <= start < end:
                return shot.id
        return ordered[-1].id if ordered else ""

    # 视频轨
    for layer in timeline.video_layers:
        for clip in layer.clips:
            sid = resolve_shot(clip)
            if not sid:
                continue
            offset = _clip_offset_ms(clip, offsets.get(sid, 0))
            z = int(layer.z_index or 0)
            track_key = str((clip.metadata or {}).get(META_TRACK_KEY)) or f"z{z}"
            container = video_tracks[sid]
            track = container.get(track_key)
            if track is None:
                track = ShotVideoTrack(id=track_key, name=layer.name or "", z_index=z)
                container[track_key] = track
            track.clips.append(
                ShotVideoClip(
                    id=clip.id,
                    start_ms=max(0, int(clip.start_ms or 0) - offset),
                    end_ms=max(0, int(clip.end_ms or 0) - offset),
                    source_sub_shot_id=str(
                        (clip.metadata or {}).get(META_SHOT_SUB_SHOT_ID, "")
                    ),
                    media_id=(clip.asset_ref or ""),
                    source_kind=str(
                        (clip.metadata or {}).get(META_SOURCE_KIND, "still")
                    ),  # type: ignore[arg-type]
                    camera_motion=(clip.motion or "static"),
                    transform=clip.transform,
                    transition_in=clip.transition_in,
                    transition_out=clip.transition_out,
                    background=clip.background,
                    motion_detail=clip.motion_detail,
                    edit_description=clip.edit_description or "",
                    metadata=_strip_projection_meta(clip.metadata),
                )
            )

    # 音频轨
    for clip in timeline.tracks.get("audio", []):
        sid = resolve_shot(clip)
        if not sid:
            continue
        offset = _clip_offset_ms(clip, offsets.get(sid, 0))
        meta = clip.metadata or {}
        kind = str(meta.get(META_AUDIO_KIND, "voice"))
        track_key = str(meta.get(META_TRACK_KEY)) or f"audio_{kind}"
        container = audio_tracks[sid]
        track = container.get(track_key)
        if track is None:
            track = ShotAudioTrack(id=track_key, name="", kind=kind)  # type: ignore[arg-type]
            container[track_key] = track
        try:
            volume = float(meta.get(META_VOLUME, 1.0))
        except (TypeError, ValueError):
            volume = 1.0
        existing_voice = _find_existing_voice_clip(by_id[sid], clip.id)
        voice_text = _resolve_voice_clip_text(clip, existing_voice)
        media_id = _resolve_voice_clip_media_id(clip, existing_voice)
        character_ref = str(meta.get(META_CHARACTER_REF, "")).strip()
        voice_name = str(meta.get(META_VOICE, "")).strip()
        if existing_voice:
            if not character_ref:
                character_ref = (existing_voice.character_ref or "").strip()
            if not voice_name:
                voice_name = (existing_voice.voice or "").strip()
        track.clips.append(
            ShotAudioClip(
                id=clip.id,
                start_ms=max(0, int(clip.start_ms or 0) - offset),
                end_ms=max(0, int(clip.end_ms or 0) - offset),
                media_id=media_id,
                text=voice_text,
                character_ref=character_ref,
                voice=voice_name,
                volume=volume,
                metadata=_strip_projection_meta(clip.metadata),
            )
        )

    # 字幕轨
    for clip in timeline.tracks.get("subtitle", []):
        sid = resolve_shot(clip)
        if not sid:
            continue
        offset = _clip_offset_ms(clip, offsets.get(sid, 0))
        meta = clip.metadata or {}
        subtitles[sid].append(
            ShotSubtitle(
                id=clip.id,
                text=clip.label or "",
                start_ms=max(0, int(clip.start_ms or 0) - offset),
                end_ms=max(0, int(clip.end_ms or 0) - offset),
                character=str(meta.get(META_SUBTITLE_CHARACTER) or "").strip(),
                color=str(meta.get(META_SUBTITLE_COLOR) or "").strip(),
            )
        )

    # 组装新的分镜
    result: list[Shot] = []
    for shot in ordered:
        vtracks = sorted(video_tracks[shot.id].values(), key=lambda t: t.z_index)
        for t in vtracks:
            t.clips.sort(key=lambda c: c.start_ms)
        atracks = list(audio_tracks[shot.id].values())
        for t in atracks:
            t.clips.sort(key=lambda c: c.start_ms)
        subs = sorted(subtitles[shot.id], key=lambda s: s.start_ms)
        new_duration = _recompute_duration(shot, vtracks, atracks, subs)
        result.append(
            shot.model_copy(
                update={
                    "video_tracks": vtracks,
                    "audio_tracks": atracks,
                    "subtitles": subs,
                    "duration_ms": new_duration,
                }
            )
        )
    return result


def _recompute_duration(
    shot: Shot,
    vtracks: list[ShotVideoTrack],
    atracks: list[ShotAudioTrack],
    subs: list[ShotSubtitle],
) -> int:
    """按回写后的镜内片段最大终点重算分镜时长（保留 visuals 参与）。"""
    end = 0
    for t in vtracks:
        for c in t.clips:
            end = max(end, int(c.end_ms or 0))
    for t in atracks:
        for c in t.clips:
            end = max(end, int(c.end_ms or 0))
    for s in subs:
        end = max(end, int(s.end_ms or 0))
    for vis in shot.sub_shots:
        end = max(end, int(vis.end_ms or 0))
    return max(end, 0)


_PROJECTION_META_KEYS = {
    META_SHOT_OFFSET,
    META_SHOT_SUB_SHOT_ID,
    META_SOURCE_KIND,
    META_AUDIO_KIND,
    META_VOICE,
    META_CHARACTER_REF,
    META_VOLUME,
    META_TRACK_KEY,
}


def _strip_projection_meta(metadata: dict[str, Any] | None) -> dict[str, Any]:
    """回写镜内 clip 时剔除投影期注入的锚点键，只保留业务/OpenCut 装饰字段。"""
    if not metadata:
        return {}
    return {k: v for k, v in metadata.items() if k not in _PROJECTION_META_KEYS}
