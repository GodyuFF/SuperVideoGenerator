"""script_agent tool handlers。"""

from __future__ import annotations

from typing import Any

from core.llm.agent.asset_content import extract_llm_content_field
from core.llm.agent.react_core import AgentRunContext
from core.models.entities import AssetScope, TextAssetType
from core.store.memory import MemoryStore
from core.store.persist import schedule_save
from core.llm.tools.result import ToolResult


def _preview_md(text: str, limit: int = 120) -> str:
    t = text.strip()
    if len(t) <= limit:
        return t
    return t[:limit] + "…"


def handle_list_text_assets(
    store: MemoryStore, ctx: AgentRunContext, args: dict[str, Any]
) -> ToolResult:
    from core.llm.tools.script.list import (
        build_text_assets_list_payload,
        format_text_assets_list_payload,
    )

    types = args.get("types")
    if types is not None and not isinstance(types, list):
        types = None
    include_content = args.get("include_content", True)
    if not isinstance(include_content, bool):
        include_content = True

    try:
        payload = build_text_assets_list_payload(
            store,
            ctx.script_id,
            types=types,
            include_content=include_content,
        )
    except ValueError as e:
        return ToolResult(
            observation=str(e),
            structured={"error": str(e), "valid": False},
            ok=False,
        )

    obs = format_text_assets_list_payload(payload)
    return ToolResult(observation=obs, structured=payload)


def handle_apply_script_action(
    store: MemoryStore,
    ctx: AgentRunContext,
    args: dict[str, Any],
    *,
    action: str,
) -> ToolResult:
    from core.llm.agent.llm_action import apply_action_result

    outputs_before = list(ctx.outputs)
    observation = apply_action_result(store, "script_agent", action, ctx, args)
    immediate = action.startswith(("create_", "update_", "delete_")) or action in (
        "parse_brief",
        "update_script",
    )
    schedule_save(store, immediate=immediate)
    structured = _structured_for_action(store, ctx, action, args, outputs_before)
    return ToolResult(
        observation=observation,
        structured=structured,
        outputs=[o for o in ctx.outputs if o not in outputs_before],
    )


def _structured_for_action(
    store: MemoryStore,
    ctx: AgentRunContext,
    action: str,
    args: dict[str, Any],
    outputs_before: list,
) -> dict[str, Any]:
    script_id = ctx.script_id

    if action in ("parse_brief", "update_script"):
        script = store.get_script(script_id)
        updated: list[str] = []
        if action == "parse_brief":
            if args.get("content_md") or args.get("script_md"):
                updated.append("content_md")
            if args.get("title"):
                updated.append("title")
            if args.get("duration_sec") is not None:
                updated.append("duration_sec")
        else:
            if args.get("title"):
                updated.append("title")
            if args.get("content_md"):
                updated.append("content_md")
            if args.get("duration_sec") is not None:
                updated.append("duration_sec")
        md = script.content_md if script else ""
        return {
            "script_id": script_id,
            "title": script.title if script else "",
            "duration_sec": script.duration_sec if script else 0,
            "content_md_preview": _preview_md(md),
            "updated_fields": updated or ["observation"],
        }

    if action.startswith("delete_"):
        asset_id = str(args.get("asset_id", ""))
        return {"asset_id": asset_id, "deleted": True}

    if action.startswith("update_"):
        asset_id = str(args.get("asset_id", ""))
        asset = store.get_text_asset(asset_id)
        content = extract_llm_content_field(args, action)
        merged_fields: list[str] = []
        if isinstance(content, dict):
            merged_fields = list(content.keys())
        if args.get("asset_name"):
            merged_fields.append("asset_name")
        return {
            "asset_id": asset_id,
            "type": asset.type.value if asset else "",
            "name": asset.name if asset else "",
            "scope": asset.scope.value if asset else "",
            "content": dict(asset.content) if asset and isinstance(asset.content, dict) else {},
            "merged_fields": merged_fields,
        }

    if action.startswith("create_"):
        new_outputs = [o for o in ctx.outputs if o not in outputs_before]
        asset_id = new_outputs[-1].asset_id if new_outputs else ""
        asset = store.get_text_asset(asset_id) if asset_id else None
        return {
            "asset_id": asset_id,
            "type": asset.type.value if asset else "",
            "name": asset.name if asset else str(args.get("asset_name", "")),
            "scope": asset.scope.value if asset else "",
            "content": dict(asset.content) if asset and isinstance(asset.content, dict) else {},
        }

    return {"action": action, "summary": str(args.get("observation", ""))}


def handle_parse_brief(store, ctx, args):
    return handle_apply_script_action(store, ctx, args, action="parse_brief")


def handle_update_script(store, ctx, args):
    return handle_apply_script_action(store, ctx, args, action="update_script")


def handle_create_plot(store, ctx, args):
    return handle_apply_script_action(store, ctx, args, action="create_plot")


def handle_create_character(store, ctx, args):
    return handle_apply_script_action(store, ctx, args, action="create_character")


def handle_create_scene(store, ctx, args):
    return handle_apply_script_action(store, ctx, args, action="create_scene")


def handle_create_prop(store, ctx, args):
    return handle_apply_script_action(store, ctx, args, action="create_prop")


def handle_update_plot(store, ctx, args):
    return handle_apply_script_action(store, ctx, args, action="update_plot")


def handle_update_character(store, ctx, args):
    return handle_apply_script_action(store, ctx, args, action="update_character")


def handle_update_scene(store, ctx, args):
    return handle_apply_script_action(store, ctx, args, action="update_scene")


def handle_update_prop(store, ctx, args):
    return handle_apply_script_action(store, ctx, args, action="update_prop")


def handle_delete_plot(store, ctx, args):
    return handle_apply_script_action(store, ctx, args, action="delete_plot")


def handle_delete_character(store, ctx, args):
    return handle_apply_script_action(store, ctx, args, action="delete_character")


def handle_delete_scene(store, ctx, args):
    return handle_apply_script_action(store, ctx, args, action="delete_scene")


def handle_delete_prop(store, ctx, args):
    return handle_apply_script_action(store, ctx, args, action="delete_prop")
