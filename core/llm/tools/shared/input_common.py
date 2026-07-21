"""各域 tool input schema 共用片段。"""

from __future__ import annotations

from typing import Any

from core.llm.prompt.tools.schema_builders import (
    _OBSERVATION,
    build_read_only_query_schema,
)

FINISH_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary": {
            "type": "string",
            "description": "可选结束摘要",
        },
    },
    "additionalProperties": False,
}

REACT_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "note": {
            "type": "string",
            "description": "可选补充说明",
        },
    },
    "additionalProperties": True,
}

OBSERVATION_ONLY: dict[str, Any] = {
    "type": "object",
    "properties": {"observation": _OBSERVATION},
    "required": ["observation"],
    "additionalProperties": True,
}

PLAN_TRACKING_PROPERTIES: dict[str, Any] = {
    "plan_status": {
        "type": "string",
        "description": "本轮执行进度与关键结论（中文，1-5 句）",
    },
    "remaining_plan": {
        "type": "array",
        "items": {"type": "string"},
        "description": "后续待执行步骤或子任务（按优先级排列）",
    },
}

PLAN_TRACKING_REQUIRED = ["plan_status", "remaining_plan"]


def merge_plan_tracking(schema: dict[str, Any], *, required: bool = False) -> dict[str, Any]:
    """在既有 schema 上合并 plan_status / remaining_plan（默认可选，显式 update_plan/replan 才必填）。"""
    merged = dict(schema)
    props = dict(merged.get("properties") or {})
    props.update(PLAN_TRACKING_PROPERTIES)
    merged["properties"] = props
    required_fields = list(merged.get("required") or [])
    if required:
        for key in PLAN_TRACKING_REQUIRED:
            if key not in required_fields:
                required_fields.append(key)
    else:
        required_fields = [k for k in required_fields if k not in PLAN_TRACKING_REQUIRED]
    merged["required"] = required_fields
    merged["additionalProperties"] = True
    return merged


READ_ONLY_QUERY_SCHEMA = merge_plan_tracking(
    build_read_only_query_schema(), required=False
)

DELETE_ASSET_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "observation": _OBSERVATION,
        "asset_id": {"type": "string", "description": "要删除的资产 ID"},
    },
    "required": ["observation", "asset_id"],
    "additionalProperties": True,
}


def update_asset_schema(content_schema: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "observation": _OBSERVATION,
            "asset_id": {
                "type": "string",
                "description": "目标资产 ID（须先 list_text_assets 获取）",
            },
            "asset_name": {
                "type": "string",
                "description": "可选：重命名资产",
            },
            "content": content_schema,
        },
        "required": ["observation", "asset_id", "content"],
        "additionalProperties": True,
    }
