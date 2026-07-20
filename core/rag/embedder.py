"""OpenAI 兼容 Embedding 客户端。"""

from __future__ import annotations

from typing import Protocol

import httpx


class Embedder(Protocol):
    """文本向量化协议。"""

    async def embed(self, text: str) -> list[float]:
        """将单段文本转为 embedding 向量。"""
        ...


class OpenAIEmbedder:
    """调用 OpenAI 兼容 embeddings API。"""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ) -> None:
        from core.rag.settings import get_embedding_manager

        mgr = get_embedding_manager()
        settings = mgr.get_settings()
        self._api_key = (api_key if api_key is not None else mgr.resolved_api_key() or "").strip()
        self._base_url = (base_url or settings.base_url or "https://api.openai.com/v1").rstrip("/")
        self._model = (model or settings.model or "text-embedding-3-small").strip()

    @property
    def has_api_key(self) -> bool:
        """是否已配置 API Key。"""
        return bool(self._api_key)

    async def embed(self, text: str) -> list[float]:
        """请求远程 embedding；无 API Key 时抛出明确错误。"""
        return self.embed_sync(text)

    def embed_sync(self, text: str) -> list[float]:
        """同步请求 OpenAI 兼容 embedding API。"""
        if not self._api_key:
            raise RuntimeError(
                "未配置 Embedding API Key（AI 配置页 / SVG_RAG_EMBEDDING_API_KEY / OPENAI_API_KEY）"
            )
        payload = {"model": self._model, "input": text}
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(
                f"{self._base_url}/embeddings", json=payload, headers=headers
            )
            resp.raise_for_status()
            data = resp.json()
        rows = data.get("data") or []
        if not rows:
            raise RuntimeError("embedding API 返回空 data")
        vector = rows[0].get("embedding")
        if not isinstance(vector, list):
            raise RuntimeError("embedding API 返回格式异常")
        return [float(x) for x in vector]


_default_embedder: OpenAIEmbedder | None = None


def get_embedder() -> OpenAIEmbedder:
    """返回进程级默认 Embedder 单例（读当前 AI 配置）。"""
    global _default_embedder
    if _default_embedder is None:
        _default_embedder = OpenAIEmbedder()
    return _default_embedder


def reset_embedder() -> None:
    """配置变更或测试后重置 Embedder 单例。"""
    global _default_embedder
    _default_embedder = None


def is_embedding_available() -> bool:
    """当前是否可用向量检索（已配置 Key 且启用）。"""
    from core.rag.settings import get_embedding_manager

    return get_embedding_manager().is_configured()
