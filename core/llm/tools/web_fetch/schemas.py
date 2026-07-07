"""read_webpage tool 的 input/output JSON Schema。"""

from __future__ import annotations

from typing import Any

from core.llm.prompt.tools.schema_builders import _OBSERVATION, _object_schema
from core.llm.tools.shared.input_common import merge_plan_tracking


def read_webpage_input_schema() -> dict[str, Any]:
    """行动执行阶段：observation + url。"""
    return _object_schema(
        {
            "observation": _OBSERVATION,
            "url": {
                "type": "string",
                "description": "要读取的网页 URL（仅 http/https）",
            },
            "max_chars": {
                "type": "integer",
                "description": "正文最大字符数（默认 8000）",
                "minimum": 500,
                "maximum": 50000,
            },
            "note": {
                "type": "string",
                "description": "可选说明",
            },
        },
        required=["observation", "url"],
        description="读取网页正文（只读）",
        additional_properties=True,
    )


def read_webpage_react_input_schema(*, for_master: bool = False) -> dict[str, Any]:
    """ReAct 决策阶段 schema。"""
    required = ["url"] if for_master else ["observation", "url"]
    base = _object_schema(
        {
            "observation": _OBSERVATION,
            "url": {
                "type": "string",
                "description": "要读取的网页 URL（仅 http/https）",
            },
            "max_chars": {
                "type": "integer",
                "description": "正文最大字符数（默认 8000）",
                "minimum": 500,
                "maximum": 50000,
            },
            "note": {
                "type": "string",
                "description": "可选说明",
            },
        },
        required=required,
        additional_properties=True,
    )
    if for_master:
        return merge_plan_tracking(base)
    return base


def read_webpage_output_schema() -> dict[str, Any]:
    return _object_schema(
        {
            "url": {"type": "string"},
            "title": {"type": "string"},
            "content": {"type": "string"},
            "truncated": {"type": "boolean"},
            "content_length": {"type": "integer"},
            "extraction_method": {"type": "string"},
            "valid": {"type": "boolean"},
        },
        required=["url", "title", "content", "truncated", "valid"],
        additional_properties=False,
    )
