"""视频风格模式注册表：内置 + 自定义 style_modes。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.llm.agent.style_profile_sync import removed_style_ids
from core.models.agent_config import CustomStyleMode
from core.models.entities import VideoStyleMode

if TYPE_CHECKING:
    from core.llm.agent.config_manager import AgentConfigManager

_BUILTIN_STYLE_MODES: list[CustomStyleMode] = [
    CustomStyleMode(
        id=VideoStyleMode.STORYBOOK.value,
        label="故事书模式",
        default_prompt_profile=VideoStyleMode.STORYBOOK.value,
        include_video_gen=False,
        builtin=True,
    ),
    CustomStyleMode(
        id=VideoStyleMode.AI_VIDEO.value,
        label="AI 视频模式",
        default_prompt_profile=VideoStyleMode.AI_VIDEO.value,
        include_video_gen=True,
        video=["text2video", "img2video", "keyframes"],
        builtin=True,
    ),
    CustomStyleMode(
        id=VideoStyleMode.FRAME_I2V.value,
        label="画面图生视频",
        default_prompt_profile=VideoStyleMode.FRAME_I2V.value,
        include_video_gen=True,
        video=["text2video", "img2video", "keyframes"],
        builtin=True,
    ),
]


def _config_manager() -> "AgentConfigManager":
    from core.llm.agent.config_manager import get_agent_config_manager

    return get_agent_config_manager()


class StyleModeRegistry:
    """合并内置与自定义视频风格，供工作台与运行时校验。"""

    @staticmethod
    def list_style_modes(*, config: AgentConfigManager | None = None) -> list[dict[str, object]]:
        """返回全部风格（builtin 优先，自定义追加）。"""
        mgr = config or _config_manager()
        data = mgr.get_data()
        builtin_ids = {m.id for m in _BUILTIN_STYLE_MODES}
        removed = removed_style_ids()
        custom = [
            m
            for m in data.style_modes
            if m.id not in builtin_ids
            and m.id not in removed
            and not m.builtin
        ]
        modes = _BUILTIN_STYLE_MODES + custom
        return [
            {
                "id": m.id,
                "label": m.label,
                "default_prompt_profile": m.default_prompt_profile,
                "include_video_gen": bool(m.video),
                "video": list(m.video or []),
                "builtin": m.builtin,
            }
            for m in modes
        ]

    @staticmethod
    def get_style_mode(style_id: str, *, config: AgentConfigManager | None = None) -> CustomStyleMode | None:
        """按 id 查找风格定义。"""
        for item in StyleModeRegistry.list_style_modes(config=config):
            if item["id"] == style_id:
                return CustomStyleMode.model_validate(item)
        return None

    @staticmethod
    def validate_style_id(style_id: str, *, config: AgentConfigManager | None = None) -> str:
        """校验风格 id 是否已注册，返回规范化 id。"""
        sid = str(style_id or "").strip()
        if not sid:
            raise ValueError("style_mode 不能为空")
        if StyleModeRegistry.get_style_mode(sid, config=config) is None:
            raise ValueError(f"未知视频风格: {sid}")
        return sid

    @staticmethod
    def style_includes_video_gen(style_id: str, *, config: AgentConfigManager | None = None) -> bool:
        """该风格是否包含 video_gen 委派（由 video 子模式列表决定）。"""
        from core.llm.style.video_capability import style_video_modes

        if style_video_modes(style_id, config=config):
            return True
        if StyleModeRegistry.get_style_mode(style_id, config=config) is None:
            return style_id == VideoStyleMode.AI_VIDEO.value
        return False

    @staticmethod
    def style_video_modes(style_id: str, *, config: AgentConfigManager | None = None) -> list[str]:
        """该风格允许的 AI 视频子模式（文生/图生/关键帧）。"""
        from core.llm.style.video_capability import style_video_modes as _modes

        return list(_modes(style_id, config=config))

    @staticmethod
    def default_prompt_profile_for_style(
        style_id: str, *, config: AgentConfigManager | None = None
    ) -> str:
        """风格对应的默认 PromptProfile id。"""
        mode = StyleModeRegistry.get_style_mode(style_id, config=config)
        if mode is None:
            return VideoStyleMode.STORYBOOK.value
        return mode.default_prompt_profile
