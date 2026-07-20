"""主编排 pipeline 进度推断测试。"""

import pytest

from core.llm.master.pipeline_progress import (
    _tts_complete,
    build_pipeline_progress,
    detect_resume_target_step,
    infer_completed_step_types,
)
from core.models.entities import (
    AssetScope,
    MediaAsset,
    MediaAssetType,
    Project,
    Script,
    TextAsset,
    TextAssetType,
    VideoPlan,
    Shot,
    VideoStyleMode,
)
from core.edit.shot_detail_sync import apply_shot_detail_patches, sync_plan_from_tts
from core.store.memory import MemoryStore
from tests.support.frame_fixtures import ensure_shot_frame_image
from tests.support.image_text_fixtures import prop_content
from tests.support.shot_fixtures import make_shot


@pytest.fixture
def ready_for_edit_store() -> MemoryStore:
    store = MemoryStore()
    project = Project(title="续跑测试")
    store.add_project(project)
    script = Script(
        project_id=project.id,
        title="小猫吃鱼",
        duration_sec=60,
        content_md="# 小猫吃鱼\n\n一只猫在河边。",
    )
    store.add_script(script)
    prop = TextAsset(
        project_id=project.id,
        script_id=script.id,
        type=TextAssetType.PROP,
        scope=AssetScope.SCRIPT_PRIVATE,
        name="鱼",
        content=prop_content(summary="鱼"),
    )
    store.add_text_asset(prop)
    media = MediaAsset(
        project_id=project.id,
        script_id=script.id,
        type=MediaAssetType.IMAGE,
        name="鱼图",
        url="https://images.test/fish.png",
        source_asset_id=prop.id,
    )
    store.add_media_asset(media)
    prop.primary_media_id = media.id
    store.update_text_asset(prop)
    shot = make_shot(order=0, duration_ms=5000, text="小猫吃鱼", camera_motion="ken_burns_in")
    shot.sub_shots[0].element_refs = {"prop": [prop.id]}
    ensure_shot_frame_image(
        store,
        project_id=project.id,
        script_id=script.id,
        shot=shot,
        image_url="https://images.test/frame.png",
    )
    plan = VideoPlan(
        script_id=script.id,
        mode=VideoStyleMode.STORYBOOK,
        shots=[shot],
    )
    store.set_video_plan(plan)
    audio = MediaAsset(
        project_id=project.id,
        script_id=script.id,
        type=MediaAssetType.AUDIO,
        name="旁白",
        url="https://audio.test/narration.mp3",
        metadata={"shot_id": shot.id, "duration_ms": 5000},
    )
    store.add_media_asset(audio)
    sync_plan_from_tts(store, script.id)
    apply_shot_detail_patches(
        store,
        script.id,
        [{"shot_id": shot.id, "display_instructions": "静态展示主体"}],
    )
    store._test_script_id = script.id  # type: ignore[attr-defined]
    return store


def test_detect_resume_target_step_edit_compose():
    assert detect_resume_target_step("从剪辑合成继续") == "edit_compose"
    assert detect_resume_target_step("continue edit compose") == "edit_compose"
    assert detect_resume_target_step("做个新剧本") is None


def test_infer_completed_step_types_when_assets_ready(ready_for_edit_store: MemoryStore):
    script_id = ready_for_edit_store._test_script_id  # type: ignore[attr-defined]
    completed = infer_completed_step_types(
        ready_for_edit_store, script_id, VideoStyleMode.STORYBOOK
    )
    assert "script_design" in completed
    assert "image_gen" in completed
    assert "storyboard" in completed
    assert "tts_gen" in completed
    assert "shot_detail" in completed


def test_build_pipeline_progress_ready_for_edit(ready_for_edit_store: MemoryStore):
    script_id = ready_for_edit_store._test_script_id  # type: ignore[attr-defined]
    progress = build_pipeline_progress(
        ready_for_edit_store, script_id, VideoStyleMode.STORYBOOK
    )
    assert progress["ready_for_edit_compose"] is True
    assert progress["gaps"] == []
    assert "storyboard" in progress["inferred_completed_steps"]
    assert "eligible_delegates" in progress
    assert "delegate_readiness" in progress


def test_detect_resume_target_step_shot_detail():
    assert detect_resume_target_step("从分镜详设继续") == "shot_detail"
    assert detect_resume_target_step("shot_detail refine") == "shot_detail"


