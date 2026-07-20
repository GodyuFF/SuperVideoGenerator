"""Conversation SQLite 仓储测试。"""

import threading
from pathlib import Path

import pytest

from core.llm.a2ui.schemas import A2UIConfirmationRequest, A2UIConfirmationResponse
from core.conversation.sqlite_store import ConversationSqliteStore
from core.conversation.store import ConversationMessage, MessageKind, MessageRole
from core.models.entities import Conversation, ConversationStatus, new_id


@pytest.fixture
def sqlite_store(tmp_path: Path) -> ConversationSqliteStore:
    return ConversationSqliteStore(db_path=tmp_path / "test_conversations.db")


def test_append_and_list_messages(sqlite_store: ConversationSqliteStore):
    conv_id = new_id("conv")
    msg = ConversationMessage(
        id=new_id("msg"),
        conversation_id=conv_id,
        project_id="p1",
        script_id="s1",
        channel="master",
        role=MessageRole.USER,
        content="你好",
        created_at="2026-01-01T00:00:00+00:00",
    )
    sqlite_store.append_message(msg)
    rows = sqlite_store.list_messages(conv_id)
    assert len(rows) == 1
    assert rows[0].content == "你好"


def test_import_from_json(sqlite_store: ConversationSqliteStore):
    conv = Conversation(
        id="conv_import",
        project_id="p1",
        script_id="s1",
        title="测试",
        status=ConversationStatus.ACTIVE,
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
    )
    msg = ConversationMessage(
        id="msg1",
        conversation_id="conv_import",
        project_id="p1",
        script_id="s1",
        channel="agent",
        agent_name="script_agent",
        step_id="step_1",
        role=MessageRole.ASSISTANT,
        content=[{"type": "text", "text": "思考"}],
        message_kind=MessageKind.DEFAULT,
        created_at="2026-01-01T00:00:01+00:00",
    )
    count = sqlite_store.import_from_json({"conv_import": conv}, {"conv_import:agent:script_agent": [msg]})
    assert count == 1
    assert sqlite_store.message_count() == 1
    listed = sqlite_store.list_conversations("p1")
    assert len(listed) == 1
    assert listed[0].title == "测试"


def test_a2ui_request_and_resolve(sqlite_store: ConversationSqliteStore):
    conv_id = "conv_a2ui"
    req = A2UIConfirmationRequest(
        confirmation_id="conf_1",
        kind="generic",
        title="补充信息",
    )
    sqlite_store.append_a2ui_request(conv_id, req)
    records = sqlite_store.list_a2ui(conv_id)
    assert len(records) == 1
    assert records[0].approved is None

    sqlite_store.resolve_a2ui(
        A2UIConfirmationResponse(
            confirmation_id="conf_1",
            approved=True,
            values={"theme": "科幻"},
        )
    )
    records = sqlite_store.list_a2ui(conv_id)
    assert records[0].approved is True
    assert records[0].response_json is not None


def test_backfill_messages_survives_concurrent_dict_growth(sqlite_store: ConversationSqliteStore):
    """并发向 messages 字典新增 key 时 backfill 不应抛 RuntimeError。"""
    conv_id = new_id("conv")
    seed_msg = ConversationMessage(
        id=new_id("msg"),
        conversation_id=conv_id,
        project_id="p1",
        script_id="s1",
        channel="master",
        role=MessageRole.USER,
        content="seed",
        created_at="2026-01-01T00:00:00+00:00",
    )
    messages_dict: dict[str, list[ConversationMessage]] = {
        f"{conv_id}:master": [seed_msg],
    }
    stop = threading.Event()

    def grow_dict() -> None:
        i = 0
        while not stop.is_set():
            messages_dict[f"{conv_id}:agent:worker_{i}"] = []
            i += 1

    worker = threading.Thread(target=grow_dict, daemon=True)
    worker.start()
    try:
        imported = sqlite_store.backfill_messages(messages_dict)
    finally:
        stop.set()
        worker.join(timeout=2)
    assert imported >= 1
    assert sqlite_store.message_count() >= 1
