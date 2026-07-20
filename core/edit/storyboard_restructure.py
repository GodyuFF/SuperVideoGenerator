"""分镜结构性复核操作：拆分/合并/增删/重排镜头（新模型：镜内多轨 Shot）。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from core.edit.shot_flatten import effective_shot_duration_ms
from core.edit.shot_validate import validate_shot_structure
from core.models.entities import (
    Shot,
    ShotSubtitle,
    ShotVideoTrack,
    ShotSubShot,
    VideoPlan,
    new_id,
    normalize_shot_orders,
)
from core.store.memory import MemoryStore

RestructureOpKind = Literal["adjust", "split", "merge", "add", "delete", "regen", "reorder"]


def _utc_now_iso() -> str:
    """返回当前 UTC ISO 时间戳。"""
    return datetime.now(timezone.utc).isoformat()


def invalidate_shot_tts(store: MemoryStore, script_id: str, shot_id: str) -> None:
    """将镜头关联 TTS 资产标记为 superseded。"""
    for media in store.media_assets.values():
        meta = media.metadata or {}
        if str(meta.get("shot_id") or "") == shot_id and str(meta.get("script_id") or script_id) == script_id:
            media.metadata = {**meta, "superseded": True, "superseded_at": _utc_now_iso()}


def _is_partial_sub_shot_patch(existing: list[ShotSubShot], raw_list: Any) -> bool:
    """判断是否可按 id 增量合并子镜 patch。"""
    if not isinstance(raw_list, list) or not raw_list:
        return False
    known = {s.id for s in existing}
    for item in raw_list:
        if not isinstance(item, dict):
            return False
        sid = str(item.get("id") or "").strip()
        if not sid or sid not in known:
            return False
    return True


def _merge_sub_shots_by_id(
    existing: list[ShotSubShot], raw_list: list[dict[str, Any]]
) -> list[ShotSubShot]:
    """按 id 合并子镜时段 patch，保留未提及字段。"""
    from core.llm.agent.llm_action import _parse_element_refs

    by_id = {s.id: s for s in existing}
    order = [s.id for s in existing]
    for raw in raw_list:
        sid = str(raw.get("id") or "").strip()
        prev = by_id[sid]
        updates: dict[str, Any] = {}
        for key in ("start_ms", "end_ms", "description", "camera_motion"):
            if key in raw and raw[key] is not None:
                if key in ("start_ms", "end_ms"):
                    updates[key] = max(0, int(raw[key]))
                elif key == "description":
                    updates[key] = str(raw[key]).strip()
                else:
                    updates[key] = raw[key]
        if "element_refs" in raw and raw["element_refs"] is not None:
            updates["element_refs"] = _parse_element_refs(raw["element_refs"])
        merged = prev.model_copy(update=updates)
        if "end_ms" in updates and merged.videos:
            span = max(0, int(merged.end_ms or 0) - int(merged.start_ms or 0))
            merged = merged.model_copy(
                update={
                    "videos": [
                        v.model_copy(update={"end_ms": span or int(v.end_ms or 0)})
                        for v in merged.videos
                    ]
                }
            )
        if "start_ms" in updates or "end_ms" in updates:
            from core.edit.sub_shot_produce import clamp_image_timings_to_sub

            merged = clamp_image_timings_to_sub(merged)
        by_id[sid] = merged
    return [by_id[sid] for sid in order]


def _is_partial_track_clip_patch(
    existing_clips: list[Any], raw_clips: Any, *, id_prefix: str
) -> bool:
    """判断 clip 列表是否可按 id 增量合并。"""
    if not isinstance(raw_clips, list) or not raw_clips:
        return False
    known = {str(c.id) for c in existing_clips}
    for item in raw_clips:
        if not isinstance(item, dict):
            return False
        cid = str(item.get("id") or "").strip()
        if not cid or cid not in known:
            return False
    return True


def _merge_audio_tracks_by_id(
    existing: list[Any], raw_list: list[dict[str, Any]]
) -> list[Any]:
    """按 track/clip id 增量合并音频轨。"""
    from core.models.entities import ShotAudioTrack

    by_track_id = {t.id: t for t in existing}
    order = [t.id for t in existing]
    for raw_track in raw_list:
        if not isinstance(raw_track, dict):
            continue
        tid = str(raw_track.get("id") or "").strip()
        if not tid or tid not in by_track_id:
            continue
        track = by_track_id[tid]
        clips_raw = raw_track.get("clips")
        if not isinstance(clips_raw, list):
            continue
        if not _is_partial_track_clip_patch(track.clips, clips_raw, id_prefix="sac"):
            continue
        clip_by_id = {c.id: c for c in track.clips}
        for cr in clips_raw:
            cid = str(cr.get("id") or "").strip()
            prev = clip_by_id[cid]
            updates: dict[str, Any] = {}
            for key in ("start_ms", "end_ms", "text", "media_id", "volume", "character_ref"):
                if key in cr and cr[key] is not None:
                    if key in ("start_ms", "end_ms"):
                        updates[key] = max(0, int(cr[key]))
                    else:
                        updates[key] = cr[key]
            clip_by_id[cid] = prev.model_copy(update=updates)
        by_track_id[tid] = track.model_copy(
            update={"clips": [clip_by_id[c.id] for c in track.clips]}
        )
    return [by_track_id[tid] for tid in order]


def _merge_subtitles_by_id(
    existing: list[ShotSubtitle], raw_list: list[dict[str, Any]]
) -> list[ShotSubtitle]:
    """按 id 增量合并字幕 patch。"""
    if not _is_partial_track_clip_patch(existing, raw_list, id_prefix="ssub"):
        return existing
    by_id = {s.id: s for s in existing}
    order = [s.id for s in existing]
    for raw in raw_list:
        sid = str(raw.get("id") or "").strip()
        prev = by_id[sid]
        updates: dict[str, Any] = {}
        for key in ("start_ms", "end_ms", "text"):
            if key in raw and raw[key] is not None:
                if key == "text":
                    updates[key] = str(raw[key]).strip()
                else:
                    updates[key] = max(0, int(raw[key]))
        by_id[sid] = prev.model_copy(update=updates)
    return [by_id[sid] for sid in order]


def _sync_video_tracks_from_sub_shots(shot: Shot) -> Shot:
    """子镜时段变更后，同步视频轨 clip 起止与 source_sub_shot 对齐。"""
    if not shot.video_tracks or not shot.sub_shots:
        return shot
    sub_by_id = {v.id: v for v in shot.sub_shots}
    new_tracks: list[ShotVideoTrack] = []
    for track in shot.video_tracks:
        new_clips = []
        for clip in track.clips:
            sid = str(getattr(clip, "source_sub_shot_id", "") or "").strip()
            sub = sub_by_id.get(sid)
            if sub is not None:
                new_clips.append(
                    clip.model_copy(
                        update={"start_ms": sub.start_ms, "end_ms": sub.end_ms}
                    )
                )
            else:
                new_clips.append(clip)
        new_tracks.append(track.model_copy(update={"clips": new_clips}))
    return shot.model_copy(update={"video_tracks": new_tracks})


def _apply_adjust(shot: Shot, op: dict[str, Any]) -> Shot:
    """调整单镜标量字段（时长、复核备注等）。"""
    from core.llm.agent.llm_action import parse_single_shot_from_data

    updates: dict[str, Any] = {}
    for key in ("duration_ms", "title", "summary", "review_note"):
        if key in op and op[key] is not None:
            updates[key] = op[key]
    shot = shot.model_copy(update=updates) if updates else shot

    merged_sub_shots = False
    if "sub_shots" in op:
        raw_sub = op["sub_shots"]
        if _is_partial_sub_shot_patch(shot.sub_shots, raw_sub):
            shot = shot.model_copy(
                update={
                    "sub_shots": _merge_sub_shots_by_id(
                        shot.sub_shots, list(raw_sub)  # type: ignore[arg-type]
                    )
                }
            )
            merged_sub_shots = True
        else:
            parsed = parse_single_shot_from_data({**op, "id": shot.id, "order": shot.order})
            if parsed is not None:
                shot = shot.model_copy(update={"sub_shots": parsed.sub_shots})

    if "audio_tracks" in op:
        raw_audio = op["audio_tracks"]
        if isinstance(raw_audio, list) and all(
            isinstance(t, dict) and str(t.get("id") or "") in {a.id for a in shot.audio_tracks}
            for t in raw_audio
        ):
            shot = shot.model_copy(
                update={"audio_tracks": _merge_audio_tracks_by_id(shot.audio_tracks, raw_audio)}
            )
        else:
            parsed = parse_single_shot_from_data({**op, "id": shot.id, "order": shot.order})
            if parsed is not None:
                shot = shot.model_copy(update={"audio_tracks": parsed.audio_tracks})

    if "subtitles" in op:
        raw_subs = op["subtitles"]
        if isinstance(raw_subs, list) and _is_partial_track_clip_patch(
            shot.subtitles, raw_subs, id_prefix="ssub"
        ):
            shot = shot.model_copy(
                update={
                    "subtitles": _merge_subtitles_by_id(shot.subtitles, list(raw_subs))  # type: ignore[arg-type]
                }
            )
        else:
            parsed = parse_single_shot_from_data({**op, "id": shot.id, "order": shot.order})
            if parsed is not None:
                shot = shot.model_copy(update={"subtitles": parsed.subtitles})

    if "video_tracks" in op:
        parsed = parse_single_shot_from_data({**op, "id": shot.id, "order": shot.order})
        if parsed is not None:
            shot = shot.model_copy(update={"video_tracks": parsed.video_tracks})
    elif merged_sub_shots:
        shot = _sync_video_tracks_from_sub_shots(shot)

    if "duration_ms" in op and op["duration_ms"] is not None:
        shot = _clamp_shot_tracks_to_duration(shot, int(op["duration_ms"]))

    return shot


def _clamp_shot_tracks_to_duration(shot: Shot, duration_ms: int) -> Shot:
    """镜时长变更后，收缩子镜/视频/音频/字幕终点至镜有效时长。"""
    duration = max(0, int(duration_ms))

    def _cap_end(end: int) -> int:
        return min(max(0, int(end)), duration)

    sub_shots = [v.model_copy(update={"end_ms": _cap_end(v.end_ms)}) for v in shot.sub_shots]
    audio_tracks = [
        t.model_copy(
            update={
                "clips": [
                    c.model_copy(update={"end_ms": _cap_end(c.end_ms)}) for c in t.clips
                ]
            }
        )
        for t in shot.audio_tracks
    ]
    subtitles = [s.model_copy(update={"end_ms": _cap_end(s.end_ms)}) for s in shot.subtitles]
    shot = shot.model_copy(
        update={
            "sub_shots": sub_shots,
            "audio_tracks": audio_tracks,
            "subtitles": subtitles,
            "duration_ms": duration,
        }
    )
    return _sync_video_tracks_from_sub_shots(shot)


def _shift_shot(shot: Shot, offset_ms: int) -> Shot:
    """把一个镜内多轨结构整体平移 offset_ms（用于合并拼接）。"""
    sub_shots = [
        v.model_copy(update={"start_ms": v.start_ms + offset_ms, "end_ms": v.end_ms + offset_ms})
        for v in shot.sub_shots
    ]
    video_tracks = [
        t.model_copy(
            update={
                "clips": [
                    c.model_copy(
                        update={"start_ms": c.start_ms + offset_ms, "end_ms": c.end_ms + offset_ms}
                    )
                    for c in t.clips
                ]
            }
        )
        for t in shot.video_tracks
    ]
    audio_tracks = [
        t.model_copy(
            update={
                "clips": [
                    c.model_copy(
                        update={"start_ms": c.start_ms + offset_ms, "end_ms": c.end_ms + offset_ms}
                    )
                    for c in t.clips
                ]
            }
        )
        for t in shot.audio_tracks
    ]
    subtitles = [
        s.model_copy(update={"start_ms": s.start_ms + offset_ms, "end_ms": s.end_ms + offset_ms})
        for s in shot.subtitles
    ]
    return shot.model_copy(
        update={
            "sub_shots": sub_shots,
            "video_tracks": video_tracks,
            "audio_tracks": audio_tracks,
            "subtitles": subtitles,
        }
    )


def _apply_split(store: MemoryStore, shots: list[Shot], shot_id: str, op: dict[str, Any]) -> list[Shot]:
    """将一镜拆为两镜（依据 op.new_shots）。"""
    from core.llm.agent.llm_action import parse_shots_from_data

    idx = next((i for i, s in enumerate(shots) if s.id == shot_id), None)
    if idx is None:
        return shots
    original = shots[idx]
    new_shots_raw = op.get("new_shots")
    if not isinstance(new_shots_raw, list) or len(new_shots_raw) < 2:
        return shots
    parsed = parse_shots_from_data(store, new_shots_raw)
    if len(parsed) < 2:
        return shots
    first = parsed[0].model_copy(update={"id": original.id, "order": original.order})
    second = parsed[1].model_copy(update={"id": new_id("shot"), "order": original.order + 1})
    out = shots[:idx] + [first, second] + shots[idx + 1 :]
    return normalize_shot_orders(out)


def _merge_shots(shots_to_merge: list[Shot]) -> Shot:
    """把多镜的镜内多轨结构按时序拼接为一镜。"""
    base = shots_to_merge[0]
    merged = base.model_copy()
    offset = effective_shot_duration_ms(base)
    for nxt in shots_to_merge[1:]:
        shifted = _shift_shot(nxt, offset)
        # 合并视觉画面
        merged = merged.model_copy(update={"sub_shots": merged.sub_shots + shifted.sub_shots})
        # 合并视频轨（按 z_index）
        vtracks = {t.z_index: t for t in merged.video_tracks}
        for t in shifted.video_tracks:
            if t.z_index in vtracks:
                cur = vtracks[t.z_index]
                vtracks[t.z_index] = cur.model_copy(update={"clips": cur.clips + t.clips})
            else:
                vtracks[t.z_index] = t
        merged = merged.model_copy(
            update={"video_tracks": [vtracks[z] for z in sorted(vtracks)]}
        )
        # 合并音频轨（按 kind+name）
        atracks = {(t.kind, t.name): t for t in merged.audio_tracks}
        for t in shifted.audio_tracks:
            key = (t.kind, t.name)
            if key in atracks:
                cur = atracks[key]
                atracks[key] = cur.model_copy(update={"clips": cur.clips + t.clips})
            else:
                atracks[key] = t
        merged = merged.model_copy(update={"audio_tracks": list(atracks.values())})
        merged = merged.model_copy(update={"subtitles": merged.subtitles + shifted.subtitles})
        offset += effective_shot_duration_ms(nxt)
    return merged.model_copy(update={"duration_ms": offset})


def _apply_merge(store: MemoryStore, shots: list[Shot], shot_ids: list[str], op: dict[str, Any]) -> list[Shot]:
    """合并多镜为一镜。"""
    from core.llm.agent.llm_action import parse_shots_from_data

    if len(shot_ids) < 2:
        return shots
    id_set = set(shot_ids)
    to_merge = [s for s in shots if s.id in id_set]
    if len(to_merge) < 2:
        return shots
    merged_raw = op.get("merged_shot")
    if isinstance(merged_raw, dict):
        parsed = parse_shots_from_data(store, [merged_raw])
        merged = parsed[0] if parsed else _merge_shots(to_merge)
    else:
        merged = _merge_shots(to_merge)
    merged = merged.model_copy(update={"id": to_merge[0].id, "order": to_merge[0].order})
    remaining = [s for s in shots if s.id not in id_set]
    insert_at = min(s.order for s in to_merge)
    out = [s for s in remaining if s.order < insert_at]
    out.append(merged)
    out.extend(sorted([s for s in remaining if s.order > insert_at], key=lambda x: x.order))
    return normalize_shot_orders(out)


def _apply_add(store: MemoryStore, shots: list[Shot], op: dict[str, Any]) -> list[Shot]:
    """在指定 order 后插入新镜头。"""
    from core.llm.agent.llm_action import parse_shots_from_data

    raw = op.get("new_shot")
    if not isinstance(raw, dict):
        return shots
    parsed = parse_shots_from_data(store, [raw])
    if not parsed:
        return shots
    new_shot = parsed[0].model_copy(update={"id": new_id("shot")})
    after_order = int(op.get("after_order", len(shots) - 1))
    out: list[Shot] = []
    for s in shots:
        out.append(s)
        if s.order == after_order:
            out.append(new_shot)
    if after_order >= len(shots) - 1 and new_shot not in out:
        out.append(new_shot)
    return normalize_shot_orders(out)


def _apply_delete(shots: list[Shot], shot_id: str) -> list[Shot]:
    """删除指定镜头。"""
    return normalize_shot_orders([s for s in shots if s.id != shot_id])


def _apply_reorder(shots: list[Shot], ordered_shot_ids: list[str]) -> list[Shot]:
    """按 ordered_shot_ids 重排镜头并重新赋值 order。"""
    by_id = {s.id: s for s in shots}
    if len(ordered_shot_ids) != len(shots):
        raise ValueError("ordered_shot_ids 数量须与镜头数一致")
    if set(ordered_shot_ids) != set(by_id.keys()):
        raise ValueError("ordered_shot_ids 须包含全部镜头 ID")
    return [by_id[sid].model_copy(update={"order": i}) for i, sid in enumerate(ordered_shot_ids)]


def _apply_regen(shot: Shot, op: dict[str, Any]) -> Shot:
    """标记镜头需补图/补片。"""
    return shot.model_copy(
        update={
            "need_regen": True,
            "regen_reason": str(op.get("regen_reason") or "复核后需重生产"),
            "review_revision": shot.review_revision + 1,
        }
    )


def apply_restructure_ops(
    store: MemoryStore,
    script_id: str,
    ops: list[dict[str, Any]],
) -> VideoPlan:
    """确定性执行分镜结构性复核操作列表。"""
    plan = store.get_video_plan_for_script(script_id)
    if not plan or not plan.shots:
        raise ValueError("未找到视频计划稿")

    shots = list(plan.shots)
    for op in ops:
        if not isinstance(op, dict):
            continue
        kind = str(op.get("op") or op.get("kind") or "").strip().lower()
        shot_id = str(op.get("shot_id") or op.get("id") or "").strip()

        if kind == "adjust" and shot_id:
            idx = next((i for i, s in enumerate(shots) if s.id == shot_id), None)
            if idx is not None:
                shots[idx] = _apply_adjust(shots[idx], op)
                invalidate_shot_tts(store, script_id, shot_id)
        elif kind == "split" and shot_id:
            shots = _apply_split(store, shots, shot_id, op)
            invalidate_shot_tts(store, script_id, shot_id)
        elif kind == "merge":
            ids = [str(x) for x in (op.get("shot_ids") or []) if x]
            for sid in ids:
                invalidate_shot_tts(store, script_id, sid)
            shots = _apply_merge(store, shots, ids, op)
        elif kind == "add":
            shots = _apply_add(store, shots, op)
        elif kind == "delete" and shot_id:
            invalidate_shot_tts(store, script_id, shot_id)
            shots = _apply_delete(shots, shot_id)
        elif kind == "regen" and shot_id:
            idx = next((i for i, s in enumerate(shots) if s.id == shot_id), None)
            if idx is not None:
                shots[idx] = _apply_regen(shots[idx], op)
        elif kind == "reorder":
            id_order = [str(x) for x in (op.get("ordered_shot_ids") or []) if x]
            if id_order:
                shots = _apply_reorder(shots, id_order)

    from core.edit.sub_shot_produce import clamp_image_timings_to_sub

    repaired: list[Shot] = []
    for shot in shots:
        clamped_subs = [clamp_image_timings_to_sub(sub) for sub in shot.sub_shots]
        if any(a is not b for a, b in zip(clamped_subs, shot.sub_shots)):
            shot = shot.model_copy(update={"sub_shots": clamped_subs})
        issues = validate_shot_structure(shot)
        if issues:
            raise ValueError(f"镜头 {shot.id} 结构校验失败：" + "；".join(issues[:3]))
        repaired.append(shot)
    shots = repaired

    new_plan = plan.model_copy(
        update={
            "shots": normalize_shot_orders(shots),
            "detail_revision": plan.detail_revision + 1,
        }
    )
    store.set_video_plan(new_plan)
    return new_plan
