"""主编排行动定义与任务简报（供 core.llm.master 共用）。"""

from typing import Literal

from core.guards.script_style import normalize_style_mode_id
from core.models.entities import VideoStyleMode
from core.llm.prompt.registry import PromptProfile, extract_role_summary, get_agent_role_prompt

MasterActionName = Literal[
    "delegate_agent",
    "finish",
]

ACTION_LABELS: dict[str, str] = {
    "delegate_agent": "委派 · 子 Agent",
    "finish": "结束编排",
}

TOOL_LABELS: dict[str, str] = {
    "tool_get_plan_summary": "调用工具 · 查询计划摘要",
    "tool_list_assets": "调用工具 · 查询资产清单",
    "tool_read_webpage": "调用工具 · 读取网页",
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
        "depends_on": "待生图文字资产（角色/道具/场景或 frame，无固定先后）",
        "produces": "配图 MediaAsset",
    },
    "storyboard": {
        "title": "分镜与视频计划稿",
        "description": _step_description("storyboard_agent"),
        "agent": "storyboard_agent",
        "depends_on": "剧本与文字资产（推荐角色/场景已有配图）",
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
    "shot_detail": {
        "title": "分镜复核",
        "description": _step_description("storyboard_refine_agent"),
        "agent": "storyboard_refine_agent",
        "depends_on": "VideoPlan、配图、TTS；AI 视频另须 video_gen（剪辑前最后一步）",
        "produces": "复核后的 VideoPlan、review_note、结构性调整",
    },
    "edit_compose": {
        "title": "剪辑合成",
        "description": _step_description("editing_agent"),
        "agent": "editing_agent",
        "depends_on": "分镜复核完成后的 VideoPlan、配图/视频、TTS",
        "produces": "EditTimeline、成片 MP4",
    },
}

_STYLE_LABELS: dict[VideoStyleMode, str] = {
    VideoStyleMode.STORYBOOK: "故事书模式",
    VideoStyleMode.AI_VIDEO: "AI 视频模式",
    VideoStyleMode.FRAME_I2V: "画面图生视频",
}

_TASK_BRIEFS_DEFAULT: dict[str, str] = {
    "script_design": (
        "根据主编排下发的创意摘要，生成完整剧本 Markdown 与文字资产"
        "（剧情段落、人物、道具、场景）。"
    ),
    "image_gen": "根据分镜创建的 frame 文字资产及角色/道具/场景批量生成或搜索对应图片素材。",
    "storyboard": (
        "基于剧本生成分镜列表与 VideoPlan：镜内 element_refs 关联角色/场景/道具；"
        "故事书模式 create_frames 为每子镜创建 frame；AI 视频模式 create_video_clips 为每子镜创建 video_clip 文字资产。"
    ),
    "video_gen": (
        "按 storyboard_agent 已创建的 video_clip 文字资产扫描并生成 AI 视频 mp4；"
        "不决定资产创建与镜内关联（由 storyboard_agent 负责）。"
    ),
    "tts_gen": "为分镜旁白文案生成配音音频文件。",
    "shot_detail": (
        "在配图与 TTS（AI 视频另含已生成视频）就绪后，对比规划与实测时长，"
        "复核并重排分镜；本步为剪辑前最后一步。"
    ),
    "edit_compose": "在分镜复核完成后，将图片/视频片段与配音规划为剪辑时间轴。",
}

_STYLE_TASK_BRIEFS: dict[VideoStyleMode, dict[str, str]] = {
    VideoStyleMode.STORYBOOK: {
        "script_design": (
            "【故事书】设计剧本与文字资产：剧情段落、角色、道具、场景；"
            "面向科普/汇报/讲解类视频，文案清晰、结构分段。"
        ),
        "image_gen": (
            "【故事书】为缺图的角色、道具、场景及 frame 画面文字资产批量生成或搜索配图；"
            "必须保证每个分镜的 frame 画面资产完成生图；构图适合 Ken Burns 运镜，留出主体安全区。"
        ),
        "storyboard": (
            "【故事书】生成分镜与视频计划稿：镜头时长、运镜、旁白文案；"
            "create_frames 为每个子镜创建剧本画面 frame 资产（必需）；以静态图+运镜为主，无需 AI 视频片段。"
        ),
        "shot_detail": (
            "【故事书】配图与 TTS 后分镜复核（剪辑前最后一步）：同步实测时长与句级字幕，"
            "完善每镜 display_instructions 与 camera_motion_refined。"
        ),
        "edit_compose": "【故事书】分镜复核完成后，将画面资产运镜片段与配音规划为剪辑时间轴。",
    },
    VideoStyleMode.AI_VIDEO: {
        "storyboard": (
            "【AI 视频】生成分镜与 VideoPlan：create_shots 填写 element_refs 与 sub_shots；"
            "create_video_clips 为每子镜创建 video_clip（含 video_prompt 与参考关联）；"
            "勿 create_frames。"
        ),
        "video_gen": (
            "【AI 视频】scan_video_clips → generate_video_clips："
            "仅将已有 video_clip 文字资产生成为 mp4 并回填 media_id；"
            "须在分镜复核之前完成。"
        ),
        "shot_detail": (
            "【AI 视频】video + TTS 后分镜复核（剪辑前最后一步）："
            "对齐实测视频/音频时长，完善每镜展示说明；禁止在复核后再生视频。"
        ),
        "edit_compose": "【AI 视频】分镜复核完成后，将 AI 视频片段与配音规划为剪辑时间轴。",
    },
    VideoStyleMode.FRAME_I2V: {
        "script_design": (
            "【画面图生视频】设计剧本与 character/prop/空镜；旁白带视觉节拍，scene 仅背景板。"
        ),
        "storyboard": (
            "【画面图生视频】create_shots → create_frames（静态合成）→ "
            "create_video_clips（动态 prompt + source_frame 绑定）。"
        ),
        "image_gen": (
            "【画面图生视频】两阶段生图：实体参考图 → 全部 frame（I2V 首帧构图）。"
        ),
        "video_gen": (
            "【画面图生视频】以 frame 为唯一图生源生成 mp4；video_clip 仅提供 motion prompt。"
        ),
        "shot_detail": (
            "【画面图生视频】frame 配图 + AI 视频 + TTS 后复核（剪辑前最后一步）。"
        ),
        "edit_compose": "【画面图生视频】AI 视频片段与配音规划时间轴。",
    },
}

