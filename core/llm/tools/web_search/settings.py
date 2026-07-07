"""联网搜索配置（环境变量）。"""

from __future__ import annotations

import os
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

WebSearchProvider = Literal["duckduckgo", "tavily"]


class WebSearchSettings(BaseSettings):
    """SVG_WEB_SEARCH_* 环境变量。"""

    model_config = SettingsConfigDict(
        env_prefix="SVG_WEB_SEARCH_",
        extra="ignore",
    )

    provider: WebSearchProvider = "duckduckgo"
    api_key: str = ""
    max_results: int = Field(default=5, ge=1, le=20)
    timeout_sec: float = Field(default=15.0, ge=3.0, le=60.0)
    user_agent: str = (
        "SuperVideoGenerator/0.1 (+https://github.com/local/super-video-generator)"
    )

    def resolved_api_key(self) -> str:
        if self.api_key.strip():
            return self.api_key.strip()
        if self.provider == "tavily":
            return (os.getenv("TAVILY_API_KEY") or "").strip()
        return ""

    def resolved_provider(self) -> WebSearchProvider:
        if self.provider == "tavily" and self.resolved_api_key():
            return "tavily"
        return "duckduckgo"


_settings: WebSearchSettings | None = None


def get_web_search_settings() -> WebSearchSettings:
    global _settings
    if _settings is None:
        _settings = WebSearchSettings()
    return _settings
