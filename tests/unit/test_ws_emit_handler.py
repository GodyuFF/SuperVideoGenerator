"""WebSocket 事件路由单元测试：带 script_id 的事件不得泄漏到其他剧本频道。"""

from unittest.mock import AsyncMock

import pytest

from apps.api.state import _ws_emit_handler, state


@pytest.fixture
def isolated_ws_clients():
    """隔离 ws_clients，避免污染全局 AppState。"""
    original = dict(state.ws_clients)
    state.ws_clients.clear()
    yield
    state.ws_clients.clear()
    state.ws_clients.update(original)


@pytest.mark.asyncio
async def test_script_scoped_event_only_targets_matching_channel(isolated_ws_clients):
    """带 script_id 的流式事件只推送到对应剧本频道。"""
    ws_script_a = AsyncMock()
    ws_script_b = AsyncMock()
    state.ws_clients["proj1:script_a"] = [ws_script_a]
    state.ws_clients["proj1:script_b"] = [ws_script_b]

    event = {
        "type": "llm_stream_delta",
        "script_id": "script_a",
        "delta": "hello",
    }
    await _ws_emit_handler(event)

    ws_script_a.send_json.assert_awaited_once_with(event)
    ws_script_b.send_json.assert_not_awaited()


@pytest.mark.asyncio
async def test_script_scoped_event_not_broadcast_globally(isolated_ws_clients):
    """带 script_id 的事件即使类型在 global_broadcast_types 中也不全量广播。"""
    ws_other = AsyncMock()
    state.ws_clients["proj2:other_script"] = [ws_other]

    event = {
        "type": "llm_stream_delta",
        "script_id": "target_script",
        "delta": "x",
    }
    await _ws_emit_handler(event)

    ws_other.send_json.assert_not_awaited()


@pytest.mark.asyncio
async def test_global_event_without_script_id_broadcasts_to_all(isolated_ws_clients):
    """无 script_id 的全局事件广播到全部连接。"""
    ws_a = AsyncMock()
    ws_b = AsyncMock()
    state.ws_clients["p1:s1"] = [ws_a]
    state.ws_clients["p2:s2"] = [ws_b]

    event = {"type": "llm_stream_delta", "delta": "global"}
    await _ws_emit_handler(event)

    ws_a.send_json.assert_awaited_once_with(event)
    ws_b.send_json.assert_awaited_once_with(event)


@pytest.mark.asyncio
async def test_a2ui_event_broadcasts_without_script_id(isolated_ws_clients):
    """A2UI 确认类事件在无 script_id 时仍全量广播。"""
    ws = AsyncMock()
    state.ws_clients["p:s"] = [ws]

    event = {"type": "a2ui_confirmation_required", "confirmation_id": "c1"}
    await _ws_emit_handler(event)

    ws.send_json.assert_awaited_once_with(event)
