"""tts_agent tools handlers."""

from __future__ import annotations

from typing import Any

from core.llm.agent.react_core import AgentRunContext
from core.llm.tools.result import ToolResult
from core.llm.tools.shared.media_common import apply_agent_action, read_media_list
from core.llm.tools.tts.extract import build_narration_payload, format_narration_observation
from core.llm.tools.tts.synthesize import run_concurrent_tts_synthesis
from core.models.entities import MediaAssetType
from core.store.memory import MemoryStore
from core.store.persist import schedule_save


def handle_extract_narration(
    store: MemoryStore, ctx: AgentRunContext, args: dict[str, Any]
) -> ToolResult:
    payload = build_narration_payload(store, ctx.script_id)
    custom_obs = str(args.get("observation", "")).strip()
    observation = format_narration_observation(payload)
    if custom_obs and not custom_obs.startswith("执行 "):
        observation = f"{custom_obs}\n\n{observation}"
    enriched = dict(args)
    enriched["line_count"] = payload.get("line_count", 0)
    enriched["items"] = payload.get("items", [])
    result = apply_agent_action(
        store, ctx, enriched, agent="tts_agent", action="extract_narration"
    )
    schedule_save(store, immediate=True)
    structured = dict(result.structured or {})
    structured.update(payload)
    return ToolResult(
        observation=observation,
        structured=structured,
        outputs=result.outputs,
        ok=bool(payload.get("valid")),
    )


async def handle_synthesize(
    store: MemoryStore, ctx: AgentRunContext, args: dict[str, Any]
) -> ToolResult:
    outputs_before = len(ctx.outputs)
    synthesized, _ = await run_concurrent_tts_synthesis(store, ctx.script_id, args, ctx)
    enriched = dict(args)
    enriched["tracks"] = synthesized
    result = apply_agent_action(store, ctx, enriched, agent="tts_agent", action="synthesize")
    concurrent_outputs = ctx.outputs[outputs_before:]
    if concurrent_outputs:
        structured = dict(result.structured or {})
        structured["output_count"] = len(concurrent_outputs)
        structured["asset_ids"] = [o.asset_id for o in concurrent_outputs if o.asset_id]
        structured["tracks"] = synthesized
        result = ToolResult(
            observation=result.observation,
            structured=structured,
            outputs=concurrent_outputs,
            ok=result.ok,
        )
    schedule_save(store, immediate=True)
    return result


handle_list_audio = lambda store, ctx, args: read_media_list(
    store, ctx, args, media_type=MediaAssetType.AUDIO
)

HANDLERS = {
    "extract_narration": handle_extract_narration,
    "synthesize": handle_synthesize,
    "list_audio": handle_list_audio,
}
