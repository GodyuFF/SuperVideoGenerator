"""FFmpeg 成片导出配置。"""

from __future__ import annotations

import os
from dataclasses import dataclass

from core.tts.ffmpeg_util import is_ffmpeg_available, is_ffmpeg_bundled, resolve_ffmpeg_binary


@dataclass
class ExportSettings:
    enabled: bool = True
    ffmpeg_path: str = ""
    fps: int = 30
    width: int = 1920
    height: int = 1080
    crf: int = 23


class ExportConfigManager:
    def __init__(self) -> None:
        self._settings = ExportSettings()

    def get_settings(self) -> ExportSettings:
        return self._settings

    def get_public_config(self) -> dict:
        s = self._settings
        ffmpeg_path = s.ffmpeg_path or resolve_ffmpeg_binary()
        return {
            "enabled": s.enabled,
            "export_enabled": s.enabled,
            "ffmpeg_path": ffmpeg_path,
            "ffmpeg_available": is_ffmpeg_available(ffmpeg_path),
            "ffmpeg_bundled": is_ffmpeg_bundled(ffmpeg_path),
            "fps": s.fps,
            "width": s.width,
            "height": s.height,
            "crf": s.crf,
            "active": s.enabled,
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
        if env_enabled in ("0", "false", "no"):
            _manager.update(enabled=False)
        ffmpeg = os.getenv("SVG_FFMPEG_PATH", "").strip()
        if ffmpeg:
            _manager.update(ffmpeg_path=ffmpeg)
    return _manager
