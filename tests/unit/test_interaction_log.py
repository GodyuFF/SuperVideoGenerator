"""交互日志持久化测试。"""

import pytest

from core.events.emitter import EventEmitter
from core.interaction_log.models import InteractionRecord
from core.interaction_log.recorder import InteractionRecorder
from core.interaction_log.store import InteractionLogStore
from core.interaction_log.redact import redact_for_log


@pytest.fixture
def log_store(tmp_path):
    db = tmp_path / "test_logs.db"
    return InteractionLogStore(db)


@pytest.mark.asyncio
async def test_append_and_list(log_store):
    store = log_store
    rec = store.append(
        InteractionRecord(
            kind="llm_response",
            source="llm",
            script_id="script_test",
            summary="test",
        )
    )
    rows = store.list_records(script_id="script_test")
    assert len(rows) >= 1
    assert rows[0].id == rec.id


@pytest.mark.asyncio
async def test_recorder_emits_event(log_store):
    emitter = EventEmitter()
    events = []

    async def capture(e):
        events.append(e)

    emitter.subscribe(capture)
    recorder = InteractionRecorder(log_store, emitter)
    await recorder.record_rule_fallback(
        script_id="s1",
        agent_name="test_agent",
        reason="no key",
    )
    assert len(events) == 1
    assert events[0]["type"] == "interaction_log"


def test_redact_api_key():
    data = {"api_key": "sk-secret123456", "model": "gpt-4"}
    out = redact_for_log(data)
    assert out["api_key"] == "***"
    assert out["model"] == "gpt-4"
