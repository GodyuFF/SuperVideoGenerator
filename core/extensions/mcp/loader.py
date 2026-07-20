"""启动时加载 MCP tools；Skill 激活时懒连接。"""

from __future__ import annotations

import logging

from core.extensions.mcp.adapter import build_mcp_tool_specs
from core.extensions.mcp.client import get_mcp_manager
from core.extensions.mcp.config import (
    McpConfigStore,
    McpServerConfig,
    load_entry_point_server_defs,
)
from core.llm.tools.registry import ToolRegistry

logger = logging.getLogger("core.extensions.mcp.loader")

_REGISTERED_MCP: set[str] = set()


def _merge_server_config(server_id: str) -> McpServerConfig | None:
    """合并 entry_point 模板与用户配置。"""
    templates = load_entry_point_server_defs()
    store = McpConfigStore()
    user_cfg = store.get(server_id)
    template = templates.get(server_id)
    if user_cfg is None and template is None:
        return None
    if user_cfg is not None:
        return user_cfg
    return McpServerConfig.from_dict(template)


def _enabled_servers(extra_ids: list[str] | None = None) -> list[McpServerConfig]:
    store = McpConfigStore()
    configs = {c.id: c for c in store.load() if c.enabled}
    for server_id in extra_ids or []:
        merged = _merge_server_config(server_id)
        if merged is not None:
            merged.enabled = True
            configs[merged.id] = merged
    return list(configs.values())


async def ensure_mcp_servers(server_ids: list[str]) -> None:
    """Skill 激活时确保指定 MCP server 已连接并注册 tools。"""
    if not server_ids:
        return
    registry = __import__("core.llm.tools.registry", fromlist=["get_tool_registry"]).get_tool_registry()
    manager = get_mcp_manager()
    for server_id in server_ids:
        cfg = _merge_server_config(server_id)
        if cfg is None:
            logger.warning("未知 MCP server：%s", server_id)
            continue
        cfg.enabled = True
        await _register_server_tools(registry, manager, cfg)


async def _register_server_tools(
    registry: ToolRegistry,
    manager,
    config: McpServerConfig,
) -> None:
    """连接 MCP server 并将其 tools 注册到 Registry。"""
    import time

    from core.logging.perf import log_perf

    if config.id in _REGISTERED_MCP:
        return
    start = time.perf_counter()
    try:
        handle = await manager.connect(config)
    except Exception:
        logger.exception("连接 MCP server 失败：%s", config.id)
        log_perf(
            "startup",
            "mcp_server 连接失败",
            duration_ms=(time.perf_counter() - start) * 1000,
            server_id=config.id,
            level="warning",
        )
        return
    tool_count = 0
    for spec in build_mcp_tool_specs(config, handle, manager):
        if registry.has(spec.name):
            continue
        registry.register(spec)
        tool_count += 1
    _REGISTERED_MCP.add(config.id)
    log_perf(
        "startup",
        "mcp_server 已注册",
        duration_ms=(time.perf_counter() - start) * 1000,
        server_id=config.id,
        tool_count=tool_count,
    )


async def init_mcp_on_startup() -> None:
    """应用启动时为已启用 MCP server 注册 tools。"""
    from core.llm.tools.registry import get_tool_registry

    registry = get_tool_registry()
    manager = get_mcp_manager()
    for cfg in _enabled_servers():
        await _register_server_tools(registry, manager, cfg)


def load_mcp_tools(registry: ToolRegistry) -> None:
    """同步占位：MCP tools 在 FastAPI startup 异步注册。"""
    del registry


def list_mcp_server_status() -> list[dict]:
    """API：列出全部已知 server 及连接状态。"""
    store = McpConfigStore()
    user_configs = {c.id: c for c in store.load()}
    templates = load_entry_point_server_defs()
    manager = get_mcp_manager()
    ids = sorted(set(user_configs) | set(templates))
    result: list[dict] = []
    for server_id in ids:
        cfg = user_configs.get(server_id)
        if cfg is None and server_id in templates:
            cfg = McpServerConfig.from_dict(templates[server_id])
        if cfg is None:
            continue
        handle = manager.get_handle(server_id)
        result.append(
            {
                **cfg.to_dict(),
                "connected": handle is not None,
                "tool_count": len(handle.tools) if handle else 0,
                "source": "entry_point" if server_id in templates else "config",
            }
        )
    return result


async def test_mcp_server(server_id: str) -> dict:
    """API：测试连接指定 MCP server。"""
    cfg = _merge_server_config(server_id)
    if cfg is None:
        return {"ok": False, "error": f"未知 server：{server_id}"}
    cfg.enabled = True
    manager = get_mcp_manager()
    try:
        handle = await manager.connect(cfg)
        return {
            "ok": True,
            "server_id": server_id,
            "tools": [t.name for t in handle.tools],
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def reset_mcp_loader_state() -> None:
    """测试用：清空已注册标记。"""
    global _REGISTERED_MCP
    _REGISTERED_MCP = set()
