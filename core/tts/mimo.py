"""Xiaomi MiMo TTS 合成。"""

from __future__ import annotations

import base64
import io
import logging
import os

from edge_tts import SubMaker
from openai import OpenAI

from core.tts.ffmpeg_util import configure_pydub_ffmpeg
from core.tts.silent import ensure_file_path_exists
from core.tts.subtitle import ensure_legacy_submaker_fields, populate_legacy_submaker_with_full_text

logger = logging.getLogger("core.tts.mimo")

_MIMO_DEFAULT_BASE_URL = "https://api.xiaomimimo.com/v1"
_MIMO_DEFAULT_TTS_MODEL = "mimo-v2.5-tts"


def _parse_extension(path: str) -> str:
    ext = os.path.splitext(path)[1].lstrip(".").lower()
    return ext or "mp3"


def synthesize_mimo_tts(
    text: str,
    voice_name: str,
    voice_file: str,
    *,
    api_key: str,
    base_url: str = "",
    model_name: str = "",
    style_prompt: str = "请用自然、清晰、适合短视频旁白的语气朗读。",
) -> SubMaker | None:
    text = text.strip()
    if not text or not api_key:
        return None

    try:
        from pydub import AudioSegment
    except ImportError as e:
        logger.error("mimo tts missing pydub: %s", e)
        return None

    configure_pydub_ffmpeg(AudioSegment)
    resolved_base = (base_url or "").strip() or _MIMO_DEFAULT_BASE_URL
    resolved_model = (model_name or "").strip() or _MIMO_DEFAULT_TTS_MODEL

    for i in range(3):
        try:
            logger.info("mimo tts start voice=%s try=%s", voice_name, i + 1)
            ensure_file_path_exists(voice_file)
            client = OpenAI(api_key=api_key, base_url=resolved_base)
            completion = client.chat.completions.create(
                model=resolved_model,
                messages=[
                    {"role": "user", "content": style_prompt},
                    {"role": "assistant", "content": text},
                ],
                audio={"format": "wav", "voice": voice_name},
            )
            if not completion or not getattr(completion, "choices", None):
                raise ValueError("MiMo TTS returned empty response")
            message = completion.choices[0].message
            audio = getattr(message, "audio", None)
            audio_data = None
            if isinstance(audio, dict):
                audio_data = audio.get("data")
            elif audio is not None:
                audio_data = getattr(audio, "data", None)
            if not audio_data:
                raise ValueError("MiMo TTS returned empty audio data")
            audio_bytes = base64.b64decode(audio_data)
            audio_segment = AudioSegment.from_file(io.BytesIO(audio_bytes), format="wav")
            output_format = _parse_extension(voice_file)
            if output_format == "wav":
                with open(voice_file, "wb") as f:
                    f.write(audio_bytes)
            else:
                audio_segment.export(voice_file, format=output_format)
            duration = len(audio_segment) / 1000.0
            sub_maker = ensure_legacy_submaker_fields(SubMaker())
            return populate_legacy_submaker_with_full_text(
                sub_maker=sub_maker,
                text=text,
                audio_duration_seconds=duration,
            )
        except Exception as e:
            logger.error("mimo tts failed: %s", e)
    return None
