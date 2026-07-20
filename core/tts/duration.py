"""音频时长读取。"""

from __future__ import annotations

import logging
import re
import subprocess
import wave
from pathlib import Path

from edge_tts import SubMaker

logger = logging.getLogger("core.tts.duration")

_FFMPEG_DURATION_RE = re.compile(
    r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
_ffmpeg_missing_logged = False


def _get_audio_duration_from_submaker(sub_maker: SubMaker) -> float:
    if hasattr(sub_maker, "cues") and sub_maker.cues:
        return sub_maker.cues[-1].end.total_seconds()
    legacy_offsets = getattr(sub_maker, "offset", [])
    if not legacy_offsets:
        return 0.0
    return legacy_offsets[-1][1] / 10000000


def _duration_from_wav(path: Path) -> float:
    """使用标准库读取 WAV 时长，无需 FFmpeg。"""
    try:
        with wave.open(str(path), "rb") as handle:
            frames = handle.getnframes()
            rate = handle.getframerate()
            if rate <= 0:
                return 0.0
            return frames / float(rate)
    except (wave.Error, OSError) as exc:
        logger.debug("wave duration probe failed for %s: %s", path, exc)
        return 0.0


def _duration_from_ffmpeg_stderr(path: Path, ffmpeg: str) -> float:
    """通过 ffmpeg -i  stderr 解析时长（不依赖 ffprobe / pydub）。"""
    try:
        proc = subprocess.run(
            [ffmpeg, "-hide_banner", "-i", str(path)],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.debug("ffmpeg duration probe failed for %s: %s", path, exc)
        return 0.0
    text = f"{proc.stderr or ''}\n{proc.stdout or ''}"
    match = _FFMPEG_DURATION_RE.search(text)
    if not match:
        return 0.0
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def _duration_from_pydub(path: Path, ffmpeg: str) -> float:
    """使用 pydub 读取音频时长。"""
    try:
        from pydub import AudioSegment

        from core.tts.ffmpeg_util import configure_pydub_ffmpeg

        configure_pydub_ffmpeg(AudioSegment)
        segment = AudioSegment.from_file(str(path))
        return len(segment) / 1000.0
    except Exception as exc:
        logger.debug("pydub duration probe failed for %s (ffmpeg=%s): %s", path, ffmpeg, exc)
        return 0.0


def _log_ffmpeg_missing_once(ffmpeg: str) -> None:
    global _ffmpeg_missing_logged
    if _ffmpeg_missing_logged:
        return
    _ffmpeg_missing_logged = True
    from core.tts.ffmpeg_util import ffmpeg_missing_message

    logger.warning("%s", ffmpeg_missing_message(ffmpeg))


def _get_audio_duration_from_file(audio_file: str | Path) -> float:
    path = Path(audio_file)
    if not path.is_file():
        logger.debug("audio file does not exist: %s", path)
        return 0.0

    if path.suffix.lower() == ".wav":
        wav_seconds = _duration_from_wav(path)
        if wav_seconds > 0:
            return wav_seconds

    from core.tts.ffmpeg_util import is_ffmpeg_available, resolve_ffmpeg_binary

    ffmpeg = resolve_ffmpeg_binary()
    if not is_ffmpeg_available(ffmpeg):
        _log_ffmpeg_missing_once(ffmpeg)
        return 0.0

    seconds = _duration_from_pydub(path, ffmpeg)
    if seconds > 0:
        return seconds

    seconds = _duration_from_ffmpeg_stderr(path, ffmpeg)
    if seconds > 0:
        return seconds

    logger.debug("unable to determine audio duration for %s", path)
    return 0.0


def get_audio_duration(target: SubMaker | str | Path) -> float:
    """读取 SubMaker 或本地音频文件的时长（秒）。"""
    if isinstance(target, SubMaker):
        return _get_audio_duration_from_submaker(target)
    if isinstance(target, (str, Path)):
        return _get_audio_duration_from_file(target)
    logger.error("invalid target type: %s", type(target))
    return 0.0


def duration_ms_from_target(target: SubMaker | str | Path) -> int:
    """读取时长并转为毫秒。"""
    seconds = get_audio_duration(target)
    return max(int(seconds * 1000), 0)
