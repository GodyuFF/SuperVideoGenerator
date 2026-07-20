"""分镜镜级时间轴解析单元测试（新模型：镜内结构为权威源）。"""

import pytest

from core.edit.shot_timing import resolve_shot_timings
from core.edit.timeline import compile_timeline_from_shots
from core.models.entities import MediaAsset, MediaAssetType
from core.store.memory import MemoryStore
from tests.support.shot_fixtures import _store_with_two_shots
from tests.support.timeline_store_fixture import timeline_store  # noqa: F401


def test_resolve_shot_timings_plan_estimate_without_timeline(timeline_store: MemoryStore):
    """无 EditTimeline 时按镜内结构累加估算时间。"""
    script_id = timeline_store._test_script_id  # type: ignore[attr-defined]
    timeline_store.edit_timelines.clear()
    timings = resolve_shot_timings(timeline_store, script_id)
    assert len(timings) == 1
    view = timings[0]
    assert view.timeline_source == "plan_estimate"
    assert view.timeline_start_ms == 0
    assert view.timeline_end_ms >= 3000


def test_resolve_shot_timings_ignores_edit_timeline(timeline_store: MemoryStore):
    """镜内结构为权威源：即使有 user_edited EditTimeline 仍用 plan_estimate。"""
    script_id = timeline_store._test_script_id  # type: ignore[attr-defined]
    timeline = timeline_store.get_edit_timeline_for_script(script_id)
    assert timeline
    layer = timeline.video_layers[0]
    clip = layer.clips[0]
    updated_clip = clip.model_copy(update={"start_ms": 1500, "end_ms": 4500})
    timeline = timeline.model_copy(
        update={
            "user_edited": True,
            "video_layers": [
                layer.model_copy(update={"clips": [updated_clip]}),
            ],
        }
    )
    timeline_store.set_edit_timeline(timeline)

    timings = resolve_shot_timings(timeline_store, script_id)
    assert timings[0].timeline_source == "plan_estimate"
    assert timings[0].timeline_start_ms == 0
    assert timings[0].timeline_end_ms >= 3000


def test_subtitle_lines_from_shot_subtitles(timeline_store: MemoryStore):
    """句级字幕来自 Shot.subtitles 并偏移到全局时间轴。"""
    script_id = timeline_store._test_script_id  # type: ignore[attr-defined]
    timings = resolve_shot_timings(timeline_store, script_id)
    lines = timings[0].subtitle_lines
    assert len(lines) >= 1
    assert lines[0].absolute_start_ms == lines[0].start_ms


def test_resolve_shot_timings_two_shots_accumulate():
    """多镜按有效时长顺序累加偏移。"""
    store, script_id, shot1, shot2 = _store_with_two_shots()
    timings = resolve_shot_timings(store, script_id)
    assert len(timings) == 2
    assert timings[0].timeline_start_ms == 0
    assert timings[1].timeline_start_ms == timings[0].timeline_end_ms


def test_sync_plan_from_tts_does_not_realign_edit_timeline():
    """TTS 同步仅写分镜计划稿，不自动重排剪辑时间轴。"""
    from core.edit.shot_detail_sync import sync_plan_from_tts

    store, script_id, shot1, shot2 = _store_with_two_shots()
    project_id = list(store.projects.keys())[0]
    plan = store.get_video_plan_for_script(script_id)
    assert plan
    store.set_edit_timeline(compile_timeline_from_shots(store, script_id=script_id, plan=plan))
    timeline_before = store.get_edit_timeline_for_script(script_id)
    assert timeline_before is not None
    rev_before = timeline_before.revision

    for shot, dur, text in (
        (shot1, 2500, "镜一"),
        (shot2, 4000, "镜二"),
    ):
        store.add_media_asset(
            MediaAsset(
                project_id=project_id,
                script_id=script_id,
                type=MediaAssetType.AUDIO,
                name=text,
                url=f"https://audio.test/{shot.id}.mp3",
                metadata={
                    "shot_id": shot.id,
                    "duration_ms": dur,
                    "subtitle_cues": [{"text": text, "start_ms": 0, "end_ms": dur}],
                },
            )
        )
    result = sync_plan_from_tts(store, script_id)
    assert "timeline_realigned" not in result

    timeline_after = store.get_edit_timeline_for_script(script_id)
    assert timeline_after is not None
    assert timeline_after.revision == rev_before

    timings = resolve_shot_timings(store, script_id)
    assert timings[0].timeline_source == "plan_estimate"
    assert timings[1].timeline_start_ms == timings[0].timeline_end_ms


def test_compile_timeline_sets_source_refs(timeline_store: MemoryStore):
    """compile_timeline_from_shots 应写入 shot source_refs。"""
    script_id = timeline_store._test_script_id  # type: ignore[attr-defined]
    plan = timeline_store.get_video_plan_for_script(script_id)
    assert plan
    shot = plan.shots[0]
    timeline = compile_timeline_from_shots(timeline_store, script_id=script_id, plan=plan)
    clip = timeline.video_layers[0].clips[0]
    assert clip.source_refs is not None
    assert clip.source_refs.shot_id == shot.id
    assert clip.source_refs.video_plan_shot_order == shot.order
