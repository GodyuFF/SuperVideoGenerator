"""测试用确定性 Embedder：按文本哈希生成固定维度向量。"""

from __future__ import annotations

import hashlib
import math


class ScriptedEmbedder:
    """不发起 HTTP，用文本 hash 生成可重复的伪 embedding。"""

    def __init__(self, *, dimensions: int = 32) -> None:
        self._dimensions = dimensions

    async def embed(self, text: str) -> list[float]:
        """将单段文本转为 embedding 向量。"""
        return self.embed_sync(text)

    def embed_sync(self, text: str) -> list[float]:
        """同步生成归一化向量。"""
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        values: list[float] = []
        for i in range(self._dimensions):
            byte = digest[i % len(digest)]
            values.append((byte / 255.0) * 2.0 - 1.0)
        norm = math.sqrt(sum(v * v for v in values)) or 1.0
        return [v / norm for v in values]
