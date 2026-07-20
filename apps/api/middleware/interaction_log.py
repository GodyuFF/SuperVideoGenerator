"""HTTP 请求交互日志中间件。"""

import logging
import re
import time
from typing import Callable

from fastapi import Request, Response

from core.logging.perf import api_slow_threshold_ms, log_perf

_perf_logger = logging.getLogger("apps.api.perf")

_SCRIPT_PATH_RE = re.compile(r"/api/projects/([^/]+)/scripts/([^/]+)")

_SKIP_API_LOG_PREFIXES = (
    "/api/interactions",
)


async def interaction_logging_middleware(request: Request, call_next: Callable) -> Response:
    """记录所有 /api 请求元数据到持久化日志（不读取 body，避免破坏下游）。"""
    if not request.url.path.startswith("/api"):
        return await call_next(request)

    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000

    path = request.url.path
    if path == "/health" or any(path.startswith(p) for p in _SKIP_API_LOG_PREFIXES):
        return response

    recorder = getattr(request.app.state, "interaction_recorder", None)
    if recorder:
        project_id = ""
        script_id = ""
        m = _SCRIPT_PATH_RE.search(path)
        if m:
            project_id, script_id = m.group(1), m.group(2)
        await recorder.record_api_request(
            method=request.method,
            url=path,
            status_code=response.status_code,
            duration_ms=duration_ms,
            project_id=project_id,
            script_id=script_id,
        )

    slow_ms = api_slow_threshold_ms()
    if duration_ms >= slow_ms or response.status_code >= 500:
        log_perf(
            "api",
            f"{request.method} {path}",
            duration_ms=duration_ms,
            level="warning" if duration_ms >= slow_ms else "info",
            logger=_perf_logger,
            status=response.status_code,
            slow_threshold_ms=slow_ms,
        )

    return response
