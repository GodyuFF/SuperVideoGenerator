"""媒体资产 list_* 只读工具：构建 JSON 载荷与 URL/路径解析。"""

from __future__ import annotations

import json
from pathlib import Path, PureWindowsPath
from typing import Any
from urllib.parse import unquote, urlparse

from core.media.duration_probe import probe_media_duration_ms
from core.models.entities import MediaAsset, MediaAssetType
from core.store.memory import MemoryStore
from core.store.project_paths import export_api_path, media_api_path, parse_relative_export_path, parse_relative_media_path

_PROMPT_PREVIEW_LEN = 120


def is_placeholder_media_url(url: str) -> bool:
    """与 llm_action._is_placeholder_url 对齐：占位或未落盘 URL。"""
    u = url.strip().lower()
    if not u:
        return True
    if "example.com" in u:
        return True
    if u.startswith("/assets/"):
        return True
    if u.startswith("timeline://"):
        return True
    return False


def resolve_media_play_link(media: MediaAsset) -> str:
    """返回前端浏览器可请求的播放 URL（优先 /api/ 路径，避免 file://）。"""
    raw = (media.url or "").strip().replace("\\", "/")
    if not raw or is_placeholder_media_url(raw):
        return ""
    if raw.startswith("/api/"):
        return raw
    if raw.startswith(("http://", "https://")):
        return raw

    parsed = parse_relative_media_path(raw)
    if parsed:
        project_id, script_id, filename = parsed
        return media_api_path(project_id, script_id, filename)

    export_parsed = parse_relative_export_path(raw)
    if export_parsed:
        project_id, script_id, filename = export_parsed
        return export_api_path(project_id, script_id, filename)

    access = resolve_media_access(raw)
    file_path = str(access.get("file_path") or "").strip()
    if file_path and Path(file_path).is_file():
        filename = Path(file_path).name
        project_id = str(media.project_id or "").strip()
        script_id = str(media.script_id or "").strip()
        if project_id and script_id and filename:
            return media_api_path(project_id, script_id, filename)

    link = str(access.get("link") or "").strip()
    if link.startswith(("http://", "https://", "/api/")):
        return link
    return ""


def resolve_media_access(url: str) -> dict[str, Any]:
    """
    解析媒体 URL 的可访问信息。

    Returns:
        link: 可用于预览/下载的链接（http(s) 或相对 API 路径）
        file_path: 本地文件绝对路径（file:// 或本地路径时）
        is_accessible: 是否有非占位链接，或本地文件存在
        is_placeholder: 是否为占位 URL
    """
    raw = (url or "").strip()
    if is_placeholder_media_url(raw):
        return {
            "url": raw,
            "link": "",
            "file_path": "",
            "is_accessible": False,
            "is_placeholder": True,
        }

    link = ""
    file_path = ""

    if raw.lower().startswith("timeline://"):
        return {
            "url": raw,
            "link": "",
            "file_path": "",
            "is_accessible": False,
            "is_placeholder": True,
        }

    if raw.startswith(("http://", "https://")):
        link = raw
        return {
            "url": raw,
            "link": link,
            "file_path": "",
            "is_accessible": True,
            "is_placeholder": False,
        }

    parsed = parse_relative_media_path(raw)
    if parsed:
        project_id, script_id, filename = parsed
        from core.store.media_storage import absolute_media_path

        file_path_obj = absolute_media_path(raw)
        link = media_api_path(project_id, script_id, filename)
        file_path = str(file_path_obj.resolve()) if file_path_obj else ""
        return {
            "url": raw,
            "link": link,
            "file_path": file_path,
            "is_accessible": file_path_obj is not None,
            "is_placeholder": False,
        }

    export_parsed = parse_relative_export_path(raw)
    if export_parsed:
        project_id, script_id, filename = export_parsed
        from core.store.project_paths import absolute_export_path

        file_path_obj = absolute_export_path(raw)
        link = export_api_path(project_id, script_id, filename)
        file_path = str(file_path_obj.resolve()) if file_path_obj else ""
        return {
            "url": raw,
            "link": link,
            "file_path": file_path,
            "is_accessible": file_path_obj is not None,
            "is_placeholder": False,
        }

    if raw.startswith("file://"):
        parsed = urlparse(raw)
        file_path = unquote(parsed.path or "")
        if (
            file_path.startswith("/")
            and len(file_path) >= 3
            and file_path[2] == ":"
        ):
            file_path = file_path[1:]
        link = raw
        exists = bool(file_path) and Path(file_path).is_file()
        return {
            "url": raw,
            "link": link,
            "file_path": file_path,
            "is_accessible": exists,
            "is_placeholder": False,
        }

    if raw.startswith("/"):
        link = raw
        return {
            "url": raw,
            "link": link,
            "file_path": "",
            "is_accessible": True,
            "is_placeholder": False,
        }

    if PureWindowsPath(raw).drive or (len(raw) > 1 and raw[1] == ":"):
        file_path = str(Path(raw))
        link = Path(file_path).as_uri()
        return {
            "url": raw,
            "link": link,
            "file_path": file_path,
            "is_accessible": Path(file_path).is_file(),
            "is_placeholder": False,
        }

    link = raw
    as_path = Path(raw)
    if as_path.is_file():
        file_path = str(as_path.resolve())
        link = as_path.resolve().as_uri()
    return {
        "url": raw,
        "link": link,
        "file_path": file_path,
        "is_accessible": bool(link),
        "is_placeholder": False,
    }


