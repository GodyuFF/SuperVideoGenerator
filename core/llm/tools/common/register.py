"""全 Agent 共享只读 tools 注册。"""

from core.llm.tools.common.skill_refs import (
    build_list_skill_refs_tool_spec,
    build_read_skill_ref_tool_spec,
)
from core.llm.tools.registry import ToolRegistry
from core.llm.tools.web_fetch.tool import build_read_webpage_tool_spec


def register_common_tools(registry: ToolRegistry) -> None:
    """注册 common Agent 只读工具（含 Skill 渐进加载）。"""
    registry.register(build_read_webpage_tool_spec())
    registry.register(build_list_skill_refs_tool_spec())
    registry.register(build_read_skill_ref_tool_spec())
