"""性能观测日志：统一 [PERF:类别] 格式，便于 grep 与指标采集。"""

from __future__ import annotations

import os
import time
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from typing import Any

from core.logging.setup import get_logger

PERF_PREFIX = "[PERF"
_DEFAULT_LOGGER = get_logger("core.perf")

_PERF_OFF_VALUES = frozenset({"0", "false", "no", "off"})


def perf_enabled() -> bool:
    """是否输出性能日志（默认开启，设 SVG_PERF_LOG=0 关闭）。"""
    return os.getenv("SVG_PERF_LOG", "1").strip().lower() not in _PERF_OFF_VALUES


def api_slow_threshold_ms() -> float:
    """API 慢请求告警阈值（毫秒）。"""
    return float(os.getenv("SVG_PERF_API_SLOW_MS", "500"))


def llm_slow_threshold_ms() -> float:
    """LLM 慢调用告警阈值（毫秒）。"""
    return float(os.getenv("SVG_PERF_LLM_SLOW_MS", "3000"))


def _format_fields(duration_ms: float | None, fields: dict[str, Any]) -> str:
    """拼接 duration 与附加字段为日志后缀。"""
    parts: list[str] = []
    if duration_ms is not None:
        parts.append(f"duration_ms={duration_ms:.1f}")
    for key, value in fields.items():
        if value is None:
            continue
        parts.append(f"{key}={value}")
    return f" {' '.join(parts)}" if parts else ""


def log_perf(
    category: str,
    message: str,
    *,
    duration_ms: float | None = None,
    level: str = "info",
    logger: Any | None = None,
    **fields: Any,
) -> None:
    """输出带 [PERF:类别] 前缀的结构化性能日志。"""
    if not perf_enabled():
        return
    log = logger or _DEFAULT_LOGGER
    suffix = _format_fields(duration_ms, fields)
    text = f"{PERF_PREFIX}:{category}] {message}{suffix}"
    log_fn = getattr(log, level, log.info)
    log_fn(text)


class PerfSpan:
    """同步计时 span，退出时自动写入 perf 日志。"""

    def __init__(
        self,
        category: str,
        message: str,
        *,
        logger: Any | None = None,
        log_level: str = "info",
        **fields: Any,
    ) -> None:
        self._category = category
        self._message = message
        self._logger = logger
        self._log_level = log_level
        self._fields = fields
        self._start = 0.0

    def __enter__(self) -> PerfSpan:
        self._start = time.perf_counter()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        duration_ms = (time.perf_counter() - self._start) * 1000
        level = "warning" if exc is not None else self._log_level
        fields = dict(self._fields)
        if exc is not None:
            fields["error"] = type(exc).__name__
        log_perf(
            self._category,
            self._message,
            duration_ms=duration_ms,
            level=level,
            logger=self._logger,
            **fields,
        )
        return False


class AsyncPerfSpan:
    """异步计时 span，退出时自动写入 perf 日志。"""

    def __init__(
        self,
        category: str,
        message: str,
        *,
        logger: Any | None = None,
        log_level: str = "info",
        **fields: Any,
    ) -> None:
        self._category = category
        self._message = message
        self._logger = logger
        self._log_level = log_level
        self._fields = fields
        self._start = 0.0

    async def __aenter__(self) -> AsyncPerfSpan:
        self._start = time.perf_counter()
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        duration_ms = (time.perf_counter() - self._start) * 1000
        level = "warning" if exc is not None else self._log_level
        fields = dict(self._fields)
        if exc is not None:
            fields["error"] = type(exc).__name__
        log_perf(
            self._category,
            self._message,
            duration_ms=duration_ms,
            level=level,
            logger=self._logger,
            **fields,
        )
        return False


@contextmanager
def perf_span(
    category: str,
    message: str,
    *,
    logger: Any | None = None,
    log_level: str = "info",
    **fields: Any,
) -> Iterator[PerfSpan]:
    """同步 perf 计时上下文。"""
    with PerfSpan(
        category,
        message,
        logger=logger,
        log_level=log_level,
        **fields,
    ) as span:
        yield span


@asynccontextmanager
async def async_perf_span(
    category: str,
    message: str,
    *,
    logger: Any | None = None,
    log_level: str = "info",
    **fields: Any,
) -> AsyncIterator[AsyncPerfSpan]:
    """异步 perf 计时上下文。"""
    async with AsyncPerfSpan(
        category,
        message,
        logger=logger,
        log_level=log_level,
        **fields,
    ) as span:
        yield span
