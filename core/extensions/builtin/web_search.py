"""web_search 内置扩展：注册联网搜索只读 Tool。"""

from __future__ import annotations

from core.llm.tools.registry import ToolRegistry
from core.llm.tools.web_search.tool import WEB_SEARCH_TOOL_NAME, build_web_search_tool_spec


def register_tools(registry: ToolRegistry) -> None:
    """将 web_search 注册为 common 只读 Tool。"""
    spec = build_web_search_tool_spec()
    # 覆盖 agent 为 common，便于 Skill manifest 按 Agent 挂载
    from dataclasses import replace

    spec = replace(
        spec,
        agent="common",
        source="extension",
    )
    if registry.has(WEB_SEARCH_TOOL_NAME):
        return
    registry.register(spec)
