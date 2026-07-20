"""MCP 调用安全边界。"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

_MAX_RESPONSE_CHARS = 64_000
_LOCAL_HOST_PATTERN = re.compile(
    r"^(localhost|127\.0\.0\.1|0\.0\.0\.0|::1|\[::1\])$",
    re.I,
)


def mcp_tool_registry_name(server_id: str, tool_name: str) -> str:
    """生成 Registry 内 MCP tool 名：mcp.{server}.{tool}。"""
    safe_server = server_id.replace(".", "_")
    safe_tool = tool_name.replace(".", "_")
    return f"mcp.{safe_server}.{safe_tool}"


def parse_mcp_tool_name(registry_name: str) -> tuple[str, str] | None:
    """从 Registry 名解析 (server_id, tool_name)。"""
    if not registry_name.startswith("mcp."):
        return None
    parts = registry_name.split(".", 2)
    if len(parts) < 3:
        return None
    return parts[1], parts[2]


def validate_server_config(command: str, transport: str, url: str) -> None:
    """启动前校验 server 配置。"""
    if transport == "stdio":
        if not command.strip():
            raise ValueError("stdio transport 需要 command")
        if "\x00" in command:
            raise ValueError("command 含非法字符")
    elif transport == "sse":
        if not url.strip():
            raise ValueError("sse transport 需要 url")
        _reject_local_url(url)
    else:
        raise ValueError(f"不支持的 transport：{transport}")


def _reject_local_url(url: str) -> None:
    parsed = urlparse(url)
    host = (parsed.hostname or "").strip()
    if not host:
        return
    if _LOCAL_HOST_PATTERN.match(host):
        raise ValueError(f"拒绝连接内网 MCP URL：{url}")


def truncate_mcp_text(text: str, *, limit: int = _MAX_RESPONSE_CHARS) -> str:
    """限制 MCP 响应文本长度。"""
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def mcp_result_to_observation(result: Any) -> tuple[str, dict[str, Any]]:
    """将 MCP CallToolResult 转为 observation 与 structured。"""
    parts: list[str] = []
    structured: dict[str, Any] = {"valid": True, "source": "mcp"}
    content = getattr(result, "content", None) or []
    for block in content:
        block_type = getattr(block, "type", None) or (
            block.get("type") if isinstance(block, dict) else None
        )
        if block_type == "text":
            text = getattr(block, "text", None) or (
                block.get("text") if isinstance(block, dict) else ""
            )
            parts.append(truncate_mcp_text(str(text)))
        elif block_type == "image":
            parts.append("[MCP 返回 image 内容，已省略]")
        else:
            parts.append(f"[MCP 内容块 type={block_type}]")
    is_error = bool(getattr(result, "isError", False))
    structured["is_error"] = is_error
    if hasattr(result, "structuredContent") and result.structuredContent:
        structured["payload"] = result.structuredContent
    observation = "\n".join(parts) if parts else "(MCP 无文本内容)"
    if is_error:
        structured["valid"] = False
    return observation, structured
