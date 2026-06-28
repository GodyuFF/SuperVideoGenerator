"""Chat 多轮消息映射与历史构建测试。"""

from core.conversation import ConversationRole, ConversationStore
from core.prompt.chat_messages import (
    build_agent_react_chat_history,
    build_master_react_chat_history,
    conversation_message_to_chat,
    fit_chat_history,
    messages_to_chat_history,
)
from core.conversation.store import ConversationMessage


def _msg(role: ConversationRole, content: str, agent: str = "") -> ConversationMessage:
    return ConversationMessage(
        conversation_id="conv1",
        project_id="p1",
        script_id="s1",
        channel="agent" if agent else "master",
        agent_name=agent,
        role=role,
        content=content,
    )


def test_conversation_message_role_mapping():
    assert conversation_message_to_chat(_msg(ConversationRole.USER, "你好")) == {
        "role": "user",
        "content": "你好",
    }
    assert conversation_message_to_chat(_msg(ConversationRole.MASTER, "收到")) == {
        "role": "assistant",
        "content": "收到",
    }
    assert conversation_message_to_chat(
        _msg(ConversationRole.OBSERVATION, "完成", "script_agent")
    ) == {"role": "user", "content": "观察：完成"}


def test_fit_chat_history_keeps_recent_messages():
    messages = [
        {"role": "user", "content": f"消息{i}"} for i in range(20)
    ]
    kept, summary = fit_chat_history(messages, window_size=5, max_chars=500)
    assert len(kept) <= 5
    assert kept[-1]["content"] == "消息19"
    assert "已压缩" in summary


def test_build_master_react_chat_history_from_store():
    store = ConversationStore()
    store.add("conv1", "p1", "s1", "master", ConversationRole.USER, "做短片")
    store.add("conv1", "p1", "s1", "master", ConversationRole.THOUGHT, "先写剧本")
    store.add("conv1", "p1", "s1", "master", ConversationRole.OBSERVATION, "工具返回计划")

    history = build_master_react_chat_history(store, "conv1")
    assert history[0]["role"] == "user"
    assert history[1]["role"] == "assistant"
    assert "思考" in history[1]["content"]
    assert history[2]["role"] == "user"
    assert "观察" in history[2]["content"]


def test_build_agent_react_chat_history_from_store():
    store = ConversationStore()
    store.add(
        "conv1", "p1", "s1", "agent", ConversationRole.TASK, "写剧本", "script_agent"
    )
    store.add(
        "conv1", "p1", "s1", "agent", ConversationRole.THOUGHT, "解析", "script_agent"
    )

    history = build_agent_react_chat_history(store, "conv1", "script_agent")
    assert len(history) == 2
    assert history[0]["content"].startswith("任务简报")
    assert history[1]["content"].startswith("思考")


def test_messages_to_chat_history_skips_unknown():
    msgs = [_msg(ConversationRole.USER, "a")]
    assert messages_to_chat_history(msgs) == [{"role": "user", "content": "a"}]
