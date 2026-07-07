"""对话完整时间线重建测试。"""

from pathlib import Path

import pytest

from core.llm.a2ui.schemas import A2UIConfirmationRequest, A2UIConfirmationResponse
from core.conversation.sqlite_store import ConversationSqliteStore
from core.conversation.store import ConversationMessage, MessageKind, MessageRole
from core.conversation.timeline import build_conversation_timeline
from core.llm.model.chat_message import text_block, tool_use_block


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
                tool_use_block(tool_id=tool_id, name="delegate_script_design", input_data={}),
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
    assert timeline[1]["action"] == "delegate_script_design"
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
