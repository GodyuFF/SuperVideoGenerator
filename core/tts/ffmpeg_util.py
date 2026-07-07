"""FFmpeg 路径解析。"""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

_FFMPEG_MISSING_HINT = (
    "未找到 FFmpeg。请重新安装项目依赖（pip install -e .），"
    "或设置 SVG_FFMPEG_PATH=完整路径\\ffmpeg.exe，"
    "或在系统 PATH 中安装 FFmpeg（Windows: winget install ffmpeg）"
)


def _bundled_ffmpeg_exe() -> str | None:
    """imageio-ffmpeg 随 pip 分发的内置 FFmpeg（免手动安装）。"""
    try:
        import imageio_ffmpeg
    except ImportError:
        return None
    try:
        exe = imageio_ffmpeg.get_ffmpeg_exe()
    except (RuntimeError, OSError) as exc:
        logger.debug("imageio-ffmpeg 不可用: %s", exc)
        return None
    path = Path(exe)
    if path.is_file():
        return str(path)
    if shutil.which(exe):
        return exe
    return None


def _windows_ffmpeg_candidates() -> list[Path]:
    candidates: list[Path] = []
    local_app = os.environ.get("LOCALAPPDATA", "").strip()
    if local_app:
        candidates.append(Path(local_app) / "Microsoft" / "WinGet" / "Links" / "ffmpeg.exe")
    program_data = os.environ.get("ProgramData", "").strip()
    if program_data:
        candidates.append(Path(program_data) / "chocolatey" / "bin" / "ffmpeg.exe")
    candidates.extend(
        [
            Path("C:/ffmpeg/bin/ffmpeg.exe"),
            Path("C:/Program Files/ffmpeg/bin/ffmpeg.exe"),
        ]
    )
    return candidates


def resolve_ffmpeg_binary() -> str:
    override = os.getenv("SVG_FFMPEG_PATH", "").strip()
    if override:
        return override
    found = shutil.which("ffmpeg")
    if found:
        return found
    if os.name == "nt":
        for candidate in _windows_ffmpeg_candidates():
            if candidate.is_file():
                return str(candidate)
    bundled = _bundled_ffmpeg_exe()
    if bundled:
        return bundled
    return "ffmpeg"


def is_ffmpeg_bundled(ffmpeg: str | None = None) -> bool:
    """当前解析到的 FFmpeg 是否来自 imageio-ffmpeg 内置包。"""
    bundled = _bundled_ffmpeg_exe()
    if not bundled:
        return False
    resolved = (ffmpeg or "").strip() or resolve_ffmpeg_binary()
    try:
        return Path(resolved).resolve() == Path(bundled).resolve()
    except OSError:
        return resolved == bundled


def is_ffmpeg_available(ffmpeg: str | None = None) -> bool:
    """检测 FFmpeg 是否可执行。"""
    path = (ffmpeg or "").strip() or resolve_ffmpeg_binary()
    if Path(path).is_file():
        return True
    return shutil.which(path) is not None


def ffmpeg_missing_message(ffmpeg: str | None = None) -> str:
    """返回带路径提示的 FFmpeg 缺失错误文案。"""
    path = (ffmpeg or "").strip() or resolve_ffmpeg_binary()
    return f"{_FFMPEG_MISSING_HINT}（当前查找：{path}）"


def configure_pydub_ffmpeg(audio_segment_cls) -> None:
    configured = resolve_ffmpeg_binary()
    if configured:
        audio_segment_cls.converter = configured
