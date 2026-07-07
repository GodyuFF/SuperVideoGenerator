"""将 MediaAsset 解析为 Agnes reference 生图可用的 URL。"""

from __future__ import annotations

from pathlib import Path

from core.edit.media_paths import local_media_to_data_url
from core.llm.tools.image.agnes_client import AgnesImageGenerationError
from core.llm.tools.shared.media_list import resolve_media_access
from core.store.memory import MemoryStore
from core.store.project_paths import parse_relative_media_path


def resolve_reference_url_for_media(
    store: MemoryStore,
    media_id: str,
) -> str:
    """返回 http(s) 或 data URL，供 reference 生图 API 使用。"""
    media = store.media_assets.get(media_id)
    if not media or not media.url:
        raise AgnesImageGenerationError(f"reference 媒体不存在：{media_id}")

    access = resolve_media_access(media.url)
    link = str(access.get("link") or "").strip()
    if link.startswith(("http://", "https://", "data:")):
        return link

    file_path = str(access.get("file_path") or "").strip()
    if file_path and Path(file_path).is_file():
        return local_media_to_data_url(Path(file_path))

    parsed = parse_relative_media_path(media.url)
    if parsed:
        from core.store.media_storage import absolute_media_path

        local = absolute_media_path(media.url)
        if local and local.is_file():
            return local_media_to_data_url(local)

    raise AgnesImageGenerationError(
        f"无法解析 reference 图片 URL（media_id={media_id}）"
    )
