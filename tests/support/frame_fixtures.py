"""测试用画面（frame）资产与镜头关联辅助。"""

from __future__ import annotations

from core.models.entities import (
    AssetScope,
    MediaAsset,
    MediaAssetType,
    TextAsset,
    TextAssetType,
    VideoPlanShot,
)
from core.store.memory import MemoryStore


def ensure_shot_frame_image(
    store: MemoryStore,
    *,
    project_id: str,
    script_id: str,
    shot: VideoPlanShot,
    element_refs: dict[str, list[str]] | None = None,
    image_url: str = "https://images.test/frame.png",
) -> tuple[TextAsset, MediaAsset]:
    """为镜头创建 frame 文字资产、配图，并写入 shot.asset_refs.frame。"""
    refs = dict(element_refs or {})
    if not refs:
        shot_refs = shot.asset_refs or {}
        for key in ("scene", "character", "prop"):
            ids = shot_refs.get(key) or []
            if ids:
                refs[key] = [str(i) for i in ids]

    frame = TextAsset(
        project_id=project_id,
        script_id=script_id,
        type=TextAssetType.FRAME,
        scope=AssetScope.SCRIPT_PRIVATE,
        name=f"画面·镜{shot.order + 1}",
        content={
            "description": shot.narration_text or "测试画面",
            "element_refs": refs,
            "shot_id": shot.id,
        },
        source_script_id=script_id,
        reuse_policy="private",
    )
    store.add_text_asset(frame)
    media = MediaAsset(
        project_id=project_id,
        script_id=script_id,
        type=MediaAssetType.IMAGE,
        name=frame.name,
        url=image_url,
        source_asset_id=frame.id,
    )
    store.add_media_asset(media)
    frame.primary_media_id = media.id
    store.update_text_asset(frame)

    asset_refs = dict(shot.asset_refs or {})
    asset_refs["frame"] = [frame.id]
    shot.asset_refs = asset_refs
    return frame, media
