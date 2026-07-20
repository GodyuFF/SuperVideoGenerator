"""媒体文件落盘到剧本目录 assets/media/。"""

from __future__ import annotations

import base64
import logging
import re
from pathlib import Path
from urllib.parse import urlparse

import httpx

from core.store.project_paths import (
    parse_relative_media_path,
    relative_media_path,
    script_media_dir,
)

logger = logging.getLogger("core.store.media_storage")

_DATA_URL_RE = re.compile(r"^data:([^;]+);base64,(.+)$", re.DOTALL)

DEFAULT_DOWNLOAD_TIMEOUT_SEC = 120.0


class MediaStorageError(OSError):
    """媒体下载或落盘失败。"""


def _extension_for_mime(mime: str, fallback: str = "bin") -> str:
    mapping = {
        "image/png": "png",
        "image/jpeg": "jpg",
        "image/jpg": "jpg",
        "image/webp": "webp",
        "image/gif": "gif",
        "video/mp4": "mp4",
        "audio/mpeg": "mp3",
        "audio/wav": "wav",
    }
    return mapping.get(mime.strip().lower(), fallback)


def _guess_ext_from_url(url: str, media_type: str) -> str:
    path = urlparse(url).path.lower()
    for ext in ("png", "jpg", "jpeg", "webp", "gif", "mp4", "mp3", "wav"):
        if path.endswith(f".{ext}"):
            return "jpg" if ext == "jpeg" else ext
    return _guess_ext(media_type)


def _download_http_to_file(url: str, dest: Path, *, timeout: float = DEFAULT_DOWNLOAD_TIMEOUT_SEC) -> str:
    """下载远程 URL 到 dest，返回 Content-Type（若有）。"""
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            resp = client.get(url)
            resp.raise_for_status()
            dest.write_bytes(resp.content)
            return str(resp.headers.get("content-type", "")).split(";")[0].strip()
    except httpx.HTTPError as e:
        raise MediaStorageError(f"下载失败：{e}") from e


def persist_media_url_to_disk(
    *,
    project_id: str,
    script_id: str,
    media_id: str,
    url: str,
    media_type: str,
) -> str:
    """
    将 data: URL、本地路径或 http(s) 远程 URL 写入 script/assets/media/，
    返回相对 data/ 的路径（projects/.../assets/media/...）。
    """
    raw = url.strip()
    if not raw or raw.startswith("placeholder:"):
        return raw

    target_dir = script_media_dir(project_id, script_id)
    target_dir.mkdir(parents=True, exist_ok=True)

    if raw.startswith("http://") or raw.startswith("https://"):
        ext = _guess_ext_from_url(raw, media_type)
        filename = f"{media_id}.{ext}"
        dest = target_dir / filename
        content_type = _download_http_to_file(raw, dest)
        if content_type:
            mime_ext = _extension_for_mime(content_type, ext)
            if mime_ext != ext:
                corrected = target_dir / f"{media_id}.{mime_ext}"
                if corrected != dest and dest.exists():
                    if corrected.exists():
                        corrected.unlink()
                    dest.rename(corrected)
                    dest = corrected
                    ext = mime_ext
                filename = f"{media_id}.{ext}"
        rel = relative_media_path(project_id, script_id, filename)
        logger.info(
            "已下载媒体到本地 project=%s script=%s path=%s",
            project_id,
            script_id,
            rel,
        )
        return rel

    match = _DATA_URL_RE.match(raw)
    if match:
        mime, b64 = match.group(1), match.group(2)
        ext = _extension_for_mime(mime, _guess_ext(media_type))
        filename = f"{media_id}.{ext}"
        path = target_dir / filename
        path.write_bytes(base64.b64decode(b64))
        return relative_media_path(project_id, script_id, filename)

    path = Path(raw)
    if path.is_file():
        ext = path.suffix.lstrip(".") or _guess_ext(media_type)
        filename = f"{media_id}.{ext}"
        dest = target_dir / filename
        dest.write_bytes(path.read_bytes())
        return relative_media_path(project_id, script_id, filename)

    return raw


def absolute_media_path(relative_url: str) -> Path | None:
    """将 projects/.../assets/media/... 转为本地绝对路径。"""
    parsed = parse_relative_media_path(relative_url)
    if not parsed:
        return None
    project_id, script_id, filename = parsed
    path = script_media_dir(project_id, script_id) / filename
    return path if path.is_file() else None


def resolve_script_media_absolute_path(
    project_id: str,
    script_id: str,
    filename: str,
    *,
    store: object | None = None,
) -> Path | None:
    """按 API 文件名或裸 media_id 解析剧本媒体本地路径。"""
    safe = Path(filename).name
    if safe != filename or ".." in filename:
        return None

    direct = absolute_media_path(relative_media_path(project_id, script_id, safe))
    if direct is not None:
        return direct

    if "." in safe:
        return None

    if store is not None:
        media = getattr(store, "media_assets", {}).get(safe)
        media_url = getattr(media, "url", None) if media is not None else None
        if isinstance(media_url, str) and media_url.strip():
            via_store = absolute_media_path(media_url.replace("\\", "/").strip())
            if via_store is not None:
                return via_store

    media_dir = script_media_dir(project_id, script_id)
    if not media_dir.is_dir():
        return None
    matches = sorted(media_dir.glob(f"{safe}.*"))
    for candidate in matches:
        if candidate.is_file():
            return candidate
    return None


def _guess_ext(media_type: str) -> str:
    mt = media_type.lower()
    if "video" in mt:
        return "mp4"
    if "audio" in mt:
        return "mp3"
    return "png"
