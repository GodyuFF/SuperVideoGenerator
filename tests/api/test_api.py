"""API 集成测试：REST 端点与健康检查。"""

import pytest
from httpx import ASGITransport, AsyncClient

from apps.api.main import app
from core.models.entities import GenerationMode, VideoStyleMode


@pytest.mark.asyncio
async def test_health():
  """健康检查应返回 ok。"""
  transport = ASGITransport(app=app)
  async with AsyncClient(transport=transport, base_url="http://test") as client:
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_create_project_and_script():
  """应能创建项目、剧本并更新配置。"""
  transport = ASGITransport(app=app)
  async with AsyncClient(transport=transport, base_url="http://test") as client:
    r = await client.post("/api/projects", json={"title": "API 测试项目"})
    assert r.status_code == 200
    project = r.json()
    pid = project["id"]

    r = await client.post(
      f"/api/projects/{pid}/scripts",
      json={"title": "第一集", "duration_sec": 90},
    )
    assert r.status_code == 200
    script = r.json()
    assert script["title"] == "第一集"

    r = await client.patch(
      f"/api/projects/{pid}/config",
      json={
        "generation_mode": GenerationMode.AUTO.value,
      },
    )
    assert r.status_code == 200
    assert r.json()["generation"]["mode"] == "auto"


@pytest.mark.asyncio
async def test_chat_rejects_style_change_when_locked():
  """风格锁定后 chat 传入不同 style_mode 应被拒绝。"""
  transport = ASGITransport(app=app)
  async with AsyncClient(transport=transport, base_url="http://test") as client:
    r = await client.post("/api/projects", json={"title": "锁定测试"})
    pid = r.json()["id"]
    r = await client.post(f"/api/projects/{pid}/scripts", json={"title": "S1"})
    sid = r.json()["id"]

    r = await client.post(
      f"/api/projects/{pid}/scripts/{sid}/chat",
      json={
        "message": "第一段剧本",
        "style_mode": VideoStyleMode.DYNAMIC_IMAGE.value,
        "generation_mode": GenerationMode.AUTO.value,
      },
    )
    assert r.status_code == 200

    r = await client.post(
      f"/api/projects/{pid}/scripts/{sid}/chat",
      json={
        "message": "尝试改风格",
        "style_mode": VideoStyleMode.AI_VIDEO.value,
      },
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_chat_drives_full_pipeline():
  """对话 API：超级视频大师自动 Plan + Execute 应完成，并绑定风格。"""
  transport = ASGITransport(app=app)
  async with AsyncClient(transport=transport, base_url="http://test") as client:
    r = await client.post("/api/projects", json={"title": "对话测试"})
    pid = r.json()["id"]
    r = await client.post(f"/api/projects/{pid}/scripts", json={"title": "S1"})
    sid = r.json()["id"]

    r = await client.post(
      f"/api/projects/{pid}/scripts/{sid}/chat",
      json={
        "message": "制作一段60秒都市情感短片",
        "generation_mode": GenerationMode.AUTO.value,
        "style_mode": VideoStyleMode.DYNAMIC_IMAGE.value,
      },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["script"]["status"] == "completed"
    assert data["script"]["style_locked"] is True
    assert data["script"]["style_mode"] == "dynamic_image"
    assert len(data["plan"]["steps"]) >= 4

    r = await client.get(f"/api/projects/{pid}/scripts/{sid}/assets")
    assert r.status_code == 200
    assert len(r.json()) >= 1
