"""Canonical LLM 请求：system / tools / messages 同级。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from core.llm.model.chat_message import ChatMessage


class ToolDefinition(BaseModel):
    """JSON Schema 风格 tool 定义（wire 层再映射为 OpenAI function）。"""

    name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any] = Field(default_factory=dict)
    kind: Literal["function", "agent"] = "function"
    agent_name: str = ""


class LlmRequest(BaseModel):
    """Prompt 层统一请求体：system 与 messages 分离。"""

    system: str
    tools: list[ToolDefinition] = Field(default_factory=list)
    messages: list[ChatMessage] = Field(default_factory=list)
    tool_choice: dict[str, Any] | None = None

    model_config = {"arbitrary_types_allowed": True}
