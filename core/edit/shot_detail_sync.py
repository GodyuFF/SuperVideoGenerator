"""分镜复核与 TTS 实测绑定（新模型：面向镜内多轨结构）。

职责（无历史兼容、无降级）：
- 把已生成的 TTS 配音 media 绑定进镜内 voice 音频 clip，并按实测时长对齐 clip 与镜时长。
- 从 TTS metadata 的句级 cue 回填镜内字幕（仅当该镜尚无字幕）。
- 复核 patch 落到 Shot 复核字段（review_note / need_regen / camera_motion）。
- 仅写分镜计划稿·镜头；剪辑时间轴由 editing_agent 专用 Tool 或用户 OpenCut PATCH 维护。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from core.edit.shot_flatten import effective_shot_duration_ms
from core.edit.timeline import (
    DURATION_DRIFT_REFRESH_MS,
    _shot_tts_duration_ms,
    build_tts_by_shot,
)
from core.models.entities import (
    Shot,
    ShotAudioClip,
    ShotAudioTrack,
    ShotSubShot,
    ShotSubtitle,
    TextAssetType,
    VideoPlan,
    new_id,
)
from core.models.image_text_asset import FrameContent, normalize_image_text_content
from core.store.memory import MemoryStore
from core.tts.subtitle import normalize_non_overlapping_cues


@dataclass
class DurationSyncDiff:
    """单镜规划时长与 TTS 实测时长偏差。"""

    shot_id: str
    order: int
    plan_duration_ms: int
    tts_duration_ms: int
    synced_duration_ms: int

    def to_dict(self) -> dict[str, Any]:
        """序列化为 JSON 友好字典。"""
        return {
            "shot_id": self.shot_id,
            "order": self.order,
            "plan_duration_ms": self.plan_duration_ms,
            "tts_duration_ms": self.tts_duration_ms,
            "synced_duration_ms": self.synced_duration_ms,
        }


def _utc_now_iso() -> str:
    """返回当前 UTC ISO 时间戳。"""
    return datetime.now(timezone.utc).isoformat()


def _first_voice_track(shot: Shot) -> ShotAudioTrack | None:
    """返回镜内首条 voice 音轨（无则 None）。"""
    for track in shot.audio_tracks:
        if track.kind == "voice":
            return track
    return None


def _media_subtitle_cues(store: MemoryStore, media_id: str) -> list[dict[str, Any]]:
    """从 TTS 媒体 metadata 读取句级 cue（[{text,start_ms,end_ms}]）。"""
    media = store.media_assets.get(media_id)
    if not media:
        return []
    cues = (media.metadata or {}).get("subtitle_cues") or []
    out: list[dict[str, Any]] = []
    if isinstance(cues, list):
        for cue in cues:
            if not isinstance(cue, dict):
                continue
            text = str(cue.get("text") or "").strip()
            if not text:
                continue
            out.append(
                {
                    "text": text,
                    "start_ms": int(cue.get("start_ms") or 0),
                    "end_ms": int(cue.get("end_ms") or 0),
                }
            )
    return out


def _normalize_cumulative_sub_shots(
    sub_shots: list[ShotSubShot], duration_ms: int
) -> list[ShotSubShot]:
    """将镜内子镜规范为累加分段：按 start_ms 排序，相邻首尾相接，末段止于镜有效时长。"""
    from core.edit.sub_shot_produce import clamp_image_timings_to_sub

    if not sub_shots:
        return sub_shots
    duration_ms = max(0, int(duration_ms))
    ordered = sorted(sub_shots, key=lambda v: int(v.start_ms or 0))
    if len(ordered) == 1:
        vis = ordered[0]
        start = max(0, min(int(vis.start_ms or 0), duration_ms))
        end = duration_ms if duration_ms > start else start + 1
        return [clamp_image_timings_to_sub(vis.model_copy(update={"start_ms": start, "end_ms": end}))]

    out: list[ShotSubShot] = []
    for idx, vis in enumerate(ordered):
        start = max(0, min(int(vis.start_ms or 0), duration_ms))
        if idx < len(ordered) - 1:
            next_start = max(
                start,
                min(int(ordered[idx + 1].start_ms or 0), duration_ms),
            )
            end = next_start if next_start > start else min(int(vis.end_ms or 0), duration_ms)
        else:
            end = duration_ms
        if end <= start:
            end = min(duration_ms, start + 1) if duration_ms > start else start + 1
        out.append(
            clamp_image_timings_to_sub(vis.model_copy(update={"start_ms": start, "end_ms": end}))
        )
    return out


def _sub_shots_need_cumulative_normalize(shot: Shot) -> bool:
    """检测镜内子镜是否未按 start_ms 累加分段（重叠或中段被拉满镜长）。"""
    if len(shot.sub_shots) < 2:
        return False
    duration_ms = max(0, int(shot.duration_ms or 0))
    ordered = sorted(shot.sub_shots, key=lambda v: int(v.start_ms or 0))
    for idx, vis in enumerate(ordered[:-1]):
        end = int(vis.end_ms or 0)
        next_start = int(ordered[idx + 1].start_ms or 0)
        if end > next_start:
            return True
        if duration_ms > 0 and end >= duration_ms and next_start < duration_ms:
            return True
    return False


def normalize_plan_sub_shot_ranges(store: MemoryStore, script_id: str) -> bool:
    """将计划稿中未累加分段的子镜规范为相邻首尾相接（仅写 VideoPlan）。"""
    plan = store.get_video_plan_for_script(script_id)
    if not plan or not plan.shots:
        return False
    updated_shots: list[Shot] = []
    changed = False
    for shot in plan.shots:
        if not _sub_shots_need_cumulative_normalize(shot):
            updated_shots.append(shot)
            continue
        duration_ms = max(
            int(shot.duration_ms or 0),
            effective_shot_duration_ms(shot),
        )
        normalized = _normalize_cumulative_sub_shots(shot.sub_shots, duration_ms)
        if normalized != shot.sub_shots:
            changed = True
            shot = shot.model_copy(update={"sub_shots": normalized})
        updated_shots.append(shot)
    if not changed:
        return False
    store.set_video_plan(
        plan.model_copy(
            update={
                "shots": updated_shots,
                "detail_revision": plan.detail_revision + 1,
            }
        )
    )
    return True


def _sync_shot_tracks_to_duration(shot: Shot, duration_ms: int) -> Shot:
    """将镜有效时长同步到镜内各轨道终点（可扩展或收缩，TTS 绑定时以实测为准）。"""
    sub_shots = _normalize_cumulative_sub_shots(shot.sub_shots, duration_ms)
    video_tracks = [
        t.model_copy(
            update={
                "clips": [
                    c.model_copy(update={"end_ms": duration_ms}) for c in t.clips
                ]
            }
        )
        for t in shot.video_tracks
    ]
    audio_tracks: list[ShotAudioTrack] = []
    for t in shot.audio_tracks:
        new_clips: list[ShotAudioClip] = []
        for idx, c in enumerate(t.clips):
            if t.kind == "voice" and idx == 0:
                # duration_ms 是镜时长；主 voice clip 从镜起点铺满（与视频轨语义一致）
                new_clips.append(
                    c.model_copy(update={"start_ms": 0, "end_ms": duration_ms})
                )
            else:
                new_clips.append(c.model_copy(update={"end_ms": duration_ms}))
        audio_tracks.append(t.model_copy(update={"clips": new_clips}))
    subtitles = [
        s.model_copy(
            update={
                "end_ms": min(int(s.end_ms or duration_ms), duration_ms)
                if int(s.end_ms or 0) > duration_ms
                else duration_ms
            }
        )
        for s in shot.subtitles
    ]
    return shot.model_copy(
        update={
            "sub_shots": sub_shots,
            "video_tracks": video_tracks,
            "audio_tracks": audio_tracks,
            "subtitles": subtitles,
            "duration_ms": duration_ms,
        }
    )


def _extend_shot_tracks_to_duration(shot: Shot, duration_ms: int) -> Shot:
    """把镜内画面/视频/音频/字幕片段终点扩展到镜有效时长。"""
    duration_ms = max(int(duration_ms), int(shot.duration_ms or 0))
    sub_shots = _normalize_cumulative_sub_shots(shot.sub_shots, duration_ms)
    video_tracks = [
        t.model_copy(
            update={
                "clips": [
                    c.model_copy(update={"end_ms": max(int(c.end_ms or 0), duration_ms)})
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
                        update={"end_ms": max(int(c.end_ms or 0), duration_ms)}
                    )
                    for c in t.clips
                ]
            }
        )
        for t in shot.audio_tracks
    ]
    subtitles = [
        s.model_copy(update={"end_ms": max(int(s.end_ms or 0), duration_ms)})
        for s in shot.subtitles
    ]
    return shot.model_copy(
        update={
            "sub_shots": sub_shots,
            "video_tracks": video_tracks,
            "audio_tracks": audio_tracks,
            "subtitles": subtitles,
            "duration_ms": duration_ms,
        }
    )


def _bind_shot_tts(
    store: MemoryStore, shot: Shot, media_id: str, tts_duration_ms: int
) -> Shot:
    """把 TTS media 绑定进镜内首条 voice clip 并对齐时长；必要时创建 voice 轨。"""
    duration = tts_duration_ms if tts_duration_ms > 0 else effective_shot_duration_ms(shot)
    track = _first_voice_track(shot)
    audio_tracks = list(shot.audio_tracks)
    if track is None:
        new_track = ShotAudioTrack(
            id=new_id("sat"),
            name="角色音",
            kind="voice",
            clips=[
                ShotAudioClip(
                    id=new_id("sac"),
                    start_ms=0,
                    end_ms=duration,
                    media_id=media_id,
                )
            ],
        )
        audio_tracks = audio_tracks + [new_track]
    else:
        new_clips: list[ShotAudioClip] = []
        if track.clips:
            first = track.clips[0]
            # TTS 为镜时长权威源：主配音 clip 相对镜起点从 0 铺开，避免非零 start 叠算
            new_clips.append(
                first.model_copy(
                    update={"media_id": media_id, "start_ms": 0, "end_ms": duration}
                )
            )
            new_clips.extend(track.clips[1:])
        else:
            new_clips.append(
                ShotAudioClip(id=new_id("sac"), start_ms=0, end_ms=duration, media_id=media_id)
            )
        rebound = track.model_copy(update={"clips": new_clips})
        audio_tracks = [rebound if t.id == track.id else t for t in audio_tracks]

    updated = shot.model_copy(update={"audio_tracks": audio_tracks})

    # 字幕：该镜无字幕时用配音 media cue 回填（不用幕文案）
    if not updated.subtitles:
        voice_track = _first_voice_track(updated)
        char_ref = ""
        if voice_track and voice_track.clips:
            char_ref = str(voice_track.clips[0].character_ref or "").strip()
        media_obj = store.media_assets.get(media_id)
        media_narration = (
            str((media_obj.metadata or {}).get("narration_text") or "").strip()
            if media_obj
            else ""
        )
        cues = _ensure_media_subtitle_cues(
            store, media_id, media_narration, prefer_audio=True
        )
        if cues:
            updated = updated.model_copy(
                update={
                    "subtitles": [
                        ShotSubtitle(
                            id=new_id("ssub"),
                            text=c["text"],
                            start_ms=c["start_ms"],
                            end_ms=c["end_ms"] or (c["start_ms"] + 500),
                            character=str(c.get("character") or char_ref).strip(),
                            color=str(c.get("color") or "").strip(),
                        )
                        for c in cues
                    ]
                }
            )

    # TTS 实测为镜时长权威源，同步收缩或扩展镜内各轨
    return _sync_shot_tracks_to_duration(updated, duration)


def _bind_tts_to_plan(
    store: MemoryStore, script_id: str, *, plan: VideoPlan | None = None
) -> tuple[VideoPlan, list[DurationSyncDiff], list[dict[str, Any]]]:
    """把 TTS 实测绑定进各镜 voice clip，返回 (新计划, 偏差, 探测失败)。"""
    if plan is None:
        plan = store.get_video_plan_for_script(script_id)
    if not plan or not plan.shots:
        raise ValueError("未找到视频计划稿")

    tts_by_shot = build_tts_by_shot(store, script_id)
    diffs: list[DurationSyncDiff] = []
    probe_failures: list[dict[str, Any]] = []
    updated_shots: list[Shot] = []

    for shot in sorted(plan.shots, key=lambda s: s.order):
        media_id = tts_by_shot.get(shot.id)
        if not media_id:
            updated_shots.append(shot)
            continue
        tts_duration = _shot_tts_duration_ms(store, media_id)
        if tts_duration <= 0:
            probe_failures.append(
                {
                    "shot_id": shot.id,
                    "order": shot.order,
                    "tts_asset_id": media_id,
                    "reason": "TTS 时长探测失败（检查 FFmpeg 是否可用、音频文件是否可读）",
                }
            )
            updated_shots.append(shot)
            continue
        plan_duration = int(shot.duration_ms or 0)
        bound = _bind_shot_tts(store, shot, media_id, tts_duration)
        updated_shots.append(bound)
        if abs(tts_duration - plan_duration) > 150:
            diffs.append(
                DurationSyncDiff(
                    shot_id=shot.id,
                    order=shot.order,
                    plan_duration_ms=plan_duration,
                    tts_duration_ms=tts_duration,
                    synced_duration_ms=int(bound.duration_ms or 0),
                )
            )

    new_plan = plan.model_copy(update={"shots": updated_shots})
    final_shots: list[Shot] = []
    for shot in new_plan.shots:
        synced, _ = _sync_shot_bound_voice_clips(store, shot)
        final_shots.append(synced)
    new_plan = new_plan.model_copy(update={"shots": final_shots})
    store.set_video_plan(new_plan)
    return new_plan, diffs, probe_failures


def sync_plan_from_tts(store: MemoryStore, script_id: str) -> dict[str, Any]:
    """TTS 后一次性同步：绑定配音 media、对齐镜时长、回填字幕（不写剪辑时间轴）。"""
    plan, diffs, probe_failures = _bind_tts_to_plan(store, script_id)
    return {
        "plan_id": plan.id,
        "shot_count": len(plan.shots),
        "duration_diffs": [d.to_dict() for d in diffs],
        "synced_shot_count": len(diffs),
        "detail_revision": plan.detail_revision,
        "probe_failures": probe_failures,
    }


def sync_actual_assets(store: MemoryStore, script_id: str) -> dict[str, Any]:
    """复核 Agent：刷新实测资产时长与偏差（仅写分镜计划稿·镜头，不写剪辑时间轴）。"""
    plan, diffs, probe_failures = _bind_tts_to_plan(store, script_id)
    return {
        "plan_id": plan.id,
        "shot_count": len(plan.shots),
        "synced_shot_count": len(diffs),
        "duration_diffs": [d.to_dict() for d in diffs],
        "detail_revision": plan.detail_revision,
        "probe_failures": probe_failures,
    }


def apply_shot_detail_patches(
    store: MemoryStore,
    script_id: str,
    patches: list[dict[str, Any]],
) -> VideoPlan:
    """将复核 patch 落到 Shot 复核字段并递增 detail_revision。"""
    plan = store.get_video_plan_for_script(script_id)
    if not plan or not plan.shots:
        raise ValueError("未找到视频计划稿")

    patch_by_id = {
        str(p.get("shot_id") or p.get("id") or ""): p
        for p in patches
        if isinstance(p, dict)
    }
    updated: list[Shot] = []
    for shot in sorted(plan.shots, key=lambda s: s.order):
        raw = patch_by_id.get(shot.id)
        if not raw:
            updated.append(shot)
            continue
        shot_updates: dict[str, Any] = {"review_revision": shot.review_revision + 1}
        note = str(raw.get("display_instructions") or raw.get("review_note") or "").strip()
        if note:
            shot_updates["review_note"] = note
        if "need_regen" in raw:
            shot_updates["need_regen"] = bool(raw["need_regen"])
        if raw.get("regen_reason"):
            shot_updates["regen_reason"] = str(raw["regen_reason"])
        if raw.get("sync_policy") in ("narration_master", "visual_master", "balanced"):
            shot_updates["sync_policy"] = str(raw["sync_policy"])
        if "lip_sync_required" in raw:
            shot_updates["lip_sync_required"] = bool(raw["lip_sync_required"])
        if raw.get("sync_notes") is not None:
            shot_updates["sync_notes"] = str(raw.get("sync_notes") or "")
        if isinstance(raw.get("proposed_sync_actions"), list):
            shot_updates["proposed_sync_actions"] = list(raw["proposed_sync_actions"])
        refined_motion = str(raw.get("camera_motion_refined") or "").strip()
        new_shot = shot.model_copy(update=shot_updates)
        if refined_motion and new_shot.sub_shots:
            sub_shots = list(new_shot.sub_shots)
            sub_shots[0] = sub_shots[0].model_copy(update={"camera_motion": refined_motion})
            new_shot = new_shot.model_copy(update={"sub_shots": sub_shots})
        updated.append(new_shot)

    new_plan = plan.model_copy(
        update={"shots": updated, "detail_revision": plan.detail_revision + 1}
    )
    store.set_video_plan(new_plan)
    return new_plan


def update_frames_from_shot_detail(store: MemoryStore, script_id: str) -> int:
    """把 Shot.review_note 合并进画面 frame 文字资产 notes。"""
    plan = store.get_video_plan_for_script(script_id)
    if not plan:
        return 0
    updated_count = 0
    for shot in plan.shots:
        note = (shot.review_note or "").strip()
        if not note:
            continue
        frame_ids = [
            img.frame_asset_id
            for v in shot.sub_shots
            for img in v.images
            if img.frame_asset_id
        ]
        if not frame_ids:
            continue
        frame_id = frame_ids[0]
        asset = store.text_assets.get(frame_id)
        if not asset or asset.type != TextAssetType.FRAME:
            continue
        content_raw = normalize_image_text_content(asset.type, asset.content)
        try:
            content = FrameContent.model_validate(content_raw)
        except Exception:
            continue
        note_line = f"[复核] {note}"
        existing_notes = (content.notes or "").strip()
        if note_line in existing_notes:
            continue
        merged_notes = f"{existing_notes}\n{note_line}".strip() if existing_notes else note_line
        new_content = content.model_copy(update={"notes": merged_notes})
        asset.content = new_content.model_dump()
        store.text_assets[frame_id] = asset
        updated_count += 1
    return updated_count


def _shot_voice_missing_media(shot: Shot, tts_by_shot: dict[str, str]) -> bool:
    """判断该镜有 TTS 资产但镜内 voice clip 尚未绑定该 media。"""
    if shot.id not in tts_by_shot:
        return False
    media_id = tts_by_shot[shot.id]
    track = _first_voice_track(shot)
    if track is None or not track.clips:
        return True
    return track.clips[0].media_id != media_id


def ensure_storyboard_tts_sync(store: MemoryStore, script_id: str) -> tuple[bool, dict[str, Any]]:
    """有 TTS 但镜内 voice clip 未绑定 media 时幂等执行 sync_plan_from_tts。"""
    plan = store.get_video_plan_for_script(script_id)
    if not plan or not plan.shots:
        return False, {}
    tts_by_shot = build_tts_by_shot(store, script_id)
    if not tts_by_shot:
        return False, {}
    needs = any(_shot_voice_missing_media(shot, tts_by_shot) for shot in plan.shots)
    if not needs:
        return False, {}
    return True, sync_plan_from_tts(store, script_id)


def lazy_sync_storyboard_if_needed(store: MemoryStore, script_id: str) -> bool:
    """看板/接口懒同步入口：绑定 TTS 与缺字幕回填（不写剪辑时间轴）。"""
    synced, _ = ensure_storyboard_tts_sync(store, script_id)
    backfilled, _ = backfill_plan_subtitles_from_voice(store, script_id)
    normalized = normalize_plan_sub_shot_ranges(store, script_id)
    return synced or backfilled or normalized


def _voice_clip_cached_duration_ms(shot: Shot) -> int:
    """读取镜内主 voice clip 缓存时长；非零起点返回 -1 表示需重绑归零。"""
    track = _first_voice_track(shot)
    if track is None or not track.clips:
        return 0
    clip = track.clips[0]
    start = int(clip.start_ms or 0)
    end = int(clip.end_ms or 0)
    if start > 0:
        return -1
    return max(0, end - start)


def _shot_tts_duration_drifted(
    shot: Shot, tts_by_shot: dict[str, str], store: MemoryStore
) -> bool:
    """判断镜内 voice clip 时长与 TTS 实测偏差是否过大。"""
    media_id = tts_by_shot.get(shot.id)
    if not media_id:
        return False
    cached = _voice_clip_cached_duration_ms(shot)
    if cached < 0:
        return True
    if cached <= 0:
        return True
    probed = _shot_tts_duration_ms(store, media_id)
    if probed <= 0:
        return False
    return abs(probed - cached) > DURATION_DRIFT_REFRESH_MS


def refresh_shot_tts_durations_if_drifted(
    store: MemoryStore, script_id: str
) -> tuple[bool, list[DurationSyncDiff]]:
    """TTS 实测与镜内 voice clip 缓存偏差过大时重绑定分镜计划稿（不写剪辑时间轴）。"""
    plan = store.get_video_plan_for_script(script_id)
    if not plan or not plan.shots:
        return False, []
    tts_by_shot = build_tts_by_shot(store, script_id)
    if not tts_by_shot:
        return False, []
    needs = any(_shot_tts_duration_drifted(shot, tts_by_shot, store) for shot in plan.shots)
    if not needs:
        return False, []
    _, diffs, _ = _bind_tts_to_plan(store, script_id)
    return True, diffs


def is_shot_detail_complete(store: MemoryStore, script_id: str) -> bool:
    """判断分镜复核是否完成：detail_revision>0 且每镜视频/音频 clip 均已绑 media。"""
    from core.edit.shot_validate import validate_shots_render_ready

    plan = store.get_video_plan_for_script(script_id)
    if not plan or not plan.shots or plan.detail_revision <= 0:
        return False
    return not validate_shots_render_ready(plan.shots)


def resolve_effective_camera_motion(shot: Shot) -> str:
    """返回该镜主画面运镜（首个画面/首个视频 clip 的运镜）。"""
    for visual in shot.sub_shots:
        if visual.camera_motion:
            return visual.camera_motion
    for track in sorted(shot.video_tracks, key=lambda t: t.z_index):
        for clip in track.clips:
            if clip.camera_motion:
                return clip.camera_motion
    return "static"


def normalize_plan_camera_motions(
    store: MemoryStore, script_id: str
) -> tuple[VideoPlan | None, bool]:
    """规范镜内画面与视频 clip 的运镜别名为 canonical 值。"""
    from core.edit.edit_capabilities import resolve_motion

    plan = store.get_video_plan_for_script(script_id)
    if not plan or not plan.shots:
        return plan, False
    changed = False
    updated: list[Shot] = []
    for shot in plan.shots:
        new_shot = shot
        new_sub_shots: list = []
        for v in shot.sub_shots:
            canonical = resolve_motion(v.camera_motion)
            if canonical != v.camera_motion:
                changed = True
                new_sub_shots.append(v.model_copy(update={"camera_motion": canonical}))
            else:
                new_sub_shots.append(v)
        if new_sub_shots != shot.sub_shots:
            new_shot = new_shot.model_copy(update={"sub_shots": new_sub_shots})
        new_vtracks = []
        for track in new_shot.video_tracks:
            new_clips = []
            for clip in track.clips:
                canonical = resolve_motion(clip.camera_motion)
                if canonical != clip.camera_motion:
                    changed = True
                    new_clips.append(clip.model_copy(update={"camera_motion": canonical}))
                else:
                    new_clips.append(clip)
            if new_clips != track.clips:
                new_vtracks.append(track.model_copy(update={"clips": new_clips}))
            else:
                new_vtracks.append(track)
        if new_vtracks != new_shot.video_tracks:
            new_shot = new_shot.model_copy(update={"video_tracks": new_vtracks})
        updated.append(new_shot)
    if changed:
        plan = plan.model_copy(update={"shots": updated})
        store.set_video_plan(plan)
    return plan, changed


def _find_voice_clip(shot: Shot, clip_id: str | None) -> tuple[ShotAudioTrack, ShotAudioClip, int] | None:
    """在镜内 voice 轨中定位 clip；clip_id 为空时取首条。"""
    for track in shot.audio_tracks:
        if track.kind != "voice":
            continue
        if clip_id:
            for idx, clip in enumerate(track.clips):
                if clip.id == clip_id:
                    return track, clip, idx
            return None
        if track.clips:
            return track, track.clips[0], 0
    return None


def _ensure_media_subtitle_cues(
    store: MemoryStore,
    media_id: str,
    narration_text: str,
    *,
    prefer_audio: bool = False,
) -> list[dict[str, Any]]:
    """读取或生成 media 句级 cue；prefer_audio 时优先音频接地而非字数比例。"""
    cues = _media_subtitle_cues(store, media_id)
    from core.edit.subtitle_align import build_cues_for_audio_media, cues_are_proportional_only

    if cues and not (prefer_audio and cues_are_proportional_only(cues)):
        return cues
    media = store.media_assets.get(media_id)
    if not media:
        return []

    cues = build_cues_for_audio_media(
        store,
        media,
        narration_text=narration_text,
        prefer_audio=prefer_audio,
    )
    if cues:
        meta = dict(media.metadata or {})
        meta["subtitle_cues"] = cues
        store.media_assets[media_id] = media.model_copy(update={"metadata": meta})
    return cues


def _append_subtitles_from_cues(
    subtitle_rows: list[ShotSubtitle],
    *,
    cues: list[dict[str, Any]],
    clip_start_ms: int,
    character: str = "",
) -> None:
    """把 media 句级 cue 追加到镜内字幕列表（相对镜起点）。"""
    char = (character or "").strip()
    for cue in cues:
        subtitle_rows.append(
            ShotSubtitle(
                id=new_id("ssub"),
                text=cue["text"],
                start_ms=clip_start_ms + int(cue.get("start_ms") or 0),
                end_ms=clip_start_ms
                + int(cue.get("end_ms") or (int(cue.get("start_ms") or 0) + 500)),
                character=str(cue.get("character") or char).strip(),
                color=str(cue.get("color") or "").strip(),
            )
        )


def build_shot_subtitles_from_voice_audio(
    store: MemoryStore,
    script_id: str,
    shot_id: str,
) -> list[dict[str, Any]]:
    """从镜内已绑定配音音频的 subtitle_cues（或 ASR）构建字幕预览，不用配音幕文案拆句。"""
    plan = store.get_video_plan_for_script(script_id)
    if not plan:
        raise ValueError("未找到视频计划稿")
    shot = next((s for s in plan.shots if s.id == shot_id), None)
    if shot is None:
        raise ValueError("镜头不存在")
    voice_track = _first_voice_track(shot)
    if voice_track is None or not voice_track.clips:
        return []

    rows: list[ShotSubtitle] = []
    for clip in sorted(voice_track.clips, key=lambda c: int(c.start_ms or 0)):
        media_id = str(clip.media_id or "").strip()
        if not media_id:
            continue
        # 不用 clip.text：幕文案可能已改，与实际配音不一致
        media = store.media_assets.get(media_id)
        media_narration = ""
        if media:
            media_narration = str((media.metadata or {}).get("narration_text") or "").strip()
        cues = _ensure_media_subtitle_cues(
            store,
            media_id,
            media_narration,
            prefer_audio=True,
        )
        if not cues:
            continue
        _append_subtitles_from_cues(
            rows,
            cues=cues,
            clip_start_ms=int(clip.start_ms or 0),
            character=str(clip.character_ref or "").strip(),
        )
    normalized = normalize_non_overlapping_cues(
        [
            {
                "id": s.id,
                "text": s.text,
                "start_ms": s.start_ms,
                "end_ms": s.end_ms,
                "character": s.character,
                "color": s.color,
            }
            for s in rows
        ]
    )
    return [
        {
            "id": str(c.get("id") or new_id("ssub")),
            "text": str(c["text"]),
            "start_ms": int(c["start_ms"]),
            "end_ms": int(c["end_ms"]),
            "character": str(c.get("character") or ""),
            "color": str(c.get("color") or ""),
        }
        for c in normalized
    ]


def _shot_needs_subtitle_backfill(shot: Shot) -> bool:
    """有已绑定配音 media 但镜内 subtitles 为空时需回填。"""
    if shot.subtitles:
        return False
    voice_track = _first_voice_track(shot)
    if voice_track is None or not voice_track.clips:
        return False
    return any(str(c.media_id or "").strip() for c in voice_track.clips)


def backfill_plan_subtitles_from_voice(
    store: MemoryStore,
    script_id: str,
) -> tuple[bool, int]:
    """为已绑定配音但缺镜内 subtitles 的镜头回填句级字幕。"""
    plan = store.get_video_plan_for_script(script_id)
    if not plan or not plan.shots:
        return False, 0
    updated_shots: list[Shot] = []
    filled = 0
    changed_any = False
    for shot in plan.shots:
        if not _shot_needs_subtitle_backfill(shot):
            updated_shots.append(shot)
            continue
        synced, changed = _sync_shot_bound_voice_clips(store, shot)
        if synced.subtitles:
            filled += 1
        if changed:
            changed_any = True
        updated_shots.append(synced)
    if not changed_any:
        return False, filled
    store.set_video_plan(
        plan.model_copy(
            update={
                "shots": updated_shots,
                "detail_revision": plan.detail_revision + 1,
            }
        )
    )
    return True, filled


def _sync_shot_bound_voice_clips(store: MemoryStore, shot: Shot) -> tuple[Shot, bool]:
    """按镜内已绑定 media 的 voice clip 对齐时长；镜无字幕时回填句级字幕。"""
    voice_track = _first_voice_track(shot)
    if not voice_track or not voice_track.clips:
        return shot, False

    changed = False
    new_clips: list[ShotAudioClip] = []
    subtitle_rows: list[ShotSubtitle] = list(shot.subtitles) if shot.subtitles else []
    fill_subtitles = not subtitle_rows
    max_end = 0
    primary_media_duration = 0

    for idx, clip in enumerate(voice_track.clips):
        media_id = str(clip.media_id or "").strip()
        if not media_id:
            new_clips.append(clip)
            max_end = max(max_end, int(clip.end_ms or 0))
            continue
        media = store.media_assets.get(media_id)
        media_narration = (
            str((media.metadata or {}).get("narration_text") or "").strip() if media else ""
        )
        duration = _shot_tts_duration_ms(store, media_id)
        if duration <= 0:
            if fill_subtitles:
                cues = _ensure_media_subtitle_cues(
                    store, media_id, media_narration, prefer_audio=True
                )
                if cues:
                    _append_subtitles_from_cues(
                        subtitle_rows,
                        cues=cues,
                        clip_start_ms=int(clip.start_ms or 0),
                        character=str(clip.character_ref or "").strip(),
                    )
                    changed = True
            new_clips.append(clip)
            max_end = max(max_end, int(clip.end_ms or 0))
            continue
        # 主配音 clip：从镜起点铺满实测时长，避免非零 start 与镜时长叠算
        if idx == 0:
            clip_start = 0
            primary_media_duration = duration
        else:
            clip_start = int(clip.start_ms or 0)
        new_end = clip_start + duration
        if (
            clip_start != int(clip.start_ms or 0)
            or new_end != int(clip.end_ms or 0)
            or clip.media_id != media_id
        ):
            changed = True
        new_clips.append(
            clip.model_copy(
                update={"media_id": media_id, "start_ms": clip_start, "end_ms": new_end}
            )
        )
        max_end = max(max_end, new_end)
        if fill_subtitles:
            cues = _ensure_media_subtitle_cues(
                store, media_id, media_narration, prefer_audio=True
            )
            if cues:
                _append_subtitles_from_cues(
                    subtitle_rows,
                    cues=cues,
                    clip_start_ms=clip_start,
                    character=str(clip.character_ref or "").strip(),
                )
                changed = True

    if not changed and not (fill_subtitles and subtitle_rows):
        if max_end <= int(shot.duration_ms or 0):
            return shot, False

    audio_tracks: list[ShotAudioTrack] = []
    voice_replaced = False
    for t in shot.audio_tracks:
        if t.kind == "voice" and not voice_replaced:
            audio_tracks.append(t.model_copy(update={"clips": new_clips}))
            voice_replaced = True
        else:
            audio_tracks.append(t)
    final_subs = shot.subtitles
    if fill_subtitles and subtitle_rows:
        final_subs = [
            ShotSubtitle(
                id=str(c.get("id") or new_id("ssub")),
                text=str(c["text"]),
                start_ms=int(c["start_ms"]),
                end_ms=int(c["end_ms"]),
                character=str(c.get("character") or ""),
                color=str(c.get("color") or ""),
            )
            for c in normalize_non_overlapping_cues(
                [
                    {
                        "id": s.id,
                        "text": s.text,
                        "start_ms": s.start_ms,
                        "end_ms": s.end_ms,
                        "character": s.character,
                        "color": s.color,
                    }
                    for s in subtitle_rows
                ]
            )
        ]
    # 镜时长取主配音实测（若有），否则取轨终点；勿把「start+时长」绝对值再送进叠算路径
    target_duration = primary_media_duration or max(max_end, int(shot.duration_ms or 0))
    updated = shot.model_copy(
        update={
            "audio_tracks": audio_tracks,
            "subtitles": final_subs,
            "duration_ms": target_duration,
        }
    )
    updated = _sync_shot_tracks_to_duration(updated, target_duration)
    return updated, True


def bind_voice_clip_media(
    store: MemoryStore,
    script_id: str,
    shot_id: str,
    media_id: str,
    *,
    clip_id: str | None = None,
) -> dict[str, Any]:
    """将配音 media 绑定到镜内 voice clip 并同步时长与句级字幕。"""
    plan = store.get_video_plan_for_script(script_id)
    if not plan:
        raise ValueError("未找到视频计划稿")
    shot = next((s for s in plan.shots if s.id == shot_id), None)
    if not shot:
        raise ValueError("镜头不存在")

    located = _find_voice_clip(shot, clip_id)
    audio_tracks = list(shot.audio_tracks)
    if located is None:
        duration = _shot_tts_duration_ms(store, media_id)
        new_track = ShotAudioTrack(
            id=new_id("sat"),
            name="角色音",
            kind="voice",
            clips=[
                ShotAudioClip(
                    id=new_id("sac"),
                    start_ms=0,
                    end_ms=max(duration, 500),
                    media_id=media_id,
                )
            ],
        )
        audio_tracks.append(new_track)
        shot = shot.model_copy(update={"audio_tracks": audio_tracks})
    else:
        track, clip, idx = located
        duration = _shot_tts_duration_ms(store, media_id)
        clip_start = int(clip.start_ms or 0)
        new_clip = clip.model_copy(
            update={
                "media_id": media_id,
                "end_ms": clip_start + max(duration, 500),
            }
        )
        new_clips = list(track.clips)
        new_clips[idx] = new_clip
        rebound = track.model_copy(update={"clips": new_clips})
        audio_tracks = [rebound if t.id == track.id else t for t in audio_tracks]
        shot = shot.model_copy(update={"audio_tracks": audio_tracks})

    synced_shot, _ = _sync_shot_bound_voice_clips(store, shot)
    new_shots = [synced_shot if s.id == shot_id else s for s in plan.shots]
    new_plan = plan.model_copy(update={"shots": new_shots})
    store.set_video_plan(new_plan)
    return {
        "shot_id": shot_id,
        "media_id": media_id,
        "duration_ms": int(synced_shot.duration_ms or 0),
        "subtitle_count": len(synced_shot.subtitles),
        "detail_revision": new_plan.detail_revision,
    }
