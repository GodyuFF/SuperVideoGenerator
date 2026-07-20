"""Profile Agent roster 与主编排 delegate 联动测试。"""

from core.llm.agent.agent_registry import (
    delegates_for_roster,
    filter_agents_catalog,
    list_agents_for_profile,
    resolve_roster_agent_for_step,
)
from core.llm.agent.config_manager import AgentConfigManager
from core.llm.master.delegate_tool import (
    DELEGATE_AGENT_ACTION,
    build_delegate_agent_input_schema,
)
from core.llm.master.session import build_master_sub_agents
from core.llm.prompt.registry import get_agent_role_prompt
from core.llm.prompt.registry import PromptProfile
from core.models.agent_config import CustomAgentDefinition
from core.models.entities import VideoStyleMode


def test_roster_remove_builtin_sub_agent(tmp_path, monkeypatch):
    """Profile roster 移除内置子 Agent 后侧栏列表同步缩短。"""
    root = tmp_path / "data"
    monkeypatch.setenv("SVG_DATA_ROOT", str(root))
    mgr = AgentConfigManager()
    roster = list_agents_for_profile("storybook", config=mgr)
    assert "script_agent" in roster
    trimmed = [a for a in roster if a != "script_agent"]
    mgr.update(profile_agents={"storybook": trimmed})
    ids = list_agents_for_profile("storybook", config=mgr)
    assert "super_video_master" in ids
    assert "script_agent" not in ids


def test_custom_agent_replaces_canonical_for_delegate(tmp_path, monkeypatch):
    """roster 中用 custom 替代 canonical 时 delegate 解析到 custom id。"""
    root = tmp_path / "data"
    monkeypatch.setenv("SVG_DATA_ROOT", str(root))
    mgr = AgentConfigManager()
    roster = list_agents_for_profile("storybook", config=mgr)
    roster = [a for a in roster if a != "script_agent"]
    roster.append("copywriter")
    mgr.update(
        custom_agents=[
            CustomAgentDefinition(id="copywriter", label="文案", based_on="script_agent"),
        ],
        profile_agents={"storybook": roster},
    )
    agent_id = resolve_roster_agent_for_step("script_design", "storybook", config=mgr)
    assert agent_id == "copywriter"


def test_delegates_filtered_by_roster(tmp_path, monkeypatch):
    """主编排 delegate 列表随 roster 过滤；schema enum 不含被移除 agent。"""
    root = tmp_path / "data"
    monkeypatch.setenv("SVG_DATA_ROOT", str(root))
    mgr = AgentConfigManager()
    roster = [a for a in list_agents_for_profile("storybook", config=mgr) if a != "image_agent"]
    mgr.update(profile_agents={"storybook": roster})
    delegates = delegates_for_roster("storybook", "storybook", config=mgr)
    assert delegates == [DELEGATE_AGENT_ACTION]
    schema = build_delegate_agent_input_schema(
        "storybook", VideoStyleMode.STORYBOOK, config=mgr
    )
    enum_ids = schema["properties"]["agent_id"]["enum"]
    assert "image_agent" not in enum_ids


def test_build_master_sub_agents_respects_roster(tmp_path, monkeypatch):
    """build_master_sub_agents 仅返回 roster 内 step。"""
    root = tmp_path / "data"
    monkeypatch.setenv("SVG_DATA_ROOT", str(root))
    mgr = AgentConfigManager()
    roster = [a for a in list_agents_for_profile("default", config=mgr) if a in ("super_video_master", "script_agent")]
    mgr.update(profile_agents={"storybook": roster})
    specs = build_master_sub_agents(profile_id="storybook", config=mgr)
    agent_names = {s.agent_name for s in specs}
    assert "script_agent" in agent_names
    assert "image_agent" not in agent_names


def test_agents_catalog_filtered_by_roster(tmp_path, monkeypatch):
    """agents_catalog 注入时按 roster 过滤章节。"""
    root = tmp_path / "data"
    monkeypatch.setenv("SVG_DATA_ROOT", str(root))
    mgr = AgentConfigManager()
    roster = [a for a in list_agents_for_profile("storybook", config=mgr) if a != "image_agent"]
    mgr.update(profile_agents={"storybook": roster})
    catalog = "## script_agent\n\nbody\n\n## image_agent\n\nimg"
    filtered = filter_agents_catalog(catalog, "storybook", config=mgr)
    assert "script_agent" in filtered
    assert "image_agent" not in filtered
    role = get_agent_role_prompt(
        "super_video_master",
        PromptProfile.STORYBOOK,
        profile_id="storybook",
        config=mgr,
    )
    assert "script_agent" in role
    assert "## image_agent" not in role
