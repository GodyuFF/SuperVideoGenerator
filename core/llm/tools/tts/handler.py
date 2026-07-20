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


async def _emit_assets_changed(ctx: AgentRunContext, *, shot_ids: list[str] | None = None) -> None:
    """TTS 落盘后通知看板刷新。"""
    emitter = ctx.work_context.get("emitter")
    if emitter is None:
        return
    payload: dict[str, Any] = {
        "type": "assets_changed",
        "script_id": ctx.script_id,
        "agent_name": "tts_agent",
        "action": "synthesize",
        "step_id": ctx.step_id,
    }
    if shot_ids:
        payload["shot_ids"] = shot_ids
        if len(shot_ids) == 1:
            payload["shot_id"] = shot_ids[0]
    await emitter.emit(payload)


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
    try:
        from core.edit.shot_detail_sync import sync_plan_from_tts

        sync_result = sync_plan_from_tts(store, ctx.script_id)
        if isinstance(result.structured, dict):
            result.structured["shot_detail_sync"] = sync_result
        try:
            from core.edit.av_sync import reconcile_script_av

            av_result = reconcile_script_av(
                store, ctx.script_id, mode="hybrid", persist=True
            )
            if isinstance(result.structured, dict):
                result.structured["av_sync"] = {
                    "auto_applied_count": av_result.get("auto_applied_count", 0),
                    "needs_user_choice_shot_ids": av_result.get(
                        "needs_user_choice_shot_ids", []
                    ),
                    "need_regen_shot_ids": av_result.get("need_regen_shot_ids", []),
                }
        except Exception as av_exc:
            if isinstance(result.structured, dict):
                result.structured["av_sync_error"] = str(av_exc)
        probe_failures = sync_result.get("probe_failures") or []
        if probe_failures:
            failed_orders = ", ".join(
                f"镜{int(item.get('order', 0)) + 1}" for item in probe_failures
            )
            result = ToolResult(
                observation=(
                    f"{result.observation}\n警告：{failed_orders} 的 TTS 时长探测失败，"
                    "分镜时长未按实测更新（请检查 FFmpeg 是否可用、音频文件是否完整）。"
                ),
                structured=result.structured,
                outputs=result.outputs,
                ok=result.ok,
            )
    except ValueError as exc:
        if isinstance(result.structured, dict):
            result.structured["shot_detail_sync_error"] = str(exc)
    schedule_save(store)
    shot_ids = [
        str(t.get("shot_id") or "").strip()
        for t in synthesized
        if str(t.get("shot_id") or "").strip()
    ]
    await _emit_assets_changed(ctx, shot_ids=shot_ids or None)
    return result


handle_list_audio = lambda store, ctx, args: read_media_list(
    store, ctx, args, media_type=MediaAssetType.AUDIO
)

HANDLERS = {
    "extract_narration": handle_extract_narration,
    "synthesize": handle_synthesize,
    "list_audio": handle_list_audio,
}
