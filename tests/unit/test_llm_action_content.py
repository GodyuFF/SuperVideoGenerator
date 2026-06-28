"""llm_action content 规范化单元测试。"""

from core.agents.asset_content import extract_llm_content_field, normalize_asset_content
from core.agents.llm_action import _coerce_asset_content, apply_action_result
from core.agents.react_core import AgentRunContext
from core.models.entities import Project, Script, TextAsset, TextAssetType, AssetScope
from core.store.memory import MemoryStore


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
    plot_text = "1. **开场**：清晨，老虎醒来。远处传来鸟鸣。"
    asset = TextAsset(
        project_id="p1",
        script_id="s1",
        type=TextAssetType.PLOT,
        name="剧情",
        content=plot_text,
    )
    assert asset.content == {"text": plot_text}


def test_normalize_asset_content_from_list():
    content = normalize_asset_content(
        ["1. **开场**：清晨", "2. **发展**：追逐"],
        action="create_plot",
    )
    assert "开场" in content["text"]
    assert "发展" in content["text"]


def test_extract_llm_content_field_text_key():
    data = {
        "observation": "已创建剧情",
        "asset_name": "开场",
        "text": "1. **开场**：清晨，老虎在森林中醒来。远处传来鸟鸣。",
    }
    assert extract_llm_content_field(data, "create_plot") == data["text"]


def test_apply_action_result_create_plot_string_content():
    store = MemoryStore()
    project = Project(title="p1")
    store.add_project(project)
    script = Script(project_id=project.id, title="s1")
    store.add_script(script)
    ctx = AgentRunContext(
        task_brief="设计短片",
        work_context={"project_id": project.id, "script_id": script.id},
        script_id=script.id,
        step_id="step1",
        agent_name="script_agent",
    )
    plot_text = "1. **开场**：清晨，老虎在森林中醒来。远处传来鸟鸣。"
    apply_action_result(
        store,
        "script_agent",
        "create_plot",
        ctx,
        {
            "observation": "已创建剧情资产",
            "asset_name": "开场剧情",
            "content": plot_text,
        },
    )
    assets = store.list_assets_for_script(script.id)
    assert len(assets) == 1
    assert assets[0].content["text"] == plot_text
