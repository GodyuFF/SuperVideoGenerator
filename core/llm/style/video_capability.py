"""视频风格 AI 生视频能力：文生/图生/关键帧三种子模式。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from core.llm.style.style_mode_registry import StyleModeRegistry
from core.store.memory import MemoryStore

if TYPE_CHECKING:
    from core.llm.agent.config_manager import AgentConfigManager

StyleVideoGenMode = Literal["text2video", "img2video", "keyframes"]

ALL_STYLE_VIDEO_MODES: tuple[StyleVideoGenMode, ...] = (
    "text2video",
    "img2video",
    "keyframes",
)


def style_video_modes(
    style_id: str,
    *,
    config: AgentConfigManager | None = None,
) -> list[StyleVideoGenMode]:
    """返回风格允许的 AI 视频子模式；空列表表示不可 AI 生视频。"""
    mode = StyleModeRegistry.get_style_mode(style_id, config=config)
    if mode is None or not mode.video:
        return []
    out: list[StyleVideoGenMode] = []
    for item in mode.video:
        key = str(item).strip()
        if key in ALL_STYLE_VIDEO_MODES and key not in out:
            out.append(key)  # type: ignore[arg-type]
    return out


def style_includes_video_gen(
    style_id: str,
    *,
    config: AgentConfigManager | None = None,
) -> bool:
    """风格是否启用任意 AI 视频子模式。"""
    return bool(style_video_modes(style_id, config=config))


def script_style_video_modes(
    store: MemoryStore,
    script_id: str,
    *,
    config: AgentConfigManager | None = None,
) -> list[StyleVideoGenMode]:
    """按剧本已锁定风格解析允许的 AI 视频子模式。"""
    from core.guards.script_style import normalize_style_mode_id

    script = store.get_script(script_id)
    if not script:
        return []
    style_id = normalize_style_mode_id(script.style_mode)
    if not style_id:
        return []
    return style_video_modes(style_id, config=config)


def assert_style_allows_video_mode(
    style_id: str,
    mode: str,
    *,
    config: AgentConfigManager | None = None,
) -> None:
    """校验风格是否允许指定 AI 视频子模式，不允许则抛 ValueError。"""
    allowed = style_video_modes(style_id, config=config)
    if not allowed:
        raise ValueError(f"视频风格 {style_id} 未配置 AI 生视频能力（video）")
    key = str(mode).strip()
    if key not in allowed:
        raise ValueError(
            f"视频风格 {style_id} 不支持 {key}，允许：{', '.join(allowed)}"
        )
