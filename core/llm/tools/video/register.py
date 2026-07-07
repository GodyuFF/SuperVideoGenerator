"""video_agent tools 注册。"""

from core.llm.tools.register_helpers import register_handlers
from core.llm.tools.registry import ToolRegistry
from core.llm.tools.video.handler import HANDLERS as VIDEO_HANDLERS

_VIDEO_META: dict[str, tuple[str, str, str, str]] = {
    "load_shots": ("video_agent", "write_pipeline", "video.load_shots", "加载分镜镜头列表"),
    "generate_clips": ("video_agent", "write_pipeline", "video.generate_clips", "为镜头生成 AI 视频片段"),
    "generate_from_timeline": ("video_agent", "write_pipeline", "video.generate_from_timeline", "按剪辑 video 轨生成视频片段"),
    "list_videos": ("video_agent", "read", "video.list_videos", "列出已生成视频资产"),
}


def register_video_tools(registry: ToolRegistry) -> None:
    register_handlers(registry, VIDEO_HANDLERS, _VIDEO_META)
