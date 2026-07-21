"""画面（frame）资产扫描与多参考图生图任务收集。"""

from __future__ import annotations

from typing import Any

from core.assets.image_prompt import compose_frame_image_prompt
from core.assets.linked_assets_prompt import merge_prompt_with_linked_assets
from core.llm.tools.image.variants import _variant_media_ready
from core.models.entities import StyleConfig, TextAssetType
from core.models.image_text_asset import normalize_image_text_content
from core.store.memory import MemoryStore

_ELEMENT_BUCKETS = ("scene", "character", "prop", "frame")
_DEFAULT_REFERENCE_ORDER = ["scene", "character", "prop", "frame"]


def _resolve_element_media_id(
    store: MemoryStore,
    text_asset_id: str,
    variant_refs: dict[str, str],
) -> str | None:
    text = store.get_text_asset(text_asset_id)
    if not text:
        return None
    content = normalize_image_text_content(text.type, text.content)
    vid = str(variant_refs.get(text_asset_id, "")).strip()
    if vid:
        from core.models.image_text_asset import resolve_variant_media_id

        mid = resolve_variant_media_id(content, vid)
        if mid:
            ready, _ = _variant_media_ready(store, mid)
            if ready:
                return mid
    if text.primary_media_id:
        ready, _ = _variant_media_ready(store, text.primary_media_id)
        if ready:
            return text.primary_media_id
    return None


def collect_reference_media_ids(
    store: MemoryStore,
    content: dict[str, Any],
) -> tuple[list[str], bool, str]:
    """按 reference_order 收集参考图 media_id；返回 (ids, all_ready, pending_reason)。"""
    element_refs = content.get("element_refs") or {}
    variant_refs = content.get("variant_refs") or {}
    order = content.get("reference_order") or list(_DEFAULT_REFERENCE_ORDER)
    media_ids: list[str] = []
    missing: list[str] = []

    for bucket in order:
        if bucket not in _ELEMENT_BUCKETS:
            continue
        ids = element_refs.get(bucket) or []
        if not isinstance(ids, list):
            ids = [ids]
        for tid in ids:
            tid_str = str(tid).strip()
            if not tid_str:
                continue
            mid = _resolve_element_media_id(store, tid_str, variant_refs)
            if mid:
                media_ids.append(mid)
            else:
                missing.append(f"{bucket}:{tid_str}")

    if missing:
        return media_ids, False, f"元素图未就绪: {', '.join(missing[:5])}"
    if not media_ids:
        return [], False, "element_refs 为空"
    return media_ids, True, ""


def build_frame_scan_row(
    store: MemoryStore,
    asset: Any,
    *,
    project_style: StyleConfig | None = None,
) -> dict[str, Any]:
    """单条 frame 资产的 scan 行。"""
    content = normalize_image_text_content(asset.type, asset.content)
    ref_ids, refs_ready, pending_reason = collect_reference_media_ids(store, content)
    has_image, image_status = _frame_image_status(store, asset)
    prompt = resolve_frame_generation_prompt(
        store, content, project_style=project_style
    )
    needs_generation = refs_ready and not has_image
    if not refs_ready:
        needs_generation = False
    return {
        "element_refs": content.get("element_refs") or {},
        "variant_refs": content.get("variant_refs") or {},
        "shot_id": content.get("shot_id") or "",
        "reference_media_ids": ref_ids,
        "references_ready": refs_ready,
        "pending_reason": pending_reason,
        "needs_generation": needs_generation,
        "has_image_prompt": bool(prompt),
        "image_prompt_preview": prompt[:120] + ("…" if len(prompt) > 120 else ""),
        "has_image": has_image,
        "image_status": image_status,
    }


def _frame_image_status(store: MemoryStore, asset: Any) -> tuple[bool, str]:
    if asset.primary_media_id:
        ready, status = _variant_media_ready(store, asset.primary_media_id)
        if ready:
            return True, "ready"
        if status == "placeholder":
            return False, "placeholder"
    for m in store.media_assets.values():
        if m.source_asset_id == asset.id and m.url:
            ready, status = _variant_media_ready(store, m.id)
            if ready:
                return True, "ready"
    return False, "missing"


def collect_frame_generation_items(
    store: MemoryStore,
    script_id: str,
    *,
    asset_filter_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    """收集待生成的 frame 图生图任务（元素参考图须已就绪）。"""
    project = store.get_script(script_id)
    project_style = None
    if project:
        proj = store.get_project(project.project_id)
        if proj:
            project_style = proj.config.style

    items: list[dict[str, Any]] = []
    for asset in store.list_assets_for_script(script_id):
        if asset.type != TextAssetType.FRAME:
            continue
        if asset_filter_ids and asset.id not in asset_filter_ids:
            continue
        content = normalize_image_text_content(asset.type, asset.content)
        ref_ids, refs_ready, pending_reason = collect_reference_media_ids(store, content)
        if not refs_ready:
            continue
        has_image, _ = _frame_image_status(store, asset)
        if has_image:
            continue
        prompt = resolve_frame_generation_prompt(
            store, content, project_style=project_style
        )
        if not prompt:
            continue
        items.append(
            {
                "source_text_asset_id": asset.id,
                "name": asset.name,
                "image_prompt": prompt,
                "asset_type": "frame",
                "reference_media_ids": ref_ids,
                "pending_reason": pending_reason,
            }
        )
    return items


def resolve_frame_generation_prompt(
    store: MemoryStore,
    content: dict[str, Any],
    *,
    project_style: StyleConfig | None = None,
) -> str:
    """
    生图用最终提示词：用户/锁存 image_prompt + 参考图说明置顶。

    无 image_prompt 时走 compose_frame_image_prompt（已含参考块 merge）。
    """
    authored = str(content.get("image_prompt", "")).strip()
    if not authored:
        prompt, _ = compose_frame_image_prompt(
            content, store=store, project_style=project_style
        )
        return prompt
    return merge_prompt_with_linked_assets(authored, store, content)
