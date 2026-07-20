"""EditTimeline 校验、编译与查询。"""

from __future__ import annotations

from typing import Any

from core.models.entities import (
    EditClip,
    EditClipBackground,
    EditClipKeyframe,
    EditClipMotionDetail,
    EditClipSourceRefs,
    EditClipTransform,
    EditClipTransition,
    EditTimeline,
    EditVideoLayer,
    MediaAssetType,
    Shot,
    VideoPlan,
    new_id,
)
from core.store.memory import MemoryStore

TRACK_KEYS = ("video", "audio", "subtitle")
AUDIO_SUBTITLE_KEYS = ("audio", "subtitle")
MAX_VIDEO_LAYERS = 5
DEFAULT_LAYER_NAME = "主画面"


def _audio_media_accessible(store: MemoryStore, media_id: str) -> bool:
    """判断音频 media 是否可播放（非 superseded 且本地/远程可访问）。"""
    from core.llm.tools.shared.media_list import resolve_media_access

    media = store.media_assets.get(media_id)
    if media is None or media.type != MediaAssetType.AUDIO:
        return False
    meta = media.metadata or {}
    if meta.get("superseded"):
        return False
    access = resolve_media_access(media.url or "")
    return bool(access.get("is_accessible"))


def _voice_clip_media_by_shot(store: MemoryStore, script_id: str) -> dict[str, str]:
    """从 VideoPlan 镜内 voice clip 收集 shot → 首选 media_id（按 clip 顺序）。"""
    out: dict[str, str] = {}
    for plan in store.video_plans.values():
        if plan.script_id != script_id:
            continue
        for shot in plan.shots:
            for track in shot.audio_tracks:
                if track.kind != "voice":
                    continue
                for clip in track.clips:
                    mid = (clip.media_id or "").strip()
                    if mid and _audio_media_accessible(store, mid):
                        out.setdefault(shot.id, mid)
                        break
                if shot.id in out:
                    break
    return out


def build_tts_by_shot(store: MemoryStore, script_id: str) -> dict[str, str]:
    """从镜内 voice clip 与 AUDIO 资产 metadata 构建 shot → asset 映射。"""
    mapping = _voice_clip_media_by_shot(store, script_id)
    for media in store.list_media_for_script(script_id):
        if media.type != MediaAssetType.AUDIO:
            continue
        meta = media.metadata or {}
        if meta.get("superseded"):
            continue
        shot_id = str(meta.get("shot_id") or "").strip()
        if not shot_id or shot_id in mapping:
            continue
        mapping[shot_id] = media.id
    return mapping


_DURATION_PROBE_DRIFT_RATIO = 0.05
DURATION_DRIFT_REFRESH_MS = 200


def _resolve_audio_media_duration_info(
    store: MemoryStore,
    media,
    *,
    prefer_probe: bool = True,
    refresh_metadata: bool = True,
) -> dict[str, Any]:
    """解析音频素材时长详情：duration_ms、duration_source、metadata_duration_ms。"""
    from core.llm.tools.shared.media_list import resolve_media_access
    from core.media.duration_probe import probe_media_duration_ms

    meta_ms = int((media.metadata or {}).get("duration_ms") or 0)
    if not prefer_probe:
        source = "metadata" if meta_ms > 0 else "none"
        return {
            "duration_ms": meta_ms,
            "duration_source": source,
            "metadata_duration_ms": meta_ms,
        }

    access = resolve_media_access(media.url)
    probed = probe_media_duration_ms(str(access.get("file_path") or ""), media.type)
    if probed is None or probed <= 0:
        source = "metadata" if meta_ms > 0 else "none"
        return {
            "duration_ms": meta_ms,
            "duration_source": source,
            "metadata_duration_ms": meta_ms,
        }
    if meta_ms <= 0:
        if refresh_metadata:
            _maybe_refresh_media_duration_metadata(store, media, probed)
        return {
            "duration_ms": probed,
            "duration_source": "probed",
            "metadata_duration_ms": 0,
        }
    drift = abs(probed - meta_ms) / max(probed, 1)
    if drift > _DURATION_PROBE_DRIFT_RATIO:
        if refresh_metadata:
            _maybe_refresh_media_duration_metadata(store, media, probed)
        return {
            "duration_ms": probed,
            "duration_source": "probed",
            "metadata_duration_ms": meta_ms,
        }
    return {
        "duration_ms": meta_ms,
        "duration_source": "metadata",
        "metadata_duration_ms": meta_ms,
    }


def _effective_audio_media_duration_ms(
    store: MemoryStore,
    media,
    *,
    prefer_probe: bool = True,
    refresh_metadata: bool = True,
) -> int:
    """解析音频素材有效时长：metadata 与本地探测取更可靠值。"""
    info = _resolve_audio_media_duration_info(
        store,
        media,
        prefer_probe=prefer_probe,
        refresh_metadata=refresh_metadata,
    )
    return int(info.get("duration_ms") or 0)


def _shot_tts_duration_ms(store: MemoryStore, audio_ref: str | None) -> int:
    """读取镜头 TTS 时长；metadata 偏短或缺失时回退本地文件探测。"""
    if not audio_ref:
        return 0
    media = store.media_assets.get(audio_ref)
    if not media:
        return 0
    return _effective_audio_media_duration_ms(store, media, refresh_metadata=True)


def shot_tts_duration_info(store: MemoryStore, audio_ref: str | None) -> dict[str, Any]:
    """读取镜头 TTS 时长详情（含 duration_source）。"""
    if not audio_ref:
        return {"duration_ms": 0, "duration_source": "none", "metadata_duration_ms": 0}
    media = store.media_assets.get(audio_ref)
    if not media:
        return {"duration_ms": 0, "duration_source": "none", "metadata_duration_ms": 0}
    return _resolve_audio_media_duration_info(store, media, refresh_metadata=True)


