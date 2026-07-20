"""共享图文资产 RAG 解析：reuse / fork / create_new 编排。"""

from __future__ import annotations

from typing import Any

from core.models.entities import (
    AssetReference,
    RelationType,
    TextAssetType,
)
from core.rag.async_bridge import run_coro_sync
from core.rag.embedder import Embedder, get_embedder, is_embedding_available
from core.rag.indexer import ensure_project_indexed_sync
from core.rag.models import ReuseDecision
from core.rag.name_match import find_shared_asset_by_name
from core.rag.query_builder import build_rag_query
from core.rag.retriever import retrieve_candidates
from core.store.memory import MemoryStore

_SHARED_CREATE_ACTIONS = frozenset({"create_character", "create_scene", "create_prop"})


def _reuse_existing(
    store: MemoryStore,
    *,
    script_id: str,
    existing: Any,
    reason: str,
) -> Any:
    """建立 RAG_REUSE 边并返回复用结果。"""
    from core.llm.agent.script_assets import CreateTextAssetOutcome, link_script_asset

    link_script_asset(
        store,
        script_id,
        existing.id,
        relation=RelationType.RAG_REUSE,
    )
    return CreateTextAssetOutcome(
        asset=existing,
        rag_decision="reuse",
        rag_reason=reason,
    )


async def resolve_shared_text_asset(
    store: MemoryStore,
    *,
    action: str,
    project_id: str,
    script_id: str,
    asset_name: str,
    content: Any,
    observation: str,
    embedder: Embedder | None = None,
    judge: Any | None = None,
) -> Any:
    """RAG 检索 + Judge 后复用、fork 或新建；无 embedding 时按名称精确匹配。"""
    from core.llm.agent.script_assets import (
        CreateTextAssetOutcome,
        _ACTION_TO_TYPE,
        _create_new_text_asset,
        merge_asset_content,
    )
    from core.llm.agent.asset_content import (
        normalize_asset_content,
        validate_create_content,
    )
    from core.assets.service import apply_character_tts_voice

    if action not in _SHARED_CREATE_ACTIONS:
        raise ValueError(f"RAG 解析不支持 action {action}")

    project = store.get_project(project_id)
    if project is None:
        raise ValueError(f"项目 {project_id} 不存在")
    rag_config = project.config.rag
    if not rag_config.enabled:
        asset = _create_new_text_asset(
            store,
            action=action,
            project_id=project_id,
            script_id=script_id,
            asset_name=asset_name,
            content=content,
            observation=observation,
            embedder=embedder,
        )
        return CreateTextAssetOutcome(asset=asset, rag_decision="create_new")

    asset_type = _ACTION_TO_TYPE[action]
    normalized = normalize_asset_content(
        content, action=action, observation=observation, strict=True
    )
    if asset_type == TextAssetType.CHARACTER:
        normalized = apply_character_tts_voice(normalized)
    validate_create_content(action, normalized)

    query = build_rag_query(
        project_id=project_id,
        script_id=script_id,
        asset_type=asset_type,
        asset_name=asset_name,
        content=normalized,
    )

    # 无 embedding Key：按规范化名称精确匹配，命中则 reuse，否则新建
    use_vector = embedder is not None or is_embedding_available()
    if not use_vector:
        matched = find_shared_asset_by_name(
            store,
            project_id=project_id,
            asset_type=asset_type,
            asset_name=asset_name,
        )
        if matched is not None:
            return _reuse_existing(
                store,
                script_id=script_id,
                existing=matched,
                reason=f"无 Embedding 配置，按名称复用「{matched.name}」",
            )
        asset = _create_new_text_asset(
            store,
            action=action,
            project_id=project_id,
            script_id=script_id,
            asset_name=asset_name,
            content=normalized,
            observation=observation,
            skip_validate=True,
            pre_normalized=normalized,
            embedder=None,
        )
        return CreateTextAssetOutcome(
            asset=asset,
            rag_decision="create_new",
            rag_reason="无 Embedding 配置且无同名共享资产，新建",
        )

    embedder = embedder or get_embedder()
    from core.rag.reuse_judge import get_reuse_judge

    judge = judge or get_reuse_judge()

    ensure_project_indexed_sync(store, project_id, embedder=embedder)
    sync_embed = getattr(embedder, "embed_sync", None)
    if callable(sync_embed):
        query_vector = sync_embed(query.requirement_text)
    else:
        query_vector = await embedder.embed(query.requirement_text)
    candidates = retrieve_candidates(store, query, query_vector, rag_config=rag_config)

    if not candidates:
        decision = ReuseDecision(
            requirement_summary=query.requirement_summary,
            decision="create_new",
            reason="无达到相似度阈值的候选",
            confidence=1.0,
        )
    else:
        decision = await judge.decide(
            store, query, candidates, rag_config=rag_config
        )

    if decision.decision == "reuse" and decision.selected_asset_id:
        existing = store.get_text_asset(decision.selected_asset_id)
        if existing is None:
            decision = ReuseDecision(
                requirement_summary=query.requirement_summary,
                decision="create_new",
                reason="候选资产不存在，回退新建",
                confidence=0.0,
            )
        else:
            return _reuse_existing(
                store,
                script_id=script_id,
                existing=existing,
                reason=decision.reason or f"复用共享资产 {existing.name}",
            )

    if decision.decision == "fork" and decision.selected_asset_id:
        original = store.get_text_asset(decision.selected_asset_id)
        if original is None:
            asset = _create_new_text_asset(
                store,
                action=action,
                project_id=project_id,
                script_id=script_id,
                asset_name=asset_name,
                content=content,
                observation=observation,
                embedder=embedder,
            )
            return CreateTextAssetOutcome(
                asset=asset,
                rag_decision="create_new",
                rag_reason="fork 候选不存在，回退新建",
            )
        fork_content = merge_asset_content(
            action, original.content, decision.fork_patch or normalized, observation
        )
        if asset_type == TextAssetType.CHARACTER:
            fork_content = apply_character_tts_voice(fork_content)
        asset = _create_new_text_asset(
            store,
            action=action,
            project_id=project_id,
            script_id=script_id,
            asset_name=asset_name,
            content=fork_content,
            observation=observation,
            skip_validate=True,
            pre_normalized=fork_content,
            embedder=embedder,
        )
        store.add_reference(
            AssetReference(
                source_id=asset.id,
                target_id=original.id,
                relation=RelationType.DERIVED_FROM,
                script_id=script_id,
            )
        )
        return CreateTextAssetOutcome(
            asset=asset,
            rag_decision="fork",
            rag_reason=decision.reason or f"派生自 {original.name}",
        )

    asset = _create_new_text_asset(
        store,
        action=action,
        project_id=project_id,
        script_id=script_id,
        asset_name=asset_name,
        content=normalized,
        observation=observation,
        skip_validate=True,
        pre_normalized=normalized,
        embedder=embedder,
    )
    return CreateTextAssetOutcome(
        asset=asset,
        rag_decision="create_new",
        rag_reason=decision.reason or "新建共享资产",
    )


def resolve_shared_text_asset_sync(
    store: MemoryStore,
    *,
    action: str,
    project_id: str,
    script_id: str,
    asset_name: str,
    content: Any,
    observation: str,
    embedder: Embedder | None = None,
    judge: Any | None = None,
) -> Any:
    """同步包装 RAG 解析（兼容已有 asyncio 事件循环）。"""
    return run_coro_sync(
        resolve_shared_text_asset(
            store,
            action=action,
            project_id=project_id,
            script_id=script_id,
            asset_name=asset_name,
            content=content,
            observation=observation,
            embedder=embedder,
            judge=judge,
        )
    )
