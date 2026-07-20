"""视频风格 video 子模式能力测试。"""

from core.llm.agent.config_manager import AgentConfigManager
from core.llm.style.style_mode_registry import StyleModeRegistry
from core.llm.style.video_capability import style_video_modes
from core.models.agent_config import CustomStyleMode
from core.models.entities import VideoStyleMode


def test_ai_video_style_has_all_modes():
    """内置 AI 视频模式应包含三种子模式。"""
    modes = style_video_modes(VideoStyleMode.AI_VIDEO.value)
    assert modes == ["text2video", "img2video", "keyframes"]


def test_storybook_has_no_video_modes():
    """故事书模式不可 AI 生视频。"""
    assert style_video_modes(VideoStyleMode.STORYBOOK.value) == []


def test_custom_style_partial_video_modes(tmp_path):
    """自定义风格可只启用部分子模式。"""
    mgr = AgentConfigManager(path=tmp_path / "agent_config.json")
    mgr.update(
        style_modes=[
            CustomStyleMode(
                id="img_only",
                label="仅图生视频",
                default_prompt_profile="storybook",
                video=["img2video"],
                builtin=False,
            )
        ]
    )
    assert style_video_modes("img_only", config=mgr) == ["img2video"]
    assert StyleModeRegistry.style_includes_video_gen("img_only", config=mgr)


def test_legacy_include_video_gen_migrates_to_video_list():
    """旧数据 include_video_gen=true 应迁移为完整 video 列表。"""
    mode = CustomStyleMode.model_validate(
        {
            "id": "legacy",
            "label": "旧风格",
            "default_prompt_profile": "storybook",
            "include_video_gen": True,
            "builtin": False,
        }
    )
    assert mode.video == ["text2video", "img2video", "keyframes"]
    assert mode.include_video_gen is True
