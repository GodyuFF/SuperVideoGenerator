from core.edit.sub_shot_produce import (
    clamp_image_timings_to_sub,
    coerce_produce_mode,
    expand_image_timing,
    infer_produce_mode,
    produce_mode_to_video_gen_mode,
    sync_produce_mode_from_video_gen_modes,
    validate_sub_shot_image_timings,
    video_gen_mode_to_produce_mode_hint,
)

from core.models.entities import ShotSubShot, ShotSubShotImage, ShotSubShotVideo





def test_expand_image_timing_unset_fills_sub_range():

    sub = ShotSubShot(start_ms=1000, end_ms=4000, description="d")

    img = ShotSubShotImage(start_ms=0, end_ms=0)

    s, e = expand_image_timing(img, sub)

    assert (s, e) == (1000, 4000)





def test_validate_image_timing_must_lie_inside_sub():

    sub = ShotSubShot(start_ms=0, end_ms=3000, description="d", images=[

        ShotSubShotImage(start_ms=0, end_ms=4000),

    ])

    issues = validate_sub_shot_image_timings(sub)

    assert any("end_ms" in x or "区间" in x for x in issues)


def test_clamp_image_timings_to_sub_shrinks_overflow():
    """子镜缩短后，越界画面时段应被钳进子镜区间。"""
    sub = ShotSubShot(
        start_ms=0,
        end_ms=4580,
        description="d",
        images=[ShotSubShotImage(start_ms=0, end_ms=8000)],
    )
    out = clamp_image_timings_to_sub(sub)
    assert out.images[0].start_ms == 0
    assert out.images[0].end_ms == 4580
    assert validate_sub_shot_image_timings(out) == []


def test_clamp_image_timings_outside_falls_back_to_full_sub():
    """画面完全落在子镜外时，回退为整段子镜区间。"""
    sub = ShotSubShot(
        start_ms=4580,
        end_ms=4581,
        description="d",
        images=[ShotSubShotImage(start_ms=8000, end_ms=15000)],
    )
    out = clamp_image_timings_to_sub(sub)
    assert out.images[0].start_ms == 4580
    assert out.images[0].end_ms == 4581
    assert validate_sub_shot_image_timings(out) == []


def test_clamp_image_timings_leaves_unset_alone():
    """未显式设置（0,0）的画面时段不被改写。"""
    sub = ShotSubShot(
        start_ms=0,
        end_ms=3000,
        description="d",
        images=[ShotSubShotImage(start_ms=0, end_ms=0)],
    )
    out = clamp_image_timings_to_sub(sub)
    assert out.images[0].start_ms == 0
    assert out.images[0].end_ms == 0
    assert out is sub





def test_infer_produce_mode_img2video_when_videos_present():

    sub = ShotSubShot(

        start_ms=0,

        end_ms=3000,

        description="跑过广场",

        videos=[ShotSubShotVideo(start_ms=0, end_ms=3000)],

    )

    assert infer_produce_mode(sub) == "img2video"





def test_infer_produce_mode_img2video_when_image_kind_video():

    sub = ShotSubShot(

        start_ms=0, end_ms=3000, description="d",

        images=[ShotSubShotImage(kind="video")],

    )

    assert infer_produce_mode(sub) == "img2video"





def test_coerce_legacy_produce_modes():

    assert coerce_produce_mode("still_edit") == "still"

    assert coerce_produce_mode("ai_video") == "img2video"

    assert coerce_produce_mode("hybrid") == "img2video"

    assert coerce_produce_mode("text2video") == "text2video"





def test_produce_mode_to_video_gen_mode():

    assert produce_mode_to_video_gen_mode("still") == "still"

    assert produce_mode_to_video_gen_mode("img2video") == "img2video"

    assert produce_mode_to_video_gen_mode("text2video") == "text2video"





def test_sync_produce_mode_from_video_gen_modes():

    assert sync_produce_mode_from_video_gen_modes(["still", "still"]) == "still"

    assert sync_produce_mode_from_video_gen_modes(["text2video"]) == "text2video"





def test_video_gen_mode_to_produce_mode_hint():

    assert video_gen_mode_to_produce_mode_hint("still") == "still"

    assert video_gen_mode_to_produce_mode_hint("img2video") == "img2video"


