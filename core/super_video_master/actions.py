"""主编排行动定义与任务简报（供 master_react 共用）。"""

from typing import Literal

from core.models.entities import VideoStyleMode

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

STEP_META: dict[str, dict[str, str]] = {
    "script_design": {
        "title": "剧本与文字资产设计",
        "description": "生成剧情、角色、场景等文字资产",
        "agent": "script_agent",
    },
    "image_gen": {
        "title": "图片素材生成",
        "description": "为文字资产生成图片",
        "agent": "image_agent",
    },
    "storyboard": {
        "title": "分镜与视频计划稿",
        "description": "生成镜头列表与运镜",
        "agent": "storyboard_agent",
    },
    "video_gen": {
        "title": "AI 视频生成",
        "description": "按镜头调用视频生成 API",
        "agent": "video_agent",
    },
    "tts_gen": {
        "title": "配音生成",
        "description": "TTS 生成旁白音频",
        "agent": "tts_agent",
    },
    "edit_compose": {
        "title": "剪辑合成",
        "description": "合成最终成片",
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
