"""Agent 定义与角色提示词集中管理。"""

from dataclasses import dataclass

from core.agents.mock_agents import (
    EditingAgent,
    ImageAgent,
    ScriptAgent,
    StoryboardAgent,
    TTSAgent,
    VideoAgent,
)


@dataclass(frozen=True)
class AgentDefinition:
    name: str
    display_name: str
    role_prompt: str
    action_pipeline: list[str]


AGENT_DEFINITIONS: dict[str, AgentDefinition] = {
    "script_agent": AgentDefinition(
        name="script_agent",
        display_name="剧本 Agent",
        role_prompt="你是剧本 Agent，负责根据任务简报生成剧情、人物、场景等文字资产。",
        action_pipeline=["parse_brief", "create_plot", "create_character", "create_scene"],
    ),
    "image_agent": AgentDefinition(
        name="image_agent",
        display_name="图片 Agent",
        role_prompt="你是图片 Agent，负责扫描文字资产并生成对应图片素材。",
        action_pipeline=["scan_text_assets", "generate_images"],
    ),
    "storyboard_agent": AgentDefinition(
        name="storyboard_agent",
        display_name="分镜 Agent",
        role_prompt="你是分镜 Agent，负责基于剧本与图片生成镜头列表与视频计划稿。",
        action_pipeline=["load_context", "create_shots", "persist_plan"],
    ),
    "video_agent": AgentDefinition(
        name="video_agent",
        display_name="视频 Agent",
        role_prompt="你是视频 Agent，负责按计划稿生成 AI 视频片段并预估费用。",
        action_pipeline=["load_shots", "generate_clips"],
    ),
    "tts_agent": AgentDefinition(
        name="tts_agent",
        display_name="配音 Agent",
        role_prompt="你是配音 Agent，负责提取旁白文案并合成 TTS 音频文件。",
        action_pipeline=["extract_narration", "synthesize"],
    ),
    "editing_agent": AgentDefinition(
        name="editing_agent",
        display_name="剪辑 Agent",
        role_prompt="你是剪辑 Agent，负责收集媒体素材并合成最终成片。",
        action_pipeline=["gather_media", "compose_final"],
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