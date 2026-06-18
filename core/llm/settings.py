"""LLM 配置：环境变量 + 运行时覆盖。"""

import os
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from core.llm.providers import DEFAULT_PROVIDER_ID, PROVIDER_PRESETS


class LLMSettings(BaseSettings):
    """ReAct LLM 配置。环境变量前缀 SVG_LLM_，例如 SVG_LLM_PROVIDER=openai。"""

    provider: str = DEFAULT_PROVIDER_ID
    model: str | None = None
    api_key: str | None = None
    base_url: str | None = None
    temperature: float = 0.2
    max_tokens: int = 1024
    timeout_sec: float = 60.0
    use_llm_react: bool = True

    model_config = SettingsConfigDict(
        env_prefix="SVG_LLM_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


class LLMConfigManager:
    """集中管理 LLM 配置，支持 API 运行时更新。"""

    def __init__(self) -> None:
        self._settings = LLMSettings()

    def get_settings(self) -> LLMSettings:
        return self._settings

    def resolved_api_key(self) -> str | None:
        s = self._settings
        if s.api_key:
            return s.api_key.strip()
        preset = PROVIDER_PRESETS.get(s.provider)
        if preset:
            env_val = os.getenv(preset.api_key_env)
            if env_val:
                return env_val.strip()
        generic = os.getenv("SVG_LLM_API_KEY")
        return generic.strip() if generic else None

    def resolved_base_url(self) -> str:
        if self._settings.base_url:
            return self._settings.base_url.rstrip("/")
        preset = PROVIDER_PRESETS.get(self._settings.provider)
        if preset:
            return preset.base_url.rstrip("/")
        return PROVIDER_PRESETS[DEFAULT_PROVIDER_ID].base_url

    def resolved_model(self) -> str:
        if self._settings.model:
            return self._settings.model
        preset = PROVIDER_PRESETS.get(self._settings.provider)
        if preset:
            return preset.default_model
        return PROVIDER_PRESETS[DEFAULT_PROVIDER_ID].default_model

    def is_llm_available(self) -> bool:
        return bool(self._settings.use_llm_react and self.resolved_api_key())

    def get_public_config(self) -> dict[str, Any]:
        s = self._settings
        preset = PROVIDER_PRESETS.get(s.provider)
        return {
            "provider": s.provider,
            "provider_label": preset.label if preset else s.provider,
            "model": self.resolved_model(),
            "base_url": self.resolved_base_url(),
            "temperature": s.temperature,
            "max_tokens": s.max_tokens,
            "use_llm_react": s.use_llm_react,
            "has_api_key": bool(self.resolved_api_key()),
            "llm_active": self.is_llm_available(),
            "available_providers": [
                {"id": p.id, "label": p.label, "default_model": p.default_model}
                for p in PROVIDER_PRESETS.values()
            ],
        }

    def update(
        self,
        provider: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        use_llm_react: bool | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        if provider is not None:
            if provider not in PROVIDER_PRESETS:
                raise ValueError(f"未知服务商: {provider}")
            self._settings.provider = provider
        if model is not None:
            self._settings.model = model
        if api_key is not None:
            key = api_key.strip()
            if key:
                self._settings.api_key = key
            elif not self.resolved_api_key():
                raise ValueError("API Key 不能为空")
        if base_url is not None:
            self._settings.base_url = base_url
        if use_llm_react is not None:
            self._settings.use_llm_react = use_llm_react
        if temperature is not None:
            self._settings.temperature = temperature
        if max_tokens is not None:
            self._settings.max_tokens = max_tokens
        return self.get_public_config()
