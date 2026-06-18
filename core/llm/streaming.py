"""LLM 流式响应解析辅助。"""

import json
import re
from collections.abc import Awaitable, Callable

OnDelta = Callable[[str], Awaitable[None]]


class ReactXmlThoughtParser:
    """从流式 XML ReAct 响应中提取 <thought> 正文增量。"""

    def __init__(self) -> None:
        self._raw = ""
        self._emitted = 0

    def feed(self, chunk: str) -> str:
        self._raw += chunk
        m_open = re.search(r"<thought>\s*", self._raw, re.IGNORECASE)
        if not m_open:
            return ""
        start = m_open.end()
        m_close = re.search(r"</thought>", self._raw[start:], re.IGNORECASE)
        content = (
            self._raw[start : start + m_close.start()]
            if m_close
            else self._raw[start:]
        )
        new_text = content[self._emitted :]
        self._emitted = len(content)
        return new_text


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
