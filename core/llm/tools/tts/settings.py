"""TTS 合成配置（环境变量 SVG_TTS_*，多引擎）。"""

from __future__ import annotations

import os
from typing import Any

from pydantic_settings import BaseSettings, SettingsConfigDict


class TtsSettings(BaseSettings):
    enabled: bool = True
    provider: str = "edge"
    model: str = "tts-1"
    base_url: str = "https://api.openai.com/v1"
    api_key: str | None = None
    default_language: str = "zh-CN"
    default_voice: str = "zh-CN-XiaoxiaoNeural-Female"
    voice_rate: float = 1.0
    voice_volume: float = 1.0
    sample_rate: int = 24000
    timeout_sec: float = 60.0
    edge_tts_timeout_sec: float = 30.0
    max_concurrency: int = 3
    ffmpeg_path: str = ""
    gemini_api_key: str | None = None
    mimo_api_key: str | None = None
    mimo_base_url: str = "https://api.xiaomimimo.com/v1"
    mimo_tts_model: str = "mimo-v2.5-tts"
    mimo_style_prompt: str = "请用自然、清晰、适合短视频旁白的语气朗读。"
    siliconflow_api_key: str | None = None
    azure_speech_key: str | None = None
    azure_speech_region: str | None = None
    trust_env: bool = False

    model_config = SettingsConfigDict(
        env_prefix="SVG_TTS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


class TtsConfigManager:
    """TTS 运行时配置。"""

    def __init__(self) -> None:
        self._settings = TtsSettings()

    def get_settings(self) -> TtsSettings:
        return self._settings

    def resolved_api_key(self) -> str | None:
        s = self._settings
        if s.api_key and s.api_key.strip():
            return s.api_key.strip()
        for env_name in ("SVG_TTS_API_KEY", "OPENAI_API_KEY"):
            val = os.getenv(env_name)
            if val and val.strip():
                return val.strip()
        return None

    def runtime_config(self):
        from core.tts.engine import build_runtime_config

        return build_runtime_config(self._settings, self.resolved_api_key())

    def preview_runtime_config(
        self,
        *,
        provider: str | None = None,
        voice_name: str | None = None,
        voice_rate: float | None = None,
        voice_volume: float | None = None,
        default_language: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        gemini_api_key: str | None = None,
        mimo_api_key: str | None = None,
        siliconflow_api_key: str | None = None,
        azure_speech_key: str | None = None,
        azure_speech_region: str | None = None,
    ):
        """试听专用：合并表单覆盖项，不依赖 enabled 开关。"""
        from core.tts.engine import build_runtime_config

        settings = self._settings.model_copy(deep=True)
        settings.enabled = True
        if provider is not None:
            settings.provider = provider
        if voice_name:
            settings.default_voice = voice_name
        if voice_rate is not None:
            settings.voice_rate = voice_rate
        if voice_volume is not None:
            settings.voice_volume = voice_volume
        if default_language is not None:
            settings.default_language = default_language
        if model is not None:
            settings.model = model
        if base_url is not None:
            settings.base_url = base_url
        if gemini_api_key and gemini_api_key.strip():
            settings.gemini_api_key = gemini_api_key.strip()
        if mimo_api_key and mimo_api_key.strip():
            settings.mimo_api_key = mimo_api_key.strip()
        if siliconflow_api_key and siliconflow_api_key.strip():
            settings.siliconflow_api_key = siliconflow_api_key.strip()
        if azure_speech_key and azure_speech_key.strip():
            settings.azure_speech_key = azure_speech_key.strip()
        if azure_speech_region is not None:
            settings.azure_speech_region = azure_speech_region
        resolved = self.resolved_api_key()
        if api_key and api_key.strip():
            resolved = api_key.strip()
        return build_runtime_config(settings, resolved)

    def is_available(self) -> bool:
        from core.tts.engine import is_tts_available

        return is_tts_available(self.runtime_config())

    def get_public_config(self) -> dict[str, Any]:
        s = self._settings
        return {
            "enabled": s.enabled,
            "provider": s.provider,
            "model": s.model,
            "base_url": s.base_url,
            "default_language": s.default_language,
            "default_voice": s.default_voice,
            "voice_rate": s.voice_rate,
            "voice_volume": s.voice_volume,
            "sample_rate": s.sample_rate,
            "timeout_sec": s.timeout_sec,
            "edge_tts_timeout_sec": s.edge_tts_timeout_sec,
            "max_concurrency": s.max_concurrency,
            "ffmpeg_path": s.ffmpeg_path,
            "mimo_base_url": s.mimo_base_url,
            "mimo_tts_model": s.mimo_tts_model,
            "mimo_style_prompt": s.mimo_style_prompt,
            "has_api_key": bool(self.resolved_api_key()),
            "has_gemini_api_key": bool(s.gemini_api_key),
            "has_mimo_api_key": bool(s.mimo_api_key),
            "has_siliconflow_api_key": bool(s.siliconflow_api_key),
            "has_azure_speech_key": bool(s.azure_speech_key),
            "azure_speech_region": s.azure_speech_region or "",
            "active": self.is_available(),
        }

    def update(
        self,
        *,
        enabled: bool | None = None,
        provider: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        default_language: str | None = None,
        default_voice: str | None = None,
        voice_rate: float | None = None,
        voice_volume: float | None = None,
        sample_rate: int | None = None,
        timeout_sec: float | None = None,
        edge_tts_timeout_sec: float | None = None,
        max_concurrency: int | None = None,
        ffmpeg_path: str | None = None,
        gemini_api_key: str | None = None,
        mimo_api_key: str | None = None,
        mimo_base_url: str | None = None,
        mimo_tts_model: str | None = None,
        mimo_style_prompt: str | None = None,
        siliconflow_api_key: str | None = None,
        azure_speech_key: str | None = None,
        azure_speech_region: str | None = None,
    ) -> dict[str, Any]:
        if enabled is not None:
            self._settings.enabled = enabled
        if provider is not None:
            self._settings.provider = provider
        if model is not None:
            self._settings.model = model
        if api_key is not None:
            key = api_key.strip()
            if key:
                self._settings.api_key = key
            elif self._settings.provider == "openai" and not self.resolved_api_key():
                raise ValueError("TTS API Key 不能为空")
        if base_url is not None:
            self._settings.base_url = base_url
        if default_language is not None:
            self._settings.default_language = default_language
        if default_voice is not None:
            self._settings.default_voice = default_voice
        if voice_rate is not None:
            self._settings.voice_rate = voice_rate
        if voice_volume is not None:
            self._settings.voice_volume = voice_volume
        if sample_rate is not None:
            self._settings.sample_rate = sample_rate
        if timeout_sec is not None:
            self._settings.timeout_sec = timeout_sec
        if edge_tts_timeout_sec is not None:
            self._settings.edge_tts_timeout_sec = edge_tts_timeout_sec
        if max_concurrency is not None:
            self._settings.max_concurrency = max_concurrency
        if ffmpeg_path is not None:
            self._settings.ffmpeg_path = ffmpeg_path
        if gemini_api_key is not None and gemini_api_key.strip():
            self._settings.gemini_api_key = gemini_api_key.strip()
        if mimo_api_key is not None and mimo_api_key.strip():
            self._settings.mimo_api_key = mimo_api_key.strip()
        if mimo_base_url is not None:
            self._settings.mimo_base_url = mimo_base_url
        if mimo_tts_model is not None:
            self._settings.mimo_tts_model = mimo_tts_model
        if mimo_style_prompt is not None:
            self._settings.mimo_style_prompt = mimo_style_prompt
        if siliconflow_api_key is not None and siliconflow_api_key.strip():
            self._settings.siliconflow_api_key = siliconflow_api_key.strip()
        if azure_speech_key is not None and azure_speech_key.strip():
            self._settings.azure_speech_key = azure_speech_key.strip()
        if azure_speech_region is not None:
            self._settings.azure_speech_region = azure_speech_region
        return self.get_public_config()


_manager: TtsConfigManager | None = None


def get_tts_manager() -> TtsConfigManager:
    global _manager
    if _manager is None:
        _manager = TtsConfigManager()
    return _manager


def reset_tts_manager() -> None:
    global _manager
    _manager = None
