"""对话完整时间线重建测试。"""

from pathlib import Path

import pytest

from core.llm.a2ui.schemas import A2UIConfirmationRequest, A2UIConfirmationResponse
from core.conversation.sqlite_store import ConversationSqliteStore
from core.conversation.store import ConversationMessage, MessageKind, MessageRole
from core.conversation.timeline import build_conversation_timeline
from core.llm.model.chat_message import text_block, thinking_block, tool_use_block


@pytest.fixture
def sqlite_store(tmp_path: Path) -> ConversationSqliteStore:
    return ConversationSqliteStore(db_path=tmp_path / "timeline.db")


def _add(store: ConversationSqliteStore, msg: ConversationMessage) -> None:
    store.append_message(msg)


def test_timeline_master_react_and_user(sqlite_store: ConversationSqliteStore):
    conv = "conv1"
    _add(
        sqlite_store,
        ConversationMessage(
            id="m1",
            conversation_id=conv,
            project_id="p",
            script_id="s",
            channel="master",
            role=MessageRole.USER,
            content="做视频",
            created_at="2026-01-01T00:00:00+00:00",
        ),
    )
    tool_id = "call_1"
    _add(
        sqlite_store,
        ConversationMessage(
            id="m2",
            conversation_id=conv,
            project_id="p",
            script_id="s",
            channel="master",
            role=MessageRole.ASSISTANT,
            content=[
                text_block("先委派"),
                tool_use_block(
                    tool_id=tool_id,
                    name="delegate_agent",
                    input_data={"agent_id": "script_agent"},
                ),
            ],
            created_at="2026-01-01T00:00:01+00:00",
        ),
    )
    _add(
        sqlite_store,
        ConversationMessage(
            id="m3",
            conversation_id=conv,
            project_id="p",
            script_id="s",
            channel="master",
            role=MessageRole.TOOL,
            content="已委派",
            tool_call_id=tool_id,
            created_at="2026-01-01T00:00:02+00:00",
        ),
    )
    timeline = build_conversation_timeline(conv, sqlite_store)
    types = [t["type"] for t in timeline]
    assert types == ["user", "react_turn"]
    assert timeline[1]["action"] == "delegate_agent"
    assert timeline[1]["action_input"]["agent_id"] == "script_agent"
    assert timeline[1]["observation"] == "已委派"


def test_timeline_sub_agent_group(sqlite_store: ConversationSqliteStore):
    conv = "conv2"
    tool_id = "call_sub"
    _add(
        sqlite_store,
        ConversationMessage(
            id="a1",
            conversation_id=conv,
            project_id="p",
            script_id="s",
            channel="agent",
            agent_name="script_agent",
            step_id="step_1",
            role=MessageRole.ASSISTANT,
            content=[
                text_block("写剧本"),
                tool_use_block(tool_id=tool_id, name="parse_brief", input_data={}),
            ],
            created_at="2026-01-01T00:00:03+00:00",
        ),
    )
    _add(
        sqlite_store,
        ConversationMessage(
            id="a2",
            conversation_id=conv,
            project_id="p",
            script_id="s",
            channel="agent",
            agent_name="script_agent",
            step_id="step_1",
            role=MessageRole.TOOL,
            content="解析完成",
            tool_call_id=tool_id,
            created_at="2026-01-01T00:00:04+00:00",
        ),
    )
    timeline = build_conversation_timeline(conv, sqlite_store)
    assert len(timeline) == 1
    assert timeline[0]["type"] == "sub_agent"
    assert timeline[0]["agent_name"] == "script_agent"
    assert timeline[0]["iterations"][0]["action"] == "parse_brief"


def test_timeline_includes_a2ui(sqlite_store: ConversationSqliteStore):
    conv = "conv3"
    req = A2UIConfirmationRequest(
        confirmation_id="conf_x",
        kind="generic",
        title="提问",
    )
    sqlite_store.append_a2ui_request(conv, req)
    sqlite_store.resolve_a2ui(
        A2UIConfirmationResponse(
            confirmation_id="conf_x",
            approved=True,
            values={"q": "a"},
        )
    )
    timeline = build_conversation_timeline(conv, sqlite_store)
    assert timeline[0]["type"] == "a2ui_confirmation"
    assert timeline[0]["status"] == "submitted"


