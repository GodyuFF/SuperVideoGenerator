"""editing_agent 剪辑计划稿与素材校验 handlers。"""

from __future__ import annotations

import json
from typing import Any

from core.edit.asset_resolver import validate_edit_timeline
from core.edit.timeline import (
    build_timeline_layer_summary,
    format_layer_summary_text,
    merge_timeline_with_fallback,
    timeline_board_items,
    validate_timeline_clips,
)
from core.llm.agent.react_core import AgentRunContext
from core.llm.hook.react_guard import EditComposeMissingAssetsError
from core.llm.master.edit_failure import format_edit_compose_failure_observation
from core.llm.tools.editing.context import build_edit_context_payload
from core.llm.tools.result import ToolResult
from core.llm.tools.shared.assets_summary import format_script_assets_payload
from core.models.entities import StepOutput
from core.store.memory import MemoryStore
from core.store.persist import schedule_save


def handle_load_edit_context(
    store: MemoryStore, ctx: AgentRunContext, args: dict[str, Any]
) -> ToolResult:
    del args
    script_id = ctx.script_id
    try:
        payload = build_edit_context_payload(store, script_id)
    except ValueError as exc:
        return ToolResult(observation=str(exc), structured={"error": str(exc)}, ok=False)
    ctx.work_context["edit_context"] = payload

    media_summary: dict[str, Any] = {}
    media_breakdown: dict[str, int] = {}
    for m in store.list_media_for_script(script_id):
        media_breakdown[m.type.value] = media_breakdown.get(m.type.value, 0) + 1
    for media_type in ("image", "audio", "video", "final"):
        cnt = payload.get("media_counts", {}).get(media_type, 0)
        if cnt:
            media_summary[media_type] = cnt
    if not media_summary:
        media_summary = {"note": "暂无可访问媒体"}

    summary = {
        "script_id": script_id,
        "has_video_plan": bool(payload.get("video_plan")),
        "shot_count": payload.get("video_plan", {}).get("shot_count", 0) if payload.get("video_plan") else 0,
        "plot_count": payload.get("plot_count", 0),
        "linked_image_count": payload.get("linked_image_count", 0),
        "has_edit_timeline": bool(payload.get("edit_timeline")),
        "media_breakdown": media_breakdown,
    }

    structured = {
        "action": "load_edit_context",
        "script_id": script_id,
        "script": payload.get("script", {}),
        "video_plan": payload.get("video_plan"),
        "edit_timeline": payload.get("edit_timeline"),
        "shot_gaps": payload.get("shot_gaps", []),
        "plots": payload.get("plots", []),
        "plot_count": payload.get("plot_count", 0),
        "assets_with_images": payload.get("assets_with_images", []),
        "linked_image_count": payload.get("linked_image_count", 0),
        "media": media_summary,
        "summary": summary,
    }
    if payload.get("message"):
        structured["message"] = payload["message"]

    obs = json.dumps(structured, ensure_ascii=False, indent=2)
    return ToolResult(observation=obs, structured=structured)


