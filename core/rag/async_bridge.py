"""在同步调用链中安全执行协程（含已有事件循环场景）。"""

from __future__ import annotations

import asyncio
import concurrent.futures
from typing import Any, Coroutine, TypeVar

T = TypeVar("T")


def run_coro_sync(coro: Coroutine[Any, Any, T]) -> T:
    """无运行中循环时用 asyncio.run；否则在独立线程中 asyncio.run。

    FastAPI / ReAct 的 sync handler 会在已有事件循环内调用 RAG 同步包装，
    此时不能再 asyncio.run，否则抛 RuntimeError；放到独立线程可安全跑完协程。
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()
