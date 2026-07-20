"""内置音效目录单元测试。"""

from __future__ import annotations

from core.sounds.builtin_catalog import get_builtin_sound, search_builtin_sounds
from core.sounds.service import _paginate, search_sound_effects
import pytest


def test_builtin_catalog_has_entries():
    """内置目录应包含多条可检索音效。"""
    hits = search_builtin_sounds("")
    assert len(hits) >= 10


def test_builtin_search_by_keyword():
    """关键词应匹配名称或标签。"""
    rain = search_builtin_sounds("rain")
    assert any("雨" in h.name or "rain" in h.tags for h in rain)


def test_get_builtin_sound_negative_id():
    """负 ID 可解析内置音效。"""
    entry = get_builtin_sound(-1)
    assert entry is not None
    assert entry.name


def test_paginate_builtin_results():
    """分页应返回 next 游标。"""
    items = [{"id": i} for i in range(5)]
    page1 = _paginate(items, page=1, page_size=2)
    assert len(page1["results"]) == 2
    assert page1["next"] == "2"
    assert page1["count"] == 5


@pytest.mark.asyncio
async def test_search_without_freesound_key_uses_builtin(monkeypatch):
    """未配置 Freesound Key 时应返回内置音效。"""
    monkeypatch.delenv("FREESOUND_API_KEY", raising=False)
    data = await search_sound_effects(query="click", page_size=10)
    assert data["source"] == "builtin"
    assert data["freesound_configured"] is False
    assert len(data["results"]) >= 1
    assert data["results"][0]["previewUrl"].startswith("/api/sounds/preview/")
