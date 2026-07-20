"""项目级 RAG 向量 SQLite 存储。"""

from __future__ import annotations

import hashlib
import math
import sqlite3
import struct
from pathlib import Path

from core.store.project_paths import rag_db_path


def _pack_vector(values: list[float]) -> bytes:
    """将 float 列表打包为 BLOB。"""
    return struct.pack(f"{len(values)}f", *values)


def _unpack_vector(blob: bytes) -> list[float]:
    """从 BLOB 解包 float 向量。"""
    count = len(blob) // 4
    return list(struct.unpack(f"{count}f", blob))


def _cosine(a: list[float], b: list[float]) -> float:
    """计算两向量余弦相似度。"""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def text_hash(text: str) -> str:
    """计算检索文本 SHA256 摘要。"""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class RagVectorStore:
    """单项目 embedding 索引的 SQLite 封装。"""

    def __init__(self, project_id: str) -> None:
        self._project_id = project_id
        self._path = rag_db_path(project_id)

    @property
    def path(self) -> Path:
        return self._path

    def _connect(self) -> sqlite3.Connection:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._path))
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS rag_embeddings (
                asset_id TEXT PRIMARY KEY,
                asset_type TEXT NOT NULL,
                text_hash TEXT NOT NULL,
                vector BLOB NOT NULL
            )
            """
        )
        conn.commit()
        return conn

    def upsert(
        self,
        asset_id: str,
        asset_type: str,
        *,
        vector: list[float],
        content_hash: str,
    ) -> None:
        """写入或更新单条 embedding。"""
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO rag_embeddings (asset_id, asset_type, text_hash, vector)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(asset_id) DO UPDATE SET
                    asset_type=excluded.asset_type,
                    text_hash=excluded.text_hash,
                    vector=excluded.vector
                """,
                (asset_id, asset_type, content_hash, _pack_vector(vector)),
            )
            conn.commit()

    def delete(self, asset_id: str) -> None:
        """删除单条 embedding。"""
        if not self._path.is_file():
            return
        with self._connect() as conn:
            conn.execute("DELETE FROM rag_embeddings WHERE asset_id = ?", (asset_id,))
            conn.commit()

    def get_hash(self, asset_id: str) -> str | None:
        """读取已索引内容的 text_hash。"""
        if not self._path.is_file():
            return None
        with self._connect() as conn:
            row = conn.execute(
                "SELECT text_hash FROM rag_embeddings WHERE asset_id = ?",
                (asset_id,),
            ).fetchone()
        return str(row[0]) if row else None

    def search(
        self,
        query_vector: list[float],
        *,
        asset_type: str,
        top_k: int,
        min_score: float,
    ) -> list[tuple[str, float]]:
        """按类型过滤并返回 Top-K (asset_id, score)。"""
        if not self._path.is_file():
            return []
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT asset_id, vector FROM rag_embeddings WHERE asset_type = ?",
                (asset_type,),
            ).fetchall()
        scored: list[tuple[str, float]] = []
        for asset_id, blob in rows:
            score = _cosine(query_vector, _unpack_vector(blob))
            if score >= min_score:
                scored.append((str(asset_id), score))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]
