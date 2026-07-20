"""plan_updated 轻量推送单元测试。"""

from unittest.mock import MagicMock

import pytest

from core.conversation import ConversationStore
from core.events.emitter import EventEmitter
from core.llm.client.settings import LLMConfigManager
from core.llm.master.master_react import MasterReActEngine
from core.models.entities import PlanDocument
from core.store.memory import MemoryStore


@pytest.mark.asyncio
async def test_emit_plan_updated_lightweight_payload():
    """plan_updated 默认不带全量 plan.steps。"""
    store = MemoryStore()
    emitter = EventEmitter()
    events: list[dict] = []

    async def capture(event: dict) -> None:
        events.append(event)

    emitter.subscribe(capture)
    engine = MasterReActEngine(
        store=store,
        emitter=emitter,
        registry=MagicMock(),
        conversations=ConversationStore(),
        confirmation=MagicMock(),
        llm_config=LLMConfigManager(),
        llm_client=MagicMock(),
    )
    plan = PlanDocument(goal="test", version=3, runtime_summary="进行中")
    session = type("S", (), {"plan_status_history": ["a"], "last_remaining_plan": ["b"]})()

    await engine._emit_plan_updated("script-1", "conv-1", plan, session)

    assert len(events) == 1
    payload = events[0]
    assert payload["type"] == "plan_updated"
    assert "plan" not in payload
    assert payload["runtime_summary"] == "进行中"
    assert payload["version"] == 3
    assert payload["plan_status_history"] == ["a"]
