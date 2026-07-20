"""Provider 降级链：主 Provider 失败时切换备选。"""

from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


def is_retryable_provider_error(exc: Exception) -> bool:
    """判断异常是否适合触发 Provider fallback（429 / 5xx）。"""
    status = getattr(exc, "http_status", None)
    if isinstance(status, int) and status in {429, 500, 502, 503, 504}:
        return True
    message = str(exc).lower()
    return any(token in message for token in ("429", "502", "503", "504", "rate limit", "too many requests"))


def build_fallback_settings(
    settings: T,
    *,
    fallback_provider: str,
    fallback_model: str = "",
) -> T | None:
    """复制 settings 并切换为 fallback provider（无效 provider 返回 None）。"""
    provider = (fallback_provider or "").strip().lower()
    if not provider:
        return None
    copy = settings.model_copy(deep=True)
    copy.provider = provider  # type: ignore[attr-defined]
    model = (fallback_model or "").strip()
    if model:
        copy.model = model  # type: ignore[attr-defined]
    return copy