def test_timeline_sub_agent_merges_interleaved_messages(sqlite_store: ConversationSqliteStore):
    """子 Agent 消息被 A2UI/主会话打断时，应合并为单块而非拆成多段。"""
    conv = "conv4"
    tool1 = "call_1"
    tool2 = "call_2"
    _add(
        sqlite_store,
        ConversationMessage(
            id="m_user",
            conversation_id=conv,
            project_id="p",
            script_id="s",
            channel="master",
            role=MessageRole.USER,
            content="开始",
            created_at="2026-01-01T00:00:00+00:00",
        ),
    )
    _add(
        sqlite_store,
        ConversationMessage(
            id="a1",
            conversation_id=conv,
            project_id="p",
            script_id="s",
            channel="agent",
            agent_name="script_agent",
            step_id="step_1",
            role=MessageRole.ASSISTANT,
            content=[
                text_block("第一轮"),
                tool_use_block(tool_id=tool1, name="parse_brief", input_data={}),
            ],
            created_at="2026-01-01T00:00:01+00:00",
        ),
    )
    _add(
        sqlite_store,
        ConversationMessage(
            id="a2",
            conversation_id=conv,
            project_id="p",
            script_id="s",
            channel="agent",
            agent_name="script_agent",
            step_id="step_1",
            role=MessageRole.TOOL,
            content="完成第一轮",
            tool_call_id=tool1,
            created_at="2026-01-01T00:00:02+00:00",
        ),
    )
    req = A2UIConfirmationRequest(
        confirmation_id="conf_mid",
        kind="generic",
        title="确认",
    )
    sqlite_store.append_a2ui_request(conv, req)
    _add(
        sqlite_store,
        ConversationMessage(
            id="a3",
            conversation_id=conv,
            project_id="p",
            script_id="s",
            channel="agent",
            agent_name="script_agent",
            step_id="step_1",
            role=MessageRole.ASSISTANT,
            content=[
                text_block("第二轮"),
                tool_use_block(tool_id=tool2, name="update_script", input_data={}),
            ],
            created_at="2026-01-01T00:00:04+00:00",
        ),
    )
    _add(
        sqlite_store,
        ConversationMessage(
            id="a4",
            conversation_id=conv,
            project_id="p",
            script_id="s",
            channel="agent",
            agent_name="script_agent",
            step_id="step_1",
            role=MessageRole.TOOL,
            content="完成第二轮",
            tool_call_id=tool2,
            created_at="2026-01-01T00:00:05+00:00",
        ),
    )
    timeline = build_conversation_timeline(conv, sqlite_store)
    sub_blocks = [t for t in timeline if t["type"] == "sub_agent"]
    assert len(sub_blocks) == 1
    assert len(sub_blocks[0]["iterations"]) == 2
    assert sub_blocks[0]["iterations"][0]["action"] == "parse_brief"
    assert sub_blocks[0]["iterations"][1]["action"] == "update_script"


