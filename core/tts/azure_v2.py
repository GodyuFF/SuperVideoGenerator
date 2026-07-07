"""Azure Speech v2 TTS 合成。"""

from __future__ import annotations

import logging
from datetime import datetime

from edge_tts import SubMaker

from core.tts.subtitle import ensure_legacy_submaker_fields
from core.tts.voices import is_azure_v2_voice

logger = logging.getLogger("core.tts.azure_v2")


def _format_duration_to_offset(duration) -> int:
    if isinstance(duration, str):
        time_obj = datetime.strptime(duration, "%H:%M:%S.%f")
        milliseconds = (
            (time_obj.hour * 3600000)
            + (time_obj.minute * 60000)
            + (time_obj.second * 1000)
            + (time_obj.microsecond // 1000)
        )
        return milliseconds * 10000
    if isinstance(duration, int):
        return duration
    return 0


def synthesize_azure_v2_tts(
    text: str,
    voice_name: str,
    voice_file: str,
    *,
    speech_key: str,
    speech_region: str,
) -> SubMaker | None:
    parsed_voice = is_azure_v2_voice(voice_name)
    if not parsed_voice:
        logger.error("invalid azure v2 voice: %s", voice_name)
        return None
    if not speech_key or not speech_region:
        logger.error("azure speech key or region not set")
        return None

    text = text.strip()
    for i in range(3):
        try:
            import azure.cognitiveservices.speech as speechsdk

            logger.info("azure v2 tts start voice=%s try=%s", parsed_voice, i + 1)
            sub_maker = ensure_legacy_submaker_fields(SubMaker())

            def speech_synthesizer_word_boundary_cb(evt: speechsdk.SessionEventArgs):
                duration = _format_duration_to_offset(str(evt.duration))
                offset = _format_duration_to_offset(evt.audio_offset)
                sub_maker.subs.append(evt.text)
                sub_maker.offset.append((offset, offset + duration))

            audio_config = speechsdk.audio.AudioOutputConfig(
                filename=voice_file, use_default_speaker=True
            )
            speech_config = speechsdk.SpeechConfig(
                subscription=speech_key, region=speech_region
            )
            speech_config.speech_synthesis_voice_name = parsed_voice
            speech_config.set_property(
                property_id=speechsdk.PropertyId.SpeechServiceResponse_RequestWordBoundary,
                value="true",
            )
            speech_config.set_speech_synthesis_output_format(
                speechsdk.SpeechSynthesisOutputFormat.Audio48Khz192KBitRateMonoMp3
            )
            speech_synthesizer = speechsdk.SpeechSynthesizer(
                audio_config=audio_config, speech_config=speech_config
            )
            speech_synthesizer.synthesis_word_boundary.connect(
                speech_synthesizer_word_boundary_cb
            )
            result = speech_synthesizer.speak_text_async(text).get()
            if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
                logger.info("azure v2 tts succeeded file=%s", voice_file)
                return sub_maker
            logger.error("azure v2 tts canceled/failed: %s", result.reason)
        except ImportError:
            logger.error("azure-cognitiveservices-speech not installed")
            return None
        except Exception as e:
            logger.error("azure v2 tts failed: %s", e)
    return None
