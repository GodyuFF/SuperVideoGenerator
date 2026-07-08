"""主编排行动定义与任务简报（供 core.llm.master 共用）。"""

from typing import Literal

from core.models.entities import VideoStyleMode
from core.llm.prompt.registry import PromptProfile, extract_role_summary, get_agent_role_prompt

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
        "depends_on": "用户创意",
        "produces": "剧本 Markdown、文字资产",
    },
    "image_gen": {
        "title": "图片素材生成",
        "description": _step_description("image_agent"),
        "agent": "image_agent",
        "depends_on": "文字资产",
        "produces": "配图 MediaAsset",
    },
    "storyboard": {
        "title": "分镜与视频计划稿",
        "description": _step_description("storyboard_agent"),
        "agent": "storyboard_agent",
        "depends_on": "剧本、推荐已有配图",
        "produces": "VideoPlan",
    },
    "video_gen": {
        "title": "AI 视频生成",
        "description": _step_description("video_agent"),
        "agent": "video_agent",
        "depends_on": "VideoPlan",
        "produces": "视频 MediaAsset",
    },
    "tts_gen": {
        "title": "配音生成",
        "description": _step_description("tts_agent"),
        "agent": "tts_agent",
        "depends_on": "VideoPlan 或旁白文本",
        "produces": "配音 MediaAsset",
    },
    "edit_compose": {
        "title": "剪辑合成",
        "description": _step_description("editing_agent"),
        "agent": "editing_agent",
        "depends_on": "VideoPlan、配图、TTS",
        "produces": "EditTimeline、成片 MP4",
    },
}

_STYLE_LABELS: dict[VideoStyleMode, str] = {
    VideoStyleMode.DYNAMIC_IMAGE: "动态图文模式",
    VideoStyleMode.DYNAMIC_COMIC: "动态漫画模式",
    VideoStyleMode.AI_VIDEO: "AI 视频模式",
}

_TASK_BRIEFS_DEFAULT: dict[str, str] = {
    "script_design": (
        "根据主编排下发的创意摘要，生成完整剧本 Markdown 与文字资产"
        "（剧情段落、人物、道具、场景）。"
    ),
    "image_gen": "根据已生成的文字资产（人物、道具、场景）批量生成或搜索对应图片素材。",
    "storyboard": "基于剧本与图片素材生成分镜列表与视频计划稿（镜头、运镜、旁白）。",
    "video_gen": "按视频计划稿中的镜头顺序生成 AI 视频片段。",
    "tts_gen": "为分镜旁白文案生成配音音频文件。",
    "edit_compose": "将图片/视频片段与配音合成为最终成片。",
}

_STYLE_TASK_BRIEFS: dict[VideoStyleMode, dict[str, str]] = {
    VideoStyleMode.DYNAMIC_IMAGE: {
        "script_design": (
            "【动态图文】设计剧本与文字资产：剧情段落、角色、道具、场景；"
            "面向科普/汇报/讲解类视频，文案清晰、结构分段。"
        ),
        "image_gen": (
            "【动态图文】为缺图的角色、道具、场景文字资产批量生成或搜索配图；"
            "构图适合 Ken Burns 运镜，留出主体安全区。"
        ),
        "storyboard": (
            "【动态图文】生成分镜与视频计划稿：镜头时长、运镜、旁白文案；"
            "以静态图+运镜为主，无需 AI 视频片段。"
        ),
        "edit_compose": "【动态图文】将图片运镜片段与配音合成为讲解类成片。",
    },
    VideoStyleMode.DYNAMIC_COMIC: {
        "script_design": (
            "【动态漫画】设计剧本与文字资产：剧情、角色、道具、场景；"
            "对白与旁白适合漫画分格呈现。"
        ),
        "image_gen": (
            "【动态漫画】为角色/道具/场景生成或搜索漫画风格配图；"
            "保持统一画风，适合分格与特写切换。"
        ),
        "storyboard": (
            "【动态漫画】生成分镜与视频计划稿：分格节奏、镜头切换、旁白/对白；"
            "以漫画画面+运镜为主。"
        ),
        "edit_compose": "【动态漫画】将漫画分格运镜与配音合成为成片。",
    },
    VideoStyleMode.AI_VIDEO: {
        "video_gen": "【AI 视频】按视频计划稿逐镜头调用视频生成 API。",
        "edit_compose": "【AI 视频】将 AI 视频片段与配音合成为成片。",
    },
}

TASK_BRIEFS: dict[str, str] = dict(_TASK_BRIEFS_DEFAULT)


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
    "tool_list_assets": "调用工具 · 查询资产清单",
    "tool_read_webpage": "调用工具 · 读取网页",
}


def action_kind(action: str) -> str:
    """返回行动类型：delegate | tool | finish | ask_user。"""
    if action == "finish":
        return "finish"
    if action == "ask_user_question":
        return "ask_user"
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


def style_mode_label(style_mode: VideoStyleMode) -> str:
    """返回视频风格中文名。"""
    return _STYLE_LABELS.get(style_mode, style_mode.value)


def uses_image_text_pipeline(style_mode: VideoStyleMode) -> bool:
    """动态图文/漫画模式：文字设计 → 图片 → 分镜 → 配音 → 剪辑（无 video_gen）。"""
    return style_mode in (
        VideoStyleMode.DYNAMIC_IMAGE,
        VideoStyleMode.DYNAMIC_COMIC,
    )


def task_brief_for_step(step_type: str, style_mode: VideoStyleMode) -> str:
    """按视频风格返回步骤任务简报。"""
    overrides = _STYLE_TASK_BRIEFS.get(style_mode, {})
    return overrides.get(step_type, _TASK_BRIEFS_DEFAULT.get(step_type, step_type))


def pipeline_for_style(style_mode: VideoStyleMode) -> list[str]:
    base = [
        "delegate_script_design",
        "delegate_storyboard",
        "delegate_image_gen",
    ]
    if style_mode == VideoStyleMode.AI_VIDEO:
        base.append("delegate_video_gen")
    base.extend(["delegate_tts_gen", "delegate_edit_compose"])
    return base
