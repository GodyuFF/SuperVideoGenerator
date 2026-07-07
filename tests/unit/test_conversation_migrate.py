"""旧消息格式迁移测试。"""

from core.conversation.migrate import upgrade_conversation_messages
from core.conversation.store import ConversationMessage, MessageKind, MessageRole, load_conversation_messages


def test_upgrade_legacy_thought_action_observation():
    legacy = [
        {
            "id": "msg_action",
            "conversation_id": "c1",
            "project_id": "p1",
            "script_id": "s1",
            "channel": "agent",
            "agent_name": "script_agent",
            "role": "thought",
            "content": "先分析",
            "created_at": "",
        },
        {
            "id": "msg_action",
            "conversation_id": "c1",
            "project_id": "p1",
            "script_id": "s1",
            "channel": "agent",
            "agent_name": "script_agent",
            "role": "action",
            "content": 'parse_brief: {"x": 1}',
            "created_at": "",
        },
        {
            "id": "msg_obs",
            "conversation_id": "c1",
            "project_id": "p1",
            "script_id": "s1",
            "channel": "agent",
            "agent_name": "script_agent",
            "role": "observation",
            "content": "解析完成",
            "created_at": "",
        },
    ]
    upgraded = upgrade_conversation_messages(legacy)
    assert len(upgraded) == 2
    assert upgraded[0]["role"] == "assistant"
    assert isinstance(upgraded[0]["content"], list)
    assert upgraded[1]["role"] == "tool"
    assert upgraded[1]["tool_call_id"] == "call_msg_action"
    assert upgraded[1]["content"] == "解析完成"


def test_upgrade_master_and_task():
    legacy = [
        {
            "id": "m1",
            "conversation_id": "c1",
            "project_id": "p1",
            "script_id": "s1",
            "channel": "master",
            "agent_name": "",
            "role": "master",
            "content": "摘要",
            "created_at": "",
        },
        {
            "id": "m2",
            "conversation_id": "c1",
            "project_id": "p1",
            "script_id": "s1",
            "channel": "agent",
            "agent_name": "script_agent",
            "role": "task",
            "content": "写剧本",
            "created_at": "",
        },
    ]
    upgraded = upgrade_conversation_messages(legacy)
    assert upgraded[0]["role"] == "assistant"
    assert upgraded[0]["message_kind"] == "summary"
    assert upgraded[1]["role"] == "assistant"
    assert upgraded[1]["message_kind"] == "task_brief"
    assert str(upgraded[1]["content"]).startswith("任务简报：")


def test_load_conversation_messages_applies_migration():
    items = load_conversation_messages(
        [
            {
                "id": "m1",
                "conversation_id": "c1",
                "project_id": "p1",
                "script_id": "s1",
                "channel": "master",
                "agent_name": "",
                "role": "user",
                "content": "hi",
                "created_at": "",
            }
        ]
    )
    assert len(items) == 1
    assert items[0].role == MessageRole.USER

    migrated = load_conversation_messages(
        [
            {
                "id": "m2",
                "conversation_id": "c1",
                "project_id": "p1",
                "script_id": "s1",
                "channel": "master",
                "agent_name": "",
                "role": "master",
                "content": "摘要",
                "created_at": "",
            }
        ]
    )
    assert migrated[0].role == MessageRole.ASSISTANT
    assert migrated[0].message_kind == MessageKind.SUMMARY
