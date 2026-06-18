"""HTTP 请求交互日志中间件。"""

import re
import time
from typing import Callable

from fastapi import Request, Response

_SCRIPT_PATH_RE = re.compile(r"/api/projects/([^/]+)/scripts/([^/]+)")


async def interaction_logging_middleware(request: Request, call_next: Callable) -> Response:
    """记录所有 /api 请求元数据到持久化日志（不读取 body，避免破坏下游）。"""
    if not request.url.path.startswith("/api"):
        return await call_next(request)

    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000

    recorder = getattr(request.app.state, "interaction_recorder", None)
    if recorder:
        project_id = ""
        script_id = ""
        m = _SCRIPT_PATH_RE.search(request.url.path)
        if m:
            project_id, script_id = m.group(1), m.group(2)
        await recorder.record_api_request(
            method=request.method,
            url=request.url.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
            project_id=project_id,
            script_id=script_id,
        )

    return response