def _maybe_refresh_media_duration_metadata(
    store: MemoryStore,
    media,
    effective_ms: int,
) -> None:
    """探测时长与 metadata 偏差较大时回写 store（供 enrich 路径使用）。"""
    if effective_ms <= 0:
        return
    meta_ms = int((media.metadata or {}).get("duration_ms") or 0)
    if meta_ms > 0 and abs(effective_ms - meta_ms) / max(effective_ms, 1) <= _DURATION_PROBE_DRIFT_RATIO:
        return
    updated_meta = {**(media.metadata or {}), "duration_ms": effective_ms}
    store.media_assets[media.id] = media.model_copy(update={"metadata": updated_meta})


def sync_audio_clip_durations_to_media(
    store: MemoryStore,
    timeline: EditTimeline,
) -> EditTimeline:
    """将 audio/subtitle clip 区间与素材真实时长对齐（跳过 user_locked）。"""
    from core.edit.shot_timing import _find_video_clip_for_shot
    from core.edit.timeline_analysis import DURATION_MISMATCH_THRESHOLD_MS

    plan = store.get_video_plan_for_script(timeline.script_id)
    shots_by_id = {s.id: s for s in plan.shots} if plan and plan.shots else {}

    audio_clips = list(timeline.tracks.get("audio", []))
    if not audio_clips:
        return timeline

    updated_audio: list[EditClip] = []
    audio_span_by_shot: dict[str, tuple[int, int]] = {}

    for clip in audio_clips:
        if _clip_is_user_protected(clip):
            updated_audio.append(clip)
            shot_id = str((clip.metadata or {}).get("shot_id") or "").strip()
            if shot_id:
                audio_span_by_shot[shot_id] = (clip.start_ms, clip.end_ms)
            continue

        asset_ref = str(clip.asset_ref or "").strip()
        media = store.media_assets.get(asset_ref) if asset_ref else None
        if media is None or media.type != MediaAssetType.AUDIO:
            updated_audio.append(clip)
            continue

        media_ms = _effective_audio_media_duration_ms(store, media)
        if media_ms <= 0:
            updated_audio.append(clip)
            continue

        _maybe_refresh_media_duration_metadata(store, media, media_ms)

        start_ms = int(clip.start_ms or 0)
        end_ms = int(clip.end_ms or start_ms)
        clip_span = max(end_ms - start_ms, 0)
        if clip_span >= media_ms - DURATION_MISMATCH_THRESHOLD_MS:
            updated_audio.append(clip)
            shot_id = str((clip.metadata or {}).get("shot_id") or "").strip()
            if not shot_id:
                shot_id = str((media.metadata or {}).get("shot_id") or "").strip()
            if shot_id:
                audio_span_by_shot[shot_id] = (start_ms, end_ms)
            continue

        target_end = start_ms + media_ms
        shot_id = str((clip.metadata or {}).get("shot_id") or "").strip()
        if not shot_id:
            shot_id = str((media.metadata or {}).get("shot_id") or "").strip()
        shot = shots_by_id.get(shot_id) if shot_id else None
        # narration_master / balanced：配音为主，扩展视频终点而非钳制音频
        # visual_master：画面为主，音频仍不超过视频终点
        policy = str(getattr(shot, "sync_policy", "") or "narration_master") if shot else "narration_master"
        if shot is not None and policy == "visual_master":
            video_clip = _find_video_clip_for_shot(timeline, shot)
            if video_clip is not None:
                target_end = min(target_end, int(video_clip.end_ms))

        if target_end <= start_ms:
            updated_audio.append(clip)
            continue

        extended = clip.model_copy(update={"end_ms": target_end})
        updated_audio.append(extended)
        if shot_id:
            audio_span_by_shot[shot_id] = (start_ms, target_end)

    tracks = dict(timeline.tracks)
    tracks["audio"] = updated_audio

    subtitle_clips = list(tracks.get("subtitle", []))
    if subtitle_clips and audio_span_by_shot:
        updated_subtitle: list[EditClip] = []
        for clip in subtitle_clips:
            if _clip_is_user_protected(clip):
                updated_subtitle.append(clip)
                continue
            shot_id = str((clip.metadata or {}).get("shot_id") or "").strip()
            span = audio_span_by_shot.get(shot_id) if shot_id else None
            if span is None:
                updated_subtitle.append(clip)
                continue
            start_ms, end_ms = span
            updated_subtitle.append(
                clip.model_copy(update={"start_ms": start_ms, "end_ms": end_ms})
            )
        tracks["subtitle"] = updated_subtitle

    max_end = max(
        (c.end_ms for c in updated_audio),
        default=timeline.duration_ms,
    )
    for layer in timeline.video_layers:
        for c in layer.clips:
            max_end = max(max_end, c.end_ms)
    return timeline.model_copy(update={"tracks": tracks, "duration_ms": max(max_end, timeline.duration_ms)})


def _parse_focal(raw: Any) -> tuple[float, float] | None:
    if not isinstance(raw, (list, tuple)) or len(raw) < 2:
        return None
    try:
        return float(raw[0]), float(raw[1])
    except (TypeError, ValueError):
        return None


def _parse_transition(raw: Any) -> EditClipTransition | None:
    if not isinstance(raw, dict):
        return None
    try:
        return EditClipTransition.model_construct(
            type=str(raw.get("type", "cut")),
            duration_ms=max(0, int(raw.get("duration_ms", 0))),
        )
    except (TypeError, ValueError):
        return None


def _parse_background(raw: Any) -> EditClipBackground | None:
    if not isinstance(raw, dict):
        return None
    try:
        return EditClipBackground.model_construct(
            type=str(raw.get("type", "solid")),
            color=str(raw.get("color", "#0f172a")),
            asset_ref=str(raw.get("asset_ref")).strip()
            if raw.get("asset_ref")
            else None,
        )
    except (TypeError, ValueError):
        return None


