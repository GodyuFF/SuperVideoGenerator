"""scan_text_assets 写操作：待生图文字资产结构化扫描载荷。"""

from __future__ import annotations

import json
from typing import Any

from core.edit.image_sync import needs_sync_from_image
from core.llm.image_text_config import resolve_image_text_config
from core.llm.prompt.config import IMAGE_PROMPT_SUMMARY_MAX
from core.llm.tools.script.list import (
    _is_linked,
    _linked_media,
    _normalize_content,
)
from core.llm.tools.image.variants import (
    asset_needs_any_generation,
    build_variant_scan_rows,
)
from core.models.entities import MediaAssetType, TextAssetType
from core.store.memory import MemoryStore

_VISUAL_TYPES = frozenset(
    {
        TextAssetType.CHARACTER.value,
        TextAssetType.SCENE.value,
        TextAssetType.PROP.value,
    }
)


def _preview_prompt(text: str, limit: int = IMAGE_PROMPT_SUMMARY_MAX) -> str:
    t = text.strip()
    if len(t) <= limit:
        return t
    return t[: limit - 1] + "…"


def _is_placeholder_url(url: str) -> bool:
    u = url.strip()
    return not u or u.startswith("placeholder:")


def _media_item_status(store: MemoryStore, item: dict[str, Any]) -> str:
    url = str(item.get("url", "")).strip()
    if not url:
        return "missing"
    if _is_placeholder_url(url):
        return "placeholder"
    media = store.media_assets.get(str(item.get("id", "")))
    if media and media.type == MediaAssetType.IMAGE:
        return "ready"
    if item.get("type") == MediaAssetType.IMAGE.value and not _is_placeholder_url(url):
        return "ready"
    return "missing"


def _linked_media_with_status(
    store: MemoryStore, text_asset_id: str
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for raw in _linked_media(store, text_asset_id):
        url = str(raw.get("url", "")).strip()
        items.append(
            {
                **raw,
                "is_placeholder": _is_placeholder_url(url),
                "image_status": _media_item_status(store, raw),
            }
        )
    return items


def _resolve_image_status(
    store: MemoryStore, asset: Any, linked: list[dict[str, Any]]
) -> tuple[bool, str]:
    if asset.primary_media_id:
        media = store.media_assets.get(asset.primary_media_id)
        if media and media.type == MediaAssetType.IMAGE:
            url = str(media.url or "").strip()
            if url and not _is_placeholder_url(url):
                return True, "ready"
            if url and _is_placeholder_url(url):
                return False, "placeholder"
    for item in linked:
        if item.get("type") != MediaAssetType.IMAGE.value:
            continue
        status = str(item.get("image_status", "missing"))
        url = str(item.get("url", "")).strip()
        if status == "ready":
            return True, "ready"
        if url and _is_placeholder_url(url):
            return False, "placeholder"
    return False, "missing"


def build_scan_text_assets_payload(
    store: MemoryStore,
    script_id: str,
) -> dict[str, Any]:
    """扫描 character/scene/prop，返回待生图决策用 JSON。"""
    script = store.get_script(script_id)
    if script is None:
        raise ValueError(f"剧本 {script_id} 不存在")

    project = store.get_project(script.project_id)
    image_cfg = resolve_image_text_config(project)
    source_mode = image_cfg.source_mode.value
    project_style = project.config.style if project else None
    assets = store.list_assets_for_script(script_id)
    refs = store.list_references_from(script_id)
    ref_map = {r.target_id: r.relation.value for r in refs}

    script_block: dict[str, Any] = {
        "id": script.id,
        "title": script.title,
        "duration_sec": script.duration_sec,
        "status": script.status.value,
        "style_mode": script.style_mode.value if script.style_mode else None,
    }

    asset_items: list[dict[str, Any]] = []
    counts_by_type = {t: 0 for t in sorted(_VISUAL_TYPES)}
    pending_count = 0

    for asset in sorted(assets, key=lambda a: (a.type.value, a.name)):
        if asset.type.value not in _VISUAL_TYPES:
            continue
        content = _normalize_content(asset, store)
        image_prompt = str(content.get("image_prompt", "")).strip()
        linked = _linked_media_with_status(store, asset.id)
        variant_rows = build_variant_scan_rows(
            store, asset, project_style=project_style
        )
        has_prompt = any(v.get("has_image_prompt") for v in variant_rows) or bool(
            image_prompt
        )
        has_image, image_status = _resolve_image_status(store, asset, linked)
        needs_generation = asset_needs_any_generation(variant_rows)
        if not variant_rows:
            needs_generation = not has_image
        linked_image_id = None
        sync_pending = False
        if has_image:
            linked_image_id = asset.primary_media_id or (
                linked[0].get("id") if linked else None
            )
            if image_status == "ready" and linked_image_id:
                needs_sync, _ = needs_sync_from_image(store, asset)
                sync_pending = needs_sync

        pending_variants = sum(1 for v in variant_rows if v.get("needs_generation"))
        if needs_generation:
            pending_count += pending_variants or 1
        counts_by_type[asset.type.value] = counts_by_type.get(asset.type.value, 0) + 1

        asset_items.append(
            {
                "id": asset.id,
                "name": asset.name,
                "type": asset.type.value,
                "linked": _is_linked(asset, script_id, ref_map),
                "primary_media_id": asset.primary_media_id or None,
                "has_image_prompt": has_prompt,
                "image_prompt_preview": _preview_prompt(image_prompt) if has_prompt else "",
                "linked_media_count": len(linked),
                "linked_media": linked,
                "has_image": has_image,
                "image_status": image_status,
                "needs_generation": needs_generation,
                "source_mode": source_mode,
                "linked_image_id": linked_image_id,
                "sync_pending": sync_pending,
                "variants": variant_rows,
                "pending_variant_count": pending_variants,
            }
        )

    payload: dict[str, Any] = {
        "project_id": script.project_id,
        "script_id": script_id,
        "script": script_block,
        "source_mode": source_mode,
        "count": len(asset_items),
        "counts_by_type": counts_by_type,
        "pending_count": pending_count,
        "assets": asset_items,
    }
    if project:
        payload["project_title"] = project.title
    if payload["count"] == 0:
        payload["message"] = "当前无待生图文字资产（人物/场景/道具）。"
    return payload


def format_scan_text_assets_payload(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def format_scan_text_assets(store: MemoryStore, script_id: str) -> str:
    payload = build_scan_text_assets_payload(store, script_id)
    return format_scan_text_assets_payload(payload)
