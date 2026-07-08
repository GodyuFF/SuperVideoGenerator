"""EditTimeline 素材校验与 normalize_tracks 扩展字段测试。"""

import pytest

from core.edit.asset_resolver import MissingItem, resolve_clip_media, validate_edit_timeline
from core.edit.timeline import (
    build_timeline_layer_summary,
    enrich_timeline_audio_from_store,
    ensure_video_layers,
    format_layer_summary_text,
    normalize_tracks,
    timeline_board_items,
    validate_timeline_clips,
)
from core.models.entities import (
    AssetScope,
    EditClip,
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
from tests.support.frame_fixtures import ensure_shot_frame_image


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
        content={"summary": "虎", "description": "东北虎" * 20},
    )
    store.add_text_asset(char)
    media = MediaAsset(
        project_id=project.id,
        script_id=script.id,
        type=MediaAssetType.IMAGE,
        name="虎图",
        url="https://images.test/tiger.png",
        source_asset_id=char.id,
    )
    store.add_media_asset(media)
    char.primary_media_id = media.id
    store.update_text_asset(char)
    shot = VideoPlanShot(
        order=0,
        duration_ms=5000,
        narration_text="老虎在雪原上",
        camera_motion="ken_burns_in",
        asset_refs={"character": [char.id]},
    )
    ensure_shot_frame_image(
        store,
        project_id=project.id,
        script_id=script.id,
        shot=shot,
        image_url="https://images.test/tiger.png",
    )
    plan = VideoPlan(
        script_id=script.id,
        mode=VideoStyleMode.DYNAMIC_IMAGE,
        shots=[shot],
    )
    store.set_video_plan(plan)
    store._test_shot_id = shot.id  # type: ignore[attr-defined]
    store._test_media_id = shot.asset_refs["frame"][0]  # frame text id; resolve uses frame media
    frame_asset = store.get_text_asset(shot.asset_refs["frame"][0])
    assert frame_asset and frame_asset.primary_media_id
    store._test_media_id = frame_asset.primary_media_id  # type: ignore[attr-defined]
    store._test_script_id = script.id  # type: ignore[attr-defined]
    return store


def test_normalize_tracks_parses_extended_clip_fields():
    raw = {
        "video": [
            {
                "track": "video",
                "start_ms": 0,
                "end_ms": 3000,
                "label": "开场",
                "edit_description": "Ken Burns 从左上推向主体",
                "transition_in": {"type": "fade", "duration_ms": 300},
                "transition_out": {"type": "dissolve", "duration_ms": 500},
                "background": {"type": "solid", "color": "#112233"},
                "motion_detail": {
                    "type": "ken_burns_in",
                    "from_focal": [0.1, 0.2],
                    "to_focal": [0.5, 0.5],
                    "scale_from": 1.0,
                    "scale_to": 1.2,
                },
                "source_refs": {
                    "shot_id": "shot_x",
                    "text_asset_ids": ["txt_a"],
                    "media_ids": ["img_a"],
                },
            }
        ],
        "audio": [],
        "subtitle": [],
    }
    tracks = normalize_tracks(raw)
    clip = tracks["video"][0]
    assert clip.edit_description.startswith("Ken Burns")
    assert clip.transition_in is not None
    assert clip.transition_in.type == "fade"
    assert clip.background is not None
    assert clip.motion_detail is not None
    assert clip.source_refs is not None
    assert clip.source_refs.shot_id == "shot_x"


def test_validate_edit_timeline_ready_when_media_resolved(store_with_plan: MemoryStore):
    script_id = store_with_plan._test_script_id  # type: ignore[attr-defined]
    media_id = store_with_plan._test_media_id  # type: ignore[attr-defined]
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
                        "asset_ref": media_id,
                    }
                ],
                "audio": [],
                "subtitle": [],
            }
        ),
    )
    report = validate_edit_timeline(store_with_plan, timeline)
    assert report.ready is True
    assert report.missing_items == []
    assert len(report.resolved_clips) == 1


