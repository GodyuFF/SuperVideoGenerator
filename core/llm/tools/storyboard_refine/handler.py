"""storyboard_refine_agent tools handlers。"""

from __future__ import annotations

import json
from typing import Any

from core.edit.shot_detail_sync import (
    apply_shot_detail_patches,
    sync_actual_assets,
    update_frames_from_shot_detail,
)
from core.edit.shot_query import build_shot_asset_timing_query, build_shot_details_query
from core.edit.storyboard_restructure import apply_restructure_ops
from core.llm.agent.react_core import AgentRunContext
from core.llm.tools.result import ToolResult
from core.llm.tools.storyboard_refine.validate import validate_refine_mutation_input, validate_review_shot_input
from core.models.entities import VideoPlan
from core.store.memory import MemoryStore
from core.store.persist import schedule_save


def _validation_error(message: str) -> ToolResult:
    """返回 preflight 校验失败结果。"""
    structured = {"error": message, "valid": False}
    return ToolResult(observation=message, structured=structured, ok=False)


def _shot_filter_from_args(args: dict[str, Any]) -> tuple[str | None, list[str] | None]:
    """从 tool 参数解析 shot_id / shot_ids 过滤。"""
    shot_id = str(args.get("shot_id") or "").strip() or None
    raw_ids = args.get("shot_ids")
    shot_ids: list[str] | None = None
    if isinstance(raw_ids, list) and raw_ids:
        shot_ids = [str(x).strip() for x in raw_ids if x]
    return shot_id, shot_ids


def _resolve_patches(
    plan: VideoPlan,
    patches: list[Any],
) -> list[dict[str, Any]]:
    """解析 patch 列表，补全缺失的 shot_id。"""
    shots_sorted = sorted(plan.shots, key=lambda s: s.order)
    resolved: list[dict[str, Any]] = []
    for i, raw in enumerate(patches):
        if not isinstance(raw, dict):
            continue
        patch = dict(raw)
        shot_id = str(patch.get("shot_id") or patch.get("id") or "").strip()
        if (not shot_id or shot_id.startswith("shot_scripted")) and shots_sorted:
            idx = int(patch.get("order", i))
            if 0 <= idx < len(shots_sorted):
                patch["shot_id"] = shots_sorted[idx].id
            else:
                patch["shot_id"] = shots_sorted[min(i, len(shots_sorted) - 1)].id
        resolved.append(patch)
    if len(resolved) == 1 and len(shots_sorted) > 1:
        template = resolved[0]
        resolved = [{**template, "shot_id": s.id} for s in shots_sorted]
    return resolved


def _apply_refine_mutation(
    store: MemoryStore,
    script_id: str,
    *,
    ops: list[Any],
    patches: list[Any],
    observation: str,
    action: str = "review_and_restructure",
    target_shot_id: str = "",
) -> ToolResult:
    """执行结构性复核与详设 patch，返回结构化结果。"""
    plan = store.get_video_plan_for_script(script_id)
    errors = validate_refine_mutation_input(
        plan,
        ops=ops,
        patches=patches,
        require_mutation=True,
    )
    if errors:
        return _validation_error("; ".join(errors))

    assert plan is not None
    restructure_op_count = 0
    if ops:
        plan = apply_restructure_ops(store, script_id, ops)
        restructure_op_count = len(ops)

    patched_shot_count = 0
    need_regen_shot_ids: list[str] = []
    if patches:
        resolved = _resolve_patches(plan, patches)
        if resolved:
            plan = apply_shot_detail_patches(store, script_id, resolved)
            patched_shot_count = len(resolved)
            need_regen_shot_ids = [
                str(p.get("shot_id") or "")
                for p in resolved
                if isinstance(p, dict) and p.get("need_regen") and p.get("shot_id")
            ]

    schedule_save(store, immediate=True)
    summary = observation.strip() or (
        f"已执行 {restructure_op_count} 项结构操作，复核 {patched_shot_count} 镜，"
        f"detail_revision={plan.detail_revision}。"
    )
    if need_regen_shot_ids:
        summary += f" 建议补图：{', '.join(need_regen_shot_ids[:5])}。"

    structured: dict[str, Any] = {
        "action": action,
        "summary": summary[:500],
        "plan_id": plan.id,
        "detail_revision": plan.detail_revision,
        "shot_count": len(plan.shots),
        "restructure_op_count": restructure_op_count,
        "patched_shot_count": patched_shot_count,
        "need_regen_shot_ids": need_regen_shot_ids,
    }
    if target_shot_id:
        structured["shot_id"] = target_shot_id
    return ToolResult(
        observation=f"{summary}\n\n{json.dumps(structured, ensure_ascii=False, indent=2)}",
        structured=structured,
    )


