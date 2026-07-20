"""LLM 配置：环境变量 + 运行时覆盖。"""

import os
from typing import Any, Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from core.llm.client.providers import DEFAULT_PROVIDER_ID, PROVIDER_PRESETS, resolved_protocol
from core.models.entities import ImageSourceMode, ImageTextConfig

# 输出 Token 上限：384k = 384 * 1024
MAX_OUTPUT_TOKENS = 393_216
DEFAULT_MAX_TOKENS = 8192


class LLMSettings(BaseSettings):
    """ReAct LLM 配置。环境变量前缀 SVG_LLM_，例如 SVG_LLM_PROVIDER=deepseek。"""

    provider: str = DEFAULT_PROVIDER_ID
    model: str | None = None
    api_key: str | None = None
    base_url: str | None = None
    temperature: float = 0.2
    max_tokens: int = DEFAULT_MAX_TOKENS
    context_window_tokens: int = 1_048_576
    history_keep_messages: int = 10
    timeout_sec: float = 60.0
    use_llm_react: bool = True
    # 工作台 ReAct 展示：True=思考/行动/观察完整信息；False=仅工具名称
    show_react_details: bool = True
    trust_env: bool = False  # 是否读取系统代理；部分环境下代理会导致 ConnectError
    image_source_default: ImageSourceMode = ImageSourceMode.GENERATE
    image_text_preset: Literal["explainer", "report", "lecture"] = "explainer"
    comic_preset: Literal["manga", "webtoon", "ink"] = "manga"
    image_batch_pending_assets: bool = True
    image_allow_search_fallback: bool = True
    # None=按模型名自动推断；True/False 强制 thinking 模式 tool_choice 适配
    thinking_mode: bool | None = None

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
        self._provider_migrated = False
        self._normalize_provider()

    def _normalize_provider(self) -> None:
        if self._settings.provider not in PROVIDER_PRESETS:
            self._settings.provider = DEFAULT_PROVIDER_ID
            self._provider_migrated = True

    def get_settings(self) -> LLMSettings:
        self._normalize_provider()
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

    def is_thinking_mode(self) -> bool:
        from core.llm.client.tool_choice import resolve_thinking_mode

        return resolve_thinking_mode(
            self.resolved_model(),
            override=self._settings.thinking_mode,
        )

    def adapt_tool_choice(self, tool_choice: dict[str, Any] | None) -> dict[str, Any] | None:
        from core.llm.client.tool_choice import adapt_tool_choice_for_thinking

        return adapt_tool_choice_for_thinking(
            tool_choice,
            thinking_mode=self.is_thinking_mode(),
        )

    def is_llm_available(self) -> bool:
        return bool(self._settings.use_llm_react and self.resolved_api_key())

    def get_image_text_defaults(self) -> ImageTextConfig:
        s = self._settings
        return ImageTextConfig(
            source_mode=s.image_source_default,
            image_text_preset=s.image_text_preset,
            comic_preset=s.comic_preset,
            batch_pending_assets=s.image_batch_pending_assets,
            allow_search_fallback=s.image_allow_search_fallback,
        )

    def get_public_config(self) -> dict[str, Any]:
        s = self._settings
        preset = PROVIDER_PRESETS.get(s.provider)
        result = {
            "provider": s.provider,
            "provider_label": preset.label if preset else s.provider,
            "protocol": resolved_protocol(s.provider),
            "model": self.resolved_model(),
            "base_url": self.resolved_base_url(),
            "temperature": s.temperature,
            "max_tokens": s.max_tokens,
            "context_window_tokens": s.context_window_tokens,
            "history_keep_messages": s.history_keep_messages,
            "use_llm_react": s.use_llm_react,
            "show_react_details": s.show_react_details,
            "has_api_key": bool(self.resolved_api_key()),
            "llm_active": self.is_llm_available(),
            "available_providers": [
                {
                    "id": p.id,
                    "label": p.label,
                    "default_model": p.default_model,
                    "protocol": p.protocol,
                }
                for p in PROVIDER_PRESETS.values()
            ],
            "image_text_defaults": self.get_image_text_defaults().model_dump(),
        }
        if self._provider_migrated:
            result["provider_migrated"] = True
        return result

    def update(
        self,
        provider: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        use_llm_react: bool | None = None,
        show_react_details: bool | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        context_window_tokens: int | None = None,
        history_keep_messages: int | None = None,
        image_source_default: ImageSourceMode | str | None = None,
        image_text_preset: str | None = None,
        comic_preset: str | None = None,
        image_batch_pending_assets: bool | None = None,
        image_allow_search_fallback: bool | None = None,
    ) -> dict[str, Any]:
        if provider is not None:
            if provider not in PROVIDER_PRESETS:
                raise ValueError(f"未知服务商: {provider}")
            self._settings.provider = provider
            self._provider_migrated = False
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
        if show_react_details is not None:
            self._settings.show_react_details = show_react_details
        if temperature is not None:
            self._settings.temperature = temperature
        if max_tokens is not None:
            if max_tokens < 256 or max_tokens > MAX_OUTPUT_TOKENS:
                raise ValueError(
                    f"max_tokens 须在 256~{MAX_OUTPUT_TOKENS} 之间（当前 {max_tokens}）"
                )
            self._settings.max_tokens = max_tokens
        if context_window_tokens is not None:
            self._settings.context_window_tokens = context_window_tokens
        if history_keep_messages is not None:
            self._settings.history_keep_messages = history_keep_messages
        if image_source_default is not None:
            self._settings.image_source_default = ImageSourceMode(image_source_default)
        if image_text_preset is not None:
            self._settings.image_text_preset = image_text_preset  # type: ignore[assignment]
        if comic_preset is not None:
            self._settings.comic_preset = comic_preset  # type: ignore[assignment]
        if image_batch_pending_assets is not None:
            self._settings.image_batch_pending_assets = image_batch_pending_assets
        if image_allow_search_fallback is not None:
            self._settings.image_allow_search_fallback = image_allow_search_fallback
        return self.get_public_config()
