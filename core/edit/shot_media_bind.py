"""镜内多轨 media_id 回填：生图/生视频后写入 sub_shots 与 video_tracks。"""

from __future__ import annotations

from typing import Any

from core.edit.shot_flatten import effective_shot_duration_ms
from core.edit.sub_shot_helpers import (
    find_sub_shot_index_by_frame,
    upsert_sub_shot_image,
)
from core.models.entities import (
    Shot,
    ShotSubShotImage,
    ShotVideoClip,
    ShotVideoTrack,
    TextAssetType,
    new_id,
)
from core.models.image_text_asset import get_base_variant, normalize_image_text_content
from core.store.memory import MemoryStore


def _resolve_frame_media_id(store: MemoryStore, frame_asset_id: str) -> str:
    """从 frame 文字资产解析已落盘的图片 media_id。"""
    asset = store.get_text_asset(frame_asset_id)
    if not asset or asset.type != TextAssetType.FRAME:
        return ""
    if asset.primary_media_id:
        return asset.primary_media_id
    content = normalize_image_text_content(asset.type, asset.content)
    base = get_base_variant(content)
    return str(base.media_id or "").strip() if base else ""


def _ensure_z0_video_tracks(
    shot: Shot,
    *,
    sub_shot_id: str,
    media_id: str,
    source_kind: str,
    camera_motion: str,
) -> list[ShotVideoTrack]:
    """确保 z0 视频轨存在并绑定 media_id。"""
    duration = effective_shot_duration_ms(shot)
    tracks = list(shot.video_tracks)
    z0_idx = next((i for i, t in enumerate(tracks) if int(t.z_index or 0) == 0), None)
    if z0_idx is None:
        clip = ShotVideoClip(
            id=new_id("svc"),
            start_ms=0,
            end_ms=duration,
            source_sub_shot_id=sub_shot_id,
            media_id=media_id,
            source_kind=source_kind,  # type: ignore[arg-type]
            camera_motion=camera_motion,
        )
        tracks.append(
            ShotVideoTrack(
                id=new_id("svt"),
                name="主画面",
                z_index=0,
                clips=[clip],
            )
        )
        return tracks

    track = tracks[z0_idx]
    new_clips: list[ShotVideoClip] = []
    matched = False
    for clip in track.clips:
        if clip.source_sub_shot_id == sub_shot_id or not matched:
            new_clips.append(
                clip.model_copy(
                    update={
                        "media_id": media_id,
                        "source_kind": source_kind,  # type: ignore[arg-type]
                        "end_ms": max(int(clip.end_ms or 0), duration),
                    }
                )
            )
            matched = True
        else:
            new_clips.append(clip)
    if not matched:
        new_clips.insert(
            0,
            ShotVideoClip(
                id=new_id("svc"),
                start_ms=0,
                end_ms=duration,
                source_sub_shot_id=sub_shot_id,
                media_id=media_id,
                source_kind=source_kind,  # type: ignore[arg-type]
                camera_motion=camera_motion,
            ),
        )
    tracks[z0_idx] = track.model_copy(update={"clips": new_clips})
    return tracks


def bind_shot_still_media(
    shot: Shot,
    sub_shot_idx: int,
    media_id: str,
    *,
    image_idx: int = 0,
) -> Shot:
    """把静态图 media 绑定到指定子镜图片与 z0 视频 clip。"""
    if not media_id or sub_shot_idx < 0 or sub_shot_idx >= len(shot.sub_shots):
        return shot
    sub = shot.sub_shots[sub_shot_idx]
    # 必须以目标 image_idx 为底稿；勿复制首图，否则多图会共用同一 ssi id
    if 0 <= image_idx < len(sub.images):
        base = sub.images[image_idx]
    else:
        base = ShotSubShotImage()
    new_image = base.model_copy(update={"media_id": media_id, "kind": "static"})
    new_sub_shots = list(shot.sub_shots)
    new_sub_shots[sub_shot_idx] = upsert_sub_shot_image(sub, new_image, image_idx=image_idx)
    updated = shot.model_copy(update={"sub_shots": new_sub_shots})
    video_tracks = _ensure_z0_video_tracks(
        updated,
        sub_shot_id=sub.id,
        media_id=media_id,
        source_kind="still",
        camera_motion=sub.camera_motion or "static",
    )
    return updated.model_copy(update={"video_tracks": video_tracks})


