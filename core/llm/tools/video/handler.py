"""video_agent tools handlers。"""

from __future__ import annotations

from typing import Any

from core.llm.agent.react_core import AgentRunContext
from core.llm.tools.shared.media_common import apply_agent_action, make_write_handler, read_media_list
from core.llm.tools.result import ToolResult
from core.llm.tools.video.generate import run_concurrent_video_generation
from core.models.entities import MediaAssetType
from core.store.memory import MemoryStore
from core.store.persist import schedule_save

handle_load_shots = make_write_handler("video_agent", "load_shots")
handle_generate_from_timeline = make_write_handler("video_agent", "generate_from_timeline")
handle_list_videos = lambda store, ctx, args: read_media_list(
    store, ctx, args, media_type=MediaAssetType.VIDEO
)


async def handle_generate_clips(
    store: MemoryStore, ctx: AgentRunContext, args: dict[str, Any]
) -> ToolResult:
    """为镜头调用 Agnes Video V2.0 生成片段并绑定镜内 z0 clip。"""
    outputs_before = len(ctx.outputs)
    enriched, errors = await run_concurrent_video_generation(
        store, ctx.script_id, args, ctx
    )
    result = apply_agent_action(
        store, ctx, enriched, agent="video_agent", action="generate_clips"
    )
    concurrent_outputs = ctx.outputs[outputs_before:]
    structured = dict(result.structured or {})
    if concurrent_outputs:
        structured["output_count"] = len(concurrent_outputs)
        structured["asset_ids"] = [
            o.asset_id for o in concurrent_outputs if o.asset_id
        ]
    if errors:
        structured["errors"] = errors
    obs = result.observation
    if errors and concurrent_outputs:
        obs = f"{obs}\n部分失败：{'；'.join(errors[:5])}"
    elif errors and not concurrent_outputs:
        obs = f"视频生成失败：{'；'.join(errors[:5])}"
        return ToolResult(
            observation=obs,
            structured={**structured, "error": errors[0]},
            ok=False,
        )
    from core.edit.shot_media_bind import bind_shot_video_media_to_plan

    clips = enriched.get("clips") if isinstance(enriched.get("clips"), list) else []
    bound = 0
    for raw in clips:
        if not isinstance(raw, dict):
            continue
        shot_id = str(raw.get("shot_id", "")).strip()
        asset_id = str(raw.get("asset_id", "")).strip()
        vc_id = str(raw.get("video_clip_asset_id", "")).strip()
        if vc_id and asset_id:
            from core.edit.shot_media_bind import bind_video_clip_media_to_plan

            if bind_video_clip_media_to_plan(
                store, ctx.script_id, vc_id, asset_id
            ):
                bound += 1
            continue
        if shot_id and asset_id:
            if bind_shot_video_media_to_plan(store, ctx.script_id, shot_id, asset_id):
                bound += 1
    if bound:
        structured["bound_shots"] = bound
        try:
            from core.edit.av_sync import reconcile_script_av

            shot_ids = [
                str(raw.get("shot_id", "")).strip()
                for raw in clips
                if isinstance(raw, dict) and str(raw.get("shot_id", "")).strip()
            ]
            av_result = reconcile_script_av(
                store,
                ctx.script_id,
                mode="hybrid",
                shot_ids=shot_ids or None,
                persist=True,
            )
            structured["av_sync"] = {
                "auto_applied_count": av_result.get("auto_applied_count", 0),
                "needs_user_choice_shot_ids": av_result.get(
                    "needs_user_choice_shot_ids", []
                ),
                "need_regen_shot_ids": av_result.get("need_regen_shot_ids", []),
            }
        except Exception as av_exc:
            structured["av_sync_error"] = str(av_exc)
    schedule_save(store, immediate=True)
    return ToolResult(
        observation=obs,
        structured=structured,
        outputs=concurrent_outputs,
        ok=result.ok,
    )


async def handle_scan_video_clips(
    store: MemoryStore, ctx: AgentRunContext, args: dict[str, Any]
) -> ToolResult:
    """扫描待生成视频的 video_clip 文字资产。"""
    from core.llm.tools.video.scan import scan_video_clips

    raw_ids = args.get("asset_ids") or args.get("video_clip_asset_ids")
    asset_ids = raw_ids if isinstance(raw_ids, list) else None
    payload = scan_video_clips(store, ctx.script_id, asset_ids=asset_ids)
    payload = {**payload, "action": "scan_video_clips"}
    obs = str(args.get("observation", "")).strip() or (
        f"共 {payload['total']} 个 video_clip，"
        f"就绪 {payload['ready_count']}，待生成 {payload['pending_count']}"
    )
    return ToolResult(observation=obs, structured=payload, ok=True)


async def handle_generate_video_clips(
    store: MemoryStore, ctx: AgentRunContext, args: dict[str, Any]
) -> ToolResult:
    """按 video_clip 文字资产生成 AI 视频。"""
    from core.llm.tools.video.video_clips import run_concurrent_video_clip_generation

    outputs_before = len(ctx.outputs)
    enriched, errors = await run_concurrent_video_clip_generation(
        store, ctx.script_id, args, ctx
    )
    result = apply_agent_action(
        store, ctx, enriched, agent="video_agent", action="generate_video_clips"
    )
    concurrent_outputs = ctx.outputs[outputs_before:]
    structured = dict(result.structured or {})
    structured.update(
        {
            "clip_count": len(enriched.get("clips") or []),
            "asset_ids": [
                c.get("asset_id")
                for c in (enriched.get("clips") or [])
                if isinstance(c, dict) and c.get("asset_id")
            ],
        }
    )
    if errors:
        structured["errors"] = errors
    obs = result.observation
    if errors and not structured.get("asset_ids"):
        return ToolResult(
            observation=f"video_clip 生成失败：{'；'.join(errors[:5])}",
            structured={**structured, "error": errors[0]},
            ok=False,
        )
    if errors:
        obs = f"{obs}\n部分失败：{'；'.join(errors[:5])}"
    if structured.get("asset_ids"):
        try:
            from core.edit.av_sync import reconcile_script_av

            av_result = reconcile_script_av(
                store, ctx.script_id, mode="hybrid", persist=True
            )
            structured["av_sync"] = {
                "auto_applied_count": av_result.get("auto_applied_count", 0),
                "needs_user_choice_shot_ids": av_result.get(
                    "needs_user_choice_shot_ids", []
                ),
                "need_regen_shot_ids": av_result.get("need_regen_shot_ids", []),
            }
        except Exception as av_exc:
            structured["av_sync_error"] = str(av_exc)
    schedule_save(store, immediate=True)
    return ToolResult(
        observation=obs,
        structured=structured,
        outputs=concurrent_outputs,
        ok=True,
    )


HANDLERS = {
    "load_shots": handle_load_shots,
    "generate_clips": handle_generate_clips,
    "scan_video_clips": handle_scan_video_clips,
    "generate_video_clips": handle_generate_video_clips,
    "generate_from_timeline": handle_generate_from_timeline,
    "list_videos": handle_list_videos,
}
