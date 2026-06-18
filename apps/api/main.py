"""FastAPI 应用入口。"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.api.middleware.interaction_log import interaction_logging_middleware
from apps.api.routes.interactions import router as interactions_router
from apps.api.routes.llm import router as llm_router
from apps.api.routes.projects import router as projects_router
from apps.api.websocket.handler import router as ws_router
from apps.api.state import state

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

app.include_router(interactions_router)
app.include_router(llm_router)
app.include_router(projects_router)
app.include_router(ws_router)


@app.get("/health")
def health():
    """健康检查。"""
    return {"status": "ok"}
