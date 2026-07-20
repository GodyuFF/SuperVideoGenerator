"""剪辑时间轴时间段分析单元测试。"""

from core.edit.timeline import compile_timeline_from_shots
from core.edit.timeline_analysis import AnalyzeTimelineRequest, analyze_edit_timeline
from core.store.memory import MemoryStore
from tests.support.timeline_store_fixture import timeline_store  # noqa: F401


def test_analyze_clips_in_range(timeline_store: MemoryStore):
    """应返回与区间相交的 clip。"""
    script_id = timeline_store._test_script_id  # type: ignore[attr-defined]
    plan = timeline_store.get_video_plan_for_script(script_id)
    timeline = compile_timeline_from_shots(timeline_store, script_id=script_id, plan=plan)
    timeline_store.set_edit_timeline(timeline)

    result = analyze_edit_timeline(
        timeline_store,
        timeline,
        AnalyzeTimelineRequest(start_ms=0, end_ms=1500),
    )
    assert result.range["start_ms"] == 0
    assert result.range["end_ms"] == 1500
    assert any(c["track"] == "video" for c in result.clips_in_range)
    assert any(c.get("partial") is True for c in result.clips_in_range)


def test_analyze_detects_gap_after_clip_shift(timeline_store: MemoryStore):
    """主视频层前移后区间开头应出现 gap。"""
    script_id = timeline_store._test_script_id  # type: ignore[attr-defined]
    plan = timeline_store.get_video_plan_for_script(script_id)
    timeline = compile_timeline_from_shots(timeline_store, script_id=script_id, plan=plan)
    layer = timeline.video_layers[0]
    clip = layer.clips[0].model_copy(update={"start_ms": 1000, "end_ms": 4000})
    timeline = timeline.model_copy(
        update={"video_layers": [layer.model_copy(update={"clips": [clip]})]}
    )

    result = analyze_edit_timeline(
        timeline_store,
        timeline,
        AnalyzeTimelineRequest(start_ms=0, end_ms=2000, include_hints=True),
    )
    video_gaps = [g for g in result.gaps if g.get("track") == "video"]
    assert any(g["start_ms"] == 0 and g["end_ms"] == 1000 for g in video_gaps)
    hint_types = {h["type"] for h in result.optimization_hints}
    assert "gap" in hint_types


def test_analyze_shot_alignment_mismatch(timeline_store: MemoryStore):
    """clip 时长与 plan 偏差应标记 mismatch。"""
    script_id = timeline_store._test_script_id  # type: ignore[attr-defined]
    plan = timeline_store.get_video_plan_for_script(script_id)
    timeline = compile_timeline_from_shots(timeline_store, script_id=script_id, plan=plan)
    layer = timeline.video_layers[0]
    clip = layer.clips[0].model_copy(update={"start_ms": 0, "end_ms": 8000})
    timeline = timeline.model_copy(
        update={"video_layers": [layer.model_copy(update={"clips": [clip]})]}
    )

    result = analyze_edit_timeline(
        timeline_store,
        timeline,
        AnalyzeTimelineRequest(include_hints=True),
    )
    assert result.shot_alignment
    row = result.shot_alignment[0]
    assert row["mismatch"] is True
    assert any(h["type"] == "shot_duration_mismatch" for h in result.optimization_hints)


def test_analyze_overlap_detection(timeline_store: MemoryStore):
    """同层重叠应出现在 overlaps 与 hints。"""
    script_id = timeline_store._test_script_id  # type: ignore[attr-defined]
    plan = timeline_store.get_video_plan_for_script(script_id)
    timeline = compile_timeline_from_shots(timeline_store, script_id=script_id, plan=plan)
    layer = timeline.video_layers[0]
    first = layer.clips[0]
    second = first.model_copy(
        update={
            "id": "clip_overlap",
            "start_ms": 2000,
            "end_ms": 5000,
            "label": "重叠段",
        }
    )
    timeline = timeline.model_copy(
        update={"video_layers": [layer.model_copy(update={"clips": [first, second]})]}
    )

    result = analyze_edit_timeline(
        timeline_store,
        timeline,
        AnalyzeTimelineRequest(start_ms=0, end_ms=6000, include_hints=True),
    )
    assert result.overlaps
    assert any(h["type"] == "overlap" for h in result.optimization_hints)


def test_analyze_clip_detail_fields(timeline_store: MemoryStore):
    """clips_in_range 应含 edit_description、transform、visible_range 与 resolved。"""
    script_id = timeline_store._test_script_id  # type: ignore[attr-defined]
    plan = timeline_store.get_video_plan_for_script(script_id)
    timeline = compile_timeline_from_shots(timeline_store, script_id=script_id, plan=plan)
    layer = timeline.video_layers[0]
    clip = layer.clips[0].model_copy(
        update={
            "edit_description": "主体居中，Ken Burns 推近",
            "motion": "ken_burns_in",
        }
    )
    timeline = timeline.model_copy(
        update={"video_layers": [layer.model_copy(update={"clips": [clip]})]}
    )
    timeline_store.set_edit_timeline(timeline)

    result = analyze_edit_timeline(
        timeline_store,
        timeline,
        AnalyzeTimelineRequest(start_ms=0, end_ms=3000, include_analysis=False),
    )
    assert result.clips_in_range
    video_clip = next(c for c in result.clips_in_range if c["track"] == "video")
    assert video_clip["edit_description"] == "主体居中，Ken Burns 推近"
    assert video_clip["motion"] == "ken_burns_in"
    assert "visible_range" in video_clip
    assert video_clip["visible_range"]["start_ms"] == 0
    assert "transform" in video_clip
    assert result.shot_alignment == []
    assert result.optimization_hints == []


def test_analyze_include_analysis_false_skips_alignment(timeline_store: MemoryStore):
    """include_analysis=false 时不输出 shot_alignment 与 optimization_hints。"""
    script_id = timeline_store._test_script_id  # type: ignore[attr-defined]
    plan = timeline_store.get_video_plan_for_script(script_id)
    timeline = compile_timeline_from_shots(timeline_store, script_id=script_id, plan=plan)
    timeline_store.set_edit_timeline(timeline)

    result = analyze_edit_timeline(
        timeline_store,
        timeline,
        AnalyzeTimelineRequest(include_analysis=False),
    )
    assert result.clips_in_range
    assert result.shot_alignment == []
    assert result.optimization_hints == []
