"""LLM 流式响应解析辅助（Anthropic Messages API SSE）。"""

import json
import re
from collections.abc import Awaitable, Callable
from typing import Any

from core.llm.client.tool_calls import ToolCallResult

OnDelta = Callable[[str], Awaitable[None]]


def parse_anthropic_sse_data(data: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """解析 Anthropic SSE data JSON，返回 (text_delta, stream_meta)。"""
    meta: dict[str, Any] = {}
    text_delta = ""
    event_type = str(data.get("type", ""))

    if event_type == "message_start":
        message = data.get("message") or {}
        if message.get("usage"):
            meta["usage"] = message["usage"]
        if message.get("id"):
            meta["response_id"] = message["id"]

    elif event_type == "content_block_delta":
        delta = data.get("delta") or {}
        if delta.get("type") == "text_delta":
            text_delta = str(delta.get("text", ""))

    elif event_type == "message_delta":
        delta = data.get("delta") or {}
        if delta.get("stop_reason"):
            meta["finish_reason"] = delta["stop_reason"]
        if data.get("usage"):
            meta["usage"] = data["usage"]

    return text_delta, meta


def parse_anthropic_sse_line(line: str, *, current_event: str = "") -> tuple[str, dict[str, Any], str]:
    """解析 Anthropic SSE 行，返回 (text_delta, stream_meta, new_event)。"""
    if line.startswith("event:"):
        return "", {}, line[6:].strip()
    if not line.startswith("data:"):
        return "", {}, current_event
    payload = line[5:].strip()
    if not payload:
        return "", {}, current_event
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return "", {}, current_event
    text_delta, meta = parse_anthropic_sse_data(data)
    return text_delta, meta, current_event


# 兼容旧 OpenAI SSE 测试/调用（逐步迁移至 Anthropic）
def parse_sse_line(line: str) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """解析 SSE data 行，返回 (delta, stream_meta)。"""
    meta: dict[str, Any] = {}
    if not line.startswith("data:"):
        return None, meta
    payload = line[5:].strip()
    if not payload or payload == "[DONE]":
        return None, meta
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return None, meta

    # Anthropic Messages API
    event_type = data.get("type")
    if event_type in {
        "message_start",
        "content_block_start",
        "content_block_delta",
        "content_block_stop",
        "message_delta",
        "message_stop",
    }:
        _, anthropic_meta = parse_anthropic_sse_data(data)
        meta.update(anthropic_meta)
        out: dict[str, Any] = {}
        if event_type == "content_block_delta":
            delta = data.get("delta") or {}
            if delta.get("type") == "text_delta":
                out["content"] = str(delta.get("text", ""))
            elif delta.get("type") == "thinking_delta":
                out["anthropic_thinking_delta"] = {
                    "index": data.get("index", 0),
                    "thinking": str(delta.get("thinking", "")),
                }
            elif delta.get("type") == "input_json_delta":
                out["anthropic_input_json_delta"] = {
                    "index": data.get("index", 0),
                    "partial_json": str(delta.get("partial_json", "")),
                }
        elif event_type == "content_block_start":
            block = data.get("content_block") or {}
            if block.get("type") == "tool_use":
                out["anthropic_tool_use_start"] = {
                    "index": data.get("index", 0),
                    "id": str(block.get("id", "")),
                    "name": str(block.get("name", "")),
                    "input": block.get("input", {}),
                }
            elif block.get("type") == "thinking":
                out["anthropic_thinking_start"] = {
                    "index": data.get("index", 0),
                    "thinking": str(block.get("thinking", "")),
                    "signature": str(block.get("signature", "")),
                }
        return (out or None), meta

    # OpenAI Chat Completions（legacy）
    if data.get("usage"):
        meta["usage"] = data["usage"]
    if data.get("id"):
        meta["response_id"] = data["id"]
    choice = (data.get("choices") or [{}])[0]
    if choice.get("finish_reason"):
        meta["finish_reason"] = choice["finish_reason"]
    delta = choice.get("delta") or {}
    if not delta:
        return None, meta
    out = {}
    if delta.get("content") is not None:
        out["content"] = str(delta["content"])
    if delta.get("tool_calls"):
        out["tool_calls"] = delta["tool_calls"]
    return (out or None), meta


def parse_sse_delta(line: str) -> dict[str, Any] | None:
    """解析 SSE 行，返回 delta 片段。"""
    delta, _ = parse_sse_line(line)
    return delta


def parse_sse_data_line(line: str) -> str | None:
    """解析 SSE 行，返回 content delta；[DONE] 返回 None。"""
    delta = parse_sse_delta(line)
    if not delta or "content" not in delta:
        return None
    return delta["content"]


def extract_tool_call_stream_parts(delta: dict[str, Any]) -> list[str]:
    """从 tool_calls SSE delta 提取文本片段（thinking 与 content 均保留，供通用场景）。"""
    parts: list[str] = []
    thinking_start = delta.get("anthropic_thinking_start")
    if isinstance(thinking_start, dict):
        text = str(thinking_start.get("thinking", ""))
        if text:
            parts.append(text)
    thinking_delta = delta.get("anthropic_thinking_delta")
    if isinstance(thinking_delta, dict):
        text = str(thinking_delta.get("thinking", ""))
        if text:
            parts.append(text)
    if delta.get("content"):
        parts.append(str(delta["content"]))
    return parts


def extract_complete_stream_parts(delta: dict[str, Any]) -> tuple[str, str]:
    """从 SSE delta 拆分正文 text 与 extended thinking 片段（供 complete/complete_json 聚合）。"""
    text = str(delta.get("content", "")) if delta.get("content") else ""
    thinking_parts: list[str] = []
    for key in ("anthropic_thinking_start", "anthropic_thinking_delta"):
        block = delta.get(key)
        if isinstance(block, dict):
            part = str(block.get("thinking", ""))
            if part:
                thinking_parts.append(part)
    return text, "".join(thinking_parts)


class ThoughtStreamExtractor:
    """从 tool_calls 流提取 ReAct thought 增量，thinking 激活后忽略 content 镜像避免重复打印。"""

    def __init__(self) -> None:
        self._saw_thinking = False

    def feed(self, delta: dict[str, Any]) -> list[str]:
        """摄入单条 SSE delta，返回应推送给前端的 thought 文本片段。"""
        parts: list[str] = []
        thinking_start = delta.get("anthropic_thinking_start")
        if isinstance(thinking_start, dict):
            text = str(thinking_start.get("thinking", ""))
            if text:
                self._saw_thinking = True
                parts.append(text)
        thinking_delta = delta.get("anthropic_thinking_delta")
        if isinstance(thinking_delta, dict):
            text = str(thinking_delta.get("thinking", ""))
            if text:
                self._saw_thinking = True
                parts.append(text)
        if not self._saw_thinking and delta.get("content"):
            parts.append(str(delta["content"]))
        return parts


class ToolCallAccumulator:
    """聚合流式 tool_calls / tool_use 与 assistant content。"""

    def __init__(self) -> None:
        self._content_parts: list[str] = []
        self._thinking_parts: list[str] = []
        self._thinking_signature: str = ""
        self._tool_calls: dict[int, dict[str, Any]] = {}
        self._stream_meta: dict[str, Any] = {}
        self._tool_input_locked: set[int] = set()

    def absorb_meta(self, meta: dict[str, Any]) -> None:
        if not meta:
            return
        thinking_delta = meta.pop("anthropic_thinking_delta", None)
        thinking_start = meta.pop("anthropic_thinking_start", None)
        if thinking_start:
            self._apply_thinking_start(thinking_start)
        if thinking_delta:
            self._apply_thinking_delta(thinking_delta)
        if meta:
            self._stream_meta.update(meta)

    def _apply_thinking_start(self, payload: dict[str, Any]) -> None:
        thinking = str(payload.get("thinking", ""))
        if thinking:
            self._thinking_parts.append(thinking)
        signature = str(payload.get("signature", ""))
        if signature:
            self._thinking_signature = signature

    def _apply_thinking_delta(self, payload: dict[str, Any]) -> None:
        part = str(payload.get("thinking", ""))
        if part:
            self._thinking_parts.append(part)

    def stream_meta(self) -> dict[str, Any]:
        return dict(self._stream_meta)

    def _ensure_tool(self, idx: int) -> dict[str, Any]:
        return self._tool_calls.setdefault(
            idx,
            {"id": "", "type": "function", "function": {"name": "", "arguments": ""}},
        )

    def feed(self, delta: dict[str, Any]) -> str:
        """摄入 delta，返回本次 content 增量（供 on_delta）。"""
        content_delta = ""
        if delta.get("content"):
            content_delta = str(delta["content"])
            self._content_parts.append(content_delta)

        thinking_start = delta.get("anthropic_thinking_start")
        if isinstance(thinking_start, dict):
            self._apply_thinking_start(thinking_start)

        thinking_delta = delta.get("anthropic_thinking_delta")
        if isinstance(thinking_delta, dict):
            self._apply_thinking_delta(thinking_delta)

        tool_start = delta.get("anthropic_tool_use_start")
        if isinstance(tool_start, dict):
            idx = int(tool_start.get("index", 0))
            slot = self._ensure_tool(idx)
            if tool_start.get("id"):
                slot["id"] = str(tool_start["id"])
            if tool_start.get("name"):
                slot["function"]["name"] = str(tool_start["name"])
            tool_input = tool_start.get("input")
            if isinstance(tool_input, dict) and tool_input:
                slot["function"]["arguments"] = json.dumps(tool_input, ensure_ascii=False)
                self._tool_input_locked.add(idx)

        input_delta = delta.get("anthropic_input_json_delta")
        if isinstance(input_delta, dict):
            idx = int(input_delta.get("index", 0))
            if idx in self._tool_input_locked:
                pass
            else:
                slot = self._ensure_tool(idx)
                slot["function"]["arguments"] += str(input_delta.get("partial_json", ""))

        for tc in delta.get("tool_calls") or []:
            if not isinstance(tc, dict):
                continue
            idx = int(tc.get("index", 0))
            slot = self._ensure_tool(idx)
            if tc.get("id"):
                slot["id"] = str(tc["id"])
            if tc.get("type"):
                slot["type"] = str(tc["type"])
            fn = tc.get("function") or {}
            if fn.get("name"):
                slot["function"]["name"] = str(fn["name"])
            if fn.get("arguments"):
                slot["function"]["arguments"] += str(fn["arguments"])
        return content_delta

    def thinking(self) -> str:
        return "".join(self._thinking_parts)

    def build(self) -> ToolCallResult:
        tool_calls = [self._tool_calls[i] for i in sorted(self._tool_calls)]
        content = "".join(self._content_parts)
        thinking = self.thinking()
        wire_blocks: list[dict[str, Any]] = []
        if thinking or self._thinking_signature:
            block: dict[str, Any] = {"type": "thinking", "thinking": thinking}
            if self._thinking_signature:
                block["signature"] = self._thinking_signature
            wire_blocks.append(block)
        elif tool_calls:
            wire_blocks.append({"type": "thinking", "thinking": ""})
        if content:
            wire_blocks.append({"type": "text", "text": content})
        if wire_blocks:
            raw_content: str | list[dict[str, Any]] = wire_blocks
        else:
            raw_content = content
        raw: dict[str, Any] = {"role": "assistant", "content": raw_content}
        if tool_calls:
            raw["tool_calls"] = tool_calls
        if self._stream_meta:
            raw["stream_meta"] = dict(self._stream_meta)
        return ToolCallResult(
            content=content,
            thinking=thinking,
            tool_calls=tool_calls,
            raw_message=raw,
        )


class ReactJsonThoughtParser:
    """从流式 JSON ReAct 响应中提取 thought 字段增量（legacy 测试用）。"""

    def __init__(self) -> None:
        self._raw = ""
        self._emitted = 0

    def feed(self, chunk: str) -> str:
        self._raw += chunk
        match = re.search(r'"thought"\s*:\s*"', self._raw)
        if not match:
            return ""
        start = match.end()
        chars: list[str] = []
        i = start
        while i < len(self._raw):
            ch = self._raw[i]
            if ch == "\\" and i + 1 < len(self._raw):
                nxt = self._raw[i + 1]
                escape_map = {
                    "n": "\n",
                    "r": "\r",
                    "t": "\t",
                    "b": "\b",
                    "f": "\f",
                    '"': '"',
                    "\\": "\\",
                    "/": "/",
                }
                chars.append(escape_map.get(nxt, nxt))
                i += 2
                continue
            if ch == '"':
                break
            chars.append(ch)
            i += 1
        text = "".join(chars)
        new_text = text[self._emitted :]
        self._emitted = len(text)
        return new_text
