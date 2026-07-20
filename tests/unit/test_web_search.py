"""web_search 单元测试。"""

from unittest.mock import MagicMock

import pytest

from core.llm.agent.react_core import AgentRunContext
from core.store.memory import MemoryStore
from core.llm.tools.registry import ToolRegistry
from core.llm.tools.web_search.models import WebSearchResponse, WebSearchResult
from core.llm.tools.web_search.providers.duckduckgo import parse_duckduckgo_html
from core.llm.tools.web_search.providers.tavily import TavilyProvider
from core.llm.tools.web_search.schemas import (
    web_search_input_schema,
    web_search_output_schema,
    web_search_react_input_schema,
)
from core.llm.tools.web_search.service import search_web
from core.llm.tools.web_search.settings import WebSearchSettings
from core.llm.tools.web_search.tool import (
    WEB_SEARCH_TOOL_NAME,
    build_web_search_tool_spec,
    handle_web_search,
)


def _react_args(**overrides: object) -> dict:
    """构造符合 ReAct schema 的 web_search 参数。"""
    base = {
        "query": "hello",
        "observation": "检索参考资料",
        "plan_status": "正在联网搜索背景资料",
        "remaining_plan": ["整理结果", "撰写剧本"],
        "max_results": 3,
    }
    base.update(overrides)
    return base

_SAMPLE_DDG_HTML = """
<html><body>
<div class="result">
  <a class="result__a" href="https://duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fa">Example A</a>
  <a class="result__snippet">Snippet for example A with enough text.</a>
</div>
<div class="result">
  <a class="result__a" href="https://example.com/b">Example B</a>
  <a class="result__snippet">Snippet for example B.</a>
</div>
</body></html>
"""

_SAMPLE_TAVILY_JSON = {
    "results": [
        {
            "title": "Tavily Result",
            "url": "https://tavily.example/doc",
            "content": "Tavily snippet body.",
            "source": "tavily",
        }
    ]
}


def test_web_search_schemas():
    """领域 schema 与 ReAct schema 字段一致，避免双重校验互相打架。"""
    inp = web_search_input_schema()
    assert inp["required"] == ["query"]
    assert "max_results" in inp["properties"]
    assert inp.get("additionalProperties") is True

    react = web_search_react_input_schema()
    assert set(react["required"]) == {
        "query",
        "observation",
        "plan_status",
        "remaining_plan",
    }
    assert "plan_status" in react["properties"]
    assert react.get("additionalProperties") is True

    out = web_search_output_schema()
    assert "results" in out["properties"]
    assert out["properties"]["results"]["type"] == "array"


def test_parse_duckduckgo_html():
    results = parse_duckduckgo_html(_SAMPLE_DDG_HTML, max_results=5)
    assert len(results) >= 1
    assert results[0].title == "Example A"
    assert results[0].url == "https://example.com/a"
    assert "Snippet" in results[0].snippet


def test_search_web_duckduckgo(monkeypatch):
    class FakeResponse:
        status_code = 200
        text = _SAMPLE_DDG_HTML

        def raise_for_status(self) -> None:
            return None

    fake_client = MagicMock()
    fake_client.post.return_value = FakeResponse()
    fake_client.__enter__.return_value = fake_client
    fake_client.__exit__.return_value = False

    monkeypatch.setattr(
        "core.llm.tools.web_search.providers.duckduckgo.httpx.Client",
        lambda **kwargs: fake_client,
    )

    response = search_web(
        "test query",
        settings=WebSearchSettings(provider="duckduckgo"),
    )
    assert response.provider == "duckduckgo"
    assert response.count >= 1
    assert response.results[0].url.startswith("https://")


