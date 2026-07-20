"""交互日志持久化测试。"""

from datetime import datetime, timedelta, timezone

import pytest

from core.events.emitter import EventEmitter
from core.interaction_log.async_writer import (
    InteractionLogWriter,
    configure_interaction_log_writer,
    reset_interaction_log_writer,
)
from core.interaction_log.file_store import InteractionFileStore
from core.interaction_log.maintenance import run_startup_retention
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


@pytest.fixture
def async_writer(log_store, file_store):
    """配置全局 InteractionLogWriter，测试结束重置。"""
    configure_interaction_log_writer(log_store, file_store)
    yield
    reset_interaction_log_writer()


@pytest.fixture
def recorder_with_writer(log_store, file_store, async_writer):
    """带异步 writer 的 InteractionRecorder。"""
    return InteractionRecorder(log_store, file_store=file_store)


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
async def test_recorder_agent_action(recorder_with_writer, log_store):
    recorder = recorder_with_writer
    await recorder.record_agent_action(
        script_id="s1",
        agent_name="script_agent",
        step_id="step1",
        action="parse_brief",
        observation="已解析",
    )
    await recorder.flush()
    rows = log_store.list_records(script_id="s1", kind="agent_action")
    assert len(rows) == 1
    assert rows[0].source == "agent"


def test_file_store_append_and_read_tail(file_store):
    rec = InteractionRecord(
        kind="llm_request",
        source="llm",
        project_id="proj_1",
        script_id="s1",
        summary="hello",
        request_body={"model": "gpt-4"},
        created_at="2026-06-17T10:00:00Z",
    )
    file_store.append(rec)
    files = file_store.list_log_files(project_id="proj_1")
    assert len(files) == 1
    assert files[0]["date"] == "2026-06-17"
    assert files[0]["project_id"] == "proj_1"
    assert files[0]["size_bytes"] > 0

    rows = file_store.read_tail(
        date="2026-06-17", limit=10, project_id="proj_1"
    )
    assert len(rows) == 1
    assert rows[0].kind == "llm_request"
    assert rows[0].request_body == {"model": "gpt-4"}


@pytest.mark.asyncio
async def test_recorder_dual_write_sqlite_and_jsonl(recorder_with_writer, log_store, file_store):
    recorder = recorder_with_writer
    await recorder.record(
        InteractionRecord(
            kind="llm_response",
            source="llm",
            project_id="proj_dual",
            script_id="dual_s1",
            summary="dual write",
            response_body={"content": "ok"},
            created_at="2026-06-17T12:00:00Z",
        )
    )
    await recorder.flush()
    sqlite_rows = log_store.list_records(script_id="dual_s1")
    assert len(sqlite_rows) == 1
    jsonl_rows = file_store.read_tail(
        date="2026-06-17", limit=10, project_id="proj_dual"
    )
    assert len(jsonl_rows) == 1
    assert jsonl_rows[0].summary == "dual write"


def test_clear_all_removes_records(log_store):
    log_store.append(
        InteractionRecord(kind="llm_response", source="llm", script_id="s1", summary="a")
    )
    assert log_store.list_records()
    log_store.clear_all()
    assert log_store.list_records() == []
    assert log_store.count_llm_calls() == 0


def test_delete_records_by_project_and_date(log_store):
    log_store.append(
        InteractionRecord(
            kind="llm_response",
            source="llm",
            project_id="proj_a",
            script_id="s1",
            summary="day1",
            created_at="2026-06-17T10:00:00Z",
        )
    )
    log_store.append(
        InteractionRecord(
            kind="llm_response",
            source="llm",
            project_id="proj_a",
            script_id="s1",
            summary="day2",
            created_at="2026-06-18T10:00:00Z",
        )
    )
    deleted = log_store.delete_records(project_id="proj_a", date="2026-06-17")
    assert deleted == 1
    rows = log_store.list_records(project_id="proj_a")
    assert len(rows) == 1
    assert rows[0].summary == "day2"


def test_file_store_delete_log_file(file_store):
    rec = InteractionRecord(
        kind="llm_request",
        source="llm",
        project_id="proj_del",
        summary="x",
        created_at="2026-06-17T08:00:00Z",
    )
    file_store.append(rec)
    assert file_store.list_log_files(project_id="proj_del")
    assert file_store.delete_log_file("proj_del", "2026-06-17") is True
    assert file_store.list_log_files(project_id="proj_del") == []


