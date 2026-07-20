"""storyboard_agent 剪辑时间轴与上下文加载。"""

from __future__ import annotations

import json
from typing import Any

from core.edit.timeline import merge_timeline_with_fallback, timeline_board_items, validate_timeline_clips
from core.llm.agent.react_core import AgentRunContext
from core.llm.tools.result import ToolResult
from core.llm.tools.storyboard.context import build_storyboard_context_payload
from core.llm.tools.shared.media_common import make_write_handler
from core.models.entities import StepOutput
from core.store.memory import MemoryStore
from core.store.persist import schedule_save

handle_create_shots = make_write_handler("storyboard_agent", "create_shots")
handle_create_frames = make_write_handler("storyboard_agent", "create_frames")
handle_create_video_clips = make_write_handler("storyboard_agent", "create_video_clips")
handle_persist_plan = make_write_handler("storyboard_agent", "persist_plan")


def handle_build_edit_timeline(
    store: MemoryStore, ctx: AgentRunContext, args: dict[str, Any]
) -> ToolResult:
    script_id = ctx.script_id
    plan = store.get_video_plan_for_script(script_id)
    if plan is None:
        return ToolResult(observation="尚未保存视频计划稿，请先 persist_plan", ok=False)

    llm_tracks = args.get("tracks")
    if isinstance(args.get("timeline"), dict):
        llm_tracks = args["timeline"].get("tracks") or llm_tracks

    timeline = merge_timeline_with_fallback(
        store,
        script_id=script_id,
        plan=plan,
        llm_tracks=llm_tracks if isinstance(llm_tracks, dict) else None,
    )
    store.set_edit_timeline(timeline)
    ctx.outputs.append(
        StepOutput(kind="json", label="edit_timeline", asset_id=timeline.id)
    )
    schedule_save(store, immediate=True)

    warnings = validate_timeline_clips(timeline)
    board = timeline_board_items(store, timeline)
    obs = str(args.get("observation", "")).strip() or (
        f"剪辑计划稿已保存，时长 {board['duration_ms']}ms，"
        f"video={len(board['tracks']['video'])} "
        f"audio={len(board['tracks']['audio'])} "
        f"subtitle={len(board['tracks']['subtitle'])}"
    )
    if warnings:
        obs += f"；警告：{'; '.join(warnings[:3])}"
    payload = {"timeline": board, "warnings": warnings}
    obs = f"{obs}\n\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
    return ToolResult(
        observation=obs,
        structured=payload,
    )


def _resolve_load_context_script_id(ctx: AgentRunContext, args: dict[str, Any]) -> str:
    """校验并返回 load_context 必填的 script_id（须与会话一致）。"""
    sid = str(args.get("script_id") or "").strip()
    if not sid:
        raise ValueError(
            "load_context 必须传入 script_id（与当前会话编排状态中的 script_id 一致）"
        )
    ctx_sid = str(ctx.script_id or "").strip()
    if ctx_sid and sid != ctx_sid:
        raise ValueError(
            f"load_context.script_id 与当前会话不一致：期望 {ctx_sid}，收到 {sid}"
        )
    return sid


def handle_load_context_enriched(
    store: MemoryStore, ctx: AgentRunContext, args: dict[str, Any]
) -> ToolResult:
    """加载剧本、文字资产与已链接图片摘要（供分镜/剪辑设计）。"""
    from core.llm.agent.llm_action import apply_action_result

    observation = apply_action_result(store, "storyboard_agent", "load_context", ctx, args)
    try:
        script_id = _resolve_load_context_script_id(ctx, args)
        payload = build_storyboard_context_payload(store, script_id)
    except ValueError as e:
        return ToolResult(observation=f"{observation}\n{e}", ok=False)

    ctx.work_context["linked_images"] = payload["assets_with_images"]
    ctx.work_context["storyboard_context"] = payload

    structured = {
        "action": "load_context",
        "script_id": payload["script_id"],
        "script": payload["script"],
        "count": payload["count"],
        "counts_by_type": payload.get("counts_by_type", {}),
        "pending_count": payload.get("pending_count", 0),
        "plot_count": payload["plot_count"],
        "plots": payload["plots"],
        "linked_image_count": payload["linked_image_count"],
        "assets_with_images": payload["assets_with_images"],
        "assets": payload.get("assets", []),
    }
    if payload.get("message"):
        structured["message"] = payload["message"]

    json_text = json.dumps(payload, ensure_ascii=False, indent=2)
    return ToolResult(
        observation=f"{observation}\n\n分镜上下文 JSON：\n{json_text}",
        structured=structured,
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
    return ToolResult(
        observation=json.dumps(board, ensure_ascii=False, indent=2),
        structured=board,
    )


HANDLERS = {
    "load_context": handle_load_context_enriched,
    "create_shots": handle_create_shots,
    "create_frames": handle_create_frames,
    "create_video_clips": handle_create_video_clips,
    "persist_plan": handle_persist_plan,
    "build_edit_timeline": handle_build_edit_timeline,
    "get_edit_timeline": handle_get_edit_timeline,
}
