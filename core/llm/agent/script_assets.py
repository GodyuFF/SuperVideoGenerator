"""剧本 Agent 文字资产 CRUD 与剧本-资产关联。"""

from dataclasses import dataclass
from typing import Any

from core.guards.reference import ReferenceGuard, ReferenceGuardError
from core.models.entities import (
    AssetReference,
    AssetScope,
    AssetStatus,
    RelationType,
    TextAsset,
    TextAssetType,
)
from core.models.image_text_asset import is_image_text_asset
from core.store.memory import MemoryStore

PLOT_ACTIONS = frozenset({"create_plot", "update_plot", "delete_plot"})
CHARACTER_ACTIONS = frozenset({"create_character", "update_character", "delete_character"})
SCENE_ACTIONS = frozenset({"create_scene", "update_scene", "delete_scene"})
PROP_ACTIONS = frozenset({"create_prop", "update_prop", "delete_prop"})
FRAME_ACTIONS = frozenset({"create_frame", "delete_frame"})
VIDEO_CLIP_ACTIONS = frozenset({"create_video_clip", "delete_video_clip"})
# script_agent ReAct 仅管理剧情与共享图文资产；frame/video_clip 由 storyboard_agent 创建
IMAGE_TEXT_ACTIONS = CHARACTER_ACTIONS | SCENE_ACTIONS | PROP_ACTIONS
SCRIPT_MUTATION_ACTIONS = frozenset(
    {
        "parse_brief",
        "update_script",
        *PLOT_ACTIONS,
        *IMAGE_TEXT_ACTIONS,
    }
)
SHARED_CREATE_ACTIONS = frozenset({"create_character", "create_scene", "create_prop"})

_ACTION_TO_TYPE: dict[str, TextAssetType] = {
    "create_plot": TextAssetType.PLOT,
    "update_plot": TextAssetType.PLOT,
    "delete_plot": TextAssetType.PLOT,
    "create_character": TextAssetType.CHARACTER,
    "update_character": TextAssetType.CHARACTER,
    "delete_character": TextAssetType.CHARACTER,
    "create_scene": TextAssetType.SCENE,
    "update_scene": TextAssetType.SCENE,
    "delete_scene": TextAssetType.SCENE,
    "create_prop": TextAssetType.PROP,
    "update_prop": TextAssetType.PROP,
    "delete_prop": TextAssetType.PROP,
    "create_frame": TextAssetType.FRAME,
    "delete_frame": TextAssetType.FRAME,
    "create_video_clip": TextAssetType.VIDEO_CLIP,
    "delete_video_clip": TextAssetType.VIDEO_CLIP,
}


@dataclass
class CreateTextAssetOutcome:
    """文字资产创建或 RAG 复用结果。"""

    asset: TextAsset
    rag_decision: str | None = None
    rag_reason: str = ""


def action_to_asset_type(action: str) -> TextAssetType | None:
    return _ACTION_TO_TYPE.get(action)


def _assert_asset_mutable(asset: TextAsset) -> None:
    if asset.status == AssetStatus.LOCKED:
        raise ValueError(f"资产 {asset.id} 已锁定，不可修改或删除")


def link_script_asset(
    store: MemoryStore,
    script_id: str,
    asset_id: str,
    *,
    relation: RelationType = RelationType.USES,
) -> AssetReference:
    """建立剧本与文字资产的引用边（看板与删除守卫）。"""
    for ref in store.references.values():
        if ref.source_id == script_id and ref.target_id == asset_id:
            if ref.relation != relation:
                ref.relation = relation
            return ref
    ref = AssetReference(
        source_id=script_id,
        target_id=asset_id,
        relation=relation,
        script_id=script_id,
    )
    return store.add_reference(ref)


def unlink_script_asset(store: MemoryStore, script_id: str, asset_id: str) -> bool:
    removed = False
    for ref_id, ref in list(store.references.items()):
        if ref.source_id == script_id and ref.target_id == asset_id:
            store.remove_reference(ref_id)
            removed = True
    return removed


def list_script_asset_refs(store: MemoryStore, script_id: str) -> list[AssetReference]:
    return [r for r in store.references.values() if r.source_id == script_id]


def merge_asset_content(
    action: str,
    existing: Any,
    incoming: Any,
    observation: str,
) -> dict[str, Any]:
    from core.llm.agent.asset_content import normalize_asset_content

    if isinstance(existing, str):
        existing = normalize_asset_content(existing, action=action)
    elif not isinstance(existing, dict):
        existing = {}
    if incoming is None and not observation:
        return existing
    new_content = normalize_asset_content(incoming, action=action, observation=observation)
    if not new_content:
        return existing
    merged = dict(existing)
    merged.update(new_content)
    return merged


