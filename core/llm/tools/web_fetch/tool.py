"""read_webpage tool handler。"""

from __future__ import annotations

from typing import Any

from core.llm.agent.react_core import AgentRunContext
from core.store.memory import MemoryStore
from core.llm.tools.result import ToolResult
from core.llm.tools.spec import ToolKind, ToolSpec
from core.llm.tools.validators import validate_against_schema
from core.llm.tools.web_fetch.schemas import (
    read_webpage_input_schema,
    read_webpage_output_schema,
)
from core.llm.tools.web_fetch.service import WebFetchError, fetch_webpage

READ_WEBPAGE_TOOL_NAME = "read_webpage"
COMMON_AGENT = "common"


def _format_observation(page: dict[str, Any]) -> str:
    title = page.get("title", "")
    url = page.get("url", "")
    content = str(page.get("content", "")).strip()
    truncated = page.get("truncated", False)
    method = page.get("extraction_method", "")
    lines = [f"已读取网页「{title}」", f"URL: {url}"]
    if method:
        lines.append(f"提取方式: {method}")
    if truncated:
        lines.append(f"（正文已截断，原文约 {page.get('content_length', 0)} 字）")
    preview = content if len(content) <= 1200 else content[:1200] + "…"
    lines.append("")
    lines.append(preview)
    return "\n".join(lines)


def handle_read_webpage(
    store: MemoryStore,
    ctx: AgentRunContext,
    args: dict[str, Any],
) -> ToolResult:
    del store, ctx
    try:
        validate_against_schema(args, read_webpage_input_schema(), label="输入")
    except ValueError as e:
        return ToolResult(
            observation=str(e),
            structured={"error": str(e), "valid": False},
            ok=False,
        )

    url = str(args.get("url", "")).strip()
    max_chars = args.get("max_chars")
    if max_chars is not None:
        try:
            max_chars = int(max_chars)
        except (TypeError, ValueError):
            max_chars = None

    try:
        page = fetch_webpage(url, max_chars=max_chars)
    except WebFetchError as e:
        return ToolResult(
            observation=str(e),
            structured={"error": str(e), "valid": False, "url": url},
            ok=False,
        )

    structured = {
        "url": page.url,
        "title": page.title,
        "content": page.content,
        "truncated": page.truncated,
        "content_length": page.content_length,
        "extraction_method": page.extraction_method,
        "valid": True,
    }
    try:
        validate_against_schema(structured, read_webpage_output_schema(), label="输出")
    except ValueError as e:
        return ToolResult(
            observation=str(e),
            structured={"error": str(e), "valid": False, "url": url},
            ok=False,
        )

    return ToolResult(
        observation=_format_observation(structured),
        structured=structured,
    )


def build_read_webpage_tool_spec() -> ToolSpec:
    return ToolSpec(
        name=READ_WEBPAGE_TOOL_NAME,
        description="读取指定 URL 的网页正文（只读，http/https）",
        input_schema=read_webpage_input_schema(),
        output_schema=read_webpage_output_schema(),
        agent=COMMON_AGENT,
        kind=ToolKind.READ,
        handler=handle_read_webpage,
        logical_name="common.read_webpage",
    )
