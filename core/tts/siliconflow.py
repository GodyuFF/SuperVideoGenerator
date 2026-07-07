"""SiliconFlow TTS 合成。"""

from __future__ import annotations

import logging

import httpx
from edge_tts import SubMaker

from core.tts.duration import get_audio_duration
from core.tts.silent import ensure_file_path_exists
from core.tts.subtitle import ensure_legacy_submaker_fields, populate_legacy_submaker_with_full_text
from core.tts.text import split_string_by_punctuations

logger = logging.getLogger("core.tts.siliconflow")


def synthesize_siliconflow_tts(
    text: str,
    model: str,
    voice: str,
    voice_rate: float,
    voice_file: str,
    *,
    api_key: str,
    voice_volume: float = 1.0,
) -> SubMaker | None:
    text = text.strip()
    if not text or not api_key:
        return None

    gain = max(-10, min(10, voice_volume - 1.0))
    url = "https://api.siliconflow.cn/v1/audio/speech"
    payload = {
        "model": model,
        "input": text,
        "voice": voice,
        "response_format": "mp3",
        "sample_rate": 32000,
        "stream": False,
        "speed": voice_rate,
        "gain": gain,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    for i in range(3):
        try:
            logger.info("siliconflow tts start model=%s try=%s", model, i + 1)
            ensure_file_path_exists(voice_file)
            with httpx.Client(timeout=120.0) as client:
                response = client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                with open(voice_file, "wb") as f:
                    f.write(response.content)
            duration = get_audio_duration(voice_file)
            if duration <= 0:
                continue
            sub_maker = ensure_legacy_submaker_fields(SubMaker())
            return populate_legacy_submaker_with_full_text(
                sub_maker=sub_maker,
                text=text,
                audio_duration_seconds=duration,
            )
        except Exception as e:
            logger.error("siliconflow tts failed: %s", e)
    return None
