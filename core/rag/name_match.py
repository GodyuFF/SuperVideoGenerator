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


def filter_shared_assets_by_name_query(
    assets: list[TextAsset],
    query: str,
) -> list[TextAsset]:
    """按规范化名称精确优先、子串其次过滤共享资产；无命中返回空列表。"""
    needle = normalize_asset_name(query)
    if not needle:
        return []
    exact: list[TextAsset] = []
    partial: list[TextAsset] = []
    for asset in assets:
        name_n = normalize_asset_name(asset.name)
        if name_n == needle:
            exact.append(asset)
        elif needle in name_n or name_n in needle:
            partial.append(asset)
    return exact + partial