@pytest.mark.asyncio
async def test_api_delete_interaction_logs(monkeypatch, tmp_path):
    from httpx import ASGITransport, AsyncClient

    from apps.api.main import app
    from apps.api import state as api_state

    db_path = tmp_path / "interaction_logs.db"
    log_dir = tmp_path / "interactions"
    api_state.state.interaction_log_store = InteractionLogStore(db_path)
    api_state.state.interaction_file_store = InteractionFileStore(log_dir)
    configure_interaction_log_writer(
        api_state.state.interaction_log_store,
        api_state.state.interaction_file_store,
    )

    api_state.state.interaction_log_store.append(
        InteractionRecord(
            kind="llm_response",
            source="llm",
            project_id="proj_api",
            script_id="scr1",
            summary="keep",
            created_at="2026-06-18T01:00:00Z",
        )
    )
    api_state.state.interaction_log_store.append(
        InteractionRecord(
            kind="llm_response",
            source="llm",
            project_id="proj_api",
            script_id="scr1",
            summary="remove",
            created_at="2026-06-17T01:00:00Z",
        )
    )
    api_state.state.interaction_file_store.append(
        InteractionRecord(
            kind="llm_request",
            source="llm",
            project_id="proj_api",
            summary="jsonl",
            created_at="2026-06-17T02:00:00Z",
        )
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.delete(
            "/api/interactions",
            params={"project_id": "proj_api", "date": "2026-06-17"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["sqlite_deleted"] == 1
        assert body["jsonl_deleted"] is True

        rows = api_state.state.interaction_log_store.list_records(project_id="proj_api")
        assert len(rows) == 1
        assert rows[0].summary == "keep"
        assert (
            api_state.state.interaction_file_store.list_log_files(
                project_id="proj_api"
            )
            == []
        )
    reset_interaction_log_writer()


def test_append_many(log_store):
    """批量插入多条记录。"""
    records = [
        InteractionRecord(
            kind="api_request",
            source="http",
            script_id="s_batch",
            summary=f"req-{i}",
        )
        for i in range(5)
    ]
    log_store.append_many(records)
    rows = log_store.list_records(script_id="s_batch", limit=10)
    assert len(rows) == 5


def test_delete_older_than(log_store):
    """按天数删除指定 kind。"""
    old = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
    recent = datetime.now(timezone.utc).isoformat()
    log_store.append(
        InteractionRecord(
            kind="api_request",
            source="http",
            summary="old",
            created_at=old,
        )
    )
    log_store.append(
        InteractionRecord(
            kind="agent_action",
            source="agent",
            script_id="s1",
            summary="old agent",
            created_at=old,
        )
    )
    log_store.append(
        InteractionRecord(
            kind="api_request",
            source="http",
            summary="new",
            created_at=recent,
        )
    )
    deleted = log_store.delete_older_than(30, kinds=("api_request",))
    assert deleted == 1
    rows = log_store.list_records(limit=10)
    assert len(rows) == 2
    kinds = {r.kind for r in rows}
    assert "agent_action" in kinds


def test_run_startup_retention(log_store):
    """启动 retention 仅清理 api_request。"""
    old = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
    log_store.append(
        InteractionRecord(
            kind="api_request",
            source="http",
            summary="stale",
            created_at=old,
        )
    )
    deleted = run_startup_retention(log_store, days=30)
    assert deleted == 1
    assert log_store.list_records() == []


def test_async_writer_batch_flush(log_store, file_store):
    """InteractionLogWriter 批量落盘。"""
    writer = InteractionLogWriter(log_store, file_store)
    for i in range(3):
        writer.enqueue(
            InteractionRecord(
                kind="llm_response",
                source="llm",
                script_id="async_s1",
                summary=f"n{i}",
                created_at="2026-06-17T12:00:00Z",
            )
        )
    writer.flush()
    assert len(log_store.list_records(script_id="async_s1")) == 3
    assert file_store.list_log_files(project_id="")
    writer.shutdown()


def test_redact_api_key():
    data = {"api_key": "sk-secret123456", "model": "gpt-4"}
    out = redact_for_log(data)
    assert out["api_key"] == "***"
    assert out["model"] == "gpt-4"
