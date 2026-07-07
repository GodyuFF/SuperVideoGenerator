"""图文资产与已链接图片摘要（storyboard / editing 共用）。"""

from __future__ import annotations

from typing import Any

from core.models.entities import TextAssetType
from core.store.memory import MemoryStore


def shot_ref_key_for_type(asset_type: str) -> str:
    if asset_type in ("character", "scene", "prop"):
        return asset_type
    return "image"


def build_plots_for_script(store: MemoryStore, script_id: str) -> list[dict[str, Any]]:
    """plot / narration 文字资产摘要。"""
    plots: list[dict[str, Any]] = []
    for asset in sorted(
        store.list_assets_for_script(script_id),
        key=lambda a: (a.type.value, a.name),
    ):
        if asset.type.value not in ("plot", "narration"):
            continue
        content = asset.content if isinstance(asset.content, dict) else {}
        text = str(content.get("text", "") or content.get("summary", "")).strip()
        if not text and isinstance(asset.content, str):
            text = asset.content.strip()
        plots.append(
            {
                "id": asset.id,
                "name": asset.name,
                "type": asset.type.value,
                "text": text[:4000],
            }
        )
    return plots


def build_assets_with_images_from_scan(
    assets: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """从 scan_text_assets 的 assets 列表提取已链接图片摘要。"""
    assets_with_images: list[dict[str, Any]] = []
    for a in assets:
        if not a.get("has_image") or not a.get("linked_image_id"):
            continue
        text_asset_id = str(a["id"])
        media_id = str(a.get("linked_image_id"))
        asset_type = str(a.get("type", ""))
        ref_key = shot_ref_key_for_type(asset_type)
        if asset_type not in (
            TextAssetType.CHARACTER.value,
            TextAssetType.SCENE.value,
            TextAssetType.PROP.value,
        ):
            ref_key = "image"
            text_asset_id = ""
        assets_with_images.append(
            {
                "id": text_asset_id or media_id,
                "name": a.get("name"),
                "type": asset_type,
                "ref_key": ref_key,
                "text_asset_id": text_asset_id or None,
                "media_id": media_id,
                "linked_image_id": media_id,
                "image_status": a.get("image_status"),
                "variants": a.get("variants") or [],
                "asset_refs_example": {ref_key: [text_asset_id or media_id]},
            }
        )
    return assets_with_images
