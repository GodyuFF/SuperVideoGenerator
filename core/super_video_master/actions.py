"""主编排行动定义与任务简报（供 master_react 共用）。"""

from typing import Literal

from core.models.entities import VideoStyleMode
from core.prompt.registry import PromptProfile, extract_role_summary, get_agent_role_prompt

MasterActionName = Literal[
    "delegate_script_design",
    "delegate_image_gen",
    "delegate_storyboard",
    "delegate_video_gen",
    "delegate_tts_gen",
    "delegate_edit_compose",
    "finish",
]

ACTION_TO_STEP: dict[str, str] = {
    "delegate_script_design": "script_design",
    "delegate_image_gen": "image_gen",
    "delegate_storyboard": "storyboard",
    "delegate_video_gen": "video_gen",
    "delegate_tts_gen": "tts_gen",
    "delegate_edit_compose": "edit_compose",
}


def _step_description(agent_name: str) -> str:
    """从 Agent 固定 role 提示词提取一步骤摘要。"""
    role = get_agent_role_prompt(agent_name, PromptProfile.DEFAULT)
    return extract_role_summary(role) or agent_name


STEP_META: dict[str, dict[str, str]] = {
    "script_design": {
        "title": "剧本与文字资产设计",
        "description": _step_description("script_agent"),
        "agent": "script_agent",
    },
    "image_gen": {
        "title": "图片素材生成",
        "description": _step_description("image_agent"),
        "agent": "image_agent",
    },
    "storyboard": {
        "title": "分镜与视频计划稿",
        "description": _step_description("storyboard_agent"),
        "agent": "storyboard_agent",
    },
    "video_gen": {
        "title": "AI 视频生成",
        "description": _step_description("video_agent"),
        "agent": "video_agent",
    },
    "tts_gen": {
        "title": "配音生成",
        "description": _step_description("tts_agent"),
        "agent": "tts_agent",
    },
    "edit_compose": {
        "title": "剪辑合成",
        "description": _step_description("editing_agent"),
        "agent": "editing_agent",
    },
}

TASK_BRIEFS: dict[str, str] = {
    "script_design": (
        "根据主编排下发的创意摘要，生成完整剧本 Markdown 与文字资产"
        "（剧情段落、人物、场景）。"
    ),
    "image_gen": "根据已生成的文字资产（人物、场景）生成对应图片素材。",
    "storyboard": "基于剧本与图片素材生成分镜列表与视频计划稿（镜头、运镜、旁白）。",
    "video_gen": "按视频计划稿中的镜头顺序生成 AI 视频片段。",
    "tts_gen": "为分镜旁白文案生成配音音频文件。",
    "edit_compose": "将图片/视频片段与配音合成为最终成片。",
}


ACTION_LABELS: dict[str, str] = {
    "delegate_script_design": "委派 · 剧本与文字资产设计",
    "delegate_image_gen": "委派 · 图片素材生成",
    "delegate_storyboard": "委派 · 分镜与视频计划稿",
    "delegate_video_gen": "委派 · AI 视频生成",
    "delegate_tts_gen": "委派 · 配音生成",
    "delegate_edit_compose": "委派 · 剪辑合成",
    "finish": "结束编排",
}

TOOL_LABELS: dict[str, str] = {
    "tool_get_plan_summary": "调用工具 · 查询计划摘要",
    "tool_list_assets": "调用工具 · 统计资产",
    "tool_estimate_video_cost": "调用工具 · 估算视频费用",
}


def action_kind(action: str) -> str:
    """返回行动类型：delegate | tool | finish。"""
    if action == "finish":
        return "finish"
    if action.startswith("tool_"):
        return "tool"
    if action.startswith("delegate_"):
        return "delegate"
    return "unknown"


def action_label(action: str) -> str:
    """返回行动的中文展示名。"""
    if action in ACTION_LABELS:
        return ACTION_LABELS[action]
    if action in TOOL_LABELS:
        return TOOL_LABELS[action]
    return action


def pipeline_for_style(style_mode: VideoStyleMode) -> list[str]:
    base = [
        "delegate_script_design",
        "delegate_image_gen",
        "delegate_storyboard",
    ]
    if style_mode == VideoStyleMode.AI_VIDEO:
        base.append("delegate_video_gen")
    base.extend(["delegate_tts_gen", "delegate_edit_compose"])
    return base
