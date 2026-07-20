"""剪辑合成：从 EditTimeline 编译成片描述（Remotion SSR / 占位 URL）。"""

from __future__ import annotations

from typing import Any

from core.edit.asset_resolver import resolve_clip_media, shot_by_id_for_script
from core.edit.timeline import flat_video_clips, timeline_duration_ms
from core.edit.transform_interp import interpolate_transform, collect_timeline_boundaries
from core.guards.script_style import normalize_style_mode_id
from core.models.entities import EditClip, EditTimeline, MediaAssetType, Shot, VideoStyleMode
from core.store.memory import MemoryStore


def _shot_by_id_for_timeline(
    store: MemoryStore, timeline: EditTimeline
) -> dict[str, Shot]:
    return shot_by_id_for_script(store, timeline.script_id)


def _resolved_media_id(
    store: MemoryStore,
    timeline: EditTimeline,
    clip: EditClip,
    *,
    shot_by_id: dict[str, Shot] | None = None,
) -> str | None:
    """与 validate_edit_timeline 一致：优先 clip.asset_ref，再 source_refs / shot。"""
    resolved = resolve_clip_media(
        store,
        clip,
        script_id=timeline.script_id,
        shot_by_id=shot_by_id or _shot_by_id_for_timeline(store, timeline),
    )
    if resolved:
        return resolved.media_id
    return clip.asset_ref or None


def gather_timeline_media(store: MemoryStore, timeline: EditTimeline) -> dict[str, Any]:
    """汇总时间轴引用的媒体资产。"""
    images: list[dict[str, Any]] = []
    videos: list[dict[str, Any]] = []
    audios: list[dict[str, Any]] = []
    missing: list[str] = []
    shot_by_id = _shot_by_id_for_timeline(store, timeline)

    for layer in timeline.video_layers:
        for clip in layer.clips:
            ref = _resolved_media_id(store, timeline, clip, shot_by_id=shot_by_id)
            if not ref:
                missing.append(f"{clip.id}:no_ref")
                continue
            media = store.media_assets.get(ref)
            if not media:
                missing.append(ref)
                continue
            item = {
                "id": media.id,
                "url": media.url,
                "name": media.name,
                "clip_id": clip.id,
                "layer_id": layer.id,
                "z_index": layer.z_index,
                "start_ms": clip.start_ms,
                "end_ms": clip.end_ms,
                "motion": clip.motion,
            }
            if media.type == MediaAssetType.IMAGE:
                images.append(item)
            elif media.type == MediaAssetType.VIDEO:
                videos.append(item)

    for clip in timeline.tracks.get("audio", []):
        ref = _resolved_media_id(store, timeline, clip, shot_by_id=shot_by_id)
        if not ref:
            continue
        media = store.media_assets.get(ref)
        if not media or media.type != MediaAssetType.AUDIO:
            continue
        audios.append(
            {
                "id": media.id,
                "url": media.url,
                "name": media.name,
                "clip_id": clip.id,
                "start_ms": clip.start_ms,
                "end_ms": clip.end_ms,
            }
        )

    return {
        "images": images,
        "videos": videos,
        "audios": audios,
        "missing_refs": missing,
        "duration_ms": timeline_duration_ms(timeline),
    }