def _preview(text: str, limit: int = _PROMPT_PREVIEW_LEN) -> str:
    t = text.strip()
    if len(t) <= limit:
        return t
    return t[: limit - 1] + "…"


def resolve_media_duration_ms(media: MediaAsset, access: dict[str, Any]) -> int | None:
    """解析媒体时长：metadata 与本地探测偏差大时以探测为准。"""
    meta = media.metadata or {}
    raw = meta.get("duration_ms")
    meta_ms = int(raw) if isinstance(raw, (int, float)) and raw > 0 else 0
    if media.type not in (MediaAssetType.AUDIO, MediaAssetType.VIDEO):
        return meta_ms if meta_ms > 0 else None
    file_path = str(access.get("file_path") or "").strip()
    if not file_path:
        return meta_ms if meta_ms > 0 else None
    probed = probe_media_duration_ms(file_path, media.type)
    if probed is None or probed <= 0:
        return meta_ms if meta_ms > 0 else None
    if meta_ms <= 0:
        return probed
    drift = abs(probed - meta_ms) / max(probed, 1)
    if drift > 0.05:
        return probed
    return meta_ms


def build_media_item(store: MemoryStore, media: MediaAsset) -> dict[str, Any]:
    access = resolve_media_access(media.url)
    play_link = resolve_media_play_link(media)
    item: dict[str, Any] = {
        "id": media.id,
        "name": media.name,
        "type": media.type.value,
        "status": media.status.value,
        "url": media.url,
        "link": play_link or access["link"],
        "file_path": access["file_path"],
        "is_accessible": access["is_accessible"],
        "is_placeholder": access["is_placeholder"],
        "source_asset_id": media.source_asset_id,
    }
    if media.source_asset_id:
        src = store.get_text_asset(media.source_asset_id)
        if src:
            item["source_asset_name"] = src.name
            item["source_asset_type"] = src.type.value
    meta = media.metadata or {}
    prompt = meta.get("generation_prompt") or meta.get("image_prompt")
    if isinstance(prompt, str) and prompt.strip():
        item["generation_prompt_preview"] = _preview(prompt)
    if meta.get("source_text_asset_id"):
        item["source_text_asset_id"] = meta["source_text_asset_id"]
    duration_ms = resolve_media_duration_ms(media, access)
    if duration_ms is not None and duration_ms > 0:
        item["duration_ms"] = duration_ms
    return item


def build_media_list_payload(
    store: MemoryStore,
    script_id: str,
    media_type: MediaAssetType,
) -> dict[str, Any]:
    """构建 list_images / list_videos 等只读工具的 JSON 结构。"""
    raw_items = store.list_media_for_script(script_id, media_type)
    items = [build_media_item(store, m) for m in raw_items]
    accessible = sum(1 for i in items if i.get("is_accessible"))
    payload: dict[str, Any] = {
        "script_id": script_id,
        "media_type": media_type.value,
        "count": len(items),
        "accessible_count": accessible,
        "items": items,
    }
    if not items:
        payload["message"] = f"当前无 {media_type.value} 类型媒体资产。"
    return payload


def format_media_list_payload(payload: dict[str, Any]) -> str:
    """序列化为 ReAct observation JSON 字符串。"""
    return json.dumps(payload, ensure_ascii=False, indent=2)


def format_media_list_summary(payload: dict[str, Any]) -> str:
    """人类可读摘要（供 legacy AgentToolExecutor）。"""
    if payload.get("count", 0) == 0:
        return str(payload.get("message", "当前无媒体资产。"))
    lines = [f"共 {payload['count']} 项 {payload.get('media_type', 'media')} 资产："]
    for item in payload.get("items", []):
        parts = [f"- {item.get('name', '?')} ({item.get('id', '')})"]
        if item.get("link"):
            parts.append(f"链接: {item['link']}")
        if item.get("file_path"):
            parts.append(f"文件: {item['file_path']}")
        if item.get("source_asset_name"):
            parts.append(
                f"来源: {item['source_asset_name']} ({item.get('source_asset_id', '')})"
            )
        if item.get("is_placeholder"):
            parts.append("[占位 URL，尚未生成真实文件]")
        elif not item.get("is_accessible"):
            parts.append("[链接不可用]")
        lines.append(" ".join(parts))
    return "\n".join(lines)
