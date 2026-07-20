"""内置风格 Profile seed 与恢复测试。"""

import json

import pytest

from core.llm.agent.config_manager import AgentConfigManager, set_agent_config_manager
from core.llm.agent.profile_seed import (
    builtin_style_profile_ids,
    is_builtin_style_profile,
    load_profile_seed,
)
from core.llm.agent.profile_workspace import delete_profile_workspace
from core.models.agent_config import (
    AgentPromptContentOverride,
    CustomAgentDefinition,
)
from core.models.entities import VideoStyleMode


def test_load_profile_seed_has_full_roster():
    """seed 工作区应包含全量 8 个内置 Agent。"""
    for pid in builtin_style_profile_ids():
        ws = load_profile_seed(pid)
        assert "super_video_master" in ws.agent_roster
        assert "editing_agent" in ws.agent_roster
        assert len(ws.agent_roster) == 8
        assert ws.prompt_content == {}
        assert ws.tool_overrides == {}


def test_restore_clears_overrides(tmp_path, monkeypatch):
    """恢复内置风格应覆盖 prompt_content 与 tool_overrides。"""
    monkeypatch.setenv("SVG_DATA_ROOT", str(tmp_path / "data"))
    set_agent_config_manager(None)
    mgr = AgentConfigManager()
    profile_id = VideoStyleMode.STORYBOOK.value
    mgr.update(
        prompt_content={
            "script_agent": {
                profile_id: AgentPromptContentOverride(role_prompt="自定义 role"),
            }
        },
        tool_overrides_by_profile={
            profile_id: {"script_agent": {"include_only": ["tool_foo"]}},
        },
        profile_agents={
            profile_id: ["super_video_master", "script_agent"],
        },
    )
    mgr.restore_builtin_profile(profile_id)
    prompt = mgr.get_agent_prompt("script_agent", profile_id)
    assert prompt["source"]["role_prompt"] == "file"
    data = mgr.get_data()
    assert not data.tool_overrides_by_profile.get(profile_id)
    assert len(data.profile_agents[profile_id]) == 8
    ws_path = (
        tmp_path
        / "data"
        / "agents"
        / "profiles"
        / profile_id
        / "workspace.json"
    )
    payload = json.loads(ws_path.read_text(encoding="utf-8"))
    assert payload.get("prompt_content") == {}
    set_agent_config_manager(None)


def test_restore_removes_profile_only_custom_agent(tmp_path, monkeypatch):
    """恢复时移除仅存在于该 Profile 的自定义 Agent。"""
    monkeypatch.setenv("SVG_DATA_ROOT", str(tmp_path / "data"))
    set_agent_config_manager(None)
    mgr = AgentConfigManager()
    profile_id = VideoStyleMode.AI_VIDEO.value
    mgr.update(
        custom_agents=[
            CustomAgentDefinition(id="copywriter", label="文案", based_on="script_agent"),
        ],
        profile_agents={
            profile_id: ["super_video_master", "copywriter"],
        },
    )
    mgr.restore_builtin_profile(profile_id)
    data = mgr.get_data()
    assert not any(a.id == "copywriter" for a in data.custom_agents)
    assert "copywriter" not in data.profile_agents[profile_id]
    set_agent_config_manager(None)


def test_builtin_profile_not_deletable(tmp_path, monkeypatch):
    """内置风格 Profile 工作区不可删除。"""
    agents_root = tmp_path / "agents"
    monkeypatch.setenv("SVG_AGENTS_ROOT", str(agents_root))
    AgentConfigManager()
    with pytest.raises(ValueError, match="内置风格"):
        delete_profile_workspace(VideoStyleMode.AI_VIDEO.value)


def test_custom_profile_cannot_restore(tmp_path, monkeypatch):
    """自定义 Profile 不可调用 restore。"""
    monkeypatch.setenv("SVG_DATA_ROOT", str(tmp_path / "data"))
    set_agent_config_manager(None)
    mgr = AgentConfigManager()
    from core.models.agent_config import CustomPromptProfile

    mgr.update(
        custom_profiles=[
            CustomPromptProfile(id="custom_style", label="Custom", based_on="storybook"),
        ],
        style_modes=[],
    )
    with pytest.raises(ValueError, match="仅内置风格"):
        mgr.restore_builtin_profile("custom_style")
    set_agent_config_manager(None)


def test_is_builtin_style_profile():
    """内置风格 id 判定。"""
    assert is_builtin_style_profile("storybook")
    assert is_builtin_style_profile("ai_video")
    assert is_builtin_style_profile("frame_i2v")
    assert not is_builtin_style_profile("marketing_video")
    assert not is_builtin_style_profile("default")
