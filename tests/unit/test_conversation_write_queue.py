"""ConversationWriteQueue 单元测试。"""

import pytest

from core.conversation.sqlite_store import ConversationSqliteStore
from core.conversation.store import ConversationMessage, MessageRole
from core.conversation.write_queue import ConversationWriteQueue


def _sample_msg(conv_id: str, suffix: str) -> ConversationMessage:
    return ConversationMessage(
        id=f"msg-{suffix}",
        conversation_id=conv_id,
        project_id="p1",
        script_id="s1",
        channel="master",
        role=MessageRole.USER,
        content=f"hello {suffix}",
        created_at=f"2026-07-12T10:00:{suffix}Z",
    )


@pytest.mark.asyncio
async def test_write_queue_batch_flush(tmp_path):
    """enqueue 多条后 drain 应批量写入 SQLite。"""
    db = tmp_path / "conv.db"
    sqlite = ConversationSqliteStore(db)
    queue = ConversationWriteQueue(sqlite, batch_size=2)
    conv_id = "conv-1"
    queue.enqueue(_sample_msg(conv_id, "01"))
    queue.enqueue(_sample_msg(conv_id, "02"))
    await queue.drain()
    rows = sqlite.list_messages(conv_id)
    assert len(rows) == 2
