"""return_to_master 工具 input schema。"""

from __future__ import annotations

from typing import Any

RETURN_TO_MASTER_REASONS = (
    "missing_upstream",
    "needs_user_input",
    "blocked",
    "partial_done",
)

RETURN_TO_MASTER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "reason": {
            "type": "string",
            "enum": list(RETURN_TO_MASTER_REASONS),
            "description": "返回主编排的原因分类",
        },
        "observation": {
            "type": "string",
            "description": "给主编排的自然语言摘要（必填）",
        },
        "missing_items": {
            "type": "array",
            "items": {"type": "object"},
            "description": "结构化缺失项（可选）",
        },
        "suggested_agent_ids": {
            "type": "array",
            "items": {"type": "string"},
            "description": "建议主编排下一步委派的 agent_id（可选）",
        },
        "resume_hint": {
            "type": "string",
            "description": "上游补全后如何重新委派本 Agent（可选）",
        },
    },
    "required": ["reason", "observation"],
    "additionalProperties": False,
}
