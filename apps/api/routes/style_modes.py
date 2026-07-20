"""REST API：视频风格模式列表。"""

from fastapi import APIRouter

from apps.api.state import state
from core.llm.style.style_mode_registry import StyleModeRegistry

router = APIRouter(prefix="/api/style-modes")


@router.get("")
def list_style_modes():
    """返回内置与自定义视频风格。"""
    return {
        "style_modes": StyleModeRegistry.list_style_modes(config=state.agent_config),
    }
