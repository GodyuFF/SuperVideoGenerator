"""MCP 语义 Tool Registry 单元测试。"""

import json

import pytest

from core.llm.agent.react_core import AgentRunContext
from core.models.entities import Project, Script
from core.store.memory import MemoryStore
from core.llm.tools import get_tool_registry


@pytest.fixture
def script_ctx() -> tuple[MemoryStore, AgentRunContext]:
    store = MemoryStore()
    project = Project(title="p1")
    store.add_project(project)
    script = Script(project_id=project.id, title="第一集")
    store.add_script(script)
    ctx = AgentRunContext(
        task_brief="测试",
        work_context={"project_id": project.id, "script_id": script.id},
        script_id=script.id,
        step_id="step1",
        agent_name="script_agent",
    )
    return store, ctx


def test_list_tools_filters_by_agent():
    registry = get_tool_registry()
    script_tools = registry.list_tools("script_agent")
    assert script_tools
    assert all(s.agent == "script_agent" for s in script_tools)
    names = {s.name for s in script_tools}
    assert "create_character" in names
    assert "list_text_assets" in names


def test_all_registered_tools_have_schemas():
    registry = get_tool_registry()
    for spec in registry.list_tools():
        assert spec.input_schema.get("type") == "object", spec.name
        assert spec.output_schema.get("type") == "object", spec.name


@pytest.mark.asyncio
async def test_call_tool_list_text_assets(script_ctx):
    store, ctx = script_ctx
    registry = get_tool_registry()
    result = await registry.call_tool(
        "list_text_assets",
        {
            "observation": "列出文字资产",
            "plan_status": "查询文字资产",
            "remaining_plan": ["finish"],
        },
        ctx,
        store,
    )
    assert result.ok
    assert result.structured["count"] == 0
    assert "assets" in result.structured
    assert "counts_by_type" in result.structured
    assert json.loads(result.observation) == result.structured


_PLAN_TRACKING_ARGS = {
    "plan_status": "进行中",
    "remaining_plan": ["finish"],
}


@pytest.mark.parametrize(
    "tool_name,agent_name",
    [
        ("list_audio", "tts_agent"),
        ("list_images", "image_agent"),
        ("get_plan", "storyboard_agent"),
    ],
)
@pytest.mark.asyncio
async def test_call_tool_read_only_accepts_plan_tracking(
    script_ctx, tool_name: str, agent_name: str
):
    store, ctx = script_ctx
    ctx.agent_name = agent_name
    registry = get_tool_registry()
    result = await registry.call_tool(
        tool_name,
        {"observation": f"执行 {tool_name}", **_PLAN_TRACKING_ARGS},
        ctx,
        store,
    )
    assert result.ok


@pytest.mark.asyncio
async def test_call_tool_input_validation_fails(script_ctx):
    store, ctx = script_ctx
    registry = get_tool_registry()
    result = await registry.call_tool("create_character", {}, ctx, store)
    assert not result.ok
    assert result.structured.get("valid") is False


@pytest.mark.asyncio
async def test_call_tool_unknown(script_ctx):
    store, ctx = script_ctx
    registry = get_tool_registry()
    result = await registry.call_tool("nonexistent_tool", {"observation": "x"}, ctx, store)
    assert not result.ok
    assert "unknown" in result.structured.get("error", "")


def test_build_tool_definitions_uses_registry_schema():
    registry = get_tool_registry()
    tools = registry.build_tool_definitions(
        ["create_plot", "finish"],
        use_full_input_schema=True,
    )
    create_plot = next(t for t in tools if t.name == "create_plot")
    assert "content" in create_plot.input_schema["properties"]
    assert create_plot.output_schema.get("type") == "object"
