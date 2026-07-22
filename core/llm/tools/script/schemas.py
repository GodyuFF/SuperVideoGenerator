"""script_agent 相关 action input schema。"""

from __future__ import annotations

from typing import Any

from core.llm.prompt.tools.schema_builders import (
    _OBSERVATION,
    build_character_content_schema,
    build_character_content_update_schema,
    build_list_project_shared_assets_input_schema,
    build_list_text_assets_input_schema,
    build_plot_content_schema,
    build_plot_content_update_schema,
    build_prop_content_schema,
    build_prop_content_update_schema,
    build_scene_content_schema,
    build_scene_content_update_schema,
    build_script_brief_action_schema,
    build_script_update_action_schema,
)
from core.llm.tools.shared.input_common import (
    DELETE_ASSET_SCHEMA,
    merge_plan_tracking,
    update_asset_schema,
)

_PLOT_CONTENT = build_plot_content_schema()
_PLOT_CONTENT_UPDATE = build_plot_content_update_schema()
_CHARACTER_CONTENT = build_character_content_schema()
_CHARACTER_CONTENT_UPDATE = build_character_content_update_schema()
_SCENE_CONTENT = build_scene_content_schema()
_SCENE_CONTENT_UPDATE = build_scene_content_update_schema()
_PROP_CONTENT = build_prop_content_schema()
_PROP_CONTENT_UPDATE = build_prop_content_update_schema()

_CREATE_ASSET_SCHEMA: dict[str, dict[str, Any]] = {
    "create_plot": {
        "type": "object",
        "properties": {
            "observation": _OBSERVATION,
            "asset_name": {"type": "string"},
            "content": _PLOT_CONTENT,
        },
        "required": ["observation", "content"],
        "additionalProperties": True,
    },
    "create_character": {
        "type": "object",
        "properties": {
            "observation": _OBSERVATION,
            "asset_name": {"type": "string"},
            "content": _CHARACTER_CONTENT,
            "reuse_asset_id": {
                "type": "string",
                "description": "复用项目共享池已有人物：填 list_project_shared_assets 返回的 id；有则只关联不新建，可省略 content",
            },
        },
        "required": ["observation"],
        "additionalProperties": True,
    },
    "create_scene": {
        "type": "object",
        "properties": {
            "observation": _OBSERVATION,
            "asset_name": {"type": "string"},
            "content": _SCENE_CONTENT,
            "reuse_asset_id": {
                "type": "string",
                "description": "复用项目共享池已有空镜：填 list_project_shared_assets 返回的 id；有则只关联不新建，可省略 content",
            },
        },
        "required": ["observation"],
        "additionalProperties": True,
    },
    "create_prop": {
        "type": "object",
        "properties": {
            "observation": _OBSERVATION,
            "asset_name": {"type": "string"},
            "content": _PROP_CONTENT,
            "reuse_asset_id": {
                "type": "string",
                "description": "复用项目共享池已有道具：填 list_project_shared_assets 返回的 id；有则只关联不新建，可省略 content",
            },
        },
        "required": ["observation"],
        "additionalProperties": True,
    },
}

SCRIPT_SCHEMAS: dict[str, dict[str, Any]] = {
    "parse_brief": build_script_brief_action_schema(),
    "update_script": build_script_update_action_schema(),
    **_CREATE_ASSET_SCHEMA,
    "update_plot": update_asset_schema(_PLOT_CONTENT_UPDATE),
    "update_character": update_asset_schema(_CHARACTER_CONTENT_UPDATE),
    "update_scene": update_asset_schema(_SCENE_CONTENT_UPDATE),
    "update_prop": update_asset_schema(_PROP_CONTENT_UPDATE),
    "delete_plot": DELETE_ASSET_SCHEMA,
    "delete_character": DELETE_ASSET_SCHEMA,
    "delete_scene": DELETE_ASSET_SCHEMA,
    "delete_prop": DELETE_ASSET_SCHEMA,
    "list_text_assets": merge_plan_tracking(build_list_text_assets_input_schema()),
    "list_project_shared_assets": merge_plan_tracking(
        build_list_project_shared_assets_input_schema()
    ),
}
