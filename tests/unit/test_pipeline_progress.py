"""主编排 pipeline 进度推断测试。"""

import pytest

from core.llm.master.pipeline_progress import (
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
    VideoPlanShot,
    VideoStyleMode,
)
from core.store.memory import MemoryStore
from tests.support.frame_fixtures import ensure_shot_frame_image
from tests.support.image_text_fixtures import prop_content


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
    shot = VideoPlanShot(
        order=0,
        duration_ms=5000,
        narration_text="小猫吃鱼",
        camera_motion="ken_burns_in",
        asset_refs={"prop": [prop.id]},
    )
    ensure_shot_frame_image(
        store,
        project_id=project.id,
        script_id=script.id,
        shot=shot,
        image_url="https://images.test/frame.png",
    )
    plan = VideoPlan(
        script_id=script.id,
        mode=VideoStyleMode.DYNAMIC_IMAGE,
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
    store._test_script_id = script.id  # type: ignore[attr-defined]
    return store


def test_detect_resume_target_step_edit_compose():
    assert detect_resume_target_step("从剪辑合成继续") == "edit_compose"
    assert detect_resume_target_step("continue edit compose") == "edit_compose"
    assert detect_resume_target_step("做个新剧本") is None


def test_infer_completed_step_types_when_assets_ready(ready_for_edit_store: MemoryStore):
    script_id = ready_for_edit_store._test_script_id  # type: ignore[attr-defined]
    completed = infer_completed_step_types(
        ready_for_edit_store, script_id, VideoStyleMode.DYNAMIC_IMAGE
    )
    assert "script_design" in completed
    assert "image_gen" in completed
    assert "storyboard" in completed
    assert "tts_gen" in completed


def test_build_pipeline_progress_ready_for_edit(ready_for_edit_store: MemoryStore):
    script_id = ready_for_edit_store._test_script_id  # type: ignore[attr-defined]
    progress = build_pipeline_progress(
        ready_for_edit_store, script_id, VideoStyleMode.DYNAMIC_IMAGE
    )
    assert progress["ready_for_edit_compose"] is True
    assert progress["gaps"] == []
    assert "storyboard" in progress["inferred_completed_steps"]


def test_image_gen_incomplete_when_frame_refs_ready_but_no_image():
    """frame 参考图就绪但仍缺图时，image_gen 不应视为完成。"""
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
    shot = VideoPlanShot(
        order=0,
        duration_ms=4000,
        narration_text="镜头",
        asset_refs={"prop": [prop.id]},
    )
    frame = TextAsset(
        project_id=project.id,
        script_id=script.id,
        type=TextAssetType.FRAME,
        scope=AssetScope.SCRIPT_PRIVATE,
        name="画面",
        content={
            "description": "测试",
            "element_refs": {"prop": [prop.id]},
            "shot_id": shot.id,
        },
    )
    store.add_text_asset(frame)
    shot.asset_refs = {"prop": [prop.id], "frame": [frame.id]}
    store.set_video_plan(
        VideoPlan(
            script_id=script.id,
            mode=VideoStyleMode.DYNAMIC_IMAGE,
            shots=[shot],
        )
    )
    completed = infer_completed_step_types(
        store, script.id, VideoStyleMode.DYNAMIC_IMAGE
    )
    assert "image_gen" not in completed

