"""图文资产 PATCH 与用户编辑服务。"""

from __future__ import annotations

from typing import Any

from core.assets.image_prompt import apply_composed_prompts, finalize_image_text_content
from core.models.entities import StyleConfig, TextAsset, TextAssetType
from core.models.image_text_asset import is_image_text_asset, normalize_image_text_content
from core.store.memory import MemoryStore


def _project_style(store: MemoryStore, project_id: str) -> StyleConfig | None:
    project = store.get_project(project_id)
    if not project:
        return None
    return project.config.style


def patch_text_asset(
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
    """用户 PATCH 更新图文资产（character/prop/scene）。"""
    asset = store.get_text_asset(asset_id)
    if not asset:
        raise ValueError(f"资产 {asset_id} 不存在")
    if asset.project_id != project_id:
        raise ValueError(f"资产 {asset_id} 不属于项目 {project_id}")
    if not is_image_text_asset(asset.type):
        raise ValueError(f"资产 {asset_id} 类型 {asset.type.value} 不支持 content 编辑")

    style = _project_style(store, project_id)

    if name is not None and name.strip():
        asset.name = name.strip()

    if primary_media_id is not None:
        asset.primary_media_id = primary_media_id or None

    if content is not None:
        merged = dict(normalize_image_text_content(asset.type, asset.content))
        merged.update(content)
        if prompt_locked is not None:
            merged["prompt_locked"] = prompt_locked
        if force_recompose_prompt:
            merged["prompt_locked"] = False
            merged["image_prompt"] = ""
        merged = apply_composed_prompts(
            asset.type,
            merged,
            project_style=style,
            preserve_prompt_lock=not force_recompose_prompt,
            force_recompose=force_recompose_prompt,
        )
        asset.content = merged
        asset.user_edited = True

    store.update_text_asset(asset)
    return asset


def finalize_text_asset_content_for_store(
    store: MemoryStore,
    asset: TextAsset,
    raw_content: Any,
    *,
    force_recompose: bool = False,
) -> dict[str, Any]:
    """Agent 创建/更新后规范化 content 并写入 prompt。"""
    style = _project_style(store, asset.project_id)
    if asset.type == TextAssetType.FRAME:
        from core.assets.image_prompt import compose_frame_image_prompt

        content = normalize_image_text_content(asset.type, raw_content)
        locked = bool(content.get("prompt_locked")) and not force_recompose
        if not locked:
            ip, neg = compose_frame_image_prompt(
                content, store=store, project_style=style
            )
            content["image_prompt"] = ip
            if not str(content.get("negative_prompt", "")).strip() or force_recompose:
                content["negative_prompt"] = neg
            from core.assets.image_prompt import PROMPT_VERSION

            content["prompt_version"] = PROMPT_VERSION
        return content
    return finalize_image_text_content(
        asset.type,
        raw_content,
        project_style=style,
        preserve_prompt_lock=True,
        force_recompose=force_recompose,
    )
