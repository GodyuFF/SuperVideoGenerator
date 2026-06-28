"""ConversationMessage → Chat API 多轮消息映射与历史构建。"""

from core.conversation import ConversationMessage, ConversationRole, ConversationStore
from core.prompt.config import (
    COMPRESSION_SNIPPET_CHARS,
    HISTORY_MAX_CHARS,
    HISTORY_WINDOW_SIZE,
)


def conversation_message_to_chat(msg: ConversationMessage) -> dict[str, str] | None:
    """将单条隔离会话消息映射为 OpenAI Chat 消息。"""
    if msg.role == ConversationRole.USER:
        return {"role": "user", "content": msg.content}
    if msg.role == ConversationRole.MASTER:
        return {"role": "assistant", "content": msg.content}
    if msg.role == ConversationRole.TASK:
        return {"role": "user", "content": f"任务简报：{msg.content}"}
    if msg.role == ConversationRole.THOUGHT:
        return {"role": "assistant", "content": f"思考：{msg.content}"}
    if msg.role == ConversationRole.ACTION:
        return {"role": "assistant", "content": f"行动：{msg.content}"}
    if msg.role == ConversationRole.OBSERVATION:
        return {"role": "user", "content": f"观察：{msg.content}"}
    return None


def messages_to_chat_history(
    messages: list[ConversationMessage],
) -> list[dict[str, str]]:
    """批量转换会话消息为 Chat API 历史。"""
    history: list[dict[str, str]] = []
    for msg in messages:
        chat = conversation_message_to_chat(msg)
        if chat:
            history.append(chat)
    return history


def fit_chat_history(
    messages: list[dict[str, str]],
    *,
    window_size: int = HISTORY_WINDOW_SIZE,
    max_chars: int = HISTORY_MAX_CHARS,
) -> tuple[list[dict[str, str]], str]:
    """对 Chat 历史做滑窗与字符预算压缩，返回 (保留消息, 摘要)。"""
    if not messages:
        return [], ""

    dropped_by_window = max(0, len(messages) - window_size)
    windowed = messages[-window_size:] if window_size > 0 else list(messages)

    kept: list[dict[str, str]] = []
    total = 0
    compressed_in_window = 0
    for msg in reversed(windowed):
        content = str(msg.get("content", "")).strip()
        if not content:
            continue
        add = len(content) + 8
        if kept and total + add > max_chars:
            compressed_in_window += 1
            continue
        kept.insert(0, msg)
        total += add

    if not kept and messages:
        last = messages[-1]
        content = str(last.get("content", ""))
        kept = [{"role": last.get("role", "user"), "content": content[:max_chars]}]

    dropped_count = dropped_by_window + compressed_in_window
    summary = ""
    if dropped_count > 0:
        dropped_msgs = messages[: len(messages) - len(kept)]
        snippets = [
            f"- [{m.get('role', 'user')}] {_truncate(str(m.get('content', '')), COMPRESSION_SNIPPET_CHARS)}"
            for m in dropped_msgs
            if str(m.get("content", "")).strip()
        ]
        if snippets:
            summary = (
                f"（已压缩较早的 {dropped_count} 条对话，以下为摘要）\n"
                + "\n".join(snippets)
            )

    return kept, summary


def _truncate(text: str, max_chars: int) -> str:
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1] + "…"


def _with_summary_prefix(
    history: list[dict[str, str]], summary: str
) -> list[dict[str, str]]:
    if not summary.strip():
        return history
    return [{"role": "user", "content": summary.strip()}] + history


def build_master_react_chat_history(
    conversations: ConversationStore,
    conversation_id: str,
) -> list[dict[str, str]]:
    """主编排 ReAct：从 master 通道构建多轮 Chat 历史。"""
    msgs = conversations.list_messages(conversation_id, "master")
    chat = messages_to_chat_history(msgs)
    fitted, summary = fit_chat_history(chat)
    return _with_summary_prefix(fitted, summary)


def build_agent_react_chat_history(
    conversations: ConversationStore,
    conversation_id: str,
    agent_name: str,
) -> list[dict[str, str]]:
    """子 Agent ReAct / 行动：从 agent 通道构建多轮 Chat 历史。"""
    msgs = conversations.list_messages(conversation_id, "agent", agent_name)
    chat = messages_to_chat_history(msgs)
    fitted, summary = fit_chat_history(chat)
    return _with_summary_prefix(fitted, summary)