def _parse_motion_detail(raw: Any) -> EditClipMotionDetail | None:
    if not isinstance(raw, dict):
        return None
    try:
        return EditClipMotionDetail(
            type=str(raw.get("type", "ken_burns_in")),
            from_focal=_parse_focal(raw.get("from_focal")),
            to_focal=_parse_focal(raw.get("to_focal")),
            scale_from=float(raw["scale_from"]) if raw.get("scale_from") is not None else None,
            scale_to=float(raw["scale_to"]) if raw.get("scale_to") is not None else None,
        )
    except (TypeError, ValueError):
        return None


def _parse_source_refs(raw: Any) -> EditClipSourceRefs | None:
    if not isinstance(raw, dict):
        return None
    text_ids = raw.get("text_asset_ids") or []
    media_ids = raw.get("media_ids") or []
    variant_ids = raw.get("variant_ids") or []
    if not isinstance(text_ids, list):
        text_ids = []
    if not isinstance(media_ids, list):
        media_ids = []
    if not isinstance(variant_ids, list):
        variant_ids = []
    try:
        order_raw = raw.get("video_plan_shot_order")
        return EditClipSourceRefs(
            shot_id=str(raw.get("shot_id", "") or ""),
            text_asset_ids=[str(x) for x in text_ids if x],
            media_ids=[str(x) for x in media_ids if x],
            variant_ids=[str(x) for x in variant_ids if x],
            video_plan_shot_order=int(order_raw) if order_raw is not None else None,
        )
    except (TypeError, ValueError):
        return None


def _parse_keyframe(raw: Any) -> EditClipKeyframe | None:
    if not isinstance(raw, dict):
        return None
    try:
        return EditClipKeyframe(
            time_ms=max(0, int(raw.get("time_ms", 0))),
            x=float(raw["x"]) if raw.get("x") is not None else None,
            y=float(raw["y"]) if raw.get("y") is not None else None,
            width=float(raw["width"]) if raw.get("width") is not None else None,
            height=float(raw["height"]) if raw.get("height") is not None else None,
            scale=float(raw["scale"]) if raw.get("scale") is not None else None,
            opacity=float(raw["opacity"]) if raw.get("opacity") is not None else None,
            rotation=float(raw["rotation"]) if raw.get("rotation") is not None else None,
        )
    except (TypeError, ValueError):
        return None


def _parse_transform(raw: Any) -> EditClipTransform | None:
    if not isinstance(raw, dict):
        return None
    try:
        keyframes_raw = raw.get("keyframes") or []
        keyframes: list[EditClipKeyframe] = []
        if isinstance(keyframes_raw, list):
            for item in keyframes_raw:
                kf = _parse_keyframe(item)
                if kf:
                    keyframes.append(kf)
        return EditClipTransform(
            x=float(raw.get("x", 0.5)),
            y=float(raw.get("y", 0.5)),
            width=float(raw.get("width", 1.0)),
            height=float(raw.get("height", 1.0)),
            opacity=float(raw.get("opacity", 1.0)),
            rotation=float(raw.get("rotation", 0.0)),
            keyframes=keyframes,
        )
    except (TypeError, ValueError):
        return None


def default_clip_transform() -> EditClipTransform:
    return EditClipTransform()


def _parse_clip_from_raw(
    raw: dict[str, Any],
    *,
    track: str,
    layer_id: str | None = None,
) -> EditClip | None:
    if track not in TRACK_KEYS:
        track = "video"
    try:
        clip = EditClip(
            id=str(raw.get("id") or new_id("clip")),
            track=track,  # type: ignore[arg-type]
            start_ms=max(0, int(raw.get("start_ms", 0))),
            end_ms=max(0, int(raw.get("end_ms", 0))),
            label=str(raw.get("label", "")).strip(),
            asset_ref=str(raw.get("asset_ref")).strip() if raw.get("asset_ref") else None,
            motion=str(raw.get("motion")).strip() if raw.get("motion") else None,
            edit_description=str(raw.get("edit_description", "")).strip(),
            transition_in=_parse_transition(raw.get("transition_in")),
            transition_out=_parse_transition(raw.get("transition_out")),
            background=_parse_background(raw.get("background")),
            motion_detail=_parse_motion_detail(raw.get("motion_detail")),
            source_refs=_parse_source_refs(raw.get("source_refs")),
            transform=_parse_transform(raw.get("transform")) or default_clip_transform(),
            layer_id=str(raw.get("layer_id") or layer_id or "").strip() or layer_id,
            metadata=dict(raw.get("metadata") or {}) if isinstance(raw.get("metadata"), dict) else {},
        )
    except (TypeError, ValueError):
        return None
    if clip.end_ms <= clip.start_ms:
        clip = clip.model_copy(update={"end_ms": clip.start_ms + 1000})
    return _normalize_clip_motion(clip)


def _normalize_clip_motion(clip: EditClip) -> EditClip:
    from core.edit.edit_capabilities import resolve_motion

    updates: dict[str, Any] = {}
    if clip.motion:
        updates["motion"] = resolve_motion(clip.motion)
    if clip.motion_detail and clip.motion_detail.type:
        updates["motion_detail"] = clip.motion_detail.model_copy(
            update={"type": resolve_motion(clip.motion_detail.type)}
        )
    if updates:
        return clip.model_copy(update=updates)
    return clip


def normalize_timeline_motions(timeline: EditTimeline) -> EditTimeline:
    """将 video clip 的 motion / motion_detail.type 归一化为 capabilities 枚举。"""
    if not timeline.video_layers:
        return timeline
    layers = [
        layer.model_copy(
            update={"clips": [_normalize_clip_motion(c) for c in layer.clips]}
        )
        for layer in timeline.video_layers
    ]
    return timeline.model_copy(update={"video_layers": layers})


