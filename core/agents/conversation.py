"""向后兼容：请使用 core.conversation。"""

from core.conversation import (
    ConversationIndex,
    ConversationMessage,
    ConversationRole,
    ConversationStore,
    conversation_key,
)

__all__ = [
    "ConversationIndex",
    "ConversationMessage",
    "ConversationRole",
    "ConversationStore",
    "conversation_key",
]
