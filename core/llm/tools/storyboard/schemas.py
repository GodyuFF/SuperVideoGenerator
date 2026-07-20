"""storyboard_agent 相关 action input schema。"""

from __future__ import annotations

from typing import Any

from core.llm.prompt.tools.schema_builders import (
    _OBSERVATION,
    build_frames_array_schema,
    build_shots_array_schema,
    build_video_clips_array_schema,
)
from core.llm.tools.shared.input_common import READ_ONLY_QUERY_SCHEMA

STORYBOARD_LOAD_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "observation": _OBSERVATION,
        "script_id": {
            "type": "string",
            "description": (
                "当前剧本 ID（必填）。必须与会话 project_context / 编排状态中的 "
                "script_id 一致，禁止省略或凭标题猜测。"
            ),
            "minLength": 1,
        },
    },
    "required": ["observation", "script_id"],
    "additionalProperties": True,
}

STORYBOARD_SHOTS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "observation": _OBSERVATION,
        "shots": build_shots_array_schema(require_voice=True),
    },
    "required": ["observation", "shots"],
    "additionalProperties": True,
}

STORYBOARD_FRAMES_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "observation": _OBSERVATION,
        "frames": build_frames_array_schema(),
    },
    "required": ["observation", "frames"],
    "additionalProperties": True,
}

STORYBOARD_VIDEO_CLIPS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "observation": _OBSERVATION,
        "video_clips": build_video_clips_array_schema(),
    },
    "required": ["observation", "video_clips"],
    "additionalProperties": True,
}

PERSIST_PLAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "observation": _OBSERVATION,
        "mode": {
            "type": "string",
            "enum": ["static_image", "dynamic_image", "ai_video"],
        },
        "shots": build_shots_array_schema(require_voice=True),
    },
    "required": ["observation", "shots"],
    "additionalProperties": True,
}

STORYBOARD_SCHEMAS: dict[str, dict[str, Any]] = {
    "load_context": STORYBOARD_LOAD_SCHEMA,
    "create_shots": STORYBOARD_SHOTS_SCHEMA,
    "create_frames": STORYBOARD_FRAMES_SCHEMA,
    "create_video_clips": STORYBOARD_VIDEO_CLIPS_SCHEMA,
    "persist_plan": PERSIST_PLAN_SCHEMA,
    "get_plan": READ_ONLY_QUERY_SCHEMA,
}
