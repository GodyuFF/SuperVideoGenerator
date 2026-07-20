"""音画协调编排器：探测 → 分级 → 自动修复 / 用户选择 / Agent 打回。"""

from __future__ import annotations

import json
from typing import Any, Literal

from core.edit.av_sync.apply import apply_sync_action_to_shot
from core.edit.av_sync.policy import classify_tier, compute_delta_ms, resolve_sync_policy
from core.edit.av_sync.probe import probe_shot_durations
from core.edit.av_sync.strategies import rank_strategies
from core.edit.av_sync.types import AvSyncResult, SyncAction, SyncStatus
from core.models.entities import Shot, VideoPlan
from core.store.memory import MemoryStore

ReconcileMode = Literal["hybrid", "auto_only", "analyze_only"]


def build_regen_reason(
    probe: Any,
    policy: str,
    delta_ms: int,
    candidates: list[SyncAction],
) -> dict[str, Any]:
    """构建结构化 regen_reason（可 JSON 序列化写入 Shot.regen_reason）。"""
    recommended = candidates[0].kind if candidates else "regen_shot"
    alternatives = [c.kind for c in candidates[1:4]]
    code = "tts_longer_than_video" if delta_ms > 0 and policy == "narration_master" else (
        "video_longer_than_tts" if policy == "visual_master" else "av_duration_mismatch"
    )
    return {
        "code": code,
        "delta_ms": int(delta_ms),
        "tts_ms": int(probe.tts_ms or 0),
        "video_ms": int(probe.video_ms or 0),
        "slot_ms": int(probe.slot_ms or 0),
        "sync_policy": policy,
        "recommended": recommended,
        "alternatives": alternatives,
    }


def format_regen_reason_text(reason: dict[str, Any]) -> str:
    """将结构化原因压成人类可读摘要（兼容旧字符串字段）。"""
    code = reason.get("code") or "av_duration_mismatch"
    delta = reason.get("delta_ms") or 0
    rec = reason.get("recommended") or ""
    return json.dumps(reason, ensure_ascii=False) if reason else f"{code}: delta={delta}ms → {rec}"


def reconcile_shot_av(
    store: MemoryStore,
    shot: Shot,
    *,
    plan: VideoPlan | None = None,
    mode: ReconcileMode = "hybrid",
    tts_by_shot: dict[str, str] | None = None,
) -> AvSyncResult:
    """对单镜执行 Plan-Execute-Verify 风格的音画协调。"""
    probe = probe_shot_durations(store, shot, plan=plan, tts_by_shot=tts_by_shot)
    policy = resolve_sync_policy(shot, probe)
    delta = compute_delta_ms(probe, policy)
    # balanced 用绝对值分级
    tier = classify_tier(delta, shot, abs_delta=True)
    candidates = rank_strategies(
        probe, policy, lip_sync_required=bool(shot.lip_sync_required)
    )

    if tier == 0 or mode == "analyze_only":
        status: SyncStatus = "ok" if tier == 0 else (
            "needs_user_choice" if tier == 2 else (
                "needs_agent_review" if tier >= 3 else "ok"
            )
        )
        if mode == "analyze_only" and tier == 1:
            status = "needs_user_choice"
        return AvSyncResult(
            shot_id=shot.id,
            status="ok" if tier == 0 else status,
            tier=tier,
            policy=policy,
            delta_ms=delta,
            probe=probe,
            options=candidates[:3] if tier > 0 else [],
            shot=shot,
        )

    if tier == 1 and mode in ("hybrid", "auto_only"):
        action = next((c for c in candidates if c.auto_eligible), None)
        if action is not None:
            # 自动路径：rate/freeze 后再确保槽位扩展
            updated = apply_sync_action_to_shot(shot, action)
            if action.kind in ("video_rate", "freeze_tail", "combined_rate") and int(
                action.params.get("target_ms") or 0
            ) > 0:
                from core.edit.av_sync.types import SyncAction as SA

                updated = apply_sync_action_to_shot(
                    updated,
                    SA(
                        kind="extend_video_slot",
                        params={"target_ms": int(action.params["target_ms"])},
                        quality_score=0,
                        auto_eligible=True,
                    ),
                )
            updated = updated.model_copy(
                update={
                    "sync_policy": policy,
                    "proposed_sync_actions": [],
                    "need_regen": False,
                    "regen_reason": "",
                }
            )
            return AvSyncResult(
                shot_id=shot.id,
                status="auto_applied",
                tier=tier,
                policy=policy,
                delta_ms=delta,
                probe=probe,
                applied=action,
                options=candidates[:3],
                shot=updated,
            )

    if tier == 2 or (tier == 1 and mode == "hybrid"):
        options = candidates[:3]
        updated = shot.model_copy(
            update={
                "sync_policy": policy,
                "proposed_sync_actions": [o.to_dict() for o in options],
            }
        )
        return AvSyncResult(
            shot_id=shot.id,
            status="needs_user_choice",
            tier=max(tier, 1),  # type: ignore[arg-type]
            policy=policy,
            delta_ms=delta,
            probe=probe,
            options=options,
            shot=updated,
        )

    # Tier 3
    reason = build_regen_reason(probe, policy, delta, candidates)
    updated = shot.model_copy(
        update={
            "sync_policy": policy,
            "need_regen": True,
            "regen_reason": format_regen_reason_text(reason),
            "proposed_sync_actions": [o.to_dict() for o in candidates[:3]],
            "sync_notes": str(shot.sync_notes or "")
            or f"音画偏差 {abs(delta)}ms，需 Agent 复核",
        }
    )
    return AvSyncResult(
        shot_id=shot.id,
        status="needs_agent_review",
        tier=3,
        policy=policy,
        delta_ms=delta,
        probe=probe,
        options=candidates[:3],
        regen_reason=reason,
        shot=updated,
    )


