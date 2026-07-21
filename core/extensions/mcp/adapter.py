"""MCP tools/list 与 tools/call 映射为 ToolSpec / ToolResult。"""

from __future__ import annotations

from typing import Any

from core.extensions.mcp.client import McpConnectionManager, McpSessionHandle
from core.extensions.mcp.config import McpServerConfig
from core.extensions.mcp.guard import (
    mcp_result_to_observation,
    mcp_tool_registry_name,
    parse_mcp_tool_name,
)
from core.llm.agent.react_core import AgentRunContext
from core.llm.tools.result import ToolResult
from core.llm.tools.shared.input_common import merge_plan_tracking
from core.llm.tools.spec import ToolKind, ToolSpec
from core.store.memory import MemoryStore


def _generic_mcp_output_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "valid": {"type": "boolean"},
            "source": {"type": "string"},
            "is_error": {"type": "boolean"},
            "payload": {"type": "object"},
        },
        "required": ["valid"],
    }


def build_mcp_tool_specs(
    config: McpServerConfig,
    handle: McpSessionHandle,
    manager: McpConnectionManager,
) -> list[ToolSpec]:
    """将 MCP list_tools 转为 ToolSpec 列表。"""
    specs: list[ToolSpec] = []
    allowed = set(config.allowed_tools or [])
    for tool in handle.tools:
        tool_name = str(getattr(tool, "name", ""))
        if not tool_name:
            continue
        if allowed and tool_name not in allowed:
            continue
        registry_name = mcp_tool_registry_name(config.id, tool_name)
        if config.tool_prefix:
            registry_name = f"{config.tool_prefix}.{tool_name}"
        description = str(getattr(tool, "description", "") or f"MCP tool {tool_name}")
        input_schema = dict(getattr(tool, "inputSchema", None) or {"type": "object", "properties": {}})
        input_schema = merge_plan_tracking(input_schema, required=False)
        handler = _make_mcp_handler(manager, config.id, tool_name, config.timeout_sec)
        specs.append(
            ToolSpec(
                name=registry_name,
                description=description,
                input_schema=input_schema,
                output_schema=_generic_mcp_output_schema(),
                agent=config.agent,
                kind=ToolKind.READ,
                handler=handler,
                logical_name=f"mcp.{config.id}.{tool_name}",
                source="mcp",
            )
        )
    return specs


def _make_mcp_handler(
    manager: McpConnectionManager,
    server_id: str,
    tool_name: str,
    timeout_sec: float,
):
    """创建 MCP 代理 handler。"""

    async def _handler(
        store: MemoryStore,
        ctx: AgentRunContext,
        args: dict[str, Any],
    ) -> ToolResult:
        del store, ctx
        call_args = {
            k: v
            for k, v in args.items()
            if k not in ("observation", "plan_status", "remaining_plan")
        }
        try:
            result = await manager.call_tool(
                server_id,
                tool_name,
                call_args,
                timeout_sec=timeout_sec,
            )
        except Exception as e:
            return ToolResult(
                observation=f"MCP 调用失败：{e}",
                structured={"valid": False, "error": str(e), "source": "mcp"},
                ok=False,
            )
        observation, structured = mcp_result_to_observation(result)
        ok = bool(structured.get("valid", True)) and not structured.get("is_error")
        return ToolResult(observation=observation, structured=structured, ok=ok)

    return _handler


def resolve_mcp_call_target(registry_name: str) -> tuple[str, str] | None:
    """解析 Registry action 对应的 MCP server 与 tool。"""
    return parse_mcp_tool_name(registry_name)