def compose_timeline_plan(
    store: MemoryStore,
    timeline: EditTimeline,
    *,
    style_mode: VideoStyleMode,
) -> dict[str, Any]:
    """
    生成合成计划（storybook → Ken Burns + 配音；ai_video → 视频轨拼接）。
    成片由 core/edit/ffmpeg_renderer.py 执行。
    """
    media = gather_timeline_media(store, timeline)
    duration = timeline_duration_ms(timeline)
    mode = "ken_burns_compose" if style_mode == VideoStyleMode.STORYBOOK else "video_concat"
    shot_by_id = _shot_by_id_for_timeline(store, timeline)

    def _clip_export_order_key(clip: EditClip) -> tuple[int, int, int]:
        """主画面层导出顺序：shot_order 优先，否则 start_ms。"""
        order = -1
        refs = clip.source_refs
        if refs and refs.video_plan_shot_order is not None:
            order = int(refs.video_plan_shot_order)
        else:
            raw = (clip.metadata or {}).get("order")
            if raw is not None:
                try:
                    order = int(raw)
                except (TypeError, ValueError):
                    order = -1
        return (order if order >= 0 else 10_000, clip.start_ms, clip.end_ms)

    segments: list[dict[str, Any]] = []
    composite_slices: list[dict[str, Any]] = []
    sorted_bounds = collect_timeline_boundaries(timeline)
    for i in range(len(sorted_bounds) - 1):
        start_ms = sorted_bounds[i]
        end_ms = sorted_bounds[i + 1]
        if end_ms <= start_ms:
            continue
        mid_ms = (start_ms + end_ms) // 2
        active_layers: list[dict[str, Any]] = []
        for layer in sorted(timeline.video_layers, key=lambda item: item.z_index):
            for clip in layer.clips:
                if clip.start_ms <= mid_ms < clip.end_ms:
                    local_ms = mid_ms - clip.start_ms
                    tr = interpolate_transform(clip, local_ms)
                    asset_ref = _resolved_media_id(
                        store, timeline, clip, shot_by_id=shot_by_id
                    )
                    active_layers.append(
                        {
                            "clip_id": clip.id,
                            "layer_id": layer.id,
                            "z_index": layer.z_index,
                            "asset_ref": asset_ref,
                            "transform": {
                                "x": tr.x,
                                "y": tr.y,
                                "width": tr.width,
                                "height": tr.height,
                                "opacity": tr.opacity,
                                "rotation": tr.rotation,
                                "scale": tr.scale,
                            },
                        }
                    )
                    break
        if active_layers:
            composite_slices.append(
                {
                    "start_ms": start_ms,
                    "end_ms": end_ms,
                    "layers": active_layers,
                }
            )

    for layer in sorted(timeline.video_layers, key=lambda item: item.z_index):
        layer_clips = list(layer.clips)
        if layer.z_index == 0:
            layer_clips.sort(key=_clip_export_order_key)
        for clip in layer_clips:
            motion = clip.motion or "ken_burns_in"
            if clip.motion_detail and clip.motion_detail.type:
                motion = clip.motion_detail.type
            asset_ref = _resolved_media_id(store, timeline, clip, shot_by_id=shot_by_id)
            tr = interpolate_transform(clip, 0)
            seg: dict[str, Any] = {
                "clip_id": clip.id,
                "layer_id": layer.id,
                "z_index": layer.z_index,
                "start_ms": clip.start_ms,
                "end_ms": clip.end_ms,
                "label": clip.label,
                "motion": motion,
                "asset_ref": asset_ref,
                "transform": {
                    "x": tr.x,
                    "y": tr.y,
                    "width": tr.width,
                    "height": tr.height,
                    "opacity": tr.opacity,
                    "rotation": tr.rotation,
                    "scale": tr.scale,
                },
                "edit_description": clip.edit_description,
                "transition_in": clip.transition_in.model_dump() if clip.transition_in else None,
                "transition_out": clip.transition_out.model_dump() if clip.transition_out else None,
                "background": clip.background.model_dump() if clip.background else None,
                "motion_detail": clip.motion_detail.model_dump() if clip.motion_detail else None,
                "source_refs": clip.source_refs.model_dump() if clip.source_refs else None,
            }
            if asset_ref and asset_ref in store.media_assets:
                seg["url"] = store.media_assets[asset_ref].url
            segments.append(seg)

    audio_tracks: list[dict[str, Any]] = []
    for clip in timeline.tracks.get("audio", []):
        audio_ref = _resolved_media_id(store, timeline, clip, shot_by_id=shot_by_id)
        audio_tracks.append(
            {
                "clip_id": clip.id,
                "start_ms": clip.start_ms,
                "end_ms": clip.end_ms,
                "asset_ref": audio_ref,
                "label": clip.label,
            }
        )

    return {
        "mode": mode,
        "style_mode": normalize_style_mode_id(style_mode) or str(style_mode),
        "duration_ms": duration,
        "segments": segments,
        "composite_slices": composite_slices,
        "audio_tracks": audio_tracks,
        "subtitle_tracks": [
            {
                "clip_id": c.id,
                "start_ms": c.start_ms,
                "end_ms": c.end_ms,
                "label": c.label,
            }
            for c in timeline.tracks.get("subtitle", [])
        ],
        "media_summary": {
            "image_count": len(media["images"]),
            "video_count": len(media["videos"]),
            "audio_count": len(media["audios"]),
            "missing_refs": media["missing_refs"],
        },
    }
