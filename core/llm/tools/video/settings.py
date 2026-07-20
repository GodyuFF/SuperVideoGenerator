"""AI 视频生成配置（环境变量 SVG_VIDEO_GEN_*，支持多 Provider）。"""

from __future__ import annotations

import os
from typing import Any

from pydantic_settings import BaseSettings, SettingsConfigDict

from core.llm.tools.shared.media_capability import list_video_provider_capabilities
from core.llm.tools.volcengine.ark_common import DEFAULT_ARK_BASE_URL, DEFAULT_SEEDANCE_MODEL

VIDEO_PROVIDERS = ("agnes", "volcengine", "kling", "runway", "fal")

DEFAULT_KLING_BASE_URL = "https://api.klingai.com/v1"
DEFAULT_KLING_MODEL = "kling-v3-omni-video"
DEFAULT_RUNWAY_BASE_URL = "https://api.dev.runwayml.com/v1"
DEFAULT_RUNWAY_MODEL = "gen4.5"
DEFAULT_FAL_VIDEO_BASE_URL = "https://fal.run"
DEFAULT_FAL_VIDEO_MODEL = "fal-ai/kling-video/v2.1/master/image-to-video"


class VideoGenSettings(BaseSettings):
    """AI 视频生成环境配置（SVG_VIDEO_GEN_*）。"""

    enabled: bool = False
    provider: str = "agnes"
    model: str = "agnes-video-v2.0"
    base_url: str = "https://apihub.agnes-ai.com/v1"
    api_key: str | None = None
    max_duration_sec: int = 10
    resolution: str = "1080p"
    # 含 429 退避余量
    timeout_sec: float = 600.0
    # Agnes Free 状态查询 RPM 极低，默认 15s
    poll_interval_sec: float = 15.0
    # Agnes Free 创建约 1 次/分钟；两次 POST /videos 最小间隔（秒），0=不限
    create_min_interval_sec: float = 60.0
    # 创建遇 429 时最多重试次数（含首次）
    create_max_attempts: int = 4
    # 默认串行，避免多 clip 叠压状态查询
    max_concurrency: int = 1
    trust_env: bool = False
    fallback_provider: str = ""
    fallback_model: str = ""

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
        for env_name in (
            "SVG_VIDEO_GEN_API_KEY",
            "AGNES_API_KEY",
            "ARK_API_KEY",
            "KLING_API_KEY",
            "KLING_ACCESS_KEY",
            "RUNWAY_API_KEY",
            "FAL_KEY",
            "FAL_API_KEY",
        ):
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
            "provider_label": (
                "火山方舟 SeedDance" if s.provider == "volcengine"
                else "Kling AI" if s.provider == "kling"
                else "Runway" if s.provider == "runway"
                else "fal.ai" if s.provider == "fal"
                else "Agnes AI"
            ),
            "available_providers": [
                {"id": "agnes", "label": "Agnes AI"},
                {"id": "volcengine", "label": "火山方舟 SeedDance"},
                {"id": "kling", "label": "Kling AI"},
                {"id": "runway", "label": "Runway"},
                {"id": "fal", "label": "fal.ai"},
            ],
            "model": s.model,
            "base_url": s.base_url,
            "default_model_volcengine": DEFAULT_SEEDANCE_MODEL,
            "default_base_url_volcengine": DEFAULT_ARK_BASE_URL,
            "max_duration_sec": s.max_duration_sec,
            "resolution": s.resolution,
            "timeout_sec": s.timeout_sec,
            "poll_interval_sec": s.poll_interval_sec,
            "create_min_interval_sec": s.create_min_interval_sec,
            "create_max_attempts": s.create_max_attempts,
            "max_concurrency": s.max_concurrency,
            "has_api_key": bool(self.resolved_api_key()),
            "active": self.is_available(),
            "fallback_provider": s.fallback_provider,
            "fallback_model": s.fallback_model,
            "capabilities": list_video_provider_capabilities(),
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
        poll_interval_sec: float | None = None,
        create_min_interval_sec: float | None = None,
        create_max_attempts: int | None = None,
        max_concurrency: int | None = None,
        fallback_provider: str | None = None,
        fallback_model: str | None = None,
    ) -> dict[str, Any]:
        """更新视频生成运行时配置。"""
        if enabled is not None:
            self._settings.enabled = enabled
        if provider is not None:
            if provider not in VIDEO_PROVIDERS:
                raise ValueError(f"不支持的视频生成服务商: {provider}")
            self._settings.provider = provider
            if provider == "volcengine" and self._settings.model == "agnes-video-v2.0":
                self._settings.model = DEFAULT_SEEDANCE_MODEL
                self._settings.base_url = DEFAULT_ARK_BASE_URL
                self._settings.poll_interval_sec = max(self._settings.poll_interval_sec, 3.0)
                self._settings.create_min_interval_sec = 0.0
            elif provider == "agnes" and self._settings.model == DEFAULT_SEEDANCE_MODEL:
                self._settings.model = "agnes-video-v2.0"
                self._settings.base_url = "https://apihub.agnes-ai.com/v1"
                self._settings.poll_interval_sec = max(self._settings.poll_interval_sec, 15.0)
                self._settings.create_min_interval_sec = max(self._settings.create_min_interval_sec, 60.0)
            elif provider == "kling":
                if self._settings.model in ("", "agnes-video-v2.0", DEFAULT_SEEDANCE_MODEL):
                    self._settings.model = DEFAULT_KLING_MODEL
                if not (self._settings.base_url or "").strip() or "agnes-ai.com" in (self._settings.base_url or ""):
                    self._settings.base_url = DEFAULT_KLING_BASE_URL
                self._settings.poll_interval_sec = max(self._settings.poll_interval_sec, 10.0)
                self._settings.create_min_interval_sec = max(self._settings.create_min_interval_sec, 5.0)
            elif provider == "runway":
                if self._settings.model in ("", "agnes-video-v2.0", DEFAULT_SEEDANCE_MODEL, DEFAULT_KLING_MODEL):
                    self._settings.model = DEFAULT_RUNWAY_MODEL
                if not (self._settings.base_url or "").strip() or "agnes-ai.com" in (self._settings.base_url or ""):
                    self._settings.base_url = DEFAULT_RUNWAY_BASE_URL
                self._settings.poll_interval_sec = max(self._settings.poll_interval_sec, 10.0)
                self._settings.create_min_interval_sec = max(self._settings.create_min_interval_sec, 5.0)
            elif provider == "fal":
                if self._settings.model in ("", "agnes-video-v2.0", DEFAULT_SEEDANCE_MODEL):
                    self._settings.model = DEFAULT_FAL_VIDEO_MODEL
                if not (self._settings.base_url or "").strip() or "agnes-ai.com" in (self._settings.base_url or ""):
                    self._settings.base_url = DEFAULT_FAL_VIDEO_BASE_URL
                self._settings.poll_interval_sec = max(self._settings.poll_interval_sec, 10.0)
                self._settings.create_min_interval_sec = max(self._settings.create_min_interval_sec, 5.0)
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
        if poll_interval_sec is not None:
            self._settings.poll_interval_sec = max(5.0, float(poll_interval_sec))
        if create_min_interval_sec is not None:
            self._settings.create_min_interval_sec = max(0.0, float(create_min_interval_sec))
        if create_max_attempts is not None:
            self._settings.create_max_attempts = max(1, int(create_max_attempts))
        if max_concurrency is not None:
            self._settings.max_concurrency = max(1, int(max_concurrency))
        if fallback_provider is not None:
            fb = fallback_provider.strip().lower()
            if fb and fb not in VIDEO_PROVIDERS:
                raise ValueError(f"不支持的 fallback 视频服务商: {fb}")
            self._settings.fallback_provider = fb
        if fallback_model is not None:
            self._settings.fallback_model = fallback_model.strip()
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
