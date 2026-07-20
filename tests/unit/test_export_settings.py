"""导出配置：Classic 浏览器导出为默认成片路径。"""

from __future__ import annotations

import pytest

from core.edit.export_settings import (
    CLASSIC_EXPORT_ONLY_MESSAGE,
    ExportConfigManager,
    require_ffmpeg_export_enabled,
)


def test_ffmpeg_export_disabled_by_default() -> None:
    """默认应关闭服务端 FFmpeg 成片导出。"""
    mgr = ExportConfigManager()
    cfg = mgr.get_public_config()
    assert cfg["export_enabled"] is False
    assert cfg["classic_export_enabled"] is True
    assert cfg["export_via_classic_only"] is True


def test_require_ffmpeg_export_raises_when_disabled(monkeypatch) -> None:
    """require_ffmpeg_export_enabled 在默认配置下应抛出说明性错误。"""
    mgr = ExportConfigManager()
    monkeypatch.setattr("core.edit.export_settings.get_export_manager", lambda: mgr)
    with pytest.raises(ValueError, match="剪辑助手"):
        require_ffmpeg_export_enabled()
    assert CLASSIC_EXPORT_ONLY_MESSAGE
