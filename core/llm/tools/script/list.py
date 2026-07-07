"""list_text_assets 只读工具：完整 JSON 载荷构建。"""

from __future__ import annotations

import json
from typing import Any

from core.models.entities import TextAssetType
from core.models.image_text_asset import (
    extract_traits,
    is_image_text_asset,
    normalize_image_text_content,
)
from core.store.memory import MemoryStore

_TEXT_ASSET_TYPES = frozenset({"character", "scene", "prop", "plot"})
_CONTENT_PREVIEW_LEN = 120


def _preview_text(text: str, limit: int = _CONTENT_PREVIEW_LEN) -> str:
    t = text.strip()
    if len(t) <= limit:
        return t
    return t[:limit] + "…"


def _normalize_content(asset: Any, store: MemoryStore) -> dict[str, Any]:
    if is_image_text_asset(asset.type):
        content = normalize_image_text_content(asset.type, asset.content)
        if not str(content.get("image_prompt", "")).strip():
            from core.assets.image_prompt import apply_composed_prompts

            project = store.get_project(asset.project_id)
            style = project.config.style if project else None
            content = apply_composed_prompts(
                asset.type, content, project_style=style, preserve_prompt_lock=True
            )
        return content
    content = asset.content
    if isinstance(content, dict):
        return dict(content)
    if isinstance(content, str) and content.strip():
        return {"text": content.strip()}
    return {}


def _shrink_content(
    asset_type: Any,
    content: dict[str, Any],
    *,
    include_content: bool,
) -> dict[str, Any]:
    if include_content:
        return content
    type_val = asset_type.value if hasattr(asset_type, "value") else str(asset_type)
    if type_val == TextAssetType.PLOT.value:
        text = str(content.get("text", "")).strip()
        return {"text": _preview_text(text)} if text else {}
    summary = str(content.get("summary", "")).strip()
    description = str(content.get("description", "")).strip()
    shrunk: dict[str, Any] = {}
    if summary:
        shrunk["summary"] = summary
    if description:
        shrunk["description"] = _preview_text(description)
    return shrunk


def _linked_media(store: MemoryStore, text_asset_id: str) -> list[dict[str, Any]]:
    from core.llm.tools.shared.media_list import build_media_item

    items: list[dict[str, Any]] = []
    for media in store.media_assets.values():
        if media.source_asset_id != text_asset_id:
            continue
        items.append(build_media_item(store, media))
    return items


def _is_linked(asset: Any, script_id: str, ref_map: dict[str, str]) -> bool:
    if asset.id in ref_map:
        return True
    return asset.script_id == script_id


def _counts_by_type(assets: list[dict[str, Any]]) -> dict[str, int]:
    counts = {t: 0 for t in sorted(_TEXT_ASSET_TYPES)}
    for item in assets:
        type_val = str(item.get("type", ""))
        if type_val in counts:
            counts[type_val] += 1
    return counts


def build_text_assets_list_payload(
    store: MemoryStore,
    script_id: str,
    *,
    types: list[str] | None = None,
    include_content: bool = True,
) -> dict[str, Any]:
    """构建 list_text_assets 的完整 JSON 结构（含剧本摘要与各资产 content）。"""
    script = store.get_script(script_id)
    if script is None:
        raise ValueError(f"剧本 {script_id} 不存在")

    type_filter: set[str] | None = None
    if types:
        type_filter = {t for t in types if t in _TEXT_ASSET_TYPES}
        if not type_filter:
            type_filter = set(_TEXT_ASSET_TYPES)

    assets = store.list_assets_for_script(script_id)
    refs = store.list_references_from(script_id)
    ref_map = {r.target_id: r.relation.value for r in refs}

    script_block: dict[str, Any] = {
        "id": script.id,
        "title": script.title,
        "duration_sec": script.duration_sec,
        "status": script.status.value,
        "content_md": script.content_md,
        "style_mode": script.style_mode.value if script.style_mode else None,
    }

    asset_items: list[dict[str, Any]] = []
    for asset in sorted(assets, key=lambda a: (a.type.value, a.name)):
        if type_filter and asset.type.value not in type_filter:
            continue
        full_content = _normalize_content(asset, store)
        content = _shrink_content(
            asset.type, full_content, include_content=include_content
        )
        item: dict[str, Any] = {
            "id": asset.id,
            "type": asset.type.value,
            "name": asset.name,
            "scope": asset.scope.value,
            "linked": _is_linked(asset, script_id, ref_map),
            "relation": ref_map.get(asset.id),
            "source_script_id": asset.source_script_id,
            "status": asset.status.value,
            "user_edited": asset.user_edited,
            "reuse_policy": asset.reuse_policy,
            "primary_media_id": asset.primary_media_id,
            "content": content,
        }
        if is_image_text_asset(asset.type):
            if include_content:
                item["traits"] = extract_traits(asset.type, full_content)
            item["linked_media"] = _linked_media(store, asset.id)
        asset_items.append(item)

    payload: dict[str, Any] = {
        "script_id": script_id,
        "script": script_block,
        "count": len(asset_items),
        "counts_by_type": _counts_by_type(asset_items),
        "assets": asset_items,
    }
    if payload["count"] == 0:
        payload["message"] = "当前无文字资产。"
    return payload


def format_text_assets_list_payload(payload: dict[str, Any]) -> str:
    """将已构建的 payload 序列化为 ReAct observation JSON 字符串。"""
    return json.dumps(payload, ensure_ascii=False, indent=2)


def format_text_assets_list(
    store: MemoryStore,
    script_id: str,
    *,
    types: list[str] | None = None,
    include_content: bool = True,
) -> str:
    """返回供 ReAct observation 使用的 JSON 字符串。"""
    payload = build_text_assets_list_payload(
        store, script_id, types=types, include_content=include_content
    )
    return format_text_assets_list_payload(payload)
