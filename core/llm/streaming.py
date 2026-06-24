"""LLM 流式响应解析辅助。"""

import json
import re
from collections.abc import Awaitable, Callable

OnDelta = Callable[[str], Awaitable[None]]


def _trim_partial_close_tag(text: str, tag: str = "thought") -> str:
    """截掉尾部未闭合的 </tag 片段，避免流式 emit 时泄漏 XML 标签。"""
    if not text:
        return text
    # 完整关闭标签之后的内容不应出现（已由 m_close 截断），这里只处理未闭合尾部
    lower = text.lower()
    close = f"</{tag.lower()}"
    idx = lower.rfind("<")
    if idx == -1:
        return text
    tail = lower[idx:]
    if close.startswith(tail) or tail.startswith(close[: len(tail)]):
        return text[:idx]
    if tail.startswith("<") and tag.lower().startswith(tail[1:]):
        return text[:idx]
    return text


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
        content = _trim_partial_close_tag(content)
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
