"""无 embedding 时的共享资产名称匹配。"""

from __future__ import annotations

import re
import unicodedata

from core.models.entities import AssetScope, TextAsset, TextAssetType
from core.store.memory import MemoryStore

_WS_RE = re.compile(r"\s+")


def normalize_asset_name(name: str) -> str:
    """规范化资产名：去空白、NFKC、小写，便于跨剧本精确匹配。"""
    text = unicodedata.normalize("NFKC", (name or "").strip())
    text = _WS_RE.sub("", text)
    return text.casefold()


def find_shared_asset_by_name(
    store: MemoryStore,
    *,
    project_id: str,
    asset_type: TextAssetType,
    asset_name: str,
) -> TextAsset | None:
    """在项目共享池中按规范化名称精确匹配同类型资产。"""
    needle = normalize_asset_name(asset_name)
    if not needle:
        return None
    for asset in store.list_shared_assets(project_id):
        if asset.scope != AssetScope.PROJECT_SHARED:
            continue
        if asset.type != asset_type:
            continue
        if normalize_asset_name(asset.name) == needle:
            return asset
    return None
