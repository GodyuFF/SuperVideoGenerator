"""web_search tool 的 input/output JSON Schema（供未来 Registry 注册）。"""

from __future__ import annotations

from typing import Any


def _object_schema(
    properties: dict[str, Any],
    *,
    required: list[str] | None = None,
    additional_properties: bool = False,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "additionalProperties": additional_properties,
    }
    if required:
        out["required"] = required
    return out


def web_search_input_schema() -> dict[str, Any]:
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
