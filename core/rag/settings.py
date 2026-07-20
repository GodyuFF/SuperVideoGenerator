"""RAG Embedding 运行时配置（环境变量 SVG_RAG_EMBEDDING_* + AI 配置页）。"""

from __future__ import annotations

import os
from typing import Any

from pydantic_settings import BaseSettings, SettingsConfigDict


class EmbeddingSettings(BaseSettings):
    """OpenAI 兼容 Embedding 连接参数。"""

    enabled: bool = True
    api_key: str | None = None
    base_url: str = "https://api.openai.com/v1"
    model: str = "text-embedding-3-small"

    model_config = SettingsConfigDict(
        env_prefix="SVG_RAG_EMBEDDING_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


class EmbeddingConfigManager:
    """Embedding 配置管理：JSON 优先，其次环境变量。"""

    def __init__(self) -> None:
        self._settings = EmbeddingSettings()

    def get_settings(self) -> EmbeddingSettings:
        """返回当前内存中的 settings。"""
        return self._settings

    def resolved_api_key(self) -> str | None:
        """解析可用 API Key：settings → SVG_RAG_EMBEDDING_API_KEY → OPENAI_API_KEY。"""
        s = self._settings
        if s.api_key and s.api_key.strip():
            return s.api_key.strip()
        for env_name in ("SVG_RAG_EMBEDDING_API_KEY", "OPENAI_API_KEY"):
            val = os.getenv(env_name)
            if val and val.strip():
                return val.strip()
        return None

    def is_configured(self) -> bool:
        """是否已配置可用 Key 且启用。"""
        return bool(self._settings.enabled and self.resolved_api_key())

    def get_public_config(self) -> dict[str, Any]:
        """返回前端可见配置（不含明文 Key）。"""
        s = self._settings
        return {
            "enabled": s.enabled,
            "base_url": s.base_url,
            "model": s.model,
            "has_api_key": bool(self.resolved_api_key()),
            "active": self.is_configured(),
        }

    def update(
        self,
        *,
        enabled: bool | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ) -> dict[str, Any]:
        """更新配置字段；api_key 留空表示不修改。"""
        if enabled is not None:
            self._settings.enabled = enabled
        if api_key is not None:
            key = api_key.strip()
            if key:
                self._settings.api_key = key
        if base_url is not None:
            self._settings.base_url = base_url.strip() or self._settings.base_url
        if model is not None:
            self._settings.model = model.strip() or self._settings.model
        from core.rag.embedder import reset_embedder

        reset_embedder()
        return self.get_public_config()


_manager: EmbeddingConfigManager | None = None


def get_embedding_manager() -> EmbeddingConfigManager:
    """返回进程级 EmbeddingConfigManager 单例。"""
    global _manager
    if _manager is None:
        _manager = EmbeddingConfigManager()
    return _manager


def reset_embedding_manager() -> None:
    """测试用：重置 Embedding 配置单例。"""
    global _manager
    _manager = None
    from core.rag.embedder import reset_embedder

    reset_embedder()
