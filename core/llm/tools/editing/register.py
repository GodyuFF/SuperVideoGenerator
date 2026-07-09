"""editing_agent tools 注册。"""

from core.llm.tools.editing.handler import HANDLERS as EDITING_HANDLERS
from core.llm.tools.editing.opencut_handler import OPEN_CUT_HANDLERS
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
    "analyze_edit_timeline": (
        "editing_agent",
        "read",
        "edit.analyze_edit_timeline",
        "按时间窗分析剪辑结构、空白、重叠与优化建议",
    ),
    "gather_media": ("editing_agent", "write_pipeline", "edit.gather_media", "收集图片/视频/配音素材"),
    "compose_final": ("editing_agent", "write_pipeline", "edit.compose_final", "合成最终成片"),
    "list_final": ("editing_agent", "read", "edit.list_final", "列出成片资产"),
}

# Agent 可控剪辑工具
_OPEN_CUT_META: dict[str, tuple[str, str, str, str]] = {
    "add_clip": ("editing_agent", "write_ad_hoc", "edit.add_clip", "添加媒体片段到时间轴"),
    "update_clip": ("editing_agent", "write_ad_hoc", "edit.update_clip", "修改片段属性（位置、时长、变换）"),
    "remove_clip": ("editing_agent", "write_ad_hoc", "edit.remove_clip", "删除时间轴片段"),
    "apply_effect": ("editing_agent", "write_ad_hoc", "edit.apply_effect", "应用视觉效果"),
    "set_keyframe": ("editing_agent", "write_ad_hoc", "edit.set_keyframe", "设置动画关键帧"),
    "export_timeline": ("editing_agent", "write_pipeline", "edit.export_timeline", "导出成片视频"),
    "get_export_status": ("editing_agent", "read", "edit.get_export_status", "查询导出进度"),
}


def register_editing_tools(registry: ToolRegistry) -> None:
    register_handlers(registry, EDITING_HANDLERS, _EDITING_META)
    register_handlers(registry, OPEN_CUT_HANDLERS, _OPEN_CUT_META)
