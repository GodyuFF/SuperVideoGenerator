"""storyboard_agent tools 注册。"""

from core.llm.tools.register_helpers import register_handlers
from core.llm.tools.registry import ToolRegistry
from core.llm.tools.storyboard.handler import HANDLERS as STORYBOARD_HANDLERS

_STORYBOARD_META: dict[str, tuple[str, str, str, str]] = {
    "load_context": (
        "storyboard_agent",
        "write_pipeline",
        "storyboard.load_context",
        "加载剧本与资产上下文（必传 script_id）",
    ),
    "create_shots": ("storyboard_agent", "write_pipeline", "storyboard.create_shots", "设计镜内多轨 Shot（sub_shots + 必填 voice audio_tracks.clip.text）"),
    "create_frames": ("storyboard_agent", "write_pipeline", "storyboard.create_frames", "为每子镜创建剧本画面 frame 文字资产"),
    "create_video_clips": (
        "storyboard_agent",
        "write_pipeline",
        "storyboard.create_video_clips",
        "为每子镜创建 video_clip 文字资产；element_refs 仅 {\"frame\":[...]}（禁止 character/scene/prop）",
    ),
    "persist_plan": ("storyboard_agent", "write_pipeline", "storyboard.persist_plan", "保存视频计划稿"),
    "get_plan": ("storyboard_agent", "read", "storyboard.get_plan", "读取当前视频计划稿"),
}


def register_storyboard_tools(registry: ToolRegistry) -> None:
    register_handlers(registry, STORYBOARD_HANDLERS, _STORYBOARD_META)
