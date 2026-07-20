"""子镜 images/videos 访问与更新辅助。"""

from __future__ import annotations

from core.models.entities import (
    Shot,
    ShotSubShot,
    ShotSubShotImage,
    ShotSubShotVideo,
)


def first_sub_shot_image(sub: ShotSubShot) -> ShotSubShotImage | None:
    """取子镜首张关联图片（单图语义的便捷访问）。"""
    return sub.images[0] if sub.images else None


def find_image_index_by_frame(sub: ShotSubShot, frame_asset_id: str) -> int | None:
    """在子镜 images 中按 frame_asset_id 定位索引。"""
    fid = frame_asset_id.strip()
    if not fid:
        return None
    for idx, img in enumerate(sub.images):
        if img.frame_asset_id.strip() == fid:
            return idx
    return None


def find_sub_shot_index_by_frame(shot: Shot, frame_asset_id: str) -> int | None:
    """在镜内子镜列表中按 frame_asset_id 定位子镜索引。"""
    for idx, sub in enumerate(shot.sub_shots):
        if find_image_index_by_frame(sub, frame_asset_id) is not None:
            return idx
    return None


def sub_shot_has_frame_link(sub: ShotSubShot) -> bool:
    """子镜是否已关联至少一个剧本画面资产。"""
    return any(img.frame_asset_id.strip() for img in sub.images)


def upsert_sub_shot_image(
    sub: ShotSubShot,
    image: ShotSubShotImage,
    *,
    image_idx: int = 0,
) -> ShotSubShot:
    """更新或追加子镜内指定位置的图片引用。"""
    images = list(sub.images)
    while len(images) <= image_idx:
        images.append(ShotSubShotImage())
    images[image_idx] = image
    return sub.model_copy(update={"images": images})


def append_sub_shot_image(sub: ShotSubShot, image: ShotSubShotImage) -> ShotSubShot:
    """向子镜追加一张图片引用。"""
    return sub.model_copy(update={"images": [*sub.images, image]})


def append_sub_shot_video(sub: ShotSubShot, video: ShotSubShotVideo) -> ShotSubShot:
    """向子镜追加一段视频引用。"""
    return sub.model_copy(update={"videos": [*sub.videos, video]})


def link_sub_shot_frame(sub: ShotSubShot, image: ShotSubShotImage) -> ShotSubShot:
    """将 frame 写入首个空 images 槽；无空槽则追加。保留占位时段与 id。"""
    for idx, existing in enumerate(sub.images):
        if (existing.frame_asset_id or "").strip():
            continue
        merged = image.model_copy(
            update={
                "id": existing.id,
                "start_ms": int(existing.start_ms or 0) or int(image.start_ms or 0),
                "end_ms": int(existing.end_ms or 0) or int(image.end_ms or 0),
                "kind": existing.kind or image.kind,
            }
        )
        return upsert_sub_shot_image(sub, merged, image_idx=idx)
    return append_sub_shot_image(sub, image)


def link_sub_shot_video(sub: ShotSubShot, video: ShotSubShotVideo) -> ShotSubShot:
    """将 video_clip 写入首个空 videos 槽；无空槽则追加。保留占位时段与 id。"""
    for idx, existing in enumerate(sub.videos):
        if (existing.video_clip_asset_id or "").strip():
            continue
        merged = video.model_copy(
            update={
                "id": existing.id,
                "start_ms": int(existing.start_ms or 0) or int(video.start_ms or 0),
                "end_ms": int(existing.end_ms or 0) or int(video.end_ms or 0),
                "source_kind": existing.source_kind or video.source_kind,
                "camera_motion": video.camera_motion or existing.camera_motion,
            }
        )
        return upsert_sub_shot_video(sub, merged, video_idx=idx)
    return append_sub_shot_video(sub, video)


def find_video_index_by_clip(sub: ShotSubShot, video_clip_asset_id: str) -> int | None:
    """在子镜 videos 中按 video_clip_asset_id 定位索引。"""
    cid = video_clip_asset_id.strip()
    if not cid:
        return None
    for idx, vid in enumerate(sub.videos):
        if vid.video_clip_asset_id.strip() == cid:
            return idx
    return None


def find_sub_shot_index_by_video_clip(shot: Shot, video_clip_asset_id: str) -> int | None:
    """在镜内子镜列表中按 video_clip_asset_id 定位子镜索引。"""
    for idx, sub in enumerate(shot.sub_shots):
        if find_video_index_by_clip(sub, video_clip_asset_id) is not None:
            return idx
    return None


def sub_shot_has_video_clip_link(sub: ShotSubShot) -> bool:
    """子镜是否已关联至少一个 video_clip 文字资产。"""
    return any(v.video_clip_asset_id.strip() for v in sub.videos)


def upsert_sub_shot_video(
    sub: ShotSubShot,
    video: ShotSubShotVideo,
    *,
    video_idx: int = 0,
) -> ShotSubShot:
    """更新或追加子镜内指定位置的视频引用。"""
    videos = list(sub.videos)
    while len(videos) <= video_idx:
        videos.append(ShotSubShotVideo())
    videos[video_idx] = video
    return sub.model_copy(update={"videos": videos})


def primary_sub_shot_media_id(sub: ShotSubShot) -> str:
    """取子镜首选 media：首张图片或首段视频。"""
    if sub.images and sub.images[0].media_id:
        return sub.images[0].media_id.strip()
    if sub.videos and sub.videos[0].media_id:
        return sub.videos[0].media_id.strip()
    return ""
