"""EditTimeline 素材校验与 normalize_tracks 扩展字段测试。"""

import pytest

from core.edit.asset_resolver import MissingItem, resolve_clip_media, validate_edit_timeline
from core.edit.timeline import (
    build_timeline_layer_summary,
    enrich_timeline_audio_from_store,
    extract_agent_video_clips,
    flat_video_clips,
    format_layer_summary_text,
    normalize_tracks,
    timeline_board_items,
    validate_timeline_clips,
    video_layers_from_agent_clips,
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
    Shot,
    VideoStyleMode,
)
from core.store.memory import MemoryStore
from tests.support.frame_fixtures import ensure_shot_frame_image


def _video_layers_from_raw(raw: dict) -> list:
    """测试辅助：从含 video 键的 tracks dict 构建 video_layers。"""
    return video_layers_from_agent_clips(extract_agent_video_clips(raw))


def _timeline_from_tracks_raw(script_id: str, raw: dict, **kwargs) -> EditTimeline:
    """测试辅助：从 tracks 原始 dict 构建含 video_layers 的时间轴。"""
    return EditTimeline(
        script_id=script_id,
        tracks=normalize_tracks(raw),
        video_layers=_video_layers_from_raw(raw),
        **kwargs,
    )


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
    from core.models.entities import ShotSubShot

    shot = Shot(
        order=0,
        duration_ms=5000,
        sub_shots=[
            ShotSubShot(
                start_ms=0,
                end_ms=5000,
                description="老虎在雪原上",
                element_refs={"character": [char.id]},
                camera_motion="ken_burns_in",
            )
        ],
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
        mode=VideoStyleMode.STORYBOOK,
        shots=[shot],
    )
    store.set_video_plan(plan)
    store._test_shot_id = shot.id  # type: ignore[attr-defined]
    frame_id = shot.sub_shots[0].images[0].frame_asset_id if shot.sub_shots[0].images else ""
    frame_asset = store.get_text_asset(frame_id) if frame_id else None
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
    clip = extract_agent_video_clips(raw)[0]
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
    raw = {
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
    timeline = _timeline_from_tracks_raw(script_id, raw, duration_ms=5000)
    report = validate_edit_timeline(store_with_plan, timeline)
    assert report.ready is True
    assert report.missing_items == []
    assert len(report.resolved_clips) == 1


def test_validate_edit_timeline_missing_image_suggests_image_gen(store_with_plan: MemoryStore):
    script_id = store_with_plan._test_script_id  # type: ignore[attr-defined]
    raw = {
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
    timeline = _timeline_from_tracks_raw(script_id, raw, duration_ms=5000)
    report = validate_edit_timeline(store_with_plan, timeline)
    assert report.ready is False
    assert any(m.category == "image" for m in report.missing_items)
    assert report.missing_items[0].suggested_upstream == "image_gen"


def test_validate_edit_timeline_missing_audio_suggests_tts_gen(store_with_plan: MemoryStore):
    script_id = store_with_plan._test_script_id  # type: ignore[attr-defined]
    media_id = store_with_plan._test_media_id  # type: ignore[attr-defined]
    raw = {
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
    timeline = _timeline_from_tracks_raw(script_id, raw, duration_ms=5000)
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
    raw = {
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
    timeline = _timeline_from_tracks_raw(script_id, raw, duration_ms=3000)
    board = timeline_board_items(store_with_plan, timeline)
    clip = board["tracks"]["video"][0]
    assert clip["edit_description"] == "测试描述"
    assert clip.get("source_refs")


def test_resolve_clip_media_via_video_plan_shot_order_zero_based(store_with_plan: MemoryStore):
    script_id = store_with_plan._test_script_id  # type: ignore[attr-defined]
    media_id = store_with_plan._test_media_id  # type: ignore[attr-defined]
    raw = {
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
    timeline = _timeline_from_tracks_raw(script_id, raw, duration_ms=5000)
    clip = flat_video_clips(timeline)[0]
    plan = store_with_plan.get_video_plan_for_script(script_id)
    shot_by_id = {s.id: s for s in plan.shots} if plan else {}
    resolved = resolve_clip_media(
        store_with_plan, clip, script_id=script_id, shot_by_id=shot_by_id
    )
    assert resolved is not None
    assert resolved.media_id == media_id
    assert resolved.is_accessible is True


def test_resolve_clip_media_via_video_plan_shot_order_one_based(store_with_plan: MemoryStore):
    pytest.skip("1-based shot order 回退已移除")


def test_timeline_board_items_preview_url_via_shot_order(store_with_plan: MemoryStore):
    script_id = store_with_plan._test_script_id  # type: ignore[attr-defined]
    raw = {
        "video": [
            {
                "track": "video",
                "start_ms": 0,
                "end_ms": 5000,
                "source_refs": {
                    "shot_id": "shot_1",
                    "video_plan_shot_order": 0,
                },
            }
        ],
        "audio": [],
        "subtitle": [],
    }
    timeline = _timeline_from_tracks_raw(script_id, raw, duration_ms=5000)
    board = timeline_board_items(store_with_plan, timeline)
    clip = board["tracks"]["video"][0]
    assert clip["preview_url"] == "https://images.test/tiger.png"
    assert clip["preview_media_type"] == "image"


def test_ensure_video_layers_migrates_legacy_tracks(store_with_plan: MemoryStore):
    pytest.skip("legacy tracks.video 迁移已移除")


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
    timeline = _timeline_from_tracks_raw(
        script_id,
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
        },
        duration_ms=5000,
    )
    board = timeline_board_items(store_with_plan, timeline)
    assert board["video_layers"]
    assert len(board["video_layers"]) == 1
    assert board["video_layers"][0]["clips"][0]["preview_url"]


def test_enrich_timeline_audio_is_noop(store_with_plan: MemoryStore):
    """镜内多轨为权威源：enrich 不再补齐 audio（投影已含完整轨）。"""
    script_id = store_with_plan._test_script_id  # type: ignore[attr-defined]
    plan = store_with_plan.get_video_plan_for_script(script_id)
    timeline = _timeline_from_tracks_raw(script_id, {"video": [], "audio": [], "subtitle": []})
    enriched = enrich_timeline_audio_from_store(store_with_plan, timeline, plan)
    assert enriched is timeline
    assert enriched.tracks.get("audio", []) == []


def test_enrich_audio_preserves_existing_clips(store_with_plan: MemoryStore):
    """enrich 不修改已有 audio clip。"""
    script_id = store_with_plan._test_script_id  # type: ignore[attr-defined]
    media_id = store_with_plan._test_media_id  # type: ignore[attr-defined]
    shot_id = store_with_plan._test_shot_id  # type: ignore[attr-defined]
    plan = store_with_plan.get_video_plan_for_script(script_id)
    timeline = _timeline_from_tracks_raw(
        script_id,
        {
            "video": [],
            "audio": [
                {
                    "track": "audio",
                    "start_ms": 100,
                    "end_ms": 200,
                    "asset_ref": media_id,
                    "metadata": {"shot_id": shot_id},
                }
            ],
            "subtitle": [],
        },
    )
    enriched = enrich_timeline_audio_from_store(store_with_plan, timeline, plan)
    audio_clips = enriched.tracks.get("audio", [])
    assert len(audio_clips) == 1
    assert audio_clips[0].start_ms == 100
    assert audio_clips[0].end_ms == 200


def test_enrich_audio_skips_duplicate_shot_id(store_with_plan: MemoryStore):
    """enrich 不追加重复 audio（保持原轨不变）。"""
    script_id = store_with_plan._test_script_id  # type: ignore[attr-defined]
    media_id = store_with_plan._test_media_id  # type: ignore[attr-defined]
    shot_id = store_with_plan._test_shot_id  # type: ignore[attr-defined]
    plan = store_with_plan.get_video_plan_for_script(script_id)
    timeline = _timeline_from_tracks_raw(
        script_id,
        {
            "audio": [
                {
                    "track": "audio",
                    "start_ms": 0,
                    "end_ms": 5000,
                    "asset_ref": media_id,
                    "metadata": {"shot_id": shot_id},
                }
            ],
        },
    )
    enriched = enrich_timeline_audio_from_store(store_with_plan, timeline, plan)
    assert len(enriched.tracks.get("audio", [])) == 1


def test_enrich_does_not_realign_agent_audio(store_with_plan: MemoryStore):
    """enrich 不再重对齐 Agent 错误时序（由镜内结构 + compile 负责）。"""
    script_id = store_with_plan._test_script_id  # type: ignore[attr-defined]
    media_id = store_with_plan._test_media_id  # type: ignore[attr-defined]
    plan = store_with_plan.get_video_plan_for_script(script_id)
    timeline = _timeline_from_tracks_raw(
        script_id,
        {
            "audio": [
                {
                    "track": "audio",
                    "start_ms": 100,
                    "end_ms": 200,
                    "asset_ref": media_id,
                }
            ],
        },
    )
    enriched = enrich_timeline_audio_from_store(store_with_plan, timeline, plan)
    audio_clips = enriched.tracks.get("audio", [])
    assert audio_clips[0].start_ms == 100
    assert audio_clips[0].end_ms == 200


def test_validate_edit_timeline_accepts_gentle_push_in_motion(store_with_plan: MemoryStore):
    script_id = store_with_plan._test_script_id  # type: ignore[attr-defined]
    media_id = store_with_plan._test_media_id  # type: ignore[attr-defined]
    raw = {
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
    timeline = _timeline_from_tracks_raw(script_id, raw, duration_ms=5000)
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


def test_sync_audio_clip_extends_when_media_longer_than_clip(
    store_with_plan: MemoryStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """metadata 偏短 + 探测更长时，sync 应拉长 audio/subtitle clip。"""
    from core.edit.timeline import sync_audio_clip_durations_to_media

    script_id = store_with_plan._test_script_id  # type: ignore[attr-defined]
    shot_id = store_with_plan._test_shot_id  # type: ignore[attr-defined]
    media_id = store_with_plan._test_media_id  # type: ignore[attr-defined]
    script = store_with_plan.get_script(script_id)
    assert script

    audio = MediaAsset(
        project_id=script.project_id,
        script_id=script_id,
        type=MediaAssetType.AUDIO,
        name="旁白",
        url="/data/fake/narration.mp3",
        metadata={"shot_id": shot_id, "duration_ms": 5000, "used_planned_timeline": True},
    )
    store_with_plan.add_media_asset(audio)

    monkeypatch.setattr(
        "core.llm.tools.shared.media_list.resolve_media_access",
        lambda _url: {"file_path": "/fake/narration.mp3", "link": "", "is_accessible": True},
    )
    monkeypatch.setattr(
        "core.media.duration_probe.probe_media_duration_ms",
        lambda _path, _type: 10000,
    )

    timeline = _timeline_from_tracks_raw(
        script_id,
        {
            "video": [
                {
                    "track": "video",
                    "start_ms": 0,
                    "end_ms": 12000,
                    "asset_ref": media_id,
                    "metadata": {"shot_id": shot_id},
                }
            ],
            "audio": [
                {
                    "track": "audio",
                    "start_ms": 0,
                    "end_ms": 5000,
                    "asset_ref": audio.id,
                    "metadata": {"shot_id": shot_id},
                }
            ],
            "subtitle": [
                {
                    "track": "subtitle",
                    "start_ms": 0,
                    "end_ms": 5000,
                    "label": "老虎在雪原上",
                    "metadata": {"shot_id": shot_id},
                }
            ],
        },
        duration_ms=12000,
    )
    synced = sync_audio_clip_durations_to_media(store_with_plan, timeline)
    audio_clip = synced.tracks["audio"][0]
    subtitle_clip = synced.tracks["subtitle"][0]
    assert audio_clip.end_ms == 10000
    assert subtitle_clip.end_ms == 10000
    updated = store_with_plan.media_assets[audio.id]
    assert int((updated.metadata or {}).get("duration_ms") or 0) == 10000


def test_analyze_emits_audio_shorter_than_media_hint(
    store_with_plan: MemoryStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """analyze API 应对 clip 短于素材时长发出 audio_shorter_than_media。"""
    from core.edit.timeline_analysis import analyze_edit_timeline

    script_id = store_with_plan._test_script_id  # type: ignore[attr-defined]
    shot_id = store_with_plan._test_shot_id  # type: ignore[attr-defined]
    script = store_with_plan.get_script(script_id)
    assert script

    audio = MediaAsset(
        project_id=script.project_id,
        script_id=script_id,
        type=MediaAssetType.AUDIO,
        name="旁白",
        url="/data/fake/narration.mp3",
        metadata={"shot_id": shot_id, "duration_ms": 5000},
    )
    store_with_plan.add_media_asset(audio)

    monkeypatch.setattr(
        "core.llm.tools.shared.media_list.resolve_media_access",
        lambda _url: {"file_path": "/fake/narration.mp3"},
    )
    monkeypatch.setattr(
        "core.media.duration_probe.probe_media_duration_ms",
        lambda _path, _type: 10000,
    )

    timeline = _timeline_from_tracks_raw(
        script_id,
        {
            "video": [],
            "audio": [
                {
                    "id": "aud_short",
                    "track": "audio",
                    "start_ms": 0,
                    "end_ms": 5000,
                    "asset_ref": audio.id,
                    "metadata": {"shot_id": shot_id},
                }
            ],
            "subtitle": [],
        },
        duration_ms=5000,
    )
    result = analyze_edit_timeline(store_with_plan, timeline)
    types = [h.get("type") for h in result.optimization_hints]
    assert "audio_shorter_than_media" in types
