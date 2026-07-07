"""TTS 统一合成入口。"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from edge_tts import SubMaker

from core.llm.tools.tts.settings import TtsSettings
from core.tts.azure_v2 import synthesize_azure_v2_tts
from core.tts.edge import synthesize_edge_tts
from core.tts.gemini import synthesize_gemini_tts
from core.tts.mimo import synthesize_mimo_tts
from core.tts.openai_client import synthesize_openai_tts
from core.tts.silent import synthesize_no_voice
from core.tts.siliconflow import synthesize_siliconflow_tts
from core.tts.text import normalize_script_text
from core.tts.voices import (
    is_azure_v2_voice,
    is_gemini_voice,
    is_mimo_voice,
    is_no_voice,
    is_siliconflow_voice,
    parse_voice_name,
    resolve_default_voice,
)

logger = logging.getLogger("core.tts.engine")


@dataclass
class TtsRuntimeConfig:
    settings: TtsSettings
    resolved_api_key: str | None = None

    @property
    def voice_name(self) -> str:
        return resolve_default_voice(
            self.settings.provider,
            self.settings.default_voice,
            self.settings.default_language,
        )

    @property
    def voice_rate(self) -> float:
        return float(self.settings.voice_rate or 1.0)

    @property
    def voice_volume(self) -> float:
        return float(self.settings.voice_volume or 1.0)


def build_runtime_config(settings: TtsSettings, resolved_api_key: str | None) -> TtsRuntimeConfig:
    return TtsRuntimeConfig(settings=settings, resolved_api_key=resolved_api_key)


def is_tts_available(config: TtsRuntimeConfig) -> bool:
    if not config.settings.enabled:
        return False
    voice = config.voice_name
    if is_no_voice(voice):
        return True
    if config.settings.provider == "edge":
        return True
    if is_siliconflow_voice(voice):
        return bool(config.settings.siliconflow_api_key)
    if is_gemini_voice(voice):
        return bool(config.settings.gemini_api_key)
    if is_mimo_voice(voice):
        return bool(config.settings.mimo_api_key)
    if is_azure_v2_voice(voice):
        return bool(config.settings.azure_speech_key and config.settings.azure_speech_region)
    if config.settings.provider == "openai":
        return bool(config.resolved_api_key)
    return True


def synthesize_speech(
    text: str,
    voice_file: str,
    config: TtsRuntimeConfig,
    *,
    voice_name: str | None = None,
    voice_rate: float | None = None,
    voice_volume: float | None = None,
) -> SubMaker | None:
    """按 voice_name 前缀路由到对应 TTS 引擎。"""
    cleaned = normalize_script_text(text)
    if not cleaned:
        logger.error("tts text is empty")
        return None

    selected_voice = (voice_name or config.voice_name).strip()
    rate = voice_rate if voice_rate is not None else config.voice_rate
    volume = voice_volume if voice_volume is not None else config.voice_volume
    settings = config.settings

    if is_no_voice(selected_voice):
        return synthesize_no_voice(cleaned, voice_file)

    azure_v2_voice = is_azure_v2_voice(selected_voice)
    if azure_v2_voice:
        return synthesize_azure_v2_tts(
            cleaned,
            selected_voice,
            voice_file,
            speech_key=settings.azure_speech_key or "",
            speech_region=settings.azure_speech_region or "",
        )

    if is_siliconflow_voice(selected_voice):
        parts = selected_voice.split(":")
        if len(parts) >= 3:
            model = parts[1]
            voice_with_gender = parts[2]
            voice = voice_with_gender.split("-")[0]
            full_voice = f"{model}:{voice}"
            return synthesize_siliconflow_tts(
                cleaned,
                model,
                full_voice,
                rate,
                voice_file,
                api_key=settings.siliconflow_api_key or "",
                voice_volume=volume,
            )
        logger.error("invalid siliconflow voice format: %s", selected_voice)
        return None

    if is_gemini_voice(selected_voice):
        parts = selected_voice.split(":")
        if len(parts) >= 2:
            voice_with_gender = parts[1]
            voice = voice_with_gender.split("-")[0]
            return synthesize_gemini_tts(
                cleaned,
                voice,
                voice_file,
                api_key=settings.gemini_api_key or "",
            )
        logger.error("invalid gemini voice format: %s", selected_voice)
        return None

    if is_mimo_voice(selected_voice):
        parts = selected_voice.split(":")
        if len(parts) >= 2:
            voice_with_gender = parts[1]
            voice = voice_with_gender.split("-")[0]
            return synthesize_mimo_tts(
                cleaned,
                voice,
                voice_file,
                api_key=settings.mimo_api_key or "",
                base_url=settings.mimo_base_url or "",
                model_name=settings.mimo_tts_model or "",
                style_prompt=settings.mimo_style_prompt or "",
            )
        logger.error("invalid mimo voice format: %s", selected_voice)
        return None

    if settings.provider == "openai":
        openai_voice = parse_voice_name(selected_voice) or "alloy"
        return synthesize_openai_tts(
            cleaned,
            openai_voice,
            rate,
            voice_file,
            api_key=config.resolved_api_key or "",
            model=settings.model,
            base_url=settings.base_url,
            timeout_sec=settings.timeout_sec,
        )

    edge_voice = parse_voice_name(selected_voice)
    timeout = settings.edge_tts_timeout_sec
    if timeout <= 0:
        timeout = None
    return synthesize_edge_tts(
        cleaned,
        edge_voice,
        rate,
        voice_file,
        timeout_seconds=timeout,
    )
