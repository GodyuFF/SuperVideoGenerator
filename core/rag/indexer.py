"""共享池文字资产的 embedding 索引维护。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from core.models.entities import AssetScope, TextAssetType
from core.rag.async_bridge import run_coro_sync
from core.rag.embedder import Embedder, get_embedder
from core.rag.query_builder import build_requirement_text
from core.rag.store import RagVectorStore, text_hash
from core.store.memory import MemoryStore

if TYPE_CHECKING:
    from core.models.entities import TextAsset

_INDEXABLE_TYPES = frozenset(
    {
        TextAssetType.CHARACTER,
        TextAssetType.SCENE,
        TextAssetType.PROP,
    }
)


class SyncEmbedder(Protocol):
    """支持同步向量化时避免嵌套 asyncio.run。"""

    def embed_sync(self, text: str) -> list[float]:
        ...


def _is_indexable(asset: TextAsset) -> bool:
    return asset.scope == AssetScope.PROJECT_SHARED and asset.type in _INDEXABLE_TYPES


def _embed_text(embedder: Embedder, text: str) -> list[float]:
    """优先同步 embedding；无 embed_sync 时经 run_coro_sync 安全跑异步 embed。"""
    sync = getattr(embedder, "embed_sync", None)
    if callable(sync):
        return sync(text)
    return run_coro_sync(embedder.embed(text))


def upsert_asset_embedding_sync(
    store: MemoryStore,
    asset: TextAsset,
    *,
    embedder: Embedder | None = None,
) -> None:
    """同步写入单条共享图文资产 embedding；无 Key 时跳过。"""
    if not _is_indexable(asset):
        return
    from core.rag.embedder import is_embedding_available

    if embedder is None and not is_embedding_available():
        return
    embedder = embedder or get_embedder()
    if hasattr(embedder, "has_api_key") and not embedder.has_api_key:
        return
    content_text = build_requirement_text(asset.name, asset.content, asset_type=asset.type)
    content_digest = text_hash(content_text)
    vector_store = RagVectorStore(asset.project_id)
    existing_hash = vector_store.get_hash(asset.id)
    if existing_hash == content_digest:
        if not asset.embedding_id:
            asset.embedding_id = asset.id
            store.update_text_asset(asset)
        return
    vector = _embed_text(embedder, content_text)
    vector_store.upsert(
        asset.id,
        asset.type.value,
        vector=vector,
        content_hash=content_digest,
    )
    asset.embedding_id = asset.id
    store.update_text_asset(asset)


async def upsert_asset_embedding(
    store: MemoryStore,
    asset: TextAsset,
    *,
    embedder: Embedder | None = None,
) -> None:
    """异步写入 embedding（委托同步实现）。"""
    upsert_asset_embedding_sync(store, asset, embedder=embedder)


def delete_asset_embedding_sync(project_id: str, asset_id: str) -> None:
    """同步删除 embedding。"""
    RagVectorStore(project_id).delete(asset_id)


async def delete_asset_embedding(project_id: str, asset_id: str) -> None:
    """异步删除 embedding。"""
    delete_asset_embedding_sync(project_id, asset_id)


async def reindex_project(
    store: MemoryStore,
    project_id: str,
    *,
    embedder: Embedder | None = None,
) -> None:
    """为项目内全部共享 character/scene/prop 补建索引。"""
    for asset in store.list_shared_assets(project_id):
        if _is_indexable(asset):
            upsert_asset_embedding_sync(store, asset, embedder=embedder)


def ensure_project_indexed_sync(
    store: MemoryStore,
    project_id: str,
    *,
    embedder: Embedder | None = None,
) -> None:
    """首次 RAG 前 lazy 补索引；无 Embedding Key 时跳过。"""
    from core.rag.embedder import is_embedding_available

    if embedder is None and not is_embedding_available():
        return
    vector_store = RagVectorStore(project_id)
    missing = [
        asset
        for asset in store.list_shared_assets(project_id)
        if _is_indexable(asset) and vector_store.get_hash(asset.id) is None
    ]
    if not missing:
        return
    embedder = embedder or get_embedder()
    for asset in missing:
        upsert_asset_embedding_sync(store, asset, embedder=embedder)


def on_shared_asset_updated(
    store: MemoryStore,
    asset: TextAsset,
    *,
    embedder: Embedder | None = None,
) -> None:
    """共享图文资产更新后同步向量索引。"""
    if _is_indexable(asset):
        upsert_asset_embedding_sync(store, asset, embedder=embedder)


def on_shared_asset_deleted(project_id: str, asset_id: str) -> None:
    """共享图文资产删除后移除向量索引。"""
    delete_asset_embedding_sync(project_id, asset_id)