def test_timeline_master_react_pairs_tool_across_a2ui(sqlite_store: ConversationSqliteStore):
    """主会话 ReAct 的 observation 可跨过中间的 A2UI 事件配对。"""
    conv = "conv5"
    tool_id = "call_master"
    _add(
        sqlite_store,
        ConversationMessage(
            id="u1",
            conversation_id=conv,
            project_id="p",
            script_id="s",
            channel="master",
            role=MessageRole.USER,
            content="你好",
            created_at="2026-01-01T00:00:00+00:00",
        ),
    )
    _add(
        sqlite_store,
        ConversationMessage(
            id="m1",
            conversation_id=conv,
            project_id="p",
            script_id="s",
            channel="master",
            role=MessageRole.ASSISTANT,
            content=[
                text_block("委派"),
                tool_use_block(
                    tool_id=tool_id,
                    name="delegate_agent",
                    input_data={"agent_id": "script_agent"},
                ),
            ],
            created_at="2026-01-01T00:00:01+00:00",
        ),
    )
    sqlite_store.append_a2ui_request(
        conv,
        A2UIConfirmationRequest(
            confirmation_id="conf_gap",
            kind="generic",
            title="中间确认",
        ),
    )
    _add(
        sqlite_store,
        ConversationMessage(
            id="m2",
            conversation_id=conv,
            project_id="p",
            script_id="s",
            channel="master",
            role=MessageRole.TOOL,
            content="已委派完成",
            tool_call_id=tool_id,
            created_at="2026-01-01T00:00:03+00:00",
        ),
    )
    timeline = build_conversation_timeline(conv, sqlite_store)
    react_items = [t for t in timeline if t["type"] == "react_turn"]
    assert len(react_items) == 1
    assert react_items[0]["observation"] == "已委派完成"


def test_timeline_page_limit(sqlite_store: ConversationSqliteStore):
    """分页时间线应限制条目数并返回 has_more。"""
    from core.conversation.timeline import build_conversation_timeline_page

    conv = "conv-page"
    for i in range(5):
        _add(
            sqlite_store,
            ConversationMessage(
                id=f"u{i}",
                conversation_id=conv,
                project_id="p",
                script_id="s",
                channel="master",
                role=MessageRole.USER,
                content=f"msg {i}",
                created_at=f"2026-07-12T10:00:{i:02d}Z",
            ),
        )
    timeline, has_more, oldest = build_conversation_timeline_page(
        conv, sqlite_store, limit=3
    )
    assert len(timeline) == 3
    assert has_more is True
    assert oldest == "2026-07-12T10:00:02Z"

    page2, has_more2, oldest2 = build_conversation_timeline_page(
        conv, sqlite_store, limit=3, before_created_at=oldest
    )
    assert has_more2 is False
    assert oldest2 == "2026-07-12T10:00:00Z"
    assert [t["content"] for t in page2 if t["type"] == "user"] == ["msg 0", "msg 1"]


def test_timeline_sub_agent_batch_actions(sqlite_store: ConversationSqliteStore):
    """子 Agent 同轮多 tool_use 应聚合为 actions[]。"""
    conv = "conv_sub_batch"
    _add(
        sqlite_store,
        ConversationMessage(
            id="m1",
            conversation_id=conv,
            project_id="p",
            script_id="s",
            channel="agent",
            agent_name="script_agent",
            step_id="step1",
            role=MessageRole.ASSISTANT,
            content=[
                thinking_block("批量创建"),
                tool_use_block(tool_id="c1", name="create_character", input_data={"asset_name": "Alice"}),
                tool_use_block(tool_id="c2", name="create_prop", input_data={"asset_name": "Sword"}),
            ],
            created_at="2026-07-13T00:00:01+00:00",
        ),
    )
    _add(
        sqlite_store,
        ConversationMessage(
            id="m2",
            conversation_id=conv,
            project_id="p",
            script_id="s",
            channel="agent",
            agent_name="script_agent",
            step_id="step1",
            role=MessageRole.TOOL,
            content="已创建 Alice",
            tool_call_id="c1",
            created_at="2026-07-13T00:00:02+00:00",
        ),
    )
    _add(
        sqlite_store,
        ConversationMessage(
            id="m3",
            conversation_id=conv,
            project_id="p",
            script_id="s",
            channel="agent",
            agent_name="script_agent",
            step_id="step1",
            role=MessageRole.TOOL,
            content="已创建 Sword",
            tool_call_id="c2",
            created_at="2026-07-13T00:00:03+00:00",
        ),
    )
    timeline = build_conversation_timeline(conv, sqlite_store)
    sub_items = [t for t in timeline if t["type"] == "sub_agent"]
    assert len(sub_items) == 1
    it = sub_items[0]["iterations"][0]
    assert "actions" in it
    assert len(it["actions"]) == 2
    assert {a["action"] for a in it["actions"]} == {"create_character", "create_prop"}
