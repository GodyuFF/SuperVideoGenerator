"""桌面生产包：将 Vite dist 挂到 FastAPI 根路径。"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.responses import FileResponse


def resolve_desktop_web_root(env: Mapping[str, str] | None = None) -> Path | None:
    """读取 SVG_DESKTOP_WEB_ROOT；目录须含 index.html。"""
    raw = (env or os.environ).get("SVG_DESKTOP_WEB_ROOT", "").strip()
    if not raw:
        return None
    root = Path(raw).resolve()
    if not (root / "index.html").is_file():
        return None
    return root


def mount_desktop_static_if_configured(
    app: FastAPI, env: Mapping[str, str] | None = None
) -> bool:
    """若配置了有效 web 根目录则挂载静态与 SPA fallback。"""
    root = resolve_desktop_web_root(env)
    if root is None:
        return False

    assets = root / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets)), name="desktop_assets")

    index = root / "index.html"

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        """非 API 路径回退到 index.html（API 路由优先匹配）。"""
        candidate = root / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(index)

    return True