def handle_get_shot_details(
    store: MemoryStore, ctx: AgentRunContext, args: dict[str, Any]
) -> ToolResult:
    """查询分镜详情（plan / detail / 配图状态）。"""
    shot_id, shot_ids = _shot_filter_from_args(args)
    try:
        payload = build_shot_details_query(
            store, ctx.script_id, shot_id=shot_id, shot_ids=shot_ids
        )
    except ValueError as exc:
        return _validation_error(str(exc))
    obs_prefix = str(args.get("observation", "")).strip() or (
        f"已查询 {payload['shot_count']} 镜分镜详情，"
        f"缺图 {len(payload.get('image_gap_shot_ids') or [])} 镜。"
    )
    return ToolResult(
        observation=f"{obs_prefix}\n\n{json.dumps(payload, ensure_ascii=False, indent=2)}",
        structured=payload,
    )


def handle_get_shot_asset_timing(
    store: MemoryStore, ctx: AgentRunContext, args: dict[str, Any]
) -> ToolResult:
    """查询镜头对应音频/视频时长；音频含各时段文字。"""
    shot_id, shot_ids = _shot_filter_from_args(args)
    kind = str(args.get("asset_kind") or "all").strip().lower()
    if kind not in ("audio", "video", "all"):
        kind = "all"
    try:
        payload = build_shot_asset_timing_query(
            store,
            ctx.script_id,
            shot_id=shot_id,
            shot_ids=shot_ids,
            asset_kind=kind,  # type: ignore[arg-type]
        )
    except ValueError as exc:
        return _validation_error(str(exc))
    obs_prefix = str(args.get("observation", "")).strip() or (
        f"已查询 {payload['shot_count']} 镜资产时长（{payload.get('asset_kind', 'all')}）。"
    )
    return ToolResult(
        observation=f"{obs_prefix}\n\n{json.dumps(payload, ensure_ascii=False, indent=2)}",
        structured=payload,
    )


def handle_sync_actual_assets(
    store: MemoryStore, ctx: AgentRunContext, args: dict[str, Any]
) -> ToolResult:
    """刷新实测资产时长与规划偏差，并运行音画分层协调。"""
    try:
        result = sync_actual_assets(store, ctx.script_id)
    except ValueError as exc:
        return _validation_error(str(exc))
    try:
        from core.edit.av_sync import reconcile_script_av

        av_result = reconcile_script_av(store, ctx.script_id, mode="hybrid", persist=True)
        result = {**result, "av_sync": av_result}
    except Exception as av_exc:
        result = {**result, "av_sync_error": str(av_exc)}
    schedule_save(store, immediate=True)
    obs_prefix = str(args.get("observation", "")).strip() or (
        f"已同步实测资产，偏差镜头 {result.get('synced_shot_count', 0)} 个。"
    )
    av = result.get("av_sync") or {}
    if av.get("auto_applied_count"):
        obs_prefix += f" 自动协调 {av['auto_applied_count']} 镜。"
    if av.get("need_regen_shot_ids"):
        obs_prefix += f" 需 Agent 复核：{', '.join(av['need_regen_shot_ids'][:5])}。"
    return ToolResult(
        observation=f"{obs_prefix}\n\n{json.dumps(result, ensure_ascii=False, indent=2)}",
        structured=result,
    )


def handle_analyze_av_sync(
    store: MemoryStore, ctx: AgentRunContext, args: dict[str, Any]
) -> ToolResult:
    """分析剧本音画时长偏差（不写回，或按 mode 应用）。"""
    from core.edit.av_sync import reconcile_script_av

    mode = str(args.get("mode") or "analyze_only").strip()
    if mode not in ("hybrid", "auto_only", "analyze_only"):
        mode = "analyze_only"
    raw_ids = args.get("shot_ids")
    shot_ids = [str(x) for x in raw_ids] if isinstance(raw_ids, list) else None
    persist = mode != "analyze_only"
    try:
        result = reconcile_script_av(
            store, ctx.script_id, mode=mode, shot_ids=shot_ids, persist=persist  # type: ignore[arg-type]
        )
    except ValueError as exc:
        return _validation_error(str(exc))
    if persist:
        schedule_save(store, immediate=True)
    obs = str(args.get("observation", "")).strip() or (
        f"音画分析完成：{result.get('shot_count', 0)} 镜，"
        f"自动 {result.get('auto_applied_count', 0)}，"
        f"待选 {len(result.get('needs_user_choice_shot_ids') or [])}，"
        f"打回 {len(result.get('need_regen_shot_ids') or [])}。"
    )
    return ToolResult(
        observation=f"{obs}\n\n{json.dumps(result, ensure_ascii=False, indent=2)}",
        structured=result,
    )


def handle_review_and_restructure(
    store: MemoryStore, ctx: AgentRunContext, args: dict[str, Any]
) -> ToolResult:
    """复核并重排分镜（preflight 后执行）。"""
    ops = args.get("restructure_ops") or []
    patches = args.get("patches") or args.get("shot_patches") or []
    return _apply_refine_mutation(
        store,
        ctx.script_id,
        ops=ops if isinstance(ops, list) else [],
        patches=patches if isinstance(patches, list) else [],
        observation=str(args.get("observation", "")),
    )


