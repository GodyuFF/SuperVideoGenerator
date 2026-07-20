"""Shot 视频生成规格解析单元测试。"""

from __future__ import annotations

from core.llm.tools.video.agnes_client import KEYFRAMES_MODE_MARKER
from core.llm.tools.video.shot_spec import resolve_shot_video_gen_spec
from core.models.entities import (
    MediaAsset,
    MediaAssetType,
    Project,
    Script,
    ShotSubShotImage,
    ShotSubShotVideo,
    TextAsset,
    TextAssetType,
    VideoPlan,
    VideoStyleMode,
)
from core.store.memory import MemoryStore
from tests.support.shot_fixtures import make_shot


def _store_with_shot_and_frame() -> tuple[MemoryStore, str, object, str]:
    """构建含画面资产的 store，返回 (store, script_id, shot, frame_id)。"""
    store = MemoryStore()
    project = Project(title="p")
    store.add_project(project)
    script = Script(project_id=project.id, title="s")
    store.add_script(script)
    frame = TextAsset(
        project_id=project.id,
        script_id=script.id,
        type=TextAssetType.FRAME,
        name="画面1",
        content={"description": "夕阳海滩", "element_refs": {}},
    )
    store.add_text_asset(frame)
    media = MediaAsset(
        project_id=project.id,
        script_id=script.id,
        type=MediaAssetType.IMAGE,
        name="frame.png",
        url="https://example.test/frame.png",
    )
    store.add_media_asset(media)
    frame.primary_media_id = media.id
    store.update_text_asset(frame)

    shot = make_shot(order=0, text="镜一")
    sub = shot.sub_shots[0]
    shot = shot.model_copy(
        update={
            "review_note": "慢镜头",
            "sub_shots": [
                sub.model_copy(
                    update={
                        "description": "猫在沙滩行走",
                        "images": [
                            ShotSubShotImage(
                                frame_asset_id=frame.id,
                                media_id=media.id,
                                kind="video",
                            )
                        ],
                    }
                )
            ],
        }
    )
    store.set_video_plan(
        VideoPlan(script_id=script.id, mode=VideoStyleMode.AI_VIDEO, shots=[shot])
    )
    return store, script.id, shot, frame.id


def test_resolve_img2video_from_frame_media() -> None:
    """有画面图片时应解析为图生视频。"""
    store, _, shot, _ = _store_with_shot_and_frame()
    spec = resolve_shot_video_gen_spec(store, shot)
    assert spec.mode == "img2video"
    assert spec.image_url
    assert "猫在沙滩" in spec.prompt


def test_resolve_text2video_without_image() -> None:
    """无图片仅有描述时应为文生视频。"""
    store, _, shot, _ = _store_with_shot_and_frame()
    sub = shot.sub_shots[0]
    shot = shot.model_copy(
        update={
            "sub_shots": [
                sub.model_copy(
                    update={
                        "images": [
                            ShotSubShotImage(
                                kind="video",
                                video_prompt="宇航员在红色星球漫步",
                            )
                        ]
                    }
                )
            ]
        }
    )
    spec = resolve_shot_video_gen_spec(
        store, shot, allowed_modes=["text2video", "img2video", "keyframes"]
    )
    assert spec.mode == "text2video"
    assert spec.image_url is None
    assert "宇航员" in spec.prompt


