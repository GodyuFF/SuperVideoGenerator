"""patch_video_text_asset 与 video_clip 用户编辑。"""

from __future__ import annotations

from typing import Any

from core.assets.video_prompt import compose_video_clip_prompt
from core.models.entities import TextAsset, TextAssetType
from core.models.video_text_asset import is_video_text_asset, normalize_video_clip_content
from core.store.memory import MemoryStore


def patch_video_text_asset(
    store: MemoryStore,
    *,
    project_id: str,
    asset_id: str,
    name: str | None = None,
    content: dict[str, Any] | None = None,
    primary_media_id: str | None = None,
    force_recompose_prompt: bool = False,
    prompt_locked: bool | None = None,
) -> TextAsset:
    """用户 PATCH 更新 video_clip 文字资产。"""
    asset = store.get_text_asset(asset_id)
    if not asset:
        raise ValueError(f"资产 {asset_id} 不存在")
    if asset.project_id != project_id:
        raise ValueError(f"资产 {asset_id} 不属于项目 {project_id}")
    if not is_video_text_asset(asset.type.value):
        raise ValueError(f"资产 {asset_id} 类型 {asset.type.value} 不是 video_clip")

    from core.assets.service import _project_style

    style = _project_style(store, project_id)

    if name is not None and name.strip():
        asset.name = name.strip()
    if primary_media_id is not None:
        asset.primary_media_id = primary_media_id or None

    if content is not None:
        merged = normalize_video_clip_content(asset.content)
        merged.update({k: v for k, v in content.items() if v is not None})
        if prompt_locked is not None:
            merged["prompt_locked"] = prompt_locked
        if force_recompose_prompt:
            merged["prompt_locked"] = False
        from core.assets.element_refs import normalize_element_refs, validate_element_refs_for_owner

        refs = normalize_element_refs(merged.get("element_refs"))
        if refs:
            validate_element_refs_for_owner(store, asset.id, refs)
            merged["element_refs"] = refs
        media_refs = merged.get("media_refs") or []
        if not isinstance(media_refs, list):
            media_refs = [str(media_refs)]
        merged["media_refs"] = [str(m).strip() for m in media_refs if str(m).strip()]
        locked = bool(merged.get("prompt_locked")) and not force_recompose_prompt
        if not locked:
            merged["video_prompt"] = compose_video_clip_prompt(
                merged, store=store, project_style=style
            )
            merged["prompt_version"] = int(merged.get("prompt_version") or 0) + 1
        asset.content = merged
        asset.user_edited = True

    store.update_text_asset(asset)
    return asset