def handle_review_shot(
    store: MemoryStore, ctx: AgentRunContext, args: dict[str, Any]
) -> ToolResult:
    """单镜复核：增量 patch 与结构 adjust（避免批量 JSON 截断）。"""
    shot_id = str(args.get("shot_id") or "").strip()
    plan = store.get_video_plan_for_script(ctx.script_id)
    patch_raw = args.get("patch")
    op_raw = args.get("restructure_op")
    errors = validate_review_shot_input(
        plan,
        shot_id=shot_id,
        patch=patch_raw,
        restructure_op=op_raw,
    )
    if errors:
        return _validation_error("; ".join(errors))

    patches: list[dict[str, Any]] = []
    if isinstance(patch_raw, dict) and patch_raw:
        patches = [{**patch_raw, "shot_id": shot_id}]

    ops: list[dict[str, Any]] = []
    if isinstance(op_raw, dict) and op_raw:
        op = dict(op_raw)
        op.setdefault("shot_id", shot_id)
        ops = [op]

    return _apply_refine_mutation(
        store,
        ctx.script_id,
        ops=ops,
        patches=patches,
        observation=str(args.get("observation", "")),
        action="review_shot",
        target_shot_id=shot_id,
    )


def handle_persist_review(
    store: MemoryStore, ctx: AgentRunContext, args: dict[str, Any]
) -> ToolResult:
    """保存分镜复核结果并确认 detail_revision。"""
    vp = store.get_video_plan_for_script(ctx.script_id)
    if not vp:
        return _validation_error("persist_review 前须已有 VideoPlan 详设")
    store.set_video_plan(vp)
    schedule_save(store, immediate=True)
    summary = str(args.get("observation", "")).strip() or (
        f"分镜复核已保存，detail_revision={vp.detail_revision}。"
    )
    structured = {
        "action": "persist_review",
        "summary": summary[:500],
        "plan_id": vp.id,
        "detail_revision": vp.detail_revision,
    }
    return ToolResult(
        observation=f"{summary}\n\n{json.dumps(structured, ensure_ascii=False, indent=2)}",
        structured=structured,
    )


def handle_update_frames(
    store: MemoryStore, ctx: AgentRunContext, args: dict[str, Any]
) -> ToolResult:
    """将 display_instructions 合并进 frame 文字资产 notes。"""
    vp = store.get_video_plan_for_script(ctx.script_id)
    if not vp or not vp.shots:
        return _validation_error("update_frames 前须已有 VideoPlan")
    count = update_frames_from_shot_detail(store, ctx.script_id)
    schedule_save(store, immediate=True)
    obs_prefix = str(args.get("observation", "")).strip() or f"已更新 {count} 个 frame 资产备注。"
    structured = {"updated_frame_count": count}
    return ToolResult(
        observation=f"{obs_prefix}\n\n{json.dumps(structured, ensure_ascii=False)}",
        structured=structured,
    )


def handle_get_plan(
    store: MemoryStore, ctx: AgentRunContext, args: dict[str, Any]
) -> ToolResult:
    """读取含 shot_detail 的视频计划稿。"""
    vp = store.get_video_plan_for_script(ctx.script_id)
    if not vp:
        structured = {
            "shot_count": 0,
            "shots": [],
            "message": "当前无视频计划稿。请先完成分镜规划与 TTS。",
        }
        obs_prefix = str(args.get("observation", "")).strip()
        obs = obs_prefix or structured["message"]
        return ToolResult(
            observation=f"{obs}\n\n{json.dumps(structured, ensure_ascii=False, indent=2)}",
            structured=structured,
        )
    shots = []
    for s in sorted(vp.shots, key=lambda x: x.order):
        block: dict[str, Any] = {
            "id": s.id,
            "order": s.order,
            "duration_ms": s.duration_ms,
            "title": s.title,
            "summary": s.summary,
            "review_note": s.review_note,
            "need_regen": s.need_regen,
            "sub_shots": [v.model_dump() for v in s.sub_shots],
            "video_tracks": [t.model_dump() for t in s.video_tracks],
            "audio_tracks": [t.model_dump() for t in s.audio_tracks],
            "subtitles": [sub.model_dump() for sub in s.subtitles],
        }
        shots.append(block)
    structured = {
        "plan_id": vp.id,
        "mode": vp.mode.value,
        "detail_revision": vp.detail_revision,
        "shot_count": len(shots),
        "shots": shots,
    }
    obs_prefix = (
        str(args.get("observation", "")).strip()
        or f"计划稿 {vp.id}，详设版本 {vp.detail_revision}，共 {len(shots)} 镜。"
    )
    return ToolResult(
        observation=f"{obs_prefix}\n\n{json.dumps(structured, ensure_ascii=False, indent=2)}",
        structured=structured,
    )


HANDLERS = {
    "get_shot_details": handle_get_shot_details,
    "get_shot_asset_timing": handle_get_shot_asset_timing,
    "get_refine_plan": handle_get_plan,
    "sync_actual_assets": handle_sync_actual_assets,
    "analyze_av_sync": handle_analyze_av_sync,
    "review_and_restructure": handle_review_and_restructure,
    "review_shot": handle_review_shot,
    "update_frames": handle_update_frames,
    "persist_review": handle_persist_review,
}
