"""联网搜索编排入口。"""

from __future__ import annotations

import httpx

from core.llm.tools.web_search.models import WebSearchResponse
from core.llm.tools.web_search.providers.duckduckgo import DuckDuckGoProvider
from core.llm.tools.web_search.providers.tavily import TavilyProvider
from core.llm.tools.web_search.settings import WebSearchSettings, get_web_search_settings


def _build_provider(settings: WebSearchSettings):
    provider_name = settings.resolved_provider()
    if provider_name == "tavily":
        return TavilyProvider(settings)
    return DuckDuckGoProvider(settings)


def search_web(
    query: str,
    *,
    max_results: int | None = None,
    settings: WebSearchSettings | None = None,
) -> WebSearchResponse:
    """执行联网搜索并返回结构化结果。"""
    q = query.strip()
    if not q:
        raise ValueError("搜索 query 不能为空")

    cfg = settings or get_web_search_settings()
    limit = max_results if max_results is not None else cfg.max_results
    limit = max(1, min(int(limit), 20))

    provider = _build_provider(cfg)
    try:
        results = provider.search(q, max_results=limit)
    except httpx.HTTPError as e:
        raise RuntimeError(f"联网搜索 HTTP 失败（{provider.name}）：{e}") from e

    return WebSearchResponse(
        query=q,
        provider=provider.name,
        count=len(results),
        results=results,
    )
