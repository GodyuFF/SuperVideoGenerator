"""等待后台 chat 编排结束的测试辅助。"""

from __future__ import annotations

import asyncio
import time

from httpx import AsyncClient


async def wait_for_chat_idle(
    client: AsyncClient,
    project_id: str,
    script_id: str,
    *,
    timeout_sec: float = 120.0,
    poll_sec: float = 0.1,
) -> None:
    """轮询 executions/active 直至主编排结束或超时。"""
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        response = await client.get(
            f"/api/projects/{project_id}/scripts/{script_id}/executions/active"
        )
        if response.status_code == 200 and not response.json().get("active"):
            return
        await asyncio.sleep(poll_sec)
    raise TimeoutError("chat execution did not finish in time")
