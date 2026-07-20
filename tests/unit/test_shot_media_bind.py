"""镜内 media_id 回填单元测试。"""

from __future__ import annotations

from core.edit.shot_media_bind import (
    bind_frame_media_to_plan,
    bind_shot_still_media,
    bind_shot_video_media_to_plan,
    sync_plan_image_media_from_frames,
)
from core.models.entities import (
    MediaAsset,
    MediaAssetType,
    Project,
    Script,
    ShotSubShotImage,
    TextAsset,
    TextAssetType,
    VideoPlan,
    VideoStyleMode,
)
from core.store.memory import MemoryStore
from tests.support.shot_fixtures import make_shot


def _store_with_shot() -> tuple[MemoryStore, str, str]:
    """构建含单镜 plan 的最小 store，返回 (store, script_id, project_id)。"""
    store = MemoryStore()
    project = Project(title="p")
    store.add_project(project)
    script = Script(project_id=project.id, title="s")
    store.add_script(script)
    shot = make_shot(order=0, text="镜一")
    store.set_video_plan(
        VideoPlan(script_id=script.id, mode=VideoStyleMode.STORYBOOK, shots=[shot])
    )
    return store, script.id, project.id


def test_bind_frame_media_updates_visual_and_video_track() -> None:
    """生图后应写入 visual.image.media_id 与 z0 video clip。"""
    store, script_id, project_id = _store_with_shot()
    plan = store.get_video_plan_for_script(script_id)
    assert plan
    shot = plan.shots[0]
    visual = shot.sub_shots[0]
    frame = TextAsset(
        project_id=project_id,
        script_id=script_id,
        type=TextAssetType.FRAME,
        name="画面·镜1",
        content={"description": "测试", "element_refs": {}},
    )
    store.add_text_asset(frame)
    shot = shot.model_copy(
        update={
            "sub_shots": [
                visual.model_copy(
                    update={
                        "images": [
                            ShotSubShotImage(frame_asset_id=frame.id, kind="static")
                        ]
                    }
                )
            ]
        }
    )
    store.set_video_plan(plan.model_copy(update={"shots": [shot]}))

    media = MediaAsset(
        project_id=project_id,
        script_id=script_id,
        type=MediaAssetType.IMAGE,
        name="frame.png",
        url="https://example.test/frame.png",
    )
    store.add_media_asset(media)
    frame.primary_media_id = media.id
    store.update_text_asset(frame)

    assert bind_frame_media_to_plan(store, script_id, frame.id, media.id)

    updated = store.get_video_plan_for_script(script_id)
    assert updated
    bound = updated.shots[0]
    assert bound.sub_shots[0].images
    assert bound.sub_shots[0].images[0].media_id == media.id
    assert bound.video_tracks[0].clips[0].media_id == media.id
    assert bound.video_tracks[0].clips[0].source_kind == "still"


def test_bind_shot_video_media_sets_video_kind() -> None:
    """生视频后应绑定 videos[] 与 z0 clip，不写入画面 images[]。"""
    store, script_id, project_id = _store_with_shot()
    plan = store.get_video_plan_for_script(script_id)
    assert plan
    shot = plan.shots[0]
    media = MediaAsset(
        project_id=project_id,
        script_id=script_id,
        type=MediaAssetType.VIDEO,
        name="clip.mp4",
        url="https://example.test/clip.mp4",
    )
    store.add_media_asset(media)

    assert bind_shot_video_media_to_plan(store, script_id, shot.id, media.id)

    updated = store.get_video_plan_for_script(script_id)
    assert updated
    bound = updated.shots[0]
    assert bound.sub_shots[0].videos
    assert bound.sub_shots[0].videos[0].media_id == media.id
    assert bound.sub_shots[0].videos[0].source_kind == "video"
    assert not any(img.media_id == media.id for img in bound.sub_shots[0].images)
    assert bound.video_tracks[0].clips[0].media_id == media.id
    assert bound.video_tracks[0].clips[0].source_kind == "video"


def test_sync_plan_image_media_from_frames_batch() -> None:
    """批量 sync 应从 frame primary_media 回填全部镜头。"""
    store, script_id, project_id = _store_with_shot()
    plan = store.get_video_plan_for_script(script_id)
    assert plan
    shot = plan.shots[0]
    frame = TextAsset(
        project_id=project_id,
        script_id=script_id,
        type=TextAssetType.FRAME,
        name="画面",
        content={"description": "x", "element_refs": {}},
    )
    store.add_text_asset(frame)
    media = MediaAsset(
        project_id=project_id,
        script_id=script_id,
        type=MediaAssetType.IMAGE,
        name="img",
        url="https://example.test/img.png",
    )
    store.add_media_asset(media)
    frame.primary_media_id = media.id
    store.update_text_asset(frame)
    visual = shot.sub_shots[0].model_copy(
        update={"images": [ShotSubShotImage(frame_asset_id=frame.id)]}
    )
    shot = shot.model_copy(update={"sub_shots": [visual]})
    store.set_video_plan(plan.model_copy(update={"shots": [shot]}))

    result = sync_plan_image_media_from_frames(store, script_id)
    assert result["bound_count"] == 1
    plan = store.get_video_plan_for_script(script_id)
    assert plan
    assert plan.shots[0].video_tracks[0].clips[0].media_id == media.id


def test_bind_shot_still_media_second_image_keeps_distinct_ids() -> None:
    """绑定非首张画面时不得复制首图 id（避免 React 重复 key）。"""
    shot = make_shot(order=0, text="多图")
    img0 = ShotSubShotImage(id="ssi_first", frame_asset_id="txt_f0", kind="static")
    img1 = ShotSubShotImage(id="ssi_second", frame_asset_id="txt_f1", kind="static")
    sub = shot.sub_shots[0].model_copy(update={"images": [img0, img1]})
    shot = shot.model_copy(update={"sub_shots": [sub]})

    bound = bind_shot_still_media(shot, 0, "media_img_2", image_idx=1)
    images = bound.sub_shots[0].images
    assert len(images) == 2
    assert images[0].id == "ssi_first"
    assert images[1].id == "ssi_second"
    assert images[1].media_id == "media_img_2"
    assert images[0].id != images[1].id


def test_parse_sub_shot_images_dedupes_duplicate_ids() -> None:
    """解析子镜 images 时重复 id 应重新分配。"""
    from core.llm.agent.llm_action import _parse_sub_shot_images

    parsed = _parse_sub_shot_images(
        {
            "images": [
                {"id": "ssi_dup", "frame_asset_id": "txt_a", "kind": "static"},
                {"id": "ssi_dup", "frame_asset_id": "txt_b", "kind": "static"},
            ]
        }
    )
    assert len(parsed) == 2
    assert parsed[0].id == "ssi_dup"
    assert parsed[1].id != "ssi_dup"
    assert parsed[0].frame_asset_id == "txt_a"
    assert parsed[1].frame_asset_id == "txt_b"
