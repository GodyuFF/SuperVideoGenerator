"""VideoPlan 用户编辑服务：单镜 patch 与结构性 ops。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from core.edit.shot_duration import reconcile_shot_duration_from_media
from core.edit.shot_sub_shot_frame_sync import sync_shot_sub_shot_frame_assets
from core.edit.shot_sub_shot_video_clip_sync import sync_shot_sub_shot_video_clip_assets
from core.edit.shot_validate import validate_shot_structure
from core.edit.storyboard_restructure import apply_restructure_ops, invalidate_shot_tts
from core.guards.reference import ScriptEditGuard, ScriptEditGuardError
from core.llm.master.actions import uses_ai_video_pipeline
from core.models.entities import Shot, VideoPlan, VideoStyleMode
from core.store.memory import MemoryStore


class VideoPlanRevisionError(Exception):
    """乐观锁 detail_revision 冲突。"""

    def __init__(self, expected: int, actual: int) -> None:
        self.expected = expected
        self.actual = actual
        super().__init__(f"detail_revision 冲突：期望 {expected}，当前 {actual}")


class VideoPlanNotFoundError(Exception):
    """未找到视频计划稿。"""


_TTS_AFFECTING_TOP_KEYS = frozenset({"audio_tracks", "subtitles", "duration_ms"})
_TRACK_KEYS = frozenset({"sub_shots", "video_tracks", "audio_tracks", "subtitles"})


def _utc_now_iso() -> str:
    """返回当前 UTC ISO 时间戳。"""
    return datetime.now(timezone.utc).isoformat()


def _assert_script_editable(store: MemoryStore, script_id: str) -> None:
    """校验剧本处于可编辑态。"""
    script = store.get_script(script_id)
    if script is None:
        raise ValueError("剧本不存在")
    ScriptEditGuard.assert_editable(script)


def _check_revision(plan: VideoPlan, expected_revision: int | None) -> None:
    """校验 If-Match revision。"""
    if expected_revision is None:
        return
    if plan.detail_revision != expected_revision:
        raise VideoPlanRevisionError(expected_revision, plan.detail_revision)


def _get_plan_or_raise(store: MemoryStore, script_id: str) -> VideoPlan:
    """获取视频计划稿，不存在时抛错。"""
    plan = store.get_video_plan_for_script(script_id)
    if not plan or not plan.shots:
        raise VideoPlanNotFoundError("未找到视频计划稿")
    return plan


def _patch_invalidate_tts(body: dict[str, Any]) -> bool:
    """判断 patch 是否影响 TTS 需失效（改动音频/字幕/时长）。"""
    return any(k in body and body[k] is not None for k in _TTS_AFFECTING_TOP_KEYS)


def _build_side_effects(
    *,
    tts_stale_shot_ids: list[str],
) -> dict[str, Any]:
    """组装副作用摘要。"""
    return {
        "tts_stale_shot_ids": tts_stale_shot_ids,
        "tts_stale": bool(tts_stale_shot_ids),
    }


def _validate_shots_or_raise(shots: list[Shot]) -> None:
    """校验镜内结构自洽，失败抛 ValueError。"""
    for shot in shots:
        issues = validate_shot_structure(shot)
        if issues:
            raise ValueError(f"镜头 {shot.id} 结构校验失败：" + "；".join(issues[:5]))


def get_video_plan_view(store: MemoryStore, script_id: str) -> dict[str, Any]:
    """返回 video-plan 视图（含 shot_timings 与 editable）。"""
    from core.edit.shot_timing import resolve_shot_timings

    script = store.get_script(script_id)
    editable = ScriptEditGuard.is_editable(script) if script else False
    vp = store.get_video_plan_for_script(script_id)
    if not vp:
        from core.models.entities import VideoPlan

        payload = VideoPlan(script_id=script_id).model_dump()
        payload["shot_timings"] = []
        payload["editable"] = editable
        return payload
    payload = vp.model_dump()
    payload["shot_timings"] = [t.to_dict() for t in resolve_shot_timings(store, script_id, plan=vp)]
    payload["editable"] = editable
    return payload


def patch_shot_plan_fields(
    store: MemoryStore,
    script_id: str,
    shot_id: str,
    body: dict[str, Any],
    *,
    expected_revision: int | None = None,
) -> dict[str, Any]:
    """单镜字段 patch，递增 detail_revision 并处理副作用。"""
    _assert_script_editable(store, script_id)
    plan = _get_plan_or_raise(store, script_id)
    _check_revision(plan, expected_revision)

    idx = next((i for i, s in enumerate(plan.shots) if s.id == shot_id), None)
    if idx is None:
        raise ValueError(f"镜头 {shot_id} 不存在")

    shot = plan.shots[idx]
    updates: dict[str, Any] = {}

    for key in (
        "title",
        "summary",
        "duration_ms",
        "review_note",
        "need_regen",
        "regen_reason",
        "sync_policy",
        "lip_sync_required",
        "sync_notes",
        "proposed_sync_actions",
    ):
        if key in body and body[key] is not None:
            updates[key] = body[key]

    if "display_instructions" in body and body["display_instructions"] is not None:
        if "review_note" not in body or body["review_note"] is None:
            updates["review_note"] = body["display_instructions"]

    # 整体替换镜内轨道（visuals/video_tracks/audio_tracks/subtitles）
    if any(k in body for k in _TRACK_KEYS):
        from core.llm.agent.llm_action import parse_single_shot_from_data

        parsed = parse_single_shot_from_data(
            {**body, "id": shot.id, "order": shot.order}
        )
        if parsed is not None:
            merge_fields: dict[str, Any] = {}
            if "sub_shots" not in body:
                merge_fields["sub_shots"] = shot.sub_shots
            # 仅替换 visuals 时须用解析结果中的 video_tracks（由 visuals 派生），勿保留旧轨
            if "video_tracks" not in body and "sub_shots" not in body:
                merge_fields["video_tracks"] = shot.video_tracks
            if "audio_tracks" not in body:
                merge_fields["audio_tracks"] = shot.audio_tracks
            if "subtitles" not in body:
                merge_fields["subtitles"] = shot.subtitles
            shot = parsed.model_copy(update=merge_fields)
    if updates:
        shot = shot.model_copy(update=updates)

    # 镜时长始终按绑定音视频实测与轨片段跨度推导（含延长配音终点）
    shot = reconcile_shot_duration_from_media(store, shot)

    refined_motion = str(body.get("camera_motion_refined") or "").strip()
    if refined_motion and shot.sub_shots:
        sub_shots = list(shot.sub_shots)
        sub_shots[0] = sub_shots[0].model_copy(update={"camera_motion": refined_motion})
        shot = shot.model_copy(update={"sub_shots": sub_shots})
        for track in shot.video_tracks:
            if track.z_index == 0 and track.clips:
                clips = list(track.clips)
                clips[0] = clips[0].model_copy(
                    update={"camera_motion": refined_motion}
                )
                shot = shot.model_copy(
                    update={
                        "video_tracks": [
                            track.model_copy(update={"clips": clips})
                            if t.id == track.id
                            else t
                            for t in shot.video_tracks
                        ]
                    }
                )
                break

    shot = sync_shot_sub_shot_frame_assets(store, script_id, shot)
    if uses_ai_video_pipeline(plan.mode):
        shot = sync_shot_sub_shot_video_clip_assets(store, script_id, shot)

    from core.assets.element_refs import normalize_element_refs, validate_element_refs_for_owner

    for sub in shot.sub_shots:
        refs = normalize_element_refs(sub.element_refs if sub.element_refs else {})
        if not refs:
            continue
        owner = ""
        if sub.images:
            owner = str(sub.images[0].frame_asset_id or "").strip()
        validate_element_refs_for_owner(store, owner or None, refs)

    _validate_shots_or_raise([shot])

    tts_stale: list[str] = []
    if _patch_invalidate_tts(body):
        invalidate_shot_tts(store, script_id, shot_id)
        tts_stale.append(shot_id)

    shots = list(plan.shots)
    shots[idx] = shot
    new_plan = plan.model_copy(
        update={
            "shots": shots,
            "detail_revision": plan.detail_revision + 1,
        }
    )
    store.set_video_plan(new_plan)

    view = get_video_plan_view(store, script_id)
    view["side_effects"] = _build_side_effects(tts_stale_shot_ids=tts_stale)
    return view


def apply_video_plan_ops(
    store: MemoryStore,
    script_id: str,
    ops: list[dict[str, Any]],
    *,
    expected_revision: int | None = None,
) -> dict[str, Any]:
    """批量执行结构性 ops。"""
    _assert_script_editable(store, script_id)
    plan = store.get_video_plan_for_script(script_id)
    if not plan:
        raise VideoPlanNotFoundError("未找到视频计划稿")
    _check_revision(plan, expected_revision)

    tts_stale: list[str] = []
    for op in ops:
        if not isinstance(op, dict):
            continue
        kind = str(op.get("op") or op.get("kind") or "").strip().lower()
        shot_id = str(op.get("shot_id") or op.get("id") or "").strip()
        if kind in {"adjust", "split", "delete", "regen"} and shot_id:
            tts_stale.append(shot_id)
        elif kind == "merge":
            for sid in op.get("shot_ids") or []:
                if sid:
                    tts_stale.append(str(sid))

    apply_restructure_ops(store, script_id, ops)

    view = get_video_plan_view(store, script_id)
    view["side_effects"] = _build_side_effects(
        tts_stale_shot_ids=list(dict.fromkeys(tts_stale)),
    )
    return view
