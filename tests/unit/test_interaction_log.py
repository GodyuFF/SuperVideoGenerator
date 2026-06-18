"""交互日志持久化测试。"""

import pytest

from core.events.emitter import EventEmitter
from core.interaction_log.file_store import InteractionFileStore
from core.interaction_log.models import InteractionRecord
from core.interaction_log.recorder import InteractionRecorder
from core.interaction_log.store import InteractionLogStore
from core.interaction_log.redact import redact_for_log


@pytest.fixture
def log_store(tmp_path):
    db = tmp_path / "test_logs.db"
    return InteractionLogStore(db)


@pytest.fixture
def file_store(tmp_path):
    return InteractionFileStore(tmp_path / "interactions")


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
async def test_recorder_agent_action(log_store):
    emitter = EventEmitter()
    recorder = InteractionRecorder(log_store, emitter)
    await recorder.record_agent_action(
        script_id="s1",
        agent_name="script_agent",
        step_id="step1",
        action="parse_brief",
        observation="已解析",
    )
    rows = log_store.list_records(script_id="s1", kind="agent_action")
    assert len(rows) == 1
    assert rows[0].source == "agent"


def test_file_store_append_and_read_tail(file_store):
    rec = InteractionRecord(
        kind="llm_request",
        source="llm",
        script_id="s1",
        summary="hello",
        request_body={"model": "gpt-4"},
        created_at="2026-06-17T10:00:00Z",
    )
    file_store.append(rec)
    files = file_store.list_log_files()
    assert len(files) == 1
    assert files[0]["date"] == "2026-06-17"
    assert files[0]["size_bytes"] > 0

    rows = file_store.read_tail(date="2026-06-17", limit=10)
    assert len(rows) == 1
    assert rows[0].kind == "llm_request"
    assert rows[0].request_body == {"model": "gpt-4"}


@pytest.mark.asyncio
async def test_recorder_dual_write_sqlite_and_jsonl(log_store, file_store):
    recorder = InteractionRecorder(log_store, file_store=file_store)
    await recorder.record(
        InteractionRecord(
            kind="llm_response",
            source="llm",
            script_id="dual_s1",
            summary="dual write",
            response_body={"content": "ok"},
            created_at="2026-06-17T12:00:00Z",
        )
    )
    sqlite_rows = log_store.list_records(script_id="dual_s1")
    assert len(sqlite_rows) == 1
    jsonl_rows = file_store.read_tail(date="2026-06-17", limit=10)
    assert len(jsonl_rows) == 1
    assert jsonl_rows[0].summary == "dual write"


def test_redact_api_key():
    data = {"api_key": "sk-secret123456", "model": "gpt-4"}
    out = redact_for_log(data)
    assert out["api_key"] == "***"
    assert out["model"] == "gpt-4"
