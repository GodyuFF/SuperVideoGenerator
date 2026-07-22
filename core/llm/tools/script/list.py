"""list_text_assets / list_project_shared_assets 只读工具：JSON 载荷构建。"""

from __future__ import annotations

import json
from typing import Any

from core.guards.script_style import normalize_style_mode_id
from core.models.entities import AssetScope, TextAssetType
from core.models.image_text_asset import (
    extract_traits,
    is_image_text_asset,
    normalize_image_text_content,
)
from core.models.video_text_asset import is_video_text_asset, normalize_video_clip_content
from core.store.memory import MemoryStore

_TEXT_ASSET_TYPES = frozenset({"character", "scene", "prop", "plot", "frame", "video_clip"})
_SHARED_POOL_TYPES = frozenset({"character", "scene", "prop"})
_CONTENT_PREVIEW_LEN = 120


def _preview_text(text: str, limit: int = _CONTENT_PREVIEW_LEN) -> str:
    t = text.strip()
    if len(t) <= limit:
        return t
    return t[:limit] + "…"


def _normalize_content(asset: Any, store: MemoryStore) -> dict[str, Any]:
    if is_video_text_asset(asset.type.value):
        return normalize_video_clip_content(asset.content)
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
        "style_mode": normalize_style_mode_id(script.style_mode) if script.style_mode else None,
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


def _counts_shared_pool(assets: list[dict[str, Any]]) -> dict[str, int]:
    """统计共享池三类资产数量。"""
    counts = {t: 0 for t in sorted(_SHARED_POOL_TYPES)}
    for item in assets:
        type_val = str(item.get("type", ""))
        if type_val in counts:
            counts[type_val] += 1
    return counts


def _serialize_shared_asset_item(
    store: MemoryStore,
    asset: Any,
    *,
    script_id: str,
    ref_map: dict[str, str],
    include_content: bool,
) -> dict[str, Any]:
    """将单条项目共享资产序列化为 list 工具条目。"""
    full_content = _normalize_content(asset, store)
    content = _shrink_content(asset.type, full_content, include_content=include_content)
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
    return item


def _collect_shared_pool_assets(
    store: MemoryStore,
    project_id: str,
    type_filter: set[str],
) -> list[Any]:
    """收集项目共享池中符合类型过滤的资产。"""
    assets: list[Any] = []
    for asset in store.list_shared_assets(project_id):
        if asset.scope != AssetScope.PROJECT_SHARED:
            continue
        if asset.type.value not in type_filter:
            continue
        assets.append(asset)
    return assets


