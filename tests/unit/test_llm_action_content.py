"""llm_action content 规范化单元测试。"""

from core.agents.llm_action import _coerce_asset_content
from core.models.entities import TextAsset, TextAssetType, AssetScope


def test_coerce_asset_content_from_string():
    raw = "1. **开场**：黄昏时分，老虎在森林中…"
    content = _coerce_asset_content("create_plot", raw, "")
    assert content == {"text": raw}
    asset = TextAsset(
        project_id="p1",
        script_id="s1",
        type=TextAssetType.PLOT,
        name="剧情",
        content=content,
    )
    assert asset.content["text"] == raw


def test_coerce_asset_content_from_dict():
    raw = {"text": "剧情正文"}
    assert _coerce_asset_content("create_plot", raw, "") == raw


def test_coerce_asset_content_fallback_observation():
    content = _coerce_asset_content("create_scene", None, "森林场景描述")
    assert content == {"description": "森林场景描述"}


def test_coerce_asset_content_character_key():
    content = _coerce_asset_content("create_character", "橙色毛发", "")
    assert content == {"appearance": "橙色毛发"}


def test_text_asset_model_coerces_string_content():
    asset = TextAsset(
        project_id="p1",
        script_id="s1",
        type=TextAssetType.PLOT,
        name="剧情",
        content="【开场】清晨，老虎醒来。",
    )
    assert asset.content == {"text": "【开场】清晨，老虎醒来。"}
