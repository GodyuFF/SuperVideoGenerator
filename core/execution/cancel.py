"""主编排执行取消注册表（按 script_id）。"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Awaitable, Callable, Sequence
from typing import TypeVar

T = TypeVar("T")


class ExecutionCancelledError(Exception):
    """用户通过 API 请求中止当前剧本的主编排执行。"""


class ExecutionCancelRegistry:
    """进程内单例：标记用户请求中止的 script_id。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cancelled: set[str] = set()
        self._active: dict[str, str] = {}  # script_id -> conversation_id

    def register(self, script_id: str, conversation_id: str) -> None:
        with self._lock:
            self._cancelled.discard(script_id)
            self._active[script_id] = conversation_id

    def request_cancel(self, script_id: str) -> bool:
        with self._lock:
            if script_id not in self._active:
                return False
            self._cancelled.add(script_id)
            return True

    def is_cancelled(self, script_id: str) -> bool:
        with self._lock:
            return script_id in self._cancelled

    def is_active(self, script_id: str) -> bool:
        with self._lock:
            return script_id in self._active

    def conversation_id(self, script_id: str) -> str | None:
        with self._lock:
            return self._active.get(script_id)

    def clear(self, script_id: str) -> None:
        with self._lock:
            self._cancelled.discard(script_id)
            self._active.pop(script_id, None)


_registry = ExecutionCancelRegistry()


def get_execution_cancel_registry() -> ExecutionCancelRegistry:
    return _registry


def check_cancelled(script_id: str) -> None:
    """若 script 已请求中止则抛出 ExecutionCancelledError。"""
    if get_execution_cancel_registry().is_cancelled(script_id):
        raise ExecutionCancelledError()


def make_abort_checker(script_id: str) -> Callable[[], bool]:
    registry = get_execution_cancel_registry()
    return lambda: registry.is_cancelled(script_id)


async def wait_or_cancel(
    script_id: str,
    coro: Awaitable[T],
    *,
    poll_sec: float = 0.3,
) -> T:
    """包装长 await：轮询取消标记，触发时 cancel 子 task 并抛 ExecutionCancelledError。"""
    check_cancelled(script_id)
    task = asyncio.create_task(coro)
    try:
        while not task.done():
            if get_execution_cancel_registry().is_cancelled(script_id):
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                raise ExecutionCancelledError()
            await asyncio.wait({task}, timeout=poll_sec)
        return task.result()
    except asyncio.CancelledError:
        raise ExecutionCancelledError() from None


async def gather_with_cancel(
    script_id: str,
    coros: Sequence[Awaitable[T]],
    *,
    poll_sec: float = 0.3,
) -> list[T]:
    """类似 gather，但在取消请求时 cancel 未完成任务并抛出 ExecutionCancelledError。"""
    if not coros:
        return []
    tasks = [asyncio.create_task(c) for c in coros]
    results: list[T | None] = [None] * len(tasks)
    pending: dict[int, asyncio.Task[T]] = dict(enumerate(tasks))
    try:
        while pending:
            check_cancelled(script_id)
            done, _ = await asyncio.wait(
                set(pending.values()),
                timeout=poll_sec,
                return_when=asyncio.FIRST_COMPLETED,
            )
            for finished in done:
                idx = next(i for i, t in pending.items() if t is finished)
                results[idx] = finished.result()
                del pending[idx]
        return list(results)  # type: ignore[return-value]
    except ExecutionCancelledError:
        for t in pending.values():
            t.cancel()
        if pending:
            await asyncio.gather(*pending.values(), return_exceptions=True)
        raise
