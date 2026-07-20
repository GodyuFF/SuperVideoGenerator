"""Canonical LlmRequest ↔ OpenAI Chat Completions API wire 转换。"""

from __future__ import annotations

import json
from typing import Any

from core.llm.model.chat_message import (
    ChatMessage,
    ContentBlock,
    message_content_text,
    normalize_content,
    text_block,
)
from core.llm.model.llm_request import LlmRequest, ToolDefinition
from core.llm.prompt.chat_messages import repair_tool_message_pairs


def tools_to_openai(tools: list[ToolDefinition]) -> list[dict[str, Any]]:
    """Canonical tools → OpenAI Chat Completions tools 数组。"""
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.input_schema,
            },
        }
        for tool in tools
    ]


def anthropic_tool_choice_to_openai(
    tool_choice: dict[str, Any] | str | None,
) -> dict[str, Any] | str | None:
    """Anthropic 风格 tool_choice → OpenAI Chat Completions tool_choice。"""
    if tool_choice is None:
        return None
    if isinstance(tool_choice, str):
        return tool_choice
    choice_type = str(tool_choice.get("type", "")).strip().lower()
    if choice_type in {"any", "required"}:
        return "required"
    if choice_type == "auto":
        return "auto"
    if choice_type == "tool":
        name = str(tool_choice.get("name", "")).strip()
        if name:
            return {"type": "function", "function": {"name": name}}
        return "required"
    if choice_type == "function":
        return tool_choice
    return "auto"


def _blocks_to_openai_content(blocks: list[ContentBlock]) -> str:
    """将 content blocks 合并为 OpenAI 字符串 content。"""
    parts: list[str] = []
    for block in blocks:
        btype = block.get("type")
        if btype == "text":
            text = str(block.get("text", "")).strip()
            if text:
                parts.append(text)
        elif btype == "thinking":
            thinking = str(block.get("thinking", "")).strip()
            if thinking:
                parts.append(thinking)
        elif btype == "tool_result":
            content = str(block.get("content", "")).strip()
            if content:
                parts.append(content)
        elif btype == "tool_use":
            name = str(block.get("name", "")).strip()
            inp = block.get("input", {})
            if isinstance(inp, str):
                arg_str = inp
            else:
                arg_str = json.dumps(inp, ensure_ascii=False)
            parts.append(f"[行动] {name}: {arg_str}" if name else f"[行动] {arg_str}")
    return "\n".join(parts)


def _assistant_tool_calls_from_blocks(blocks: list[ContentBlock]) -> list[dict[str, Any]]:
    """从 assistant content blocks 提取 OpenAI tool_calls。"""
    calls: list[dict[str, Any]] = []
    for block in blocks:
        if block.get("type") != "tool_use":
            continue
        tool_id = str(block.get("id", "")).strip()
        name = str(block.get("name", "")).strip()
        inp = block.get("input", {})
        if isinstance(inp, str):
            arguments = inp
        else:
            arguments = json.dumps(inp, ensure_ascii=False)
        calls.append(
            {
                "id": tool_id or f"call_{len(calls)}",
                "type": "function",
                "function": {"name": name, "arguments": arguments},
            }
        )
    return calls


def canonical_to_openai_messages(messages: list[ChatMessage]) -> list[dict[str, Any]]:
    """canonical block messages → OpenAI Chat Completions wire 格式。"""
    wire: list[dict[str, Any]] = []
    pending_user_text: list[str] = []

    def flush_user() -> None:
        nonlocal pending_user_text
        if pending_user_text:
            wire.append({"role": "user", "content": "\n".join(pending_user_text)})
            pending_user_text = []

    for msg in messages:
        role = str(msg.get("role", "user"))
        blocks = normalize_content(msg.get("content"))

        if role == "system":
            text = _blocks_to_openai_content(blocks)
            if text.strip():
                wire.append({"role": "system", "content": text})
            continue

        if role == "user":
            text = _blocks_to_openai_content(blocks)
            if text.strip():
                pending_user_text.append(text)
            continue

        if role == "tool":
            flush_user()
            tool_id = str(msg.get("tool_call_id", "")).strip()
            content = _blocks_to_openai_content(blocks)
            wire.append({"role": "tool", "tool_call_id": tool_id, "content": content})
            continue

        if role != "assistant":
            continue

        flush_user()
        tool_calls = _assistant_tool_calls_from_blocks(blocks)
        non_tool_blocks = [b for b in blocks if b.get("type") != "tool_use"]
        content = _blocks_to_openai_content(non_tool_blocks)

        assistant_msg: dict[str, Any] = {"role": "assistant"}
        if content.strip():
            assistant_msg["content"] = content
        elif not tool_calls:
            assistant_msg["content"] = ""
        if tool_calls:
            assistant_msg["tool_calls"] = tool_calls
        wire.append(assistant_msg)

        for block in blocks:
            if block.get("type") != "tool_result":
                continue
            tool_id = str(block.get("tool_use_id", "")).strip()
            result_content = str(block.get("content", "")).strip()
            wire.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_id,
                    "content": result_content,
                }
            )

    flush_user()
    return wire


def llm_request_to_openai_messages(request: LlmRequest) -> list[dict[str, Any]]:
    """canonical messages → OpenAI wire messages（system 可内嵌或顶层）。"""
    repaired = repair_tool_message_pairs(request.messages)
    wire = canonical_to_openai_messages(repaired)
    if request.system.strip():
        wire.insert(0, {"role": "system", "content": request.system.strip()})
    return wire


def llm_request_to_openai_payload(
    request: LlmRequest,
    *,
    model: str,
    temperature: float,
    max_tokens: int,
    stream: bool = True,
) -> dict[str, Any]:
    """HTTP 请求 body（OpenAI Chat Completions API）。"""
    payload: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": llm_request_to_openai_messages(request),
        "stream": stream,
    }
    if temperature is not None:
        payload["temperature"] = temperature
    if request.tools:
        payload["tools"] = tools_to_openai(request.tools)
    if request.tool_choice is not None:
        payload["tool_choice"] = anthropic_tool_choice_to_openai(request.tool_choice)
    return payload


def openai_message_content_preview(msg: dict[str, Any]) -> str:
    """提取 OpenAI wire message 的可读文本摘要。"""
    content = msg.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return message_content_text(content)  # type: ignore[arg-type]
    return ""
