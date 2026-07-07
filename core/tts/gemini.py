"""Google Gemini TTS 合成。"""

from __future__ import annotations

import base64
import io
import logging

from edge_tts import SubMaker

from core.tts.ffmpeg_util import configure_pydub_ffmpeg
from core.tts.silent import ensure_file_path_exists
from core.tts.subtitle import populate_legacy_submaker_with_full_text

logger = logging.getLogger("core.tts.gemini")


def synthesize_gemini_tts(
    text: str,
    voice_name: str,
    voice_file: str,
    *,
    api_key: str,
) -> SubMaker | None:
    text = text.strip()
    if not text or not api_key:
        return None

    try:
        from pydub import AudioSegment
        import google.generativeai as genai
    except ImportError as e:
        logger.error("gemini tts missing dependency: %s", e)
        return None

    configure_pydub_ffmpeg(AudioSegment)
    genai.configure(api_key=api_key)

    for i in range(3):
        try:
            logger.info("gemini tts start voice=%s try=%s", voice_name, i + 1)
            ensure_file_path_exists(voice_file)
            model = genai.GenerativeModel("gemini-2.5-flash-preview-tts")
            generation_config = {
                "response_modalities": ["AUDIO"],
                "speech_config": {
                    "voice_config": {
                        "prebuilt_voice_config": {"voice_name": voice_name}
                    }
                },
            }
            response = model.generate_content(
                contents=text,
                generation_config=generation_config,
            )
            if not response.candidates or not response.candidates[0].content:
                continue
            audio_data = None
            for part in response.candidates[0].content.parts:
                if hasattr(part, "inline_data") and part.inline_data:
                    audio_data = part.inline_data.data
                    break
            if not audio_data:
                continue
            audio_bytes = (
                base64.b64decode(audio_data)
                if isinstance(audio_data, str)
                else audio_data
            )
            audio_segment = AudioSegment.from_file(
                io.BytesIO(audio_bytes),
                format="raw",
                frame_rate=24000,
                channels=1,
                sample_width=2,
            )
            audio_segment.export(voice_file, format="mp3")
            duration = len(audio_segment) / 1000.0
            sub_maker = SubMaker()
            return populate_legacy_submaker_with_full_text(
                sub_maker=sub_maker,
                text=text,
                audio_duration_seconds=duration,
            )
        except Exception as e:
            logger.error("gemini tts failed: %s", e)
    return None
