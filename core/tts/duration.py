"""音频时长读取。"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from edge_tts import SubMaker

logger = logging.getLogger("core.tts.duration")


def _get_audio_duration_from_submaker(sub_maker: SubMaker) -> float:
    if hasattr(sub_maker, "cues") and sub_maker.cues:
        return sub_maker.cues[-1].end.total_seconds()
    legacy_offsets = getattr(sub_maker, "offset", [])
    if not legacy_offsets:
        return 0.0
    return legacy_offsets[-1][1] / 10000000


def _get_audio_duration_from_file(audio_file: str | Path) -> float:
    path = Path(audio_file)
    if not path.is_file():
        logger.error("audio file does not exist: %s", path)
        return 0.0
    try:
        from pydub import AudioSegment

        from core.tts.ffmpeg_util import configure_pydub_ffmpeg

        configure_pydub_ffmpeg(AudioSegment)
        segment = AudioSegment.from_file(str(path))
        return len(segment) / 1000.0
    except Exception as e:
        logger.error("failed to get audio duration from file: %s", e)
        return 0.0


def get_audio_duration(target: SubMaker | str | Path) -> float:
    if isinstance(target, SubMaker):
        return _get_audio_duration_from_submaker(target)
    if isinstance(target, (str, Path)):
        return _get_audio_duration_from_file(target)
    logger.error("invalid target type: %s", type(target))
    return 0.0


def duration_ms_from_target(target: SubMaker | str | Path) -> int:
    seconds = get_audio_duration(target)
    return max(int(seconds * 1000), 0)
