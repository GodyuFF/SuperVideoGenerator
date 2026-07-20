"""StreamDeltaBatcher 单元测试。"""

import asyncio

import pytest

from core.llm.client.stream_delta_batcher import StreamDeltaBatcher, make_batched_delta_handler


@pytest.mark.asyncio
async def test_stream_delta_batcher_merges_deltas():
    """多次 feed 应合并为单次 emit。"""
    emitted: list[str] = []

    async def emit(payload: str) -> None:
        emitted.append(payload)

    batcher = StreamDeltaBatcher(emit, flush_interval_sec=0.05, max_chars=1000)
    await batcher.feed("a")
    await batcher.feed("b")
    await batcher.drain()
    await asyncio.sleep(0.05)
    assert "".join(emitted) == "ab"


@pytest.mark.asyncio
async def test_make_batched_delta_handler_drain():
    """make_batched_delta_handler 返回的 drain 应刷出剩余缓冲。"""
    chunks: list[str] = []

    async def emit(payload: str) -> None:
        chunks.append(payload)

    on_delta, drain = make_batched_delta_handler(emit, flush_interval_sec=1.0, max_chars=64)
    await on_delta("hello")
    await drain()
    await asyncio.sleep(0.05)
    assert chunks == ["hello"]
