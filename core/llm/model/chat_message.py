"""Chat API 消息与 content block 模型（canonical 格式）。"""

from __future__ import annotations

import json
from typing import Any, Literal, TypeAlias

ChatRole: TypeAlias = Literal["system", "user", "assistant", "tool"]
AnthropicMessage: TypeAlias = dict[str, Any]
ContentBlock: TypeAlias = dict[str, Any]
ChatMessage: TypeAlias = dict[str, Any]


def text_block(text: str) -> ContentBlock:
    return {"type": "text", "text": text}


def thinking_block(thinking: str, *, signature: str = "") -> ContentBlock:
    block: ContentBlock = {"type": "thinking", "thinking": thinking}
    if signature:
        block["signature"] = signature
    return block


def tool_use_block(*, tool_id: str, name: str, input_data: dict[str, Any]) -> ContentBlock:
    return {"type": "tool_use", "id": tool_id, "name": name, "input": input_data}


def tool_result_block(
    *,
    tool_use_id: str,
    content: str,
    is_error: bool = False,
) -> ContentBlock:
    block: ContentBlock = {
        "type": "tool_result",
        "tool_use_id": tool_use_id,
        "content": content,
    }
    if is_error:
        block["is_error"] = True
    return block


def normalize_content(content: str | list[ContentBlock] | None) -> list[ContentBlock]:
    """将 str 或 block 列表统一为 content blocks。"""
    if content is None:
        return []
    if isinstance(content, str):
        return [text_block(content)] if content else []
    if isinstance(content, list):
        return list(content)
    return [text_block(str(content))]


def chat_message(
    role: ChatRole,
    content: str | list[ContentBlock],
    *,
    tool_call_id: str = "",
) -> ChatMessage:
    msg: ChatMessage = {"role": role, "content": normalize_content(content)}
    if role == "tool" and tool_call_id:
        msg["tool_call_id"] = tool_call_id
    return msg


def tool_message(tool_call_id: str, content: str) -> ChatMessage:
    """构造 canonical tool 角色消息。"""
    return chat_message("tool", content, tool_call_id=tool_call_id)


def _blocks_to_text_content(blocks: list[ContentBlock]) -> str:
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
    return "\n".join(parts)


def message_content_text(content: str | list[ContentBlock]) -> str:
    """从 message content 提取纯文本（用于 state JSON 解析等）。"""
    return _blocks_to_text_content(normalize_content(content))


def flatten_content_blocks(blocks: list[ContentBlock]) -> str:
    """将 content blocks 压平为可读文本（压缩摘要、字符预算用）。"""
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
        elif btype == "tool_use":
            name = str(block.get("name", ""))
            inp = block.get("input", {})
            if isinstance(inp, str):
                input_str = inp
            else:
                input_str = json.dumps(inp, ensure_ascii=False)
            parts.append(f"[行动] {name}: {input_str}")
        elif btype == "tool_result":
            result = str(block.get("content", "")).strip()
            if result:
                parts.append(f"[观察] {result}")
    return "\n".join(parts)


def _canonical_block_to_anthropic(block: ContentBlock) -> ContentBlock:
    """Canonical block → Anthropic Messages API content block。"""
    btype = block.get("type")
    if btype == "thinking":
        out: ContentBlock = {
            "type": "thinking",
            "thinking": str(block.get("thinking", "")),
        }
        signature = block.get("signature")
        if signature:
            out["signature"] = str(signature)
        return out
    if btype == "tool_use":
        return {
            "type": "tool_use",
            "id": str(block.get("id", "")),
            "name": str(block.get("name", "")),
            "input": block.get("input", {}) if isinstance(block.get("input"), dict) else {},
        }
    if btype == "tool_result":
        result: ContentBlock = {
            "type": "tool_result",
            "tool_use_id": str(block.get("tool_use_id", "")),
            "content": str(block.get("content", "")),
        }
        if block.get("is_error"):
            result["is_error"] = True
        return result
    if btype == "text":
        return text_block(str(block.get("text", "")))
    return text_block(str(block))


def _assistant_blocks_for_wire(blocks: list[ContentBlock]) -> list[ContentBlock]:
    """assistant content blocks → Anthropic wire blocks（含 thinking 模式兼容）。"""
    non_results = [b for b in blocks if b.get("type") != "tool_result"]
    has_tool_use = any(b.get("type") == "tool_use" for b in non_results)
    has_thinking = any(b.get("type") == "thinking" for b in non_results)
    converted = [_canonical_block_to_anthropic(b) for b in non_results]
    if has_tool_use and not has_thinking:
        if converted and converted[0].get("type") == "text":
            first = converted[0]
            converted[0] = {
                "type": "thinking",
                "thinking": str(first.get("text", "")),
            }
        else:
            converted.insert(0, {"type": "thinking", "thinking": ""})
    return converted