def reconcile_script_av(
    store: MemoryStore,
    script_id: str,
    *,
    mode: ReconcileMode = "hybrid",
    shot_ids: list[str] | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    """对剧本下全部（或指定）镜头执行音画协调并可选写回 VideoPlan。"""
    plan = store.get_video_plan_for_script(script_id)
    if not plan or not plan.shots:
        return {
            "script_id": script_id,
            "shot_count": 0,
            "results": [],
            "need_regen_shot_ids": [],
            "needs_user_choice_shot_ids": [],
            "auto_applied_count": 0,
        }

    from core.edit.timeline import build_tts_by_shot

    tts_by_shot = build_tts_by_shot(store, script_id)
    id_filter = set(shot_ids) if shot_ids else None
    results: list[AvSyncResult] = []
    updated_shots: list[Shot] = []
    changed = False

    for shot in sorted(plan.shots, key=lambda s: s.order):
        if id_filter is not None and shot.id not in id_filter:
            updated_shots.append(shot)
            continue
        result = reconcile_shot_av(
            store, shot, plan=plan, mode=mode, tts_by_shot=tts_by_shot
        )
        results.append(result)
        new_shot = result.shot if isinstance(result.shot, Shot) else shot
        if new_shot is not shot and new_shot != shot:
            changed = True
        # 比较关键字段是否变化
        if (
            new_shot.duration_ms != shot.duration_ms
            or new_shot.need_regen != shot.need_regen
            or new_shot.regen_reason != shot.regen_reason
            or new_shot.proposed_sync_actions != shot.proposed_sync_actions
            or new_shot.sync_policy != shot.sync_policy
            or new_shot.video_tracks != shot.video_tracks
            or new_shot.audio_tracks != shot.audio_tracks
        ):
            changed = True
        updated_shots.append(new_shot)

    if persist and changed:
        new_plan = plan.model_copy(
            update={
                "shots": updated_shots,
                "detail_revision": plan.detail_revision + 1,
            }
        )
        store.set_video_plan(new_plan)

    return {
        "script_id": script_id,
        "shot_count": len(results),
        "results": [r.to_dict() for r in results],
        "need_regen_shot_ids": [
            r.shot_id for r in results if r.status == "needs_agent_review"
        ],
        "needs_user_choice_shot_ids": [
            r.shot_id for r in results if r.status == "needs_user_choice"
        ],
        "auto_applied_count": sum(
            1 for r in results if r.status == "auto_applied"
        ),
        "detail_revision": (
            store.get_video_plan_for_script(script_id).detail_revision
            if store.get_video_plan_for_script(script_id)
            else plan.detail_revision
        ),
    }


def apply_named_sync_action(
    store: MemoryStore,
    script_id: str,
    shot_id: str,
    action: SyncAction | dict[str, Any],
) -> dict[str, Any]:
    """用户选择 Tier2 方案后应用到指定镜并写回。"""
    plan = store.get_video_plan_for_script(script_id)
    if not plan:
        raise ValueError("未找到视频计划稿")
    idx = next((i for i, s in enumerate(plan.shots) if s.id == shot_id), None)
    if idx is None:
        raise ValueError(f"镜头 {shot_id} 不存在")
    act = action if isinstance(action, SyncAction) else SyncAction.from_dict(action)
    shot = plan.shots[idx]
    updated = apply_sync_action_to_shot(shot, act)
    if act.kind in ("video_rate", "freeze_tail", "combined_rate"):
        target = int(act.params.get("target_ms") or 0)
        if target > 0:
            updated = apply_sync_action_to_shot(
                updated,
                SyncAction(
                    kind="extend_video_slot",
                    params={"target_ms": target},
                    quality_score=0,
                    auto_eligible=True,
                ),
            )
    # 结构级：仅标记 need_regen
    if act.kind in ("split_shot", "extend_video_gen", "rewrite_narration", "regen_shot"):
        reason = {
            "code": "user_chose_structural_fix",
            "recommended": act.kind,
            "delta_ms": 0,
            "tts_ms": 0,
            "video_ms": 0,
            "sync_policy": shot.sync_policy,
            "alternatives": [],
        }
        updated = updated.model_copy(
            update={
                "need_regen": True,
                "regen_reason": format_regen_reason_text(reason),
                "proposed_sync_actions": [],
            }
        )
    else:
        updated = updated.model_copy(
            update={
                "need_regen": False,
                "regen_reason": "",
                "proposed_sync_actions": [],
            }
        )
    shots = list(plan.shots)
    shots[idx] = updated
    store.set_video_plan(
        plan.model_copy(
            update={"shots": shots, "detail_revision": plan.detail_revision + 1}
        )
    )
    return {
        "shot_id": shot_id,
        "applied": act.to_dict(),
        "detail_revision": plan.detail_revision + 1,
        "shot": updated.model_dump(),
    }
