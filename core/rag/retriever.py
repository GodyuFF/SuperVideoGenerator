"""RAG 向量检索：硬规则过滤 + Top-K。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.models.entities import RagConfig
from core.models.image_text_asset import normalize_image_text_content
from core.rag.models import RagHit, RagQuery
from core.rag.store import RagVectorStore
from core.store.memory import MemoryStore

if TYPE_CHECKING:
    pass


def retrieve_candidates(
    store: MemoryStore,
    query: RagQuery,
    query_vector: list[float],
    *,
    rag_config: RagConfig,
) -> list[RagHit]:
    """在项目共享池中检索与查询最相似的 Top-K 候选。"""
    if query.asset_type not in rag_config.index_types:
        return []
    vector_store = RagVectorStore(query.project_id)
    raw_hits = vector_store.search(
        query_vector,
        asset_type=query.asset_type,
        top_k=rag_config.top_k,
        min_score=rag_config.similarity_threshold,
    )
    hits: list[RagHit] = []
    for asset_id, score in raw_hits:
        asset = store.get_text_asset(asset_id)
        if asset is None or asset.project_id != query.project_id:
            continue
        content = normalize_image_text_content(asset.type, asset.content)
        summary = str(content.get("summary", "")).strip() or asset.name
        preview = {
            key: content.get(key)
            for key in ("summary", "description", "role", "location", "category")
            if content.get(key)
        }
        hits.append(
            RagHit(
                asset_id=asset.id,
                name=asset.name,
                asset_type=asset.type.value,
                summary=summary,
                score=score,
                content_preview=preview,
            )
        )
    return hits
