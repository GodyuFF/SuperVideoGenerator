"""资产谱系查询单元测试。"""

from core.assets.lineage import (
    AssetKind,
    build_lineage,
    build_project_graph,
    resolve_descriptor,
)
from core.llm.agent.script_assets import create_text_asset_for_action, link_script_asset
from core.models.entities import (
    AssetReference,
    AssetScope,
    MediaAsset,
    MediaAssetType,
    Project,
    RelationType,
    Script,
    TextAsset,
    TextAssetType,
    VideoPlan,
    Shot,
)
from core.store.memory import MemoryStore
from tests.support.image_text_fixtures import character_content, scene_content
from tests.support.shot_fixtures import make_shot


def _setup_store() -> tuple[MemoryStore, str, str]:
    store = MemoryStore()
    project = Project(title="测试项目")
    store.add_project(project)
    script = Script(project_id=project.id, title="第一集")
    store.add_script(script)
    return store, project.id, script.id


def test_resolve_descriptor_text_asset():
    store, project_id, script_id = _setup_store()
    char = create_text_asset_for_action(
        store,
        action="create_character",
        project_id=project_id,
        script_id=script_id,
        asset_name="小猫",
        content=character_content(summary="小猫", description="一只橘色小猫。" * 10),
        observation="",
    ).asset
    desc = resolve_descriptor(store, char.id)
    assert desc is not None
    assert desc.kind == AssetKind.TEXT_CHARACTER
    assert desc.name == "小猫"


def test_lineage_character_generates_media():
    store, project_id, script_id = _setup_store()
    char = create_text_asset_for_action(
        store,
        action="create_character",
        project_id=project_id,
        script_id=script_id,
        asset_name="小猫",
        content=character_content(summary="小猫", description="一只橘色小猫。" * 10),
        observation="",
    ).asset
    media = MediaAsset(
        project_id=project_id,
        script_id=script_id,
        type=MediaAssetType.IMAGE,
        name="小猫主图",
        url="/data/test.png",
        source_asset_id=char.id,
    )
    store.add_media_asset(media)
    store.add_reference(
        AssetReference(
            source_id=char.id,
            target_id=media.id,
            relation=RelationType.GENERATES,
            script_id=script_id,
        )
    )

    view = build_lineage(store, project_id, char.id)
    assert view is not None
    relations = {e.relation for e in view.outgoing}
    assert "generates" in relations
    targets = {e.target.id for e in view.outgoing}
    assert media.id in targets


def test_lineage_shot_ref_incoming():
    store, project_id, script_id = _setup_store()
    char = create_text_asset_for_action(
        store,
        action="create_character",
        project_id=project_id,
        script_id=script_id,
        asset_name="小猫",
        content=character_content(summary="小猫", description="一只橘色小猫。" * 10),
        observation="",
    ).asset
    shot = make_shot(order=0, text="小猫吃鱼")
    shot.sub_shots[0].element_refs = {"character": [char.id]}
    plan = VideoPlan(script_id=script_id, shots=[shot])
    store.set_video_plan(plan)

    view = build_lineage(store, project_id, char.id)
    assert view is not None
    incoming_relations = {e.relation for e in view.incoming}
    assert "shot_ref" in incoming_relations


def test_lineage_frame_element_refs():
    store, project_id, script_id = _setup_store()
    scene = create_text_asset_for_action(
        store,
        action="create_scene",
        project_id=project_id,
        script_id=script_id,
        asset_name="厨房",
        content=scene_content(summary="厨房", description="明亮厨房空镜背景。" * 8),
        observation="",
    ).asset
    frame_asset = TextAsset(
        project_id=project_id,
        script_id=script_id,
        scope=AssetScope.SCRIPT_PRIVATE,
        type=TextAssetType.FRAME,
        name="画面1",
        content={
            "summary": "画面",
            "description": "合成画面描述。" * 10,
            "element_refs": {"scene": [scene.id]},
            "visual_style": "写实",
            "color_palette": "暖色",
            "prompt_hint": "合成",
        },
        source_script_id=script_id,
    )
    store.add_text_asset(frame_asset)
    link_script_asset(store, script_id, frame_asset.id)

    view = build_lineage(store, project_id, scene.id)
    assert view is not None
    assert any(e.relation == "element_ref" for e in view.incoming)

    frame_view = build_lineage(store, project_id, frame_asset.id)
    assert frame_view is not None
    assert any(e.relation == "element_ref" for e in frame_view.outgoing)


def test_build_project_graph_has_generates_edge():
    store, project_id, script_id = _setup_store()
    char = create_text_asset_for_action(
        store,
        action="create_character",
        project_id=project_id,
        script_id=script_id,
        asset_name="小猫",
        content=character_content(summary="小猫", description="一只橘色小猫。" * 10),
        observation="",
    ).asset
    media = MediaAsset(
        project_id=project_id,
        script_id=script_id,
        type=MediaAssetType.IMAGE,
        name="小猫图",
        url="/data/test.png",
        source_asset_id=char.id,
    )
    store.add_media_asset(media)

    nodes, edges, stats = build_project_graph(store, project_id, script_id)
    assert stats["node_count"] >= 3
    gen_edges = [e for e in edges if e.relation == "generates"]
    assert any(e.source == char.id and e.target == media.id for e in gen_edges)
