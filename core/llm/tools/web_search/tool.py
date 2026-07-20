"""web_search tool handler 与 ToolSpec 工厂（经 svg.tools 扩展注册）。"""

from __future__ import annotations

from typing import Any

from core.llm.agent.react_core import AgentRunContext
from core.store.memory import MemoryStore
from core.llm.tools.result import ToolResult
from core.llm.tools.spec import ToolKind, ToolSpec
from core.llm.tools.validators import validate_against_schema
from core.llm.tools.web_search.schemas import (
    web_search_output_schema,
    web_search_react_input_schema,
)
from core.llm.tools.web_search.service import search_web

WEB_SEARCH_TOOL_NAME = "web_search"


def _format_observation(query: str, provider: str, results: list[dict[str, Any]]) -> str:
    """将搜索结果格式化为 ReAct observation 文本。"""
    if not results:
        return f"搜索「{query}」未找到结果（provider={provider}）。"
    lines = [f"搜索「{query}」共 {len(results)} 条（{provider}）："]
    for idx, item in enumerate(results, start=1):
        title = str(item.get("title", ""))
        url = str(item.get("url", ""))
        snippet = str(item.get("snippet", "")).strip()
        lines.append(f"{idx}. {title}\n   {url}")
        if snippet:
            preview = snippet if len(snippet) <= 160 else snippet[:160] + "…"
            lines.append(f"   {preview}")
    return "\n".join(lines)


def handle_web_search(
    store: MemoryStore,
    ctx: AgentRunContext,
    args: dict[str, Any],
) -> ToolResult:
    """执行联网搜索；输入须与 Registry / ReAct schema 一致（含 plan 跟踪字段）。"""
    del store, ctx  # 只读工具，不读写 Store
    try:
        validate_against_schema(args, web_search_react_input_schema(), label="输入")
    except ValueError as e:
        return ToolResult(
            observation=str(e),
            structured={"error": str(e), "valid": False},
            ok=False,
        )

    query = str(args.get("query", "")).strip()
    if not query:
        return ToolResult(
            observation="搜索 query 不能为空",
            structured={"error": "empty query", "valid": False},
            ok=False,
        )

    max_results = args.get("max_results", 5)
    try:
        max_results = int(max_results)
    except (TypeError, ValueError):
        max_results = 5

    try:
        response = search_web(query, max_results=max_results)
    except (ValueError, RuntimeError) as e:
        return ToolResult(
            observation=str(e),
            structured={"error": str(e), "valid": False, "query": query},
            ok=False,
        )

    structured = response.model_dump()
    try:
        validate_against_schema(structured, web_search_output_schema(), label="输出")
    except ValueError as e:
        return ToolResult(
            observation=str(e),
            structured={"error": str(e), "valid": False, "query": query},
            ok=False,
        )

    observation = _format_observation(
        response.query,
        response.provider,
        structured["results"],
    )
    return ToolResult(observation=observation, structured=structured)


def build_web_search_tool_spec() -> ToolSpec:
    """构建 ToolSpec，供扩展注册到 Registry。"""
    return ToolSpec(
        name=WEB_SEARCH_TOOL_NAME,
        description="联网搜索互联网，返回标题、链接与摘要（只读）",
        input_schema=web_search_react_input_schema(),
        output_schema=web_search_output_schema(),
        agent="utility",
        kind=ToolKind.READ,
        handler=handle_web_search,
        logical_name="utility.web_search",
    )
