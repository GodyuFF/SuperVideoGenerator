"""ffmpeg_util 单元测试。"""

from pathlib import Path
from unittest.mock import patch

from core.tts.ffmpeg_util import (
    ffmpeg_missing_message,
    is_ffmpeg_available,
    is_ffmpeg_bundled,
    resolve_ffmpeg_binary,
)


def test_is_ffmpeg_available_with_existing_file(tmp_path):
    ffmpeg = tmp_path / "ffmpeg.exe"
    ffmpeg.write_bytes(b"")
    assert is_ffmpeg_available(str(ffmpeg)) is True


def test_is_ffmpeg_available_with_which():
    with patch("core.tts.ffmpeg_util.shutil.which", return_value="/usr/bin/ffmpeg"):
        assert is_ffmpeg_available("ffmpeg") is True


def test_ffmpeg_missing_message_includes_path():
    msg = ffmpeg_missing_message("/missing/ffmpeg.exe")
    assert "未找到 FFmpeg" in msg
    assert "/missing/ffmpeg.exe" in msg
    assert "SVG_FFMPEG_PATH" in msg


def test_resolve_ffmpeg_binary_env_override(monkeypatch):
    monkeypatch.setenv("SVG_FFMPEG_PATH", "C:/custom/ffmpeg.exe")
    assert resolve_ffmpeg_binary() == "C:/custom/ffmpeg.exe"


def test_resolve_ffmpeg_binary_falls_back_to_bundled(monkeypatch):
    monkeypatch.delenv("SVG_FFMPEG_PATH", raising=False)
    with patch("core.tts.ffmpeg_util.shutil.which", return_value=None), patch(
        "core.tts.ffmpeg_util._bundled_ffmpeg_exe", return_value="/bundled/ffmpeg.exe"
    ):
        assert resolve_ffmpeg_binary() == "/bundled/ffmpeg.exe"


def test_is_ffmpeg_bundled_when_using_imageio_path(monkeypatch):
    monkeypatch.delenv("SVG_FFMPEG_PATH", raising=False)
    with patch("core.tts.ffmpeg_util._bundled_ffmpeg_exe", return_value="/bundled/ffmpeg.exe"), patch(
        "core.tts.ffmpeg_util.shutil.which", return_value=None
    ), patch("core.tts.ffmpeg_util._windows_ffmpeg_candidates", return_value=[]):
        assert resolve_ffmpeg_binary() == "/bundled/ffmpeg.exe"
        assert is_ffmpeg_bundled() is True
