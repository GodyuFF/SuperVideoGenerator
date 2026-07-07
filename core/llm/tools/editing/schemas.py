"""editing_agent 相关 action input schema。"""

from __future__ import annotations

from typing import Any

from core.llm.prompt.tools.schema_builders import (
    _OBSERVATION,
    build_video_plan_shot_schema,
)
from core.llm.tools.shared.edit_timeline_schema import (
    EDIT_TIMELINE_TRACKS_SCHEMA,
    EDIT_VIDEO_LAYERS_SCHEMA,
)
from core.llm.tools.shared.input_common import OBSERVATION_ONLY, READ_ONLY_QUERY_SCHEMA

COMPOSE_FINAL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "observation": _OBSERVATION,
        "timeline_id": {"type": "string", "description": "剪辑计划稿 ID"},
        "final_url": {"type": "string", "description": "成片 URL（无 API 时可省略）"},
        "url": {"type": "string"},
        "timeline": {
            "type": "array",
            "items": build_video_plan_shot_schema(),
            "description": "legacy：镜头数组；优先使用 timeline_id",
        },
    },
    "required": ["observation"],
    "additionalProperties": True,
}

PLAN_EDIT_TIMELINE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "observation": _OBSERVATION,
        "mode": {
            "type": "string",
            "enum": ["create", "merge", "replace"],
            "description": "create=新建；merge=保留用户 clip 补缺失；replace=全量替换",
        },
        "tracks": EDIT_TIMELINE_TRACKS_SCHEMA,
        "video_layers": EDIT_VIDEO_LAYERS_SCHEMA,
        "timeline": {
            "type": "object",
            "properties": {
                "duration_ms": {"type": "integer"},
                "tracks": EDIT_TIMELINE_TRACKS_SCHEMA,
                "video_layers": EDIT_VIDEO_LAYERS_SCHEMA,
            },
        },
    },
    "required": ["observation"],
    "additionalProperties": True,
}

REPORT_MISSING_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "observation": _OBSERVATION,
        "missing_items": {
            "type": "array",
            "items": {"type": "object"},
            "description": "可选：补充缺失说明",
        },
    },
    "required": ["observation"],
    "additionalProperties": True,
}

EDITING_SCHEMAS: dict[str, dict[str, Any]] = {
    "load_edit_context": READ_ONLY_QUERY_SCHEMA,
    "plan_edit_timeline": PLAN_EDIT_TIMELINE_SCHEMA,
    "validate_edit_assets": READ_ONLY_QUERY_SCHEMA,
    "report_missing_assets": REPORT_MISSING_SCHEMA,
    "get_edit_timeline": READ_ONLY_QUERY_SCHEMA,
    "gather_media": dict(OBSERVATION_ONLY),
    "compose_final": COMPOSE_FINAL_SCHEMA,
    "list_final": READ_ONLY_QUERY_SCHEMA,
}
