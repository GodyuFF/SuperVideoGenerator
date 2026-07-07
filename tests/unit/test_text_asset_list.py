"""list_text_assets JSON 载荷测试。"""

import json

import pytest

from core.llm.agent.script_assets import link_script_asset
from core.llm.tools.shared.executor import AgentToolExecutor
from core.llm.tools.script.list import (
    build_text_assets_list_payload,
    format_text_assets_list,
    format_text_assets_list_payload,
)
from core.llm.agent.react_core import AgentRunContext
from core.models.entities import AssetScope, Project, Script, TextAsset, TextAssetType
from core.store.memory import MemoryStore
from core.llm.tools import get_tool_registry
from tests.support.image_text_fixtures import character_content, scene_content


def _setup_script_with_assets() -> tuple[MemoryStore, str, str]:
    store = MemoryStore()
    project = Project(title="p1")
    store.add_project(project)
    script = Script(
        project_id=project.id,
        title="测试剧本",
        duration_sec=30,
        content_md="# 标题\n\n剧本正文。",
    )
    store.add_script(script)
    char_content = character_content(summary="机器人主角")
    char = TextAsset(
        project_id=project.id,
        type=TextAssetType.CHARACTER,
        name="小铁",
        content=char_content,
        scope=AssetScope.PROJECT_SHARED,
        source_script_id=script.id,
    )
    store.add_text_asset(char)
    link_script_asset(store, script.id, char.id)
    store.add_text_asset(
        TextAsset(
            project_id=project.id,
            script_id=script.id,
            type=TextAssetType.PLOT,
            name="第一幕",
            content={"text": "剧情段落正文，用于时长评估。"},
            scope=AssetScope.SCRIPT_PRIVATE,
        )
    )
    scene = TextAsset(
        project_id=project.id,
        type=TextAssetType.SCENE,
        name="未关联场景",
        content=scene_content(summary="后台场景"),
        scope=AssetScope.PROJECT_SHARED,
        source_script_id=script.id,
    )
    store.add_text_asset(scene)
    return store, project.id, script.id


def test_build_text_assets_list_includes_full_content():
    store, _project_id, script_id = _setup_script_with_assets()

    payload = build_text_assets_list_payload(store, script_id)
    assert payload["count"] == 3
    assert payload["script"]["content_md"].startswith("# 标题")
    assert payload["script"]["duration_sec"] == 30
    assert payload["counts_by_type"]["character"] == 1
    assert payload["counts_by_type"]["plot"] == 1
    assert payload["counts_by_type"]["scene"] == 1

    char = next(a for a in payload["assets"] if a["type"] == "character")
    assert char["content"]["description"]
    assert char["content"].get("image_prompt")
    assert char["traits"]["role"] == "主角"
    assert char["linked"] is True
    assert "summary" in char["content"]

    plot = next(a for a in payload["assets"] if a["type"] == "plot")
    assert plot["content"]["text"] == "剧情段落正文，用于时长评估。"
    assert plot["linked"] is True

    unlinked_scene = next(a for a in payload["assets"] if a["name"] == "未关联场景")
    assert unlinked_scene["linked"] is False


def test_build_text_assets_list_filters_by_types():
    store, _project_id, script_id = _setup_script_with_assets()
    payload = build_text_assets_list_payload(
        store, script_id, types=["character", "plot"]
    )
    assert payload["count"] == 2
    assert set(payload["counts_by_type"].keys()) == {
        "character",
        "plot",
        "prop",
        "scene",
    }
    assert payload["counts_by_type"]["scene"] == 0


def test_build_text_assets_list_include_content_false():
    store, _project_id, script_id = _setup_script_with_assets()
    payload = build_text_assets_list_payload(
        store, script_id, include_content=False
    )
    char = next(a for a in payload["assets"] if a["type"] == "character")
    assert "image_prompt" not in char["content"]
    assert "traits" not in char
    assert char["linked_media"] == []
    assert char["content"]["summary"]


def test_build_text_assets_list_script_not_found():
    store = MemoryStore()
    with pytest.raises(ValueError, match="不存在"):
        build_text_assets_list_payload(store, "script_missing")


def test_format_text_assets_list_returns_json_string():
    store = MemoryStore()
    project = Project(title="p1")
    store.add_project(project)
    script = Script(project_id=project.id, title="s1")
    store.add_script(script)

    raw = format_text_assets_list(store, script.id)
    data = json.loads(raw)
    assert data["count"] == 0
    assert data["assets"] == []
    assert data["message"] == "当前无文字资产。"
    assert data["counts_by_type"]["character"] == 0


def test_format_text_assets_list_payload_matches_structured():
    store, _project_id, script_id = _setup_script_with_assets()
    payload = build_text_assets_list_payload(store, script_id)
    raw = format_text_assets_list_payload(payload)
    assert json.loads(raw) == payload


def test_executor_list_text_assets_json():
    store, project_id, script_id = _setup_script_with_assets()
    executor = AgentToolExecutor(store)
    ctx = AgentRunContext(
        task_brief="",
        work_context={"project_id": project_id},
        script_id=script_id,
        step_id="step1",
        agent_name="script_agent",
    )
    result = executor.execute_by_action("script_agent", "list_text_assets", ctx)
    data = json.loads(result)
    assert data["count"] == 3
    assert data["assets"][0]["content"]
    assert "counts_by_type" in data


@pytest.mark.asyncio
async def test_registry_list_text_assets_observation_is_json():
    store, project_id, script_id = _setup_script_with_assets()
    ctx = AgentRunContext(
        task_brief="",
        work_context={"project_id": project_id},
        script_id=script_id,
        step_id="step1",
        agent_name="script_agent",
    )
    registry = get_tool_registry()
    result = await registry.call_tool(
        "list_text_assets",
        {
            "observation": "列出文字资产",
            "plan_status": "列出文字资产",
            "remaining_plan": ["finish"],
        },
        ctx,
        store,
    )
    assert result.ok
    assert json.loads(result.observation) == result.structured
    assert result.structured["count"] == 3


@pytest.mark.asyncio
async def test_registry_list_text_assets_script_not_found():
    store = MemoryStore()
    ctx = AgentRunContext(
        task_brief="",
        work_context={},
        script_id="script_missing",
        step_id="step1",
        agent_name="script_agent",
    )
    result = await get_tool_registry().call_tool(
        "list_text_assets",
        {"observation": "列出"},
        ctx,
        store,
    )
    assert not result.ok
    assert result.structured.get("valid") is False
