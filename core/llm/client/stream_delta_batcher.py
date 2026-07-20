"""
LLM 流式 delta 批量合并发射，降低 WebSocket 背压。
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Awaitable, Callable


class StreamDeltaBatcher:
    """缓冲 LLM delta 并按时间/长度阈值批量 flush。"""

    def __init__(
        self,
        emit: Callable[[str], Awaitable[None]],
        *,
        flush_interval_sec: float = 0.032,
        max_chars: int = 256,
    ) -> None:
        self._emit = emit
        self._flush_interval_sec = flush_interval_sec
        self._max_chars = max_chars
        self._buffer = ""
        self._last_flush = time.monotonic()
        self._lock = asyncio.Lock()
        self._flush_task: asyncio.Task[None] | None = None

    async def feed(self, delta: str) -> None:
        """追加 delta 片段，必要时调度 flush。"""
        if not delta:
            return
        async with self._lock:
            self._buffer += delta
            now = time.monotonic()
            should_flush = (
                len(self._buffer) >= self._max_chars
                or now - self._last_flush >= self._flush_interval_sec
            )
            if should_flush:
                await self._flush_locked()
            elif self._flush_task is None or self._flush_task.done():
                self._flush_task = asyncio.create_task(self._delayed_flush())

    async def _delayed_flush(self) -> None:
        await asyncio.sleep(self._flush_interval_sec)
        async with self._lock:
            if self._buffer:
                await self._flush_locked()

    async def _flush_locked(self) -> None:
        if not self._buffer:
            return
        payload = self._buffer
        self._buffer = ""
        self._last_flush = time.monotonic()
        asyncio.create_task(self._emit(payload))

    async def drain(self) -> None:
        """刷出剩余缓冲（流结束时调用）。"""
        async with self._lock:
            if self._flush_task and not self._flush_task.done():
                self._flush_task.cancel()
                try:
                    await self._flush_task
                except asyncio.CancelledError:
                    pass
                self._flush_task = None
            if self._buffer:
                await self._flush_locked()


def make_batched_delta_handler(
    emit_delta: Callable[[str], Awaitable[None]],
    **kwargs: Any,
) -> tuple[Callable[[str], Awaitable[None]], Callable[[], Awaitable[None]]]:
    """
    创建批量 delta 处理器与 drain 回调。

    返回 (on_delta, drain) 供 LLM 流式调用链使用。
    """
    batcher = StreamDeltaBatcher(emit_delta, **kwargs)

    async def on_delta(delta: str) -> None:
        await batcher.feed(delta)

    async def drain() -> None:
        await batcher.drain()

    return on_delta, drain
