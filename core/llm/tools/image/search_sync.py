"""image_agent search_images / sync_text_from_image handlers."""

from __future__ import annotations

import json
from typing import Any

from core.assets.image_prompt import compose_image_prompt
from core.edit.image_sync import (
    apply_auto_patch_to_content,
    build_sync_summary,
    needs_sync_from_image,
    split_image_observations,
)
from core.llm.agent.react_core import AgentRunContext
from core.llm.tools.image.scan import build_scan_text_assets_payload
from core.llm.tools.result import ToolResult
from core.llm.tools.web_search.service import search_web
from core.models.entities import MediaAssetType, RelationType, new_id
from core.models.entities import AssetReference, AssetStatus, MediaAsset
from core.models.image_text_asset import is_image_text_asset, normalize_image_text_content
from core.store.memory import MemoryStore
from core.store.persist import schedule_save


def _is_placeholder_url(url: str) -> bool:
    u = url.strip().lower()
    return not u or u.startswith("placeholder:") or "example.com" in u


def _persist_search_image(
    store: MemoryStore,
    *,
    project_id: str,
    script_id: str,
    source_text_asset_id: str,
    url: str,
    name: str,
    image_prompt: str = "",
) -> MediaAsset:
    from core.store.media_storage import persist_media_url_to_disk

    media = MediaAsset(
        id=new_id("media"),
        project_id=project_id,
        script_id=script_id,
        type=MediaAssetType.IMAGE,
        name=name,
        url=url,
        source_asset_id=source_text_asset_id,
        status=AssetStatus.GENERATED,
        metadata={
            "source": "search",
            "generation_prompt": image_prompt,
            "source_text_asset_id": source_text_asset_id,
        },
    )
    media.url = persist_media_url_to_disk(
        project_id=project_id,
        script_id=script_id,
        media_id=media.id,
        url=media.url,
        media_type=media.type.value,
    )
    store.add_media_asset(media)
    text = store.get_text_asset(source_text_asset_id)
    if text:
        from core.models.image_text_asset import (
            ensure_image_variants,
            get_base_variant,
            update_variant_in_content,
        )

        content = normalize_image_text_content(text.type, text.content)
        content = ensure_image_variants(content)
        base = get_base_variant(content)
        if base:
            content = update_variant_in_content(
                content, base.id, media_id=media.id, status="ready"
            )
            media.metadata["variant_id"] = base.id
            media.metadata["variant_kind"] = "base"
        text.content = content
        text.primary_media_id = media.id
        store.update_text_asset(text)
    store.add_reference(
        AssetReference(
            source_id=source_text_asset_id,
            target_id=media.id,
            relation=RelationType.GENERATES,
            script_id=script_id,
        )
    )
    return media


def handle_search_images(
    store: MemoryStore, ctx: AgentRunContext, args: dict[str, Any]
) -> ToolResult:
    """按 query 或 LLM 提供的 items 搜图并关联文字资产。"""
    script = store.get_script(ctx.script_id)
    if script is None:
        return ToolResult(observation="剧本不存在", ok=False)

    items = args.get("items")
    added = 0
    results: list[dict[str, Any]] = []

    if isinstance(items, list) and items:
        for raw in items:
            if not isinstance(raw, dict):
                continue
            url = str(raw.get("url", "")).strip()
            source_id = str(raw.get("source_text_asset_id", "")).strip()
            if not source_id or _is_placeholder_url(url):
                continue
            name = str(raw.get("name", "search_image"))
            prompt = str(raw.get("image_prompt", "")).strip()
            media = _persist_search_image(
                store,
                project_id=script.project_id,
                script_id=ctx.script_id,
                source_text_asset_id=source_id,
                url=url,
                name=name,
                image_prompt=prompt,
            )
            added += 1
            results.append({"media_id": media.id, "source_text_asset_id": source_id, "url": media.url})
    else:
        query = str(args.get("query", "")).strip()
        asset_id = str(args.get("asset_id", "")).strip()
        if not query and asset_id:
            asset = store.get_text_asset(asset_id)
            if asset:
                content = normalize_image_text_content(asset.type, asset.content)
                query = str(content.get("image_prompt") or content.get("summary") or asset.name)
        if not query:
            return ToolResult(observation="search_images 需要 query 或 items", ok=False)
        try:
            response = search_web(query, max_results=int(args.get("max_results", 5)))
        except (ValueError, RuntimeError) as e:
            return ToolResult(observation=str(e), ok=False)
        for hit in response.results[:3]:
            hit_data = hit.model_dump() if hasattr(hit, "model_dump") else hit
            url = str(hit_data.get("url", "") if isinstance(hit_data, dict) else hit.url)
            if _is_placeholder_url(url) or not asset_id:
                continue
            media = _persist_search_image(
                store,
                project_id=script.project_id,
                script_id=ctx.script_id,
                source_text_asset_id=asset_id,
                url=url,
                name=str((hit_data.get("title") if isinstance(hit_data, dict) else hit.title) or query)[:80],
            )
            added += 1
            title = hit_data.get("title") if isinstance(hit_data, dict) else hit.title
            results.append({"media_id": media.id, "url": media.url, "title": title})
            break

    schedule_save(store, immediate=True)
    obs = str(args.get("observation", "")).strip() or f"搜图完成，关联 {added} 张图片。"
    structured = {"added": added, "results": results}
    return ToolResult(observation=obs, structured=structured)


