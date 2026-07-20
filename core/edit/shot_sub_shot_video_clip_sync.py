"""镜内子镜与 video_clip 文字资产同步（用户 PATCH / Agent create_video_clips 共用语义）。"""

from __future__ import annotations

from typing import Any

from core.assets.service import finalize_text_asset_content_for_store
from core.edit.sub_shot_helpers import (
    append_sub_shot_video,
    sub_shot_has_video_clip_link,
)
from core.llm.agent.script_assets import link_script_asset
from core.models.entities import (
    AssetScope,
    Shot,
    ShotSubShot,
    ShotSubShotVideo,
    TextAsset,
    TextAssetType,
)
from core.store.memory import MemoryStore


def _video_clip_content_from_sub_shot(shot: Shot, sub: ShotSubShot, idx: int) -> dict[str, Any]:
    """由子镜字段组装 video_clip 文字资产 content。"""
    desc = (sub.description or "").strip()
    return {
        "summary": desc[:80],
        "video_prompt": desc,
        "tags": [],
        "notes": "",
        "video_mode": "auto",
        "camera_motion": (sub.camera_motion or "static").strip(),
        "element_refs": dict(sub.element_refs or {}),
        "media_refs": [],
        "reference_order": ["scene", "character", "prop", "frame", "media"],
        "shot_id": shot.id,
        "sub_shot_id": sub.id,
        "prompt_locked": False,
        "prompt_version": 0,
    }


def _create_video_clip_for_sub_shot(
    store: MemoryStore,
    script_id: str,
    shot: Shot,
    sub: ShotSubShot,
    idx: int,
) -> tuple[TextAsset, ShotSubShot]:
    """为子镜创建 video_clip 文字资产并追加到 videos。"""
    script = store.get_script(script_id)
    project_id = script.project_id if script else ""
    if not project_id:
        raise ValueError("无法解析 project_id，无法创建 video_clip 资产")

    content = _video_clip_content_from_sub_shot(shot, sub, idx)
    name = f"视频片段·镜{shot.order + 1}" + (f"-{idx + 1}" if idx > 0 else "")
    asset = TextAsset(
        project_id=project_id,
        script_id=script_id,
        scope=AssetScope.SCRIPT_PRIVATE,
        type=TextAssetType.VIDEO_CLIP,
        name=name,
        content=content,
        source_script_id=script_id,
        reuse_policy="private",
    )
    asset.content = finalize_text_asset_content_for_store(
        store, asset, content, force_recompose=True
    )
    store.add_text_asset(asset)
    link_script_asset(store, script_id, asset.id)

    new_video = ShotSubShotVideo(
        video_clip_asset_id=asset.id,
        camera_motion=sub.camera_motion or "static",
    )
    updated = append_sub_shot_video(sub, new_video)
    return asset, updated


def _sync_existing_video_clip_from_sub_shot(
    store: MemoryStore,
    sub: ShotSubShot,
    shot_id: str,
) -> None:
    """将子镜描述与 element_refs 回写已绑定的 video_clip 文字资产。"""
    for vid in sub.videos:
        clip_id = vid.video_clip_asset_id.strip()
        if not clip_id:
            continue
        asset = store.get_text_asset(clip_id)
        if asset is None or asset.type != TextAssetType.VIDEO_CLIP:
            continue
        raw = dict(asset.content or {})
        desc = (sub.description or "").strip()
        if not bool(raw.get("prompt_locked")):
            raw["video_prompt"] = desc or str(raw.get("video_prompt") or "").strip()
        if not raw.get("summary"):
            raw["summary"] = desc[:80]
        raw["element_refs"] = dict(sub.element_refs or {})
        raw["shot_id"] = shot_id
        raw["sub_shot_id"] = sub.id
        if sub.camera_motion:
            raw["camera_motion"] = sub.camera_motion
        locked = bool(raw.get("prompt_locked"))
        asset.content = finalize_text_asset_content_for_store(
            store, asset, raw, force_recompose=not locked
        )
        store.update_text_asset(asset)


def sync_shot_sub_shot_video_clip_assets(
    store: MemoryStore,
    script_id: str,
    shot: Shot,
) -> Shot:
    """同步子镜与 video_clip 资产：无 clip 的子镜自动创建；已关联的回写描述。"""
    if not shot.sub_shots:
        return shot

    new_sub_shots: list[ShotSubShot] = []
    for idx, sub in enumerate(shot.sub_shots):
        if sub_shot_has_video_clip_link(sub):
            _sync_existing_video_clip_from_sub_shot(store, sub, shot.id)
            new_sub_shots.append(sub)
        else:
            _, updated = _create_video_clip_for_sub_shot(store, script_id, shot, sub, idx)
            new_sub_shots.append(updated)

    return shot.model_copy(update={"sub_shots": new_sub_shots})
