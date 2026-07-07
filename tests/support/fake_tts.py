"""测试用 TTS 假实现（仅 tests/ 使用）。"""

from __future__ import annotations

from pathlib import Path

from edge_tts import SubMaker

from core.tts.subtitle import populate_legacy_submaker_with_full_text


def write_minimal_mp3(path: Path) -> None:
    """写入极短静音 mp3 占位（非完整 MP3 帧，但满足落盘路径检测）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x00" * 128)


def fake_submaker_for_text(text: str, duration_seconds: float = 2.0) -> SubMaker:
    sub_maker = SubMaker()
    return populate_legacy_submaker_with_full_text(
        sub_maker=sub_maker,
        text=text,
        audio_duration_seconds=duration_seconds,
    )
