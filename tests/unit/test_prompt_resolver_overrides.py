"""prompt_content 覆盖优先于磁盘 md。"""

from core.llm.agent.config_manager import AgentConfigManager
from core.llm.agent.prompt_resolver import resolve_agent_prompts
from core.models.agent_config import AgentPromptContentOverride


def test_prompt_content_overrides_disk(tmp_path, monkeypatch):
    root = tmp_path / "data"
    monkeypatch.setenv("SVG_DATA_ROOT", str(root))
    mgr = AgentConfigManager()
    mgr.update(
        prompt_content={
            "storyboard_agent": {
                "storybook": AgentPromptContentOverride(role_prompt="覆盖分镜 role"),
            }
        }
    )
    bundle = resolve_agent_prompts(
        "storyboard_agent",
        global_profiles={**mgr.get_profiles(), "storyboard_agent": "storybook"},
        config=mgr,
    )
    assert bundle.role_prompt == "覆盖分镜 role"
