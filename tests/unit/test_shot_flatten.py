"""镜内多轨结构 ↔ EditTimeline 转换层（core.edit.shot_flatten）单元测试。

验证：投影正确性、多镜偏移累加、多图层归并、往返一致（Shot→Timeline→Shot）、
有效时长计算、以及「无降级」行为（缺 media 只透传空引用）。
"""

from core.edit.shot_flatten import (
    META_AUDIO_KIND,
    META_SHOT_OFFSET,
    META_TRACK_KEY,
    apply_timeline_edits_to_shots,
    compile_timeline_from_shots,
    effective_shot_duration_ms,
    shot_offsets,
    shot_to_audio_clips,
    shot_to_subtitle_clips,
    shot_to_video_layers,
)
from core.models.entities import (
    EditClip,
    EditClipSourceRefs,
    EditClipTransform,
    EditTimeline,
    Shot,
    ShotAudioClip,
    ShotAudioTrack,
    ShotSubtitle,
    ShotVideoClip,
    ShotVideoTrack,
    ShotSubShot,
    ShotSubShotImage,
)


def _make_shot(order: int, duration_ms: int, *, with_overlay: bool = False) -> Shot:
    """构造一个含视频/音频/字幕多轨的分镜，时长与内容终点对齐。"""
    video_tracks = [
        ShotVideoTrack(
            id=f"vt{order}_main",
            name="主画面",
            z_index=0,
            clips=[
                ShotVideoClip(
                    id=f"vc{order}_0",
                    start_ms=0,
                    end_ms=duration_ms,
                    source_sub_shot_id=f"vis{order}",
                    media_id=f"media_vid_{order}",
                    source_kind="video",
                    camera_motion="ken_burns_in",
                    transform=EditClipTransform(x=0.5, y=0.5, width=1.0, height=1.0),
                    edit_description="主画面片段",
                )
            ],
        )
    ]
    if with_overlay:
        video_tracks.append(
            ShotVideoTrack(
                id=f"vt{order}_ov",
                name="叠加层 1",
                z_index=1,
                clips=[
                    ShotVideoClip(
                        id=f"vc{order}_ov",
                        start_ms=500,
                        end_ms=duration_ms,
                        media_id=f"media_ov_{order}",
                        source_kind="still",
                        camera_motion="static",
                    )
                ],
            )
        )
    return Shot(
        id=f"shot_{order}",
        order=order,
        duration_ms=duration_ms,
        title=f"镜{order}",
        sub_shots=[
            ShotSubShot(
                id=f"vis{order}",
                start_ms=0,
                end_ms=duration_ms,
                description="一个画面",
                element_refs={"character": [f"char{order}"]},
                camera_motion="ken_burns_in",
                image=ShotSubShotImage(kind="video", frame_asset_id=f"frame{order}"),
            )
        ],
        video_tracks=video_tracks,
        audio_tracks=[
            ShotAudioTrack(
                id=f"at{order}_voice",
                name="角色音",
                kind="voice",
                clips=[
                    ShotAudioClip(
                        id=f"ac{order}_0",
                        start_ms=0,
                        end_ms=duration_ms,
                        media_id=f"media_tts_{order}",
                        text=f"旁白{order}",
                        character_ref=f"char{order}",
                        voice="zh-CN-XiaoxiaoNeural",
                        volume=1.0,
                    )
                ],
            )
        ],
        subtitles=[
            ShotSubtitle(
                id=f"sub{order}_0", text=f"字幕{order}", start_ms=0, end_ms=duration_ms
            )
        ],
    )


def test_effective_shot_duration_uses_max_end() -> None:
    """有效时长取 duration_ms 与镜内片段最大终点的较大值。"""
    shot = Shot(id="s", order=0, duration_ms=2000)
    shot.video_tracks = [
        ShotVideoTrack(
            id="vt",
            clips=[ShotVideoClip(id="c", start_ms=0, end_ms=5000)],
        )
    ]
    assert effective_shot_duration_ms(shot) == 5000


def test_shot_offsets_accumulate_in_order() -> None:
    """分镜偏移按 order 顺序累加有效时长。"""
    shots = [_make_shot(1, 4000), _make_shot(0, 3000)]
    offsets = shot_offsets(shots)
    assert offsets["shot_0"] == 0
    assert offsets["shot_1"] == 3000