def _create_new_text_asset(
    store: MemoryStore,
    *,
    action: str,
    project_id: str,
    script_id: str,
    asset_name: str,
    content: Any,
    observation: str,
    skip_validate: bool = False,
    pre_normalized: dict[str, Any] | None = None,
    embedder: Any | None = None,
) -> TextAsset:
    """新建文字资产并关联剧本（不含 RAG 分支）。"""
    from core.llm.agent.asset_content import (
        normalize_asset_content,
        validate_create_content,
    )
    from core.assets.service import (
        apply_character_tts_voice,
        finalize_text_asset_content_for_store,
    )

    asset_type = _ACTION_TO_TYPE[action]
    scope = (
        AssetScope.SCRIPT_PRIVATE
        if asset_type in (TextAssetType.PLOT, TextAssetType.FRAME, TextAssetType.VIDEO_CLIP)
        else AssetScope.PROJECT_SHARED
    )
    reuse = "shared" if scope == AssetScope.PROJECT_SHARED else "private"
    if pre_normalized is not None:
        normalized = pre_normalized
    else:
        normalized = normalize_asset_content(
            content, action=action, observation=observation, strict=True
        )
    if asset_type == TextAssetType.CHARACTER:
        normalized = apply_character_tts_voice(normalized)
    if not skip_validate:
        validate_create_content(action, normalized)
    asset = TextAsset(
        project_id=project_id,
        script_id=script_id
        if asset_type in (TextAssetType.PLOT, TextAssetType.FRAME, TextAssetType.VIDEO_CLIP)
        else None,
        scope=scope,
        type=asset_type,
        name=asset_name,
        content=normalized,
        source_script_id=script_id,
        reuse_policy=reuse,
    )
    if is_image_text_asset(asset_type) or asset_type == TextAssetType.VIDEO_CLIP:
        asset.content = finalize_text_asset_content_for_store(
            store, asset, asset.content, force_recompose=True
        )
    store.add_text_asset(asset)
    link_script_asset(store, script_id, asset.id)
    if scope == AssetScope.PROJECT_SHARED:
        project = store.get_project(project_id)
        if project is not None and project.config.rag.enabled:
            from core.rag.indexer import on_shared_asset_updated

            on_shared_asset_updated(store, asset, embedder=embedder)
    return asset


def create_text_asset_for_action(
    store: MemoryStore,
    *,
    action: str,
    project_id: str,
    script_id: str,
    asset_name: str,
    content: Any,
    observation: str,
) -> CreateTextAssetOutcome:
    """创建文字资产；共享图文类型走 RAG 按需复用。"""
    if action in SHARED_CREATE_ACTIONS:
        project = store.get_project(project_id)
        if project is not None and project.config.rag.enabled:
            from core.rag.resolver import resolve_shared_text_asset_sync

            return resolve_shared_text_asset_sync(
                store,
                action=action,
                project_id=project_id,
                script_id=script_id,
                asset_name=asset_name,
                content=content,
                observation=observation,
            )
    asset = _create_new_text_asset(
        store,
        action=action,
        project_id=project_id,
        script_id=script_id,
        asset_name=asset_name,
        content=content,
        observation=observation,
    )
    return CreateTextAssetOutcome(asset=asset)


def update_text_asset_for_action(
    store: MemoryStore,
    *,
    action: str,
    script_id: str,
    asset_id: str,
    asset_name: str | None,
    content: Any,
    observation: str,
) -> TextAsset:
    from core.assets.service import finalize_text_asset_content_for_store

    asset = store.get_text_asset(asset_id)
    if not asset:
        raise ValueError(f"资产 {asset_id} 不存在")
    expected = _ACTION_TO_TYPE.get(action)
    if expected and asset.type != expected:
        raise ValueError(f"资产 {asset_id} 类型为 {asset.type.value}，与行动 {action} 不匹配")
    _assert_asset_mutable(asset)
    if asset_name:
        asset.name = asset_name
    merged = merge_asset_content(action, asset.content, content, observation)
    if asset.type == TextAssetType.CHARACTER:
        from core.assets.service import apply_character_tts_voice

        merged = apply_character_tts_voice(merged)
    if is_image_text_asset(asset.type):
        merged = finalize_text_asset_content_for_store(
            store, asset, merged, force_recompose=not bool(asset.content.get("prompt_locked"))
        )
    asset.content = merged
    store.update_text_asset(asset)
    link_script_asset(store, script_id, asset.id)
    project = store.get_project(asset.project_id)
    if project is not None and project.config.rag.enabled:
        from core.rag.indexer import on_shared_asset_updated

        on_shared_asset_updated(store, asset)
    return asset


def delete_text_asset_for_action(
    store: MemoryStore,
    *,
    action: str,
    script_id: str,
    asset_id: str,
) -> None:
    asset = store.get_text_asset(asset_id)
    if not asset:
        raise ValueError(f"资产 {asset_id} 不存在")
    expected = _ACTION_TO_TYPE.get(action)
    if expected and asset.type != expected:
        raise ValueError(f"资产 {asset_id} 类型为 {asset.type.value}，与行动 {action} 不匹配")
    _assert_asset_mutable(asset)
    guard = ReferenceGuard(store)
    try:
        guard.assert_can_delete(asset_id)
    except ReferenceGuardError as e:
        external = [r for r in e.references if r.source_id != script_id]
        if external:
            raise
    project_id = asset.project_id
    unlink_script_asset(store, script_id, asset_id)
    for ref_id, ref in list(store.references.items()):
        if ref.source_id == asset_id or ref.target_id == asset_id:
            store.remove_reference(ref_id)
    store.delete_text_asset(asset_id)
    if asset.scope == AssetScope.PROJECT_SHARED and asset.type.value in (
        "character",
        "scene",
        "prop",
    ):
        from core.rag.indexer import on_shared_asset_deleted

        on_shared_asset_deleted(project_id, asset_id)
