# tests/unit/test_desktop_static.py
from pathlib import Path
from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.api.desktop_static import (
    mount_desktop_static_if_configured,
    resolve_desktop_web_root,
)


def test_resolve_missing_env_returns_none(monkeypatch, tmp_path):
    monkeypatch.delenv("SVG_DESKTOP_WEB_ROOT", raising=False)
    assert resolve_desktop_web_root({}) is None


def test_mount_serves_index_and_spa_fallback(monkeypatch, tmp_path):
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("<html>ok</html>", encoding="utf-8")
    (web / "assets").mkdir()
    (web / "assets" / "a.js").write_text("1", encoding="utf-8")
    monkeypatch.setenv("SVG_DESKTOP_WEB_ROOT", str(web))

    app = FastAPI()

    @app.get("/api/ping")
    def ping():
        return {"ok": True}

    assert mount_desktop_static_if_configured(app) is True
    client = TestClient(app)
    assert client.get("/api/ping").json() == {"ok": True}
    assert "ok" in client.get("/").text
    assert client.get("/assets/a.js").text == "1"
    # SPA：未知前端路由回 index
    assert "ok" in client.get("/workbench/foo").text


def test_mount_does_not_break_health(monkeypatch, tmp_path):
    """SPA catch-all 不得覆盖 /health。"""
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("<html>ok</html>", encoding="utf-8")
    monkeypatch.setenv("SVG_DESKTOP_WEB_ROOT", str(web))

    app = FastAPI()

    @app.get("/health")
    def health():
        return {"status": "ok"}

    assert mount_desktop_static_if_configured(app) is True
    client = TestClient(app)
    assert client.get("/health").json() == {"status": "ok"}


def test_main_health_without_desktop_env(monkeypatch):
    """未配置 SVG_DESKTOP_WEB_ROOT 时 main 应用 /health 不变。"""
    monkeypatch.delenv("SVG_DESKTOP_WEB_ROOT", raising=False)
    from apps.api.main import app

    client = TestClient(app)
    assert client.get("/health").json() == {"status": "ok"}