def normalize_video_layers(raw_layers: list[Any] | None) -> list[EditVideoLayer]:
    """解析 video_layers 列表为 EditVideoLayer。"""
    layers: list[EditVideoLayer] = []
    if isinstance(raw_layers, list):
        for idx, raw in enumerate(raw_layers[:MAX_VIDEO_LAYERS]):
            if not isinstance(raw, dict):
                continue
            layer_id = str(raw.get("id") or new_id("vly"))
            clips_raw = raw.get("clips") or []
            clips: list[EditClip] = []
            if isinstance(clips_raw, list):
                for clip_raw in clips_raw:
                    if not isinstance(clip_raw, dict):
                        continue
                    clip = _parse_clip_from_raw(
                        clip_raw, track="video", layer_id=layer_id
                    )
                    if clip:
                        clips.append(clip)
            clips.sort(key=lambda c: (c.start_ms, c.end_ms))
            try:
                z_index = int(raw.get("z_index", idx))
            except (TypeError, ValueError):
                z_index = idx
            layers.append(
                EditVideoLayer(
                    id=layer_id,
                    name=str(raw.get("name", "")).strip() or f"视频层 {idx + 1}",
                    z_index=z_index,
                    clips=clips,
                )
            )
    if layers:
        layers.sort(key=lambda layer: layer.z_index)
    return layers


def video_layers_from_agent_clips(clips: list[EditClip]) -> list[EditVideoLayer]:
    """将 Agent 扁平 video clip 列表包装为单层 video_layers。"""
    if not clips:
        return []
    layer_id = new_id("vly")
    wrapped = [
        c.model_copy(
            update={
                "layer_id": layer_id,
                "transform": c.transform or default_clip_transform(),
            }
        )
        for c in clips
    ]
    return [
        EditVideoLayer(
            id=layer_id,
            name=DEFAULT_LAYER_NAME,
            z_index=0,
            clips=wrapped,
        )
    ]


def resolve_agent_video_layers(
    agent_video_layers: list[EditVideoLayer] | None,
    agent_video_clips: list[EditClip] | None = None,
) -> list[EditVideoLayer]:
    """解析 Agent 输入的 video_layers 或扁平 video clips。"""
    if agent_video_layers:
        return agent_video_layers
    if agent_video_clips:
        return video_layers_from_agent_clips(agent_video_clips)
    return []


def flat_video_clips(timeline: EditTimeline) -> list[EditClip]:
    """从 video_layers 扁平化读取全部 video clip。"""
    out: list[EditClip] = []
    for layer in sorted(timeline.video_layers, key=lambda item: item.z_index):
        out.extend(layer.clips)
    return out


def serialize_clip_item(
    store: MemoryStore,
    timeline: EditTimeline,
    clip: EditClip,
    *,
    shot_by_id: dict[str, Shot],
) -> dict[str, Any]:
    from core.edit.asset_resolver import resolve_clip_media

    preview_url = ""
    preview_media_type = ""
    if clip.track in ("video", "audio"):
        resolved = resolve_clip_media(
            store,
            clip,
            script_id=timeline.script_id,
            shot_by_id=shot_by_id,
        )
        if resolved and resolved.is_accessible:
            preview_url = resolved.link or resolved.url
            preview_media_type = resolved.media_type
    return {
        "id": clip.id,
        "track": clip.track,
        "start_ms": clip.start_ms,
        "end_ms": clip.end_ms,
        "label": clip.label,
        "asset_ref": clip.asset_ref,
        "motion": clip.motion,
        "edit_description": clip.edit_description,
        "transition_in": clip.transition_in.model_dump() if clip.transition_in else None,
        "transition_out": clip.transition_out.model_dump() if clip.transition_out else None,
        "background": clip.background.model_dump() if clip.background else None,
        "motion_detail": clip.motion_detail.model_dump() if clip.motion_detail else None,
        "source_refs": clip.source_refs.model_dump() if clip.source_refs else None,
        "transform": clip.transform.model_dump() if clip.transform else None,
        "layer_id": clip.layer_id,
        "preview_url": preview_url,
        "preview_media_type": preview_media_type,
        "metadata": clip.metadata,
    }


def normalize_tracks(tracks: dict[str, Any] | None) -> dict[str, list[EditClip]]:
    """将 LLM/JSON 轨道数据规范为 audio/subtitle EditClip 列表。"""
    out: dict[str, list[EditClip]] = {k: [] for k in AUDIO_SUBTITLE_KEYS}
    if not isinstance(tracks, dict):
        return out
    for key in AUDIO_SUBTITLE_KEYS:
        raw_list = tracks.get(key) or []
        if not isinstance(raw_list, list):
            continue
        for raw in raw_list:
            if not isinstance(raw, dict):
                continue
            track = str(raw.get("track", key))
            if track not in AUDIO_SUBTITLE_KEYS:
                track = key
            clip = _parse_clip_from_raw(raw, track=track)
            if clip:
                out[key].append(clip)
        out[key].sort(key=lambda c: (c.start_ms, c.end_ms))
    return out


def extract_agent_video_clips(tracks: dict[str, Any] | None) -> list[EditClip]:
    """从 Agent tracks 字典提取扁平 video clip 列表。"""
    if not isinstance(tracks, dict):
        return []
    raw_list = tracks.get("video") or []
    if not isinstance(raw_list, list):
        return []
    clips: list[EditClip] = []
    for raw in raw_list:
        if not isinstance(raw, dict):
            continue
        clip = _parse_clip_from_raw(raw, track="video")
        if clip:
            clips.append(clip)
    clips.sort(key=lambda c: (c.start_ms, c.end_ms))
    return clips


def _max_clip_end_ms(timeline: EditTimeline) -> int:
    """各轨 clip 终点最大值（毫秒）。"""
    max_end = 0
    for layer in timeline.video_layers:
        for clip in layer.clips:
            max_end = max(max_end, int(clip.end_ms or 0))
    for clips in timeline.tracks.values():
        for clip in clips:
            max_end = max(max_end, int(clip.end_ms or 0))
    return max_end


