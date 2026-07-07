"""AI 视频生成配置（环境变量 SVG_VIDEO_GEN_*，API 接入预留）。"""

from __future__ import annotations

import os
from typing import Any

from pydantic_settings import BaseSettings, SettingsConfigDict


class VideoGenSettings(BaseSettings):
    enabled: bool = False
    provider: str = "agnes"
    model: str = "agnes-video-v2.0"
    base_url: str = "https://apihub.agnes-ai.com/v1"
    api_key: str | None = None
    max_duration_sec: int = 10
    resolution: str = "1080p"
    timeout_sec: float = 300.0
    trust_env: bool = False

    model_config = SettingsConfigDict(
        env_prefix="SVG_VIDEO_GEN_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


class VideoGenConfigManager:
    """视频生成运行时配置。"""

    def __init__(self) -> None:
        self._settings = VideoGenSettings()

    def get_settings(self) -> VideoGenSettings:
        return self._settings

    def resolved_api_key(self) -> str | None:
        s = self._settings
        if s.api_key and s.api_key.strip():
            return s.api_key.strip()
        for env_name in ("SVG_VIDEO_GEN_API_KEY", "AGNES_API_KEY"):
            val = os.getenv(env_name)
            if val and val.strip():
                return val.strip()
        return None

    def is_available(self) -> bool:
        s = self._settings
        return bool(s.enabled and self.resolved_api_key())

    def get_public_config(self) -> dict[str, Any]:
        s = self._settings
        return {
            "enabled": s.enabled,
            "provider": s.provider,
            "model": s.model,
            "base_url": s.base_url,
            "max_duration_sec": s.max_duration_sec,
            "resolution": s.resolution,
            "timeout_sec": s.timeout_sec,
            "has_api_key": bool(self.resolved_api_key()),
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
        max_duration_sec: int | None = None,
        resolution: str | None = None,
        timeout_sec: float | None = None,
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
            elif not self.resolved_api_key():
                raise ValueError("视频 API Key 不能为空")
        if base_url is not None:
            self._settings.base_url = base_url
        if max_duration_sec is not None:
            self._settings.max_duration_sec = max_duration_sec
        if resolution is not None:
            self._settings.resolution = resolution
        if timeout_sec is not None:
            self._settings.timeout_sec = timeout_sec
        return self.get_public_config()


_manager: VideoGenConfigManager | None = None


def get_video_gen_manager() -> VideoGenConfigManager:
    global _manager
    if _manager is None:
        _manager = VideoGenConfigManager()
    return _manager


def reset_video_gen_manager() -> None:
    global _manager
    _manager = None