def test_search_web_tavily(monkeypatch):
    class FakeResponse:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self):
            return _SAMPLE_TAVILY_JSON

    fake_client = MagicMock()
    fake_client.post.return_value = FakeResponse()
    fake_client.__enter__.return_value = fake_client
    fake_client.__exit__.return_value = False

    monkeypatch.setattr(
        "core.llm.tools.web_search.providers.tavily.httpx.Client",
        lambda **kwargs: fake_client,
    )

    response = search_web(
        "ai video",
        settings=WebSearchSettings(provider="tavily", api_key="tvly-test"),
    )
    assert response.provider == "tavily"
    assert response.count == 1
    assert response.results[0].title == "Tavily Result"


def test_handle_web_search_success(monkeypatch):
    monkeypatch.setattr(
        "core.llm.tools.web_search.tool.search_web",
        lambda query, max_results=None: WebSearchResponse(
            query=query,
            provider="duckduckgo",
            count=1,
            results=[
                WebSearchResult(
                    title="Hit",
                    url="https://hit.example",
                    snippet="body",
                    source="duckduckgo",
                )
            ],
        ),
    )
    store = MemoryStore()
    ctx = AgentRunContext(
        task_brief="",
        work_context={},
        script_id="s1",
        step_id="step1",
        agent_name="utility",
    )
    result = handle_web_search(store, ctx, _react_args())
    assert result.ok
    assert result.structured["count"] == 1
    assert "Hit" in result.observation


def test_handle_web_search_empty_query():
    """空白 query 应失败（先过 schema，再过业务校验）。"""
    store = MemoryStore()
    ctx = AgentRunContext(
        task_brief="",
        work_context={},
        script_id="s1",
        step_id="step1",
        agent_name="utility",
    )
    result = handle_web_search(store, ctx, _react_args(query="   "))
    assert not result.ok


def test_handle_web_search_rejects_missing_plan_fields():
    """缺少 plan_status 时应与 Registry 校验一致地拒绝。"""
    store = MemoryStore()
    ctx = AgentRunContext(
        task_brief="",
        work_context={},
        script_id="s1",
        step_id="step1",
        agent_name="utility",
    )
    result = handle_web_search(
        store,
        ctx,
        {"query": "hello", "observation": "检索", "max_results": 3},
    )
    assert not result.ok
    assert "plan_status" in result.observation


@pytest.mark.asyncio
async def test_registry_call_web_search_with_plan_tracking(monkeypatch):
    """Registry → handler 双重校验对含 plan 字段的调用应通过。"""
    monkeypatch.setattr(
        "core.llm.tools.web_search.tool.search_web",
        lambda query, max_results=None: WebSearchResponse(
            query=query,
            provider="duckduckgo",
            count=1,
            results=[
                WebSearchResult(
                    title="Hit",
                    url="https://hit.example",
                    snippet="body",
                    source="duckduckgo",
                )
            ],
        ),
    )
    registry = ToolRegistry()
    registry.register(build_web_search_tool_spec())
    store = MemoryStore()
    ctx = AgentRunContext(
        task_brief="",
        work_context={},
        script_id="s1",
        step_id="step1",
        agent_name="common",
    )
    result = await registry.call_tool(
        WEB_SEARCH_TOOL_NAME, _react_args(), ctx, store
    )
    assert result.ok
    assert result.structured["count"] == 1


def test_build_web_search_tool_spec_not_in_default_registry():
    """ToolSpec 使用统一 ReAct schema；bootstrap 默认不注册。"""
    spec = build_web_search_tool_spec()
    assert spec.name == WEB_SEARCH_TOOL_NAME
    assert spec.kind.value == "read"
    assert set(spec.input_schema["required"]) == {
        "query",
        "observation",
        "plan_status",
        "remaining_plan",
    }

    registry = ToolRegistry()
    assert not registry.has(WEB_SEARCH_TOOL_NAME)

    # 可手动注册，但 bootstrap 默认不包含
    registry.register(spec)
    assert registry.has(WEB_SEARCH_TOOL_NAME)


def test_tavily_requires_api_key():
    provider = TavilyProvider(WebSearchSettings(provider="tavily", api_key=""))
    with pytest.raises(ValueError, match="API"):
        provider.search("q", max_results=1)