def _max_video_end_ms(timeline: EditTimeline) -> int:
    """视频层 clip 终点最大值（毫秒）。"""
    max_end = 0
    for layer in timeline.video_layers:
        for clip in layer.clips:
            max_end = max(max_end, int(clip.end_ms or 0))
    return max_end


def timeline_duration_ms(timeline: EditTimeline) -> int:
    """成片有效时长：以视频层终点为准，避免孤立音频误剪拖长 duration_ms。"""
    video_end = _max_video_end_ms(timeline)
    all_end = _max_clip_end_ms(timeline)
    if video_end > 0:
        return video_end
    if all_end > 0:
        return all_end
    stored = int(timeline.duration_ms or 0)
    return stored if stored > 0 else 0


def sync_timeline_duration_ms(timeline: EditTimeline) -> EditTimeline:
    """将 duration_ms 与轨 clip 终点对齐后写回时间轴。"""
    duration = timeline_duration_ms(timeline)
    if duration <= 0:
        return timeline
    return timeline.model_copy(update={"duration_ms": duration})


def validate_timeline_clips(timeline: EditTimeline) -> list[str]:
    """返回重叠/非法片段警告（不阻断保存）。"""
    warnings: list[str] = []
    for layer in timeline.video_layers:
        prev_end = -1
        for clip in layer.clips:
            if clip.end_ms <= clip.start_ms:
                warnings.append(f"视频层 {layer.name or layer.id} clip {clip.id} 时长无效")
            if clip.start_ms < prev_end:
                warnings.append(
                    f"视频层 {layer.name or layer.id} clip {clip.id} 与同层片段重叠"
                )
            prev_end = max(prev_end, clip.end_ms)
    for track_name in ("audio", "subtitle"):
        clips = timeline.tracks.get(track_name, [])
        prev_end = -1
        for clip in clips:
            if clip.end_ms <= clip.start_ms:
                warnings.append(f"{track_name} 轨 clip {clip.id} 时长无效")
            if clip.start_ms < prev_end:
                warnings.append(f"{track_name} 轨 clip {clip.id} 与前一片段重叠")
            prev_end = max(prev_end, clip.end_ms)
    return warnings


def _compact_transform(transform: EditClipTransform | None) -> dict[str, float] | None:
    if transform is None:
        return None
    return {
        "x": transform.x,
        "y": transform.y,
        "width": transform.width,
        "height": transform.height,
    }


def build_timeline_layer_summary(
    store: MemoryStore,
    timeline: EditTimeline,
) -> dict[str, Any]:
    """紧凑图层摘要：每层 clip 时间/transform/asset_ref 与同层重叠标记。"""
    del store
    warnings = validate_timeline_clips(timeline)
    same_layer_overlaps: list[dict[str, Any]] = []
    video_layers_out: list[dict[str, Any]] = []

    for layer in sorted(timeline.video_layers, key=lambda item: item.z_index):
        prev_end = -1
        prev_clip_id = ""
        clips_out: list[dict[str, Any]] = []
        for clip in layer.clips:
            overlap = prev_end >= 0 and clip.start_ms < prev_end
            if overlap:
                same_layer_overlaps.append(
                    {
                        "layer_id": layer.id,
                        "layer_name": layer.name or layer.id,
                        "clip_id": clip.id,
                        "prev_clip_id": prev_clip_id,
                        "overlap_ms": prev_end - clip.start_ms,
                    }
                )
            shot_id = str((clip.metadata or {}).get("shot_id") or "").strip()
            item: dict[str, Any] = {
                "id": clip.id,
                "label": clip.label,
                "start_ms": clip.start_ms,
                "end_ms": clip.end_ms,
                "asset_ref": clip.asset_ref,
                "transform": _compact_transform(clip.transform),
                "overlap_with_prev": overlap,
            }
            if shot_id:
                item["shot_id"] = shot_id
            clips_out.append(item)
            prev_end = max(prev_end, clip.end_ms)
            prev_clip_id = clip.id

        video_layers_out.append(
            {
                "id": layer.id,
                "name": layer.name,
                "z_index": layer.z_index,
                "clip_count": len(clips_out),
                "clips": clips_out,
            }
        )

    return {
        "timeline_id": timeline.id,
        "revision": timeline.revision,
        "user_edited": timeline.user_edited,
        "duration_ms": timeline_duration_ms(timeline),
        "max_video_layers": MAX_VIDEO_LAYERS,
        "video_layers": video_layers_out,
        "track_counts": {
            "video": sum(len(layer["clips"]) for layer in video_layers_out),
            "audio": len(timeline.tracks.get("audio", [])),
            "subtitle": len(timeline.tracks.get("subtitle", [])),
        },
        "warnings": warnings,
        "same_layer_overlaps": same_layer_overlaps,
    }


def format_layer_summary_text(summary: dict[str, Any]) -> str:
    """人类可读的图层摘要一行。"""
    parts: list[str] = []
    for layer in summary.get("video_layers") or []:
        name = str(layer.get("name") or layer.get("id") or "层")
        z_index = layer.get("z_index", 0)
        clip_count = layer.get("clip_count", 0)
        parts.append(f"Layer{z_index} {name}({clip_count}段)")
    text = " ".join(parts) if parts else "无视频层"
    warns = summary.get("warnings") or []
    if warns:
        text += f"；警告 {len(warns)} 条"
    overlaps = summary.get("same_layer_overlaps") or []
    if overlaps:
        text += f"；同层重叠 {len(overlaps)} 处"
    return text


