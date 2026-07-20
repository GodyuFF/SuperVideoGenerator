"""EditTimeline 素材解析与校验。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from core.edit.edit_capabilities import edit_capability_issues
from core.edit.timeline import flat_video_clips, resolve_shot_image_ref
from core.llm.tools.shared.media_list import is_placeholder_media_url, resolve_media_access
from core.models.entities import (
    EditClip,
    EditTimeline,
    MediaAsset,
    MediaAssetType,
    Shot,
    VideoPlan,
)
from core.store.memory import MemoryStore

SuggestedUpstream = Literal[
    "script_design", "image_gen", "tts_gen", "storyboard", "none"
]
MissingCategory = Literal[
    "image", "audio", "video", "text_asset", "scene", "background", "timeline"
]


@dataclass
class MissingItem:
    category: MissingCategory
    clip_id: str
    reason: str
    suggested_upstream: SuggestedUpstream
    shot_id: str = ""
    text_asset_id: str = ""
    track: str = ""


@dataclass
class ResolvedClipMedia:
    clip_id: str
    track: str
    media_id: str
    media_type: str
    url: str
    link: str
    is_accessible: bool


@dataclass
class EditTimelineValidationReport:
    ready: bool
    missing_items: list[MissingItem] = field(default_factory=list)
    resolved_clips: list[ResolvedClipMedia] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "missing_items": [
                {
                    "category": m.category,
                    "clip_id": m.clip_id,
                    "track": m.track,
                    "shot_id": m.shot_id,
                    "text_asset_id": m.text_asset_id,
                    "reason": m.reason,
                    "suggested_upstream": m.suggested_upstream,
                }
                for m in self.missing_items
            ],
            "resolved_clips": [
                {
                    "clip_id": r.clip_id,
                    "track": r.track,
                    "media_id": r.media_id,
                    "media_type": r.media_type,
                    "url": r.url,
                    "link": r.link,
                    "is_accessible": r.is_accessible,
                }
                for r in self.resolved_clips
            ],
            "summary": self.summary,
        }


def _media_accessible(media: MediaAsset | None) -> bool:
    if media is None or not media.url:
        return False
    if is_placeholder_media_url(media.url):
        return False
    access = resolve_media_access(media.url)
    return bool(access.get("is_accessible"))


def _resolve_from_text_assets(
    store: MemoryStore, text_ids: list[str], script_id: str
) -> str | None:
    for tid in text_ids:
        text = store.get_text_asset(tid)
        if text and text.primary_media_id:
            media = store.media_assets.get(text.primary_media_id)
            if _media_accessible(media):
                return text.primary_media_id
        for media in store.list_media_for_script(script_id):
            if (
                media.source_asset_id == tid
                and media.type == MediaAssetType.IMAGE
                and _media_accessible(media)
            ):
                return media.id
    return None


def _resolve_from_variant_ids(
    store: MemoryStore,
    text_ids: list[str],
    variant_ids: list[str],
) -> str | None:
    from core.models.image_text_asset import normalize_image_text_content, resolve_variant_media_id

    for vid in variant_ids:
        for tid in text_ids:
            text = store.get_text_asset(tid)
            if not text:
                continue
            content = normalize_image_text_content(text.type, text.content)
            mid = resolve_variant_media_id(content, vid)
            if mid:
                media = store.media_assets.get(mid)
                if _media_accessible(media):
                    return mid
    return None


def shot_by_id_for_script(store: MemoryStore, script_id: str) -> dict[str, Shot]:
    plan = store.get_video_plan_for_script(script_id)
    if not plan:
        return {}
    return {s.id: s for s in plan.shots}


def _shots_by_order(plan: VideoPlan | None) -> dict[int, Shot]:
    if not plan:
        return {}
    return {s.order: s for s in plan.shots}


def _resolve_shot_for_clip(
    clip: EditClip,
    shot_by_id: dict[str, Shot],
    *,
    shots_by_order: dict[int, Shot] | None = None,
) -> Shot | None:
    """按 shot_id 或 video_plan_shot_order 解析镜头（兼容 Agent 占位 shot_id）。"""
    shot_id = ""
    if clip.source_refs and clip.source_refs.shot_id:
        shot_id = str(clip.source_refs.shot_id).strip()
    elif clip.metadata.get("shot_id"):
        shot_id = str(clip.metadata.get("shot_id")).strip()

    if shot_id and shot_id in shot_by_id:
        return shot_by_id[shot_id]

    order_raw = (
        clip.source_refs.video_plan_shot_order
        if clip.source_refs and clip.source_refs.video_plan_shot_order is not None
        else None
    )
    if order_raw is None:
        return None

    by_order = shots_by_order if shots_by_order is not None else {s.order: s for s in shot_by_id.values()}
    if order_raw in by_order:
        return by_order[order_raw]
    return None


def resolve_clip_media(
    store: MemoryStore,
    clip: EditClip,
    *,
    script_id: str,
    shot_by_id: dict[str, Shot] | None = None,
) -> ResolvedClipMedia | None:
    """按优先级解析 clip 对应媒体；无法解析返回 None。"""
    expected_types = {
        "video": (MediaAssetType.IMAGE, MediaAssetType.VIDEO),
        "audio": (MediaAssetType.AUDIO,),
    }
    if clip.track not in expected_types:
        return None

    media_id: str | None = None
    if clip.asset_ref:
        media = store.media_assets.get(clip.asset_ref)
        if media and media.type in expected_types[clip.track] and _media_accessible(media):
            media_id = media.id

    if not media_id and clip.source_refs:
        for mid in clip.source_refs.media_ids:
            media = store.media_assets.get(mid)
            if media and media.type in expected_types[clip.track] and _media_accessible(media):
                media_id = media.id
                break
        if not media_id and clip.source_refs.text_asset_ids:
            if clip.source_refs.variant_ids:
                media_id = _resolve_from_variant_ids(
                    store,
                    clip.source_refs.text_asset_ids,
                    clip.source_refs.variant_ids,
                )
            if not media_id:
                media_id = _resolve_from_text_assets(
                    store, clip.source_refs.text_asset_ids, script_id
                )

    if not media_id and shot_by_id and clip.track == "video":
        plan = store.get_video_plan_for_script(script_id)
        shot = _resolve_shot_for_clip(
            clip,
            shot_by_id,
            shots_by_order=_shots_by_order(plan),
        )
        if shot:
            media_id = resolve_shot_image_ref(store, shot)

    if not media_id and clip.track == "video" and clip.background and clip.background.asset_ref:
        bg = store.media_assets.get(clip.background.asset_ref)
        if bg and bg.type == MediaAssetType.IMAGE and _media_accessible(bg):
            media_id = bg.id

    if not media_id:
        return None

    media = store.media_assets.get(media_id)
    if not media:
        return None
    access = resolve_media_access(media.url)
    return ResolvedClipMedia(
        clip_id=clip.id,
        track=clip.track,
        media_id=media.id,
        media_type=media.type.value,
        url=media.url,
        link=str(access.get("link") or ""),
        is_accessible=bool(access.get("is_accessible")),
    )


def _upstream_for_video_missing(
    clip: EditClip, shot_by_id: dict[str, Shot]
) -> SuggestedUpstream:
    shot_id = (clip.source_refs.shot_id if clip.source_refs else "") or str(
        clip.metadata.get("shot_id") or ""
    )
    if not shot_id and not clip.asset_ref:
        return "storyboard"
    if clip.source_refs and clip.source_refs.text_asset_ids:
        return "image_gen"
    return "image_gen"


def validate_edit_timeline(
    store: MemoryStore,
    timeline: EditTimeline,
) -> EditTimelineValidationReport:
    """校验时间轴素材是否齐备、可访问。"""
    script_id = timeline.script_id
    plan = store.get_video_plan_for_script(script_id)
    shot_by_id: dict[str, Shot] = {}
    if plan:
        shot_by_id = {s.id: s for s in plan.shots}

    missing: list[MissingItem] = []
    resolved: list[ResolvedClipMedia] = []

    video_clip_count = sum(len(layer.clips) for layer in timeline.video_layers)
    track_counts = {
        "video": video_clip_count,
        "audio": len(timeline.tracks.get("audio", [])),
        "subtitle": len(timeline.tracks.get("subtitle", [])),
    }

    if not any(track_counts.values()):
        missing.append(
            MissingItem(
                category="timeline",
                clip_id="",
                track="",
                reason="剪辑计划稿为空，需 plan_edit_timeline",
                suggested_upstream="storyboard",
            )
        )

    for layer in timeline.video_layers:
        for clip in layer.clips:
            resolved_media = resolve_clip_media(
                store, clip, script_id=script_id, shot_by_id=shot_by_id
            )
            if resolved_media and resolved_media.is_accessible:
                resolved.append(resolved_media)
                continue
            upstream = _upstream_for_video_missing(clip, shot_by_id)
            text_id = ""
            if clip.source_refs and clip.source_refs.text_asset_ids:
                text_id = clip.source_refs.text_asset_ids[0]
            missing.append(
                MissingItem(
                    category="image",
                    clip_id=clip.id,
                    track="video",
                    shot_id=(clip.source_refs.shot_id if clip.source_refs else "")
                    or str(clip.metadata.get("shot_id") or ""),
                    text_asset_id=text_id,
                    reason=f"视频轨片段缺少可访问图片：{clip.label or clip.id}",
                    suggested_upstream=upstream,
                )
            )

    for clip in timeline.tracks.get("audio", []):
        resolved_media = resolve_clip_media(
            store, clip, script_id=script_id, shot_by_id=shot_by_id
        )
        if resolved_media and resolved_media.is_accessible:
            resolved.append(resolved_media)
            continue
        missing.append(
            MissingItem(
                category="audio",
                clip_id=clip.id,
                track="audio",
                shot_id=str(clip.metadata.get("shot_id") or ""),
                reason=f"音频轨片段缺少配音：{clip.label or clip.id}",
                suggested_upstream="tts_gen",
            )
        )

    for layer in timeline.video_layers:
        for clip in layer.clips:
            if clip.background and clip.background.type == "image" and clip.background.asset_ref:
                bg = store.media_assets.get(clip.background.asset_ref)
                if not _media_accessible(bg):
                    missing.append(
                        MissingItem(
                            category="background",
                            clip_id=clip.id,
                            track="video",
                            reason=f"背景图不可访问：{clip.background.asset_ref}",
                            suggested_upstream="image_gen",
                        )
                    )

    for clip_id, field, reason in edit_capability_issues(timeline):
        missing.append(
            MissingItem(
                category="timeline",
                clip_id=clip_id,
                track="video",
                reason=f"剪辑能力不支持 ({field})：{reason}",
                suggested_upstream="none",
            )
        )

    ready = len(missing) == 0
    return EditTimelineValidationReport(
        ready=ready,
        missing_items=missing,
        resolved_clips=resolved,
        summary={
            "track_counts": track_counts,
            "missing_count": len(missing),
            "resolved_count": len(resolved),
        },
    )
