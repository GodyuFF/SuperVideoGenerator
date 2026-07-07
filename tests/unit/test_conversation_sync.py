"""对话 index ↔ SQLite 同步测试。"""

from core.conversation.index import ConversationIndex
from core.conversation.sqlite_store import ConversationSqliteStore
from core.conversation.store import ConversationMessage, MessageRole
from core.models.entities import Conversation, ConversationStatus, new_id


def test_merge_from_sqlite_restores_missing_index(tmp_path):
    sqlite = ConversationSqliteStore(db_path=tmp_path / "conv.db")
    index = ConversationIndex()
    conv = Conversation(
        id="conv_sqlite_only",
        project_id="p1",
        script_id="s1",
        title="历史对话",
        status=ConversationStatus.ACTIVE,
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-02T00:00:00+00:00",
    )
    sqlite.upsert_conversation(conv)
    sqlite.append_message(
        ConversationMessage(
            id=new_id("msg"),
            conversation_id=conv.id,
            project_id="p1",
            script_id="s1",
            channel="master",
            role=MessageRole.USER,
            content="你好",
            created_at="2026-01-01T00:00:01+00:00",
        )
    )

    assert index.list_for_project("p1", script_id="s1") == []
    added = index.merge_from_sqlite(sqlite)
    assert added == 1
    items = index.list_for_project("p1", script_id="s1")
    assert len(items) == 1
    assert items[0].id == "conv_sqlite_only"
    assert sqlite.list_messages("conv_sqlite_only")


def test_get_conversation_from_sqlite(tmp_path):
    sqlite = ConversationSqliteStore(db_path=tmp_path / "conv2.db")
    conv = Conversation(
        id="conv_get",
        project_id="p2",
        script_id="s2",
        title="T",
        status=ConversationStatus.ACTIVE,
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
    )
    sqlite.upsert_conversation(conv)
    loaded = sqlite.get_conversation("conv_get")
    assert loaded is not None
    assert loaded.title == "T"
