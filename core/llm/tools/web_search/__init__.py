"""联网搜索能力（独立 tool 实现，暂未注册到 Agent Registry）。"""

from core.llm.tools.web_search.models import WebSearchResponse, WebSearchResult
from core.llm.tools.web_search.service import search_web
from core.llm.tools.web_search.tool import (
    WEB_SEARCH_TOOL_NAME,
    build_web_search_tool_spec,
    handle_web_search,
)

__all__ = [
    "WEB_SEARCH_TOOL_NAME",
    "WebSearchResponse",
    "WebSearchResult",
    "build_web_search_tool_spec",
    "handle_web_search",
    "search_web",
]
