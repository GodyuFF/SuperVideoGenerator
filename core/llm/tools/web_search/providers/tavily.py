"""Tavily Search API（需 API Key，适合生产）。"""

from __future__ import annotations

import httpx

from core.llm.tools.web_search.models import WebSearchResult
from core.llm.tools.web_search.providers.base import WebSearchProviderBase

_TAVILY_URL = "https://api.tavily.com/search"


class TavilyProvider(WebSearchProviderBase):
    name = "tavily"

    def search(self, query: str, *, max_results: int) -> list[WebSearchResult]:
        api_key = self._settings.resolved_api_key()
        if not api_key:
            raise ValueError("Tavily 搜索需要配置 SVG_WEB_SEARCH_API_KEY 或 TAVILY_API_KEY")

        payload = {
            "api_key": api_key,
            "query": query,
            "max_results": max_results,
            "search_depth": "basic",
            "include_answer": False,
        }
        with httpx.Client(timeout=self._settings.timeout_sec) as client:
            response = client.post(_TAVILY_URL, json=payload)
            response.raise_for_status()
            data = response.json()

        items = data.get("results") or []
        results: list[WebSearchResult] = []
        for item in items[:max_results]:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title", "")).strip()
            url = str(item.get("url", "")).strip()
            if not title or not url:
                continue
            snippet = str(item.get("content", item.get("snippet", ""))).strip()
            results.append(
                WebSearchResult(
                    title=title,
                    url=url,
                    snippet=snippet,
                    source=str(item.get("source", "tavily")),
                )
            )
        return results