def compile_timeline_from_shots(
    store: MemoryStore,
    *,
    script_id: str,
    plan: VideoPlan,
    tts_by_shot: dict[str, str] | None = None,
) -> EditTimeline:
    """把 VideoPlan 镜内多轨结构确定性投影为 EditTimeline（OpenCut 可剪辑工程）。

    单一转换路径：委托 core.edit.shot_flatten 逐镜展开镜内 video/audio/subtitle 轨为
    全局绝对时间的多层时间轴。分镜是权威源，媒体已绑定在镜内 clip 上（无 fallback 编译）。
    """
    del tts_by_shot  # 媒体已绑定在镜内 clip，无需外部 TTS 映射
    from core.edit.shot_flatten import compile_timeline_from_shots as _project

    timeline = _project(plan.shots, script_id=script_id, plan_id=plan.id)
    return normalize_timeline_motions(timeline)


def _clip_is_user_locked(clip: EditClip) -> bool:
    """仅显式 user_locked 的 clip 才禁止系统调整时长（edited_by=user 不算锁定）。"""
    return bool((clip.metadata or {}).get("user_locked"))


def realign_edit_timeline_from_plan(store: MemoryStore, script_id: str) -> bool:
    """从分镜计划稿重新投影剪辑时间轴（仅 editing_agent 域显式调用；禁止侧效自动触发）。"""
    timeline = store.get_edit_timeline_for_script(script_id)
    if timeline is not None and timeline.user_edited:
        return False
    plan = store.get_video_plan_for_script(script_id)
    if not plan or not plan.shots:
        return False
    compiled = compile_timeline_from_shots(store, script_id=script_id, plan=plan)
    updates = {
        "revision": (timeline.revision + 1) if timeline else 0,
        "last_edited_by": "system_tts_sync",
        "updated_at": _timeline_now(),
    }
    if timeline is not None:
        updates["id"] = timeline.id
    store.set_edit_timeline(compiled.model_copy(update=updates))
    return True


def realign_edit_timeline_durations_from_plan(store: MemoryStore, script_id: str) -> bool:
    """镜内结构为权威源：时长同步即重新投影（用户手改时间轴由镜内回写驱动）。"""
    return realign_edit_timeline_from_plan(store, script_id)


def resolve_shot_image_ref(store: MemoryStore, shot: Shot) -> str | None:
    """解析分镜主画面（frame）图片 media。

    仅返回可访问的 IMAGE：优先子镜 images[] 已绑定 media，其次 frame 文字资产
    primary_media。不接受视频 media，不回退 video_tracks / videos[] / scene。
    """

    def _accessible_image(media_id: str) -> str | None:
        media = store.media_assets.get(media_id)
        if (
            media
            and media.type == MediaAssetType.IMAGE
            and media.url
            and not str(media.url).startswith("placeholder:")
        ):
            return media.id
        return None

    def _from_frame_asset(frame_asset_id: str) -> str | None:
        fid = (frame_asset_id or "").strip()
        if not fid:
            return None
        asset = store.text_assets.get(fid)
        if not asset or not asset.primary_media_id:
            return None
        return _accessible_image(asset.primary_media_id)

    for sub in shot.sub_shots:
        for img in sub.images:
            if img.media_id:
                mid = _accessible_image(img.media_id)
                if mid:
                    return mid
            mid = _from_frame_asset(img.frame_asset_id)
            if mid:
                return mid
    return None


def resolve_shot_video_ref(store: MemoryStore, shot: Shot) -> str | None:
    """解析分镜主视频 media：优先视频轨，其次子镜 videos[]。

    仅返回可访问的 VIDEO；不把画面位 images[] 中的误绑视频当作规范来源。
    """

    def _accessible_video(media_id: str) -> str | None:
        media = store.media_assets.get(media_id)
        if (
            media
            and media.type == MediaAssetType.VIDEO
            and media.url
            and not str(media.url).startswith("placeholder:")
        ):
            return media.id
        return None

    for track in sorted(shot.video_tracks, key=lambda t: t.z_index):
        for clip in track.clips:
            if clip.media_id and str(getattr(clip, "source_kind", "") or "") == "video":
                mid = _accessible_video(clip.media_id)
                if mid:
                    return mid
    for track in sorted(shot.video_tracks, key=lambda t: t.z_index):
        for clip in track.clips:
            if clip.media_id:
                mid = _accessible_video(clip.media_id)
                if mid:
                    return mid
    for sub in shot.sub_shots:
        for vid in sub.videos:
            if vid.media_id:
                mid = _accessible_video(vid.media_id)
                if mid:
                    return mid
    return None


def enrich_timeline_audio_from_store(
    store: MemoryStore,
    timeline: EditTimeline,
    plan: VideoPlan | None = None,
    *,
    skip_subtitle_enrich: bool = False,
) -> EditTimeline:
    """镜内多轨为权威源，投影已含 audio/subtitle 轨；此处仅归一化返回（无补齐/降级）。"""
    del plan, skip_subtitle_enrich
    return timeline


def finalize_merged_timeline(
    store: MemoryStore,
    timeline: EditTimeline,
    plan: VideoPlan | None,
    *,
    skip_subtitle_enrich: bool = False,
) -> EditTimeline:
    """导出/写回前：对齐音频 clip 时长、按主轨扩展视频槽位，并归一化运镜。"""
    del skip_subtitle_enrich
    timeline = sync_audio_clip_durations_to_media(store, timeline)
    timeline = _extend_video_clips_for_narration_master(store, timeline, plan)
    return normalize_timeline_motions(timeline)


