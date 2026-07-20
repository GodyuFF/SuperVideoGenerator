"""真实 LLM 对话冒烟（需 SVG_LLM_API_KEY，默认不跑）。"""

import os

import pytest
from httpx import ASGITransport, AsyncClient

from apps.api.main import app
from apps.api.state import delete_project
from tests.support.chat_wait import wait_for_chat_idle

pytestmark = pytest.mark.live


@pytest.mark.asyncio
async def test_chat_hello_with_deepseek():
    api_key = os.getenv("SVG_LLM_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        pytest.skip("未设置 SVG_LLM_API_KEY 或 DEEPSEEK_API_KEY")

    pid: str | None = None
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.patch(
                "/api/ai/config",
                json={
                    "llm": {
                        "provider": "deepseek",
                        "use_llm_react": True,
                        "api_key": api_key,
                    },
                },
            )

            pr = await client.post("/api/projects", json={"title": "Live 测试"})
            pid = pr.json()["id"]
            sr = await client.post(
                f"/api/projects/{pid}/scripts",
                json={"title": "Live 剧本", "duration_sec": 60},
            )
            sid = sr.json()["id"]

            r = await client.post(
                f"/api/projects/{pid}/scripts/{sid}/chat",
                json={
                    "message": "你好",
                    "generation_mode": "auto",
                    "style_mode": "storybook",
                },
                timeout=30.0,
            )

            if r.status_code != 202:
                detail = r.json().get("detail", r.text)
                pytest.fail(f"chat 失败 {r.status_code}: {detail}")

            data = r.json()
            assert data.get("conversation_id")

            await wait_for_chat_idle(client, pid, sid, timeout_sec=300.0)

            sr = await client.get(f"/api/projects/{pid}/scripts/{sid}")
            assert sr.status_code == 200
            script = sr.json()
            assert script.get("status") in ("completed", "failed", "executing")

            logs = await client.get("/api/interactions?script_id=" + sid + "&limit=20")
            kinds = [x["kind"] for x in logs.json().get("records", [])]
            assert "llm_request" in kinds
            assert "llm_response" in kinds
    finally:
        if pid:
            try:
                delete_project(pid)
            except ValueError:
                pass
