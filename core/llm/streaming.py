"""LLM 流式响应解析辅助。"""

import json
import re
from collections.abc import Awaitable, Callable

OnDelta = Callable[[str], Awaitable[None]]


def parse_sse_data_line(line: str) -> str | None:
    """解析 OpenAI 兼容 SSE 行，返回 content delta；[DONE] 返回 None。"""
    if not line.startswith("data:"):
        return None
    payload = line[5:].strip()
    if not payload or payload == "[DONE]":
        return None
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return None
    choice = (data.get("choices") or [{}])[0]
    delta = choice.get("delta") or {}
    content = delta.get("content")
    if content is None:
        return None
    return str(content)


class ReactJsonThoughtParser:
    """从流式 JSON ReAct 响应中提取 thought 字段增量。"""

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
