"""REST API：MCP Server 配置与连通性。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from core.extensions.mcp.config import McpConfigStore, McpServerConfig
from core.extensions.mcp.loader import list_mcp_server_status, test_mcp_server

router = APIRouter(prefix="/api/mcp")


class McpServerUpsertBody(BaseModel):
    """创建或更新 MCP Server 配置。"""

    id: str
    title: str = ""
    description: str = ""
    enabled: bool = False
    transport: str = "stdio"
    command: str = ""
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    url: str = ""
    timeout_sec: float = 30.0
    agent: str = "common"
    allowed_tools: list[str] | None = None
    tool_prefix: str = ""


@router.get("/servers")
def get_mcp_servers():
    """列出 MCP Server 配置与连接状态。"""
    return list_mcp_server_status()


@router.put("/servers/{server_id}")
def upsert_mcp_server(server_id: str, body: McpServerUpsertBody):
    """更新 MCP Server 配置（写入 data/mcp_config.json）。"""
    payload: dict[str, Any] = body.model_dump()
    payload["id"] = server_id
    config = McpServerConfig.from_dict(payload)
    McpConfigStore().upsert(config)
    return config.to_dict()


@router.post("/servers/{server_id}/test")
async def post_mcp_server_test(server_id: str):
    """测试连接 MCP Server。"""
    return await test_mcp_server(server_id)