def test_compile_single_shot_projection() -> None:
    """单镜投影出正确的视频/音频/字幕轨与总时长。"""
    timeline = compile_timeline_from_shots(
        [_make_shot(0, 4000)], script_id="script_x"
    )
    assert timeline.duration_ms == 4000
    assert len(timeline.video_layers) == 1
    main = timeline.video_layers[0]
    assert main.z_index == 0
    assert len(main.clips) == 1
    clip = main.clips[0]
    assert clip.track == "video"
    assert clip.start_ms == 0 and clip.end_ms == 4000
    assert clip.asset_ref == "media_vid_0"
    assert clip.source_refs.shot_id == "shot_0"
    assert len(timeline.tracks["audio"]) == 1
    assert timeline.tracks["audio"][0].label == "旁白0"
    assert len(timeline.tracks["subtitle"]) == 1


def test_compile_multi_shot_absolute_time() -> None:
    """多镜投影后 clip 采用累加后的全局绝对时间。"""
    timeline = compile_timeline_from_shots(
        [_make_shot(0, 3000), _make_shot(1, 4000)], script_id="s"
    )
    assert timeline.duration_ms == 7000
    audio = timeline.tracks["audio"]
    assert len(audio) == 2
    assert audio[0].start_ms == 0 and audio[0].end_ms == 3000
    assert audio[1].start_ms == 3000 and audio[1].end_ms == 7000


def test_compile_multi_layer_merge_across_shots() -> None:
    """多镜的同 z_index 视频轨归并为同一 EditVideoLayer。"""
    timeline = compile_timeline_from_shots(
        [
            _make_shot(0, 3000, with_overlay=True),
            _make_shot(1, 3000, with_overlay=True),
        ],
        script_id="s",
    )
    assert len(timeline.video_layers) == 2
    z0, z1 = timeline.video_layers
    assert z0.z_index == 0 and len(z0.clips) == 2
    assert z1.z_index == 1 and len(z1.clips) == 2
    # 叠加层片段相对镜起点 500ms，累加到第二镜后为 3500ms
    assert z1.clips[1].start_ms == 3500


def test_missing_media_no_fallback() -> None:
    """缺 media 的画面片段只透传空引用，不注入占位素材（无降级）。"""
    shot = Shot(
        id="shot_0",
        order=0,
        duration_ms=2000,
        video_tracks=[
            ShotVideoTrack(
                id="vt",
                z_index=0,
                clips=[ShotVideoClip(id="c", start_ms=0, end_ms=2000, media_id="")],
            )
        ],
    )
    timeline = compile_timeline_from_shots([shot], script_id="s")
    assert timeline.video_layers[0].clips[0].asset_ref is None


def test_round_trip_shots_timeline_shots() -> None:
    """Shot → Timeline → Shot 往返，镜内轨道数据保持一致。"""
    original = [
        _make_shot(0, 3000, with_overlay=True),
        _make_shot(1, 4000),
    ]
    timeline = compile_timeline_from_shots(original, script_id="s")
    restored = apply_timeline_edits_to_shots(original, timeline)

    assert [s.id for s in restored] == [s.id for s in original]
    for orig, back in zip(original, restored):
        assert back.duration_ms == orig.duration_ms
        # 视频轨：数量、z、clip 相对时间、media、source_kind 一致
        assert len(back.video_tracks) == len(orig.video_tracks)
        for ot, bt in zip(
            sorted(orig.video_tracks, key=lambda t: t.z_index),
            sorted(back.video_tracks, key=lambda t: t.z_index),
        ):
            assert bt.z_index == ot.z_index
            assert len(bt.clips) == len(ot.clips)
            for oc, bc in zip(ot.clips, bt.clips):
                assert bc.id == oc.id
                assert bc.start_ms == oc.start_ms
                assert bc.end_ms == oc.end_ms
                assert bc.media_id == oc.media_id
                assert bc.source_kind == oc.source_kind
                assert bc.camera_motion == oc.camera_motion
        # 音频轨
        assert len(back.audio_tracks) == len(orig.audio_tracks)
        for oa, ba in zip(orig.audio_tracks, back.audio_tracks):
            assert ba.kind == oa.kind
            for oc, bc in zip(oa.clips, ba.clips):
                assert bc.id == oc.id
                assert bc.start_ms == oc.start_ms
                assert bc.end_ms == oc.end_ms
                assert bc.media_id == oc.media_id
                assert bc.text == oc.text
                assert bc.voice == oc.voice
                assert bc.character_ref == oc.character_ref
        # 字幕
        assert len(back.subtitles) == len(orig.subtitles)
        for os_, bs in zip(orig.subtitles, back.subtitles):
            assert bs.id == os_.id
            assert bs.text == os_.text
            assert bs.start_ms == os_.start_ms
            assert bs.end_ms == os_.end_ms


