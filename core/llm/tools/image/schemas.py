"""image_agent 相关 action input schema。"""

from __future__ import annotations

from typing import Any

from core.llm.prompt.tools.schema_builders import _OBSERVATION
from core.llm.tools.shared.input_common import READ_ONLY_QUERY_SCHEMA

IMAGE_SCAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "observation": _OBSERVATION,
        "count": {"type": "integer", "description": "待生图文字资产数量"},
    },
    "required": ["observation"],
    "additionalProperties": True,
}

IMAGE_GENERATE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "observation": _OBSERVATION,
        "items": {
            "type": "array",
            "description": "可选；仅含 source_text_asset_id 指定部分资产。省略时后端 scan 全量待生图项。禁止填 image_prompt/name/url。",
            "items": {
                "type": "object",
                "properties": {
                    "source_text_asset_id": {
                        "type": "string",
                        "description": "文字资产 ID（与 asset_id 二选一）",
                    },
                    "asset_id": {
                        "type": "string",
                        "description": "同 source_text_asset_id，兼容字段",
                    },
                },
            },
        },
    },
    "required": ["observation"],
    "additionalProperties": True,
}

IMAGE_SEARCH_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "observation": _OBSERVATION,
        "query": {"type": "string", "description": "搜图关键词"},
        "asset_id": {"type": "string", "description": "关联的文字资产 ID"},
        "max_results": {"type": "integer"},
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "source_text_asset_id": {"type": "string"},
                    "url": {"type": "string"},
                    "name": {"type": "string"},
                    "image_prompt": {"type": "string"},
                },
            },
        },
    },
    "required": ["observation"],
    "additionalProperties": True,
}

IMAGE_SYNC_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "observation": _OBSERVATION,
        "asset_id": {"type": "string"},
        "image_observations": {
            "type": "object",
            "description": "从实际图片观察到的字段（color_palette/visual_style/description 等）",
        },
        "apply_major_changes": {"type": "boolean"},
        "apply_fields": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": ["observation", "asset_id"],
    "additionalProperties": True,
}

IMAGE_SCHEMAS: dict[str, dict[str, Any]] = {
    "scan_text_assets": IMAGE_SCAN_SCHEMA,
    "generate_images": IMAGE_GENERATE_SCHEMA,
    "search_images": IMAGE_SEARCH_SCHEMA,
    "sync_text_from_image": IMAGE_SYNC_SCHEMA,
    "list_images": READ_ONLY_QUERY_SCHEMA,
}
