"""图文资产 image_variants 扫描与生图任务收集。"""

from __future__ import annotations

from typing import Any

from core.assets.image_prompt import compose_base_image_prompt, compose_variant_image_prompt
from core.llm.tools.shared.media_list import is_placeholder_media_url, resolve_media_access
from core.models.entities import MediaAssetType, StyleConfig
from core.models.image_text_asset import (
    ImageVariant,
    ensure_image_variants,
    find_variant,
    get_base_variant,
    normalize_image_text_content,
    parse_image_variants,
)
from core.store.memory import MemoryStore


def _variant_media_ready(store: MemoryStore, media_id: str | None) -> tuple[bool, str]:
    if not media_id:
        return False, "missing"
    media = store.media_assets.get(media_id)
    if not media or media.type != MediaAssetType.IMAGE:
        return False, "missing"
    url = str(media.url or "").strip()
    if not url or is_placeholder_media_url(url):
        return False, "placeholder"
    access = resolve_media_access(url)
    if access.get("is_accessible"):
        return True, "ready"
    return False, "missing"


def build_variant_scan_rows(
    store: MemoryStore,
    asset: Any,
    *,
    project_style: StyleConfig | None = None,
) -> list[dict[str, Any]]:
    """为 scan 输出 variants[] 行。"""
    content = normalize_image_text_content(asset.type, asset.content)
    content = ensure_image_variants(content, primary_media_id=asset.primary_media_id)
    rows: list[dict[str, Any]] = []
    base = get_base_variant(content)
    for v in parse_image_variants(content):
        ready, status = _variant_media_ready(store, v.media_id)
        needs = not ready
        prompt = str(v.image_prompt).strip()
        if not prompt and v.kind == "base":
            prompt, _ = compose_base_image_prompt(
                asset.type, content, project_style=project_style
            )
        elif not prompt and v.kind != "base":
            prompt, _ = compose_variant_image_prompt(
                asset.type, content, v, project_style=project_style
            )
        ref_media: str | None = None
        if v.kind != "base" and v.reference_variant_id:
            ref_v = find_variant(content, v.reference_variant_id)
            if ref_v:
                ref_media = ref_v.media_id
        elif v.kind != "base" and base:
            ref_media = base.media_id
        ref_ready = True
        if v.kind != "base":
            ref_ready, _ = _variant_media_ready(store, ref_media)
            if not ref_ready:
                needs = True
        rows.append(
            {
                "id": v.id,
                "kind": v.kind,
                "label": v.label,
                "meaning": v.meaning,
                "media_id": v.media_id,
                "reference_variant_id": v.reference_variant_id
                or (base.id if base else ""),
                "reference_media_id": ref_media,
                "reference_ready": ref_ready,
                "image_status": status,
                "needs_generation": needs,
                "has_image_prompt": bool(prompt),
                "image_prompt_preview": prompt[:120] + ("…" if len(prompt) > 120 else ""),
            }
        )
    return rows


def asset_needs_any_generation(rows: list[dict[str, Any]]) -> bool:
    return any(r.get("needs_generation") for r in rows)


def collect_variant_generation_items(
    store: MemoryStore,
    script_id: str,
    *,
    asset_filter_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    """收集待生变体任务（含 variant_id / reference）。"""
    from core.llm.tools.image.scan import build_scan_text_assets_payload

    payload = build_scan_text_assets_payload(store, script_id)
    items: list[dict[str, Any]] = []
    for asset in payload.get("assets", []):
        if not isinstance(asset, dict):
            continue
        aid = str(asset.get("id", ""))
        if asset_filter_ids and aid not in asset_filter_ids:
            continue
        for row in asset.get("variants") or []:
            if not isinstance(row, dict):
                continue
            if not row.get("needs_generation"):
                continue
            if not row.get("has_image_prompt"):
                continue
            kind = str(row.get("kind", ""))
            if kind != "base" and not row.get("reference_ready"):
                continue
            src = store.get_text_asset(aid)
            if not src:
                continue
            content = normalize_image_text_content(src.type, src.content)
            content = ensure_image_variants(content, primary_media_id=src.primary_media_id)
            variant = find_variant(content, str(row.get("id", "")))
            if not variant:
                continue
            if variant.kind == "base":
                prompt, _ = compose_base_image_prompt(src.type, content)
            else:
                prompt, _ = compose_variant_image_prompt(src.type, content, variant)
            item: dict[str, Any] = {
                "source_text_asset_id": aid,
                "variant_id": variant.id,
                "variant_kind": variant.kind,
                "name": f"{src.name}-{variant.label or variant.kind}",
                "image_prompt": prompt,
            }
            if variant.kind != "base":
                ref_mid = str(row.get("reference_media_id", "")).strip()
                if ref_mid:
                    item["reference_media_id"] = ref_mid
            items.append(item)
    bases = [i for i in items if i.get("variant_kind") == "base"]
    derivs = [i for i in items if i.get("variant_kind") != "base"]
    return bases + derivs
