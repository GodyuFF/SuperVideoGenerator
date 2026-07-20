#!/usr/bin/env python3
"""tests/support 用最小 MCP stdio server（仅测试）。"""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("svg-test-server")


@mcp.tool()
def echo(message: str) -> str:
    """回显输入消息。"""
    return f"echo:{message}"


if __name__ == "__main__":
    mcp.run(transport="stdio")
