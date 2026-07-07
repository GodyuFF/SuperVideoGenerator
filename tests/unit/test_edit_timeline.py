"""EditTimeline 模型与编译测试。"""

import pytest

from core.edit.compose import compose_timeline_plan, gather_timeline_media
from core.edit.image_sync import apply_auto_patch_to_content, split_image_observations
from core.edit.timeline import (
    compile_timeline_from_shots,
    merge_timeline_with_fallback,
    normalize_tracks,
    validate_timeline_clips,
)
from core.models.entities import (
    AssetScope,
    EditTimeline,
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
from core.store.persist import load_store, save_store
from tests.support.image_text_fixtures import prop_content


@pytest.fixture
def store_with_plan() -> MemoryStore:
    store = MemoryStore()
    project = Project(title="p")
    store.add_project(project)
    script = Script(project_id=project.id, title="s1", duration_sec=60)
    store.add_script(script)
    char = TextAsset(
        project_id=project.id,
        script_id=script.id,
        type=TextAssetType.CHARACTER,
        scope=AssetScope.SCRIPT_PRIVATE,
        name="虎",
        content=prop_content(summary="虎", description="东北虎"),
    )
    store.add_text_asset(char)
    media = MediaAsset(
        project_id=project.id,
        script_id=script.id,
        type=MediaAssetType.IMAGE,
        name="虎图",
        url="https://cdn.example.com/tiger.png",
        source_asset_id=char.id,
    )
    store.add_media_asset(media)
    char.primary_media_id = media.id
    store.update_text_asset(char)
    plan = VideoPlan(
        script_id=script.id,
        mode=VideoStyleMode.DYNAMIC_IMAGE,
        shots=[
            VideoPlanShot(
                order=0,
                duration_ms=5000,
                narration_text="老虎在雪原上",
                camera_motion="ken_burns_in",
                asset_refs={"character": [char.id]},
            )
        ],
    )
    store.set_video_plan(plan)
    return store


def test_compile_timeline_from_shots(store_with_plan: MemoryStore):
    script_id = list(store_with_plan.scripts.keys())[0]
    plan = store_with_plan.get_video_plan_for_script(script_id)
    assert plan
    timeline = compile_timeline_from_shots(store_with_plan, script_id=script_id, plan=plan)
    assert timeline.duration_ms == 5000
    assert len(timeline.tracks["video"]) == 1
    assert len(timeline.tracks["audio"]) == 1
    assert len(timeline.tracks["subtitle"]) == 1
    assert timeline.tracks["video"][0].asset_ref is not None


def test_merge_timeline_prefers_llm_tracks(store_with_plan: MemoryStore):
    script_id = list(store_with_plan.scripts.keys())[0]
    plan = store_with_plan.get_video_plan_for_script(script_id)
    llm = {
        "video": [
            {
                "track": "video",
                "start_ms": 0,
                "end_ms": 3000,
                "label": "自定义片段",
            }
        ],
        "audio": [],
        "subtitle": [],
    }
    timeline = merge_timeline_with_fallback(
        store_with_plan,
        script_id=script_id,
        plan=plan,
        llm_tracks=llm,
    )
    assert timeline.tracks["video"][0].label == "自定义片段"


def test_validate_timeline_overlap_warning():
    raw_tracks = {
        "video": [
            {"track": "video", "start_ms": 0, "end_ms": 3000, "label": "a"},
            {"track": "video", "start_ms": 2000, "end_ms": 4000, "label": "b"},
        ],
        "audio": [],
        "subtitle": [],
    }
    timeline = EditTimeline(
        script_id="s1",
        duration_ms=5000,
        tracks=normalize_tracks(raw_tracks),
    )
    warnings = validate_timeline_clips(timeline)
    assert warnings


def test_image_sync_auto_patch():
    auto, major, names = split_image_observations(
        {
            "color_palette": "橙黑",
            "description": "实际为孟加拉虎",
        }
    )
    assert "color_palette" in auto
    assert "description" in major
    patched = apply_auto_patch_to_content(
        TextAssetType.PROP,
        {"summary": "x", "description": "old", "color_palette": "灰"},
        auto,
    )
    assert patched["color_palette"] == "橙黑"


def test_compose_timeline_plan(store_with_plan: MemoryStore):
    script_id = list(store_with_plan.scripts.keys())[0]
    plan = store_with_plan.get_video_plan_for_script(script_id)
    timeline = compile_timeline_from_shots(store_with_plan, script_id=script_id, plan=plan)
    store_with_plan.set_edit_timeline(timeline)
    media = gather_timeline_media(store_with_plan, timeline)
    assert media["duration_ms"] == 5000
    compose = compose_timeline_plan(
        store_with_plan, timeline, style_mode=VideoStyleMode.DYNAMIC_IMAGE
    )
    assert compose["mode"] == "ken_burns_compose"
    assert len(compose["segments"]) == 1


def test_compose_resolves_clips_from_source_refs_only(store_with_plan: MemoryStore):
    """plan_edit_timeline 可能只写 source_refs，compose 应与 validate 一致解析 media。"""
    script_id = list(store_with_plan.scripts.keys())[0]
    char = next(iter(store_with_plan.text_assets.values()))
    assert char.primary_media_id
    media = store_with_plan.media_assets[char.primary_media_id]
    media.url = "https://images.test/tiger.png"
    timeline = EditTimeline(
        script_id=script_id,
        duration_ms=5000,
        tracks=normalize_tracks(
            {
                "video": [
                    {
                        "track": "video",
                        "start_ms": 0,
                        "end_ms": 5000,
                        "label": "虎",
                        "source_refs": {"text_asset_ids": [char.id]},
                    }
                ],
                "audio": [],
                "subtitle": [],
            }
        ),
    )
    media = gather_timeline_media(store_with_plan, timeline)
    assert media["missing_refs"] == []
    assert len(media["images"]) == 1
    compose = compose_timeline_plan(
        store_with_plan, timeline, style_mode=VideoStyleMode.DYNAMIC_IMAGE
    )
    assert compose["segments"][0]["asset_ref"] == char.primary_media_id
    assert compose["segments"][0]["url"]


def test_edit_timeline_persist_roundtrip(store_with_plan: MemoryStore, tmp_path):
    script_id = list(store_with_plan.scripts.keys())[0]
    plan = store_with_plan.get_video_plan_for_script(script_id)
    timeline = compile_timeline_from_shots(store_with_plan, script_id=script_id, plan=plan)
    store_with_plan.set_edit_timeline(timeline)
    path = tmp_path / "store.json"
    save_store(store_with_plan, path)
    loaded = MemoryStore()
    assert load_store(loaded, path)
    loaded_tl = loaded.get_edit_timeline_for_script(script_id)
    assert loaded_tl is not None
    assert loaded_tl.duration_ms == timeline.duration_ms
