"""Agent 工具 override 语义测试。"""

from core.llm.tools.agent_tool_config import (
    apply_agent_tool_overrides,
    apply_master_tool_overrides,
    is_system_tool,
    list_configurable_tool_names,
    list_system_tools,
    resolve_effective_configurable_tools,
    split_effective_tools_for_react,
)
from core.models.agent_config import AgentToolOverride


def test_include_only_whitelist():
    actions = ["load_context", "create_shots", "finish", "return_to_master"]
    result = apply_agent_tool_overrides(
        "storyboard_agent",
        actions,
        AgentToolOverride(include_only=["load_context"]),
    )
    assert result == ["load_context", "finish", "return_to_master"]


def test_exclude_removes_action():
    actions = ["load_context", "create_shots", "finish"]
    result = apply_agent_tool_overrides(
        "storyboard_agent",
        actions,
        AgentToolOverride(exclude=["create_shots"]),
    )
    assert "create_shots" not in result
    assert "finish" in result


def test_exclude_cannot_remove_system_tools():
    actions = ["load_context", "finish", "ask_user_question", "return_to_master"]
    result = apply_agent_tool_overrides(
        "storyboard_agent",
        actions,
        AgentToolOverride(exclude=["finish", "ask_user_question", "return_to_master"]),
    )
    assert result == ["load_context", "finish", "ask_user_question", "return_to_master"]


def test_master_only_filters_tools():
    actions = ["delegate_agent", "tool_list_assets", "tool_get_plan_summary", "finish"]
    result = apply_master_tool_overrides(
        actions,
        AgentToolOverride(include_only=["tool_get_plan_summary"]),
    )
    assert "delegate_agent" in result
    assert "tool_get_plan_summary" in result
    assert "tool_list_assets" not in result


def test_system_tools_classification():
    assert is_system_tool("storyboard_agent", "finish")
    assert is_system_tool("storyboard_agent", "ask_user_question")
    assert is_system_tool("storyboard_agent", "return_to_master")
    assert is_system_tool("super_video_master", "delegate_agent")
    assert not is_system_tool("storyboard_agent", "load_context")

    configurable = list_configurable_tool_names("storyboard_agent")
    assert "finish" not in configurable
    assert "ask_user_question" not in configurable
    assert "return_to_master" not in configurable

    system = list_system_tools("super_video_master")
    assert "finish" in system
    assert "ask_user_question" in system
    assert "delegate_agent" in system
    assert "tool_list_assets" not in system


def test_include_only_cross_agent_action():
    """include_only 可挂载其他 Agent 域的 action。"""
    override = AgentToolOverride(include_only=["create_plot", "load_context"])
    effective = resolve_effective_configurable_tools("image_agent", "image_agent", override)
    assert "create_plot" in effective
    assert "load_context" in effective
    pipeline, reads, adhoc = split_effective_tools_for_react("image_agent", effective)
    assert "create_plot" in adhoc
    assert "load_context" in pipeline or "load_context" in reads or "load_context" in adhoc
