"""联网搜索 Provider 抽象。"""

from __future__ import annotations

from abc import ABC, abstractmethod

from core.llm.tools.web_search.models import WebSearchResult
from core.llm.tools.web_search.settings import WebSearchSettings


class WebSearchProviderBase(ABC):
    """搜索后端接口。"""

    name: str

    def __init__(self, settings: WebSearchSettings) -> None:
        self._settings = settings

    @abstractmethod
    def search(self, query: str, *, max_results: int) -> list[WebSearchResult]:
        raise NotImplementedError
