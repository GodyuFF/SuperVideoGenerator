"""全量 Agent × PromptProfile 提示词组装测试。"""

import pytest

from core.llm.agent.agent_registry import BUILTIN_AGENT_IDS
from core.llm.agent.config_manager import AgentConfigManager
from core.llm.agent.prompt_resolver import resolve_agent_prompts
from core.llm.prompt.profile_registry import PromptProfileRegistry
from core.llm.prompt.registry import PromptProfile
from core.models.agent_config import AgentPromptContentOverride


@pytest.mark.parametrize("profile", list(PromptProfile))
@pytest.mark.parametrize("agent_name", BUILTIN_AGENT_IDS)
def test_get_bundle_non_empty_for_all_profiles(agent_name: str, profile: PromptProfile):
    """PromptProfileRegistry.get_bundle 对所有内置 Agent × Profile 返回非空 role。"""
    bundle = PromptProfileRegistry.get_bundle(agent_name, profile.value)
    assert bundle.role_prompt.strip(), f"{agent_name}/{profile.value} role_prompt 为空"


@pytest.mark.parametrize("profile", list(PromptProfile))
@pytest.mark.parametrize("agent_name", BUILTIN_AGENT_IDS)
def test_resolve_agent_prompts_non_empty(agent_name: str, profile: PromptProfile):
    """resolve_agent_prompts 对所有内置 Agent × Profile 返回非空 role。"""
    bundle = resolve_agent_prompts(
        agent_name,
        global_profiles={agent_name: profile.value},
    )
    assert bundle.role_prompt.strip(), f"{agent_name}/{profile.value} role_prompt 为空"


@pytest.mark.parametrize("profile", [p for p in PromptProfile if p != PromptProfile.DEFAULT])
@pytest.mark.parametrize("agent_name", BUILTIN_AGENT_IDS)
def test_prompt_content_override_applies_to_editable_profiles(agent_name: str, profile: PromptProfile, tmp_path, monkeypatch):
    """prompt_content 覆盖对可编辑 Profile 生效。"""
    root = tmp_path / "data"
    monkeypatch.setenv("SVG_DATA_ROOT", str(root))
    mgr = AgentConfigManager()
    override_text = f"覆盖提示词-{agent_name}-{profile.value}"
    mgr.update(
        prompt_content={
            agent_name: {
                profile.value: AgentPromptContentOverride(role_prompt=override_text),
            }
        }
    )
    bundle = resolve_agent_prompts(
        agent_name,
        global_profiles={**mgr.get_profiles(), agent_name: profile.value},
        config=mgr,
    )
    assert bundle.role_prompt == override_text, f"{agent_name}/{profile.value} 未应用覆盖"


def test_all_profiles_registered():
    """内置 PromptProfile 均可被 registry 列出。"""
    profiles = PromptProfileRegistry.list_all_profiles()
    ids = {str(p["id"]) for p in profiles}
    for profile in PromptProfile:
        assert profile.value in ids
