"""镜内子镜与剧本 frame 文字资产同步（用户 PATCH / Agent create_frames 共用语义）。"""

from __future__ import annotations

from typing import Any

from core.assets.service import finalize_text_asset_content_for_store
from core.edit.sub_shot_helpers import (
    append_sub_shot_image,
    sub_shot_has_frame_link,
)
from core.llm.agent.script_assets import link_script_asset
from core.models.entities import (
    AssetScope,
    Shot,
    ShotSubShot,
    ShotSubShotImage,
    TextAsset,
    TextAssetType,
)
from core.store.memory import MemoryStore


def _frame_content_from_sub_shot(shot: Shot, sub: ShotSubShot, idx: int) -> dict[str, Any]:
    """由子镜字段组装 frame 文字资产 content（精简五块）。"""
    seed = (sub.description or "").strip()
    return {
        "summary": seed[:80],
        "image_prompt": seed,
        "notes": "",
        "element_refs": dict(sub.element_refs or {}),
        "variant_refs": {},
        "shot_id": shot.id,
        "prompt_locked": False,
        "reference_order": ["scene", "character", "prop"],
    }


def _create_frame_for_sub_shot(
    store: MemoryStore,
    script_id: str,
    shot: Shot,
    sub: ShotSubShot,
    idx: int,
) -> tuple[TextAsset, ShotSubShot]:
    """为子镜创建 frame 文字资产并追加到 images。"""
    script = store.get_script(script_id)
    project_id = script.project_id if script else ""
    if not project_id:
        raise ValueError("无法解析 project_id，无法创建画面资产")

    content = _frame_content_from_sub_shot(shot, sub, idx)
    name = f"画面·镜{shot.order + 1}" + (f"-{idx + 1}" if idx > 0 else "")
    asset = TextAsset(
        project_id=project_id,
        script_id=script_id,
        scope=AssetScope.SCRIPT_PRIVATE,
        type=TextAssetType.FRAME,
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

    new_image = ShotSubShotImage(frame_asset_id=asset.id)
    updated = append_sub_shot_image(sub, new_image)
    return asset, updated


def _sync_existing_frame_from_sub_shot(
    store: MemoryStore,
    sub: ShotSubShot,
    shot_id: str,
) -> None:
    """将子镜描述与 element_refs 回写已绑定的 frame 文字资产。"""
    for img in sub.images:
        frame_id = img.frame_asset_id.strip()
        if not frame_id:
            continue
        asset = store.get_text_asset(frame_id)
        if asset is None or asset.type != TextAssetType.FRAME:
            continue
        raw = dict(asset.content or {})
        seed = (sub.description or "").strip()
        if not raw.get("summary"):
            raw["summary"] = seed[:80]
        locked = bool(raw.get("prompt_locked"))
        if seed and not locked:
            raw["image_prompt"] = seed
        raw["element_refs"] = dict(sub.element_refs or {})
        raw["shot_id"] = shot_id
        asset.content = finalize_text_asset_content_for_store(
            store, asset, raw, force_recompose=not locked
        )
        store.update_text_asset(asset)


def sync_shot_sub_shot_frame_assets(
    store: MemoryStore,
    script_id: str,
    shot: Shot,
) -> Shot:
    """同步子镜与剧本画面资产：无 frame 的子镜自动创建；已关联的回写描述。"""
    if not shot.sub_shots:
        return shot

    new_sub_shots: list[ShotSubShot] = []
    for idx, sub in enumerate(shot.sub_shots):
        if sub_shot_has_frame_link(sub):
            _sync_existing_frame_from_sub_shot(store, sub, shot.id)
            new_sub_shots.append(sub)
        else:
            _, updated = _create_frame_for_sub_shot(store, script_id, shot, sub, idx)
            new_sub_shots.append(updated)

    return shot.model_copy(update={"sub_shots": new_sub_shots})

