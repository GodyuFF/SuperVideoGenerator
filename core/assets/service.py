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
        from core.models.image_text_asset import merge_incoming_variants

        merged = dict(normalize_image_text_content(asset.type, asset.content))
        patch_body = dict(content)
        incoming_variants = patch_body.pop("image_variants", None)
        merged.update(patch_body)
        if isinstance(incoming_variants, list):
            merged = merge_incoming_variants(merged, incoming_variants)
        if prompt_locked is not None:
            merged["prompt_locked"] = prompt_locked
        if force_recompose_prompt:
            merged["prompt_locked"] = False
            merged["image_prompt"] = ""
        if asset.type == TextAssetType.CHARACTER:
            merged = apply_character_tts_voice(merged)
        from core.assets.element_refs import normalize_element_refs, validate_element_refs_for_owner

        refs = normalize_element_refs(merged.get("element_refs"))
        if refs:
            validate_element_refs_for_owner(store, asset.id, refs)
            merged["element_refs"] = refs
        merged = apply_composed_prompts(
            asset.type,
            merged,
            project_style=style,
            preserve_prompt_lock=not force_recompose_prompt,
            force_recompose=force_recompose_prompt,
        )
        if isinstance(incoming_variants, list) and incoming_variants:
            if bool(merged.get("prompt_locked")) and not force_recompose_prompt:
                from core.assets.image_prompt import recompose_variant_image_prompts

                merged = recompose_variant_image_prompts(
                    asset.type,
                    merged,
                    project_style=style,
                )
        asset.content = merged
        asset.user_edited = True

    store.update_text_asset(asset)
    return asset


def apply_character_tts_voice(content: dict[str, Any]) -> dict[str, Any]:
    """为角色 content 解析并写入符合当前 TTS 配置的 tts_voice。"""
    from core.llm.tools.tts.settings import get_tts_manager
    from core.tts.voices import resolve_character_tts_voice

    out = dict(content)
    settings = get_tts_manager().get_settings()
    out["tts_voice"] = resolve_character_tts_voice(
        out.get("tts_voice"),
        gender=str(out.get("gender", "")),
        provider=settings.provider,
        locale=settings.default_language,
        default_voice=settings.default_voice,
    )
    return out


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
    if asset.type == TextAssetType.VIDEO_CLIP:
        from core.assets.video_prompt import compose_video_clip_prompt
        from core.models.video_text_asset import normalize_video_clip_content

        content = normalize_video_clip_content(raw_content)
        locked = bool(content.get("prompt_locked")) and not force_recompose
        if not locked:
            content["video_prompt"] = compose_video_clip_prompt(
                content, store=store, project_style=style
            )
            content["prompt_version"] = int(content.get("prompt_version") or 0) + 1
        return content
    if asset.type == TextAssetType.CHARACTER:
        content = normalize_image_text_content(asset.type, raw_content)
        content = apply_character_tts_voice(content)
        return finalize_image_text_content(
            asset.type,
            content,
            project_style=style,
            preserve_prompt_lock=True,
            force_recompose=force_recompose,
        )
    return finalize_image_text_content(
        asset.type,
        raw_content,
        project_style=style,
        preserve_prompt_lock=True,
        force_recompose=force_recompose,
    )