def test_validate_edit_timeline_missing_image_suggests_image_gen(store_with_plan: MemoryStore):
    script_id = store_with_plan._test_script_id  # type: ignore[attr-defined]
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
                        "label": "缺图",
                        "asset_ref": "img_missing",
                        "source_refs": {
                            "shot_id": "shot_unknown",
                            "text_asset_ids": ["txt_missing"],
                        },
                    }
                ],
                "audio": [],
                "subtitle": [],
            }
        ),
    )
    report = validate_edit_timeline(store_with_plan, timeline)
    assert report.ready is False
    assert any(m.category == "image" for m in report.missing_items)
    assert report.missing_items[0].suggested_upstream == "image_gen"


def test_validate_edit_timeline_missing_audio_suggests_tts_gen(store_with_plan: MemoryStore):
    script_id = store_with_plan._test_script_id  # type: ignore[attr-defined]
    media_id = store_with_plan._test_media_id  # type: ignore[attr-defined]
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
                        "asset_ref": media_id,
                    }
                ],
                "audio": [
                    {
                        "track": "audio",
                        "start_ms": 0,
                        "end_ms": 5000,
                        "label": "旁白",
                        "asset_ref": "aud_missing",
                    }
                ],
                "subtitle": [],
            }
        ),
    )
    report = validate_edit_timeline(store_with_plan, timeline)
    assert report.ready is False
    audio_missing = [m for m in report.missing_items if m.category == "audio"]
    assert audio_missing
    assert audio_missing[0].suggested_upstream == "tts_gen"


def test_validate_empty_timeline_suggests_plan_edit_timeline(store_with_plan: MemoryStore):
    script_id = store_with_plan._test_script_id  # type: ignore[attr-defined]
    timeline = EditTimeline(script_id=script_id, duration_ms=0, tracks=normalize_tracks({}))
    report = validate_edit_timeline(store_with_plan, timeline)
    assert report.ready is False
    assert any("plan_edit_timeline" in m.reason for m in report.missing_items)


def test_timeline_board_items_includes_extended_fields(store_with_plan: MemoryStore):
    script_id = store_with_plan._test_script_id  # type: ignore[attr-defined]
    timeline = EditTimeline(
        script_id=script_id,
        duration_ms=3000,
        tracks=normalize_tracks(
            {
                "video": [
                    {
                        "track": "video",
                        "start_ms": 0,
                        "end_ms": 3000,
                        "edit_description": "测试描述",
                        "source_refs": {"shot_id": "s1"},
                    }
                ],
                "audio": [],
                "subtitle": [],
            }
        ),
    )
    board = timeline_board_items(store_with_plan, timeline)
    clip = board["tracks"]["video"][0]
    assert clip["edit_description"] == "测试描述"
    assert clip.get("source_refs")


def test_resolve_clip_media_via_video_plan_shot_order_zero_based(store_with_plan: MemoryStore):
    script_id = store_with_plan._test_script_id  # type: ignore[attr-defined]
    media_id = store_with_plan._test_media_id  # type: ignore[attr-defined]
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
                        "source_refs": {
                            "shot_id": "shot_placeholder",
                            "video_plan_shot_order": 0,
                        },
                    }
                ],
                "audio": [],
                "subtitle": [],
            }
        ),
    )
    clip = timeline.tracks["video"][0]
    plan = store_with_plan.get_video_plan_for_script(script_id)
    shot_by_id = {s.id: s for s in plan.shots} if plan else {}
    resolved = resolve_clip_media(
        store_with_plan, clip, script_id=script_id, shot_by_id=shot_by_id
    )
    assert resolved is not None
    assert resolved.media_id == media_id
    assert resolved.is_accessible is True


def test_resolve_clip_media_via_video_plan_shot_order_one_based(store_with_plan: MemoryStore):
    script_id = store_with_plan._test_script_id  # type: ignore[attr-defined]
    media_id = store_with_plan._test_media_id  # type: ignore[attr-defined]
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
                        "source_refs": {
                            "shot_id": "shot_1",
                            "video_plan_shot_order": 1,
                        },
                    }
                ],
                "audio": [],
                "subtitle": [],
            }
        ),
    )
    clip = timeline.tracks["video"][0]
    plan = store_with_plan.get_video_plan_for_script(script_id)
    shot_by_id = {s.id: s for s in plan.shots} if plan else {}
    resolved = resolve_clip_media(
        store_with_plan, clip, script_id=script_id, shot_by_id=shot_by_id
    )
    assert resolved is not None
    assert resolved.media_id == media_id


