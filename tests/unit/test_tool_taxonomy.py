"""工具分类 taxonomy 覆盖与 API 视图测试。"""

from core.llm.agent.agent_registry import BUILTIN_AGENT_IDS
from core.llm.agent.config_manager import AgentConfigManager, _ALL_AGENT_NAMES
from core.llm.tools import get_tool_registry
from core.llm.tools.agent_tool_config import list_agent_tool_names, list_system_tools
from core.llm.tools.tool_taxonomy import resolve_tool_taxonomy, tool_public_view


def test_registry_tools_have_taxonomy():
    """Registry 中每个 tool 均可解析出非空 scopes / operations / description。"""
    registry = get_tool_registry()
    for spec in registry.list_tools():
        tax = resolve_tool_taxonomy(spec.agent, spec.name, description=spec.description, kind=spec.kind)
        assert tax.scopes, f"{spec.agent}.{spec.name} 缺少 scopes"
        assert tax.operations, f"{spec.agent}.{spec.name} 缺少 operations"
        assert tax.description.strip(), f"{spec.agent}.{spec.name} 缺少 description"


def test_all_agent_tools_have_taxonomy_in_public_view():
    """各 Agent 全部 action（含 system）在 public view 中带分类标签。"""
    for agent in _ALL_AGENT_NAMES:
        for action in list_agent_tool_names(agent):
            view = tool_public_view(agent_name=agent, action=action, name=action)
            assert view["scopes"], f"{agent}.{action} 缺少 scopes"
            assert view["operations"], f"{agent}.{action} 缺少 operations"
            assert str(view["description"]).strip()


def test_config_manager_tool_options_include_taxonomy():
    """Agent 配置 API 的 tool_options / system_tools 含 scopes 与 operations。"""
    mgr = AgentConfigManager()
    agents = mgr.list_agents_public()
    for item in agents:
        for tool in item.get("tool_options") or []:
            assert tool.get("scopes"), f"{item['name']} tool_options 缺少 scopes: {tool['action']}"
            assert tool.get("operations"), f"{item['name']} tool_options 缺少 operations: {tool['action']}"
            assert tool.get("description")
        for tool in item.get("system_tools") or []:
            assert tool.get("scopes"), f"{item['name']} system_tools 缺少 scopes: {tool['action']}"
            assert tool.get("operations"), f"{item['name']} system_tools 缺少 operations: {tool['action']}"


def test_system_tools_have_control_or_delegate_operation():
    """系统工具的操作意义应为 control 或 delegate。"""
    for agent in BUILTIN_AGENT_IDS:
        for action in list_system_tools(agent):
            tax = resolve_tool_taxonomy(agent, action)
            assert tax.operations[0] in ("control", "delegate"), (
                f"{agent}.{action} 应为 control/delegate，实际 {tax.operations}"
            )


def test_explicit_taxonomy_matches_known_actions():
    """显式映射的 action 使用预期范围标签。"""
    tax = resolve_tool_taxonomy("script_agent", "create_character")
    assert "character" in tax.scopes
    assert "create" in tax.operations
    assert "人物" in tax.description

    master_tax = resolve_tool_taxonomy("super_video_master", "delegate_agent")
    assert "orchestration" in master_tax.scopes
    assert master_tax.operations == ("delegate",)


def test_multi_scope_read_tools_flagged_in_public_view():
    """跨范围只读工具带 multi_scope_read 与详细描述。"""
    view = tool_public_view(
        agent_name="storyboard_agent",
        action="load_context",
        name="load_context",
        read_only=False,
    )
    assert view["multi_scope_read"] is True
    assert "查询" in str(view["description"])
    assert len(view["affected_data_read"]) >= 2

    single = tool_public_view(
        agent_name="storyboard_agent",
        action="get_plan",
        name="get_plan",
        read_only=True,
    )
    assert single["multi_scope_read"] is False


def test_tool_public_view_includes_schemas():
    """public view 应附带 input/output JSON Schema。"""
    view = tool_public_view(
        agent_name="script_agent",
        action="create_character",
        name="create_character",
    )
    assert view["input_schema"]["type"] == "object"
    assert "properties" in view["input_schema"]
    assert view["output_schema"]["type"] == "object"
