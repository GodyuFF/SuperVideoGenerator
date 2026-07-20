"""video_agent tools 注册。"""

from core.llm.tools.register_helpers import register_handlers
from core.llm.tools.registry import ToolRegistry
from core.llm.tools.video.handler import HANDLERS as VIDEO_HANDLERS

_VIDEO_META: dict[str, tuple[str, str, str, str]] = {
    "load_shots": ("video_agent", "write_ad_hoc", "video.load_shots", "【legacy】加载分镜镜头列表"),
    "generate_clips": ("video_agent", "write_ad_hoc", "video.generate_clips", "【legacy】为镜头生成 AI 视频片段"),
    "scan_video_clips": ("video_agent", "read", "video.scan_video_clips", "扫描待生成 video_clip 文字资产"),
    "generate_video_clips": (
        "video_agent",
        "write_pipeline",
        "video.generate_video_clips",
        "为 storyboard 已创建的 video_clip 文字资产生成 AI 视频 mp4",
    ),
    "generate_from_timeline": (
        "video_agent",
        "write_ad_hoc",
        "video.generate_from_timeline",
        "按剪辑 video 轨批量生成（可选路径）",
    ),
    "list_videos": ("video_agent", "read", "video.list_videos", "列出已生成视频资产"),
}


def register_video_tools(registry: ToolRegistry) -> None:
    register_handlers(registry, VIDEO_HANDLERS, _VIDEO_META)
