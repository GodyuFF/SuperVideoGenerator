"""LLM 协议层模型（非领域实体）。"""

from core.llm.model.chat_message import (
    ChatMessage,
    canonical_to_anthropic_messages,
    chat_message,
    flatten_content_blocks,
    normalize_content,
    text_block,
    tool_result_block,
    tool_use_block,
)
from core.llm.model.llm_request import LlmRequest, ToolDefinition
from core.llm.model.react import ReActAgentInfo, ReActStepRecord, ReActToolInfo, new_conversation_id

__all__ = [
    "ChatMessage",
    "LlmRequest",
    "ReActAgentInfo",
    "ReActStepRecord",
    "ReActToolInfo",
    "ToolDefinition",
    "canonical_to_anthropic_messages",
    "chat_message",
    "flatten_content_blocks",
    "new_conversation_id",
    "normalize_content",
    "text_block",
    "tool_result_block",
    "tool_use_block",
]