def test_round_trip_after_user_edit_shifts_relative_time() -> None:
    """模拟 OpenCut 手改：延长首镜片段后回写，相对时间换算正确。"""
    original = [_make_shot(0, 3000), _make_shot(1, 3000)]
    timeline = compile_timeline_from_shots(original, script_id="s")
    # 手动把第二镜的音频 clip 起点后移 200ms（保持其 shot_offset 锚点不变）
    audio_clips = timeline.tracks["audio"]
    second = audio_clips[1]
    second.start_ms += 200
    restored = apply_timeline_edits_to_shots(original, timeline)
    # 第二镜偏移 3000，手改后绝对 3200 → 相对 200
    back_audio = restored[1].audio_tracks[0].clips[0]
    assert back_audio.start_ms == 200


def test_opencut_placeholder_label_preserves_voice_text_and_media() -> None:
    """OpenCut 用 clip id 占位 label 且清空 asset_ref 时，应保留镜内配音文案与 media。"""
    clip_id = "sac_199a0d6fbe6f"
    original = [
        _make_shot(0, 3000).model_copy(
            update={
                "id": "shot_a",
                "audio_tracks": [
                    ShotAudioTrack(
                        id="at0_voice",
                        name="角色音",
                        kind="voice",
                        clips=[
                            ShotAudioClip(
                                id=clip_id,
                                start_ms=0,
                                end_ms=3000,
                                media_id="media_voice_ok",
                                text="旁白原文",
                                character_ref="char_1",
                                voice="zh-CN-XiaoxiaoNeural",
                            )
                        ],
                    )
                ],
            }
        )
    ]
    timeline = EditTimeline(
        script_id="s",
        tracks={
            "audio": [
                EditClip(
                    id=clip_id,
                    track="audio",
                    start_ms=0,
                    end_ms=3000,
                    label=clip_id,
                    asset_ref="",
                    source_refs=EditClipSourceRefs(shot_id="shot_a"),
                    metadata={
                        META_SHOT_OFFSET: 0,
                        META_AUDIO_KIND: "voice",
                        META_TRACK_KEY: "at0_voice",
                        "classic": {"mediaId": "media_stale"},
                    },
                )
            ]
        },
    )
    restored = apply_timeline_edits_to_shots(original, timeline)
    clip = restored[0].audio_tracks[0].clips[0]
    assert clip.text == "旁白原文"
    assert clip.media_id == "media_voice_ok"
    assert clip.character_ref == "char_1"


def test_shot_to_single_track_helpers() -> None:
    """便捷单轨转换方法可用。"""
    shot = _make_shot(0, 2000, with_overlay=True)
    layers = shot_to_video_layers(shot, offset_ms=1000)
    assert len(layers) == 2
    assert layers[0].clips[0].start_ms == 1000
    audio = shot_to_audio_clips(shot, offset_ms=1000)
    assert audio[0].start_ms == 1000
    subs = shot_to_subtitle_clips(shot, offset_ms=1000)
    assert subs[0].start_ms == 1000


def test_subtitle_character_color_round_trip() -> None:
    """字幕 character/color 经 Timeline 投影往返保留。"""
    shot = Shot(
        id="shot_sub",
        order=0,
        duration_ms=3000,
        subtitles=[
            ShotSubtitle(
                id="ssub_1",
                text="你好",
                start_ms=0,
                end_ms=1500,
                character="txt_hero",
                color="#FFCC00",
            ),
            ShotSubtitle(
                id="ssub_2",
                text="旁白",
                start_ms=1500,
                end_ms=3000,
            ),
        ],
    )
    timeline = compile_timeline_from_shots([shot], script_id="s")
    clips = timeline.tracks["subtitle"]
    assert clips[0].metadata.get("character") == "txt_hero"
    assert clips[0].metadata.get("color") == "#FFCC00"
    assert "character" not in clips[1].metadata
    restored = apply_timeline_edits_to_shots([shot], timeline)
    assert restored[0].subtitles[0].character == "txt_hero"
    assert restored[0].subtitles[0].color == "#FFCC00"
    assert restored[0].subtitles[1].character == ""
    assert restored[0].subtitles[1].color == ""
