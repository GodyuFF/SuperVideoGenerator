"""video_agent 相关 action input schema。"""

from __future__ import annotations

from typing import Any

from core.llm.prompt.tools.schema_builders import _OBSERVATION
from core.llm.tools.shared.input_common import READ_ONLY_QUERY_SCHEMA
from core.llm.tools.storyboard.schemas import STORYBOARD_LOAD_SCHEMA

VIDEO_CLIPS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "observation": _OBSERVATION,
        "clips": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "shot_id": {"type": "string"},
                    "url": {"type": "string"},
                    "duration_ms": {"type": "integer"},
                },
            },
        },
    },
    "required": ["observation"],
    "additionalProperties": True,
}

VIDEO_FROM_TIMELINE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "observation": _OBSERVATION,
        "timeline_id": {"type": "string"},
        "placeholder_url": {"type": "string"},
    },
    "required": ["observation"],
    "additionalProperties": True,
}

VIDEO_SCHEMAS: dict[str, dict[str, Any]] = {
    "load_shots": STORYBOARD_LOAD_SCHEMA,
    "generate_clips": VIDEO_CLIPS_SCHEMA,
    "generate_from_timeline": VIDEO_FROM_TIMELINE_SCHEMA,
    "list_videos": READ_ONLY_QUERY_SCHEMA,
}
