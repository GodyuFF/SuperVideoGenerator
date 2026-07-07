"""editing_agent tools 注册。"""

from core.llm.tools.editing.handler import HANDLERS as EDITING_HANDLERS
from core.llm.tools.register_helpers import register_handlers
from core.llm.tools.registry import ToolRegistry

_EDITING_META: dict[str, tuple[str, str, str, str]] = {
    "load_edit_context": (
        "editing_agent",
        "read",
        "edit.load_edit_context",
        "加载 VideoPlan 与可用素材清单",
    ),
    "plan_edit_timeline": (
        "editing_agent",
        "write_pipeline",
        "edit.plan_edit_timeline",
        "生成详细剪辑计划稿（三轨+运镜/转场/背景）",
    ),
    "validate_edit_assets": (
        "editing_agent",
        "read",
        "edit.validate_edit_assets",
        "校验剪辑计划稿素材是否齐备",
    ),
    "report_missing_assets": (
        "editing_agent",
        "write_pipeline",
        "edit.report_missing_assets",
        "上报缺失素材供主编排重委派",
    ),
    "get_edit_timeline": (
        "editing_agent",
        "read",
        "edit.get_edit_timeline",
        "读取剪辑计划稿",
    ),
    "gather_media": ("editing_agent", "write_pipeline", "edit.gather_media", "收集图片/视频/配音素材"),
    "compose_final": ("editing_agent", "write_pipeline", "edit.compose_final", "合成最终成片"),
    "list_final": ("editing_agent", "read", "edit.list_final", "列出成片资产"),
}


def register_editing_tools(registry: ToolRegistry) -> None:
    register_handlers(registry, EDITING_HANDLERS, _EDITING_META)
