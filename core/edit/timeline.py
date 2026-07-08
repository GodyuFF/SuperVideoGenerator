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
    VideoPlan,
    VideoPlanShot,
    new_id,
)
from core.store.memory import MemoryStore

TRACK_KEYS = ("video", "audio", "subtitle")
MAX_VIDEO_LAYERS = 5
DEFAULT_LAYER_NAME = "主画面"


def build_tts_by_shot(store: MemoryStore, script_id: str) -> dict[str, str]:
    """从已落盘 AUDIO 资产的 metadata.shot_id 构建 shot → asset 映射。"""
    mapping: dict[str, str] = {}
    for media in store.list_media_for_script(script_id):
        if media.type != MediaAssetType.AUDIO:
            continue
        shot_id = str((media.metadata or {}).get("shot_id") or "").strip()
        if shot_id:
            mapping[shot_id] = media.id
    return mapping


def _shot_tts_duration_ms(store: MemoryStore, audio_ref: str | None) -> int:
    if not audio_ref:
        return 0
    media = store.media_assets.get(audio_ref)
    if not media:
        return 0
    return int((media.metadata or {}).get("duration_ms") or 0)


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
    timeline = ensure_video_layers(timeline)
    if timeline.video_layers:
        layers = [
            layer.model_copy(
                update={"clips": [_normalize_clip_motion(c) for c in layer.clips]}
            )
            for layer in timeline.video_layers
        ]
        timeline = timeline.model_copy(update={"video_layers": layers})
        sync_legacy_video_track(timeline)
        return timeline
    video = timeline.tracks.get("video", [])
    if not video:
        return timeline
    tracks = dict(timeline.tracks)
    tracks["video"] = [_normalize_clip_motion(c) for c in video]
    return timeline.model_copy(update={"tracks": tracks})


def normalize_video_layers(
    raw_layers: list[Any] | None,
    *,
    legacy_video_clips: list[EditClip] | None = None,
) -> list[EditVideoLayer]:
    """解析 video_layers；空时从 legacy tracks.video 迁移为单层。"""
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
    if legacy_video_clips:
        layer_id = new_id("vly")
        clips = [
            c.model_copy(
                update={
                    "layer_id": layer_id,
                    "transform": c.transform or default_clip_transform(),
                }
            )
            for c in legacy_video_clips
        ]
        return [
            EditVideoLayer(
                id=layer_id,
                name=DEFAULT_LAYER_NAME,
                z_index=0,
                clips=clips,
            )
        ]
    return []


def ensure_video_layers(timeline: EditTimeline) -> EditTimeline:
    """确保 timeline 含 video_layers（从 tracks.video 迁移）。"""
    if timeline.video_layers:
        return timeline
    legacy = list(timeline.tracks.get("video", []))
    if not legacy:
        return timeline
    layers = normalize_video_layers(None, legacy_video_clips=legacy)
    return timeline.model_copy(update={"video_layers": layers})


def sync_legacy_video_track(timeline: EditTimeline) -> None:
    """将 video_layers 扁平化写入 tracks.video（向后兼容）。"""
    timeline = ensure_video_layers(timeline)
    flat: list[EditClip] = []
    for layer in sorted(timeline.video_layers, key=lambda item: item.z_index):
        for clip in layer.clips:
            flat.append(clip.model_copy(update={"layer_id": layer.id}))
    timeline.tracks["video"] = flat


def flat_video_clips(timeline: EditTimeline) -> list[EditClip]:
    timeline = ensure_video_layers(timeline)
    out: list[EditClip] = []
    for layer in sorted(timeline.video_layers, key=lambda item: item.z_index):
        out.extend(layer.clips)
    return out


