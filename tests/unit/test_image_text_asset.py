"""图文资产 content 规范化与 prop CRUD 测试。"""

from core.llm.agent.script_assets import create_text_asset_for_action
from core.models.entities import AssetScope, Project, Script, TextAssetType
from core.models.image_text_asset import (
    normalize_image_text_content,
)
from core.store.memory import MemoryStore
from tests.support.image_text_fixtures import prop_content


def test_normalize_image_text_content_ignores_legacy_appearance_key():
    content = normalize_image_text_content(
        TextAssetType.CHARACTER,
        {"appearance": "橙色毛发的老虎"},
    )
    assert content.get("description", "") == ""


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


def test_normalize_preserves_variant_refs_on_frame_and_character():
    """图文 content 规范化保留关联子形象 variant_refs。"""
    refs = {"ta_char_1": "var_expr_1"}
    frame = normalize_image_text_content(
        TextAssetType.FRAME,
        {"summary": "画面", "element_refs": {"character": ["ta_char_1"]}, "variant_refs": refs},
    )
    assert frame["variant_refs"] == refs
    char = normalize_image_text_content(
        TextAssetType.CHARACTER,
        {"description": "主角", "variant_refs": refs},
    )
    assert char["variant_refs"] == refs


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
    ).asset
    assert prop.type == TextAssetType.PROP
    assert prop.scope == AssetScope.PROJECT_SHARED
    assert prop.content["description"].startswith("古铜色长剑")
    assert prop.content.get("image_prompt")
    assert prop.reuse_policy == "shared"