def canonical_to_anthropic_messages(messages: list[ChatMessage]) -> list[AnthropicMessage]:
    """canonical block messages → Anthropic Messages API wire 格式（仅 user/assistant）。"""
    wire: list[AnthropicMessage] = []
    pending_user_blocks: list[ContentBlock] = []

    def flush_user() -> None:
        nonlocal pending_user_blocks
        if pending_user_blocks:
            wire.append({"role": "user", "content": list(pending_user_blocks)})
            pending_user_blocks = []

    for msg in messages:
        role = str(msg.get("role", "user"))
        blocks = normalize_content(msg.get("content"))

        if role == "system":
            continue

        if role == "user":
            for block in blocks:
                pending_user_blocks.append(_canonical_block_to_anthropic(block))
            continue

        if role == "tool":
            tool_id = str(msg.get("tool_call_id", ""))
            content_text = _blocks_to_text_content(blocks)
            pending_user_blocks.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": content_text,
                }
            )
            continue

        if role != "assistant":
            continue

        flush_user()
        orphan_tool_results: list[ContentBlock] = []
        assistant_source: list[ContentBlock] = []
        for block in blocks:
            if block.get("type") == "tool_result":
                orphan_tool_results.append(_canonical_block_to_anthropic(block))
            else:
                assistant_source.append(block)

        assistant_blocks = _assistant_blocks_for_wire(assistant_source)
        if assistant_blocks:
            wire.append({"role": "assistant", "content": assistant_blocks})
        if orphan_tool_results:
            pending_user_blocks.extend(orphan_tool_results)

    flush_user()
    return wire


def anthropic_to_canonical_messages(messages: list[AnthropicMessage]) -> list[ChatMessage]:
    """Anthropic wire messages → canonical block messages。"""
    canonical: list[ChatMessage] = []
    for msg in messages:
        role = str(msg.get("role", "user"))
        raw_content = msg.get("content")
        if isinstance(raw_content, str):
            blocks = [text_block(raw_content)] if raw_content else []
        elif isinstance(raw_content, list):
            blocks = []
            for block in raw_content:
                if not isinstance(block, dict):
                    continue
                btype = block.get("type")
                if btype == "text":
                    blocks.append(text_block(str(block.get("text", ""))))
                elif btype == "thinking":
                    sig = str(block.get("signature", ""))
                    blocks.append(
                        thinking_block(str(block.get("thinking", "")), signature=sig)
                    )
                elif btype == "tool_use":
                    blocks.append(
                        tool_use_block(
                            tool_id=str(block.get("id", "")),
                            name=str(block.get("name", "")),
                            input_data=block.get("input", {})
                            if isinstance(block.get("input"), dict)
                            else {},
                        )
                    )
                elif btype == "tool_result":
                    blocks.append(
                        tool_result_block(
                            tool_use_id=str(block.get("tool_use_id", "")),
                            content=str(block.get("content", "")),
                            is_error=bool(block.get("is_error")),
                        )
                    )
        else:
            blocks = []

        if role == "assistant":
            tool_results = [b for b in blocks if b.get("type") == "tool_result"]
            other = [b for b in blocks if b.get("type") != "tool_result"]
            if other:
                canonical.append(chat_message("assistant", other))
            for tr in tool_results:
                canonical.append(
                    tool_message(
                        str(tr.get("tool_use_id", "")),
                        str(tr.get("content", "")),
                    )
                )
            continue

        if role == "user":
            tool_results = [b for b in blocks if b.get("type") == "tool_result"]
            text_blocks = [b for b in blocks if b.get("type") != "tool_result"]
            if text_blocks:
                canonical.append(chat_message("user", text_blocks))
            for tr in tool_results:
                canonical.append(
                    tool_message(
                        str(tr.get("tool_use_id", "")),
                        str(tr.get("content", "")),
                    )
                )
    return canonical


def wire_message_chars_anthropic(msg: AnthropicMessage) -> int:
    """估算单条 Anthropic wire message 字符数（滑窗压缩用）。"""
    return len(json.dumps(msg, ensure_ascii=False))


def parse_action_content(content: str) -> tuple[str, dict[str, Any]]:
    """解析 ACTION 消息 content：'{action}: {input}'。"""
    text = content.strip()
    if ": " not in text:
        return text, {}
    name, _, rest = text.partition(": ")
    name = name.strip()
    rest = rest.strip()
    if not rest:
        return name, {}
    try:
        parsed = json.loads(rest)
        if isinstance(parsed, dict):
            return name, parsed
    except json.JSONDecodeError:
        pass
    try:
        from core.llm.json_parse import parse_llm_json_object

        parsed = parse_llm_json_object(rest)
        if isinstance(parsed, dict):
            return name, parsed
    except ValueError:
        pass
    return name, {"raw": rest}


def format_action_content(action: str, action_input: dict[str, Any]) -> str:
    """持久化 ACTION 消息（JSON，避免 Python repr 导致 raw）。"""
    return f"{action}: {json.dumps(action_input, ensure_ascii=False)}"


def tool_call_id_for_action(action_msg_id: str) -> str:
    return f"call_{action_msg_id}"
