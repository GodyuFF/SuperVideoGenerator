"""FFmpeg 成片导出配置。"""

from __future__ import annotations

import os
from dataclasses import dataclass

from core.tts.ffmpeg_util import is_ffmpeg_available, is_ffmpeg_bundled, resolve_ffmpeg_binary

# 成片导出策略：默认仅允许 OpenCut 剪辑器浏览器导出；服务端 FFmpeg 合成需显式开启。
CLASSIC_EXPORT_ONLY_MESSAGE = (
    "成片导出已改为仅支持在剪辑助手（OpenCut 编辑器）内使用浏览器导出，"
    "不再使用服务端 FFmpeg 合成。请打开「剪辑修改」后在编辑器顶栏点击「导出」。"
)


@dataclass
class ExportSettings:
    enabled: bool = False
    ffmpeg_path: str = ""
    fps: int = 30
    width: int = 1920
    height: int = 1080
    crf: int = 23


class ExportConfigManager:
    """FFmpeg 成片导出开关与参数管理。"""

    def __init__(self) -> None:
        self._settings = ExportSettings()

    def get_settings(self) -> ExportSettings:
        return self._settings

    def is_ffmpeg_export_enabled(self) -> bool:
        """是否允许服务端 FFmpeg 合成成片（默认关闭）。"""
        return bool(self._settings.enabled)

    def get_public_config(self) -> dict:
        s = self._settings
        ffmpeg_path = s.ffmpeg_path or resolve_ffmpeg_binary()
        ffmpeg_enabled = self.is_ffmpeg_export_enabled()
        return {
            "enabled": ffmpeg_enabled,
            "export_enabled": ffmpeg_enabled,
            "classic_export_enabled": True,
            "export_via_classic_only": not ffmpeg_enabled,
            "ffmpeg_path": ffmpeg_path,
            "ffmpeg_available": is_ffmpeg_available(ffmpeg_path),
            "ffmpeg_bundled": is_ffmpeg_bundled(ffmpeg_path),
            "fps": s.fps,
            "width": s.width,
            "height": s.height,
            "crf": s.crf,
            "active": ffmpeg_enabled,
        }

    def update(
        self,
        *,
        enabled: bool | None = None,
        ffmpeg_path: str | None = None,
        fps: int | None = None,
        width: int | None = None,
        height: int | None = None,
        crf: int | None = None,
    ) -> None:
        if enabled is not None:
            self._settings.enabled = enabled
        if ffmpeg_path is not None:
            self._settings.ffmpeg_path = ffmpeg_path
        if fps is not None:
            self._settings.fps = fps
        if width is not None:
            self._settings.width = width
        if height is not None:
            self._settings.height = height
        if crf is not None:
            self._settings.crf = crf

    def resolve_ffmpeg(self) -> str:
        raw = (self._settings.ffmpeg_path or "").strip()
        return raw or resolve_ffmpeg_binary()


_manager: ExportConfigManager | None = None


def get_export_manager() -> ExportConfigManager:
    global _manager
    if _manager is None:
        _manager = ExportConfigManager()
        env_enabled = os.getenv("SVG_EXPORT_ENABLED", "").strip().lower()
        if env_enabled in ("1", "true", "yes"):
            _manager.update(enabled=True)
        elif env_enabled in ("0", "false", "no"):
            _manager.update(enabled=False)
        ffmpeg = os.getenv("SVG_FFMPEG_PATH", "").strip()
        if ffmpeg:
            _manager.update(ffmpeg_path=ffmpeg)
    return _manager


def reset_export_manager() -> ExportConfigManager:
    """重置导出管理器（测试隔离用）。"""
    global _manager
    _manager = ExportConfigManager()
    env_enabled = os.getenv("SVG_EXPORT_ENABLED", "").strip().lower()
    if env_enabled in ("1", "true", "yes"):
        _manager.update(enabled=True)
    elif env_enabled in ("0", "false", "no"):
        _manager.update(enabled=False)
    ffmpeg = os.getenv("SVG_FFMPEG_PATH", "").strip()
    if ffmpeg:
        _manager.update(ffmpeg_path=ffmpeg)
    return _manager


def require_ffmpeg_export_enabled() -> None:
    """校验服务端 FFmpeg 导出已启用，否则抛出 ValueError。"""
    if not get_export_manager().is_ffmpeg_export_enabled():
        raise ValueError(CLASSIC_EXPORT_ONLY_MESSAGE)
