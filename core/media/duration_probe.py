"""本地媒体文件时长探测。"""

from __future__ import annotations

import logging
from pathlib import Path

from core.models.entities import MediaAssetType
from core.tts.duration import duration_ms_from_target

logger = logging.getLogger(__name__)

# (resolved_path, mtime_ns, size) -> duration_ms；进程内复用，避免每次 GET 重复 ffmpeg
_PROBE_CACHE: dict[tuple[str, int, int], int] = {}


def clear_duration_probe_cache() -> None:
    """清空时长探测缓存（测试或文件被覆盖后调用）。"""
    _PROBE_CACHE.clear()


def probe_media_duration_ms(file_path: str, media_type: MediaAssetType) -> int | None:
    """从本地文件探测时长（毫秒）；无法探测时返回 None。"""
    if media_type not in (MediaAssetType.AUDIO, MediaAssetType.VIDEO):
        return None
    path = Path(file_path)
    if not path.is_file():
        return None
    try:
        stat = path.stat()
        cache_key = (str(path.resolve()), int(stat.st_mtime_ns), int(stat.st_size))
    except OSError:
        cache_key = None
    if cache_key is not None and cache_key in _PROBE_CACHE:
        return _PROBE_CACHE[cache_key]
    try:
        ms = duration_ms_from_target(path)
    except Exception as exc:
        logger.debug("probe media duration failed for %s: %s", path, exc)
        return None
    if ms <= 0:
        return None
    if cache_key is not None:
        _PROBE_CACHE[cache_key] = ms
    return ms