TASK_BRIEFS: dict[str, str] = dict(_TASK_BRIEFS_DEFAULT)


def action_kind(action: str) -> str:
    """返回行动类型：delegate | tool | finish | ask_user。"""
    if action == "finish":
        return "finish"
    if action == "ask_user_question":
        return "ask_user"
    if action.startswith("tool_"):
        return "tool"
    if action == "delegate_agent":
        return "delegate"
    return "unknown"


def action_label(action: str, *, agent_id: str | None = None) -> str:
    """返回行动的中文展示名；委派可附带 agent_id。"""
    if action == "delegate_agent" and agent_id:
        from core.llm.agent.agent_registry import resolve_display_name

        try:
            name = resolve_display_name(agent_id)
            return f"委派 · {name}"
        except ValueError:
            return f"委派 · {agent_id}"
    if action in ACTION_LABELS:
        return ACTION_LABELS[action]
    if action in TOOL_LABELS:
        return TOOL_LABELS[action]
    return action


def style_mode_label(style_mode: VideoStyleMode | str) -> str:
    """返回视频风格中文名。"""
    sid = normalize_style_mode_id(style_mode) or str(style_mode)
    try:
        enum_mode = VideoStyleMode(sid)
        return _STYLE_LABELS.get(enum_mode, sid)
    except ValueError:
        return sid


def uses_frame_i2v_pipeline(style_mode: VideoStyleMode | str) -> bool:
    """画面图生视频模式：frame + video_clip 双资产，I2V 只认 frame。"""
    sid = normalize_style_mode_id(style_mode)
    return sid == VideoStyleMode.FRAME_I2V.value


def uses_image_text_pipeline(style_mode: VideoStyleMode | str) -> bool:
    """图文管线：故事书/画面图生视频需 frame 配图与 voice 必填。"""
    sid = normalize_style_mode_id(style_mode)
    return sid in (VideoStyleMode.STORYBOOK.value, VideoStyleMode.FRAME_I2V.value)


def uses_ai_video_pipeline(style_mode: VideoStyleMode | str) -> bool:
    """AI 视频管线：需 video_clip 与 video_gen（含纯 ai_video 与 frame_i2v）。"""
    sid = normalize_style_mode_id(style_mode)
    return sid in (VideoStyleMode.AI_VIDEO.value, VideoStyleMode.FRAME_I2V.value)


_STORYBOARD_PIPELINE_ORDER = (
    "load_context",
    "create_shots",
    "create_frames",
    "create_video_clips",
    "persist_plan",
)


def filter_storyboard_pipeline_actions(
    actions: list[str],
    style_mode: VideoStyleMode | str | None,
) -> list[str]:
    """按视频风格过滤分镜 Agent 流水线（frame_i2v 保留双轨，其余二选一）。"""
    ordered = [a for a in _STORYBOARD_PIPELINE_ORDER if a in actions]
    extras = [a for a in actions if a not in _STORYBOARD_PIPELINE_ORDER]
    if uses_frame_i2v_pipeline(style_mode or ""):
        pass
    elif uses_ai_video_pipeline(style_mode or ""):
        ordered = [a for a in ordered if a != "create_frames"]
    else:
        ordered = [a for a in ordered if a != "create_video_clips"]
    return ordered + extras


_VIDEO_PIPELINE_ORDER = (
    "generate_video_clips",
    "generate_from_timeline",
)


def filter_video_pipeline_actions(actions: list[str]) -> list[str]:
    """视频 Agent 主流水线：generate_video_clips（legacy action 与只读 scan 不进入 pipeline）。"""
    legacy = frozenset({"load_shots", "generate_clips", "scan_video_clips"})
    ordered = [a for a in _VIDEO_PIPELINE_ORDER if a in actions]
    extras = [a for a in actions if a not in _VIDEO_PIPELINE_ORDER and a not in legacy]
    return ordered + extras


def task_brief_for_step(step_type: str, style_mode: VideoStyleMode | str) -> str:
    """按视频风格返回步骤任务简报。"""
    sid = normalize_style_mode_id(style_mode)
    try:
        enum_mode = VideoStyleMode(sid) if sid else VideoStyleMode.STORYBOOK
    except ValueError:
        enum_mode = VideoStyleMode.STORYBOOK
    overrides = _STYLE_TASK_BRIEFS.get(enum_mode, {})
    return overrides.get(step_type, _TASK_BRIEFS_DEFAULT.get(step_type, step_type))