def _extend_video_clips_for_narration_master(
    store: MemoryStore,
    timeline: EditTimeline,
    plan: VideoPlan | None,
) -> EditTimeline:
    """narration_master：当同镜配音长于视频 clip 时，扩展视频终点以匹配音频。"""
    from core.edit.shot_timing import _find_audio_clip_for_shot, _find_video_clip_for_shot

    if plan is None or not plan.shots:
        plan = store.get_video_plan_for_script(timeline.script_id)
    if plan is None or not plan.shots:
        return timeline

    # shot_id → 需要扩展到的绝对终点
    extend_end_by_shot: dict[str, int] = {}
    for shot in plan.shots:
        policy = str(getattr(shot, "sync_policy", "") or "narration_master")
        if policy == "visual_master":
            continue
        audio_clip = _find_audio_clip_for_shot(timeline, shot)
        video_clip = _find_video_clip_for_shot(timeline, shot)
        if audio_clip is None or video_clip is None:
            continue
        if int(audio_clip.end_ms) > int(video_clip.end_ms) + 500:
            extend_end_by_shot[shot.id] = int(audio_clip.end_ms)

    if not extend_end_by_shot:
        return timeline

    def _clip_shot_id(clip: EditClip) -> str:
        if clip.source_refs and clip.source_refs.shot_id:
            return clip.source_refs.shot_id.strip()
        return str((clip.metadata or {}).get("shot_id") or "").strip()

    new_layers: list = []
    changed = False
    max_end = timeline.duration_ms
    for layer in timeline.video_layers:
        new_clips = []
        for clip in layer.clips:
            sid = _clip_shot_id(clip)
            target = extend_end_by_shot.get(sid)
            if target is not None and int(clip.end_ms) < target:
                meta = dict(clip.metadata or {})
                # 保留已有 rate/freeze；若无 freeze 则标记需垫帧
                if not meta.get("freeze_tail_ms") and not meta.get("playback_rate"):
                    meta["freeze_tail_ms"] = target - int(clip.end_ms)
                new_clips.append(clip.model_copy(update={"end_ms": target, "metadata": meta}))
                changed = True
                max_end = max(max_end, target)
            else:
                new_clips.append(clip)
                max_end = max(max_end, int(clip.end_ms))
        new_layers.append(layer.model_copy(update={"clips": new_clips}))

    if not changed:
        return timeline
    return timeline.model_copy(
        update={"video_layers": new_layers, "duration_ms": max(max_end, timeline.duration_ms)}
    )


def merge_timeline_with_fallback(
    store: MemoryStore,
    *,
    script_id: str,
    plan: VideoPlan | None,
    llm_tracks: dict[str, Any] | None,
    tts_by_shot: dict[str, str] | None = None,
    existing: EditTimeline | None = None,
    mode: str = "create",
    llm_video_layers: list[Any] | None = None,
    skip_subtitle_enrich: bool = False,
) -> EditTimeline:
    """优先使用 LLM 轨道；空轨时用 shots 编译补齐；支持 merge/replace。"""
    normalized = normalize_tracks(llm_tracks)
    agent_video = extract_agent_video_clips(llm_tracks)
    parsed_layers = (
        normalize_video_layers(llm_video_layers)
        if isinstance(llm_video_layers, list)
        else None
    )
    video_layers = resolve_agent_video_layers(parsed_layers, agent_video or None)
    has_any = bool(video_layers) or any(normalized[k] for k in AUDIO_SUBTITLE_KEYS)
    if has_any and plan:
        if existing is not None and mode in ("merge", "replace"):
            return finalize_merged_timeline(
                store,
                merge_agent_timeline(
                    existing,
                    normalized,
                    script_id=script_id,
                    plan_id=plan.id,
                    mode=mode,
                    agent_video_layers=video_layers,
                ),
                plan,
                skip_subtitle_enrich=skip_subtitle_enrich,
            )
        ends = [
            c.end_ms for clips in normalized.values() for c in clips
        ] + [
            c.end_ms for layer in video_layers for c in layer.clips
        ]
        duration = max(ends, default=0)
        audio_subtitle_tracks = {
            k: list(normalized.get(k, [])) for k in AUDIO_SUBTITLE_KEYS
        }
        return finalize_merged_timeline(
            store,
            EditTimeline(
                script_id=script_id,
                plan_id=plan.id,
                duration_ms=duration,
                tracks=audio_subtitle_tracks,
                video_layers=video_layers,
                last_edited_by="agent",
                updated_at=_timeline_now(),
            ),
            plan,
            skip_subtitle_enrich=skip_subtitle_enrich,
        )
    if plan and plan.shots:
        return finalize_merged_timeline(
            store,
            compile_timeline_from_shots(
                store, script_id=script_id, plan=plan, tts_by_shot=tts_by_shot
            ),
            plan,
            skip_subtitle_enrich=skip_subtitle_enrich,
        )
    return finalize_merged_timeline(
        store,
        EditTimeline(
            script_id=script_id,
            plan_id=plan.id if plan else "",
            duration_ms=0,
            tracks=normalized,
        ),
        plan,
        skip_subtitle_enrich=skip_subtitle_enrich,
    )


def _timeline_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def _clip_is_user_protected(clip: EditClip) -> bool:
    meta = clip.metadata or {}
    if meta.get("user_locked"):
        return True
    if str(meta.get("edited_by", "")).strip() == "user":
        return True
    return False


def _layer_is_user_protected(layer: EditVideoLayer) -> bool:
    return any(_clip_is_user_protected(c) for c in layer.clips)


def merge_agent_video_layers(
    existing_layers: list[EditVideoLayer],
    agent_layers: list[EditVideoLayer],
    *,
    mode: str,
) -> list[EditVideoLayer]:
    if mode == "replace" or not existing_layers:
        return agent_layers
    protected_layers = {
        layer.id: layer for layer in existing_layers if _layer_is_user_protected(layer)
    }
    protected_clip_ids = {
        c.id for layer in protected_layers.values() for c in layer.clips
    }
    merged: list[EditVideoLayer] = list(protected_layers.values())
    seen_layer_ids = set(protected_layers.keys())
    for layer in agent_layers:
        if layer.id in seen_layer_ids:
            continue
        protected_clips = [c for c in layer.clips if c.id in protected_clip_ids]
        if protected_clips and layer.id not in protected_layers:
            merged.append(
                layer.model_copy(
                    update={
                        "clips": protected_clips
                        + [c for c in layer.clips if c.id not in protected_clip_ids]
                    }
                )
            )
        else:
            merged.append(layer)
        seen_layer_ids.add(layer.id)
    merged.sort(key=lambda item: item.z_index)
    return merged[:MAX_VIDEO_LAYERS]


