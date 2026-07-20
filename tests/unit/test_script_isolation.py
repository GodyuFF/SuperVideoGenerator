"""双剧本资源隔离单元测试。"""

from core.board.builder import BoardBuilder
from core.llm.agent.script_assets import link_script_asset
from core.models.entities import (
    AssetScope,
    MediaAsset,
    MediaAssetType,
    Project,
    Script,
    TextAsset,
    TextAssetType,
)
from core.store.memory import MemoryStore
from tests.support.image_text_fixtures import character_content, scene_content


def _two_script_store() -> tuple[MemoryStore, str, str, str]:
    """创建含两个剧本的项目：剧本1有角色/场景/剧情，剧本2为空。"""
    store = MemoryStore()
    project = Project(title="双剧本项目")
    store.add_project(project)
    script1 = Script(project_id=project.id, title="剧本一", content_md="# 一")
    script2 = Script(project_id=project.id, title="剧本二", content_md="# 二")
    store.add_script(script1)
    store.add_script(script2)

    char = TextAsset(
        project_id=project.id,
        type=TextAssetType.CHARACTER,
        name="小铁",
        content=character_content(summary="机器人"),
        scope=AssetScope.PROJECT_SHARED,
        source_script_id=script1.id,
    )
    store.add_text_asset(char)
    link_script_asset(store, script1.id, char.id)

    scene = TextAsset(
        project_id=project.id,
        type=TextAssetType.SCENE,
        name="实验室",
        content=scene_content(summary="未来实验室"),
        scope=AssetScope.PROJECT_SHARED,
        source_script_id=script1.id,
    )
    store.add_text_asset(scene)

    plot = TextAsset(
        project_id=project.id,
        script_id=script1.id,
        type=TextAssetType.PLOT,
        name="第一幕",
        content={"text": "剧本一剧情"},
        scope=AssetScope.SCRIPT_PRIVATE,
    )
    store.add_text_asset(plot)

    frame = TextAsset(
        project_id=project.id,
        script_id=script1.id,
        type=TextAssetType.FRAME,
        name="画面·镜1",
        content={"summary": "剧本一画面"},
        scope=AssetScope.SCRIPT_PRIVATE,
        source_script_id=script1.id,
    )
    store.add_text_asset(frame)

    store.add_media_asset(
        MediaAsset(
            project_id=project.id,
            script_id=script1.id,
            type=MediaAssetType.IMAGE,
            name="小铁图",
            url="https://cdn.example.com/hero.png",
            source_asset_id=char.id,
        )
    )

    return store, project.id, script1.id, script2.id


def test_script2_character_board_excludes_script1_unlinked_assets():
    """剧本1未链接到剧本2的共享角色/场景不应出现在剧本2看板。"""
    store, project_id, script1_id, script2_id = _two_script_store()
    builder = BoardBuilder(store)

    char_view = builder.build("character", project_id, script2_id)
    scene_view = builder.build("scene", project_id, script2_id)
    prop_view = builder.build("prop", project_id, script2_id)

    assert char_view.items == []
    assert scene_view.items == []
    assert prop_view.items == []

    script1_char = builder.build("character", project_id, script1_id)
    assert len(script1_char.items) == 1
    assert script1_char.items[0]["name"] == "小铁"


def test_script2_sees_rag_linked_shared_character():
    """剧本2通过 AssetReference 引用剧本1角色时，角色 Tab 应可见。"""
    store, project_id, script1_id, script2_id = _two_script_store()
    char = next(
        a
        for a in store.text_assets.values()
        if a.type == TextAssetType.CHARACTER
    )
    link_script_asset(store, script2_id, char.id)

    char_view = BoardBuilder(store).build("character", project_id, script2_id)
    assert len(char_view.items) == 1
    assert char_view.items[0]["id"] == char.id


def test_script2_private_assets_isolated():
    """剧本1的 plot/frame/media 不应出现在剧本2看板。"""
    store, project_id, script1_id, script2_id = _two_script_store()
    builder = BoardBuilder(store)

    script_view = builder.build("script", project_id, script2_id)
    frame_view = builder.build("frame", project_id, script2_id)
    media_view = builder.build("media", project_id, script2_id)

    assert script_view.items == []
    assert frame_view.items == []
    assert media_view.items == []


def test_list_assets_matches_visible_scope():
    """Agent 与看板使用同一可见范围：未链接共享资产不出现在剧本2。"""
    store, _project_id, script1_id, script2_id = _two_script_store()

    script2_assets = store.list_assets_for_script(script2_id)
    script2_visible = store.list_visible_text_assets_for_script(script2_id)
    assert {a.id for a in script2_assets} == {a.id for a in script2_visible}
    assert script2_assets == []

    script1_assets = store.list_assets_for_script(script1_id)
    script1_names = {a.name for a in script1_assets}
    assert "小铁" in script1_names
    assert "实验室" in script1_names
    assert "第一幕" in script1_names


def test_visible_assets_media_scoped_to_script():
    """剧本2引用共享角色时，关联图片仅展示剧本2自身媒体。"""
    store, project_id, script1_id, script2_id = _two_script_store()
    char = next(
        a
        for a in store.text_assets.values()
        if a.type == TextAssetType.CHARACTER
    )
    link_script_asset(store, script2_id, char.id)

    char_view = BoardBuilder(store).build("character", project_id, script2_id)
    assert len(char_view.items) == 1
    assert char_view.items[0]["images"] == []

    char_view_s1 = BoardBuilder(store).build("character", project_id, script1_id)
    assert len(char_view_s1.items[0]["images"]) == 1
