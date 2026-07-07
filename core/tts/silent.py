"""无配音静音轨生成。"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import unicodedata

from edge_tts import SubMaker

from core.tts.ffmpeg_util import resolve_ffmpeg_binary
from core.tts.subtitle import populate_legacy_submaker_with_full_text
from core.tts.text import split_string_by_punctuations

logger = logging.getLogger("core.tts.silent")


def ensure_file_path_exists(file_path: str) -> None:
    dir_path = os.path.dirname(file_path)
    if dir_path:
        os.makedirs(dir_path, exist_ok=True)


def estimate_no_voice_duration(text: str) -> float:
    normalized_text = (text or "").strip()
    if not normalized_text:
        return 3.0

    cjk_chars = len(re.findall(r"[\u4e00-\u9fff]", normalized_text))
    words = len(re.findall(r"[A-Za-z0-9]+", normalized_text))
    ascii_word_chars = sum(len(word) for word in re.findall(r"[A-Za-z0-9]+", normalized_text))
    other_text_chars = 0
    for char in normalized_text:
        category = unicodedata.category(char)
        if category.startswith(("L", "N")):
            other_text_chars += 1
    other_text_chars = max(other_text_chars - cjk_chars - ascii_word_chars, 0)
    sentence_count = max(len(split_string_by_punctuations(normalized_text)), 1)

    cjk_duration = cjk_chars / 4.2
    word_duration = words / 2.7
    other_text_duration = other_text_chars / 4.0
    pause_duration = max(sentence_count - 1, 0) * 0.35
    return max(3.0, cjk_duration + word_duration + other_text_duration + pause_duration)


def generate_silent_audio(duration_seconds: float, output_file: str) -> bool:
    ensure_file_path_exists(output_file)
    duration_seconds = max(float(duration_seconds or 0), 0.1)
    ffmpeg_binary = resolve_ffmpeg_binary()
    command = [
        ffmpeg_binary,
        "-y",
        "-f",
        "lavfi",
        "-i",
        "anullsrc=r=44100:cl=mono",
        "-t",
        f"{duration_seconds:.3f}",
        "-codec:a",
        "libmp3lame",
        "-q:a",
        "4",
        output_file,
    ]
    logger.info("generating silent audio, duration=%.2fs", duration_seconds)
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        logger.error(
            "failed to generate silent audio: %s",
            (result.stderr or result.stdout or "").strip(),
        )
        return False
    if not os.path.exists(output_file) or os.path.getsize(output_file) <= 0:
        logger.error("silent audio output missing or empty: %s", output_file)
        return False
    return True


def synthesize_no_voice(text: str, voice_file: str) -> SubMaker | None:
    duration_seconds = estimate_no_voice_duration(text)
    if not generate_silent_audio(duration_seconds, voice_file):
        return None
    sub_maker = SubMaker()
    return populate_legacy_submaker_with_full_text(
        sub_maker=sub_maker,
        text=text,
        audio_duration_seconds=duration_seconds,
    )
