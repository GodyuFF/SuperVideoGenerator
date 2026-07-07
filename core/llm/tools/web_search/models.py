"""联网搜索领域模型。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class WebSearchResult(BaseModel):
    """单条搜索结果。"""

    title: str
    url: str
    snippet: str = ""
    source: str = ""


class WebSearchResponse(BaseModel):
    """搜索响应载荷。"""

    query: str
    provider: str
    count: int
    results: list[WebSearchResult] = Field(default_factory=list)