def handle_plan_edit_timeline(
    store: MemoryStore, ctx: AgentRunContext, args: dict[str, Any]
) -> ToolResult:
    script_id = ctx.script_id
    plan = store.get_video_plan_for_script(script_id)
    if plan is None:
        return ToolResult(observation="尚未保存视频计划稿，请先 storyboard persist_plan", ok=False)

    llm_tracks = args.get("tracks")
    llm_video_layers = args.get("video_layers")
    if isinstance(args.get("timeline"), dict):
        tl = args["timeline"]
        llm_tracks = tl.get("tracks") or llm_tracks
        llm_video_layers = tl.get("video_layers") or llm_video_layers

    mode = str(args.get("mode", "")).strip().lower()
    existing = store.get_edit_timeline_for_script(script_id)
    if not mode:
        mode = "merge" if existing and existing.user_edited else "create"

    skip_subtitle_enrich = bool(args.get("skip_subtitle_enrich"))
    if (
        not skip_subtitle_enrich
        and mode == "replace"
        and isinstance(llm_tracks, dict)
        and llm_tracks.get("subtitle") == []
    ):
        skip_subtitle_enrich = True

    timeline = merge_timeline_with_fallback(
        store,
        script_id=script_id,
        plan=plan,
        llm_tracks=llm_tracks if isinstance(llm_tracks, dict) else None,
        llm_video_layers=llm_video_layers if isinstance(llm_video_layers, list) else None,
        existing=existing,
        mode=mode,
        skip_subtitle_enrich=skip_subtitle_enrich,
    )
    store.set_edit_timeline(timeline)
    ctx.outputs.append(
        StepOutput(kind="json", label="edit_timeline", asset_id=timeline.id)
    )
    schedule_save(store, immediate=True)

    warnings = validate_timeline_clips(timeline)
    board = timeline_board_items(store, timeline)
    layer_summary = build_timeline_layer_summary(store, timeline)
    layer_text = format_layer_summary_text(layer_summary)
    obs = str(args.get("observation", "")).strip() or (
        f"剪辑计划稿已保存，时长 {board['duration_ms']}ms，"
        f"{layer_text}，"
        f"audio={len(board['tracks']['audio'])} "
        f"subtitle={len(board['tracks']['subtitle'])}"
    )
    if warnings:
        obs += f"；警告：{'; '.join(warnings)}"
    payload = {
        "timeline": board,
        "warnings": warnings,
        "layer_summary": layer_summary,
    }
    obs = f"{obs}\n\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
    return ToolResult(observation=obs, structured=payload)


def handle_validate_edit_assets(
    store: MemoryStore, ctx: AgentRunContext, args: dict[str, Any]
) -> ToolResult:
    del args
    timeline = store.get_edit_timeline_for_script(ctx.script_id)
    if timeline is None:
        structured = {
            "ready": False,
            "missing_items": [
                {
                    "category": "timeline",
                    "clip_id": "",
                    "reason": "尚无剪辑计划稿，请先 plan_edit_timeline",
                    "suggested_upstream": "storyboard",
                }
            ],
            "summary": {},
        }
        return ToolResult(
            observation=json.dumps(structured, ensure_ascii=False, indent=2),
            structured=structured,
            ok=False,
        )
    report = validate_edit_timeline(store, timeline)
    layer_summary = build_timeline_layer_summary(store, timeline)
    structured = report.to_dict()
    summary = dict(structured.get("summary") or {})
    summary["layer_summary"] = layer_summary
    summary["warnings"] = layer_summary.get("warnings") or []
    structured["summary"] = summary
    obs = json.dumps(structured, ensure_ascii=False, indent=2)
    return ToolResult(observation=obs, structured=structured, ok=report.ready)


def handle_report_missing_assets(
    store: MemoryStore, ctx: AgentRunContext, args: dict[str, Any]
) -> ToolResult:
    timeline = store.get_edit_timeline_for_script(ctx.script_id)
    if timeline is None:
        raise EditComposeMissingAssetsError("report_missing_assets", "尚无剪辑计划稿，无法报告缺失素材。")

    report = validate_edit_timeline(store, timeline)
    if report.ready:
        structured = report.to_dict()
        return ToolResult(
            observation="素材校验已通过，无需上报缺失项。",
            structured=structured,
            ok=True,
        )

    obs = format_edit_compose_failure_observation(report)
    if str(args.get("observation", "")).strip():
        obs = f"{args['observation'].strip()}\n\n{obs}"
    raise EditComposeMissingAssetsError(
        "report_missing_assets",
        obs,
        validation_report=report,
    )


def handle_get_edit_timeline(
    store: MemoryStore, ctx: AgentRunContext, args: dict[str, Any]
) -> ToolResult:
    del args
    timeline = store.get_edit_timeline_for_script(ctx.script_id)
    if timeline is None:
        structured = {"duration_ms": 0, "timeline": None, "message": "当前剧本尚无剪辑计划稿"}
        return ToolResult(
            observation=structured["message"],
            structured=structured,
        )
    board = timeline_board_items(store, timeline)
    layer_summary = build_timeline_layer_summary(store, timeline)
    layer_text = format_layer_summary_text(layer_summary)
    structured = {**board, "layer_summary": layer_summary}
    obs = f"{layer_text}\n\n{json.dumps(board, ensure_ascii=False, indent=2)}"
    return ToolResult(
        observation=obs,
        structured=structured,
    )
