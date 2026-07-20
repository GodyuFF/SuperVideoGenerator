"""pytest data 隔离：防止测试误清空真实 conversations.db。"""

from core.conversation.sqlite_store import ConversationSqliteStore
from core.store import project_paths
from tests.support.data_isolation import rebind_conversation_storage, rebind_data_root


def test_rebind_conversation_storage_uses_session_data_root(tmp_path, monkeypatch):
    """rebind 后 AppState 的 SQLite 应指向会话临时目录，而非仓库 data/。"""
    from apps.api.state import state

    session_root = tmp_path / "svg_session"
    rebind_data_root(session_root)

    assert state.conversation_sqlite._path == session_root / "conversations.db"
    assert project_paths.DATA_ROOT == session_root


def test_rebind_conversation_storage_updates_singleton(tmp_path):
    """单独 rebind 对话存储时也应切换 db 路径。"""
    from apps.api.state import state

    alt_root = tmp_path / "alt_data"
    alt_root.mkdir()
    project_paths.DATA_ROOT = alt_root
    rebind_conversation_storage()

    assert isinstance(state.conversation_sqlite, ConversationSqliteStore)
    assert state.conversation_sqlite._path == alt_root / "conversations.db"
