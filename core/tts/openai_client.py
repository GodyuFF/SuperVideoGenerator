"""OpenAI TTS API 合成。"""

from __future__ import annotations

import logging
from pathlib import Path

import httpx
from edge_tts import SubMaker

from core.tts.duration import get_audio_duration
from core.tts.silent import ensure_file_path_exists
from core.tts.subtitle import populate_legacy_submaker_with_full_text

logger = logging.getLogger("core.tts.openai_client")


def synthesize_openai_tts(
    text: str,
    voice_name: str,
    voice_rate: float,
    voice_file: str,
    *,
    api_key: str,
    model: str = "tts-1",
    base_url: str = "https://api.openai.com/v1",
    timeout_sec: float = 60.0,
) -> SubMaker | None:
    text = text.strip()
    if not text or not api_key:
        return None

    url = base_url.rstrip("/") + "/audio/speech"
    payload = {
        "model": model,
        "input": text,
        "voice": voice_name or "alloy",
        "response_format": "mp3",
        "speed": max(0.25, min(4.0, voice_rate)),
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    for i in range(3):
        try:
            logger.info("openai tts start model=%s try=%s", model, i + 1)
            ensure_file_path_exists(voice_file)
            with httpx.Client(timeout=timeout_sec) as client:
                resp = client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                Path(voice_file).write_bytes(resp.content)
            duration = get_audio_duration(voice_file)
            if duration <= 0:
                continue
            sub_maker = SubMaker()
            return populate_legacy_submaker_with_full_text(
                sub_maker=sub_maker,
                text=text,
                audio_duration_seconds=duration,
            )
        except Exception as e:
            logger.error("openai tts failed: %s", e)
    return None