def _serialize_shared_pool(
    store: MemoryStore,
    script_id: str,
    assets: list[Any],
    *,
    ref_map: dict[str, str],
    include_content: bool,
    scores: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    """将共享资产列表序列化为工具条目，可选附带 score。"""
    items: list[dict[str, Any]] = []
    for asset in assets:
        item = _serialize_shared_asset_item(
            store,
            asset,
            script_id=script_id,
            ref_map=ref_map,
            include_content=include_content,
        )
        if scores is not None and asset.id in scores:
            item["score"] = scores[asset.id]
        items.append(item)
    return items


def _search_shared_by_embedding(
    store: MemoryStore,
    *,
    project_id: str,
    script_id: str,
    query: str,
    type_filter: set[str],
    embedder: Any,
) -> tuple[list[Any], dict[str, float]]:
    """按 query 向量检索共享池，返回资产与 score（降序）。"""
    from core.models.entities import TextAssetType
    from core.rag.indexer import ensure_project_indexed_sync
    from core.rag.models import RagQuery
    from core.rag.retriever import retrieve_candidates

    project = store.get_project(project_id)
    rag_config = project.config.rag if project is not None else None
    if rag_config is None:
        return [], {}

    ensure_project_indexed_sync(store, project_id, embedder=embedder)
    sync_embed = getattr(embedder, "embed_sync", None)
    if callable(sync_embed):
        query_vector = sync_embed(query)
    else:
        from core.rag.async_bridge import run_coro_sync

        query_vector = run_coro_sync(embedder.embed(query))

    scores: dict[str, float] = {}
    ordered_ids: list[str] = []
    for type_val in sorted(type_filter):
        asset_type = TextAssetType(type_val)
        rag_query = RagQuery(
            project_id=project_id,
            script_id=script_id,
            asset_type=type_val,  # type: ignore[arg-type]
            asset_name=query,
            requirement_summary=query,
            requirement_text=query,
        )
        for hit in retrieve_candidates(
            store, rag_query, query_vector, rag_config=rag_config
        ):
            if hit.asset_id in scores:
                if hit.score > scores[hit.asset_id]:
                    scores[hit.asset_id] = hit.score
                continue
            scores[hit.asset_id] = hit.score
            ordered_ids.append(hit.asset_id)

    ordered_ids.sort(key=lambda aid: scores.get(aid, 0.0), reverse=True)
    assets: list[Any] = []
    for aid in ordered_ids:
        asset = store.get_text_asset(aid)
        if asset is None:
            continue
        if asset.type.value not in type_filter:
            continue
        assets.append(asset)
    return assets, scores


def build_project_shared_assets_list_payload(
    store: MemoryStore,
    script_id: str,
    *,
    types: list[str] | None = None,
    include_content: bool = True,
    query: str | None = None,
    embedder: Any | None = None,
) -> dict[str, Any]:
    """构建项目共享池列表；可选 query 走 Embedding 或名称匹配。"""
    from core.rag.embedder import get_embedder, is_embedding_available
    from core.rag.name_match import filter_shared_assets_by_name_query

    script = store.get_script(script_id)
    if script is None:
        raise ValueError(f"剧本 {script_id} 不存在")

    type_filter: set[str] = set(_SHARED_POOL_TYPES)
    if types:
        type_filter = {t for t in types if t in _SHARED_POOL_TYPES}
        if not type_filter:
            type_filter = set(_SHARED_POOL_TYPES)

    refs = store.list_references_from(script_id)
    ref_map = {r.target_id: r.relation.value for r in refs}
    pool = _collect_shared_pool_assets(store, script.project_id, type_filter)
    q = (query or "").strip()

    match_mode = "full"
    fallback_full = False
    scores: dict[str, float] | None = None
    selected = sorted(pool, key=lambda a: (a.type.value, a.name))

    if q:
        use_vector = embedder is not None or is_embedding_available()
        if use_vector:
            active_embedder = embedder or get_embedder()
            selected, scores = _search_shared_by_embedding(
                store,
                project_id=script.project_id,
                script_id=script_id,
                query=q,
                type_filter=type_filter,
                embedder=active_embedder,
            )
            match_mode = "embedding"
        else:
            matched = filter_shared_assets_by_name_query(pool, q)
            match_mode = "name"
            if matched:
                selected = matched
            else:
                selected = sorted(pool, key=lambda a: (a.type.value, a.name))
                fallback_full = True

    asset_items = _serialize_shared_pool(
        store,
        script_id,
        selected,
        ref_map=ref_map,
        include_content=include_content,
        scores=scores,
    )

    payload: dict[str, Any] = {
        "project_id": script.project_id,
        "script_id": script_id,
        "match_mode": match_mode,
        "query": q,
        "count": len(asset_items),
        "counts_by_type": _counts_shared_pool(asset_items),
        "assets": asset_items,
    }
    if fallback_full:
        payload["fallback_full"] = True
    if payload["count"] == 0:
        payload["message"] = "项目共享池暂无角色/空镜/道具。"
    return payload


def format_project_shared_assets_list(
    store: MemoryStore,
    script_id: str,
    *,
    types: list[str] | None = None,
    include_content: bool = True,
    query: str | None = None,
) -> str:
    """返回项目共享池列表的 ReAct observation JSON。"""
    payload = build_project_shared_assets_list_payload(
        store,
        script_id,
        types=types,
        include_content=include_content,
        query=query,
    )
    return format_text_assets_list_payload(payload)
