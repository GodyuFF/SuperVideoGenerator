"""交互日志异步批量写入：后台线程落盘，避免阻塞 asyncio 事件循环。"""

from __future__ import annotations

import queue
import threading
import time
from typing import TYPE_CHECKING

from core.interaction_log.models import InteractionRecord

if TYPE_CHECKING:
    from core.interaction_log.file_store import InteractionFileStore
    from core.interaction_log.store import InteractionLogStore

_BATCH_SIZE = 32
_FLUSH_INTERVAL_SEC = 0.05
_SENTINEL = object()
_FLUSH_MARKER = object()


class InteractionLogWriter:
    """将 InteractionRecord 入队，由守护线程批量写入 SQLite 与 JSONL。"""

    def __init__(
        self,
        store: InteractionLogStore,
        file_store: InteractionFileStore | None = None,
    ) -> None:
        self._store = store
        self._file_store = file_store
        self._queue: queue.Queue = queue.Queue()
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._worker_loop,
            name="interaction-log-writer",
            daemon=True,
        )
        self._thread.start()

    def enqueue(self, record: InteractionRecord) -> None:
        """非阻塞入队；主线程与协程均可调用。"""
        if self._stop.is_set():
            self._flush_batch([record])
            return
        self._queue.put(record)

    def flush(self, timeout: float = 5.0) -> None:
        """等待队列清空并完成落盘（测试与 shutdown 用）。"""
        done = threading.Event()
        self._queue.put((_FLUSH_MARKER, done))
        if not done.wait(timeout):
            raise TimeoutError("InteractionLogWriter flush 超时")

    def shutdown(self, timeout: float = 10.0) -> None:
        """停止 worker 并刷完剩余记录。"""
        self._stop.set()
        self._queue.put(_SENTINEL)
        self._thread.join(timeout=timeout)

    def _worker_loop(self) -> None:
        """批量 drain 队列并写入存储。"""
        batch: list[InteractionRecord] = []
        last_flush = time.monotonic()
        while True:
            timeout = max(
                0.0,
                _FLUSH_INTERVAL_SEC - (time.monotonic() - last_flush),
            )
            try:
                item = self._queue.get(timeout=timeout if batch else None)
            except queue.Empty:
                item = None

            if item is _SENTINEL:
                if batch:
                    self._flush_batch(batch)
                return

            if isinstance(item, tuple) and len(item) == 2 and item[0] is _FLUSH_MARKER:
                if batch:
                    self._flush_batch(batch)
                    batch = []
                    last_flush = time.monotonic()
                item[1].set()
                continue

            if isinstance(item, InteractionRecord):
                batch.append(item)

            should_flush = (
                len(batch) >= _BATCH_SIZE
                or (batch and time.monotonic() - last_flush >= _FLUSH_INTERVAL_SEC)
            )
            if should_flush and batch:
                self._flush_batch(batch)
                batch = []
                last_flush = time.monotonic()

    def _flush_batch(self, records: list[InteractionRecord]) -> None:
        """单事务批量写入 SQLite，并追加 JSONL。"""
        if not records:
            return
        self._store.append_many(records)
        if self._file_store:
            for rec in records:
                self._file_store.append(rec)


_WRITER: InteractionLogWriter | None = None


def configure_interaction_log_writer(
    store: InteractionLogStore,
    file_store: InteractionFileStore | None = None,
) -> InteractionLogWriter:
    """初始化全局 InteractionLogWriter（AppState 启动时调用）。"""
    global _WRITER
    if _WRITER is not None:
        _WRITER.shutdown()
    _WRITER = InteractionLogWriter(store, file_store)
    return _WRITER


def get_interaction_log_writer() -> InteractionLogWriter | None:
    """获取已配置的全局 writer；未配置时返回 None。"""
    return _WRITER


def reset_interaction_log_writer() -> None:
    """测试用：关闭并清空全局 writer。"""
    global _WRITER
    if _WRITER is not None:
        _WRITER.shutdown()
        _WRITER = None
