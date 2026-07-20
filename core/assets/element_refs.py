"""element_refs 校验：桶与资产类型对齐、禁止环引用、生图拓扑序。"""

from __future__ import annotations

from typing import Any

from core.models.entities import TextAssetType
from core.models.image_text_asset import ImageTextAssetType
from core.store.memory import MemoryStore

ELEMENT_REF_BUCKETS: tuple[str, ...] = ("scene", "character", "prop", "frame", "video_clip")

BUCKET_TO_ASSET_TYPE: dict[str, TextAssetType] = {
    "scene": TextAssetType.SCENE,
    "character": TextAssetType.CHARACTER,
    "prop": TextAssetType.PROP,
    "frame": TextAssetType.FRAME,
    "video_clip": TextAssetType.VIDEO_CLIP,
}

ASSET_TYPE_TO_BUCKET: dict[str, str] = {
    ImageTextAssetType.SCENE.value: "scene",
    ImageTextAssetType.CHARACTER.value: "character",
    ImageTextAssetType.PROP.value: "prop",
    ImageTextAssetType.FRAME.value: "frame",
    TextAssetType.VIDEO_CLIP.value: "video_clip",
}

DEFAULT_FRAME_REFERENCE_ORDER: list[str] = ["scene", "character", "prop", "frame"]


def normalize_element_refs(raw: Any) -> dict[str, list[str]]:
    """将 element_refs 规范为 bucket → id 列表。"""
    if not isinstance(raw, dict):
        return {}
    out: dict[str, list[str]] = {}
    for bucket in ELEMENT_REF_BUCKETS:
        val = raw.get(bucket)
        if val is None:
            continue
        if isinstance(val, list):
            ids = [str(x).strip() for x in val if str(x).strip()]
        else:
            s = str(val).strip()
            ids = [s] if s else []
        if ids:
            out[bucket] = ids
    return out


def flatten_ref_ids(element_refs: dict[str, list[str]]) -> list[str]:
    """展开全部引用目标 ID（去重保序）。"""
    seen: set[str] = set()
    ordered: list[str] = []
    for bucket in ELEMENT_REF_BUCKETS:
        for tid in element_refs.get(bucket) or []:
            if tid not in seen:
                seen.add(tid)
                ordered.append(tid)
    return ordered


def validate_bucket_asset_types(store: MemoryStore, element_refs: dict[str, list[str]]) -> None:
    """每个桶内 ID 须为对应类型的文字资产。"""
    for bucket, ids in element_refs.items():
        if bucket not in BUCKET_TO_ASSET_TYPE:
            raise ValueError(f"不支持的 element_refs 桶: {bucket}")
        expected = BUCKET_TO_ASSET_TYPE[bucket]
        for tid in ids:
            asset = store.get_text_asset(tid)
            if not asset:
                raise ValueError(f"引用资产不存在: {tid}")
            if asset.type != expected:
                raise ValueError(
                    f"element_refs.{bucket} 仅允许 {expected.value} 资产，"
                    f"收到 {asset.type.value}: {tid}"
                )


def _refs_for_asset(store: MemoryStore, asset_id: str) -> list[str]:
    """读取文字资产 element_refs 中的全部目标 ID。"""
    asset = store.get_text_asset(asset_id)
    if not asset:
        return []
    content = asset.content if isinstance(asset.content, dict) else {}
    return flatten_ref_ids(normalize_element_refs(content.get("element_refs")))


def would_create_element_ref_cycle(
    store: MemoryStore,
    owner_id: str,
    element_refs: dict[str, list[str]],
) -> bool:
    """新增/更新 owner 的 element_refs 是否会形成环（owner 依赖链回到 owner）。"""
    owner_id = (owner_id or "").strip()
    if not owner_id:
        return False
    targets = flatten_ref_ids(element_refs)
    if owner_id in targets:
        return True

    def reaches_owner(current: str, visiting: set[str]) -> bool:
        if current == owner_id:
            return True
        if current in visiting:
            return False
        visiting.add(current)
        for nxt in _refs_for_asset(store, current):
            if reaches_owner(nxt, visiting):
                return True
        return False

    for tid in targets:
        if reaches_owner(tid, set()):
            return True
    return False


def validate_element_refs_for_owner(
    store: MemoryStore,
    owner_id: str | None,
    element_refs: dict[str, list[str]],
) -> None:
    """校验类型对齐且无环引用。"""
    refs = normalize_element_refs(element_refs)
    if not refs:
        return
    validate_bucket_asset_types(store, refs)
    oid = (owner_id or "").strip()
    if oid and would_create_element_ref_cycle(store, oid, refs):
        raise ValueError("element_refs 形成环引用，请移除循环依赖后再保存")


def topo_sort_assets_by_element_refs(
    store: MemoryStore,
    asset_ids: list[str],
) -> list[str]:
    """按 element_refs 依赖拓扑排序：被引用者先于引用者生成。"""
    ids = [str(i).strip() for i in asset_ids if str(i).strip()]
    if len(ids) <= 1:
        return ids
    id_set = set(ids)
    deps: dict[str, set[str]] = {aid: set() for aid in ids}
    for aid in ids:
        for ref in _refs_for_asset(store, aid):
            if ref in id_set:
                deps[aid].add(ref)
    ordered: list[str] = []
    remaining = set(ids)
    while remaining:
        ready = [aid for aid in remaining if not (deps[aid] & remaining)]
        if not ready:
            ordered.extend(sorted(remaining))
            break
        ready.sort()
        for aid in ready:
            ordered.append(aid)
            remaining.discard(aid)
    return ordered


def topo_sort_generation_items(
    store: MemoryStore,
    items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """对生图任务列表按 source_text_asset_id 的 element_refs 依赖排序。"""
    if len(items) <= 1:
        return items
    by_id: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for item in items:
        sid = str(item.get("source_text_asset_id", "")).strip()
        if not sid:
            continue
        by_id[sid] = item
        if sid not in order:
            order.append(sid)
    sorted_ids = topo_sort_assets_by_element_refs(store, order)
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for sid in sorted_ids:
        if sid in by_id and sid not in seen:
            out.append(by_id[sid])
            seen.add(sid)
    for item in items:
        sid = str(item.get("source_text_asset_id", "")).strip()
        if sid and sid in seen:
            continue
        out.append(item)
    return out