def merge_agent_timeline(
    existing: EditTimeline | None,
    agent_tracks: dict[str, list[EditClip]],
    *,
    script_id: str,
    plan_id: str,
    mode: str = "merge",
    agent_video_layers: list[EditVideoLayer] | None = None,
) -> EditTimeline:
    """Agent 写入时间轴：merge 保留用户 clip，replace/create 全量替换。"""
    if existing is None or mode == "create":
        ends = [
            c.end_ms for clips in agent_tracks.values() for c in clips
        ] + [
            c.end_ms for layer in (agent_video_layers or []) for c in layer.clips
        ]
        duration = max(ends, default=0)
        layers = resolve_agent_video_layers(
            agent_video_layers,
            agent_tracks.get("video"),
        )
        return EditTimeline(
            script_id=script_id,
            plan_id=plan_id,
            duration_ms=duration,
            tracks={k: list(agent_tracks.get(k, [])) for k in AUDIO_SUBTITLE_KEYS},
            video_layers=layers,
            last_edited_by="agent",
            updated_at=_timeline_now(),
        )

    if mode == "replace" or not existing.user_edited:
        ends = [
            c.end_ms for clips in agent_tracks.values() for c in clips
        ] + [
            c.end_ms for layer in (agent_video_layers or []) for c in layer.clips
        ]
        duration = max(ends, default=existing.duration_ms)
        layers = resolve_agent_video_layers(
            agent_video_layers,
            agent_tracks.get("video"),
        )
        return existing.model_copy(
            update={
                "plan_id": plan_id or existing.plan_id,
                "duration_ms": duration or timeline_duration_ms(existing),
                "tracks": {k: list(agent_tracks.get(k, [])) for k in AUDIO_SUBTITLE_KEYS},
                "video_layers": layers,
                "revision": existing.revision + 1,
                "last_edited_by": "agent",
                "updated_at": _timeline_now(),
            }
        )

    merged_tracks: dict[str, list[EditClip]] = {k: [] for k in AUDIO_SUBTITLE_KEYS}
    for key in AUDIO_SUBTITLE_KEYS:
        existing_clips = list(existing.tracks.get(key, []))
        agent_clips = list(agent_tracks.get(key, []))
        protected = {c.id: c for c in existing_clips if _clip_is_user_protected(c)}
        protected_shots = {
            str((c.metadata or {}).get("shot_id", "")).strip()
            for c in protected.values()
            if (c.metadata or {}).get("shot_id")
        }
        merged: list[EditClip] = list(protected.values())
        seen_ids = set(protected.keys())
        for clip in agent_clips:
            if clip.id in seen_ids:
                continue
            shot_id = str((clip.metadata or {}).get("shot_id", "")).strip()
            if shot_id and shot_id in protected_shots:
                continue
            meta = dict(clip.metadata or {})
            meta.setdefault("edited_by", "agent")
            merged.append(clip.model_copy(update={"metadata": meta}))
            seen_ids.add(clip.id)
        merged.sort(key=lambda c: (c.start_ms, c.end_ms))
        merged_tracks[key] = merged

    agent_layers = resolve_agent_video_layers(
        agent_video_layers,
        agent_tracks.get("video"),
    )
    merged_layers = merge_agent_video_layers(
        existing.video_layers, agent_layers, mode="merge"
    )

    ends = [
        c.end_ms for clips in merged_tracks.values() for c in clips
    ] + [
        c.end_ms for layer in merged_layers for c in layer.clips
    ]
    duration = max(ends, default=existing.duration_ms)
    return existing.model_copy(
        update={
            "plan_id": plan_id or existing.plan_id,
            "duration_ms": duration or timeline_duration_ms(existing),
            "tracks": merged_tracks,
            "video_layers": merged_layers,
            "revision": existing.revision + 1,
            "last_edited_by": "agent",
            "updated_at": _timeline_now(),
        }
    )


def timeline_board_items(
    store: MemoryStore,
    timeline: EditTimeline,
) -> dict[str, Any]:
    """供看板 API 使用的序列化结构。"""
    from core.edit.asset_resolver import shot_by_id_for_script

    shot_by_id = shot_by_id_for_script(store, timeline.script_id)
    tracks_out: dict[str, list[dict[str, Any]]] = {}
    for key in TRACK_KEYS:
        items: list[dict[str, Any]] = []
        if key == "video":
            for layer in sorted(timeline.video_layers, key=lambda item: item.z_index):
                for clip in layer.clips:
                    items.append(
                        serialize_clip_item(store, timeline, clip, shot_by_id=shot_by_id)
                    )
        else:
            for clip in timeline.tracks.get(key, []):
                items.append(
                    serialize_clip_item(store, timeline, clip, shot_by_id=shot_by_id)
                )
        tracks_out[key] = items

    video_layers_out: list[dict[str, Any]] = []
    for layer in sorted(timeline.video_layers, key=lambda item: item.z_index):
        video_layers_out.append(
            {
                "id": layer.id,
                "name": layer.name,
                "z_index": layer.z_index,
                "clips": [
                    serialize_clip_item(store, timeline, clip, shot_by_id=shot_by_id)
                    for clip in layer.clips
                ],
            }
        )

    return {
        "timeline_id": timeline.id,
        "plan_id": timeline.plan_id,
        "duration_ms": timeline_duration_ms(timeline),
        "revision": timeline.revision,
        "user_edited": timeline.user_edited,
        "last_edited_by": timeline.last_edited_by,
        "updated_at": timeline.updated_at,
        "metadata": dict(timeline.metadata or {}),
        "tracks": tracks_out,
        "video_layers": video_layers_out,
    }
