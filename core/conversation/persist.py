"""对话索引与消息 JSON 持久化（随 dev_store.json 或独立字段）。"""

import json
from pathlib import Path

from core.conversation.index import ConversationIndex
from core.conversation.store import ConversationMessage, ConversationStore, load_conversation_messages
from core.models.entities import Conversation
from core.store.persist import DEFAULT_PATH, is_enabled

_CONV_MESSAGES_KEY = "conversation_messages"


def save_conversations(
    index: ConversationIndex,
    store: ConversationStore,
    path: Path | None = None,
) -> None:
    if not is_enabled():
        return
    file_path = path or DEFAULT_PATH
    if not file_path.exists():
        return
    try:
        raw = json.loads(file_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return
    raw["conversations"] = {
        k: v.model_dump() for k, v in index.conversations.items()
    }
    raw[_CONV_MESSAGES_KEY] = {
        k: [m.model_dump() for m in msgs]
        for k, msgs in store.messages.items()
    }
    file_path.write_text(
        json.dumps(raw, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_conversations(
    index: ConversationIndex,
    store: ConversationStore,
    path: Path | None = None,
) -> bool:
    if not is_enabled():
        return False
    file_path = path or DEFAULT_PATH
    if not file_path.exists():
        return False
    try:
        raw = json.loads(file_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    convs = {
        k: Conversation.model_validate(v)
        for k, v in raw.get("conversations", {}).items()
    }
    index.load_dict(convs)
    msg_data: dict[str, list[ConversationMessage]] = {}
    for k, items in raw.get(_CONV_MESSAGES_KEY, {}).items():
        msg_data[k] = load_conversation_messages(items)
    store.load_dict(msg_data)
    return bool(convs or msg_data)
