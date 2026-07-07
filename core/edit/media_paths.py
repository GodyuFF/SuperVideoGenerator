"""剪辑导出媒体路径解析与 data URL 转换。"""

from __future__ import annotations

import base64
import re
from pathlib import Path
from urllib.parse import unquote

from core.models.entities import EditTimeline, MediaAssetType
from core.store.media_storage import MediaStorageError, absolute_media_path, persist_media_url_to_disk
from core.store.memory import MemoryStore
from core.store.project_paths import parse_relative_media_path

_API_MEDIA_RE = re.compile(
    r"^/api/projects/([^/]+)/scripts/([^/]+)/assets/media/([^/?#]+)$"
)

_MIME_BY_SUFFIX = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
}


class ExportMediaError(RuntimeError):
    """导出素材路径解析失败。"""


def ms_to_frame(ms: int, fps: int) -> int:
    return max(0, round(ms / 1000.0 * fps))


def local_media_to_data_url(path: Path) -> str:
    """将本地媒体文件转为 data URL。"""
    if not path.is_file():
        raise ExportMediaError(f"媒体文件不存在：{path}")
    mime = _MIME_BY_SUFFIX.get(path.suffix.lower(), "application/octet-stream")
    payload = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{payload}"


def resolve_local_path_for_url(
    store: MemoryStore,
    *,
    project_id: str,
    script_id: str,
    media_id: str,
    url: str,
    media_type: str,
) -> Path:
    raw = (url or "").strip()
    if not raw or raw.startswith("placeholder:"):
        raise ExportMediaError(f"素材 {media_id} 无有效 URL")

    api_match = _API_MEDIA_RE.match(raw)
    if api_match:
        pid, sid, filename = api_match.groups()
        rel = f"projects/{pid}/scripts/{sid}/assets/media/{unquote(filename)}"
        local = absolute_media_path(rel)
        if local is None:
            raise ExportMediaError(f"本地媒体不存在：{rel}")
        return local.resolve()

    parsed = parse_relative_media_path(raw.replace("\\", "/"))
    if parsed:
        local = absolute_media_path(raw.replace("\\", "/"))
        if local is None:
            raise ExportMediaError(f"本地媒体不存在：{raw}")
        return local.resolve()

    if raw.startswith("http://") or raw.startswith("https://"):
        try:
            rel = persist_media_url_to_disk(
                project_id=project_id,
                script_id=script_id,
                media_id=media_id,
                url=raw,
                media_type=media_type,
            )
        except MediaStorageError as e:
            raise ExportMediaError(str(e)) from e
        local = absolute_media_path(rel)
        if local is None:
            raise ExportMediaError(f"下载后仍无法定位媒体：{media_id}")
        media = store.media_assets.get(media_id)
        if media and media.url != rel:
            media.url = rel
        return local.resolve()

    path = Path(raw)
    if path.is_file():
        return path.resolve()

    raise ExportMediaError(f"无法解析素材路径：{media_id} ({raw[:80]})")


def subtitle_for_segment(
    timeline: EditTimeline,
    *,
    start_ms: int,
    end_ms: int,
) -> str:
    for clip in timeline.tracks.get("subtitle", []):
        if clip.start_ms == start_ms and clip.end_ms == end_ms:
            return (clip.label or "").strip()
        if clip.start_ms <= start_ms < clip.end_ms:
            return (clip.label or "").strip()
    return ""
