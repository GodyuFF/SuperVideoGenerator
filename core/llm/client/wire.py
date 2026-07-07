"""Canonical LlmRequest ↔ Anthropic Messages API wire ↔ 日志 body 转换。"""

from __future__ import annotations

from typing import Any

from core.llm.model.chat_message import canonical_to_anthropic_messages
from core.llm.model.llm_request import LlmRequest, ToolDefinition


def tools_to_anthropic(tools: list[ToolDefinition]) -> list[dict[str, Any]]:
    """Canonical tools → Anthropic Messages API tools 数组。"""
    return [
        {
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.input_schema,
        }
        for tool in tools
    ]


def llm_request_to_wire_messages(request: LlmRequest) -> list[dict[str, Any]]:
    """canonical messages → Anthropic wire messages（system 由顶层字段承载）。"""
    return canonical_to_anthropic_messages(request.messages)


def llm_request_to_anthropic_payload(
    request: LlmRequest,
    *,
    model: str,
    temperature: float,
    max_tokens: int,
    stream: bool = True,
) -> dict[str, Any]:
    """HTTP 请求 body（Anthropic Messages API）。"""
    payload: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": llm_request_to_wire_messages(request),
        "stream": stream,
    }
    if request.system.strip():
        payload["system"] = request.system
    if temperature is not None:
        payload["temperature"] = temperature
    if request.tools:
        payload["tools"] = tools_to_anthropic(request.tools)
    if request.tool_choice is not None:
        payload["tool_choice"] = request.tool_choice
    return payload


# 兼容旧调用名
llm_request_to_wire_payload = llm_request_to_anthropic_payload
tools_to_openai = tools_to_anthropic


def llm_request_to_log_body(
    request: LlmRequest,
    **params: Any,
) -> dict[str, Any]:
    """交互日志 request_body：system / tools / messages 分列。"""
    body: dict[str, Any] = {
        "system": request.system,
        "messages": request.messages,
        **params,
    }
    if request.tools:
        body["tools"] = [tool.model_dump() for tool in request.tools]
    if request.tool_choice is not None:
        body["tool_choice"] = request.tool_choice
    return body
