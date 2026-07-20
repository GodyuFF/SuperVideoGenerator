"""示例 Tool 注册器。"""

from __future__ import annotations

from typing import Any

from core.llm.agent.react_core import AgentRunContext
from core.llm.tools.registry import ToolRegistry
from core.llm.tools.result import ToolResult
from core.llm.tools.shared.input_common import merge_plan_tracking
from core.llm.tools.spec import ToolKind, ToolSpec
from core.store.memory import MemoryStore


def _handle_hello(
    store: MemoryStore,
    ctx: AgentRunContext,
    args: dict[str, Any],
) -> ToolResult:
    """示例只读 handler。"""
    del store, ctx
    name = str(args.get("name", "world"))
    text = f"Hello, {name}!"
    return ToolResult(
        observation=text,
        structured={"valid": True, "message": text},
    )


def register_tools(registry: ToolRegistry) -> None:
    """注册 ext.hello tool。"""
    if registry.has("ext.hello"):
        return
    registry.register(
        ToolSpec(
            name="ext.hello",
            description="示例扩展：问候",
            input_schema=merge_plan_tracking(
                {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                }
            ),
            output_schema={
                "type": "object",
                "properties": {"valid": {"type": "boolean"}, "message": {"type": "string"}},
                "required": ["valid"],
            },
            agent="common",
            kind=ToolKind.READ,
            handler=_handle_hello,
            logical_name="ext.hello",
            source="extension",
        )
    )
