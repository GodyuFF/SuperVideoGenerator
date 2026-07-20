"""AppState 启动同步优化测试。"""

from unittest.mock import MagicMock

from core.conversation import ConversationIndex
from core.models.entities import Conversation


def test_sync_skips_existing_sqlite_conversations():
    """启动同步不对已在 SQLite 中的对话重复 upsert。"""
    from apps.api.state import AppState

    index = ConversationIndex()
    index.load_dict(
        {
            "conv_a": Conversation(
                id="conv_a",
                project_id="proj_1",
                script_id="scr_1",
                title="A",
            ),
            "conv_b": Conversation(
                id="conv_b",
                project_id="proj_1",
                script_id="scr_1",
                title="B",
            ),
        }
    )

    sqlite = MagicMock()
    sqlite.list_all_conversations.return_value = [
        Conversation(
            id="conv_a",
            project_id="proj_1",
            script_id="scr_1",
            title="A",
        ),
    ]
    sqlite.message_count.return_value = 1

    state_obj = object.__new__(AppState)
    state_obj.conversation_index = index
    state_obj.conversation_sqlite = sqlite
    state_obj.conversations = MagicMock()
    state_obj.conversations.messages = {}
    state_obj.store = MagicMock()

    AppState._sync_conversation_stores(state_obj)

    upsert_ids = [call.args[0].id for call in sqlite.upsert_conversation.call_args_list]
    assert upsert_ids == ["conv_b"]
    sqlite.backfill_messages.assert_not_called()
