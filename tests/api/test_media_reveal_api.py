"""媒体 reveal API 测试。"""

from pathlib import Path
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from apps.api.main import app
from core.store import project_paths


@pytest.mark.asyncio
async def test_get_script_media_by_bare_media_id(tmp_path, monkeypatch):
    """GET 媒体接口应支持裸 media_id（无扩展名）。"""
    monkeypatch.setattr(project_paths, "PROJECTS_ROOT", tmp_path / "projects")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post("/api/projects", json={"title": "媒体 GET 测试"})
        pid = r.json()["id"]
        r = await client.post(f"/api/projects/{pid}/scripts", json={"title": "S1"})
        sid = r.json()["id"]

        media_dir = project_paths.script_media_dir(pid, sid)
        media_dir.mkdir(parents=True, exist_ok=True)
        (media_dir / "media_09bb5a381262.png").write_bytes(b"\x89PNG\r\n")

        r = await client.get(
            f"/api/projects/{pid}/scripts/{sid}/assets/media/media_09bb5a381262"
        )
        assert r.status_code == 200
        assert r.content.startswith(b"\x89PNG")


@pytest.mark.asyncio
async def test_reveal_script_media_file(tmp_path, monkeypatch):
    """落盘媒体文件应可通过 reveal 端点在资源管理器中定位。"""
    monkeypatch.setattr(project_paths, "PROJECTS_ROOT", tmp_path / "projects")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post("/api/projects", json={"title": "媒体 reveal 测试"})
        pid = r.json()["id"]
        r = await client.post(f"/api/projects/{pid}/scripts", json={"title": "S1"})
        sid = r.json()["id"]

        media_dir = project_paths.script_media_dir(pid, sid)
        media_dir.mkdir(parents=True, exist_ok=True)
        clip = media_dir / "clip_test.mp4"
        clip.write_bytes(b"fake-mp4")

        with patch("core.edit.export_reveal.reveal_path_in_file_manager") as reveal:
            r = await client.post(
                f"/api/projects/{pid}/scripts/{sid}/assets/media/clip_test.mp4/reveal",
            )
            assert r.status_code == 200
            assert r.json()["ok"] is True
            reveal.assert_called_once()
            called_path: Path = reveal.call_args[0][0]
            assert called_path.name == "clip_test.mp4"
