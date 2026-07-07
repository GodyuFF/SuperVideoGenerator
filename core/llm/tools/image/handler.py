"""image_agent tools handlers."""

from __future__ import annotations

from typing import Any

from core.llm.agent.react_core import AgentRunContext
from core.llm.tools.image.scan import (
    build_scan_text_assets_payload,
    format_scan_text_assets_payload,
)
from core.llm.tools.image.search_sync import (
    handle_search_images,
    handle_sync_text_from_image,
)
from core.llm.tools.result import ToolResult
from core.llm.tools.image.generate import run_concurrent_image_generation
from core.llm.tools.shared.media_common import apply_agent_action, read_media_list
from core.models.entities import MediaAssetType
from core.store.memory import MemoryStore
from core.store.persist import schedule_save


def handle_scan_text_assets(
    store: MemoryStore, ctx: AgentRunContext, args: dict[str, Any]
) -> ToolResult:
    try:
        payload = build_scan_text_assets_payload(store, ctx.script_id)
    except ValueError as e:
        return ToolResult(
            observation=str(e),
            structured={"error": str(e), "valid": False},
            ok=False,
        )
    custom_obs = str(args.get("observation", "")).strip()
    observation = format_scan_text_assets_payload(payload)
    if custom_obs and not custom_obs.startswith("执行 "):
        observation = f"{custom_obs}\n\n{observation}"
    schedule_save(store, immediate=True)
    return ToolResult(observation=observation, structured=payload)


handle_list_images = lambda store, ctx, args: read_media_list(
    store, ctx, args, media_type=MediaAssetType.IMAGE
)
async def handle_generate_images(
    store: MemoryStore, ctx: AgentRunContext, args: dict[str, Any]
) -> ToolResult:
    outputs_before = len(ctx.outputs)
    enriched, _ = await run_concurrent_image_generation(
        store, ctx.script_id, args, ctx
    )
    result = apply_agent_action(
        store, ctx, enriched, agent="image_agent", action="generate_images"
    )
    concurrent_outputs = ctx.outputs[outputs_before:]
    if concurrent_outputs:
        structured = dict(result.structured or {})
        structured["output_count"] = len(concurrent_outputs)
        structured["asset_ids"] = [
            o.asset_id for o in concurrent_outputs if o.asset_id
        ]
        result = ToolResult(
            observation=result.observation,
            structured=structured,
            outputs=concurrent_outputs,
            ok=result.ok,
        )
    return result

HANDLERS = {
    "list_images": handle_list_images,
    "scan_text_assets": handle_scan_text_assets,
    "generate_images": handle_generate_images,
    "search_images": handle_search_images,
    "sync_text_from_image": handle_sync_text_from_image,
}
