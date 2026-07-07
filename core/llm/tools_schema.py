"""OpenAI function tools 定义：ReAct 决策与行动执行（re-export canonical registry）。"""

from core.llm.prompt.tools.registry import (
    build_action_tool,
    build_master_react_tools,
    build_react_tool,
    build_sub_agent_react_tools,
    tool_choice_force,
    tool_spec_for_action,
)

__all__ = [
    "build_action_tool",
    "build_master_react_tools",
    "build_react_tool",
    "build_sub_agent_react_tools",
    "tool_choice_force",
    "tool_spec_for_action",
]
