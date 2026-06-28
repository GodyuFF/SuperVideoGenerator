"""LLM 驱动的子 Agent：ReAct 决策与动作执行均通过大模型。"""

from core.agents.base import ReActAgent


class ScriptAgent(ReActAgent):
    name = "script_agent"
    display_name = "剧本 Agent"


class ImageAgent(ReActAgent):
    name = "image_agent"
    display_name = "图片 Agent"


class StoryboardAgent(ReActAgent):
    name = "storyboard_agent"
    display_name = "分镜 Agent"


class VideoAgent(ReActAgent):
    name = "video_agent"
    display_name = "视频 Agent"


class TTSAgent(ReActAgent):
    name = "tts_agent"
    display_name = "配音 Agent"


class EditingAgent(ReActAgent):
    name = "editing_agent"
    display_name = "剪辑 Agent"
