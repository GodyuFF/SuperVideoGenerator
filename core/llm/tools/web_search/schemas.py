"""web_search tool 的 input/output JSON Schema。"""

from __future__ import annotations

from typing import Any

from core.llm.tools.shared.input_common import merge_plan_tracking


def _object_schema(
    properties: dict[str, Any],
    *,
    required: list[str] | None = None,
    additional_properties: bool = False,
) -> dict[str, Any]:
    """组装 object 类型 JSON Schema。"""
    out: dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "additionalProperties": additional_properties,
    }
    if required:
        out["required"] = required
    return out


def web_search_input_schema() -> dict[str, Any]:
    """领域参数 schema（不含 ReAct plan 跟踪字段）。"""
    return _object_schema(
        {
            "query": {
                "type": "string",
                "description": "搜索关键词或自然语言问题",
                "minLength": 1,
            },
            "max_results": {
                "type": "integer",
                "description": "返回条数上限（1–20，默认 5）",
                "minimum": 1,
                "maximum": 20,
                "default": 5,
            },
            "observation": {
                "type": "string",
                "description": "给 ReAct 循环的简短观察说明（注册到 Agent 时使用）",
            },
        },
        required=["query"],
        # 允许 plan_status 等 ReAct 公共字段透传；完整 required 见 web_search_react_input_schema
        additional_properties=True,
    )


def web_search_react_input_schema() -> dict[str, Any]:
    """ReAct / Registry 完整输入 schema（含 observation 与 plan 跟踪）。"""
    base = web_search_input_schema()
    props = dict(base.get("properties") or {})
    return merge_plan_tracking(
        {
            "type": "object",
            "properties": props,
            "required": ["query", "observation"],
            "additionalProperties": True,
        }
    )


def web_search_output_schema() -> dict[str, Any]:
    result_item = _object_schema(
        {
            "title": {"type": "string"},
            "url": {"type": "string"},
            "snippet": {"type": "string"},
            "source": {"type": "string"},
        },
        required=["title", "url"],
    )
    return _object_schema(
        {
            "query": {"type": "string"},
            "provider": {"type": "string"},
            "count": {"type": "integer"},
            "results": {
                "type": "array",
                "items": result_item,
            },
        },
        required=["query", "provider", "count", "results"],
    )
