"""图文资产 content 规范化与 prop CRUD 测试。"""

from core.llm.agent.script_assets import create_text_asset_for_action
from core.models.entities import AssetScope, Project, Script, TextAssetType
from core.models.image_text_asset import (
    normalize_image_text_content,
    upgrade_text_asset_content,
)
from core.store.memory import MemoryStore
from tests.support.image_text_fixtures import prop_content


def test_normalize_image_text_content_migrates_appearance():
    content = normalize_image_text_content(
        TextAssetType.CHARACTER,
        {"appearance": "橙色毛发的老虎"},
    )
    assert content["description"] == "橙色毛发的老虎"
    assert content["summary"] == ""


def test_normalize_image_text_content_preserves_traits():
    content = normalize_image_text_content(
        TextAssetType.PROP,
        {
            "description": "银色复古相机",
            "category": "日用品",
            "material": "金属",
            "tags": "复古,摄影",
        },
    )
    assert content["description"] == "银色复古相机"
    assert content["category"] == "日用品"
    assert content["tags"] == ["复古", "摄影"]


def test_create_prop_shared_and_linked():
    store = MemoryStore()
    project = Project(title="p1")
    store.add_project(project)
    script = Script(project_id=project.id, title="s1")
    store.add_script(script)
    prop = create_text_asset_for_action(
        store,
        action="create_prop",
        project_id=project.id,
        script_id=script.id,
        asset_name="宝剑",
        content=prop_content(
            summary="宝剑",
            description="古铜色长剑，剑身有岁月痕迹，适合作为武侠叙事核心道具，金属质感清晰。",
            category="武器",
        ),
        observation="",
    )
    assert prop.type == TextAssetType.PROP
    assert prop.scope == AssetScope.PROJECT_SHARED
    assert prop.content["description"].startswith("古铜色长剑")
    assert prop.content.get("image_prompt")
    assert prop.reuse_policy == "shared"


    store = MemoryStore()
    project = Project(title="p1")
    store.add_project(project)
    from core.models.entities import TextAsset

    asset = TextAsset(
        project_id=project.id,
        type=TextAssetType.SCENE,
        name="旧场景",
        content={"description": "森林"},
        scope=AssetScope.PROJECT_SHARED,
    )
    upgraded = upgrade_text_asset_content(asset)
    assert upgraded.content["description"] == "森林"
    assert "visual_style" in upgraded.content
