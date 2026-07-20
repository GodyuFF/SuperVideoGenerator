"""AgentConfigManager 读写与校验测试。"""



import pytest



from core.llm.agent.config_manager import AgentConfigManager, set_agent_config_manager

from core.models.agent_config import (
    AgentPromptContentOverride,
    AgentToolOverride,
    CustomAgentDefinition,
    CustomPromptProfile,
    CustomStyleMode,
)





@pytest.fixture

def agents_data_root(tmp_path, monkeypatch):

    """隔离 Agent 配置目录。"""

    root = tmp_path / "data"

    monkeypatch.setenv("SVG_DATA_ROOT", str(root))

    monkeypatch.delenv("SVG_AGENT_CONFIG_PATH", raising=False)

    monkeypatch.delenv("SVG_AGENTS_ROOT", raising=False)

    set_agent_config_manager(None)

    yield root

    set_agent_config_manager(None)





def _custom_style_patch():
    """自定义风格与 Profile 1:1 测试数据。"""
    return dict(
        style_modes=[
            CustomStyleMode(
                id="brand_style",
                label="品牌",
                default_prompt_profile="brand_style",
                builtin=False,
            ),
        ],
        custom_profiles=[
            CustomPromptProfile(id="brand_style", label="品牌", based_on="storybook"),
        ],
    )


def test_custom_profile_roundtrip(agents_data_root):
    mgr = AgentConfigManager()
    mgr.update(**_custom_style_patch())

    mgr.update(prompt_profiles={"script_agent": "brand_style"})

    data = mgr.get_data()

    assert data.custom_profiles[0].id == "brand_style"

    assert data.prompt_profiles["script_agent"] == "brand_style"





def test_prompt_content_override(agents_data_root):

    mgr = AgentConfigManager()

    mgr.update(

        prompt_content={

            "script_agent": {

                "storybook": AgentPromptContentOverride(role_prompt="自定义剧本 role"),

            }

        }

    )

    prompt = mgr.get_agent_prompt("script_agent", "storybook")

    assert prompt["role_prompt"] == "自定义剧本 role"

    assert prompt["source"]["role_prompt"] == "override"





def test_default_profile_mutation_rejected(agents_data_root):

    """default Profile 禁止写入 prompt_content。"""

    mgr = AgentConfigManager()

    with pytest.raises(ValueError, match="default Profile"):

        mgr.update(

            prompt_content={

                "script_agent": {

                    "default": AgentPromptContentOverride(role_prompt="不可写"),

                }

            }

        )





def test_remove_custom_profile_cascades_agent_config(agents_data_root):
    """删除 custom profile 时清理 prompt_content 与 prompt_profiles。"""
    mgr = AgentConfigManager()
    mgr.update(
        **_custom_style_patch(),
        prompt_profiles={"script_agent": "brand_style", "image_agent": "default"},
        prompt_content={
            "script_agent": {
                "brand_style": AgentPromptContentOverride(role_prompt="品牌专用 role"),
            },
            "image_agent": {
                "brand_style": AgentPromptContentOverride(role_prompt="不应保留"),
            },
        },
    )
    mgr.update(style_modes=[], custom_profiles=[])

    data = mgr.get_data()

    assert data.custom_profiles == []

    assert "brand_style" not in data.prompt_content.get("script_agent", {})

    assert "brand_style" not in data.prompt_content.get("image_agent", {})

    assert data.prompt_profiles["script_agent"] == "storybook"

    assert data.prompt_profiles["image_agent"] == "default"





def test_tool_overrides_exclude(agents_data_root):

    mgr = AgentConfigManager()

    mgr.update(

        tool_overrides={

            "script_agent": AgentToolOverride(exclude=["delete_plot"]),

        }

    )

    agents = mgr.list_agents_public()

    script = next(a for a in agents if a["name"] == "script_agent")

    assert "delete_plot" not in script["effective_tools"]

    assert "finish" in script["effective_tools"]





def test_list_includes_super_video_master():

    mgr = AgentConfigManager()

    names = [a["name"] for a in mgr.list_agents_public()]

    assert "super_video_master" in names





def test_remove_custom_agent_cascades_config(agents_data_root):

    """删除 custom agent 时清理 profile 编排与覆盖。"""

    mgr = AgentConfigManager()

    mgr.update(

        custom_agents=[

            CustomAgentDefinition(id="copywriter", label="文案", based_on="script_agent"),

        ],

        profile_agents={"storybook": ["copywriter"]},

        prompt_content={

            "copywriter": {

                "storybook": AgentPromptContentOverride(role_prompt="专用"),

            }

        },

        tool_overrides_by_profile={

            "storybook": {"copywriter": AgentToolOverride(exclude=["delete_plot"])},

        },

    )

    mgr.update(custom_agents=[], profile_agents={})

    data = mgr.get_data()

    assert data.custom_agents == []

    assert "copywriter" not in data.prompt_content

    assert "copywriter" not in data.tool_overrides_by_profile.get("storybook", {})





def test_tool_overrides_by_profile(agents_data_root):

    """Profile 级工具覆盖优先于全局。"""

    mgr = AgentConfigManager()

    mgr.update(

        tool_overrides_by_profile={

            "storybook": {

                "script_agent": AgentToolOverride(exclude=["delete_plot"]),

            }

        }

    )

    agents = mgr.list_agents_public(profile_id="storybook")

    script = next(a for a in agents if a["name"] == "script_agent")

    assert "delete_plot" not in script["effective_tools"]


