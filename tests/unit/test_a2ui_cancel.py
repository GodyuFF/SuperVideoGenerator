"""A2UI 确认批量取消测试。"""

import asyncio

import pytest

from core.events.emitter import EventEmitter
from core.llm.a2ui.manager import ConfirmationManager
from core.llm.a2ui.schemas import A2UIConfirmationResponse


@pytest.mark.asyncio
async def test_cancel_all_pending_resolves_futures():
    emitter = EventEmitter()
    mgr = ConfirmationManager(emitter, default_timeout=None)

    async def wait_one():
        loop = asyncio.get_event_loop()
        future = loop.create_future()
        mgr._pending["conf_1"] = future
        return await future

    task = asyncio.create_task(wait_one())
    await asyncio.sleep(0.01)
    count = mgr.cancel_all_pending()
    assert count == 1
    response = await task
    assert response.approved is False
    assert response.values.get("intent") == "abort"
