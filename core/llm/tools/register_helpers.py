"""Tool 注册辅助：按域 handler + meta 写入 Registry。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from core.llm.tools.output_schemas import (
    analyze_edit_timeline_output_schema,
    asset_mutation_output_schema,
    build_edit_timeline_output_schema,
    validate_edit_assets_output_schema,
    delete_asset_output_schema,
    edit_timeline_board_output_schema,
    export_status_output_schema,
    export_timeline_output_schema,
    generic_action_output_schema,
    load_edit_context_output_schema,
    list_text_assets_output_schema,
    media_list_output_schema,
    opencut_clip_mutation_output_schema,
    plot_content_output_schema,
    read_only_items_output_schema,
    read_webpage_output_schema,
    refine_plan_output_schema,
    scan_text_assets_output_schema,
    script_mutation_output_schema,
    search_images_output_schema,
    shot_frame_update_output_schema,
    shot_persist_output_schema,
    shot_refine_mutation_output_schema,
    shot_asset_timing_output_schema,
    shot_details_query_output_schema,
    shot_sync_output_schema,
    av_sync_analyze_output_schema,
    storyboard_load_context_output_schema,
    storyboard_shots_output_schema,
    sync_text_from_image_output_schema,
    video_plan_output_schema,
)
from core.llm.tools.registry import ToolRegistry
from core.llm.tools.spec import ToolKind, ToolSpec

# 分镜复核 tool 显式 output schema（须先于 startswith 启发式匹配）
_STORYBOARD_REFINE_OUTPUT: dict[str, Callable[[], dict[str, Any]]] = {
    "get_shot_details": shot_details_query_output_schema,
    "get_shot_asset_timing": shot_asset_timing_output_schema,
    "sync_actual_assets": shot_sync_output_schema,
    "analyze_av_sync": av_sync_analyze_output_schema,
    "get_refine_plan": refine_plan_output_schema,
    "update_frames": shot_frame_update_output_schema,
    "persist_review": shot_persist_output_schema,
    "review_and_restructure": shot_refine_mutation_output_schema,
    "review_shot": shot_refine_mutation_output_schema,
}

# OpenCut / 剪辑 Agent 显式 output schema（须先于 startswith("update_") 启发式）
_EDITING_OUTPUT: dict[str, Callable[[], dict[str, Any]]] = {
    "add_clip": opencut_clip_mutation_output_schema,
    "update_clip": opencut_clip_mutation_output_schema,
    "remove_clip": opencut_clip_mutation_output_schema,
    "apply_effect": opencut_clip_mutation_output_schema,
    "set_keyframe": opencut_clip_mutation_output_schema,
    "export_timeline": export_timeline_output_schema,
    "get_export_status": export_status_output_schema,
}

# script 域 update_* 白名单（其余 update_* 不得误匹配 asset_mutation）
_SCRIPT_UPDATE_OUTPUT: dict[str, Callable[[], dict[str, Any]]] = {
    "update_script": script_mutation_output_schema,
    "update_plot": asset_mutation_output_schema,
    "update_character": asset_mutation_output_schema,
    "update_scene": asset_mutation_output_schema,
    "update_prop": asset_mutation_output_schema,
}


def output_schema_for(name: str) -> dict:
    refine_schema = _STORYBOARD_REFINE_OUTPUT.get(name)
    if refine_schema is not None:
        return refine_schema()
    editing_schema = _EDITING_OUTPUT.get(name)
    if editing_schema is not None:
        return editing_schema()
    script_update_schema = _SCRIPT_UPDATE_OUTPUT.get(name)
    if script_update_schema is not None:
        return script_update_schema()
    if name == "list_text_assets":
        return list_text_assets_output_schema()
    if name == "scan_text_assets":
        return scan_text_assets_output_schema()
    if name in ("parse_brief", "update_script"):
        return script_mutation_output_schema()
    if name.startswith("delete_"):
        return delete_asset_output_schema()
    if name == "create_plot":
        return plot_content_output_schema()
    if name in ("create_shots", "create_frames", "create_video_clips", "persist_plan"):
        return storyboard_shots_output_schema()
    if name.startswith("create_"):
        return asset_mutation_output_schema()
    if name == "get_plan":
        return video_plan_output_schema()
    if name == "load_context":
        return storyboard_load_context_output_schema()
    if name == "load_edit_context":
        return load_edit_context_output_schema()
    if name == "build_edit_timeline" or name == "plan_edit_timeline":
        return build_edit_timeline_output_schema()
    if name == "validate_edit_assets" or name == "report_missing_assets":
        return validate_edit_assets_output_schema()
    if name == "get_edit_timeline":
        return edit_timeline_board_output_schema()
    if name == "analyze_edit_timeline":
        return analyze_edit_timeline_output_schema()
    if name == "read_webpage":
        return read_webpage_output_schema()
    if name.startswith("list_"):
        return media_list_output_schema()
    if name == "search_images":
        return search_images_output_schema()
    if name == "sync_text_from_image":
        return sync_text_from_image_output_schema()
    if name == "return_to_master":
        return {"type": "object"}
    if name == "web_search":
        from core.llm.tools.web_search.schemas import web_search_output_schema

        return web_search_output_schema()
    return generic_action_output_schema()


def register_handlers(
    registry: ToolRegistry,
    handlers: dict,
    tool_meta: dict[str, tuple[str, str, str, str]],
) -> None:
    for name, handler in handlers.items():
        meta = tool_meta.get(name)
        if not meta:
            continue
        agent, kind_str, logical_name, description = meta
        from core.llm.tools.schemas import action_input_schema

        registry.register(
            ToolSpec(
                name=name,
                description=description,
                input_schema=action_input_schema(name),
                output_schema=output_schema_for(name),
                agent=agent,
                kind=ToolKind(kind_str),
                handler=handler,
                logical_name=logical_name,
            )
        )