def handle_sync_text_from_image(
    store: MemoryStore, ctx: AgentRunContext, args: dict[str, Any]
) -> ToolResult:
    """根据实际图片观察回写文字资产（白名单自动 patch + 重大字段提示）。"""
    asset_id = str(args.get("asset_id", "")).strip()
    if not asset_id:
        return ToolResult(observation="sync_text_from_image 缺少 asset_id", ok=False)

    asset = store.get_text_asset(asset_id)
    if asset is None:
        return ToolResult(observation=f"文字资产 {asset_id} 不存在", ok=False)

    needs_sync, skip_reason = needs_sync_from_image(store, asset)
    if not needs_sync:
        obs = str(args.get("observation", "")).strip() or (
            f"文字资产 {asset.name}（{asset_id}）无需 sync_text_from_image：{skip_reason}。"
        )
        return ToolResult(
            observation=obs,
            structured={
                "asset_id": asset_id,
                "skipped": True,
                "skip_reason": skip_reason,
                "auto_patched": [],
                "major_pending": [],
                "major_applied": [],
            },
        )

    observations = args.get("image_observations") or args.get("patch") or {}
    if not isinstance(observations, dict):
        return ToolResult(observation="image_observations 必须为对象", ok=False)

    auto_patch, major, major_names = split_image_observations(observations)
    apply_major = bool(args.get("apply_major_changes"))
    allowed_major = _allowed_major_fields(args)
    if major and not apply_major:
        major = {k: v for k, v in major.items() if k in allowed_major}
        major_names = [k for k in major_names if k in major]

    content = normalize_image_text_content(asset.type, asset.content)
    if auto_patch:
        content = apply_auto_patch_to_content(asset.type, content, auto_patch)
    if major and apply_major:
        content = {**content, **major}
        if is_image_text_asset(asset.type):
            content["image_prompt"] = compose_image_prompt(asset.type, content)[0]

    asset.content = content
    if auto_patch or (major and apply_major):
        store.update_text_asset(asset)

    schedule_save(store, immediate=True)
    summary = build_sync_summary(
        asset,
        auto_patch,
        major_names,
        applied_major=bool(major and apply_major),
    )
    obs = str(args.get("observation", "")).strip() or summary
    return ToolResult(
        observation=obs,
        structured={
            "asset_id": asset_id,
            "skipped": False,
            "auto_patched": list(auto_patch.keys()),
            "major_pending": major_names if not apply_major else [],
            "major_applied": major_names if apply_major else [],
        },
    )


def _allowed_major_fields(args: dict[str, Any]) -> set[str]:
    if args.get("apply_major_changes"):
        return {"summary", "description", "text"}
    explicit = args.get("apply_fields")
    if isinstance(explicit, list):
        return {str(x) for x in explicit}
    return set()

