"""core/llm/prompt 提示词加载与注册表测试。"""

from core.llm.prompt.registry import (
    AGENT_PROMPT_PROFILES,
    get_action_json_system_base,
    get_agent_bundle,
    get_react_system_prompt,
    PromptProfile,
)
from core.llm.prompt.loader import load_required


def test_react_system_prompt_loaded_from_file():
    text = get_react_system_prompt()
    assert "tool_calls" in text
    assert "ReAct" in text
    assert text == load_required("rules/react_tools.md")


def test_action_tools_system_base_loaded():
    text = get_action_json_system_base()
    assert "observation" in text
    assert "function" in text
    assert "input_schema" in text or "tools" in text


def test_fixed_role_path():
    from core.llm.prompt.registry import get_agent_role_prompt

    text = get_agent_role_prompt("script_agent", PromptProfile.DEFAULT)
    assert "# Identity" in text
    assert "剧本 Agent" in text


def test_agent_prompt_profiles_cover_pipeline_agents():
    for name in (
        "script_agent",
        "image_agent",
        "storyboard_agent",
        "video_agent",
        "tts_agent",
        "editing_agent",
    ):
        assert name in AGENT_PROMPT_PROFILES
        bundle = get_agent_bundle(name, PromptProfile.DEFAULT)
        assert bundle.role_prompt.strip()


def test_super_video_master_role_prompt():
    from core.llm.prompt.registry import get_agent_role_prompt

    text = get_agent_role_prompt("super_video_master", PromptProfile.DEFAULT)
    assert "超级视频大师" in text
    assert "# Identity" in text


def test_extract_role_summary():
    from core.llm.prompt.registry import extract_role_summary

    summary = extract_role_summary("# Identity\n你是剧本 Agent，负责设计剧本。")
    assert "剧本 Agent" in summary



def test_storyboard_storybook_role_requires_voice():
    """storybook role 应写明 audio_tracks voice clip text 必填。"""
    from core.llm.prompt.registry import get_agent_role_prompt

    role = get_agent_role_prompt("storyboard_agent", PromptProfile.STORYBOOK)
    assert "audio_tracks" in role
    assert "voice" in role
