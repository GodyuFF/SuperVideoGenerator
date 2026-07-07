"""网页读取 tool。"""

from core.llm.tools.web_fetch.extractors import extract_title, html_to_text
from core.llm.tools.web_fetch.service import WebFetchError, fetch_webpage
from core.llm.tools.web_fetch.tool import (
    COMMON_AGENT,
    READ_WEBPAGE_TOOL_NAME,
    build_read_webpage_tool_spec,
    handle_read_webpage,
)

__all__ = [
    "COMMON_AGENT",
    "READ_WEBPAGE_TOOL_NAME",
    "WebFetchError",
    "build_read_webpage_tool_spec",
    "fetch_webpage",
    "handle_read_webpage",
]
