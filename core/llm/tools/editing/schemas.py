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
from core.llm.tools.editing.opencut_tools import OPEN_CUT_TOOL_SCHEMAS
from core.llm.tools.shared.input_common import OBSERVATION_ONLY, READ_ONLY_QUERY_SCHEMA, merge_plan_tracking

COMPOSE_FINAL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "observation": _OBSERVATION,
        "timeline_id": {"type": "string", "description": "剪辑计划稿 ID"},
        "final_url": {"type": "string", "description": "成片 URL（无 API 时可省略）"},
        "url": {"type": "string"},
        "skip_subtitles": {
            "type": "boolean",
            "description": "为 true 时导出纯画面+配音，不回填 TTS 字幕轨、不烧录字幕",
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
        "skip_subtitle_enrich": {
            "type": "boolean",
            "description": "为 true 时跳过从 TTS subtitle_cues 自动补齐 subtitle 轨",
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

ANALYZE_EDIT_TIMELINE_SCHEMA: dict[str, Any] = merge_plan_tracking(
    {
        "type": "object",
        "properties": {
            "observation": _OBSERVATION,
            "start_ms": {
                "type": "integer",
                "description": "查询区间起点（毫秒）；读取某时间段剪辑详情时须指定",
            },
            "end_ms": {
                "type": "integer",
                "description": "查询区间终点（毫秒）；读取某时间段剪辑详情时须指定",
            },
            "tracks": {
                "type": "array",
                "items": {"type": "string", "enum": ["video", "audio", "subtitle"]},
                "description": "可选：仅分析指定轨道",
            },
            "layer_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "可选：仅分析指定视频层",
            },
            "include_hints": {
                "type": "boolean",
                "description": "是否输出 optimization_hints，默认 true",
            },
            "include_shot_alignment": {
                "type": "boolean",
                "description": "是否输出每镜对齐信息，默认 true",
            },
            "include_analysis": {
                "type": "boolean",
                "description": "是否输出 gaps/overlaps/hints/alignment 等结构分析；仅读 clip 详情时可设 false 以减 token",
            },
        },
        "required": ["observation"],
        "additionalProperties": True,
    }
)

EDITING_SCHEMAS: dict[str, dict[str, Any]] = {
    "load_edit_context": READ_ONLY_QUERY_SCHEMA,
    "plan_edit_timeline": PLAN_EDIT_TIMELINE_SCHEMA,
    "validate_edit_assets": READ_ONLY_QUERY_SCHEMA,
    "report_missing_assets": REPORT_MISSING_SCHEMA,
    "get_edit_timeline": READ_ONLY_QUERY_SCHEMA,
    "analyze_edit_timeline": ANALYZE_EDIT_TIMELINE_SCHEMA,
    "gather_media": dict(OBSERVATION_ONLY),
    "compose_final": COMPOSE_FINAL_SCHEMA,
    "list_final": READ_ONLY_QUERY_SCHEMA,
}

# OpenCut 精确剪辑工具 schema（合并 plan_status / remaining_plan）
for _action, _schema in OPEN_CUT_TOOL_SCHEMAS.items():
    if _action in EDITING_SCHEMAS:
        continue
    if _action in ("get_edit_timeline", "get_export_status"):
        EDITING_SCHEMAS[_action] = merge_plan_tracking(dict(_schema))
    elif _action == "export_timeline":
        EDITING_SCHEMAS[_action] = merge_plan_tracking(dict(_schema))
    else:
        EDITING_SCHEMAS[_action] = merge_plan_tracking(dict(_schema))
