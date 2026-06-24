"""Agent 提示词集中管理：按模式（default / dynamic_image / ai_video）区分角色与行动说明。"""

from enum import Enum

from pydantic import BaseModel


class PromptProfile(str, Enum):
    """提示词配置模式，与视频风格模式对齐并可独立选用。"""

    DEFAULT = "default"
    DYNAMIC_IMAGE = "dynamic_image"
    AI_VIDEO = "ai_video"


class AgentPromptBundle(BaseModel):
    """单个 Agent 在某模式下的提示词集合。"""

    role_prompt: str
    action_hint: str = ""  # 追加到 ACTION_JSON_SYSTEM 的模式专属说明


# 各 Agent 在不同模式下的提示词；未列出的模式回退到 default
AGENT_PROMPT_PROFILES: dict[str, dict[PromptProfile, AgentPromptBundle]] = {
    "script_agent": {
        PromptProfile.DEFAULT: AgentPromptBundle(
            role_prompt="你是剧本 Agent，负责根据任务简报生成剧情、人物、场景等文字资产。",
        ),
        PromptProfile.DYNAMIC_IMAGE: AgentPromptBundle(
            role_prompt=(
                "你是剧本 Agent（动态图片模式）。"
                "重点产出适合静态画面+运镜的旁白文案与场景描述，"
                "人物与场景需便于后续生图与 Ken Burns 运镜。"
            ),
            action_hint="create_plot 的旁白须口语化、适合配音朗读。",
        ),
        PromptProfile.AI_VIDEO: AgentPromptBundle(
            role_prompt=(
                "你是剧本 Agent（AI 视频模式）。"
                "剧情与场景设计需考虑镜头可视频化，"
                "避免纯抽象概念，便于分镜与图生视频。"
            ),
        ),
    },
    "image_agent": {
        PromptProfile.DEFAULT: AgentPromptBundle(
            role_prompt="你是图片 Agent，负责扫描文字资产并生成对应图片素材。",
        ),
        PromptProfile.DYNAMIC_IMAGE: AgentPromptBundle(
            role_prompt=(
                "你是图片 Agent（动态图片模式）。"
                "为人物与场景生成高分辨率、无水印、适合全屏展示的参考图。"
            ),
            action_hint="generate_images 优先 character 与 scene 类型资产。",
        ),
        PromptProfile.AI_VIDEO: AgentPromptBundle(
            role_prompt=(
                "你是图片 Agent（AI 视频模式）。"
                "生成可作为视频首帧/尾帧的清晰构图，注意主体居中、光影稳定。"
            ),
        ),
    },
    "storyboard_agent": {
        PromptProfile.DEFAULT: AgentPromptBundle(
            role_prompt="你是分镜 Agent，负责基于剧本与图片生成镜头列表与视频计划稿。",
        ),
        PromptProfile.DYNAMIC_IMAGE: AgentPromptBundle(
            role_prompt=(
                "你是分镜 Agent（动态图片模式）。"
                "每个镜头必须含 narration_text 与 camera_motion（如 ken_burns_in），"
                "时长 3–6 秒，无需 ai_video_hint。"
            ),
            action_hint="create_shots 的 narration_text 必填；camera_motion 使用 ken_burns_* 或 pan。",
        ),
        PromptProfile.AI_VIDEO: AgentPromptBundle(
            role_prompt=(
                "你是分镜 Agent（AI 视频模式）。"
                "镜头设计需标注图生视频意图，时长受项目 videoGen 约束。"
            ),
            action_hint="create_shots 可为每镜补充 ai_video 相关描述于 narration 或备注。",
        ),
    },
    "video_agent": {
        PromptProfile.DEFAULT: AgentPromptBundle(
            role_prompt="你是视频 Agent，负责按计划稿生成 AI 视频片段并预估费用。",
        ),
        PromptProfile.AI_VIDEO: AgentPromptBundle(
            role_prompt=(
                "你是视频 Agent（AI 视频模式）。"
                "按镜头调用图生视频，load_shots 须给出准确 estimated_cost_usd。"
            ),
        ),
    },
    "tts_agent": {
        PromptProfile.DEFAULT: AgentPromptBundle(
            role_prompt="你是配音 Agent，负责提取旁白文案并合成 TTS 音频文件。",
        ),
        PromptProfile.DYNAMIC_IMAGE: AgentPromptBundle(
            role_prompt=(
                "你是配音 Agent（动态图片模式）。"
                "必须为每个分镜镜头提取旁白并合成完整音轨，不可遗漏。"
            ),
        ),
    },
    "editing_agent": {
        PromptProfile.DEFAULT: AgentPromptBundle(
            role_prompt="你是剪辑 Agent，负责收集媒体素材并合成最终成片。",
        ),
        PromptProfile.DYNAMIC_IMAGE: AgentPromptBundle(
            role_prompt=(
                "你是剪辑 Agent（动态图片模式）。"
                "合成时以图片轨道+运镜+配音为主，无需视频片段。"
            ),
        ),
        PromptProfile.AI_VIDEO: AgentPromptBundle(
            role_prompt=(
                "你是剪辑 Agent（AI 视频模式）。"
                "拼接 AI 视频片段与配音，注意镜头顺序与转场。"
            ),
        ),
    },
}


def default_role_prompt(agent_name: str) -> str:
    """返回 Agent 的 default 模式 role_prompt（兼容 definitions 引用）。"""
    profiles = AGENT_PROMPT_PROFILES.get(agent_name, {})
    bundle = profiles.get(PromptProfile.DEFAULT)
    if bundle:
        return bundle.role_prompt
    return f"你是 {agent_name}。"


def list_prompt_profiles() -> list[dict[str, str]]:
    return [
        {"id": p.value, "label": _PROFILE_LABELS[p]}
        for p in PromptProfile
    ]


_PROFILE_LABELS: dict[PromptProfile, str] = {
    PromptProfile.DEFAULT: "默认",
    PromptProfile.DYNAMIC_IMAGE: "动态图片模式",
    PromptProfile.AI_VIDEO: "AI 视频模式",
}
