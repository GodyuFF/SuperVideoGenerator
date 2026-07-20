"""Agent 注册表：Profile 编排与自定义 Agent。"""

import pytest

from core.llm.agent.agent_registry import (
    is_builtin_agent,
    list_agents_for_profile,
    validate_custom_agent_definition,
)
from core.llm.agent.config_manager import AgentConfigManager
from core.models.agent_config import CustomAgentDefinition


def test_builtin_agents_always_in_profile_roster(tmp_path):
    """内置 Agent 始终出现在 Profile 编排中。"""
    mgr = AgentConfigManager(path=tmp_path / "agent_config.json")
    ids = list_agents_for_profile("default", config=mgr)
    assert "super_video_master" in ids
    assert "script_agent" in ids
    assert is_builtin_agent("script_agent")


def test_custom_agent_per_profile(tmp_path):
    """自定义 Agent 仅出现在绑定的 Profile。"""
    path = tmp_path / "agent_config.json"
    mgr = AgentConfigManager(path=path)
    mgr.update(
        custom_agents=[
            CustomAgentDefinition(id="copywriter", label="文案", based_on="script_agent"),
        ],
        profile_agents={"storybook": ["super_video_master", "copywriter"]},
    )
    default_ids = list_agents_for_profile("default", config=mgr)
    image_ids = list_agents_for_profile("storybook", config=mgr)
    assert "copywriter" not in default_ids
    assert "copywriter" in image_ids


def test_validate_custom_agent_rejects_builtin_id():
    """不可使用内置 Agent id 作为自定义 Agent。"""
    with pytest.raises(ValueError, match="内置"):
        validate_custom_agent_definition(
            CustomAgentDefinition(id="script_agent", label="x", based_on="script_agent")
        )
