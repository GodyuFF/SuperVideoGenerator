"""单元测试：ConversationIndex 与 ConversationStore。"""

import pytest

from core.conversation import ConversationIndex, ConversationStore
from core.models.entities import Project, Script
from core.store.memory import MemoryStore


@pytest.fixture
def ids():
    store = MemoryStore()
    project = Project(title="P")
    script = Script(project_id=project.id, title="S")
    store.add_project(project)
    store.add_script(script)
    return project.id, script.id


def test_conversation_store_isolates_by_conversation_id(ids):
    project_id, script_id = ids
    store = ConversationStore()
    store.add_user_message("conv_a", project_id, script_id, "hello a")
    store.add_user_message("conv_b", project_id, script_id, "hello b")

    a_msgs = store.list_master_messages_for_ui("conv_a")
    b_msgs = store.list_master_messages_for_ui("conv_b")
    assert len(a_msgs) == 1
    assert len(b_msgs) == 1
    assert a_msgs[0].content == "hello a"
    assert b_msgs[0].content == "hello b"


def test_conversation_index_list_for_project(ids):
    project_id, script_id = ids
    index = ConversationIndex()
    c1 = index.create(project_id, script_id, title="第一")
    c2 = index.create(project_id, script_id, title="第二")
    index.touch_after_message(c1.id, last_summary="摘要1")
    index.touch_after_message(c2.id, last_summary="摘要2")

    listed = index.list_for_project(project_id, script_id=script_id)
    assert len(listed) == 2
    assert listed[0].id in (c1.id, c2.id)


def test_conversation_index_require_rejects_mismatch(ids):
    project_id, script_id = ids
    index = ConversationIndex()
    conv = index.create(project_id, script_id)
    with pytest.raises(ValueError, match="不匹配"):
        index.require(conv.id, project_id="other", script_id=script_id)


def test_clear_agent_session_per_conversation(ids):
    project_id, script_id = ids
    store = ConversationStore()
    store.add_task_brief("conv1", project_id, script_id, "t1", "script_agent")
    store.add_task_brief("conv2", project_id, script_id, "t2", "script_agent")
    store.clear_agent_session("conv1", "script_agent")
    assert store.list_messages("conv1", "agent", "script_agent") == []
    assert len(store.list_messages("conv2", "agent", "script_agent")) == 1


def test_clear_agent_session_preserves_sqlite(ids, tmp_path):
    project_id, script_id = ids
    from core.conversation.sqlite_store import ConversationSqliteStore

    sqlite = ConversationSqliteStore(db_path=tmp_path / "conv.db")
    store = ConversationStore(sqlite_store=sqlite)
    store.add_task_brief("conv1", project_id, script_id, "t1", "script_agent")
    store.clear_agent_session("conv1", "script_agent")
    assert store.list_messages("conv1", "agent", "script_agent") == []
    archived = sqlite.list_messages("conv1")
    assert len(archived) == 1
    assert archived[0].message_kind.value == "task_brief"
