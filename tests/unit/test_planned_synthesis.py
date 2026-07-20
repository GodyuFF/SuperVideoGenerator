"""规划约束 TTS 合成单元测试（新模型：镜内 voice clip）。"""

from pathlib import Path

from core.models.entities import Shot, ShotAudioClip, ShotAudioTrack
from core.tts.engine import TtsRuntimeConfig
from core.tts.planned_synthesis import build_voice_segments_from_shot, synthesize_shot_with_plan
from core.llm.tools.tts.settings import TtsSettings
from tests.support.shot_fixtures import make_shot


def _shot_with_voice_segments() -> Shot:
    """构造含多段 voice clip 的镜头。"""
    return Shot(
        order=0,
        duration_ms=3000,
        audio_tracks=[
            ShotAudioTrack(
                kind="voice",
                name="角色音",
                clips=[
                    ShotAudioClip(start_ms=500, end_ms=2500, text="测试"),
                ],
            )
        ],
    )


def test_build_voice_segments_from_shot():
    """应从镜内 voice clip 提取语音段。"""
    segments = build_voice_segments_from_shot(_shot_with_voice_segments())
    assert len(segments) == 1
    assert segments[0]["target_ms"] == 2000


def test_synthesize_shot_with_plan_single_voice(tmp_path: Path):
    """单段 voice clip 应按规划合成并产出文件。"""
    settings = TtsSettings(enabled=True, provider="edge", default_voice="no-voice")
    runtime = TtsRuntimeConfig(settings=settings)
    output = tmp_path / "shot.mp3"
    shot = make_shot(order=0, duration_ms=3000, text="测试")
    result = synthesize_shot_with_plan(shot, output, runtime)
    assert result.used_planned_timeline is True
    assert output.is_file()
    assert result.duration_ms > 0
