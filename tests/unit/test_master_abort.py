"""主编排中止：慢任务 + request_cancel 应快速抛出 ExecutionCancelledError。"""

import asyncio

import pytest

from core.execution.cancel import (
    ExecutionCancelledError,
    get_execution_cancel_registry,
    wait_or_cancel,
)


@pytest.mark.asyncio
async def test_delegate_like_task_aborts_before_completion():
    """模拟子 Agent 委派：取消后不应等待慢任务跑完。"""
    reg = get_execution_cancel_registry()
    reg.clear("script_abort")
    reg.register("script_abort", "conv_1")

    async def slow_delegate() -> list[str]:
        await asyncio.sleep(10)
        return ["done"]

    async def request_abort_after_delay() -> None:
        await asyncio.sleep(0.08)
        reg.request_cancel("script_abort")

    cancel_task = asyncio.create_task(request_abort_after_delay())
    started = asyncio.get_event_loop().time()
    try:
        with pytest.raises(ExecutionCancelledError):
            await wait_or_cancel("script_abort", slow_delegate(), poll_sec=0.05)
    finally:
        await cancel_task
        reg.clear("script_abort")

    elapsed = asyncio.get_event_loop().time() - started
    assert elapsed < 2.0