def bind_shot_video_media(shot: Shot, media_id: str, sub_shot_idx: int = 0) -> Shot:
    """把 AI 视频 media 绑定到子镜 videos[] 与 z0 视频轨（不写入画面 images[]）。"""
    from core.edit.sub_shot_helpers import upsert_sub_shot_video
    from core.models.entities import ShotSubShotVideo

    if not media_id or not shot.sub_shots:
        return shot
    idx = min(max(sub_shot_idx, 0), len(shot.sub_shots) - 1)
    sub = shot.sub_shots[idx]
    if sub.videos:
        new_vid = sub.videos[0].model_copy(update={"media_id": media_id, "source_kind": "video"})
        new_sub = upsert_sub_shot_video(sub, new_vid, video_idx=0)
    else:
        new_vid = ShotSubShotVideo(
            media_id=media_id,
            start_ms=0,
            end_ms=max(0, int(sub.end_ms or 0) - int(sub.start_ms or 0)),
            source_kind="video",
            camera_motion=sub.camera_motion or "static",
        )
        new_sub = upsert_sub_shot_video(sub, new_vid, video_idx=0)
    new_sub_shots = list(shot.sub_shots)
    new_sub_shots[idx] = new_sub
    updated = shot.model_copy(update={"sub_shots": new_sub_shots})
    video_tracks = _ensure_z0_video_tracks(
        updated,
        sub_shot_id=sub.id,
        media_id=media_id,
        source_kind="video",
        camera_motion=sub.camera_motion or "static",
    )
    return updated.model_copy(update={"video_tracks": video_tracks})


def _apply_shot_update(
    store: MemoryStore, script_id: str, shot_id: str, updated: Shot
) -> bool:
    """写回单镜并可选重投影时间轴。"""
    plan = store.get_video_plan_for_script(script_id)
    if not plan or not plan.shots:
        return False
    shots = [
        updated if s.id == shot_id else s for s in plan.shots
    ]
    store.set_video_plan(plan.model_copy(update={"shots": shots}))
    return True


def bind_frame_media_to_plan(
    store: MemoryStore, script_id: str, frame_asset_id: str, media_id: str
) -> bool:
    """生图落盘后，把 media 绑定到对应镜的子镜与 video_tracks。"""
    frame_asset_id = frame_asset_id.strip()
    media_id = media_id.strip()
    if not frame_asset_id or not media_id:
        return False
    plan = store.get_video_plan_for_script(script_id)
    if not plan or not plan.shots:
        return False
    for shot in plan.shots:
        idx = find_sub_shot_index_by_frame(shot, frame_asset_id)
        if idx is None:
            continue
        bound = bind_shot_still_media(shot, idx, media_id)
        return _apply_shot_update(store, script_id, shot.id, bound)
    return False


def bind_shot_video_media_to_plan(
    store: MemoryStore, script_id: str, shot_id: str, media_id: str
) -> bool:
    """生视频落盘后，把 media 绑定到指定镜的 video_tracks。"""
    shot_id = shot_id.strip()
    media_id = media_id.strip()
    if not shot_id or not media_id:
        return False
    plan = store.get_video_plan_for_script(script_id)
    if not plan or not plan.shots:
        return False
    for shot in plan.shots:
        if shot.id != shot_id:
            continue
        bound = bind_shot_video_media(shot, media_id)
        return _apply_shot_update(store, script_id, shot.id, bound)
    return False


