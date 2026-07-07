"""storyboard_agent tools 注册。"""

from core.llm.tools.register_helpers import register_handlers
from core.llm.tools.registry import ToolRegistry
from core.llm.tools.storyboard.handler import HANDLERS as STORYBOARD_HANDLERS

_STORYBOARD_META: dict[str, tuple[str, str, str, str]] = {
    "load_context": ("storyboard_agent", "write_pipeline", "storyboard.load_context", "加载剧本与资产上下文"),
    "create_shots": ("storyboard_agent", "write_pipeline", "storyboard.create_shots", "设计镜头列表"),
    "persist_plan": ("storyboard_agent", "write_pipeline", "storyboard.persist_plan", "保存视频计划稿"),
    "get_plan": ("storyboard_agent", "read", "storyboard.get_plan", "读取当前视频计划稿"),
}


def register_storyboard_tools(registry: ToolRegistry) -> None:
    register_handlers(registry, STORYBOARD_HANDLERS, _STORYBOARD_META)
