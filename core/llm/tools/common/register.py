"""全 Agent 共享只读 tools 注册。"""

from core.llm.tools.registry import ToolRegistry
from core.llm.tools.web_fetch.tool import build_read_webpage_tool_spec


def register_common_tools(registry: ToolRegistry) -> None:
    registry.register(build_read_webpage_tool_spec())
