"""FastAPI 应用入口。"""

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from apps.api.middleware.interaction_log import interaction_logging_middleware
from apps.api.routes.board import router as board_router
from apps.api.routes.agents import router as agents_router
from apps.api.routes.interactions import router as interactions_router
from apps.api.routes.ai import router as ai_router
from apps.api.routes.llm import router as llm_router
from apps.api.routes.projects import router as projects_router
from apps.api.routes.skills import router as skills_router
from apps.api.routes.edit_timeline import router as edit_timeline_router
from apps.api.websocket.handler import router as ws_router
from apps.api.state import state

logger = logging.getLogger("apps.api")

app = FastAPI(title="SuperVideoGenerator API", version="0.1.0")
app.state.interaction_recorder = state.interaction_recorder

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
app.include_router(interactions_router)
app.include_router(ai_router)
app.include_router(llm_router)
app.include_router(projects_router)
app.include_router(skills_router)
app.include_router(edit_timeline_router)
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