def test_tts_complete_false_when_all_shots_missing_voice():
    """图文管线：有子镜但全镜无 voice text 时 TTS 不应视为完成。"""
    store = MemoryStore()
    project = Project(title="无旁白")
    store.add_project(project)
    script = Script(project_id=project.id, title="s1")
    store.add_script(script)
    shot = make_shot(order=0, duration_ms=4000, text="")
    shot.audio_tracks = []
    store.set_video_plan(
        VideoPlan(script_id=script.id, mode=VideoStyleMode.STORYBOOK, shots=[shot])
    )
    assert _tts_complete(store, script.id) is False


def test_shot_detail_incomplete_blocks_edit_ready():
    """TTS 完成但详设未完成时，不应 ready_for_edit_compose。"""
    store = MemoryStore()
    project = Project(title="详设缺口")
    store.add_project(project)
    script = Script(project_id=project.id, title="s1", duration_sec=30)
    store.add_script(script)
    shot = make_shot(order=0, duration_ms=4000, text="旁白")
    ensure_shot_frame_image(
        store,
        project_id=project.id,
        script_id=script.id,
        shot=shot,
        image_url="https://images.test/frame.png",
    )
    store.set_video_plan(
        VideoPlan(script_id=script.id, mode=VideoStyleMode.STORYBOOK, shots=[shot])
    )
    store.add_media_asset(
        MediaAsset(
            project_id=project.id,
            script_id=script.id,
            type=MediaAssetType.AUDIO,
            name="tts",
            url="https://audio.test/a.mp3",
            metadata={"shot_id": shot.id, "duration_ms": 4000},
        )
    )
    progress = build_pipeline_progress(store, script.id, VideoStyleMode.STORYBOOK)
    assert progress["ready_for_edit_compose"] is False
    assert any("shot_detail" in g for g in progress["gaps"])


def test_image_gen_incomplete_when_frame_refs_ready_but_no_image():
    store = MemoryStore()
    project = Project(title="frame 测试")
    store.add_project(project)
    script = Script(project_id=project.id, title="s1", duration_sec=30)
    store.add_script(script)
    prop = TextAsset(
        project_id=project.id,
        script_id=script.id,
        type=TextAssetType.PROP,
        scope=AssetScope.SCRIPT_PRIVATE,
        name="鱼",
        content=prop_content(summary="鱼"),
    )
    store.add_text_asset(prop)
    media = MediaAsset(
        project_id=project.id,
        script_id=script.id,
        type=MediaAssetType.IMAGE,
        name="鱼图",
        url="https://images.test/fish.png",
        source_asset_id=prop.id,
    )
    store.add_media_asset(media)
    prop.primary_media_id = media.id
    store.update_text_asset(prop)
    frame = TextAsset(
        project_id=project.id,
        script_id=script.id,
        type=TextAssetType.FRAME,
        scope=AssetScope.SCRIPT_PRIVATE,
        name="画面",
        content={
            "description": "测试",
            "element_refs": {"prop": [prop.id]},
            "shot_id": "",
        },
    )
    store.add_text_asset(frame)
    shot = make_shot(order=0, duration_ms=4000, text="镜头")
    shot.sub_shots[0].element_refs = {"prop": [prop.id]}
    from core.models.entities import ShotSubShotImage

    shot.sub_shots[0].images = [
        ShotSubShotImage(kind="static", frame_asset_id=frame.id, media_id="")
    ]
    store.set_video_plan(
        VideoPlan(
            script_id=script.id,
            mode=VideoStyleMode.STORYBOOK,
            shots=[shot],
        )
    )
    completed = infer_completed_step_types(
        store, script.id, VideoStyleMode.STORYBOOK
    )
    assert "image_gen" not in completed


def test_storyboard_incomplete_when_sub_shot_missing_frame():
    """单子镜有 frame、另一子镜无 frame 时 storyboard/image_gen 管线应未完成。"""
    from core.llm.master.pipeline_progress import _frames_cover_all_shots
    from core.models.entities import ShotSubShot, ShotSubShotImage, new_id

    store = MemoryStore()
    project = Project(title="双子镜")
    store.add_project(project)
    script = Script(project_id=project.id, title="s1")
    store.add_script(script)
    shot = make_shot(order=0, duration_ms=6000, text="旁白")
    sub_b = ShotSubShot(
        id=new_id("ssb"),
        start_ms=3000,
        end_ms=6000,
        description="无 frame 子镜",
        camera_motion="static",
    )
    shot.sub_shots[0].images = [ShotSubShotImage(frame_asset_id="frame_ok")]
    shot = shot.model_copy(update={"sub_shots": [shot.sub_shots[0], sub_b]})
    store.set_video_plan(
        VideoPlan(
            script_id=script.id,
            mode=VideoStyleMode.STORYBOOK,
            shots=[shot],
        )
    )
    assert _frames_cover_all_shots(store, script.id) is False

