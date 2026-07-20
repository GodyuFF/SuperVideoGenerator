"""
对话消息 SQLite 异步批量写入队列。
"""

from __future__ import annotations

import asyncio
import threading
from typing import TYPE_CHECKING

from core.logging.perf import log_perf

if TYPE_CHECKING:
    from core.conversation.sqlite_store import ConversationSqliteStore
    from core.conversation.store import ConversationMessage


class ConversationWriteQueue:
    """将对话消息写入排队，批量落盘以降低 ReAct 热路径阻塞。"""

    def __init__(
        self,
        sqlite: ConversationSqliteStore,
        *,
        batch_size: int = 10,
    ) -> None:
        self._sqlite = sqlite
        self._batch_size = batch_size
        self._queue: list[ConversationMessage] = []
        self._lock = threading.Lock()
        self._flush_task: asyncio.Task[None] | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._closed = False

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """绑定事件循环以启用定时 flush 后台任务。"""
        self._loop = loop
        if self._flush_task is None or self._flush_task.done():
            self._flush_task = loop.create_task(self._periodic_flush())

    def enqueue(self, msg: ConversationMessage) -> None:
        """将消息加入写入队列（同步入口，供 ConversationStore 调用）。"""
        if self._closed:
            self._sqlite.append_message(msg)
            return
        with self._lock:
            self._queue.append(msg)
            should_flush = len(self._queue) >= self._batch_size
        if should_flush:
            self._schedule_flush()

    def _schedule_flush(self) -> None:
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self.flush(), self._loop)
        else:
            self._flush_sync()

    async def _periodic_flush(self) -> None:
        while not self._closed:
            await asyncio.sleep(0.2)
            await self.flush()

    def _flush_sync(self) -> None:
        with self._lock:
            if not self._queue:
                return
            batch = self._queue[:]
            self._queue.clear()
        self._sqlite.append_messages_batch(batch)
        log_perf("conv.write_queue", "flush_batch", batch_size=len(batch))

    async def flush(self) -> None:
        """将队列中的消息批量写入 SQLite。"""
        await asyncio.to_thread(self._flush_sync)

    async def drain(self) -> None:
        """刷出全部待写消息并停止后台调度。"""
        self._closed = True
        if self._flush_task and not self._flush_task.done():
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
        await self.flush()