def sync_plan_image_media_from_frames(
    store: MemoryStore, script_id: str
) -> dict[str, Any]:
    """扫描全部 frame 的 primary_media，回填镜内 sub_shots/video_tracks。"""
    plan = store.get_video_plan_for_script(script_id)
    if not plan or not plan.shots:
        return {"bound_count": 0, "plan_id": plan.id if plan else ""}

    bound_count = 0
    updated_shots: list[Shot] = []
    for shot in plan.shots:
        new_shot = shot
        for idx, sub in enumerate(shot.sub_shots):
            for img_idx, img in enumerate(sub.images):
                frame_id = img.frame_asset_id.strip()
                if not frame_id:
                    continue
                media_id = _resolve_frame_media_id(store, frame_id)
                if not media_id:
                    continue
                current = img.media_id or ""
                z0_media = ""
                for track in new_shot.video_tracks:
                    if int(track.z_index or 0) == 0 and track.clips:
                        z0_media = track.clips[0].media_id or ""
                        break
                if current == media_id and z0_media == media_id:
                    continue
                new_shot = bind_shot_still_media(
                    new_shot, idx, media_id, image_idx=img_idx
                )
                bound_count += 1
        updated_shots.append(new_shot)

    if bound_count:
        plan = plan.model_copy(update={"shots": updated_shots})
        store.set_video_plan(plan)

    return {
        "bound_count": bound_count,
        "plan_id": plan.id,
        "shot_count": len(plan.shots),
    }


def bind_video_clip_media(
    shot: Shot,
    video_clip_asset_id: str,
    media_id: str,
    *,
    sub_shot_idx: int = 0,
) -> Shot:
    """将 media 绑定到镜内子镜 videos[] 与 video_tracks。"""
    from core.edit.sub_shot_helpers import find_sub_shot_index_by_video_clip, upsert_sub_shot_video

    cid = video_clip_asset_id.strip()
    mid = media_id.strip()
    if not cid or not mid:
        return shot
    idx = find_sub_shot_index_by_video_clip(shot, cid)
    if idx is None:
        idx = min(max(sub_shot_idx, 0), max(len(shot.sub_shots) - 1, 0))
    if not shot.sub_shots:
        return shot
    sub = shot.sub_shots[idx]
    vid_idx = next(
        (i for i, v in enumerate(sub.videos) if v.video_clip_asset_id.strip() == cid),
        len(sub.videos),
    )
    if vid_idx >= len(sub.videos):
        from core.models.entities import ShotSubShotVideo

        new_vid = ShotSubShotVideo(video_clip_asset_id=cid, media_id=mid)
        sub = upsert_sub_shot_video(sub, new_vid, video_idx=vid_idx)
    else:
        sub = upsert_sub_shot_video(
            sub,
            sub.videos[vid_idx].model_copy(update={"media_id": mid, "video_clip_asset_id": cid}),
            video_idx=vid_idx,
        )
    sub_shots = list(shot.sub_shots)
    sub_shots[idx] = sub
    updated = shot.model_copy(update={"sub_shots": sub_shots})
    return bind_shot_video_media(updated, mid)


def bind_video_clip_media_to_plan(
    store: MemoryStore,
    script_id: str,
    video_clip_asset_id: str,
    media_id: str,
    *,
    sub_shot_idx: int = 0,
) -> bool:
    """生视频落盘后，把 media 绑定到 video_clip 关联的子镜与 video_tracks。"""
    cid = video_clip_asset_id.strip()
    mid = media_id.strip()
    if not cid or not mid:
        return False
    plan = store.get_video_plan_for_script(script_id)
    if not plan or not plan.shots:
        return False
    content_asset = store.get_text_asset(cid)
    shot_id_hint = ""
    if content_asset and isinstance(content_asset.content, dict):
        shot_id_hint = str(content_asset.content.get("shot_id") or "").strip()
    for shot in plan.shots:
        if shot_id_hint and shot.id != shot_id_hint:
            continue
        from core.edit.sub_shot_helpers import find_sub_shot_index_by_video_clip

        if shot_id_hint or find_sub_shot_index_by_video_clip(shot, cid) is not None:
            bound = bind_video_clip_media(
                shot, cid, mid, sub_shot_idx=sub_shot_idx
            )
            return _apply_shot_update(store, script_id, shot.id, bound)
    if shot_id_hint:
        return False
    for shot in plan.shots:
        bound = bind_video_clip_media(shot, cid, mid, sub_shot_idx=sub_shot_idx)
        return _apply_shot_update(store, script_id, shot.id, bound)
    return False