def serialize_clip_item(
    store: MemoryStore,
    timeline: EditTimeline,
    clip: EditClip,
    *,
    shot_by_id: dict[str, VideoPlanShot],
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
    """将 LLM/JSON 轨道数据规范为 EditClip 列表。"""
    out: dict[str, list[EditClip]] = {k: [] for k in TRACK_KEYS}
    if not isinstance(tracks, dict):
        return out
    for key in TRACK_KEYS:
        raw_list = tracks.get(key) or []
        if not isinstance(raw_list, list):
            continue
        for raw in raw_list:
            if not isinstance(raw, dict):
                continue
            track = str(raw.get("track", key))
            if track not in TRACK_KEYS:
                track = key
            clip = _parse_clip_from_raw(raw, track=track)
            if clip:
                out[key].append(clip)
        out[key].sort(key=lambda c: (c.start_ms, c.end_ms))
    return out


def timeline_duration_ms(timeline: EditTimeline) -> int:
    if timeline.duration_ms > 0:
        return timeline.duration_ms
    max_end = 0
    timeline = ensure_video_layers(timeline)
    for layer in timeline.video_layers:
        for clip in layer.clips:
            max_end = max(max_end, clip.end_ms)
    for clips in timeline.tracks.values():
        for clip in clips:
            if clip.track != "video":
                max_end = max(max_end, clip.end_ms)
    return max_end


def validate_timeline_clips(timeline: EditTimeline) -> list[str]:
    """返回重叠/非法片段警告（不阻断保存）。"""
    warnings: list[str] = []
    timeline = ensure_video_layers(timeline)
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
    timeline = ensure_video_layers(timeline)
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
    """从 VideoPlan 镜头确定性编译三轨时间轴（LLM 漏轨时的 fallback）。"""
    from core.edit.edit_capabilities import resolve_motion

    if tts_by_shot is None:
        tts_by_shot = build_tts_by_shot(store, script_id)
    else:
        tts_by_shot = dict(tts_by_shot)
    auto_tts = build_tts_by_shot(store, script_id)
    for shot_id, asset_id in auto_tts.items():
        tts_by_shot.setdefault(shot_id, asset_id)
    video_clips: list[EditClip] = []
    audio_clips: list[EditClip] = []
    subtitle_clips: list[EditClip] = []
    cursor = 0
    shots = sorted(plan.shots, key=lambda s: s.order)

    for shot in shots:
        duration = max(shot.duration_ms, 1000)
        audio_ref = tts_by_shot.get(shot.id)
        tts_duration = _shot_tts_duration_ms(store, audio_ref)
        if tts_duration > duration:
            duration = tts_duration
        start = cursor
        end = cursor + duration
        image_id = resolve_shot_image_ref(store, shot)
        video_label = f"镜{shot.order + 1} · {shot.camera_motion}"
        if shot.narration_text:
            video_label += f" · {shot.narration_text[:40]}"
        video_clips.append(
            EditClip(
                track="video",
                start_ms=start,
                end_ms=end,
                label=video_label,
                asset_ref=image_id,
                motion=resolve_motion(shot.camera_motion or "ken_burns_in"),
                transform=default_clip_transform(),
                metadata={"shot_id": shot.id, "order": shot.order},
            )
        )
        narration = shot.narration_text.strip()
        if narration or audio_ref:
            audio_clips.append(
                EditClip(
                    track="audio",
                    start_ms=start,
                    end_ms=end,
                    label=narration or f"镜{shot.order + 1} 配音",
                    asset_ref=audio_ref,
                    metadata={"shot_id": shot.id},
                )
            )
        if narration:
            subtitle_clips.append(
                EditClip(
                    track="subtitle",
                    start_ms=start,
                    end_ms=end,
                    label=narration,
                    metadata={"shot_id": shot.id},
                )
            )
        cursor = end

    main_layer_id = new_id("vly")
    video_layers = [
        EditVideoLayer(
            id=main_layer_id,
            name=DEFAULT_LAYER_NAME,
            z_index=0,
            clips=[
                c.model_copy(update={"layer_id": main_layer_id, "transform": default_clip_transform()})
                for c in video_clips
            ],
        )
    ]
    timeline = EditTimeline(
        script_id=script_id,
        plan_id=plan.id,
        duration_ms=cursor,
        tracks={
            "video": video_clips,
            "audio": audio_clips,
            "subtitle": subtitle_clips,
        },
        video_layers=video_layers,
    )
    return timeline


def resolve_shot_image_ref(store: MemoryStore, shot: VideoPlanShot) -> str | None:
    refs = shot.asset_refs or {}
    variant_refs = shot.variant_refs or {}

    def _resolve_ref(ref_str: str) -> str | None:
        media = store.media_assets.get(ref_str)
        if (
            media
            and media.type == MediaAssetType.IMAGE
            and media.url
            and not str(media.url).startswith("placeholder:")
        ):
            return media.id
        text = store.get_text_asset(ref_str)
        if text:
            vid = variant_refs.get(ref_str, "")
            if vid:
                from core.models.image_text_asset import (
                    normalize_image_text_content,
                    resolve_variant_media_id,
                )

                content = normalize_image_text_content(text.type, text.content)
                mid = resolve_variant_media_id(content, vid)
                if mid:
                    return mid
            if text.primary_media_id:
                return text.primary_media_id
            script_ids = {text.script_id} if text else set()
            for script in store.scripts.values():
                script_ids.add(script.id)
            for sid in script_ids:
                for media in store.list_media_for_script(sid):
                    if (
                        media.source_asset_id == ref_str
                        and media.type == MediaAssetType.IMAGE
                        and media.url
                    ):
                        return media.id
        return None

    for key in ("frame", "image"):
        for ref_id in refs.get(key) or []:
            mid = _resolve_ref(str(ref_id))
            if mid:
                return mid

    # 纯空镜镜头：仅 scene 且无 frame 时允许 scene 背景板
    if not refs.get("frame"):
        for ref_id in refs.get("scene") or []:
            mid = _resolve_ref(str(ref_id))
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
    """从 Store TTS 与 VideoPlan 补齐缺失的 audio/subtitle 轨（不覆盖 user_locked clip）。"""
    if plan is None:
        plan = store.get_video_plan_for_script(timeline.script_id)
    if not plan or not plan.shots:
        return timeline

    reference = compile_timeline_from_shots(store, script_id=timeline.script_id, plan=plan)
    tts_by_shot = build_tts_by_shot(store, timeline.script_id)
    if not tts_by_shot and not reference.tracks.get("audio"):
        return timeline

    ref_by_shot: dict[str, dict[str, EditClip]] = {"audio": {}, "subtitle": {}}
    for track_name in ("audio", "subtitle"):
        for clip in reference.tracks.get(track_name, []):
            shot_id = str((clip.metadata or {}).get("shot_id") or "").strip()
            if shot_id:
                ref_by_shot[track_name][shot_id] = clip

    tracks = dict(timeline.tracks)
    for track_name in ("audio", "subtitle"):
        if skip_subtitle_enrich and track_name == "subtitle":
            continue
        existing = list(tracks.get(track_name, []))
        ref_clips = reference.tracks.get(track_name, [])
        if not existing and ref_clips:
            tracks[track_name] = ref_clips
            continue

        merged: list[EditClip] = []
        covered_shots: set[str] = set()
        for clip in existing:
            if _clip_is_user_protected(clip):
                merged.append(clip)
                shot_id = str((clip.metadata or {}).get("shot_id") or "").strip()
                if shot_id:
                    covered_shots.add(shot_id)
                continue
            shot_id = str((clip.metadata or {}).get("shot_id") or "").strip()
            if (
                track_name == "audio"
                and not clip.asset_ref
                and shot_id
                and shot_id in tts_by_shot
            ):
                merged.append(
                    clip.model_copy(update={"asset_ref": tts_by_shot[shot_id]})
                )
                covered_shots.add(shot_id)
            else:
                merged.append(clip)
                if shot_id:
                    covered_shots.add(shot_id)

        for shot_id, ref_clip in ref_by_shot[track_name].items():
            if shot_id in covered_shots:
                continue
            merged.append(ref_clip)
        merged.sort(key=lambda c: (c.start_ms, c.end_ms))
        tracks[track_name] = merged

    return timeline.model_copy(update={"tracks": tracks})


def finalize_merged_timeline(
    store: MemoryStore,
    timeline: EditTimeline,
    plan: VideoPlan | None,
    *,
    skip_subtitle_enrich: bool = False,
) -> EditTimeline:
    """Agent merge / 导出前：补齐 audio/subtitle 并归一化运镜。"""
    from core.edit.subtitle_align import enrich_subtitles_from_audio

    timeline = enrich_timeline_audio_from_store(
        store, timeline, plan, skip_subtitle_enrich=skip_subtitle_enrich
    )
    if not skip_subtitle_enrich:
        timeline = enrich_subtitles_from_audio(store, timeline, plan)
    return normalize_timeline_motions(timeline)


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
    video_layers = normalize_video_layers(
        llm_video_layers if isinstance(llm_video_layers, list) else None,
        legacy_video_clips=normalized.get("video"),
    )
    if video_layers:
        normalized["video"] = [
            c for layer in video_layers for c in layer.clips
        ]
    has_any = bool(video_layers) or any(normalized[k] for k in TRACK_KEYS)
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
        duration = max(
            (c.end_ms for clips in normalized.values() for c in clips),
            default=0,
        )
        return finalize_merged_timeline(
            store,
            EditTimeline(
                script_id=script_id,
                plan_id=plan.id,
                duration_ms=duration,
                tracks=normalized,
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
        duration = max(
            (c.end_ms for clips in agent_tracks.values() for c in clips),
            default=0,
        )
        layers = agent_video_layers or normalize_video_layers(
            None, legacy_video_clips=agent_tracks.get("video", [])
        )
        return EditTimeline(
            script_id=script_id,
            plan_id=plan_id,
            duration_ms=duration,
            tracks={k: list(agent_tracks.get(k, [])) for k in TRACK_KEYS},
            video_layers=layers,
            last_edited_by="agent",
            updated_at=_timeline_now(),
        )

    existing = ensure_video_layers(existing)

    if mode == "replace" or not existing.user_edited:
        duration = max(
            (c.end_ms for clips in agent_tracks.values() for c in clips),
            default=existing.duration_ms,
        )
        layers = agent_video_layers or normalize_video_layers(
            None, legacy_video_clips=agent_tracks.get("video", [])
        )
        return existing.model_copy(
            update={
                "plan_id": plan_id or existing.plan_id,
                "duration_ms": duration or timeline_duration_ms(existing),
                "tracks": {k: list(agent_tracks.get(k, [])) for k in TRACK_KEYS},
                "video_layers": layers,
                "revision": existing.revision + 1,
                "last_edited_by": "agent",
                "updated_at": _timeline_now(),
            }
        )

    merged_tracks: dict[str, list[EditClip]] = {k: [] for k in TRACK_KEYS}
    for key in TRACK_KEYS:
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

    agent_layers = agent_video_layers or normalize_video_layers(
        None, legacy_video_clips=agent_tracks.get("video", [])
    )
    merged_layers = merge_agent_video_layers(
        existing.video_layers, agent_layers, mode="merge"
    )
    merged_tracks["video"] = [c for layer in merged_layers for c in layer.clips]

    duration = max(
        (c.end_ms for clips in merged_tracks.values() for c in clips),
        default=existing.duration_ms,
    )
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

    timeline = ensure_video_layers(timeline)
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
        "tracks": tracks_out,
        "video_layers": video_layers_out,
    }
