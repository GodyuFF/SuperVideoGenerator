"""Agent 定义与元数据集中管理（提示词见 prompts.py，工具见 tools/specs.py）。"""

from dataclasses import dataclass

from core.agents.llm_agents import (
    EditingAgent,
    ImageAgent,
    ScriptAgent,
    StoryboardAgent,
    TTSAgent,
    VideoAgent,
)
from core.agents.prompts import default_role_prompt
from core.agents.tools.specs import AGENT_TOOLS, AgentToolSpec


@dataclass(frozen=True)
class AgentDefinition:
    name: str
    display_name: str
    action_pipeline: list[str]
    tools: tuple[AgentToolSpec, ...] = ()

    @property
    def role_prompt(self) -> str:
        """默认模式 role_prompt（运行时由 prompt_resolver 按模式解析）。"""
        return default_role_prompt(self.name)


def _def(
    name: str,
    display_name: str,
    action_pipeline: list[str],
) -> AgentDefinition:
    return AgentDefinition(
        name=name,
        display_name=display_name,
        action_pipeline=action_pipeline,
        tools=tuple(AGENT_TOOLS.get(name, [])),
    )


AGENT_DEFINITIONS: dict[str, AgentDefinition] = {
    "script_agent": _def(
        "script_agent",
        "剧本 Agent",
        ["parse_brief", "create_plot", "create_character", "create_scene"],
    ),
    "image_agent": _def(
        "image_agent",
        "图片 Agent",
        ["scan_text_assets", "generate_images"],
    ),
    "storyboard_agent": _def(
        "storyboard_agent",
        "分镜 Agent",
        ["load_context", "create_shots", "persist_plan"],
    ),
    "video_agent": _def(
        "video_agent",
        "视频 Agent",
        ["load_shots", "generate_clips"],
    ),
    "tts_agent": _def(
        "tts_agent",
        "配音 Agent",
        ["extract_narration", "synthesize"],
    ),
    "editing_agent": _def(
        "editing_agent",
        "剪辑 Agent",
        ["gather_media", "compose_final"],
    ),
}

AGENT_CLASSES: dict[str, type] = {
    "script_agent": ScriptAgent,
    "image_agent": ImageAgent,
    "storyboard_agent": StoryboardAgent,
    "video_agent": VideoAgent,
    "tts_agent": TTSAgent,
    "editing_agent": EditingAgent,
}
