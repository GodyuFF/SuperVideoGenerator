"""element_refs 类型对齐、环检测与拓扑排序测试。"""

from __future__ import annotations

import pytest

from core.assets.element_refs import (
    topo_sort_assets_by_element_refs,
    validate_element_refs_for_owner,
    would_create_element_ref_cycle,
)
from core.models.entities import (
    AssetScope,
    Project,
    Script,
    ScriptStatus,
    TextAsset,
    TextAssetType,
)
from core.store.memory import MemoryStore
from tests.support.image_text_fixtures import character_content, scene_content


@pytest.fixture
def script_store() -> tuple[MemoryStore, str, str]:
    """项目 + 剧本存储。"""
    store = MemoryStore()
    project = Project(title="ref-test")
    store.add_project(project)
    script = Script(project_id=project.id, title="S1", status=ScriptStatus.DRAFT)
    store.add_script(script)
    return store, script.id, project.id


def _add_char(store: MemoryStore, project_id: str, script_id: str, name: str) -> str:
    asset = TextAsset(
        project_id=project_id,
        type=TextAssetType.CHARACTER,
        scope=AssetScope.PROJECT_SHARED,
        name=name,
        content={**character_content(), "element_refs": {}},
        source_script_id=script_id,
    )
    store.add_text_asset(asset)
    return asset.id


def test_reject_wrong_bucket_type(script_store: tuple[MemoryStore, str, str]) -> None:
    """character 桶不能引用 scene 资产。"""
    store, script_id, project_id = script_store
    scene = TextAsset(
        project_id=project_id,
        type=TextAssetType.SCENE,
        scope=AssetScope.PROJECT_SHARED,
        name="空镜",
        content=scene_content(),
        source_script_id=script_id,
    )
    store.add_text_asset(scene)
    with pytest.raises(ValueError, match="仅允许"):
        validate_element_refs_for_owner(
            store,
            None,
            {"character": [scene.id]},
        )


def test_detect_direct_cycle(script_store: tuple[MemoryStore, str, str]) -> None:
    """A→B 且 B→A 应判为环。"""
    store, script_id, project_id = script_store
    a = _add_char(store, project_id, script_id, "A")
    b = _add_char(store, project_id, script_id, "B")
    b_asset = store.get_text_asset(b)
    assert b_asset
    b_asset.content = {**b_asset.content, "element_refs": {"character": [a]}}
    store.update_text_asset(b_asset)
    assert would_create_element_ref_cycle(store, a, {"character": [b]})


def test_topo_sort_dependency_order(script_store: tuple[MemoryStore, str, str]) -> None:
    """B 引用 A 时 A 应排在 B 前。"""
    store, script_id, project_id = script_store
    a = _add_char(store, project_id, script_id, "A")
    b = _add_char(store, project_id, script_id, "B")
    b_asset = store.get_text_asset(b)
    assert b_asset
    b_asset.content = {**b_asset.content, "element_refs": {"character": [a]}}
    store.update_text_asset(b_asset)
    ordered = topo_sort_assets_by_element_refs(store, [b, a])
    assert ordered.index(a) < ordered.index(b)
