"""DuckDuckGo HTML Lite 搜索（无需 API Key，适合开发/测试）。"""

from __future__ import annotations

import html
import re
from html.parser import HTMLParser
from urllib.parse import parse_qs, unquote, urlparse

import httpx

from core.llm.tools.web_search.models import WebSearchResult
from core.llm.tools.web_search.providers.base import WebSearchProviderBase

_DDG_HTML_URL = "https://html.duckduckgo.com/html/"
_RESULT_LINK_RE = re.compile(
    r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
_SNIPPET_RE = re.compile(
    r'class="result__snippet"[^>]*>(.*?)</(?:a|td|div)>',
    re.IGNORECASE | re.DOTALL,
)


def _strip_tags(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text)


def _normalize_ddg_url(raw_href: str) -> str:
    href = html.unescape(raw_href.strip())
    if href.startswith("//"):
        href = f"https:{href}"
    parsed = urlparse(href)
    if "duckduckgo.com" in parsed.netloc and parsed.path == "/l/":
        target = parse_qs(parsed.query).get("uddg", [""])[0]
        if target:
            return unquote(target)
    return href


class _DDGHTMLParser(HTMLParser):
    """从 DuckDuckGo HTML 结果页提取链接与摘要。"""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._results: list[WebSearchResult] = []
        self._capture_title = False
        self._capture_snippet = False
        self._current_href = ""
        self._title_parts: list[str] = []
        self._snippet_parts: list[str] = []

    @property
    def results(self) -> list[WebSearchResult]:
        return self._results

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {k: v for k, v in attrs if v is not None}
        class_name = attr_map.get("class", "")
        if tag == "a" and "result__a" in class_name:
            self._capture_title = True
            self._current_href = _normalize_ddg_url(attr_map.get("href", ""))
            self._title_parts = []
            return
        if "result__snippet" in class_name:
            self._capture_snippet = True
            self._snippet_parts = []

    def handle_endtag(self, tag: str) -> None:
        if self._capture_title and tag == "a":
            title = _strip_tags("".join(self._title_parts)).strip()
            if title and self._current_href:
                self._results.append(
                    WebSearchResult(
                        title=title,
                        url=self._current_href,
                        snippet="",
                        source="duckduckgo",
                    )
                )
            self._capture_title = False
            self._current_href = ""
            self._title_parts = []
            return
        if self._capture_snippet and tag in {"a", "td", "div"}:
            snippet = _strip_tags("".join(self._snippet_parts)).strip()
            if snippet and self._results:
                last = self._results[-1]
                if not last.snippet:
                    self._results[-1] = last.model_copy(update={"snippet": snippet})
            self._capture_snippet = False
            self._snippet_parts = []

    def handle_data(self, data: str) -> None:
        if self._capture_title:
            self._title_parts.append(data)
        if self._capture_snippet:
            self._snippet_parts.append(data)


def parse_duckduckgo_html(html_text: str, *, max_results: int) -> list[WebSearchResult]:
    parser = _DDGHTMLParser()
    parser.feed(html_text)
    results = parser.results
    if results:
        return results[:max_results]

    # 正则回退：HTMLParser 未命中时仍尝试解析
    links = list(_RESULT_LINK_RE.finditer(html_text))
    snippets = list(_SNIPPET_RE.finditer(html_text))
    fallback: list[WebSearchResult] = []
    for idx, match in enumerate(links[:max_results]):
        title = _strip_tags(match.group(2)).strip()
        url = _normalize_ddg_url(match.group(1))
        snippet = ""
        if idx < len(snippets):
            snippet = _strip_tags(snippets[idx].group(1)).strip()
        if title and url:
            fallback.append(
                WebSearchResult(
                    title=title,
                    url=url,
                    snippet=snippet,
                    source="duckduckgo",
                )
            )
    return fallback


class DuckDuckGoProvider(WebSearchProviderBase):
    name = "duckduckgo"

    def search(self, query: str, *, max_results: int) -> list[WebSearchResult]:
        headers = {
            "User-Agent": self._settings.user_agent,
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
        with httpx.Client(
            timeout=self._settings.timeout_sec,
            follow_redirects=True,
            headers=headers,
        ) as client:
            response = client.post(
                _DDG_HTML_URL,
                data={"q": query, "b": "", "kl": "wt-wt"},
            )
            response.raise_for_status()
        return parse_duckduckgo_html(response.text, max_results=max_results)
