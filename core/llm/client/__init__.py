"""LLM HTTP 客户端与 wire 层。"""

from core.llm.client.client import LLMClient
from core.llm.client.errors import format_llm_http_error
from core.llm.client.providers import (
    DEFAULT_PROVIDER_ID,
    PROVIDER_PRESETS,
    list_providers,
    react_tool_choice,
)
from core.llm.client.settings import LLMConfigManager, LLMSettings
from core.llm.client.token_round import TokenRoundAccumulator
from core.llm.client.tokens import TokenEstimate, estimate_chat_tokens, estimate_text_tokens
from core.llm.client.tool_calls import ToolCallResult
from core.llm.client.wire import (
    llm_request_to_anthropic_payload,
    llm_request_to_log_body,
    llm_request_to_wire_messages,
    tools_to_anthropic,
)

__all__ = [
    "DEFAULT_PROVIDER_ID",
    "LLMClient",
    "LLMConfigManager",
    "LLMSettings",
    "PROVIDER_PRESETS",
    "TokenEstimate",
    "TokenRoundAccumulator",
    "ToolCallResult",
    "estimate_chat_tokens",
    "estimate_text_tokens",
    "format_llm_http_error",
    "list_providers",
    "llm_request_to_anthropic_payload",
    "llm_request_to_log_body",
    "llm_request_to_wire_messages",
    "react_tool_choice",
    "tools_to_anthropic",
]
