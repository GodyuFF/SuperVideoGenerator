"""分镜镜级时间轴解析单元测试。"""

import pytest

from core.edit.shot_timing import resolve_shot_timings
from core.edit.timeline import compile_timeline_from_shots
from core.models.entities import (
    EditClip,
    EditClipSourceRefs,
    EditTimeline,
    EditVideoLayer,
    MediaAsset,
    MediaAssetType,
    VideoPlan,
    VideoPlanShot,
    new_id,
)
from core.store.memory import MemoryStore
from tests.support.timeline_store_fixture import timeline_store  # noqa: F401


def test_resolve_shot_timings_plan_estimate_without_timeline(timeline_store: MemoryStore):
    """无 EditTimeline 时按 plan + TTS 累加估算时间。"""
    script_id = timeline_store._test_script_id  # type: ignore[attr-defined]
    timeline_store.edit_timelines.clear()
    timings = resolve_shot_timings(timeline_store, script_id)
    assert len(timings) == 1
    view = timings[0]
    assert view.timeline_source == "plan_estimate"
    assert view.timeline_start_ms == 0
    assert view.timeline_end_ms >= 3000


def test_resolve_shot_timings_from_edit_timeline(timeline_store: MemoryStore):
    """有 EditTimeline 时以 clip 区间为准。"""
    script_id = timeline_store._test_script_id  # type: ignore[attr-defined]
    plan = timeline_store.get_video_plan_for_script(script_id)
    assert plan

    timeline = timeline_store.get_edit_timeline_for_script(script_id)
    assert timeline
    layer = timeline.video_layers[0]
    clip = layer.clips[0]
    updated_clip = clip.model_copy(update={"start_ms": 1500, "end_ms": 4500})
    timeline = timeline.model_copy(
        update={
            "video_layers": [
                layer.model_copy(update={"clips": [updated_clip]}),
            ]
        }
    )
    timeline_store.set_edit_timeline(timeline)

    timings = resolve_shot_timings(timeline_store, script_id)
    assert timings[0].timeline_source == "edit_timeline"
    assert timings[0].timeline_start_ms == 1500
    assert timings[0].timeline_end_ms == 4500


def test_subtitle_lines_absolute_offset(timeline_store: MemoryStore):
    """TTS subtitle_cues 应偏移到 audio clip 绝对时间。"""
    script_id = timeline_store._test_script_id  # type: ignore[attr-defined]
    plan = timeline_store.get_video_plan_for_script(script_id)
    assert plan
    shot = plan.shots[0]

    audio = next(
        m for m in timeline_store.list_media_for_script(script_id) if m.type == MediaAssetType.AUDIO
    )
    audio.metadata = {
        **(audio.metadata or {}),
        "shot_id": shot.id,
        "duration_ms": 3200,
        "subtitle_cues": [
            {"text": "老虎", "start_ms": 0, "end_ms": 1200},
            {"text": "在雪原上", "start_ms": 1200, "end_ms": 3200},
        ],
    }

    timeline = timeline_store.get_edit_timeline_for_script(script_id)
    assert timeline
    audio_clip = timeline.tracks["audio"][0]
    shifted = audio_clip.model_copy(update={"start_ms": 2000, "end_ms": 5200})
    timeline = timeline.model_copy(
        update={"tracks": {**timeline.tracks, "audio": [shifted]}}
    )
    timeline_store.set_edit_timeline(timeline)

    timings = resolve_shot_timings(timeline_store, script_id)
    lines = timings[0].subtitle_lines
    assert len(lines) == 2
    assert lines[0].absolute_start_ms == 2000
    assert lines[0].absolute_end_ms == 3200
    assert lines[1].absolute_start_ms == 3200
    assert lines[1].absolute_end_ms == 5200


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
