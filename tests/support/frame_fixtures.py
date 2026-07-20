"""测试用画面（frame）资产与镜头关联辅助（新模型：镜内多轨 Shot）。"""

from __future__ import annotations

from core.models.entities import (
    AssetScope,
    MediaAsset,
    MediaAssetType,
    Shot,
    ShotVideoClip,
    ShotVideoTrack,
    ShotSubShot,
    ShotSubShotImage,
    TextAsset,
    TextAssetType,
    new_id,
)
from core.store.memory import MemoryStore


def ensure_shot_frame_image(
    store: MemoryStore,
    *,
    project_id: str,
    script_id: str,
    shot: Shot,
    element_refs: dict[str, list[str]] | None = None,
    image_url: str = "https://images.test/frame.png",
) -> tuple[TextAsset, MediaAsset]:
    """为镜头创建 frame 文字资产与配图，并绑定到镜内首个画面与 z0 视频 clip。"""
    refs = dict(element_refs or {})
    if not refs and shot.sub_shots:
        refs = dict(shot.sub_shots[0].element_refs)

    frame = TextAsset(
        project_id=project_id,
        script_id=script_id,
        type=TextAssetType.FRAME,
        scope=AssetScope.SCRIPT_PRIVATE,
        name=f"画面·镜{shot.order + 1}",
        content={
            "description": (shot.sub_shots[0].description if shot.sub_shots else "测试画面"),
            "element_refs": refs,
            "shot_id": shot.id,
        },
        source_script_id=script_id,
        reuse_policy="private",
    )
    store.add_text_asset(frame)
    media = MediaAsset(
        project_id=project_id,
        script_id=script_id,
        type=MediaAssetType.IMAGE,
        name=frame.name,
        url=image_url,
        source_asset_id=frame.id,
    )
    store.add_media_asset(media)
    frame.primary_media_id = media.id
    store.update_text_asset(frame)

    # 确保有画面并绑定图片
    if not shot.sub_shots:
        shot.sub_shots = [
            ShotSubShot(
                id=new_id("vis"),
                start_ms=0,
                end_ms=shot.duration_ms,
                description="测试画面",
                element_refs=refs,
            )
        ]
    shot.sub_shots[0].images = [
        ShotSubShotImage(kind="static", frame_asset_id=frame.id, media_id=media.id)
    ]
    # 确保 z0 视频轨 clip 绑定 media
    if not shot.video_tracks:
        shot.video_tracks = [
            ShotVideoTrack(
                id=new_id("svt"),
                name="主画面",
                z_index=0,
                clips=[
                    ShotVideoClip(
                        id=new_id("svc"),
                        start_ms=0,
                        end_ms=shot.duration_ms,
                        source_sub_shot_id=shot.sub_shots[0].id,
                        media_id=media.id,
                        source_kind="still",
                    )
                ],
            )
        ]
    else:
        for track in shot.video_tracks:
            for clip in track.clips:
                if not clip.media_id:
                    clip.media_id = media.id
    return frame, media
