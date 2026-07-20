"""MCP Client 连接与会话管理。"""

from __future__ import annotations

import asyncio
import logging
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from typing import Any

from core.extensions.mcp.config import McpServerConfig
from core.extensions.mcp.guard import validate_server_config

logger = logging.getLogger("core.extensions.mcp.client")


@dataclass
class McpSessionHandle:
    """已连接的 MCP 会话句柄。"""

    server_id: str
    session: Any
    tools: list[Any] = field(default_factory=list)


class McpConnectionManager:
    """管理 MCP Server 长连接（stdio / SSE）。"""

    def __init__(self) -> None:
        self._handles: dict[str, McpSessionHandle] = {}
        self._stacks: dict[str, AsyncExitStack] = {}
        self._lock = asyncio.Lock()

    async def connect(self, config: McpServerConfig) -> McpSessionHandle:
        """连接 MCP Server 并缓存会话。"""
        validate_server_config(config.command, config.transport, config.url)
        async with self._lock:
            if config.id in self._handles:
                return self._handles[config.id]
            handle = await self._open_session(config)
            self._handles[config.id] = handle
            return handle

    async def disconnect(self, server_id: str) -> None:
        """关闭指定 server 连接。"""
        async with self._lock:
            stack = self._stacks.pop(server_id, None)
            self._handles.pop(server_id, None)
        if stack is not None:
            await stack.aclose()

    async def shutdown_all(self) -> None:
        """关闭全部 MCP 连接。"""
        async with self._lock:
            ids = list(self._handles.keys())
        for server_id in ids:
            await self.disconnect(server_id)

    async def call_tool(
        self,
        server_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        *,
        timeout_sec: float = 30.0,
    ) -> Any:
        """调用 MCP tool。"""
        handle = self._handles.get(server_id)
        if handle is None:
            raise RuntimeError(f"MCP server 未连接：{server_id}")
        return await asyncio.wait_for(
            handle.session.call_tool(tool_name, arguments=arguments),
            timeout=timeout_sec,
        )

    def get_handle(self, server_id: str) -> McpSessionHandle | None:
        """获取已连接句柄。"""
        return self._handles.get(server_id)

    async def _open_session(self, config: McpServerConfig) -> McpSessionHandle:
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
        except ImportError as e:
            raise RuntimeError(
                "未安装 mcp 包，请 pip install mcp 后启用 MCP 扩展"
            ) from e

        stack = AsyncExitStack()
        self._stacks[config.id] = stack

        if config.transport == "stdio":
            params = StdioServerParameters(
                command=config.command,
                args=list(config.args),
                env=config.env or None,
            )
            read, write = await stack.enter_async_context(stdio_client(params))
        elif config.transport == "sse":
            from mcp.client.sse import sse_client

            read, write = await stack.enter_async_context(sse_client(config.url))
        else:
            raise ValueError(f"不支持的 transport：{config.transport}")

        session = await stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        listed = await session.list_tools()
        tools = list(getattr(listed, "tools", None) or [])
        logger.info(
            "MCP server 已连接：%s tools=%s",
            config.id,
            [t.name for t in tools],
        )
        return McpSessionHandle(server_id=config.id, session=session, tools=tools)


_MANAGER: McpConnectionManager | None = None


def get_mcp_manager() -> McpConnectionManager:
    """获取全局 MCP 连接管理器。"""
    global _MANAGER
    if _MANAGER is None:
        _MANAGER = McpConnectionManager()
    return _MANAGER


def reset_mcp_manager() -> None:
    """重置管理器（测试用）。"""
    global _MANAGER
    _MANAGER = None
