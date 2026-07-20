"""画面图生视频（frame_i2v）模式单元测试。"""

from __future__ import annotations

import pytest

from core.llm.agent.llm_action import (
    _assert_sub_shots_have_frames,
    _assert_sub_shots_have_video_clips,
)
from core.llm.master.actions import filter_storyboard_pipeline_actions
from core.llm.master.pipeline_progress import (
    _edit_compose_gaps,
    infer_completed_step_types,
)
from core.llm.style.style_mode_registry import StyleModeRegistry
from core.llm.tools.video.frame_i2v_spec import resolve_frame_i2v_clip_spec
from core.llm.tools.video.video_clips import collect_video_clip_specs
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


def _shot_with_frame_and_clip(*, with_frame: bool = True, with_clip: bool = True):
    """构造带子镜 frame / video_clip 关联的镜头。"""
    shot = make_shot(order=0, text="镜一")
    sub = shot.sub_shots[0]
    frame_id = "txt_frame_test"
    clip_id = "txt_vc_test"
    images = []
    videos = []
    if with_frame:
        images = [ShotSubShotImage(frame_asset_id=frame_id)]
    if with_clip:
        videos = [
            ShotSubShotVideo(
                video_clip_asset_id=clip_id,
                source_frame_asset_id=frame_id if with_frame else "",
            )
        ]
    shot = shot.model_copy(
        update={
            "sub_shots": [
                sub.model_copy(update={"images": images, "videos": videos})
            ]
        }
    )
    return shot, frame_id, clip_id


def test_style_registry_lists_frame_i2v():
    """内置风格注册表应包含 frame_i2v 及三种 video 子模式。"""
    modes = StyleModeRegistry.list_style_modes()
    entry = next(m for m in modes if m["id"] == VideoStyleMode.FRAME_I2V.value)
    assert entry["label"] == "画面图生视频"
    assert set(entry["video"]) == {"text2video", "img2video", "keyframes"}


def test_storyboard_pipeline_keeps_both_actions():
    """frame_i2v 分镜流水线应同时保留 create_frames 与 create_video_clips。"""
    full = [
        "load_context",
        "create_shots",
        "create_frames",
        "create_video_clips",
        "persist_plan",
    ]
    filtered = filter_storyboard_pipeline_actions(full, VideoStyleMode.FRAME_I2V)
    assert "create_frames" in filtered
    assert "create_video_clips" in filtered


def test_persist_plan_requires_both_frame_and_video_clip():
    """frame_i2v persist 前每子镜须同时有 frame 与 video_clip。"""
    shot_ok, _, _ = _shot_with_frame_and_clip(with_frame=True, with_clip=True)
    _assert_sub_shots_have_frames(VideoStyleMode.FRAME_I2V, [shot_ok])
    _assert_sub_shots_have_video_clips(VideoStyleMode.FRAME_I2V, [shot_ok])

    shot_no_frame, _, _ = _shot_with_frame_and_clip(with_frame=False, with_clip=True)
    with pytest.raises(ValueError, match="frame"):
        _assert_sub_shots_have_frames(VideoStyleMode.FRAME_I2V, [shot_no_frame])

    shot_no_clip, _, _ = _shot_with_frame_and_clip(with_frame=True, with_clip=False)
    with pytest.raises(ValueError, match="video_clip"):
        _assert_sub_shots_have_video_clips(VideoStyleMode.FRAME_I2V, [shot_no_clip])


def _build_frame_i2v_store(*, with_frame_image: bool = True) -> tuple[MemoryStore, str, str, str]:
    """构建 frame_i2v 测试 store，返回 (store, script_id, frame_id, clip_id)。"""
    store = MemoryStore()
    project = Project(title="p")
    store.add_project(project)
    script = Script(
        project_id=project.id,
        title="s",
        style_mode=VideoStyleMode.FRAME_I2V.value,
    )
    store.add_script(script)

    shot, frame_id, clip_id = _shot_with_frame_and_clip()
    frame = TextAsset(
        id=frame_id,
        project_id=project.id,
        script_id=script.id,
        type=TextAssetType.FRAME,
        name="画面1",
        content={"image_prompt": "静态合成画面", "element_refs": {}},
    )
    store.add_text_asset(frame)
    clip = TextAsset(
        id=clip_id,
        project_id=project.id,
        script_id=script.id,
        type=TextAssetType.VIDEO_CLIP,
        name="视频1",
        content={
            "video_prompt": "镜头缓慢推进，人物微微转头，光影随云层变化",
            "element_refs": {},
        },
    )
    store.add_text_asset(clip)

    if with_frame_image:
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
        sub = shot.sub_shots[0]
        shot = shot.model_copy(
            update={
                "sub_shots": [
                    sub.model_copy(
                        update={
                            "images": [
                                ShotSubShotImage(
                                    frame_asset_id=frame_id,
                                    media_id=media.id,
                                )
                            ]
                        }
                    )
                ]
            }
        )

    store.set_video_plan(
        VideoPlan(
            script_id=script.id,
            mode=VideoStyleMode.FRAME_I2V,
            shots=[shot],
        )
    )
    return store, script.id, frame_id, clip_id


def test_resolve_frame_i2v_uses_frame_for_img2video():
    """有 frame 图片时应解析为 img2video，且 prompt 来自 video_clip。"""
    store, script_id, _, clip_id = _build_frame_i2v_store(with_frame_image=True)
    spec = resolve_frame_i2v_clip_spec(
        store,
        script_id,
        clip_id,
        allowed_modes=["text2video", "img2video", "keyframes"],
    )
    assert spec.mode == "img2video"
    assert spec.image_url == "https://example.test/frame.png"
    assert "镜头缓慢推进" in spec.prompt


def test_resolve_frame_i2v_text2video_without_frame_image():
    """无 frame 图片时应回退 text2video。"""
    store, script_id, _, clip_id = _build_frame_i2v_store(with_frame_image=False)
    spec = resolve_frame_i2v_clip_spec(
        store,
        script_id,
        clip_id,
        allowed_modes=["text2video", "img2video", "keyframes"],
    )
    assert spec.mode == "text2video"
    assert spec.image_url is None


def test_collect_video_clip_specs_uses_frame_i2v_resolver():
    """frame_i2v 风格下 collect_video_clip_specs 应走 frame 优先解析。"""
    store, script_id, _, clip_id = _build_frame_i2v_store(with_frame_image=True)
    specs = collect_video_clip_specs(
        store,
        script_id,
        {"asset_ids": [clip_id]},
    )
    assert len(specs) == 1
    assert specs[0].mode == "img2video"
    assert specs[0].video_clip_asset_id == clip_id


def test_edit_compose_gaps_require_image_and_video_for_frame_i2v():
    """frame_i2v 剪辑前须同时满足 image_gen 与 video_gen。"""
    store, script_id, _, _ = _build_frame_i2v_store(with_frame_image=True)
    gaps = _edit_compose_gaps(store, script_id)
    assert any("video_gen" in g for g in gaps)
    assert any("tts" in g.lower() or "配音" in g for g in gaps)


def test_infer_completed_excludes_video_gen_until_ready():
    """frame_i2v 在 video 未生成时不应推断 video_gen 完成。"""
    store, script_id, _, _ = _build_frame_i2v_store(with_frame_image=True)
    completed = infer_completed_step_types(
        store, script_id, VideoStyleMode.FRAME_I2V
    )
    assert "video_gen" not in completed
