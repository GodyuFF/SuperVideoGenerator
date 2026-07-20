"""Agent 定义与元数据集中管理（提示词见 prompts.py，工具见 tools/specs.py）。"""

from dataclasses import dataclass

from core.llm.agent.llm_agents import (
    EditingAgent,
    ImageAgent,
    ScriptAgent,
    StoryboardAgent,
    StoryboardRefineAgent,
    TTSAgent,
    VideoAgent,
)
from core.llm.agent.prompts import default_role_prompt
from core.llm.tools.shared.agent_tools import AGENT_TOOLS, AgentToolSpec, ad_hoc_actions, pipeline_actions, read_actions


@dataclass(frozen=True)
class AgentDefinition:
    name: str
    display_name: str
    action_pipeline: list[str]
    ad_hoc_actions: list[str]
    read_actions: list[str]
    tools: tuple[AgentToolSpec, ...] = ()

    @property
    def role_prompt(self) -> str:
        """默认模式 role_prompt（运行时由 prompt_resolver 按模式解析）。"""
        return default_role_prompt(self.name)


def _def(
    name: str,
    display_name: str,
    *,
    action_pipeline: list[str] | None = None,
) -> AgentDefinition:
    tools = tuple(AGENT_TOOLS.get(name, []))
    return AgentDefinition(
        name=name,
        display_name=display_name,
        action_pipeline=action_pipeline or pipeline_actions(name),
        ad_hoc_actions=ad_hoc_actions(name),
        read_actions=read_actions(name),
        tools=tools,
    )


AGENT_DEFINITIONS: dict[str, AgentDefinition] = {
    "script_agent": _def("script_agent", "剧本 Agent"),
    "image_agent": _def("image_agent", "图片 Agent"),
    "storyboard_agent": _def(
        "storyboard_agent",
        "分镜 Agent",
        action_pipeline=[
            "load_context",
            "create_shots",
            "create_frames",
            "create_video_clips",
            "persist_plan",
        ],
    ),
    "storyboard_refine_agent": _def(
        "storyboard_refine_agent",
        "分镜复核 Agent",
        action_pipeline=[
        "sync_actual_assets",
        "update_frames",
            "persist_review",
        ],
    ),
    "video_agent": _def("video_agent", "视频 Agent"),
    "tts_agent": _def("tts_agent", "配音 Agent"),
    "editing_agent": _def("editing_agent", "剪辑 Agent"),
}

AGENT_CLASSES: dict[str, type] = {
    "script_agent": ScriptAgent,
    "image_agent": ImageAgent,
    "storyboard_agent": StoryboardAgent,
    "storyboard_refine_agent": StoryboardRefineAgent,
    "video_agent": VideoAgent,
    "tts_agent": TTSAgent,
    "editing_agent": EditingAgent,
}
