"""compose 边界切片与 transform 导出辅助测试。"""

from core.edit.compose import compose_timeline_plan
from core.edit.timeline import compile_timeline_from_shots
from core.edit.transform_interp import (
    build_scaled_video_filter,
    clip_has_animated_transform,
    collect_timeline_boundaries,
)
from core.models.entities import (
    EditClip,
    EditClipKeyframe,
    EditClipTransform,
    VideoStyleMode,
)
from tests.support.timeline_store_fixture import timeline_store


def test_collect_timeline_boundaries_includes_keyframes(timeline_store):
    script_id = timeline_store._test_script_id  # type: ignore[attr-defined]
    plan = timeline_store.get_video_plan_for_script(script_id)
    assert plan
    timeline = compile_timeline_from_shots(
        timeline_store,
        script_id=script_id,
        plan=plan,
    )
    clip = timeline.video_layers[0].clips[0]
    clip.transform = EditClipTransform(
        keyframes=[
            EditClipKeyframe(time_ms=500, opacity=0.0),
            EditClipKeyframe(time_ms=2500, opacity=1.0),
        ]
    )
    bounds = collect_timeline_boundaries(timeline)
    assert clip.start_ms + 500 in bounds
    assert clip.start_ms + 2500 in bounds


def test_compose_extra_slices_for_keyframes(timeline_store):
    script_id = timeline_store._test_script_id  # type: ignore[attr-defined]
    plan = timeline_store.get_video_plan_for_script(script_id)
    assert plan
    timeline = compile_timeline_from_shots(
        timeline_store,
        script_id=script_id,
        plan=plan,
    )
    clip = timeline.video_layers[0].clips[0]
    clip.transform = EditClipTransform(
        keyframes=[
            EditClipKeyframe(time_ms=1000, width=0.5),
            EditClipKeyframe(time_ms=2000, width=1.0),
        ]
    )
    plan_data = compose_timeline_plan(
        timeline_store, timeline, style_mode=VideoStyleMode.STORYBOOK
    )
    slices = plan_data["composite_slices"]
    widths = [
        layer["transform"]["width"]
        for slc in slices
        for layer in slc.get("layers", [])
        if layer.get("clip_id") == clip.id
    ]
    assert len(widths) >= 2
    assert min(widths) < max(widths)


def test_clip_has_animated_transform():
    clip = EditClip(
        id="c1",
        track="video",
        start_ms=0,
        end_ms=1000,
        transform=EditClipTransform(),
    )
    assert clip_has_animated_transform(clip) is False
    clip2 = EditClip(
        id="c2",
        track="video",
        start_ms=0,
        end_ms=1000,
        transform=EditClipTransform(keyframes=[EditClipKeyframe(time_ms=0)]),
    )
    assert clip_has_animated_transform(clip2) is True


def test_build_scaled_video_filter_rotation_and_opacity():
    from core.edit.transform_interp import ResolvedTransform

    vf = build_scaled_video_filter(
        ResolvedTransform(0.5, 0.5, 1.0, 1.0, 0.5, 45.0, 1.0),
        canvas_width=1920,
        canvas_height=1080,
    )
    assert "rotate=" in vf
    assert "colorchannelmixer=aa=0.5000" in vf
