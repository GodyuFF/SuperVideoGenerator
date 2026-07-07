"""执行取消注册表单元测试。"""

import asyncio

import pytest

from core.execution.cancel import (
    ExecutionCancelRegistry,
    ExecutionCancelledError,
    check_cancelled,
    gather_with_cancel,
    get_execution_cancel_registry,
    wait_or_cancel,
)


def test_register_and_cancel():
    reg = ExecutionCancelRegistry()
    reg.register("script_1", "conv_1")
    assert reg.is_active("script_1")
    assert not reg.is_cancelled("script_1")
    assert reg.request_cancel("script_1")
    assert reg.is_cancelled("script_1")
    reg.clear("script_1")
    assert not reg.is_active("script_1")
    assert not reg.request_cancel("script_1")


def test_request_cancel_inactive_returns_false():
    reg = ExecutionCancelRegistry()
    assert reg.request_cancel("missing") is False


def test_check_cancelled_raises():
    reg = get_execution_cancel_registry()
    reg.clear("s1")
    reg.register("s1", "c1")
    check_cancelled("s1")
    reg.request_cancel("s1")
    with pytest.raises(ExecutionCancelledError):
        check_cancelled("s1")
    reg.clear("s1")


@pytest.mark.asyncio
async def test_wait_or_cancel_completes_normally():
    reg = get_execution_cancel_registry()
    reg.clear("s1")
    reg.register("s1", "c1")

    async def quick() -> str:
        return "ok"

    assert await wait_or_cancel("s1", quick()) == "ok"
    reg.clear("s1")


@pytest.mark.asyncio
async def test_wait_or_cancel_aborts_slow_task():
    reg = get_execution_cancel_registry()
    reg.clear("s1")
    reg.register("s1", "c1")

    async def slow() -> str:
        await asyncio.sleep(5)
        return "late"

    async def cancel_soon() -> None:
        await asyncio.sleep(0.05)
        reg.request_cancel("s1")

    cancel_task = asyncio.create_task(cancel_soon())
    try:
        with pytest.raises(ExecutionCancelledError):
            await wait_or_cancel("s1", slow(), poll_sec=0.05)
    finally:
        await cancel_task
        reg.clear("s1")


@pytest.mark.asyncio
async def test_gather_with_cancel_stops_on_request():
    reg = get_execution_cancel_registry()
    reg.clear("s1")
    reg.register("s1", "c1")

    async def item(n: int) -> int:
        await asyncio.sleep(0.2 * n)
        return n

    async def cancel_mid() -> None:
        await asyncio.sleep(0.15)
        reg.request_cancel("s1")

    cancel_task = asyncio.create_task(cancel_mid())
    try:
        with pytest.raises(ExecutionCancelledError):
            await gather_with_cancel(
                "s1",
                [item(1), item(2), item(3)],
                poll_sec=0.05,
            )
    finally:
        await cancel_task
        reg.clear("s1")
