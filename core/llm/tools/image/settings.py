"""Agnes AI 生图配置（环境变量 SVG_IMAGE_GEN_* + 运行时 PATCH）。"""

from __future__ import annotations

import os
from typing import Any

from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_AGNES_BASE_URL = "https://apihub.agnes-ai.com/v1"
DEFAULT_AGNES_IMAGE_MODEL = "agnes-image-2.0-flash"
DEFAULT_IMAGE_SIZE = "1024x768"

IMAGE_SIZE_OPTIONS = ("1024x768", "1024x1024", "768x1024")


class ImageGenSettings(BaseSettings):
    """默认使用 [Agnes AI](https://agnes-ai.com/zh-Hans/docs/overview) OpenAI 兼容生图 API。"""

    enabled: bool = True
    provider: str = "agnes"
    model: str = DEFAULT_AGNES_IMAGE_MODEL
    base_url: str = DEFAULT_AGNES_BASE_URL
    api_key: str | None = None
    default_size: str = DEFAULT_IMAGE_SIZE
    timeout_sec: float = 120.0
    max_concurrency: int = 4
    trust_env: bool = False
    reference_enabled: bool = True
    reference_model: str = ""
    reference_image_field: str = "image_url"

    model_config = SettingsConfigDict(
        env_prefix="SVG_IMAGE_GEN_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


class ImageGenConfigManager:
    """生图 API 运行时配置。"""

    def __init__(self) -> None:
        self._settings = ImageGenSettings()

    def get_settings(self) -> ImageGenSettings:
        return self._settings

    def resolved_api_key(self) -> str | None:
        s = self._settings
        if s.api_key and s.api_key.strip():
            return s.api_key.strip()
        for env_name in ("SVG_IMAGE_GEN_API_KEY", "AGNES_API_KEY"):
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
            "provider_label": "Agnes AI",
            "model": s.model,
            "base_url": s.base_url,
            "default_size": s.default_size,
            "available_sizes": list(IMAGE_SIZE_OPTIONS),
            "timeout_sec": s.timeout_sec,
            "max_concurrency": s.max_concurrency,
            "has_api_key": bool(self.resolved_api_key()),
            "active": self.is_available(),
            "reference_enabled": s.reference_enabled,
            "reference_model": s.reference_model or s.model,
            "reference_image_field": s.reference_image_field,
        }

    def update(
        self,
        *,
        enabled: bool | None = None,
        provider: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        default_size: str | None = None,
        timeout_sec: float | None = None,
        max_concurrency: int | None = None,
        reference_enabled: bool | None = None,
        reference_model: str | None = None,
        reference_image_field: str | None = None,
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
                raise ValueError("生图 API Key 不能为空")
        if base_url is not None:
            self._settings.base_url = base_url.rstrip("/")
        if default_size is not None:
            if default_size not in IMAGE_SIZE_OPTIONS:
                raise ValueError(f"不支持的图片尺寸: {default_size}")
            self._settings.default_size = default_size
        if timeout_sec is not None:
            self._settings.timeout_sec = timeout_sec
        if max_concurrency is not None:
            if max_concurrency < 1:
                raise ValueError("max_concurrency 至少为 1")
            self._settings.max_concurrency = max_concurrency
        if reference_enabled is not None:
            self._settings.reference_enabled = reference_enabled
        if reference_model is not None:
            self._settings.reference_model = reference_model.strip()
        if reference_image_field is not None:
            field = reference_image_field.strip()
            if not field:
                raise ValueError("reference_image_field 不能为空")
            self._settings.reference_image_field = field
        return self.get_public_config()


_manager: ImageGenConfigManager | None = None


def get_image_gen_manager() -> ImageGenConfigManager:
    global _manager
    if _manager is None:
        _manager = ImageGenConfigManager()
    return _manager


def get_image_gen_settings() -> ImageGenSettings:
    return get_image_gen_manager().get_settings()


def reset_image_gen_settings() -> None:
    """测试用：重置单例。"""
    global _manager
    _manager = None


def resolved_image_gen_api_key(settings: ImageGenSettings | None = None) -> str | None:
    s = settings or get_image_gen_settings()
    if s.api_key and s.api_key.strip():
        return s.api_key.strip()
    for env_name in ("SVG_IMAGE_GEN_API_KEY", "AGNES_API_KEY"):
        val = os.getenv(env_name)
        if val and val.strip():
            return val.strip()
    return None


def is_image_gen_available(settings: ImageGenSettings | None = None) -> bool:
    s = settings or get_image_gen_settings()
    return bool(s.enabled and resolved_image_gen_api_key(s))
