"""transform_interp 关键帧插值测试。"""

from core.edit.ken_burns_filter import clip_has_ken_burns
from core.edit.transform_interp import (
    ResolvedTransform,
    build_scaled_video_filter,
    collect_timeline_boundaries,
    interpolate_transform,
    snap_even_dim,
    timeline_needs_composite_export,
    transform_to_overlay_pixels,
)
from core.models.entities import (
    EditClip,
    EditClipKeyframe,
    EditClipMotionDetail,
    EditClipTransform,
    EditTimeline,
    EditVideoLayer,
)


def test_interpolate_transform_defaults_fullscreen():
    clip = EditClip(track="video", start_ms=0, end_ms=5000)
    resolved = interpolate_transform(clip, 1000)
    assert resolved.x == 0.5
    assert resolved.y == 0.5
    assert resolved.width == 1.0
    assert resolved.height == 1.0
    assert resolved.opacity == 1.0


def test_interpolate_transform_keyframes():
    clip = EditClip(
        track="video",
        start_ms=0,
        end_ms=5000,
        transform=EditClipTransform(
            x=0.5,
            y=0.5,
            width=1.0,
            height=1.0,
            keyframes=[
                EditClipKeyframe(time_ms=0, x=0.2, y=0.2, width=0.5, height=0.5),
                EditClipKeyframe(time_ms=2000, x=0.8, y=0.8, width=0.3, height=0.3),
            ],
        ),
    )
    at_start = interpolate_transform(clip, 0)
    assert at_start.x == 0.2
    assert at_start.width == 0.5

    mid = interpolate_transform(clip, 1000)
    assert 0.4 < mid.x < 0.6
    assert 0.35 < mid.width < 0.45

    at_end = interpolate_transform(clip, 2000)
    assert at_end.x == 0.8
    assert at_end.width == 0.3


def test_transform_to_overlay_pixels():
    from core.edit.transform_interp import ResolvedTransform

    pixels = transform_to_overlay_pixels(
        ResolvedTransform(x=0.5, y=0.5, width=0.5, height=0.5, opacity=1.0, rotation=0.0),
        canvas_width=1920,
        canvas_height=1080,
    )
    assert pixels["w"] == 960
    assert pixels["h"] == 540
    assert pixels["x"] == 480
    assert pixels["y"] == 270


def test_clip_has_ken_burns_detects_motion():
    static = EditClip(track="video", start_ms=0, end_ms=3000, motion="static")
    assert clip_has_ken_burns(static) is False
    kb = EditClip(track="video", start_ms=0, end_ms=3000, motion="ken_burns_in")
    assert clip_has_ken_burns(kb) is True


def test_timeline_needs_composite_for_ken_burns():
    timeline = EditTimeline(
        script_id="scr",
        duration_ms=5000,
        video_layers=[
            EditVideoLayer(
                id="vly",
                clips=[
                    EditClip(
                        track="video",
                        start_ms=0,
                        end_ms=5000,
                        motion="ken_burns_in",
                        motion_detail=EditClipMotionDetail(
                            type="ken_burns_in",
                            scale_from=1.0,
                            scale_to=1.2,
                        ),
                    )
                ],
            )
        ],
    )
    assert timeline_needs_composite_export(timeline) is True


def test_collect_timeline_boundaries_includes_ken_burns_steps():
    timeline = EditTimeline(
        script_id="scr",
        duration_ms=5000,
        video_layers=[
            EditVideoLayer(
                id="vly",
                clips=[
                    EditClip(
                        track="video",
                        start_ms=0,
                        end_ms=2000,
                        motion="ken_burns_in",
                    )
                ],
            )
        ],
    )
    bounds = collect_timeline_boundaries(timeline)
    assert 250 in bounds
    assert 500 in bounds


def test_snap_even_dim_rounds_odd_up():
    assert snap_even_dim(1215) == 1216
    assert snap_even_dim(1920) == 1920
    assert snap_even_dim(1) == 2


def test_overlay_pixels_even_for_ken_burns_scale():
    """scale=1.125 时 int 截断会产生奇数 h，须规范为偶数避免 FFmpeg pad 失败。"""
    pixels = transform_to_overlay_pixels(
        ResolvedTransform(x=0.5, y=0.5, width=1.0, height=1.0, opacity=1.0, rotation=0.0, scale=1.125),
        canvas_width=1920,
        canvas_height=1080,
    )
    assert pixels["w"] % 2 == 0
    assert pixels["h"] % 2 == 0
    assert pixels["w"] == 2160
    assert pixels["h"] == 1216


def test_build_scaled_video_filter_force_divisible_by_2():
    vf = build_scaled_video_filter(
        ResolvedTransform(0.5, 0.5, 1.0, 1.0, 1.0, 0.0, 1.125),
        canvas_width=1920,
        canvas_height=1080,
    )
    assert "force_divisible_by=2" in vf
    assert "pad=2160:1216" in vf


def test_static_motion_ignores_motion_detail_scale():
    clip = EditClip(
        track="video",
        start_ms=0,
        end_ms=12000,
        motion="static",
        motion_detail=EditClipMotionDetail(
            type="ken_burns_in",
            scale_from=1.0,
            scale_to=1.15,
        ),
    )
    resolved = interpolate_transform(clip, 6000)
    assert resolved.scale == 1.0
