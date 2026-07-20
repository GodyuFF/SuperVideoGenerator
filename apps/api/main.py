"""FastAPI 应用入口。"""

import asyncio
import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from apps.api.middleware.interaction_log import interaction_logging_middleware
from apps.api.routes.board import router as board_router
from apps.api.routes.agents import router as agents_router
from apps.api.routes.style_modes import router as style_modes_router
from apps.api.routes.tools import router as tools_router
from apps.api.routes.interactions import router as interactions_router
from apps.api.routes.ai import router as ai_router
from apps.api.routes.projects import router as projects_router
from apps.api.routes.skills import router as skills_router
from apps.api.routes.sounds import router as sounds_router
from apps.api.routes.mcp import router as mcp_router
from apps.api.routes.edit_timeline import router as edit_timeline_router
from apps.api.routes.edit_session import router as edit_session_router
from apps.api.routes.ui_prefs import router as ui_prefs_router
from apps.api.routes.generation_queue import router as generation_queue_router
from apps.api.websocket.handler import router as ws_router
from apps.api.state import state

logger = logging.getLogger("apps.api")

app = FastAPI(title="SuperVideoGenerator API", version="0.1.0")
app.state.interaction_recorder = state.interaction_recorder


@app.on_event("startup")
async def startup_mcp_tools() -> None:
    """启动时加载 Agent 配置并为已启用的 MCP Server 注册 tools。"""
    import time

    from core.extensions.mcp.loader import init_mcp_on_startup
    from core.interaction_log.maintenance import run_startup_retention
    from core.llm.agent.config_paths import resolve_agent_config_path
    from core.llm.tools.registry import get_tool_registry, reset_tool_registry
    from core.logging.perf import async_perf_span, log_perf

    startup_start = time.perf_counter()

    async with async_perf_span("startup", "reload_agent_config", logger=logger):
        state.reload_agent_config()
    logger.info("Agent 配置已加载：%s", resolve_agent_config_path())

    async with async_perf_span("startup", "tool_registry_bootstrap", logger=logger):
        reset_tool_registry()
        registry = get_tool_registry()
    async with async_perf_span("startup", "mcp_init", logger=logger):
        await init_mcp_on_startup()

    deleted = 0
    async with async_perf_span("startup", "interaction_log_retention", logger=logger):
        deleted = await asyncio.to_thread(
            run_startup_retention,
            state.interaction_log_store,
        )
    if deleted:
        logger.info("启动 retention 已清理 %s 条过期 api_request 日志", deleted)

    state.conversation_write_queue.bind_loop(asyncio.get_running_loop())

    total_ms = (time.perf_counter() - startup_start) * 1000
    log_perf(
        "startup",
        "FastAPI startup 完成",
        duration_ms=total_ms,
        logger=logger,
        tool_count=len(registry.list_tools()),
    )


@app.on_event("shutdown")
async def shutdown_mcp_tools() -> None:
    """关闭全部 MCP 连接并刷盘交互日志。"""
    from core.extensions.mcp.client import get_mcp_manager
    from core.interaction_log.async_writer import get_interaction_log_writer

    await get_mcp_manager().shutdown_all()
    writer = get_interaction_log_writer()
    if writer is not None:
        await asyncio.to_thread(writer.shutdown)

# 允许前端跨域（开发环境）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.middleware("http")(interaction_logging_middleware)

app.include_router(board_router)
app.include_router(agents_router)
app.include_router(style_modes_router)
app.include_router(tools_router)
app.include_router(interactions_router)
app.include_router(ai_router)
app.include_router(projects_router)
app.include_router(skills_router)
app.include_router(sounds_router)
app.include_router(mcp_router)
app.include_router(edit_timeline_router)
app.include_router(edit_session_router)
app.include_router(ui_prefs_router)
app.include_router(generation_queue_router)
app.include_router(ws_router)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """未捕获异常返回 JSON detail，避免前端仅显示 Internal Server Error。"""
    from fastapi import HTTPException

    if isinstance(exc, HTTPException):
        detail = exc.detail
        if not isinstance(detail, str):
            detail = str(detail)
        return JSONResponse(status_code=exc.status_code, content={"detail": detail})
    logger.exception("未处理异常 %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc) or "服务器内部错误"},
    )


@app.get("/health")
def health():
    """健康检查。"""
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
