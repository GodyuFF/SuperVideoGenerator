"""Tool 注册辅助：按域 handler + meta 写入 Registry。"""

from __future__ import annotations

from core.llm.tools.output_schemas import (
    asset_mutation_output_schema,
    build_edit_timeline_output_schema,
    validate_edit_assets_output_schema,
    delete_asset_output_schema,
    edit_timeline_board_output_schema,
    generic_action_output_schema,
    load_edit_context_output_schema,
    list_text_assets_output_schema,
    media_list_output_schema,
    plot_content_output_schema,
    read_only_items_output_schema,
    read_webpage_output_schema,
    scan_text_assets_output_schema,
    script_mutation_output_schema,
    search_images_output_schema,
    storyboard_load_context_output_schema,
    storyboard_shots_output_schema,
    sync_text_from_image_output_schema,
    video_plan_output_schema,
)
from core.llm.tools.registry import ToolRegistry
from core.llm.tools.spec import ToolKind, ToolSpec


def output_schema_for(name: str) -> dict:
    if name == "list_text_assets":
        return list_text_assets_output_schema()
    if name == "scan_text_assets":
        return scan_text_assets_output_schema()
    if name in ("parse_brief", "update_script"):
        return script_mutation_output_schema()
    if name.startswith("delete_"):
        return delete_asset_output_schema()
    if name.startswith("update_"):
        return asset_mutation_output_schema()
    if name == "create_plot":
        return plot_content_output_schema()
    if name in ("create_shots", "create_frames", "persist_plan"):
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
    if name == "read_webpage":
        return read_webpage_output_schema()
    if name.startswith("list_"):
        return media_list_output_schema()
    if name == "search_images":
        return search_images_output_schema()
    if name == "sync_text_from_image":
        return sync_text_from_image_output_schema()
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
