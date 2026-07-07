"""剧本 Agent 文字资产 CRUD 与剧本-资产关联。"""

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
IMAGE_TEXT_ACTIONS = CHARACTER_ACTIONS | SCENE_ACTIONS | PROP_ACTIONS
SCRIPT_MUTATION_ACTIONS = frozenset(
    {
        "parse_brief",
        "update_script",
        *PLOT_ACTIONS,
        *IMAGE_TEXT_ACTIONS,
    }
)

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
}


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


def create_text_asset_for_action(
    store: MemoryStore,
    *,
    action: str,
    project_id: str,
    script_id: str,
    asset_name: str,
    content: Any,
    observation: str,
) -> TextAsset:
    from core.llm.agent.asset_content import (
        normalize_asset_content,
        validate_create_content,
    )
    from core.assets.service import finalize_text_asset_content_for_store

    asset_type = _ACTION_TO_TYPE[action]
    scope = (
        AssetScope.SCRIPT_PRIVATE
        if asset_type == TextAssetType.PLOT
        else AssetScope.PROJECT_SHARED
    )
    reuse = "shared" if scope == AssetScope.PROJECT_SHARED else "private"
    normalized = normalize_asset_content(
        content, action=action, observation=observation, strict=True
    )
    validate_create_content(action, normalized)
    asset = TextAsset(
        project_id=project_id,
        script_id=script_id if asset_type == TextAssetType.PLOT else None,
        scope=scope,
        type=asset_type,
        name=asset_name,
        content=normalized,
        source_script_id=script_id,
        reuse_policy=reuse,
    )
    if is_image_text_asset(asset_type):
        asset.content = finalize_text_asset_content_for_store(
            store, asset, asset.content, force_recompose=True
        )
    store.add_text_asset(asset)
    link_script_asset(store, script_id, asset.id)
    return asset


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
    if is_image_text_asset(asset.type):
        merged = finalize_text_asset_content_for_store(
            store, asset, merged, force_recompose=not bool(asset.content.get("prompt_locked"))
        )
    asset.content = merged
    store.update_text_asset(asset)
    link_script_asset(store, script_id, asset.id)
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
    unlink_script_asset(store, script_id, asset_id)
    for ref_id, ref in list(store.references.items()):
        if ref.source_id == asset_id or ref.target_id == asset_id:
            store.remove_reference(ref_id)
    store.delete_text_asset(asset_id)
