"""镜内多轨结构校验（core.edit.shot_validate）单元测试。"""

from core.edit.shot_validate import (
    validate_shot_structure,
    validate_shot_voice_content,
    validate_shots_editable,
    validate_shots_render_ready,
    validate_shots_voice_content,
)
from core.models.entities import (
    Shot,
    ShotAudioClip,
    ShotAudioTrack,
    ShotSubtitle,
    ShotVideoClip,
    ShotVideoTrack,
    ShotSubShot,
)


def _valid_shot() -> Shot:
    """构造一个结构自洽、已绑 media 的分镜。"""
    return Shot(
        id="shot_ok",
        order=0,
        duration_ms=4000,
        sub_shots=[ShotSubShot(id="v", start_ms=0, end_ms=4000, description="画面")],
        video_tracks=[
            ShotVideoTrack(
                id="vt",
                z_index=0,
                clips=[
                    ShotVideoClip(id="c", start_ms=0, end_ms=4000, media_id="m_vid")
                ],
            )
        ],
        audio_tracks=[
            ShotAudioTrack(
                id="at",
                kind="voice",
                clips=[
                    ShotAudioClip(id="a", start_ms=0, end_ms=4000, media_id="m_tts")
                ],
            )
        ],
        subtitles=[ShotSubtitle(id="s", text="字幕", start_ms=0, end_ms=4000)],
    )


def test_valid_shot_passes() -> None:
    """自洽分镜无结构问题、渲染就绪。"""
    shot = _valid_shot()
    assert validate_shot_structure(shot) == []
    assert validate_shots_render_ready([shot]) == []


def test_long_duration_allowed() -> None:
    """分镜时长无硬上限：超过原 15s 仍可通过结构校验。"""
    shot = _valid_shot()
    shot.duration_ms = 18000
    shot.sub_shots[0].end_ms = 18000
    shot.video_tracks[0].clips[0].end_ms = 18000
    shot.audio_tracks[0].clips[0].end_ms = 18000
    shot.subtitles[0].end_ms = 18000
    assert validate_shot_structure(shot) == []


def test_empty_shot_flagged() -> None:
    """既无画面也无视频片段的空镜被报告。"""
    shot = Shot(id="empty", order=0, duration_ms=2000)
    issues = validate_shot_structure(shot)
    assert any("至少需要一个画面" in i for i in issues)


def test_same_track_overlap_flagged() -> None:
    """同一视频轨内片段重叠被报告。"""
    shot = Shot(
        id="ov",
        order=0,
        duration_ms=4000,
        video_tracks=[
            ShotVideoTrack(
                id="vt",
                z_index=0,
                clips=[
                    ShotVideoClip(id="c1", start_ms=0, end_ms=3000, media_id="m1"),
                    ShotVideoClip(id="c2", start_ms=2000, end_ms=4000, media_id="m2"),
                ],
            )
        ],
    )
    issues = validate_shot_structure(shot)
    assert any("重叠" in i for i in issues)


def test_clip_out_of_bounds_flagged() -> None:
    """片段超出镜内区间被报告。"""
    shot = Shot(
        id="oob",
        order=0,
        duration_ms=3000,
        video_tracks=[
            ShotVideoTrack(
                id="vt",
                z_index=0,
                clips=[ShotVideoClip(id="c", start_ms=0, end_ms=5000, media_id="m")],
            )
        ],
    )
    issues = validate_shot_structure(shot)
    assert any("超出镜内" in i for i in issues)


def test_render_ready_flags_missing_media_no_fallback() -> None:
    """缺 media 的视频/音频片段在渲染就绪校验中被显式列出（无降级）。"""
    shot = _valid_shot()
    shot.video_tracks[0].clips[0].media_id = ""
    shot.audio_tracks[0].clips[0].media_id = ""
    missing = validate_shots_render_ready([shot])
    assert len(missing) == 2
    assert any("缺少 media" in i for i in missing)


def test_validate_shots_editable_only_returns_problem_shots() -> None:
    """批量校验仅返回有问题的分镜。"""
    good = _valid_shot()
    bad = Shot(id="bad", order=1, duration_ms=0)
    result = validate_shots_editable([good, bad])
    assert "shot_ok" not in result
    assert "bad" in result


def test_validate_shots_voice_content_requires_voice_text() -> None:
    """有子镜但无 voice text 时校验失败。"""
    shot = Shot(
        id="no_voice",
        order=0,
        duration_ms=4000,
        sub_shots=[ShotSubShot(id="v", start_ms=0, end_ms=4000, description="画面")],
    )
    issues = validate_shot_voice_content(shot)
    assert issues
    assert any("voice" in i.lower() for i in issues)

    shot_with_voice = _valid_shot()
    shot_with_voice.audio_tracks[0].clips[0].text = "旁白"
    assert validate_shot_voice_content(shot_with_voice) == []
    assert validate_shots_voice_content([shot_with_voice]) == {}
