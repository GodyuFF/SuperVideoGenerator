"""WhisperX 强制对齐配置（环境变量 SVG_WHISPERX_*）。"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class WhisperXSettings(BaseSettings):
    """WhisperX 对齐/转写语言、ASR 模型与可选 align 模型名。"""

    language: str = "zh"
    model: str = "base"
    align_model: str = ""

    model_config = SettingsConfigDict(
        env_prefix="SVG_WHISPERX_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_whisperx_settings() -> WhisperXSettings:
    """读取并缓存 WhisperX 配置。"""
    return WhisperXSettings()
