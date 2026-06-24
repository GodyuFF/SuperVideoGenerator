"""Agent 提示词模式与工具规格测试。"""

import pytest

from core.agents.config_manager import AgentConfigManager
from core.agents.definitions import AGENT_DEFINITIONS
from core.agents.prompt_resolver import resolve_agent_prompts
from core.agents.prompts import PromptProfile
from core.agents.tools.specs import AGENT_TOOLS
from core.models.entities import AgentPromptOverride, AgentsProjectConfig, Project, ProjectConfig


def test_all_agents_have_default_prompts():
    for name in AGENT_DEFINITIONS:
        bundle = resolve_agent_prompts(name)
        assert bundle.role_prompt.strip()


def test_all_agents_have_tools():
    for name in AGENT_DEFINITIONS:
        tools = AGENT_TOOLS.get(name, [])
        assert len(tools) >= 2, f"{name} 应至少定义 2 个工具"


def test_style_mode_selects_dynamic_image_prompt():
    from core.models.entities import VideoStyleMode

    bundle = resolve_agent_prompts(
        "storyboard_agent",
        style_mode=VideoStyleMode.DYNAMIC_IMAGE,
    )
    assert "动态图片" in bundle.role_prompt
    assert bundle.action_hint


def test_global_profile_override(tmp_path):
    path = tmp_path / "agent_config.json"
    mgr = AgentConfigManager(path=path)
    mgr.update(prompt_profiles={"script_agent": PromptProfile.AI_VIDEO.value})
    bundle = resolve_agent_prompts(
        "script_agent",
        global_profiles=mgr.get_profiles(),
    )
    assert "AI 视频" in bundle.role_prompt


def test_project_role_prompt_override():
    project = Project(
        title="test",
        config=ProjectConfig(
            agents=AgentsProjectConfig(
                overrides={
                    "script_agent": AgentPromptOverride(
                        role_prompt="自定义剧本提示词"
                    )
                }
            )
        ),
    )
    bundle = resolve_agent_prompts("script_agent", project=project)
    assert bundle.role_prompt == "自定义剧本提示词"


def test_agent_config_manager_list_public():
    mgr = AgentConfigManager()
    agents = mgr.list_agents_public()
    assert len(agents) == len(AGENT_DEFINITIONS)
    for item in agents:
        assert item["tools"]
        assert item["effective_role_prompt"]
