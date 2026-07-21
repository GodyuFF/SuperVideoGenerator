"""显式计划工具 update_plan / replan 的 input schema。"""

from __future__ import annotations

from typing import Any

from core.llm.prompt.tools.schema_builders import _OBSERVATION
from core.llm.tools.shared.input_common import PLAN_TRACKING_PROPERTIES

UPDATE_PLAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "observation": _OBSERVATION,
        **PLAN_TRACKING_PROPERTIES,
    },
    "required": ["observation", "plan_status", "remaining_plan"],
    "additionalProperties": True,
}

_REPLAN_OP_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "op": {
            "type": "string",
            "enum": ["set_status", "skip", "reset_pending", "set_title"],
            "description": "步骤操作类型",
        },
        "step_id": {"type": "string", "description": "目标步骤 ID（优先）"},
        "step_type": {"type": "string", "description": "目标步骤 type（无 step_id 时）"},
        "status": {
            "type": "string",
            "enum": [
                "pending",
                "running",
                "completed",
                "failed",
                "skipped",
                "awaiting_confirmation",
                "paused",
            ],
            "description": "set_status 时的新状态",
        },
        "title": {"type": "string", "description": "set_title 时的新标题"},
    },
    "required": ["op"],
    "additionalProperties": True,
}

_UPSERT_STEP_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "type": {"type": "string", "description": "步骤 type（如 storyboard）"},
        "title": {"type": "string", "description": "步骤标题"},
        "agent": {"type": "string", "description": "负责的子 Agent 名"},
        "description": {"type": "string"},
        "status": {
            "type": "string",
            "enum": [
                "pending",
                "running",
                "completed",
                "failed",
                "skipped",
                "awaiting_confirmation",
                "paused",
            ],
        },
    },
    "required": ["type", "title", "agent"],
    "additionalProperties": True,
}

REPLAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "observation": _OBSERVATION,
        "reason": {
            "type": "string",
            "description": "重规划原因（中文）",
        },
        **PLAN_TRACKING_PROPERTIES,
        "goal": {
            "type": "string",
            "description": "可选：覆盖计划目标",
        },
        "ops": {
            "type": "array",
            "items": _REPLAN_OP_SCHEMA,
            "description": "对已有步骤的操作列表",
        },
        "upsert_steps": {
            "type": "array",
            "items": _UPSERT_STEP_SCHEMA,
            "description": "追加尚未存在的步骤骨架",
        },
    },
    "required": ["observation", "reason", "plan_status", "remaining_plan"],
    "additionalProperties": True,
}