def test_resolve_keyframes_marker() -> None:
    """video_prompt 为关键帧标记时应解析为 keyframes。"""
    store, script_id, shot, frame_id = _store_with_shot_and_frame()
    script = store.get_script(script_id)
    assert script
    frame2 = TextAsset(
        project_id=script.project_id,
        script_id=script_id,
        type=TextAssetType.FRAME,
        name="画面2",
        content={"description": "特写", "element_refs": {}},
    )
    store.add_text_asset(frame2)
    media2 = MediaAsset(
        project_id=script.project_id,
        script_id=script_id,
        type=MediaAssetType.IMAGE,
        name="frame2.png",
        url="https://example.test/frame2.png",
    )
    store.add_media_asset(media2)
    frame2.primary_media_id = media2.id
    store.update_text_asset(frame2)

    sub = shot.sub_shots[0]
    media_id = sub.images[0].media_id
    shot = shot.model_copy(
        update={
            "sub_shots": [
                sub.model_copy(
                    update={
                        "images": [
                            ShotSubShotImage(
                                frame_asset_id=frame_id,
                                media_id=media_id,
                                kind="video",
                                video_prompt=KEYFRAMES_MODE_MARKER,
                            ),
                            ShotSubShotImage(
                                frame_asset_id=frame2.id,
                                media_id=media2.id,
                                kind="video",
                            ),
                        ]
                    }
                )
            ]
        }
    )
    spec = resolve_shot_video_gen_spec(store, shot)
    assert spec.mode == "keyframes"
    assert len(spec.keyframe_urls) >= 2


def test_resolve_img2video_source_frame_override() -> None:
    """videos[].source_frame_asset_id 应优先作为图生视频源。"""
    store, _, shot, frame_id = _store_with_shot_and_frame()
    sub = shot.sub_shots[0]
    shot = shot.model_copy(
        update={
            "sub_shots": [
                sub.model_copy(
                    update={
                        "videos": [
                            ShotSubShotVideo(source_frame_asset_id=frame_id)
                        ],
                    }
                )
            ]
        }
    )
    spec = resolve_shot_video_gen_spec(store, shot)
    assert spec.mode == "img2video"
    assert spec.source_frame_asset_id == frame_id


def test_explicit_two_frames_keyframes() -> None:
    """显式选择 2 张画面参考时应解析为关键帧模式。"""
    store, script_id, shot, frame_id = _store_with_shot_and_frame()
    script = store.get_script(script_id)
    assert script
    frame2 = TextAsset(
        project_id=script.project_id,
        script_id=script.id,
        type=TextAssetType.FRAME,
        name="画面2",
        content={"description": "远景", "element_refs": {}},
    )
    store.add_text_asset(frame2)
    media2 = MediaAsset(
        project_id=script.project_id,
        script_id=script.id,
        type=MediaAssetType.IMAGE,
        name="frame2.png",
        url="https://example.test/frame2.png",
    )
    store.add_media_asset(media2)
    frame2.primary_media_id = media2.id
    store.update_text_asset(frame2)

    spec = resolve_shot_video_gen_spec(
        store,
        shot,
        source_frame_asset_ids=[frame_id, frame2.id],
        allowed_modes=["text2video", "img2video", "keyframes"],
    )
    assert spec.mode == "keyframes"
    assert len(spec.keyframe_urls) >= 2
    assert frame_id in spec.source_frame_asset_ids
    assert frame2.id in spec.source_frame_asset_ids


def test_explicit_character_ref_img2video() -> None:
    """显式选择角色形象参考时应解析为图生视频。"""
    store, script_id, shot, _ = _store_with_shot_and_frame()
    script = store.get_script(script_id)
    assert script
    character = TextAsset(
        project_id=script.project_id,
        script_id=script_id,
        type=TextAssetType.CHARACTER,
        name="主角",
        content={"summary": "少年", "element_refs": {}},
    )
    store.add_text_asset(character)
    char_media = MediaAsset(
        project_id=script.project_id,
        script_id=script_id,
        type=MediaAssetType.IMAGE,
        name="hero.png",
        url="https://example.test/hero.png",
    )
    store.add_media_asset(char_media)
    character.primary_media_id = char_media.id
    store.update_text_asset(character)

    spec = resolve_shot_video_gen_spec(
        store,
        shot,
        source_element_refs={"character": [character.id]},
        allowed_modes=["text2video", "img2video", "keyframes"],
    )
    assert spec.mode == "img2video"
    assert spec.image_url
    assert "hero.png" in spec.image_url or "example.test" in spec.image_url