def test_timeline_board_items_preview_url_via_shot_order(store_with_plan: MemoryStore):
    script_id = store_with_plan._test_script_id  # type: ignore[attr-defined]
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
                        "source_refs": {
                            "shot_id": "shot_1",
                            "video_plan_shot_order": 1,
                        },
                    }
                ],
                "audio": [],
                "subtitle": [],
            }
        ),
    )
    board = timeline_board_items(store_with_plan, timeline)
    clip = board["tracks"]["video"][0]
    assert clip["preview_url"] == "https://images.test/tiger.png"
    assert clip["preview_media_type"] == "image"


def test_ensure_video_layers_migrates_legacy_tracks(store_with_plan: MemoryStore):
    script_id = store_with_plan._test_script_id  # type: ignore[attr-defined]
    media_id = store_with_plan._test_media_id  # type: ignore[attr-defined]
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
                        "asset_ref": media_id,
                    }
                ],
                "audio": [],
                "subtitle": [],
            }
        ),
    )
    assert timeline.video_layers == []
    migrated = ensure_video_layers(timeline)
    assert len(migrated.video_layers) == 1
    assert migrated.video_layers[0].name == "主画面"
    assert len(migrated.video_layers[0].clips) == 1
    assert migrated.video_layers[0].clips[0].transform is not None


def test_validate_timeline_clips_allows_cross_layer_overlap(store_with_plan: MemoryStore):
    script_id = store_with_plan._test_script_id  # type: ignore[attr-defined]
    media_id = store_with_plan._test_media_id  # type: ignore[attr-defined]
    layer_a = "vly_a"
    layer_b = "vly_b"
    timeline = EditTimeline(
        script_id=script_id,
        duration_ms=5000,
        tracks=normalize_tracks({"video": [], "audio": [], "subtitle": []}),
        video_layers=[
            {
                "id": layer_a,
                "name": "主画面",
                "z_index": 0,
                "clips": [
                    {
                        "track": "video",
                        "start_ms": 0,
                        "end_ms": 5000,
                        "asset_ref": media_id,
                        "layer_id": layer_a,
                    }
                ],
            },
            {
                "id": layer_b,
                "name": "画中画",
                "z_index": 1,
                "clips": [
                    {
                        "track": "video",
                        "start_ms": 0,
                        "end_ms": 5000,
                        "asset_ref": media_id,
                        "layer_id": layer_b,
                        "transform": {"x": 0.8, "y": 0.2, "width": 0.3, "height": 0.3},
                    }
                ],
            },
        ],
    )
    warnings = validate_timeline_clips(timeline)
    assert not any("重叠" in w for w in warnings)


def test_validate_timeline_clips_warns_same_layer_overlap(store_with_plan: MemoryStore):
    script_id = store_with_plan._test_script_id  # type: ignore[attr-defined]
    media_id = store_with_plan._test_media_id  # type: ignore[attr-defined]
    layer_id = "vly_main"
    timeline = EditTimeline(
        script_id=script_id,
        duration_ms=5000,
        tracks=normalize_tracks({"video": [], "audio": [], "subtitle": []}),
        video_layers=[
            {
                "id": layer_id,
                "name": "主画面",
                "z_index": 0,
                "clips": [
                    {
                        "track": "video",
                        "start_ms": 0,
                        "end_ms": 4000,
                        "asset_ref": media_id,
                    },
                    {
                        "track": "video",
                        "start_ms": 3000,
                        "end_ms": 5000,
                        "asset_ref": media_id,
                    },
                ],
            }
        ],
    )
    warnings = validate_timeline_clips(timeline)
    assert any("重叠" in w for w in warnings)


def test_timeline_board_items_includes_video_layers(store_with_plan: MemoryStore):
    script_id = store_with_plan._test_script_id  # type: ignore[attr-defined]
    media_id = store_with_plan._test_media_id  # type: ignore[attr-defined]
    timeline = ensure_video_layers(
        EditTimeline(
            script_id=script_id,
            duration_ms=5000,
            tracks=normalize_tracks(
                {
                    "video": [
                        {
                            "track": "video",
                            "start_ms": 0,
                            "end_ms": 5000,
                            "asset_ref": media_id,
                        }
                    ],
                    "audio": [],
                    "subtitle": [],
                }
            ),
        )
    )
    board = timeline_board_items(store_with_plan, timeline)
    assert board["video_layers"]
    assert len(board["video_layers"]) == 1
    assert board["video_layers"][0]["clips"][0]["preview_url"]


