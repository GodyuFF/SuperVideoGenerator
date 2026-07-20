"""镜时长与 voice span 单源计算测试。"""

from __future__ import annotations

from core.edit.shot_duration import (
    is_planned_tts_media,
    quantize_duration_ms,
    reconcile_shot_duration_from_media,
    resolve_display_shot_duration_ms,
    resolve_effective_shot_duration_ms,
    resolve_shot_voice_span_ms,
)
from core.models.entities import (
    MediaAsset,
    MediaAssetType,
    Shot,
    ShotAudioClip,
    ShotAudioTrack,
    ShotSubShot,
    ShotSubShotVideo,
    ShotVideoClip,
    ShotVideoTrack,
)
from tests.support.shot_fixtures import _store_with_shot


def test_is_planned_tts_media_by_flag() -> None:
    """used_planned_timeline 标记应识别为规划 TTS。"""
    store, script_id, shot = _store_with_shot()
    script = store.get_script(script_id)
    assert script
    audio = MediaAsset(
        project_id=script.project_id,
        script_id=script_id,
        type=MediaAssetType.AUDIO,
        name="配音",
        url="file:///tmp/planned.mp3",
        metadata={"shot_id": shot.id, "duration_ms": 10000, "used_planned_timeline": True},
    )
    store.add_media_asset(audio)
    assert is_planned_tts_media(store, audio.id) is True


def test_resolve_shot_voice_span_planned_uses_full_file_duration() -> None:
    """规划 TTS 的 voice span 应覆盖文件全长（0 → duration_ms）。"""
    store, script_id, shot = _store_with_shot()
    script = store.get_script(script_id)
    assert script
    audio = MediaAsset(
        project_id=script.project_id,
        script_id=script_id,
        type=MediaAssetType.AUDIO,
        name="配音",
        url="file:///tmp/planned.mp3",
        metadata={"shot_id": shot.id, "duration_ms": 10000, "used_planned_timeline": True},
    )
    store.add_media_asset(audio)
    tts_by_shot = {shot.id: audio.id}
    start, end = resolve_shot_voice_span_ms(store, shot, tts_by_shot)
    assert start == 0
    assert end == 10000


def test_resolve_display_shot_duration_timeline_requires_media() -> None:
    """无 media_id 的剪辑 clip 不应作为展示时长来源。"""
    shot = Shot(
        id="sh0",
        order=1,
        duration_ms=3000,
        video_tracks=[
            ShotVideoTrack(
                id="vt0",
                z_index=0,
                clips=[ShotVideoClip(id="vc0", start_ms=0, end_ms=4500)],
            )
        ],
        audio_tracks=[
            ShotAudioTrack(
                id="at0",
                kind="voice",
                clips=[ShotAudioClip(id="ac0", start_ms=0, end_ms=3200, text="旁白")],
            )
        ],
    )
    duration_ms, source = resolve_display_shot_duration_ms(shot)
    assert duration_ms == 3200
    assert source == "voice"


def test_resolve_display_shot_duration_prefers_timeline() -> None:
    """有镜内 source_kind=video 的 clip 时展示时长应取剪辑轴跨度。"""
    shot = Shot(
        id="sh1",
        order=1,
        duration_ms=3000,
        video_tracks=[
            ShotVideoTrack(
                id="vt0",
                z_index=0,
                clips=[
                    ShotVideoClip(
                        id="vc1",
                        start_ms=0,
                        end_ms=4500,
                        media_id="media_vid",
                        source_kind="video",
                    )
                ],
            )
        ],
    )
    duration_ms, source = resolve_display_shot_duration_ms(shot, tts_duration_ms=5000)
    assert duration_ms == 4500
    assert source == "timeline"


def test_resolve_display_shot_duration_still_clip_not_timeline() -> None:
    """静图 still 占位 clip 不应作为剪辑轴展示时长来源。"""
    shot = Shot(
        id="sh_still",
        order=1,
        duration_ms=3000,
        video_tracks=[
            ShotVideoTrack(
                id="vt0",
                z_index=0,
                clips=[
                    ShotVideoClip(
                        id="vc_still",
                        start_ms=0,
                        end_ms=4500,
                        media_id="media_img",
                        source_kind="still",
                    )
                ],
            )
        ],
        audio_tracks=[
            ShotAudioTrack(
                id="at0",
                kind="voice",
                clips=[ShotAudioClip(id="ac0", start_ms=0, end_ms=3200, text="旁白")],
            )
        ],
    )
    duration_ms, source = resolve_display_shot_duration_ms(shot)
    assert duration_ms == 3200
    assert source == "voice"


def test_resolve_display_shot_duration_falls_back_to_voice() -> None:
    """无剪辑/视频时展示时长应取配音跨度。"""
    shot = Shot(
        id="sh2",
        order=1,
        duration_ms=3000,
        audio_tracks=[
            ShotAudioTrack(
                id="at0",
                kind="voice",
                clips=[
                    ShotAudioClip(
                        id="ac1",
                        start_ms=0,
                        end_ms=4200,
                        text="旁白",
                    )
                ],
            )
        ],
    )
    duration_ms, source = resolve_display_shot_duration_ms(shot)
    assert duration_ms == 4200
    assert source == "voice"


def test_resolve_display_shot_duration_video_before_voice() -> None:
    """子镜视频优先于配音。"""
    shot = Shot(
        id="sh3",
        order=1,
        duration_ms=3000,
        sub_shots=[
            ShotSubShot(
                id="ss1",
                start_ms=0,
                end_ms=3000,
                videos=[
                    ShotSubShotVideo(
                        id="sv1",
                        media_id="media_vid",
                        start_ms=0,
                        end_ms=3800,
                    )
                ],
            )
        ],
        audio_tracks=[
            ShotAudioTrack(
                id="at0",
                kind="voice",
                clips=[ShotAudioClip(id="ac1", start_ms=0, end_ms=5000, text="旁白")],
            )
        ],
    )
    duration_ms, source = resolve_display_shot_duration_ms(shot, tts_duration_ms=5000)
    assert duration_ms == 3800
    assert source == "video"


def test_quantize_duration_ms_ceil_to_second() -> None:
    """镜时长应对齐到整秒（向上取整）。"""
    assert quantize_duration_ms(0) == 1000
    assert quantize_duration_ms(8000) == 8000
    assert quantize_duration_ms(8001) == 9000
    assert quantize_duration_ms(8400) == 9000


def test_reconcile_shot_duration_from_voice_media() -> None:
    """绑定配音后应按音频实测时长回填幕终点与镜时长（整秒）。"""
    store, script_id, shot = _store_with_shot()
    script = store.get_script(script_id)
    assert script
    audio = MediaAsset(
        project_id=script.project_id,
        script_id=script_id,
        type=MediaAssetType.AUDIO,
        name="配音",
        url="file:///tmp/voice.mp3",
        metadata={"shot_id": shot.id, "duration_ms": 8400},
    )
    store.add_media_asset(audio)
    shot = shot.model_copy(
        update={
            "duration_ms": 3000,
            "audio_tracks": [
                ShotAudioTrack(
                    id="at0",
                    kind="voice",
                    clips=[
                        ShotAudioClip(
                            id="ac0",
                            start_ms=0,
                            end_ms=3000,
                            text="旁白",
                            media_id=audio.id,
                        )
                    ],
                )
            ],
        }
    )
    reconciled = reconcile_shot_duration_from_media(store, shot)
    voice = reconciled.audio_tracks[0].clips[0]
    assert voice.end_ms == 9000
    assert reconciled.duration_ms == 9000
    assert resolve_effective_shot_duration_ms(store, reconciled) == 9000
