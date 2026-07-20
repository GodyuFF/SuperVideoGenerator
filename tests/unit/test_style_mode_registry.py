"""StyleModeRegistry 自定义风格测试。"""

from core.llm.agent.config_manager import AgentConfigManager
from core.llm.master.delegate_deps import delegates_for_style
from core.llm.style.style_mode_registry import StyleModeRegistry
from core.models.agent_config import CustomStyleMode
from core.models.entities import VideoStyleMode


def test_builtin_style_modes():
    modes = StyleModeRegistry.list_style_modes()
    ids = {m["id"] for m in modes}
    assert VideoStyleMode.STORYBOOK.value in ids
    assert VideoStyleMode.AI_VIDEO.value in ids
    assert VideoStyleMode.FRAME_I2V.value in ids
    assert "dynamic_comic" not in ids


def test_custom_style_with_video_gen(tmp_path):
    path = tmp_path / "agent_config.json"
    mgr = AgentConfigManager(path=path)
    mgr.update(
        style_modes=[
            CustomStyleMode(
                id="brand_video",
                label="品牌 AI 视频",
                default_prompt_profile="brand_video",
                include_video_gen=True,
                video=["text2video", "img2video", "keyframes"],
                builtin=False,
            )
        ],
    )
    assert StyleModeRegistry.style_includes_video_gen("brand_video", config=mgr)
    assert delegates_for_style("brand_video", config=mgr) == ["delegate_agent"]