def test_enrich_timeline_audio_from_store_fills_empty_audio(store_with_plan: MemoryStore):
    from core.models.entities import MediaAsset, MediaAssetType

    script_id = store_with_plan._test_script_id  # type: ignore[attr-defined]
    media_id = store_with_plan._test_media_id  # type: ignore[attr-defined]
    shot_id = store_with_plan._test_shot_id  # type: ignore[attr-defined]
    plan = store_with_plan.get_video_plan_for_script(script_id)
    assert plan

    script = store_with_plan.get_script(script_id)
    assert script
    audio = MediaAsset(
        project_id=script.project_id,
        script_id=script_id,
        type=MediaAssetType.AUDIO,
        name="旁白",
        url="https://audio.test/narration.mp3",
        metadata={"shot_id": shot_id, "duration_ms": 5000},
    )
    store_with_plan.add_media_asset(audio)

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
                        "asset_ref": media_id,
                        "metadata": {"shot_id": shot_id},
                    }
                ],
                "audio": [],
                "subtitle": [],
            }
        ),
    )
    enriched = enrich_timeline_audio_from_store(store_with_plan, timeline, plan)
    audio_clips = enriched.tracks.get("audio", [])
    assert len(audio_clips) == 1
    assert audio_clips[0].asset_ref == audio.id
    report = validate_edit_timeline(store_with_plan, enriched)
    assert report.ready is True


def test_validate_edit_timeline_accepts_gentle_push_in_motion(store_with_plan: MemoryStore):
    script_id = store_with_plan._test_script_id  # type: ignore[attr-defined]
    media_id = store_with_plan._test_media_id  # type: ignore[attr-defined]
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
                        "asset_ref": media_id,
                        "motion": "gentle_push_in",
                    }
                ],
                "audio": [],
                "subtitle": [],
            }
        ),
    )
    report = validate_edit_timeline(store_with_plan, timeline)
    assert report.ready is True


def test_build_timeline_layer_summary_includes_transform_and_overlaps(
    store_with_plan: MemoryStore,
):
    script_id = store_with_plan._test_script_id  # type: ignore[attr-defined]
    media_id = store_with_plan._test_media_id  # type: ignore[attr-defined]
    timeline = EditTimeline(
        script_id=script_id,
        duration_ms=5000,
        tracks=normalize_tracks({"video": [], "audio": [], "subtitle": []}),
        video_layers=[
            {
                "id": "vly_pip",
                "name": "画中画",
                "z_index": 1,
                "clips": [
                    {
                        "id": "clip_a",
                        "track": "video",
                        "start_ms": 0,
                        "end_ms": 4000,
                        "asset_ref": media_id,
                        "transform": {"x": 0.8, "y": 0.2, "width": 0.3, "height": 0.3},
                    },
                    {
                        "id": "clip_b",
                        "track": "video",
                        "start_ms": 3000,
                        "end_ms": 5000,
                        "asset_ref": media_id,
                        "transform": {"x": 0.2, "y": 0.8, "width": 0.3, "height": 0.3},
                    },
                ],
            }
        ],
    )
    summary = build_timeline_layer_summary(store_with_plan, timeline)
    assert summary["max_video_layers"] == 5
    assert len(summary["video_layers"]) == 1
    clips = summary["video_layers"][0]["clips"]
    assert clips[0]["transform"]["width"] == 0.3
    assert clips[1]["overlap_with_prev"] is True
    assert summary["same_layer_overlaps"]
    assert summary["same_layer_overlaps"][0]["clip_id"] == "clip_b"
    text = format_layer_summary_text(summary)
    assert "Layer1" in text
    assert "同层重叠" in text


def test_format_layer_summary_text_no_layers():
    text = format_layer_summary_text({"video_layers": [], "warnings": []})
    assert text == "无视频层"
