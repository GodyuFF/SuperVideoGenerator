"""音频时长探测单元测试。"""

import wave
from pathlib import Path
from unittest.mock import patch

import pytest

from core.tts.duration import (
    _duration_from_ffmpeg_stderr,
    _duration_from_wav,
    duration_ms_from_target,
)


def test_duration_from_wav(tmp_path: Path) -> None:
    """WAV 文件应无需 FFmpeg 即可探测时长。"""
    wav_path = tmp_path / "clip.wav"
    with wave.open(str(wav_path), "w") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(1000)
        handle.writeframes(b"\x00\x00" * 2000)
    assert _duration_from_wav(wav_path) == pytest.approx(2.0, abs=0.05)
    assert duration_ms_from_target(wav_path) >= 1900


def test_duration_from_ffmpeg_stderr_parses_duration() -> None:
    """ffmpeg -i 输出应能解析出时长。"""
    fake_stderr = (
        "Input #0, mp3, from 'test.mp3':\n"
        "  Duration: 00:00:05.12, start: 0.000000, bitrate: 128 kb/s\n"
    )

    class _Result:
        stderr = fake_stderr
        stdout = ""

    with patch("core.tts.duration.subprocess.run", return_value=_Result()):
        seconds = _duration_from_ffmpeg_stderr(Path("test.mp3"), "ffmpeg.exe")
    assert seconds == pytest.approx(5.12, abs=0.01)


def test_duration_missing_file_returns_zero(tmp_path: Path) -> None:
    """文件不存在时返回 0，不抛异常。"""
    assert duration_ms_from_target(tmp_path / "missing.mp3") == 0


def test_duration_uses_metadata_fallback_path_when_ffmpeg_missing(tmp_path: Path) -> None:
    """FFmpeg 不可用时探测返回 0（调用方回退 metadata.duration_ms）。"""
    mp3_path = tmp_path / "tts.mp3"
    mp3_path.write_bytes(b"fake")
    with patch("core.tts.ffmpeg_util.is_ffmpeg_available", return_value=False):
        assert duration_ms_from_target(mp3_path) == 0
